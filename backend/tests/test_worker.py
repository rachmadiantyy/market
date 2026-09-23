"""Worker tests: success, failure, provider failure, retry, status updates."""

import json
import uuid

from sqlalchemy import select

from app.models import AIGeneration, AIContentType, GenerationStatus, AIPlatform, Job, JobStatus
from app.providers.ai.base import AIProviderConfigError, AIProviderError
from app.services import generation as generation_service
from app.workers.handlers import (
    COMPLETED,
    FAILED,
    RETRIED,
    SKIPPED,
    handle_generation_job,
)
from tests.conftest import StubProvider


async def _seed_generation(
    session_factory, *, variations: int = 2, status: GenerationStatus = GenerationStatus.queued
) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as db:
        record = AIGeneration(
            type=AIContentType.caption,
            platform=AIPlatform.tiktok,
            variations=variations,
            prompt="Buat caption produk",
            status=status,
        )
        db.add(record)
        await db.flush()
        job = Job(
            queue="default",
            task=generation_service.GENERATION_TASK,
            payload={"generation_id": str(record.id)},
        )
        db.add(job)
        await db.commit()
        return record.id, job.id


async def _job_message(generation_id, job_id, attempt: int = 0) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "task": generation_service.GENERATION_TASK,
        "payload": {
            "generation_id": str(generation_id),
            "job_id": str(job_id),
            "attempt": attempt,
        },
    }


async def test_worker_success_saves_result(session_factory, fake_redis):
    generation_id, job_id = await _seed_generation(session_factory)
    provider = StubProvider(
        output=json.dumps({"variations": ["varian satu", "varian dua"]})
    )

    outcome = await handle_generation_job(
        await _job_message(generation_id, job_id),
        session_factory=session_factory,
        provider=provider,
    )

    assert outcome == COMPLETED

    async with session_factory() as db:
        record = await db.get(AIGeneration, generation_id)
        assert record.status == GenerationStatus.completed
        assert record.completed_at is not None
        assert record.error_message is None
        assert record.model == "stub-model"
        texts = [v["text"] for v in record.result["variations"]]
        assert texts == ["varian satu", "varian dua"]


async def test_worker_success_marks_job_succeeded(session_factory, fake_redis):
    generation_id, job_id = await _seed_generation(session_factory)

    await handle_generation_job(
        await _job_message(generation_id, job_id),
        session_factory=session_factory,
        provider=StubProvider(output='{"variations": ["a"]}'),
    )

    async with session_factory() as db:
        job = await db.get(Job, job_id)
        assert job.status == JobStatus.succeeded
        assert job.started_at is not None
        assert job.finished_at is not None


async def test_worker_status_transitions_to_completed(session_factory, fake_redis):
    generation_id, job_id = await _seed_generation(session_factory)
    seen: list[GenerationStatus] = []

    class RecordingProvider(StubProvider):
        async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
            async with session_factory() as probe:
                current = await probe.get(AIGeneration, generation_id)
                seen.append(current.status)
            return await super().generate(
                system_prompt=system_prompt, user_prompt=user_prompt
            )

    await handle_generation_job(
        await _job_message(generation_id, job_id),
        session_factory=session_factory,
        provider=RecordingProvider(output='{"variations": ["x"]}'),
    )

    assert seen == [GenerationStatus.processing]


async def test_worker_failure_records_error_and_keeps_running(
    session_factory, fake_redis
):
    generation_id, job_id = await _seed_generation(session_factory)
    provider = StubProvider(error=AIProviderError("provider sedang down"))

    outcome = await handle_generation_job(
        await _job_message(generation_id, job_id),
        session_factory=session_factory,
        provider=provider,
        max_retries=1,
    )

    assert outcome == FAILED

    async with session_factory() as db:
        record = await db.get(AIGeneration, generation_id)
        assert record.status == GenerationStatus.failed
        assert record.error_message is not None
        assert "Gagal memanggil penyedia AI" in record.error_message
        assert record.completed_at is None

        job = await db.get(Job, job_id)
        assert job.status == JobStatus.failed


