"""Tests for Telegram -> existing AI generation pipeline integration."""

from sqlalchemy import select

from app.core.time import now
from app.models import AIContentType, AIGeneration, GenerationStatus, Job, Product
from app.services import generation as generation_service
from app.services.telegram.handlers import handle_update
from tests.telegram_helpers import callback_update, message_update

VALID_URL = "https://example.com/aff"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64


async def _create_product(session_factory, name: str = "Produk AI") -> Product:
    async with session_factory() as db:
        product = Product(
            name=name,
            affiliate_url=VALID_URL,
            category="Kecantikan",
            target_audience="Remaja putri",
            description="Serum vitamin C.",
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product


async def test_generate_button_offers_content_types(bot_ctx, session_factory):
    product = await _create_product(session_factory)
    bot_ctx.client.clear()

    await handle_update(bot_ctx, callback_update(f"ai:generate:{product.id}"))

    keyboard = bot_ctx.client.messages[-1]["reply_markup"]["inline_keyboard"]
    payloads = [button["callback_data"] for row in keyboard for button in row]
    assert f"ai:run:{product.id}:caption" in payloads
    assert f"ai:run:{product.id}:hook" in payloads
    assert f"ai:run:{product.id}:short_video_script" in payloads
    assert f"ai:run:{product.id}:cta" in payloads


async def test_generate_creates_generation_and_job(bot_ctx, session_factory, fake_redis):
    product = await _create_product(session_factory, "Produk Generate")
    bot_ctx.client.clear()

    await handle_update(bot_ctx, callback_update(f"ai:run:{product.id}:caption"))

    async with session_factory() as db:
        generations = list((await db.execute(select(AIGeneration))).scalars().all())
        jobs = list((await db.execute(select(Job))).scalars().all())

    assert len(generations) == 1
    record = generations[0]
    assert record.product_id == product.id
    assert record.type == AIContentType.caption
    assert record.status == GenerationStatus.queued
    assert "Produk Generate" in record.prompt
    assert "Kecantikan" in record.prompt
    assert "Remaja putri" in record.prompt

    # Reuses the exact same task/queue as the HTTP API.
    assert len(jobs) == 1
    assert jobs[0].task == generation_service.GENERATION_TASK
    assert jobs[0].payload["generation_id"] == str(record.id)

    depth = await fake_redis.llen(
        f"{generation_service.queue.DEFAULT_QUEUE}:{generation_service.GENERATION_QUEUE}"
    )
    assert depth == 1

    assert "Generasi dibuat" in bot_ctx.client.last_text()


async def test_analyze_uses_product_description_type(
    bot_ctx, session_factory, fake_redis
):
    product = await _create_product(session_factory, "Produk Analisis")
    bot_ctx.client.clear()

    await handle_update(bot_ctx, callback_update(f"ai:analyze:{product.id}"))

    async with session_factory() as db:
        record = (await db.execute(select(AIGeneration))).scalars().one()

    assert record.type == AIContentType.product_description
    assert record.variations == 1


async def test_generate_unknown_product(bot_ctx):
    bot_ctx.client.clear()

    await handle_update(
        bot_ctx,
        callback_update("ai:run:00000000-0000-0000-0000-000000000000:caption"),
    )

    assert "tidak ditemukan" in bot_ctx.client.last_text().lower()


async def test_generate_unknown_content_type(bot_ctx, session_factory):
    product = await _create_product(session_factory, "Produk Tipe")
    bot_ctx.client.clear()

    await handle_update(bot_ctx, callback_update(f"ai:run:{product.id}:bogus"))

    assert "tidak dikenal" in bot_ctx.client.last_text().lower()


async def test_status_shows_queued(bot_ctx, session_factory):
    product = await _create_product(session_factory, "Produk Status")
    async with session_factory() as db:
        record = AIGeneration(
            product_id=product.id,
            type=AIContentType.caption,
            prompt="test",
            status=GenerationStatus.queued,
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

    bot_ctx.client.clear()
    await handle_update(bot_ctx, callback_update(f"ai:status:{record.id}"))

    assert "queued" in bot_ctx.client.last_text().lower()


async def test_status_shows_completed_variations(bot_ctx, session_factory):
    product = await _create_product(session_factory, "Produk Selesai")
    async with session_factory() as db:
        record = AIGeneration(
            product_id=product.id,
            type=AIContentType.caption,
            prompt="test",
            status=GenerationStatus.completed,
            result={
                "variations": [
                    {"index": 1, "text": "Variasi pertama"},
                    {"index": 2, "text": "Variasi kedua"},
                ]
            },
            completed_at=now(),
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

    bot_ctx.client.clear()
    await handle_update(bot_ctx, callback_update(f"ai:status:{record.id}"))

    text = bot_ctx.client.last_text()
    assert "2 variasi" in text
    assert "Variasi pertama" in text
    assert "Variasi kedua" in text


async def test_status_shows_failure_with_retry_button(bot_ctx, session_factory):
    product = await _create_product(session_factory, "Produk Gagal")
    async with session_factory() as db:
        record = AIGeneration(
            product_id=product.id,
            type=AIContentType.caption,
            prompt="test",
            status=GenerationStatus.failed,
            error_message="Gagal memanggil penyedia AI: timeout",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

    bot_ctx.client.clear()
    await handle_update(bot_ctx, callback_update(f"ai:status:{record.id}"))

    text = bot_ctx.client.last_text()
    assert "Generation failed" in text
    assert "timeout" in text

    keyboard = bot_ctx.client.messages[-1]["reply_markup"]["inline_keyboard"]
    payloads = [button["callback_data"] for row in keyboard for button in row]
    assert f"ai:retry:{record.id}" in payloads


async def test_retry_failed_generation(bot_ctx, session_factory, fake_redis):
    product = await _create_product(session_factory, "Produk Retry")
    async with session_factory() as db:
        record = AIGeneration(
            product_id=product.id,
            type=AIContentType.caption,
            prompt="test",
            status=GenerationStatus.failed,
            error_message="boom",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

    bot_ctx.client.clear()
    await handle_update(bot_ctx, callback_update(f"ai:retry:{record.id}"))

    async with session_factory() as db:
        refreshed = await db.get(AIGeneration, record.id)
        jobs = list((await db.execute(select(Job))).scalars().all())

    assert refreshed.status == GenerationStatus.queued
    assert refreshed.error_message is None
    assert len(jobs) == 1
    assert "dimasukkan kembali" in bot_ctx.client.last_text()


async def test_status_unknown_generation(bot_ctx):
    bot_ctx.client.clear()

    await handle_update(
        bot_ctx,
        callback_update("ai:status:00000000-0000-0000-0000-000000000000"),
    )

    assert "tidak ditemukan" in bot_ctx.client.last_text().lower()


async def test_ai_cancel(bot_ctx):
    bot_ctx.client.clear()

    await handle_update(bot_ctx, callback_update("ai:cancel"))

    assert "Dibatalkan" in bot_ctx.client.last_text()


async def test_prompt_is_capped_at_2000_chars(bot_ctx, session_factory, fake_redis):
    async with session_factory() as db:
        product = Product(
            name="N" * 200,
            affiliate_url=VALID_URL,
            category="C" * 100,
            target_audience="A" * 500,
            description="D" * 1500,
        )
        db.add(product)
        await db.commit()
        await db.refresh(product)

    bot_ctx.client.clear()
    await handle_update(bot_ctx, callback_update(f"ai:run:{product.id}:caption"))

    async with session_factory() as db:
        record = (await db.execute(select(AIGeneration))).scalars().one()

    assert len(record.prompt) <= 2000
