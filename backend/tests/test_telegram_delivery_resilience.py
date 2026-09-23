"""Delivery resilience tests.

Telegram rejects an entire `sendMessage` call when an inline-keyboard URL is not
publicly reachable (a `localhost` FRONTEND_BASE_URL, for example), and
`answerCallbackQuery` fails for expired queries. Neither may cost the admin the
message or the action itself.
"""

from app.services.telegram.client import TelegramError
from app.services.telegram.handlers import handle_update
from app.services.telegram import texts
from tests.telegram_helpers import callback_update, message_update


class KeyboardRejectingClient:
    """Raises whenever a reply_markup is attached, like Telegram does."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def send_message(self, chat_id, text, *, reply_markup=None, parse_mode=None):
        if reply_markup is not None:
            raise TelegramError(
                "Telegram error (400): Bad Request: inline keyboard button URL "
                "'http://localhost:3000/products' is invalid: Wrong HTTP URL"
            )
        return await self._inner.send_message(
            chat_id, text, reply_markup=None, parse_mode=parse_mode
        )


class ExpiredCallbackClient:
    """answerCallbackQuery fails, e.g. the query id expired after a restart."""

    def __init__(self, inner):
        self._inner = inner

    def __getattr__(self, name):
        return getattr(self._inner, name)

    async def answer_callback_query(self, callback_query_id, text=None):
        raise TelegramError(
            "Telegram error (400): Bad Request: query is too old and response "
            "timeout expired or query ID is invalid"
        )


async def test_rejected_keyboard_still_delivers_the_text(bot_ctx):
    bot_ctx.client = KeyboardRejectingClient(bot_ctx.client)

    await handle_update(bot_ctx, message_update("/start"))

    assert "Selamat datang" in bot_ctx.client.last_text()


async def test_rejected_keyboard_keeps_product_confirmation(bot_ctx, session_factory):
    """The '✅ Product added' message is the critical one: it must always land."""
    bot_ctx.client = KeyboardRejectingClient(bot_ctx.client)

    await handle_update(bot_ctx, message_update("/add"))
    for value in (
        "Produk Tombol Gagal",
        "https://example.com/aff",
        "150000",
        "15000",
        "Fashion",
        "Umum",
        "Deskripsi",
    ):
        await handle_update(bot_ctx, message_update(value))
    await handle_update(bot_ctx, message_update(photo=True))
    await handle_update(bot_ctx, message_update("/done"))

    assert "Product added" in bot_ctx.client.last_text()
    assert "Produk Tombol Gagal" in bot_ctx.client.last_text()


async def test_expired_callback_ack_does_not_cancel_the_action(bot_ctx):
    bot_ctx.client = ExpiredCallbackClient(bot_ctx.client)

    await handle_update(bot_ctx, callback_update("bogus:data"))

    # The action still ran: unknown callback data produced its normal reply.
    assert bot_ctx.client.last_text() == texts.UNKNOWN_INPUT_TEXT


async def test_expired_callback_ack_still_rejects_unauthorized_user(bot_ctx):
    bot_ctx.client = ExpiredCallbackClient(bot_ctx.client)

    await handle_update(
        bot_ctx,
        callback_update(
            "ai:generate:00000000-0000-0000-0000-000000000000",
            user_id="999999",
            chat_id="999999",
        ),
    )

    assert texts.UNAUTHORIZED_TEXT in bot_ctx.client.texts()
