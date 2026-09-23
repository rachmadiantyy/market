"""AI text generation orchestration.

The API route creates the record and enqueues; the worker consumes and calls
the provider. Both share the helpers here.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import get_logger
from app.models import (
    AIContentType,
    AIGeneration,
    AIPlatform,
    GenerationStatus,
    Job,
    JobStatus,
)
from app.providers.ai import (
    AIProvider,
    AIProviderConfigError,
    AIProviderError,
    AIResponseError,
    get_ai_provider,
)
from app.providers.ai.openai_compatible import redact
from app.schemas import AIResultPayload, AIResultVariation
from app.services import queue
from app.services.prompt_templates import prompt_template_service

logger = get_logger(__name__)

GENERATION_TASK = "generate_content"
GENERATION_QUEUE = "default"


def build_user_error(exc: Exception) -> str:
    """Map an internal exception to a safe, credential-free message."""
    if isinstance(exc, AIProviderConfigError):
        return "Konfigurasi AI belum lengkap. Hubungi administrator."
    if isinstance(exc, AIProviderError):
        return f"Gagal memanggil penyedia AI: {redact(str(exc))}"
    if isinstance(exc, AIResponseError):
        return f"Respons AI tidak valid: {exc}"
    return "Terjadi kesalahan internal saat memproses generasi."


async def enqueue_generation(
    generation_id: UUID, *, job_id: str | None = None, attempt: int = 0
) -> str:
    """Push a generation job onto Redis. Returns the queue job id."""
    return await queue.enqueue(
        GENERATION_QUEUE,
        GENERATION_TASK,
        {
            "generation_id": str(generation_id),
            "job_id": job_id,
            "attempt": attempt,
        },
    )


class QueueUnavailableError(Exception):
    """Raised when a generation record exists but could not be enqueued."""


async def create_generation_record(
    db: AsyncSession,
    *,
    prompt: str,
    product_id: UUID | None = None,
    content_type: AIContentType = AIContentType.caption,
    platform: AIPlatform = AIPlatform.tiktok,
    variations: int = 3,
    notify_chat_id: str | None = None,
) -> AIGeneration:
    """Create a queued generation plus its Job row, then enqueue it.

    Shared by the HTTP API and the Telegram bot so the pipeline is identical.
    Raises QueueUnavailableError if the job could not be enqueued (the record is
    then marked failed so the caller never reports a false success).
    """
    record = AIGeneration(
        product_id=product_id,
        type=content_type,
        platform=platform,
        variations=variations,
        prompt=prompt,
        status=GenerationStatus.queued,
        notify_chat_id=notify_chat_id,
    )
    db.add(record)
    await db.flush()

    job = Job(
        queue=GENERATION_QUEUE,
        task=GENERATION_TASK,
        payload={"generation_id": str(record.id)},
    )
    db.add(job)
    await db.commit()

    try:
        await enqueue_generation(record.id, job_id=str(job.id))
    except Exception as exc:  # noqa: BLE001
        record.status = GenerationStatus.failed
        record.error_message = "Antrian tidak tersedia. Coba lagi nanti."
        job.status = JobStatus.failed
        await db.commit()
        raise QueueUnavailableError(str(exc)) from exc

    return record


async def load_generation_with_product(
    db: AsyncSession, generation_id: UUID
) -> AIGeneration | None:
    stmt = (
        select(AIGeneration)
        .options(selectinload(AIGeneration.product))
        .where(AIGeneration.id == generation_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def retry_generation_record(
    db: AsyncSession, record: AIGeneration
) -> AIGeneration:
    """Re-queue a finished generation. Caller must validate current status."""
    job = Job(
        queue=GENERATION_QUEUE,
        task=GENERATION_TASK,
        payload={"generation_id": str(record.id)},
    )
    db.add(job)

    record.status = GenerationStatus.queued
    record.error_message = None
    record.completed_at = None
    record.result = None
    await db.commit()

    try:
        await enqueue_generation(record.id, job_id=str(job.id))
    except Exception as exc:  # noqa: BLE001
        record.status = GenerationStatus.failed
        record.error_message = "Antrian tidak tersedia. Coba lagi nanti."
        job.status = JobStatus.failed
        await db.commit()
        raise QueueUnavailableError(str(exc)) from exc

    return record


def parse_provider_output(raw: str, expected: int) -> AIResultPayload:
    """Parse and validate raw provider text into a structured payload."""
    import json
    import re

    text = raw.strip()
    if not text:
        raise AIResponseError("Respons AI kosong")

    # Tolerate ```json ... ``` fences.
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    data: object
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise AIResponseError("Respons AI bukan JSON yang valid") from exc

    if isinstance(data, dict):
        raw_variations = data.get("variations")
    elif isinstance(data, list):
        raw_variations = data
    else:
        raise AIResponseError("Respons AI tidak berisi daftar variasi")

    if not isinstance(raw_variations, list) or not raw_variations:
        raise AIResponseError("Respons AI tidak berisi daftar variasi")

    variations: list[AIResultVariation] = []
    for item in raw_variations:
        if isinstance(item, str):
            content = item.strip()
        elif isinstance(item, dict):
            content = str(item.get("text") or item.get("content") or "").strip()
        else:
            continue
        if not content:
            continue
        variations.append(
            AIResultVariation(index=len(variations) + 1, text=content[:5000])
        )

    if not variations:
        raise AIResponseError("Tidak ada variasi valid pada respons AI")

    return AIResultPayload(variations=variations[:expected])


async def process_generation(
    generation: AIGeneration, provider: AIProvider | None = None
) -> AIResultPayload:
    """Call the provider for a generation and return the validated payload.

    Raises AIProviderError / AIResponseError so the caller can decide retry.
    """
    provider = provider or get_ai_provider()

    product = generation.product
    built = prompt_template_service.build(
        content_type=generation.type,
        platform=generation.platform,
        prompt=generation.prompt,
        variations=generation.variations,
        product_name=product.name if product else None,
        product_description=product.description if product else None,
        affiliate_url=product.affiliate_url if product else None,
    )

    logger.info(
        "Calling AI provider %s (model=%s, template=%s, generation=%s)",
        provider.name,
        provider.model,
        built.template,
        generation.id,
    )

    raw = await provider.generate(
        system_prompt=built.system_prompt,
        user_prompt=built.user_prompt,
    )
    payload = parse_provider_output(raw, generation.variations)
    generation.model = provider.model or None
    return payload


def is_retryable(exc: Exception) -> bool:
    """Config errors will never succeed on retry; everything else might."""
    return not isinstance(exc, AIProviderConfigError)


def max_attempts() -> int:
    return max(1, settings.ai_max_retries)
