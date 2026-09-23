"""Task handlers for the Redis worker.

Kept separate from the runner loop so handlers can be unit-tested without Redis.
"""

import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.logging import get_logger
from app.models import AIGeneration, GenerationStatus, Job, JobStatus
from app.providers.ai import AIProvider
from app.services import generation as generation_service
from app.services import notifications, queue

logger = get_logger(__name__)

COMPLETED = "completed"
RETRIED = "retried"
FAILED = "failed"
SKIPPED = "skipped"


async def _update_job(
    db: AsyncSession,
    job_id: str | None,
    *,
    status: JobStatus,
    attempts: int | None = None,
    error: str | None = None,
) -> None:
    if not job_id:
        return
    try:
        job_uuid = UUID(job_id)
    except (ValueError, TypeError):
        return
    job = await db.get(Job, job_uuid)
    if job is None:
        return
    job.status = status
    if attempts is not None:
        job.attempts = attempts
    if error is not None:
        job.error = error
    if status == JobStatus.running and job.started_at is None:
        from app.core.time import now

        job.started_at = now()
    if status in (JobStatus.succeeded, JobStatus.failed):
        from app.core.time import now

        job.finished_at = now()


async def handle_generation_job(
    job: dict,
    *,
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
    provider: AIProvider | None = None,
    max_retries: int | None = None,
    retry_delay_seconds: float = 1.0,
) -> str:
    """Process one generation job.

    Returns one of: completed, retried, failed, skipped.
    Never raises for expected provider/validation failures.
    """
    payload = job.get("payload") or {}
    raw_id = payload.get("generation_id")
    job_id = payload.get("job_id")
    attempt = int(payload.get("attempt", 0))
    limit = max_retries if max_retries is not None else generation_service.max_attempts()

    if not raw_id:
        logger.warning("Generation job without generation_id (job=%s)", job.get("id"))
        return SKIPPED

    try:
        generation_id = UUID(str(raw_id))
    except (ValueError, TypeError):
        logger.warning("Generation job with invalid generation_id: %s", raw_id)
        return SKIPPED

    async with session_factory() as db:
        stmt = (
            select(AIGeneration)
            .options(selectinload(AIGeneration.product))
            .where(AIGeneration.id == generation_id)
        )
        generation = (await db.execute(stmt)).scalar_one_or_none()
        if generation is None:
            logger.warning("Generation %s not found", generation_id)
            return SKIPPED

        # Idempotency: do not redo finished work.
        if generation.status == GenerationStatus.completed:
            logger.info("Generation %s already completed, skipping", generation_id)
            return SKIPPED

        generation.status = GenerationStatus.processing
        generation.error_message = None
        await _update_job(db, job_id, status=JobStatus.running, attempts=attempt + 1)
        await db.commit()

        try:
            result = await generation_service.process_generation(
                generation, provider=provider
            )
        except Exception as exc:  # noqa: BLE001
            return await _handle_failure(
                db,
                generation,
                exc,
                job_id=job_id,
                attempt=attempt,
                limit=limit,
                retry_delay_seconds=retry_delay_seconds,
            )

        from app.core.time import now

        generation.result = result.model_dump()
        generation.status = GenerationStatus.completed
        generation.error_message = None
        generation.completed_at = now()
        await _update_job(db, job_id, status=JobStatus.succeeded, attempts=attempt + 1)
        notify_chat_id = generation.notify_chat_id
        await db.commit()

    await _notify_finished(notify_chat_id, generation_id, GenerationStatus.completed)

    logger.info("Generation %s completed", generation_id)
    return COMPLETED


async def _notify_finished(
    chat_id: str | None, generation_id: UUID, status: GenerationStatus
) -> None:
    """Push a terminal-state event so the chat UI can render the result.

    Best-effort: a notification failure must never mark a finished job as failed.
    """
    if not chat_id:
        return
    await notifications.notify_generation_finished(
        chat_id=chat_id,
        generation_id=str(generation_id),
        status=status.value,
    )


async def _handle_failure(
    db: AsyncSession,
    generation: AIGeneration,
    exc: Exception,
    *,
    job_id: str | None,
    attempt: int,
    limit: int,
    retry_delay_seconds: float,
) -> str:
    logger.warning(
        "Generation %s failed (attempt %s/%s): %s",
        generation.id,
        attempt + 1,
        limit,
        type(exc).__name__,
    )

    retryable = generation_service.is_retryable(exc)
    if retryable and attempt + 1 < limit:
        generation.status = GenerationStatus.queued
        generation.error_message = None
        await _update_job(db, job_id, status=JobStatus.pending, attempts=attempt + 1)
        await db.commit()

        if retry_delay_seconds > 0:
            await asyncio.sleep(retry_delay_seconds)

        try:
            await generation_service.enqueue_generation(
                generation.id, job_id=job_id, attempt=attempt + 1
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to re-enqueue generation %s", generation.id)
            generation.status = GenerationStatus.failed
            generation.error_message = "Antrian tidak tersedia saat mencoba ulang."
            await _update_job(db, job_id, status=JobStatus.failed)
            notify_chat_id = generation.notify_chat_id
            await db.commit()
            await _notify_finished(notify_chat_id, generation.id, GenerationStatus.failed)
            return FAILED
        return RETRIED

    generation.status = GenerationStatus.failed
    generation.error_message = generation_service.build_user_error(exc)
    await _update_job(db, job_id, status=JobStatus.failed, attempts=attempt + 1)
    notify_chat_id = generation.notify_chat_id
    await db.commit()

    await _notify_finished(notify_chat_id, generation.id, GenerationStatus.failed)
    return FAILED


async def dispatch(job: dict) -> str:
    """Route a queue message to its handler."""
    task = job.get("task")
    if task == generation_service.GENERATION_TASK:
        return await handle_generation_job(job)
    logger.warning("No handler registered for task '%s'", task)
    return SKIPPED
