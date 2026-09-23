"""Live end-to-end verification of the Telegram -> Postgres -> dashboard -> AI flow.

This harness drives the REAL bot handlers against the REAL PostgreSQL, Redis
queue, worker and AI provider, and sends the bot's replies to the REAL admin
chat through the Telegram Bot API.

The single simulated part is the inbound direction: Telegram itself is the only
party that can deliver an update to `getUpdates`, so the update payloads are
built locally (identical in shape to Telegram's) and passed to `handle_update`.
Media bytes are likewise supplied locally because a real `file_id` only exists
for a file that was actually uploaded to Telegram.

Run inside the backend container:

    docker compose exec -T backend python scripts/e2e_telegram_live.py
"""

import asyncio
import base64
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

sys.path.insert(0, "/app")

from sqlalchemy import select, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.redis import close_redis, get_redis  # noqa: E402
from app.models import (  # noqa: E402
    AIGeneration,
    GenerationStatus,
    Job,
    JobStatus,
    Product,
    ProductMedia,
)
from app.services.telegram.client import TelegramClient  # noqa: E402
from app.services.telegram.handlers import (  # noqa: E402
    BotContext,
    handle_update,
)
from app.services.telegram.state import ConversationStore  # noqa: E402

# A 1x1 baseline JPEG, and a minimal ISO-BMFF (MP4) header.
JPEG_BYTES = base64.b64decode(
    "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRof"
    "Hh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAAB"
    "AAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q=="
)
MP4_BYTES = bytes.fromhex(
    "000000186674797069736f6d0000020069736f6d69736f32"
    "00000008667265650000002c6d646174"
)

E2E_PHOTO_ID = "e2e-photo-file-id"
E2E_VIDEO_ID = "e2e-video-file-id"

MEDIA_BYTES = {f"e2e/{E2E_PHOTO_ID}": JPEG_BYTES, f"e2e/{E2E_VIDEO_ID}": MP4_BYTES}

PRODUCT_NAME = "E2E Sepatu Olahraga Pro"

PASS: list[str] = []
FAIL: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    line = f"{label}{(' — ' + detail) if detail else ''}"
    (PASS if ok else FAIL).append(line)
    print(f"{'PASS' if ok else 'FAIL'}: {line}", flush=True)