async def test_worker_provider_failure_is_retried_then_succeeds(
    session_factory, fake_redis
):
    generation_id, job_id = await _seed_generation(session_factory)
    provider = StubProvider(error=AIProviderError("rate limit"))

    outcome = await handle_generation_job(
        await _job_message(generation_id, job_id),
        session_factory=session_factory,
        provider=provider,
        max_retries=3,
        retry_delay_seconds=0,
    )

    assert outcome == RETRIED

    async with session_factory() as db:
        record = await db.get(AIGeneration, generation_id)
        assert record.status == GenerationStatus.queued
        assert record.error_message is None

    # The re-enqueued job should carry attempt=1 and succeed on the second run.
    queued = await fake_redis.brpop(f"{generation_service.queue.DEFAULT_QUEUE}:default", timeout=1)
    message = json.loads(queued[1])
    assert message["payload"]["attempt"] == 1

    outcome = await handle_generation_job(
        message,
        session_factory=session_factory,
        provider=StubProvider(output='{"variations": ["akhirnya"]}'),
        max_retries=3,
    )
    assert outcome == COMPLETED


async def test_worker_config_error_fails_without_retry(session_factory, fake_redis):
    generation_id, job_id = await _seed_generation(session_factory)
    provider = StubProvider(error=AIProviderConfigError("missing key"))

    outcome = await handle_generation_job(
        await _job_message(generation_id, job_id),
        session_factory=session_factory,
        provider=provider,
        max_retries=5,
    )

    assert outcome == FAILED

    async with session_factory() as db:
        record = await db.get(AIGeneration, generation_id)
        assert record.status == GenerationStatus.failed
        assert "Konfigurasi AI belum lengkap" in record.error_message


async def test_worker_retry_exhaustion(session_factory, fake_redis):
    generation_id, job_id = await _seed_generation(session_factory)
    provider = StubProvider(error=AIProviderError("selalu gagal"))

    outcome = await handle_generation_job(
        await _job_message(generation_id, job_id, attempt=2),
        session_factory=session_factory,
        provider=provider,
        max_retries=3,
        retry_delay_seconds=0,
    )

    assert outcome == FAILED


async def test_worker_skips_already_completed_generation(session_factory, fake_redis):
    generation_id, job_id = await _seed_generation(
        session_factory, status=GenerationStatus.completed
    )
    provider = StubProvider(output='{"variations": ["jangan dipakai"]}')

    outcome = await handle_generation_job(
        await _job_message(generation_id, job_id),
        session_factory=session_factory,
        provider=provider,
    )

    assert outcome == SKIPPED
    assert provider.calls == 0


async def test_worker_skips_missing_generation(session_factory, fake_redis):
    outcome = await handle_generation_job(
        await _job_message(uuid.uuid4(), uuid.uuid4()),
        session_factory=session_factory,
        provider=StubProvider(),
    )
    assert outcome == SKIPPED


async def test_retry_endpoint_requeues_failed_generation(client, session_factory, fake_redis):
    generation_id, _ = await _seed_generation(
        session_factory, status=GenerationStatus.failed
    )
    async with session_factory() as db:
        record = await db.get(AIGeneration, generation_id)
        record.error_message = "gagal sebelumnya"
        await db.commit()

    resp = await client.post(f"/api/v1/ai/generations/{generation_id}/retry")
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["error_message"] is None

    async with session_factory() as db:
        jobs = list((await db.execute(select(Job))).scalars().all())
    assert len(jobs) == 2


async def test_retry_endpoint_rejects_in_progress(client, session_factory, fake_redis):
    generation_id, _ = await _seed_generation(
        session_factory, status=GenerationStatus.processing
    )

    resp = await client.post(f"/api/v1/ai/generations/{generation_id}/retry")
    assert resp.status_code == 409
