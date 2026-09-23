"""Telegram command and conversation handlers.

All logic lives here; the polling loop only fetches updates and delegates.
Handlers are dependency-injected via BotContext so they can be tested without
a live Telegram connection.
"""

import contextlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import Settings, settings as default_settings
from app.core.logging import get_logger
from app.models import (
    AIContentType,
    AIGeneration,
    AIPlatform,
    GenerationStatus,
    MediaType,
    Product,
    ProductMedia,
    ProductStatus,
)
from app.services import generation as generation_service
from app.services import media_storage, notifications
from app.services.media_storage import MediaError
from app.services.telegram import texts
from app.services.telegram.client import TelegramClient, TelegramError
from app.services.telegram.state import (
    ADD_STEPS,
    OPTIONAL_STEPS,
    AddStep,
    ConversationState,
    ConversationStore,
)

logger = get_logger(__name__)

MAX_NAME = 255
MAX_URL = 1024
MAX_CATEGORY = 128
MAX_AUDIENCE = 1000
MAX_DESCRIPTION = 2000
MAX_MEDIA_PER_PRODUCT = 10


@dataclass
class BotContext:
    client: TelegramClient
    session_factory: async_sessionmaker[AsyncSession]
    store: ConversationStore
    settings: Settings

    def is_authorized(self, user_id: str, chat_id: str) -> bool:
        users = self.settings.telegram_admin_user_ids
        chats = self.settings.telegram_admin_chat_ids
        # Secure by default: with no allow-list configured, nobody is allowed.
        if not users and not chats:
            return False
        return user_id in users or chat_id in chats


def build_default_context() -> BotContext:
    from app.core.database import SessionLocal

    return BotContext(
        client=TelegramClient(),
        session_factory=SessionLocal,
        store=ConversationStore(),
        settings=default_settings,
    )


# --- helpers ---------------------------------------------------------------


