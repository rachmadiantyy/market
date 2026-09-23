"""Telegram bot runtime: long-polling loop with a liveness heartbeat.

The bot starts automatically with `docker compose up -d`. It fails fast with a
clear message when the token is missing, and never crashes the container on a
transient Telegram or database error.
"""

import asyncio
import contextlib
import time
from pathlib import Path

from app.core.config import settings
from app.core.database import engine
from app.core.logging import get_logger
from app.core.redis import close_redis, get_redis
from app.services import notifications
from app.services.telegram.client import TelegramAuthError, TelegramClient, TelegramError
from app.services.telegram.handlers import (
    BotContext,
    build_default_context,
    deliver_notification,
    handle_update,
)

logger = get_logger(__name__)

BACKOFF_INITIAL = 1.0
BACKOFF_MAX = 30.0
HEARTBEAT_INTERVAL = 5.0
NOTIFICATION_POLL_TIMEOUT = 5


def touch_heartbeat(path: str | None = None) -> None:
    """Write a heartbeat file used by the Docker healthcheck. Never raises."""
    target = Path(path or settings.telegram_heartbeat_file)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(int(time.time())))
    except OSError:
        logger.debug("Could not write heartbeat file %s", target)


async def _heartbeat_loop(stop: asyncio.Event) -> None:
    while not stop.is_set():
        touch_heartbeat()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_INTERVAL)


async def _notification_loop(ctx: BotContext, stop: asyncio.Event) -> None:
    """Deliver events published by the worker (e.g. finished generations).

    Runs alongside polling so the bot can push results without the admin
    having to ask for them.
    """
    while not stop.is_set():
        try:
            event = await notifications.dequeue(timeout=NOTIFICATION_POLL_TIMEOUT)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Notification dequeue failed; retrying")
            await asyncio.sleep(1)
            continue

        if event is None:
            continue

        try:
            await deliver_notification(ctx, event)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to deliver notification")


async def run_polling(ctx: BotContext, *, max_iterations: int | None = None) -> None:
    """Long-poll Telegram and dispatch updates."""
    offset: int | None = None
    backoff = BACKOFF_INITIAL
    iterations = 0

    stop = asyncio.Event()
    heartbeat = asyncio.create_task(_heartbeat_loop(stop))
    notifier = asyncio.create_task(_notification_loop(ctx, stop))

    logger.info("Telegram bot polling started")
    try:
        while True:
            if max_iterations is not None and iterations >= max_iterations:
                break
            iterations += 1

            try:
                updates = await ctx.client.get_updates(offset=offset)
                backoff = BACKOFF_INITIAL
            except TelegramAuthError as exc:
                logger.error("Telegram rejected the bot token: %s", exc)
                await asyncio.sleep(BACKOFF_MAX)
                continue
            except TelegramError as exc:
                logger.warning("getUpdates failed (%s); retrying in %.0fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)
                continue

            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                await handle_update(ctx, update)
    finally:
        stop.set()
        for task in (heartbeat, notifier):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


async def _verify_connection(ctx: BotContext) -> bool:
    try:
        me = await ctx.client.get_me()
    except TelegramAuthError as exc:
        logger.error("Cannot start bot: %s", exc)
        return False
    except TelegramError as exc:
        logger.warning("Could not verify bot identity: %s", exc)
        return True  # network hiccup; let the polling loop retry
    logger.info("Bot connected as @%s", me.get("username") or me.get("id"))
    return True


async def main() -> None:
    if not settings.telegram_bot_token:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. The telegram-bot service will idle "
            "without processing updates."
        )
        # Keep the container alive and healthy so `docker compose up -d` does not
        # spin; the operator can set the token and restart.
        while True:
            touch_heartbeat()
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    if not settings.telegram_admin_user_ids and not settings.telegram_admin_chat_ids:
        logger.warning(
            "No TELEGRAM_ADMIN_USER_ID / TELEGRAM_ADMIN_CHAT_ID configured. "
            "All users will be rejected (secure by default)."
        )

    get_redis()
    ctx = build_default_context()

    if not await _verify_connection(ctx):
        while True:
            touch_heartbeat()
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    try:
        await run_polling(ctx)
    finally:
        await close_redis()
        await engine.dispose()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
