"""Tests for /start, /help, authorization, and invalid input."""

from sqlalchemy import func, select

from app.models import Product
from app.services.telegram import texts
from app.services.telegram.handlers import handle_update
from tests.telegram_helpers import (
    ADMIN_CHAT_ID,
    ADMIN_USER_ID,
    OTHER_CHAT_ID,
    OTHER_USER_ID,
    callback_update,
    message_update,
)


async def test_start_sends_welcome(bot_ctx):
    await handle_update(bot_ctx, message_update("/start"))

    assert len(bot_ctx.client.messages) == 1
    text = bot_ctx.client.last_text()
    assert "Selamat datang" in text
    assert "/add" in text
    assert bot_ctx.client.messages[0]["chat_id"] == ADMIN_CHAT_ID


async def test_help_lists_commands(bot_ctx):
    await handle_update(bot_ctx, message_update("/help"))

    text = bot_ctx.client.last_text()
    assert "Bantuan" in text
    assert "/add" in text
    assert "/products" in text
    assert "/stats" in text
    assert "/cancel" in text


async def test_start_via_botname_suffix(bot_ctx):
    """Commands addressed as /start@mybot must still work."""
    await handle_update(bot_ctx, message_update("/start@my_affiliate_bot"))

    assert "Selamat datang" in bot_ctx.client.last_text()


async def test_authorized_user_allowed(bot_ctx):
    await handle_update(bot_ctx, message_update("/start"))

    assert texts.UNAUTHORIZED_TEXT not in bot_ctx.client.last_text()


async def test_unauthorized_user_rejected_on_command(bot_ctx):
    await handle_update(
        bot_ctx, message_update("/add", user_id=OTHER_USER_ID, chat_id=OTHER_CHAT_ID)
    )

    assert bot_ctx.client.last_text() == texts.UNAUTHORIZED_TEXT


async def test_unauthorized_user_cannot_start_conversation(bot_ctx, session_factory):
    for command in ("/start", "/add", "/products", "/stats", "/help"):
        bot_ctx.client.clear()
        await handle_update(
            bot_ctx,
            message_update(command, user_id=OTHER_USER_ID, chat_id=OTHER_CHAT_ID),
        )
        assert bot_ctx.client.last_text() == texts.UNAUTHORIZED_TEXT

    # No state should have been created for the intruder.
    assert await bot_ctx.store.get(OTHER_USER_ID) is None


async def test_unauthorized_user_cannot_trigger_ai(bot_ctx, session_factory):
    bot_ctx.client.clear()
    await handle_update(
        bot_ctx,
        callback_update(
            "ai:generate:00000000-0000-0000-0000-000000000000",
            user_id=OTHER_USER_ID,
            chat_id=OTHER_CHAT_ID,
        ),
    )

    assert texts.UNAUTHORIZED_TEXT in bot_ctx.client.texts()


async def test_no_allowlist_configured_rejects_everyone(
    bot_ctx, monkeypatch
):
    """Secure by default: an empty allow-list means nobody is authorized."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "telegram_admin_user_id", "")
    monkeypatch.setattr(settings, "telegram_admin_chat_id", "")

    await handle_update(bot_ctx, message_update("/start"))

    assert bot_ctx.client.last_text() == texts.UNAUTHORIZED_TEXT


async def test_chat_id_allowlist_grants_access(bot_ctx, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "telegram_admin_user_id", "")
    monkeypatch.setattr(settings, "telegram_admin_chat_id", ADMIN_CHAT_ID)

    await handle_update(bot_ctx, message_update("/start"))

    assert "Selamat datang" in bot_ctx.client.last_text()


async def test_unknown_command_returns_hint(bot_ctx):
    await handle_update(bot_ctx, message_update("/nonsense"))

    assert bot_ctx.client.last_text() == texts.UNKNOWN_INPUT_TEXT


async def test_plain_text_without_flow(bot_ctx):
    await handle_update(bot_ctx, message_update("halo bot"))

    assert bot_ctx.client.last_text() == texts.UNKNOWN_INPUT_TEXT


async def test_photo_without_flow_hints_to_add(bot_ctx, session_factory):
    await handle_update(bot_ctx, message_update(photo=True, file_id="p1"))

    assert bot_ctx.client.last_text() == texts.NO_ACTIVE_FLOW_TEXT

    async with session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(Product))
    assert count == 0


async def test_unknown_callback_data(bot_ctx):
    await handle_update(bot_ctx, callback_update("bogus:data"))

    assert bot_ctx.client.last_text() == texts.UNKNOWN_INPUT_TEXT


async def test_callback_is_acknowledged(bot_ctx):
    await handle_update(bot_ctx, callback_update("bogus:data"))

    assert bot_ctx.client.callback_answers[-1]["callback_query_id"] == "cb-1"


async def test_stats_reports_zero_on_empty_database(bot_ctx):
    await handle_update(bot_ctx, message_update("/stats"))

    text = bot_ctx.client.last_text()
    assert "Statistik" in text
    assert "Produk: *0*" in text


async def test_products_empty_state(bot_ctx):
    await handle_update(bot_ctx, message_update("/products"))

    assert "Belum ada produk" in bot_ctx.client.last_text()


async def test_products_shows_name_price_and_status(bot_ctx, session_factory):
    """The compact list must carry name, price and status (no hidden fields)."""
    from app.models import Product, ProductStatus

    async with session_factory() as db:
        db.add(
            Product(
                name="Produk Daftar",
                price=250000,
                status=ProductStatus.active,
            )
        )
        await db.commit()

    await handle_update(bot_ctx, message_update("/products"))

    text = bot_ctx.client.last_text()
    assert "Produk Daftar" in text
    assert "Rp250,000" in text
    assert "active" in text


async def test_stats_states_analytics_not_available(bot_ctx):
    """Analytics ingestion does not exist yet; say so instead of inventing data."""
    await handle_update(bot_ctx, message_update("/stats"))

    assert "Analytics not available yet." in bot_ctx.client.last_text()


async def test_cancel_without_flow(bot_ctx):
    await handle_update(bot_ctx, message_update("/cancel"))

    assert bot_ctx.client.last_text() == texts.NO_ACTIVE_FLOW_TEXT