async def _send(
    ctx: BotContext,
    chat_id: str,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    try:
        await ctx.client.send_message(
            chat_id, text, reply_markup=reply_markup, parse_mode="Markdown"
        )
    except TelegramError as exc:
        if reply_markup is None:
            logger.warning("Failed to send telegram message: %s", exc)
            return
        # Telegram validates inline-keyboard URLs and rejects the whole message
        # when one is not publicly reachable (a `localhost` FRONTEND_BASE_URL,
        # for instance). The confirmation text matters more than the buttons, so
        # retry once without the keyboard instead of losing the message.
        logger.warning("Telegram rejected the keyboard (%s); retrying without it", exc)
        try:
            await ctx.client.send_message(chat_id, text, parse_mode="Markdown")
        except TelegramError as retry_exc:
            logger.warning("Failed to send telegram message: %s", retry_exc)


def _parse_amount(raw: str) -> float:
    """Parse '150000', '150.000', '150,5', 'Rp 150000' into a float.

    Indonesian formatting uses '.' for thousands and ',' for decimals, so we
    disambiguate rather than assuming a C locale.
    """
    cleaned = raw.strip().lower().replace("rp", "").replace("idr", "").strip()
    cleaned = cleaned.replace(" ", "")
    if not cleaned:
        raise ValueError("kosong")

    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    elif "." in cleaned:
        parts = cleaned.split(".")
        # '150.000' -> thousands; '150.50' -> decimal
        if len(parts) > 2 or len(parts[-1]) == 3:
            cleaned = cleaned.replace(".", "")

    value = float(cleaned)
    if value < 0:
        raise ValueError("negatif")
    if value > 999_999_999_999:
        raise ValueError("terlalu besar")
    return round(value, 2)


def _validate_step_value(step: AddStep, raw: str) -> tuple[str | float | None, str | None]:
    """Return (value, error). Value None means 'leave unset'."""
    text = raw.strip()

    if step == AddStep.name:
        if len(text) < 2:
            return None, "Nama produk minimal 2 karakter. Coba lagi."
        if len(text) > MAX_NAME:
            return None, f"Nama produk maksimal {MAX_NAME} karakter. Coba lagi."
        return text, None

    if step == AddStep.affiliate_url:
        if not text.lower().startswith(("http://", "https://")):
            return None, "URL harus diawali `http://` atau `https://`. Coba lagi."
        if "." not in text or len(text) > MAX_URL:
            return None, "URL tidak valid. Coba lagi."
        return text, None

    if step in (AddStep.price, AddStep.commission):
        try:
            return _parse_amount(text), None
        except ValueError:
            return None, "Angka tidak valid. Kirim angka saja, contoh `150000`."

    if step == AddStep.category:
        if len(text) > MAX_CATEGORY:
            return None, f"Kategori maksimal {MAX_CATEGORY} karakter."
        return text, None

    if step == AddStep.target_audience:
        if len(text) > MAX_AUDIENCE:
            return None, f"Target audiens maksimal {MAX_AUDIENCE} karakter."
        return text, None

    if step == AddStep.description:
        if len(text) > MAX_DESCRIPTION:
            return None, f"Deskripsi maksimal {MAX_DESCRIPTION} karakter."
        return text, None

    return text, None


async def _prompt_current_step(ctx: BotContext, chat_id: str, state: ConversationState) -> None:
    if state.step == AddStep.media:
        await _send(ctx, chat_id, texts.MEDIA_HINT, texts.media_buttons())
        return
    await _send(
        ctx,
        chat_id,
        texts.STEP_PROMPTS[state.step],
        texts.skip_buttons(state.step),
    )


async def _advance(
    ctx: BotContext, chat_id: str, user_id: str, state: ConversationState
) -> None:
    index = ADD_STEPS.index(state.step)
    if index + 1 >= len(ADD_STEPS):
        await _finalize_product(ctx, chat_id, user_id, state)
        return
    state.step = ADD_STEPS[index + 1]
    await ctx.store.save(state)
    await _prompt_current_step(ctx, chat_id, state)


# --- command handlers ------------------------------------------------------


async def handle_start(ctx: BotContext, chat_id: str, user_id: str) -> None:
    await _send(ctx, chat_id, texts.WELCOME_TEXT)


async def handle_help(ctx: BotContext, chat_id: str, user_id: str) -> None:
    await _send(ctx, chat_id, texts.HELP_TEXT)


async def handle_add(ctx: BotContext, chat_id: str, user_id: str) -> None:
    await ctx.store.clear(user_id)
    state = ConversationState(user_id=user_id, step=AddStep.name, data={})
    await ctx.store.save(state)
    await _send(
        ctx,
        chat_id,
        "🆕 *Tambah produk baru*\n\nKita akan mengisi data bertahap. "
        "Ketik /cancel kapan saja untuk membatalkan.",
    )
    await _prompt_current_step(ctx, chat_id, state)


async def handle_cancel(ctx: BotContext, chat_id: str, user_id: str) -> None:
    state = await ctx.store.get(user_id)
    await ctx.store.clear(user_id)
    if state is None:
        await _send(ctx, chat_id, texts.NO_ACTIVE_FLOW_TEXT)
        return
    await _send(ctx, chat_id, "❌ Proses dibatalkan. Data tidak disimpan.")


async def handle_products(ctx: BotContext, chat_id: str, user_id: str) -> None:
    async with ctx.session_factory() as db:
        stmt = (
            select(Product)
            .options(selectinload(Product.media))
            .order_by(Product.created_at.desc())
            .limit(10)
        )
        products = list((await db.execute(stmt)).scalars().all())

    if not products:
        await _send(ctx, chat_id, "📦 Belum ada produk. Kirim /add untuk menambahkan.")
        return

    lines = ["📦 *Produk terakhir:*", ""]
    for product in products:
        price = f"Rp{product.price:,.0f}" if product.price is not None else "-"
        media_count = len(product.media)
        lines.append(
            f"• *{texts.escape_md(product.name)}*\n"
            f"  💰 {price} | 🏷️ {texts.escape_md(product.status.value)} | "
            f"🖼️ {media_count} media"
        )
    lines.append("")
    lines.append("Kirim /add untuk menambah produk baru.")
    await _send(ctx, chat_id, "\n".join(lines))


async def handle_stats(ctx: BotContext, chat_id: str, user_id: str) -> None:
    async with ctx.session_factory() as db:
        products = await db.scalar(select(func.count()).select_from(Product)) or 0
        media = await db.scalar(select(func.count()).select_from(ProductMedia)) or 0
        rows = await db.execute(
            select(AIGeneration.status, func.count())
            .group_by(AIGeneration.status)
        )
        by_status = {status.value: count for status, count in rows.all()}

    queued = by_status.get(GenerationStatus.queued.value, 0)
    processing = by_status.get(GenerationStatus.processing.value, 0)
    completed = by_status.get(GenerationStatus.completed.value, 0)
    failed = by_status.get(GenerationStatus.failed.value, 0)

    text = (
        "📊 *Statistik*\n\n"
        f"📦 Produk: *{products}*\n"
        f"🖼️ Media: *{media}*\n\n"
        "📈 Analytics not available yet.\n\n"
        "*Generasi AI:*\n"
        f"⏳ Queued: {queued}\n"
        f"⚙️ Processing: {processing}\n"
        f"✅ Completed: {completed}\n"
        f"❌ Failed: {failed}"
    )
    await _send(ctx, chat_id, text)


# --- /add conversation -----------------------------------------------------


async def _handle_conversation_text(
    ctx: BotContext, chat_id: str, user_id: str, state: ConversationState, text: str
) -> None:
    stripped = text.strip()

    if stripped.lower() == texts.SKIP_COMMAND:
        if state.step not in OPTIONAL_STEPS:
            await _send(ctx, chat_id, "⚠️ Kolom ini wajib diisi dan tidak bisa di-skip.")
            return
        await _advance(ctx, chat_id, user_id, state)
        return

    if state.step == AddStep.media:
        await _send(ctx, chat_id, texts.MEDIA_HINT, texts.media_buttons())
        return

    value, error = _validate_step_value(state.step, stripped)
    if error:
        await _send(ctx, chat_id, f"⚠️ {error}")
        return

    state.data[state.step.value] = value
    await _advance(ctx, chat_id, user_id, state)


async def _handle_media_message(
    ctx: BotContext, chat_id: str, user_id: str, state: ConversationState, message: dict
) -> None:
    if state.step != AddStep.media:
        await _send(ctx, chat_id, "ℹ️ Media hanya diminta pada langkah terakhir /add.")
        return

    media_items = state.data.setdefault("media", [])
    if len(media_items) >= MAX_MEDIA_PER_PRODUCT:
        await _send(
            ctx,
            chat_id,
            f"⚠️ Maksimal {MAX_MEDIA_PER_PRODUCT} media per produk. Ketik /done.",
        )
        return

    candidate: dict[str, Any] | None = None
    if message.get("photo") is not None:
        photos = message.get("photo") or []
        if not isinstance(photos, list) or not photos:
            await _send(ctx, chat_id, "⚠️ Kirim foto atau video yang valid.")
            return
        largest = max(photos, key=lambda p: p.get("file_size") or 0)
        candidate = {
            "kind": MediaType.image.value,
            "file_id": largest.get("file_id"),
            "mime": "image/jpeg",  # Telegram photos are always JPEG
            "size": largest.get("file_size"),
            "filename": None,
        }
    elif message.get("video") is not None:
        video = message["video"]
        candidate = {
            "kind": MediaType.video.value,
            "file_id": video.get("file_id"),
            "mime": video.get("mime_type"),
            "size": video.get("file_size"),
            "filename": video.get("file_name"),
        }

    if candidate is None or not candidate.get("file_id"):
        await _send(ctx, chat_id, "⚠️ Kirim foto atau video yang valid.")
        return

    # Validate before downloading so the user gets immediate feedback.
    try:
        media_storage.validate_declared_size(candidate.get("size"))
        mime, resolved_type = media_storage.validate_mime(candidate.get("mime"))
    except MediaError as exc:
        await _send(ctx, chat_id, f"⚠️ {exc}\n\nCoba kirim file lain.")
        return

    candidate["mime"] = mime
    candidate["kind"] = resolved_type.value
    media_items.append(candidate)

    if resolved_type == MediaType.image:
        state.images += 1
    else:
        state.videos += 1
    await ctx.store.save(state)

    await _send(
        ctx,
        chat_id,
        f"✅ Media diterima ({resolved_type.value}). "
        f"Total: {state.images} gambar, {state.videos} video.\n"
        "Kirim media lain atau ketik /done.",
        texts.media_buttons(),
    )


async def _handle_done(ctx: BotContext, chat_id: str, user_id: str, state: ConversationState) -> None:
    if state.step != AddStep.media:
        await _send(ctx, chat_id, "ℹ️ Belum waktunya menyelesaikan. Ikuti langkah yang diminta.")
        return
    media_items = state.data.get("media") or []
    if not media_items:
        await _send(
            ctx,
            chat_id,
            "⚠️ Minimal 1 media (foto atau video) diperlukan.\n" + texts.MEDIA_HINT,
            texts.media_buttons(),
        )
        return
    await _finalize_product(ctx, chat_id, user_id, state)


async def _finalize_product(
    ctx: BotContext, chat_id: str, user_id: str, state: ConversationState
) -> None:
    data = state.data
    media_items: list[dict[str, Any]] = data.get("media") or []

    try:
        async with ctx.session_factory() as db:
            product = Product(
                name=data.get("name"),
                affiliate_url=data.get("affiliate_url"),
                price=data.get("price"),
                commission=data.get("commission"),
                category=data.get("category"),
                target_audience=data.get("target_audience"),
                description=data.get("description"),
                currency="IDR",
                status=ProductStatus.active,
                metadata_={"source": "telegram", "telegram_user_id": user_id},
            )
            db.add(product)
            await db.flush()

            stored, failed = await _download_media(ctx, db, product, media_items)

            if failed:
                product.metadata_ = {
                    **(product.metadata_ or {}),
                    "pending_media": [item for item, _ in failed],
                }
            await db.commit()
            product_id = product.id
    except Exception:  # noqa: BLE001
        logger.exception("Failed to save product from telegram")
        await _send(
            ctx,
            chat_id,
            "❌ Gagal menyimpan produk karena masalah database.\n"
            "Data percakapan masih tersimpan — coba /done lagi sebentar.",
        )
        return

    await ctx.store.clear(user_id)
    await ctx.store.set_last_product(user_id, str(product_id))

    lines = [
        "✅ *Product added*",
        "",
        f"*Product:* {texts.escape_md(data.get('name'))}",
        f"*Affiliate URL:* {texts.escape_md(data.get('affiliate_url') or '-')}",
    ]
    if data.get("price") is not None:
        lines.append(f"*Price:* Rp{data['price']:,.0f}")
    if data.get("commission") is not None:
        lines.append(f"*Commission:* Rp{data['commission']:,.0f}")
    if data.get("category"):
        lines.append(f"*Category:* {texts.escape_md(data['category'])}")
    if data.get("target_audience"):
        lines.append(f"*Target audience:* {texts.escape_md(data['target_audience'])}")
    lines.append(f"*Media:* {len(stored)} file tersimpan")

    if failed:
        lines.append("")
        lines.append(f"⚠️ {len(failed)} media gagal diunduh:")
        for _, error in failed:
            lines.append(f"• {texts.escape_md(error)}")

    keyboard = texts.product_actions(str(product_id))
    if failed:
        keyboard = texts.product_actions_with_media_retry(str(product_id))

    await _send(ctx, chat_id, "\n".join(lines), keyboard)


async def _download_media(
    ctx: BotContext,
    db: AsyncSession,
    product: Product,
    media_items: list[dict[str, Any]],
) -> tuple[list[ProductMedia], list[tuple[dict[str, Any], str]]]:
    stored: list[ProductMedia] = []
    failed: list[tuple[dict[str, Any], str]] = []

    for item in media_items:
        try:
            file_info = await ctx.client.get_file(item["file_id"])
            file_path = file_info.get("file_path")
            if not file_path:
                raise MediaError("Telegram tidak memberikan lokasi file.")
            data = await ctx.client.download_file(file_path)
            saved = media_storage.save_bytes(
                data=data,
                product_id=product.id,
                mime=item.get("mime"),
                original_filename=item.get("filename"),
            )
            record = ProductMedia(
                product_id=product.id,
                media_type=saved.media_type,
                file_path=saved.file_path,
                mime_type=saved.mime_type,
                file_size=saved.file_size,
                source="telegram",
                telegram_file_id=item["file_id"],
                original_filename=saved.original_filename,
            )
            db.add(record)
            stored.append(record)
        except MediaError as exc:
            failed.append((item, str(exc)))
        except TelegramError as exc:
            failed.append((item, f"Telegram error: {exc}"))
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected media download failure")
            failed.append((item, "Kesalahan tak terduga saat mengunduh media."))

    return stored, failed


async def retry_pending_media(ctx: BotContext, chat_id: str, product_id: str) -> None:
    """Retry media downloads that failed during product creation."""
    async with ctx.session_factory() as db:
        product = await db.get(Product, UUID(product_id))
        if product is None:
            await _send(ctx, chat_id, "❌ Produk tidak ditemukan.")
            return
        pending = list((product.metadata_ or {}).get("pending_media") or [])
        if not pending:
            await _send(ctx, chat_id, "ℹ️ Tidak ada media yang perlu diulang.")
            return

        stored, failed = await _download_media(ctx, db, product, pending)
        metadata = dict(product.metadata_ or {})
        if failed:
            metadata["pending_media"] = [item for item, _ in failed]
        else:
            metadata.pop("pending_media", None)
        product.metadata_ = metadata
        await db.commit()

    if failed:
        details = "\n".join(f"• {error}" for _, error in failed)
        await _send(ctx, chat_id, f"⚠️ Sebagian media masih gagal:\n{details}")
    else:
        await _send(ctx, chat_id, f"✅ {len(stored)} media berhasil diunduh ulang.")


# --- AI actions ------------------------------------------------------------


def _build_generation_prompt(product: Product, content_type: AIContentType) -> str:
    parts = [f"Buat {content_type.value.replace('_', ' ')} untuk produk {product.name}."]
    if product.category:
        parts.append(f"Kategori: {product.category}.")
    if product.target_audience:
        parts.append(f"Target audiens: {product.target_audience}.")
    if product.description:
        parts.append(f"Deskripsi produk: {product.description}")
    prompt = " ".join(parts).strip()
    return prompt[:2000]


async def _trigger_generation(
    ctx: BotContext,
    chat_id: str,
    product_id: str,
    content_type: AIContentType,
    *,
    variations: int = 3,
) -> None:
    async with ctx.session_factory() as db:
        product = await db.get(Product, UUID(product_id))
        if product is None:
            await _send(ctx, chat_id, "❌ Produk tidak ditemukan.")
            return

        prompt = _build_generation_prompt(product, content_type)
        try:
            record = await generation_service.create_generation_record(
                db,
                prompt=prompt,
                product_id=product.id,
                content_type=content_type,
                platform=AIPlatform.tiktok,
                variations=variations,
                # The worker publishes the finished result back to this chat.
                notify_chat_id=chat_id,
            )
        except generation_service.QueueUnavailableError:
            await _send(
                ctx,
                chat_id,
                "❌ Gagal memasukkan job ke antrian. Coba lagi sebentar.",
            )
            return
        except Exception:  # noqa: BLE001
            logger.exception("Telegram generation trigger failed")
            await _send(ctx, chat_id, "❌ Terjadi kesalahan saat membuat generasi.")
            return

        generation_id = str(record.id)

    await _send(
        ctx,
        chat_id,
        "🤖 *Generasi dibuat!*\n\n"
        f"Produk: {texts.escape_md(product.name)}\n"
        f"Tipe: {content_type.value}\n"
        f"ID: `{generation_id}`\n\n"
        "Status: ⏳ queued — worker sedang memproses.\n"
        "Cek status kapan saja dengan tombol di bawah.",
        _status_buttons(generation_id),
    )


def _status_buttons(generation_id: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🔄 Cek Status", "callback_data": f"ai:status:{generation_id}"}]
        ]
    }


