"""Tests for the /add conversation flow, validation, and media handling."""

from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models import MediaType, Product, ProductMedia, ProductStatus
from app.services.telegram import texts
from app.services.telegram.handlers import handle_update
from app.services.telegram.state import ConversationStore
from tests.telegram_helpers import callback_update, message_update

VALID_URL = "https://example.com/aff/product"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64


async def _start_add(ctx) -> None:
    await handle_update(ctx, message_update("/add"))


async def _send_text(ctx, text: str) -> None:
    await handle_update(ctx, message_update(text))


async def _fill_required(ctx, *, name: str = "Kopi Gayo") -> None:
    await _start_add(ctx)
    await _send_text(ctx, name)
    await _send_text(ctx, VALID_URL)


async def test_add_starts_conversation(bot_ctx):
    await _start_add(bot_ctx)

    texts_sent = bot_ctx.client.texts()
    assert any("Tambah produk baru" in t for t in texts_sent)
    assert any("Nama produk" in t for t in texts_sent)

    state = await bot_ctx.store.get("111111")
    assert state is not None
    assert state.step.value == "name"


async def test_state_survives_store_restart(bot_ctx):
    """State lives in Redis, so a fresh store instance still sees it."""
    await _start_add(bot_ctx)
    await _send_text(bot_ctx, "Produk Persisten")

    fresh_store = ConversationStore()
    state = await fresh_store.get("111111")

    assert state is not None
    assert state.data["name"] == "Produk Persisten"
    assert state.step.value == "affiliate_url"


async def test_full_add_flow_creates_product_with_media(bot_ctx, session_factory):
    bot_ctx.client.files = {
        "files/photo-1": PNG_BYTES,
        "files/video-1": MP4_BYTES,
    }

    await _start_add(bot_ctx)
    await _send_text(bot_ctx, "Kopi Gayo Premium")
    await _send_text(bot_ctx, VALID_URL)
    await _send_text(bot_ctx, "150000")
    await _send_text(bot_ctx, "15000")
    await _send_text(bot_ctx, "Minuman")
    await _send_text(bot_ctx, "Pekerja kantoran")
    await _send_text(bot_ctx, "Kopi arabika single origin dari Aceh.")
    await handle_update(bot_ctx, message_update(photo=True, file_id="photo-1"))
    await handle_update(
        bot_ctx, message_update(video=True, file_id="video-1", file_name="promo.mp4")
    )
    await _send_text(bot_ctx, "/done")

    async with session_factory() as db:
        products = list((await db.execute(select(Product))).scalars().all())
        assert len(products) == 1
        product = products[0]
        assert product.name == "Kopi Gayo Premium"
        assert product.affiliate_url == VALID_URL
        assert float(product.price) == 150000.0
        assert float(product.commission) == 15000.0
        assert product.category == "Minuman"
        assert product.target_audience == "Pekerja kantoran"
        assert product.description == "Kopi arabika single origin dari Aceh."
        assert product.status == ProductStatus.active

        media = list(
            (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id)))
            .scalars()
            .all()
        )
        assert len(media) == 2
        kinds = {m.media_type for m in media}
        assert kinds == {MediaType.image, MediaType.video}
        assert all(m.source == "telegram" for m in media)
        assert all(m.file_size > 0 for m in media)

        # Files really exist on disk.
        for item in media:
            assert (Path(settings.uploads_dir) / item.file_path).exists()
            assert item.file_path.startswith(f"products/{product.id}/")


