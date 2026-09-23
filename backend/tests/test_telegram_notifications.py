"""Tests for the cross-process generation notifications.

Covers the contract the worker and the Telegram bot share:
worker finishes -> Redis event -> bot pushes the rendered result into the chat.
"""

import asyncio
import contextlib
import json

from sqlalchemy import select

from app.core.config import settings
from app.models import AIContentType, AIGeneration, AIPlatform, GenerationStatus, Product
from app.providers.ai.base import AIProviderConfigError
from app.services import generation as generation_service
from app.services import notifications
from app.services.telegram.handlers import (
    BotContext,
    build_default_context,
    deliver_notification,
    handle_update,
)
from app.workers import handlers as worker_handlers
from tests.conftest import StubProvider
from tests.telegram_helpers import ADMIN_CHAT_ID, callback_update

VALID_URL = "https://example.com/aff"
STUB_OUTPUT = json.dumps({"variations": ["[MOCK variasi 1] hasil", "[MOCK variasi 2] hasil"]})


async def _product(session_factory, name: str = "Produk Notifikasi") -> Product:
    async with session_factory() as db:
        product = Product(name=name, affiliate_url=VALID_URL, description="Deskripsi.")
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product


async def _queued_generation(
    session_factory, *, notify_chat_id: str | None, name: str = "Produk Notifikasi"
) -> str:
    """Create a generation through the shared service (as the bot does)."""
    product = await _product(session_factory, name)
    async with session_factory() as db:
        record = await generation_service.create_generation_record(
            db,
            prompt="Brief",
            product_id=product.id,
            content_type=AIContentType.caption,
            platform=AIPlatform.tiktok,
            variations=2,
            notify_chat_id=notify_chat_id,
        )
        return str(record.id)


async def _drain() -> None:
    """Empty the queue left behind by the generation enqueue itself."""
    while await notifications.pending_count() > 0:
        await notifications.dequeue(timeout=1)


# --- the queue itself ------------------------------------------------------


async def test_empty_notification_queue_yields_nothing(fake_redis):
    assert await notifications.pending_count() == 0
    assert await notifications.dequeue(timeout=1) is None


async def test_enqueue_dequeue_roundtrip(fake_redis):
    await notifications.notify_generation_finished(
        chat_id="42", generation_id="abc", status="completed"
    )

    assert await notifications.pending_count() == 1
    event = await notifications.dequeue(timeout=1)

    assert event["kind"] == notifications.GENERATION_FINISHED
    assert event["payload"]["chat_id"] == "42"
    assert event["payload"]["generation_id"] == "abc"
    assert await notifications.pending_count() == 0


async def test_notifications_are_delivered_in_order(fake_redis):
    await notifications.notify_generation_finished(
        chat_id="1", generation_id="first", status="completed"
    )
    await notifications.notify_generation_finished(
        chat_id="1", generation_id="second", status="failed"
    )

    first = await notifications.dequeue(timeout=1)
    second = await notifications.dequeue(timeout=1)

    assert first["payload"]["generation_id"] == "first"
    assert second["payload"]["generation_id"] == "second"


# --- worker publishes ------------------------------------------------------


async def test_generation_publishes_event_on_success(session_factory, fake_redis):
    """The worker announces a completed generation to its originating chat."""
    generation_id = await _queued_generation(
        session_factory, notify_chat_id=ADMIN_CHAT_ID
    )
    await _drain()

    outcome = await worker_handlers.handle_generation_job(
        {"payload": {"generation_id": generation_id}},
        session_factory=session_factory,
        provider=StubProvider(output=STUB_OUTPUT),
    )

    assert outcome == worker_handlers.COMPLETED
    event = await notifications.dequeue(timeout=1)
    assert event is not None
    assert event["kind"] == notifications.GENERATION_FINISHED
    assert event["payload"] == {
        "chat_id": ADMIN_CHAT_ID,
        "generation_id": generation_id,
        "status": "completed",
    }


async def test_generation_without_chat_id_publishes_nothing(session_factory, fake_redis):
    """HTTP/dashboard generations have no chat to notify."""
    generation_id = await _queued_generation(session_factory, notify_chat_id=None)
    await _drain()

    outcome = await worker_handlers.handle_generation_job(
        {"payload": {"generation_id": generation_id}},
        session_factory=session_factory,
        provider=StubProvider(output=STUB_OUTPUT),
    )

    assert outcome == worker_handlers.COMPLETED
    assert await notifications.pending_count() == 0


async def test_generation_failure_notifies_chat(session_factory, fake_redis):
    generation_id = await _queued_generation(
        session_factory, notify_chat_id=ADMIN_CHAT_ID, name="Produk Gagal"
    )
    await _drain()

    outcome = await worker_handlers.handle_generation_job(
        {"payload": {"generation_id": generation_id}},
        session_factory=session_factory,
        provider=StubProvider(error=AIProviderConfigError("missing key")),
        max_retries=1,
        retry_delay_seconds=0,
    )

    assert outcome == worker_handlers.FAILED
    event = await notifications.dequeue(timeout=1)
    assert event["payload"]["status"] == "failed"
    assert event["payload"]["chat_id"] == ADMIN_CHAT_ID


async def test_retry_does_not_notify_until_terminal(session_factory, fake_redis):
    """A retryable failure re-queues silently; only the terminal state notifies."""
    generation_id = await _queued_generation(
        session_factory, notify_chat_id=ADMIN_CHAT_ID, name="Produk Retry"
    )
    await _drain()

    outcome = await worker_handlers.handle_generation_job(
        {"payload": {"generation_id": generation_id}},
        session_factory=session_factory,
        provider=StubProvider(error=AIProviderConfigError("missing key")),
        max_retries=3,
        retry_delay_seconds=0,
    )

    # Config errors never retry, so this is already terminal.
    assert outcome == worker_handlers.FAILED
    assert await notifications.pending_count() == 1