async def show_generation_status(ctx: BotContext, chat_id: str, generation_id: str) -> None:
    async with ctx.session_factory() as db:
        record = await generation_service.load_generation_with_product(
            db, UUID(generation_id)
        )

    if record is None:
        await _send(ctx, chat_id, "❌ Generasi tidak ditemukan.")
        return

    product_id = str(record.product_id) if record.product_id else ""

    if record.status in (GenerationStatus.queued, GenerationStatus.processing):
        await _send(
            ctx,
            chat_id,
            f"⏳ Status: *{record.status.value}*\nWorker sedang memproses. "
            "Tekan Cek Status lagi sebentar.",
            _status_buttons(generation_id),
        )
        return

    if record.status == GenerationStatus.failed:
        await _send(
            ctx,
            chat_id,
            "❌ *Generation failed*\n\n"
            f"Alasan: {texts.escape_md(record.error_message or 'Tidak diketahui')}",
            texts.generation_failed_buttons(product_id, generation_id),
        )
        return

    variations = (record.result or {}).get("variations") or []
    lines = [f"✅ *Selesai — {len(variations)} variasi*", ""]
    for item in variations:
        lines.append(
            f"*Variasi {item.get('index')}*\n{texts.escape_md(item.get('text'))}\n"
        )
    await _send(
        ctx,
        chat_id,
        "\n".join(lines),
        texts.generation_result_buttons(product_id) if product_id else None,
    )