async def test_confirmation_message_and_buttons(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/photo-1": PNG_BYTES}

    await _fill_required(bot_ctx, name="Sepatu Lari")
    await _send_text(bot_ctx, "/skip")  # price
    await _send_text(bot_ctx, "/skip")  # commission
    await _send_text(bot_ctx, "/skip")  # category
    await _send_text(bot_ctx, "/skip")  # target audience
    await _send_text(bot_ctx, "/skip")  # description
    await handle_update(bot_ctx, message_update(photo=True, file_id="photo-1"))
    await _send_text(bot_ctx, "/done")

    final = bot_ctx.client.last_text()
    assert "✅" in final and "Product added" in final
    assert "Sepatu Lari" in final
    assert VALID_URL in final

    keyboard = bot_ctx.client.messages[-1]["reply_markup"]["inline_keyboard"]
    labels = [button["text"] for row in keyboard for button in row]
    assert any("Analyze with AI" in label for label in labels)
    assert any("Generate Content" in label for label in labels)
    assert any("Open Dashboard" in label for label in labels)


async def test_skip_all_optional_fields(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/photo-1": PNG_BYTES}

    await _fill_required(bot_ctx, name="Produk Minimal")
    for _ in range(5):
        await _send_text(bot_ctx, "/skip")
    await handle_update(bot_ctx, message_update(photo=True, file_id="photo-1"))
    await _send_text(bot_ctx, "/done")

    async with session_factory() as db:
        product = (await db.execute(select(Product))).scalars().one()
    assert product.name == "Produk Minimal"
    assert product.price is None
    assert product.commission is None
    assert product.category is None
    assert product.target_audience is None
    assert product.description is None


async def test_skip_via_inline_button(bot_ctx):
    await _fill_required(bot_ctx, name="Produk Tombol")

    await handle_update(bot_ctx, callback_update("add:skip"))  # skip price

    state = await bot_ctx.store.get("111111")
    assert state is not None
    assert state.step.value == "commission"


async def test_cannot_skip_required_name_field(bot_ctx):
    await _start_add(bot_ctx)
    bot_ctx.client.clear()

    await _send_text(bot_ctx, "/skip")

    assert "wajib" in bot_ctx.client.last_text().lower()
    state = await bot_ctx.store.get("111111")
    assert state.step.value == "name"


@pytest.mark.parametrize(
    "bad_input,expected_step",
    [
        ("a", "name"),
        ("x" * 300, "name"),
    ],
)
async def test_invalid_name_keeps_user_on_step(bot_ctx, bad_input, expected_step):
    await _start_add(bot_ctx)
    bot_ctx.client.clear()

    await _send_text(bot_ctx, bad_input)

    assert "⚠️" in bot_ctx.client.last_text()
    state = await bot_ctx.store.get("111111")
    assert state.step.value == expected_step


@pytest.mark.parametrize("bad_url", ["example.com", "ftp://x", "not a url"])
async def test_invalid_url_rejected(bot_ctx, bad_url):
    await _start_add(bot_ctx)
    await _send_text(bot_ctx, "Produk URL")
    bot_ctx.client.clear()

    await _send_text(bot_ctx, bad_url)

    assert "URL" in bot_ctx.client.last_text()
    state = await bot_ctx.store.get("111111")
    assert state.step.value == "affiliate_url"


@pytest.mark.parametrize("bad_price", ["seribu", "12abc", "-5"])
async def test_invalid_price_rejected(bot_ctx, bad_price):
    await _fill_required(bot_ctx, name="Produk Harga")
    bot_ctx.client.clear()

    await _send_text(bot_ctx, bad_price)

    assert "Angka tidak valid" in bot_ctx.client.last_text()
    state = await bot_ctx.store.get("111111")
    assert state.step.value == "price"


async def test_price_accepts_formatted_input(bot_ctx):
    await _fill_required(bot_ctx, name="Produk Format")

    await _send_text(bot_ctx, "Rp 150.000")

    state = await bot_ctx.store.get("111111")
    assert state.data["price"] == 150000.0
    assert state.step.value == "commission"


async def test_cancel_clears_state_and_saves_nothing(bot_ctx, session_factory):
    await _fill_required(bot_ctx, name="Produk Batal")

    await _send_text(bot_ctx, "/cancel")

    assert "dibatalkan" in bot_ctx.client.last_text().lower()
    assert await bot_ctx.store.get("111111") is None

    async with session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(Product))
    assert count == 0


async def test_cancel_via_button(bot_ctx):
    await _fill_required(bot_ctx, name="Produk Batal 2")

    await handle_update(bot_ctx, callback_update("add:cancel"))

    assert await bot_ctx.store.get("111111") is None


async def test_done_without_media_is_rejected(bot_ctx, session_factory):
    await _fill_required(bot_ctx, name="Produk Tanpa Media")
    for _ in range(5):
        await _send_text(bot_ctx, "/skip")
    bot_ctx.client.clear()

    await _send_text(bot_ctx, "/done")

    assert "Minimal 1 media" in bot_ctx.client.last_text()

    async with session_factory() as db:
        count = await db.scalar(select(func.count()).select_from(Product))
    assert count == 0


async def test_media_only_accepted_in_media_step(bot_ctx):
    await _start_add(bot_ctx)
    bot_ctx.client.clear()

    await handle_update(bot_ctx, message_update(photo=True, file_id="p1"))

    assert "langkah terakhir" in bot_ctx.client.last_text()


async def test_media_step_hint_on_text(bot_ctx):
    await _fill_required(bot_ctx, name="Produk Media")
    for _ in range(5):
        await _send_text(bot_ctx, "/skip")
    bot_ctx.client.clear()

    await _send_text(bot_ctx, "ini bukan media")

    assert "Kirim foto atau video" in bot_ctx.client.last_text()


async def test_empty_photo_is_rejected(bot_ctx):
    await _fill_required(bot_ctx, name="Produk Foto Kosong")
    for _ in range(5):
        await _send_text(bot_ctx, "/skip")
    bot_ctx.client.clear()

    update = message_update(photo=True, file_id="p1")
    update["message"]["photo"] = []
    await handle_update(bot_ctx, update)

    assert "⚠️" in bot_ctx.client.last_text()


async def test_products_command_lists_saved_product(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/photo-1": PNG_BYTES}
    await _fill_required(bot_ctx, name="Produk Terdaftar")
    for _ in range(5):
        await _send_text(bot_ctx, "/skip")
    await handle_update(bot_ctx, message_update(photo=True, file_id="photo-1"))
    await _send_text(bot_ctx, "/done")

    bot_ctx.client.clear()
    await _send_text(bot_ctx, "/products")

    assert "Produk Terdaftar" in bot_ctx.client.last_text()
    assert "1 media" in bot_ctx.client.last_text()


async def test_stats_counts_saved_product(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/photo-1": PNG_BYTES}
    await _fill_required(bot_ctx, name="Produk Statistik")
    for _ in range(5):
        await _send_text(bot_ctx, "/skip")
    await handle_update(bot_ctx, message_update(photo=True, file_id="photo-1"))
    await _send_text(bot_ctx, "/done")

    bot_ctx.client.clear()
    await _send_text(bot_ctx, "/stats")

    text = bot_ctx.client.last_text()
    assert "Produk: *1*" in text
    assert "Media: *1*" in text


async def test_markdown_in_product_name_is_escaped(bot_ctx):
    bot_ctx.client.files = {"files/photo-1": PNG_BYTES}
    await _fill_required(bot_ctx, name="Produk *Promo* _Spesial_")
    for _ in range(5):
        await _send_text(bot_ctx, "/skip")
    await handle_update(bot_ctx, message_update(photo=True, file_id="photo-1"))
    await _send_text(bot_ctx, "/done")

    assert "Produk \\*Promo\\* \\_Spesial\\_" in bot_ctx.client.last_text()
