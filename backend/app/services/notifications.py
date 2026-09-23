"""Cross-process notification queue backed by Redis.

The worker runs in its own container and cannot call Telegram directly without
duplicating delivery logic. Instead it publishes a small, channel-agnostic
event onto a Redis list; the Telegram bot drains that list and renders the
message. Because the queue lives in Redis, notifications survive a bot restart
and are never lost while the bot is down.

This module deliberately knows nothing about Telegram, and the Telegram bot
knows nothing about the AI pipeline — each side only shares the event shape.
"""

import json
from typing import Any

from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger(__name__)

NOTIFICATION_KEY = "affiliate:notifications"

GENERATION_FINISHED = "generation_finished"


async def enqueue(kind: str, payload: dict[str, Any] | None = None) -> None:
    """Publish an event. Never raises: a lost notification must not fail a job."""
    message = json.dumps({"kind": kind, "payload": payload or {}})
    try:
        await get_redis().lpush(NOTIFICATION_KEY, message)
    except Exception:  # noqa: BLE001
        logger.warning("Could not publish notification '%s'", kind, exc_info=True)


async def dequeue(timeout: int = 5) -> dict[str, Any] | None:
    """Block until an event is available (or the timeout elapses).

    Events are pushed with LPUSH and popped with BRPOP so they are delivered in
    publish order (FIFO).
    """
    result = await get_redis().brpop(NOTIFICATION_KEY, timeout=timeout)
    if result is None:
        return None
    _, raw = result
    try:
        data = json.loads(raw)
    except ValueError:
        logger.warning("Discarding corrupt notification payload")
        return None
    return data if isinstance(data, dict) else None


async def pending_count() -> int:
    """Number of undelivered events (used by tests and diagnostics)."""
    return int(await get_redis().llen(NOTIFICATION_KEY))


async def notify_generation_finished(
    *, chat_id: str, generation_id: str, status: str
) -> None:
    """Tell the chat that owns a generation that it reached a terminal state."""
    await enqueue(
        GENERATION_FINISHED,
        {"chat_id": chat_id, "generation_id": generation_id, "status": status},
    )