async def deliver_notification(ctx: BotContext, event: dict[str, Any]) -> None:
    """Render a cross-process event (published by the worker) into a message.

    The bot owns all Telegram-facing copy; the worker only announces that a
    generation reached a terminal state.
    """
    if event.get("kind") != notifications.GENERATION_FINISHED:
        return

    payload = event.get("payload") or {}
    chat_id = str(payload.get("chat_id") or "")
    generation_id = str(payload.get("generation_id") or "")
    if not chat_id or not generation_id:
        return

    # Defence in depth: a notification must never reach a non-admin chat.
    if not ctx.is_authorized(chat_id, chat_id):
        logger.warning("Dropping notification for unauthorized chat %s", chat_id)
        return

    await show_generation_status(ctx, chat_id, generation_id)


async def retry_generation(ctx: BotContext, chat_id: str, generation_id: str) -> None:
    async with ctx.session_factory() as db:
        record = await generation_service.load_generation_with_product(
            db, UUID(generation_id)
        )
        if record is None:
            await _send(ctx, chat_id, "❌ Generasi tidak ditemukan.")
            return
        if record.status in (GenerationStatus.queued, GenerationStatus.processing):
            await _send(ctx, chat_id, "ℹ️ Generasi masih diproses.")
            return
        try:
            await generation_service.retry_generation_record(db, record)
        except generation_service.QueueUnavailableError:
            await _send(ctx, chat_id, "❌ Gagal memasukkan ulang ke antrian.")
            return

    await _send(
        ctx,
        chat_id,
        "🔁 Generasi dimasukkan kembali ke antrian.",
        _status_buttons(generation_id),
    )


