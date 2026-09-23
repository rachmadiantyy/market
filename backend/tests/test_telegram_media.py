"""Tests for Telegram media handling: validation, storage, retry."""

from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import MediaType, Product, ProductMedia
from app.services import media_storage
from app.services.telegram.handlers import handle_update
from tests.telegram_helpers import callback_update, message_update

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
MP4_BYTES = b"\x00\x00\x00\x18ftypmp42" + b"0" * 64
VALID_URL = "https://example.com/aff"


async def _to_media_step(ctx, name: str = "Produk Media") -> None:
    await handle_update(ctx, message_update("/add"))
    await handle_update(ctx, message_update(name))
    await handle_update(ctx, message_update(VALID_URL))
    for _ in range(5):
        await handle_update(ctx, message_update("/skip"))


async def test_photo_stored_with_generated_filename(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/photo-1": PNG_BYTES}
    await _to_media_step(bot_ctx)

    await handle_update(bot_ctx, message_update(photo=True, file_id="photo-1"))
    await handle_update(bot_ctx, message_update("/done"))

    async with session_factory() as db:
        media = (await db.execute(select(ProductMedia))).scalars().one()

    # Filename is ours (uuid), never Telegram's.
    assert media.file_path.endswith(".jpg")
    name = Path(media.file_path).name
    assert name != "photo-1"
    assert len(name) == len("a" * 32) + len(".jpg")
    assert media.mime_type == "image/jpeg"
    assert media.media_type == MediaType.image
    assert media.telegram_file_id == "photo-1"
    assert (Path(settings.uploads_dir) / media.file_path).read_bytes() == PNG_BYTES


async def test_video_stored_with_mime_extension(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/video-1": MP4_BYTES}
    await _to_media_step(bot_ctx, name="Produk Video")

    await handle_update(
        bot_ctx,
        message_update(video=True, file_id="video-1", file_name="../../etc/passwd.mp4"),
    )
    await handle_update(bot_ctx, message_update("/done"))

    async with session_factory() as db:
        media = (await db.execute(select(ProductMedia))).scalars().one()

    assert media.media_type == MediaType.video
    assert media.mime_type == "video/mp4"
    assert media.file_path.endswith(".mp4")
    # Original filename is recorded for display only, with path components stripped.
    assert media.original_filename == "passwd.mp4"
    assert ".." not in media.file_path
    assert "/etc/" not in media.file_path


async def test_unique_filenames_for_identical_uploads(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/p1": PNG_BYTES, "files/p2": PNG_BYTES}
    await _to_media_step(bot_ctx, name="Produk Duplikat")

    await handle_update(bot_ctx, message_update(photo=True, file_id="p1"))
    await handle_update(bot_ctx, message_update(photo=True, file_id="p2"))
    await handle_update(bot_ctx, message_update("/done"))

    async with session_factory() as db:
        media = list((await db.execute(select(ProductMedia))).scalars().all())

    paths = {m.file_path for m in media}
    assert len(paths) == 2


@pytest.mark.parametrize("mime", ["application/pdf", "text/plain", "video/x-msvideo"])
async def test_disallowed_mime_rejected(bot_ctx, session_factory, mime):
    await _to_media_step(bot_ctx, name="Produk Mime")
    bot_ctx.client.clear()

    await handle_update(
        bot_ctx,
        message_update(video=True, file_id="bad", video_mime=mime, file_name="x.bin"),
    )

    assert "tidak" in bot_ctx.client.last_text().lower()
    state = await bot_ctx.store.get("111111")
    assert state.data.get("media") is None


async def test_oversized_declared_file_rejected(bot_ctx):
    await _to_media_step(bot_ctx, name="Produk Besar")
    bot_ctx.client.clear()
    oversized = settings.media_max_file_size_bytes + 1

    await handle_update(
        bot_ctx, message_update(video=True, file_id="big", file_size=oversized)
    )

    assert "melebihi batas" in bot_ctx.client.last_text()
    state = await bot_ctx.store.get("111111")
    assert not state.data.get("media")


async def test_oversized_download_marks_media_failed(
    bot_ctx, session_factory, monkeypatch
):
    """Declared size lies; the actual download must still be capped."""
    monkeypatch.setattr(settings, "media_max_file_size_mb", 1)
    bot_ctx.client.files = {"files/huge": b"x" * (2 * 1024 * 1024)}
    await _to_media_step(bot_ctx, name="Produk Unduh Besar")

    # Declared size is small (1 KB) so it passes the pre-check...
    await handle_update(
        bot_ctx, message_update(video=True, file_id="huge", file_size=1024)
    )
    # ...but save_bytes enforces the real limit.
    await handle_update(bot_ctx, message_update("/done"))

    async with session_factory() as db:
        product = (await db.execute(select(Product))).scalars().one()
        media_count = len(
            (await db.execute(select(ProductMedia))).scalars().all()
        )
    pending = (product.metadata_ or {}).get("pending_media") or []

    # Product is still saved; the media is reported as failed and retryable.
    assert media_count == 0
    assert len(pending) == 1
    assert "gagal diunduh" in bot_ctx.client.last_text().lower()

    keyboard = bot_ctx.client.messages[-1]["reply_markup"]["inline_keyboard"]
    payloads = [b["callback_data"] for row in keyboard for b in row if "callback_data" in b]
    assert f"add:retry_media:{product.id}" in payloads


async def test_get_file_failure_is_recoverable(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/good": PNG_BYTES}
    bot_ctx.client.fail_get_file_for = {"bad"}
    await _to_media_step(bot_ctx, name="Produk Gagal")

    await handle_update(bot_ctx, message_update(photo=True, file_id="bad"))
    await handle_update(bot_ctx, message_update("/done"))

    async with session_factory() as db:
        product = (await db.execute(select(Product))).scalars().one()
    pending = (product.metadata_ or {}).get("pending_media") or []
    assert len(pending) == 1

    # Retry succeeds once the failure is cleared.
    bot_ctx.client.fail_get_file_for = set()
    bot_ctx.client.files = {"files/bad": PNG_BYTES}
    bot_ctx.client.clear()

    await handle_update(bot_ctx, callback_update(f"add:retry_media:{product.id}"))

    assert "berhasil diunduh ulang" in bot_ctx.client.last_text()

    async with session_factory() as db:
        media = (await db.execute(select(ProductMedia))).scalars().all()
        refreshed = await db.get(Product, product.id)

    assert len(media) == 1
    assert not (refreshed.metadata_ or {}).get("pending_media")


async def test_retry_media_without_pending(bot_ctx, session_factory):
    bot_ctx.client.files = {"files/p1": PNG_BYTES}
    await _to_media_step(bot_ctx, name="Produk Tanpa Pending")
    await handle_update(bot_ctx, message_update(photo=True, file_id="p1"))
    await handle_update(bot_ctx, message_update("/done"))

    async with session_factory() as db:
        product = (await db.execute(select(Product))).scalars().one()

    bot_ctx.client.clear()
    await handle_update(bot_ctx, callback_update(f"add:retry_media:{product.id}"))

    assert "Tidak ada media" in bot_ctx.client.last_text()


async def test_retry_media_unknown_product(bot_ctx):
    await handle_update(
        bot_ctx,
        callback_update("add:retry_media:00000000-0000-0000-0000-000000000000"),
    )

    assert "tidak ditemukan" in bot_ctx.client.last_text().lower()


async def test_media_limit_enforced(bot_ctx, monkeypatch):
    bot_ctx.client.files = {f"files/p{i}": PNG_BYTES for i in range(12)}
    await _to_media_step(bot_ctx, name="Produk Limit")
    monkeypatch.setattr(
        "app.services.telegram.handlers.MAX_MEDIA_PER_PRODUCT", 2
    )

    await handle_update(bot_ctx, message_update(photo=True, file_id="p0"))
    await handle_update(bot_ctx, message_update(photo=True, file_id="p1"))
    bot_ctx.client.clear()
    await handle_update(bot_ctx, message_update(photo=True, file_id="p2"))

    assert "Maksimal" in bot_ctx.client.last_text()


async def test_sanitize_filename_strips_paths():
    assert media_storage.sanitize_filename("../../etc/passwd") == "passwd"
    assert media_storage.sanitize_filename("/tmp/a/b.png") == "b.png"
    assert media_storage.sanitize_filename(None) is None
    assert media_storage.sanitize_filename("") is None


async def test_save_bytes_rejects_disallowed_mime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    import pytest as _pytest

    from app.services.media_storage import MediaTypeNotAllowedError

    with _pytest.raises(MediaTypeNotAllowedError):
        media_storage.save_bytes(
            data=b"data", product_id=UUID(int=1), mime="application/x-msdownload"
        )