# --- bot delivers ----------------------------------------------------------


async def test_deliver_notification_sends_result_to_chat(
    bot_ctx, session_factory, fake_redis
):
    """A finished generation is rendered back into the originating chat."""
    generation_id = await _queued_generation(
        session_factory, notify_chat_id=ADMIN_CHAT_ID, name="Produk Terkirim"
    )
    await _drain()

    await worker_handlers.handle_generation_job(
        {"payload": {"generation_id": generation_id}},
        session_factory=session_factory,
        provider=StubProvider(output=STUB_OUTPUT),
    )

    event = await notifications.dequeue(timeout=1)
    assert event is not None

    bot_ctx.client.clear()
    await deliver_notification(bot_ctx, event)

    text = bot_ctx.client.last_text()
    assert "Selesai" in text
    # The generated content itself is sent, not just a status line.
    assert "MOCK variasi 1" in text
    assert bot_ctx.client.messages[0]["chat_id"] == ADMIN_CHAT_ID


async def test_deliver_failure_notification_includes_reason(
    bot_ctx, session_factory, fake_redis
):
    generation_id = await _queued_generation(
        session_factory, notify_chat_id=ADMIN_CHAT_ID, name="Produk Gagal Kirim"
    )
    await _drain()

    await worker_handlers.handle_generation_job(
        {"payload": {"generation_id": generation_id}},
        session_factory=session_factory,
        provider=StubProvider(error=AIProviderConfigError("missing key")),
        max_retries=1,
        retry_delay_seconds=0,
    )

    event = await notifications.dequeue(timeout=1)
    bot_ctx.client.clear()
    await deliver_notification(bot_ctx, event)

    assert "Generation failed" in bot_ctx.client.last_text()


async def test_deliver_notification_ignores_unauthorized_chat(bot_ctx, fake_redis):
    bot_ctx.client.clear()

    await deliver_notification(
        bot_ctx,
        {
            "kind": notifications.GENERATION_FINISHED,
            "payload": {
                "chat_id": "999999",
                "generation_id": "00000000-0000-0000-0000-000000000000",
                "status": "completed",
            },
        },
    )

    assert bot_ctx.client.messages == []


async def test_deliver_notification_ignores_unknown_kind(bot_ctx, fake_redis):
    bot_ctx.client.clear()

    await deliver_notification(bot_ctx, {"kind": "something_else", "payload": {}})

    assert bot_ctx.client.messages == []


async def test_deliver_notification_ignores_malformed_payload(bot_ctx, fake_redis):
    bot_ctx.client.clear()

    await deliver_notification(
        bot_ctx, {"kind": notifications.GENERATION_FINISHED, "payload": {"chat_id": ""}}
    )

    assert bot_ctx.client.messages == []


# --- wiring ----------------------------------------------------------------


async def test_trigger_from_telegram_sets_notify_chat(
    bot_ctx, session_factory, fake_redis
):
    """The chat id is persisted so the worker knows where to report back."""
    product = await _product(session_factory, "Produk Trigger")

    await handle_update(bot_ctx, callback_update(f"ai:run:{product.id}:caption"))

    async with session_factory() as db:
        record = (await db.execute(select(AIGeneration))).scalars().one()

    assert record.notify_chat_id == ADMIN_CHAT_ID
    assert record.status == GenerationStatus.queued


async def test_notification_survives_bot_restart(
    bot_ctx, session_factory, fake_redis, tmp_path, monkeypatch
):
    """Events are queued in Redis, so a fresh bot process still delivers them."""
    generation_id = await _queued_generation(
        session_factory, notify_chat_id=ADMIN_CHAT_ID, name="Produk Restart"
    )
    await _drain()

    # The worker completes the job while the bot process is down.
    await worker_handlers.handle_generation_job(
        {"payload": {"generation_id": generation_id}},
        session_factory=session_factory,
        provider=StubProvider(output=STUB_OUTPUT),
    )

    fresh_ctx = BotContext(
        client=bot_ctx.client,
        session_factory=bot_ctx.session_factory,
        store=build_default_context().store,
        settings=settings,
    )
    bot_ctx.client.clear()

    # A restarted bot still finds the event waiting in Redis.
    event = await notifications.dequeue(timeout=1)
    assert event is not None
    await deliver_notification(fresh_ctx, event)

    assert "MOCK variasi 1" in bot_ctx.client.last_text()


async def test_notification_loop_delivers_pending_event(
    bot_ctx, session_factory, fake_redis
):
    """The polling runtime drains the notification queue and pushes results."""
    generation_id = await _queued_generation(
        session_factory, notify_chat_id=ADMIN_CHAT_ID, name="Produk Loop"
    )
    await _drain()
    await worker_handlers.handle_generation_job(
        {"payload": {"generation_id": generation_id}},
        session_factory=session_factory,
        provider=StubProvider(output=STUB_OUTPUT),
    )

    from app.services.telegram.runtime import _notification_loop

    stop = asyncio.Event()
    task = asyncio.create_task(_notification_loop(bot_ctx, stop))
    try:
        for _ in range(100):
            if bot_ctx.client.messages:
                break
            await asyncio.sleep(0.05)
    finally:
        stop.set()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert "MOCK variasi 1" in bot_ctx.client.last_text()