# --- dispatch --------------------------------------------------------------


def _extract_message(update: dict[str, Any]) -> dict[str, Any] | None:
    message = update.get("message")
    return message if isinstance(message, dict) else None


def _extract_callback(update: dict[str, Any]) -> dict[str, Any] | None:
    callback = update.get("callback_query")
    return callback if isinstance(callback, dict) else None


async def handle_update(ctx: BotContext, update: dict[str, Any]) -> None:
    """Entry point for a single Telegram update. Never raises."""
    try:
        await _dispatch(ctx, update)
    except Exception:  # noqa: BLE001
        logger.exception("Unhandled error while processing telegram update")


async def _dispatch(ctx: BotContext, update: dict[str, Any]) -> None:
    message = _extract_message(update)
    if message is not None:
        await _handle_message_update(ctx, message)
        return

    callback = _extract_callback(update)
    if callback is not None:
        await _handle_callback_update(ctx, callback)


def _has_media(message: dict[str, Any]) -> bool:
    """True when the message carries a media field at all (even if malformed)."""
    return (
        message.get("photo") is not None
        or message.get("video") is not None
        or message.get("document") is not None
    )


async def _handle_message_update(ctx: BotContext, message: dict[str, Any]) -> None:
    chat = message.get("chat") or {}
    sender = message.get("from") or {}
    chat_id = str(chat.get("id", ""))
    user_id = str(sender.get("id", ""))
    if not chat_id or not user_id:
        return

    if not ctx.is_authorized(user_id, chat_id):
        logger.warning("Rejected unauthorized telegram user %s", user_id)
        await _send(ctx, chat_id, texts.UNAUTHORIZED_TEXT)
        return

    text = message.get("text")

    if isinstance(text, str) and text.startswith("/"):
        command = text.split()[0].split("@")[0].lower()
        await _handle_command(ctx, chat_id, user_id, command, message)
        return

    state = await ctx.store.get(user_id)
    if state is None:
        if _has_media(message):
            await _send(ctx, chat_id, texts.NO_ACTIVE_FLOW_TEXT)
            return
        await _send(ctx, chat_id, texts.UNKNOWN_INPUT_TEXT)
        return

    if _has_media(message):
        await _handle_media_message(ctx, chat_id, user_id, state, message)
        return

    if isinstance(text, str) and text.strip():
        await _handle_conversation_text(ctx, chat_id, user_id, state, text)
        return

    await _send(ctx, chat_id, texts.UNKNOWN_INPUT_TEXT)