class LiveTelegramClient(TelegramClient):
    """Real Bot API calls, with locally supplied bytes for synthesized uploads."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[dict] = []

    async def send_message(self, chat_id, text, *, reply_markup=None, parse_mode=None):
        self.sent.append({"text": text, "reply_markup": reply_markup})
        print(f"\n[BOT -> TELEGRAM {chat_id}] {text[:400]}", flush=True)
        return await super().send_message(
            chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode
        )

    async def answer_callback_query(self, callback_query_id, text=None):
        print(f"[BOT -> TELEGRAM callback] {text}", flush=True)
        return await super().answer_callback_query(callback_query_id, text)

    async def get_file(self, file_id: str) -> dict:
        return {"file_id": file_id, "file_path": f"e2e/{file_id}"}

    async def download_file(self, file_path: str) -> bytes:
        return MEDIA_BYTES[file_path]


def message_update(
    text_value=None, *, photo=False, video=False, update_id=1, user_id, chat_id
) -> dict:
    message = {
        "message_id": update_id,
        "date": int(time.time()),
        "chat": {"id": int(chat_id), "type": "private"},
        "from": {"id": int(user_id), "is_bot": False, "first_name": "Admin", "username": "admin"},
    }
    if text_value is not None:
        message["text"] = text_value
    if photo:
        message["photo"] = [
            {"file_id": "e2e-photo-small", "file_size": 128, "width": 90, "height": 90},
            {"file_id": E2E_PHOTO_ID, "file_size": len(JPEG_BYTES), "width": 1280, "height": 720},
        ]
    if video:
        message["video"] = {
            "file_id": E2E_VIDEO_ID,
            "file_size": len(MP4_BYTES),
            "mime_type": "video/mp4",
            "file_name": "../../../etc/passwd.mp4",
            "duration": 3,
            "width": 640,
            "height": 360,
        }
    return {"update_id": update_id, "message": message}


def callback_update(data: str, *, update_id=1, user_id, chat_id) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb-{update_id}",
            "from": {"id": int(user_id), "is_bot": False, "first_name": "Admin"},
            "message": {
                "message_id": update_id,
                "date": int(time.time()),
                "chat": {"id": int(chat_id), "type": "private"},
            },
            "data": data,
        },
    }


async def http_get(url: str, timeout: float = 30.0) -> tuple[int, str]:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            return response.status_code, response.text
    except Exception as exc:  # noqa: BLE001
        return 0, f"{type(exc).__name__}: {exc}"


async def main() -> int:
    admin_ids = sorted(settings.telegram_admin_user_ids)
    if not admin_ids:
        print("No TELEGRAM_ADMIN_USER_ID configured; cannot run the authorized flow.")
        return 2
    user_id = admin_ids[0]
    chat_id = user_id

    client = LiveTelegramClient()
    ctx = BotContext(
        client=client,
        session_factory=SessionLocal,
        store=ConversationStore(),
        settings=settings,
    )

    print("=" * 78)
    print(f"E2E admin user_id={user_id}  provider={settings.ai_provider}")
    print("=" * 78)

    # 1. commands ------------------------------------------------------------
    steps: list[dict] = [
        message_update("/start", update_id=1, user_id=user_id, chat_id=chat_id),
        message_update("/help", update_id=2, user_id=user_id, chat_id=chat_id),
    ]
    # 2. /add conversation ---------------------------------------------------
    field_values = [
        PRODUCT_NAME,
        "https://shopee.co.id/e2e-sepatu-olahraga-pro",
        "Rp 289.000",
        "28.900",
        "Fashion",
        "Pekerja kantoran dan pelari pemula",
        "Sepatu olahraga ringan dengan sol EVA dan upper mesh bernapas.",
    ]
    steps.append(message_update("/add", update_id=3, user_id=user_id, chat_id=chat_id))
    for index, value in enumerate(field_values, start=4):
        steps.append(message_update(value, update_id=index, user_id=user_id, chat_id=chat_id))

    # 3. media (photo + video) ----------------------------------------------
    steps.append(message_update(photo=True, update_id=11, user_id=user_id, chat_id=chat_id))
    steps.append(message_update(video=True, update_id=12, user_id=user_id, chat_id=chat_id))
    steps.append(message_update("/done", update_id=13, user_id=user_id, chat_id=chat_id))

    for update in steps:
        await handle_update(ctx, update)

    # 4. product persisted? --------------------------------------------------
    async with SessionLocal() as db:
        product = (
            await db.execute(
                select(Product)
                .where(Product.name == PRODUCT_NAME)
                .order_by(Product.created_at.desc())
            )
        ).scalars().first()
        media = []
        if product is not None:
            media = list(
                (
                    await db.execute(
                        select(ProductMedia).where(ProductMedia.product_id == product.id)
                    )
                ).scalars().all()
            )

    check("product persisted to PostgreSQL", product is not None)
    if product is None:
        print("Aborting: no product row.")
        return 1

    product_id = str(product.id)
    print(f"\nproduct_id={product_id} affiliate_url={product.affiliate_url}")

    check("affiliate URL stored", bool(product.affiliate_url))
    check("price parsed from 'Rp 289.000'", product.price == 289000.0, f"price={product.price}")
    check("commission parsed", product.commission == 28900.0, f"commission={product.commission}")
    check("category stored", product.category == "Fashion")
    check("target audience stored", bool(product.target_audience))
    check("description stored", bool(product.description))
    check("2 media rows stored", len(media) == 2, f"media={len(media)}")

    kinds = sorted(item.media_type.value for item in media)
    check("image + video stored", kinds == ["image", "video"], f"kinds={kinds}")
    check(
        "telegram filename never used as a path",
        all(".." not in item.file_path and "passwd" not in item.file_path for item in media),
        f"paths={[item.file_path for item in media]}",
    )
    check(
        "generated filenames are uuid-based",
        all(Path(item.file_path).stem and len(Path(item.file_path).stem) == 32 for item in media),
    )
    check(
        "media files exist on disk",
        all(Path("uploads", item.file_path).is_file() for item in media),
    )

    # 5. dashboard visibility -------------------------------------------------
    status, body = await http_get("http://localhost:8000/api/v1/products")
    check("products API returns the new product", status == 200 and PRODUCT_NAME in body, f"HTTP {status}")

    status, html = await http_get("http://frontend:3000/products", timeout=90)
    check(
        "dashboard /products renders the product (server-side fetch)",
        status == 200 and PRODUCT_NAME in html,
        f"HTTP {status}, len={len(html)}",
    )

    status, html = await http_get("http://frontend:3000/dashboard/products", timeout=90)
    check(
        "dashboard /dashboard/products route resolves",
        status in (200, 307),
        f"HTTP {status}",
    )

    # 6. AI generation through the existing pipeline --------------------------
    await handle_update(
        ctx, callback_update(f"ai:generate:{product_id}", update_id=20, user_id=user_id, chat_id=chat_id)
    )
    await handle_update(
        ctx,
        callback_update(
            f"ai:run:{product_id}:caption", update_id=21, user_id=user_id, chat_id=chat_id
        ),
    )

    async with SessionLocal() as db:
        record = (
            await db.execute(
                select(AIGeneration)
                .where(AIGeneration.product_id == UUID(product_id))
                .order_by(AIGeneration.created_at.desc())
            )
        ).scalars().first()

    check("AI generation record created via bot", record is not None)
    if record is None:
        return 1

    generation_id = str(record.id)
    check(
        "generation accepted by the queue (not failed)",
        record.status != GenerationStatus.failed,
        f"status={record.status.value} (worker may already have finished)",
    )
    check("generation carries the telegram chat for notification", str(record.notify_chat_id) == chat_id)
    check(
        "generation reuses the product's fields in the prompt",
        "Sepatu" in (record.prompt or "") and "Fashion" in (record.prompt or ""),
    )

    async with SessionLocal() as db:
        job = (
            await db.execute(
                select(Job).order_by(Job.created_at.desc()).limit(1)
            )
        ).scalars().first()
    check(
        "queue Job row created for the generation",
        job is not None and job.task == "generate_content" and job.queue == "default",
        f"task={getattr(job, 'task', None)} queue={getattr(job, 'queue', None)}",
    )

    depth = int(await get_redis().llen("affiliate:jobs:default"))
    print(f"\nredis jobs queue depth right after enqueue: {depth}")

    # 7. wait for the real worker container to finish the job -----------------
    print("\nwaiting for the worker container to process the job ...")
    deadline = time.time() + 90
    while time.time() < deadline:
        async with SessionLocal() as db:
            row = await db.get(AIGeneration, UUID(generation_id))
            state = row.status if row else None
        if state in (GenerationStatus.completed, GenerationStatus.failed):
            break
        await asyncio.sleep(1.5)

    async with SessionLocal() as db:
        row = await db.get(AIGeneration, UUID(generation_id))
    check(
        "worker completed the generation",
        row.status == GenerationStatus.completed,
        f"status={row.status.value} error={row.error_message}",
    )
    variations = ((row.result or {}).get("variations") or []) if row.result else []
    check("3 content variations produced", len(variations) == 3, f"variations={len(variations)}")
    check("generation stores the model used", bool(row.model), f"model={row.model}")
    check("generation has a completion timestamp", row.completed_at is not None)

    async with SessionLocal() as db:
        job = await db.get(Job, job.id)
    check(
        "queue Job reached 'succeeded'",
        job is not None and job.status == JobStatus.succeeded,
        f"status={getattr(job, 'status', None)}",
    )
    check("job was attempted exactly once", job is not None and job.attempts == 1, f"attempts={getattr(job, 'attempts', None)}")
    if variations:
        print("\nfirst variation:")
        print("  " + str(variations[0].get("text"))[:300])

    # 8. the bot pushes the result back to Telegram ---------------------------
    print("\nwaiting for the bot container to drain the notification queue ...")
    pending = 1
    deadline = time.time() + 40
    while time.time() < deadline:
        pending = int(await get_redis().llen("affiliate:notifications"))
        if pending == 0:
            break
        await asyncio.sleep(1)
    check(
        "completion notification drained by the bot (pushed to Telegram)",
        pending == 0,
        f"pending={pending}",
    )

    # 9. remaining commands ---------------------------------------------------
    await handle_update(ctx, message_update("/products", update_id=30, user_id=user_id, chat_id=chat_id))
    await handle_update(ctx, message_update("/stats", update_id=31, user_id=user_id, chat_id=chat_id))
    await handle_update(ctx, message_update("/tidakdikenal", update_id=32, user_id=user_id, chat_id=chat_id))

    # 10. authorization -------------------------------------------------------
    # A user id that never talked to the bot cannot be messaged: the rejection
    # must therefore be proven at the handler boundary, not on Telegram.
    before = len(client.sent)
    await handle_update(
        ctx,
        message_update("/start", update_id=40, user_id="424242", chat_id="424242"),
    )
    check(
        "unauthorized user rejected with a generic message",
        any("tidak memiliki akses" in m["text"] for m in client.sent[before:]),
        f"replies={[m['text'][:40] for m in client.sent[before:]]}",
    )

    # 11. state survives a restart -------------------------------------------
    await handle_update(ctx, message_update("/add", update_id=50, user_id=user_id, chat_id=chat_id))
    await handle_update(
        ctx, message_update("Produk Uji Restart", update_id=51, user_id=user_id, chat_id=chat_id)
    )
    fresh_store = ConversationStore()
    restored = await fresh_store.get(user_id)
    check(
        "conversation state persisted in Redis (survives restart)",
        restored is not None and restored.data.get("name") == "Produk Uji Restart",
        f"step={restored.step.value if restored else None}",
    )
    await handle_update(ctx, message_update("/cancel", update_id=52, user_id=user_id, chat_id=chat_id))

    # 12. secret leakage ------------------------------------------------------
    status, openapi = await http_get("http://localhost:8000/openapi.json")
    lowered = openapi.lower()
    check(
        "OpenAPI schema exposes no token / api key",
        settings.telegram_bot_token.lower() not in lowered
        and "telegram_bot_token" not in lowered
        and (not settings.ai_api_key or settings.ai_api_key.lower() not in lowered),
    )
    transcript = json.dumps(client.sent)
    check(
        "bot replies never echo the bot token",
        settings.telegram_bot_token not in transcript,
    )

    print("\n" + "=" * 78)
    print(f"PASSED {len(PASS)}  FAILED {len(FAIL)}")
    for item in FAIL:
        print(f"  FAIL: {item}")
    print("=" * 78)

    await close_redis()
    return 0 if not FAIL else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
