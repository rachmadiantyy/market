"""API tests: request creation, queue job creation, validation, retrieval."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AIGeneration, GenerationStatus, Job, Product
from app.services import generation as generation_service


async def _create_product(session_factory, name: str = "Produk Uji") -> Product:
    async with session_factory() as db:
        product = Product(name=name, description="Deskripsi produk uji")
        db.add(product)
        await db.commit()
        await db.refresh(product)
        return product


async def test_generate_creates_record_and_returns_id(client, session_factory):
    resp = await client.post(
        "/api/v1/ai/generate",
        json={
            "prompt": "Buat caption untuk produk kopi lokal",
            "content_type": "caption",
            "platform": "tiktok",
            "variations": 3,
        },
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()

    assert uuid.UUID(body["id"])
    assert body["status"] == "queued"
    assert body["prompt"] == "Buat caption untuk produk kopi lokal"
    assert body["variations"] == 3
    assert body["result"] is None
    assert body["error_message"] is None


async def test_generate_persists_record(client, session_factory):
    resp = await client.post(
        "/api/v1/ai/generate",
        json={"prompt": "Tulis hook menarik", "content_type": "hook"},
    )
    generation_id = resp.json()["id"]

    async with session_factory() as db:
        record = await db.get(AIGeneration, uuid.UUID(generation_id))
        assert record is not None
        assert record.status == GenerationStatus.queued


async def test_generate_creates_queue_job(client, session_factory):
    resp = await client.post(
        "/api/v1/ai/generate",
        json={"prompt": "Buat CTA singkat", "content_type": "cta"},
    )
    generation_id = resp.json()["id"]

    async with session_factory() as db:
        result = await db.execute(select(Job))
        jobs = list(result.scalars().all())

    assert len(jobs) == 1
    assert jobs[0].task == generation_service.GENERATION_TASK
    assert jobs[0].payload["generation_id"] == generation_id


async def test_generate_enqueues_to_redis(client, fake_redis):
    await client.post(
        "/api/v1/ai/generate",
        json={"prompt": "Buat deskripsi produk", "content_type": "product_description"},
    )
    depth = await fake_redis.llen(f"{generation_service.queue.DEFAULT_QUEUE}:default")
    assert depth == 1


async def test_generate_with_product(client, session_factory):
    product = await _create_product(session_factory, "Sepatu Lari")

    resp = await client.post(
        "/api/v1/ai/generate",
        json={"prompt": "Buat caption", "product_id": str(product.id)},
    )
    assert resp.status_code == 202
    assert resp.json()["product_id"] == str(product.id)
    assert resp.json()["product_name"] == "Sepatu Lari"


async def test_generate_unknown_product_returns_404(client):
    resp = await client.post(
        "/api/v1/ai/generate",
        json={"prompt": "Buat caption", "product_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": ""},
        {"prompt": "   "},
        {"prompt": "ok", "variations": 0},
        {"prompt": "ok", "variations": 21},
        {"prompt": "x" * 2001},
        {"prompt": "ok", "content_type": "not_a_type"},
        {"prompt": "ok", "platform": "myspace"},
    ],
)
async def test_generate_validation_rejects_invalid(client, payload):
    resp = await client.post("/api/v1/ai/generate", json=payload)
    assert resp.status_code == 422


async def test_list_generations(client):
    for i in range(3):
        await client.post("/api/v1/ai/generate", json={"prompt": f"prompt {i}"})

    resp = await client.get("/api/v1/ai/generations")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


async def test_list_generations_filter_by_status(client):
    await client.post("/api/v1/ai/generate", json={"prompt": "satu"})

    resp = await client.get("/api/v1/ai/generations?status=queued")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    resp = await client.get("/api/v1/ai/generations?status=completed")
    assert resp.status_code == 200
    assert len(resp.json()) == 0


async def test_get_generation_by_id(client):
    created = await client.post("/api/v1/ai/generate", json={"prompt": "ambil ini"})
    generation_id = created.json()["id"]

    resp = await client.get(f"/api/v1/ai/generations/{generation_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == generation_id


async def test_get_generation_not_found(client):
    resp = await client.get(f"/api/v1/ai/generations/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_generation_invalid_uuid(client):
    resp = await client.get("/api/v1/ai/generations/not-a-uuid")
    assert resp.status_code == 422