async def _handle_command(
    ctx: BotContext,
    chat_id: str,
    user_id: str,
    command: str,
    message: dict[str, Any],
) -> None:
    if command == "/start":
        await handle_start(ctx, chat_id, user_id)
    elif command == "/help":
        await handle_help(ctx, chat_id, user_id)
    elif command == "/add":
        await handle_add(ctx, chat_id, user_id)
    elif command == "/cancel":
        await handle_cancel(ctx, chat_id, user_id)
    elif command == "/products":
        await handle_products(ctx, chat_id, user_id)
    elif command == "/stats":
        await handle_stats(ctx, chat_id, user_id)
    elif command == "/done":
        state = await ctx.store.get(user_id)
        if state is None:
            await _send(ctx, chat_id, texts.NO_ACTIVE_FLOW_TEXT)
        else:
            await _handle_done(ctx, chat_id, user_id, state)
    elif command == texts.SKIP_COMMAND:
        state = await ctx.store.get(user_id)
        if state is None:
            await _send(ctx, chat_id, texts.NO_ACTIVE_FLOW_TEXT)
        else:
            await _handle_conversation_text(ctx, chat_id, user_id, state, texts.SKIP_COMMAND)
    else:
        await _send(ctx, chat_id, texts.UNKNOWN_INPUT_TEXT)


async def _handle_callback_update(ctx: BotContext, callback: dict[str, Any]) -> None:
    sender = callback.get("from") or {}
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    user_id = str(sender.get("id", ""))
    chat_id = str(chat.get("id", "")) or user_id
    data = callback.get("data") or ""
    callback_id = str(callback.get("id", ""))

    if not ctx.is_authorized(user_id, chat_id):
        logger.warning("Rejected unauthorized telegram callback from %s", user_id)
        if callback_id:
            with contextlib.suppress(TelegramError):
                await ctx.client.answer_callback_query(callback_id, "Tidak diizinkan.")
        await _send(ctx, chat_id, texts.UNAUTHORIZED_TEXT)
        return

    if callback_id:
        # Acknowledge best-effort: an expired query must not abort the action.
        with contextlib.suppress(TelegramError):
            await ctx.client.answer_callback_query(callback_id)

    await _handle_callback_data(ctx, chat_id, user_id, data)


async def _handle_callback_data(
    ctx: BotContext, chat_id: str, user_id: str, data: str
) -> None:
    parts = data.split(":")
    namespace = parts[0] if parts else ""

    if namespace == "add":
        action = parts[1] if len(parts) > 1 else ""
        if action == "cancel":
            await handle_cancel(ctx, chat_id, user_id)
            return
        # Media retry works after the conversation state has been cleared.
        if action == "retry_media" and len(parts) > 2:
            await retry_pending_media(ctx, chat_id, parts[2])
            return
        state = await ctx.store.get(user_id)
        if state is None:
            await _send(ctx, chat_id, texts.NO_ACTIVE_FLOW_TEXT)
            return
        if action == "skip":
            if state.step not in OPTIONAL_STEPS:
                await _send(ctx, chat_id, "⚠️ Kolom ini wajib diisi.")
                return
            await _advance(ctx, chat_id, user_id, state)
            return
        if action == "done":
            await _handle_done(ctx, chat_id, user_id, state)
            return
        await _send(ctx, chat_id, texts.UNKNOWN_INPUT_TEXT)
        return

    if namespace == "ai":
        action = parts[1] if len(parts) > 1 else ""
        if action == "cancel":
            await _send(ctx, chat_id, "Dibatalkan.")
            return
        if action == "analyze" and len(parts) > 2:
            await _trigger_generation(
                ctx, chat_id, parts[2], AIContentType.product_description, variations=1
            )
            return
        if action == "generate" and len(parts) > 2:
            await _send(
                ctx,
                chat_id,
                "✍️ *Pilih jenis konten* yang ingin dibuat:",
                texts.analyze_type_buttons(parts[2]),
            )
            return
        if action == "run" and len(parts) > 3:
            try:
                content_type = AIContentType(parts[3])
            except ValueError:
                await _send(ctx, chat_id, "❌ Jenis konten tidak dikenal.")
                return
            await _trigger_generation(ctx, chat_id, parts[2], content_type)
            return
        if action == "status" and len(parts) > 2:
            await show_generation_status(ctx, chat_id, parts[2])
            return
        if action == "retry" and len(parts) > 2:
            await retry_generation(ctx, chat_id, parts[2])
            return

    await _send(ctx, chat_id, texts.UNKNOWN_INPUT_TEXT)
