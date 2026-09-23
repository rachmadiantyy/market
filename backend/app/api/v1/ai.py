from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models import AIGeneration, GenerationStatus, Product
from app.schemas import AIGenerateRequest, AIGenerationRead
from app.services import generation as generation_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post(
    "/generate",
    response_model=AIGenerationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_generation(
    payload: AIGenerateRequest, db: AsyncSession = Depends(get_db)
) -> AIGeneration:
    if payload.product_id is not None:
        product = await db.get(Product, payload.product_id)
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")

    try:
        record = await generation_service.create_generation_record(
            db,
            prompt=payload.prompt,
            product_id=payload.product_id,
            content_type=payload.content_type,
            platform=payload.platform,
            variations=payload.variations,
        )
    except generation_service.QueueUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gagal memasukkan job ke antrian",
        ) from None

    loaded = await generation_service.load_generation_with_product(db, record.id)
    assert loaded is not None
    return loaded


@router.get("/generations", response_model=list[AIGenerationRead])
async def list_generations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status_filter: GenerationStatus | None = Query(default=None, alias="status"),
    product_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> list[AIGeneration]:
    stmt = (
        select(AIGeneration)
        .options(selectinload(AIGeneration.product))
        .order_by(AIGeneration.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status_filter is not None:
        stmt = stmt.where(AIGeneration.status == status_filter)
    if product_id is not None:
        stmt = stmt.where(AIGeneration.product_id == product_id)

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/generations/{generation_id}", response_model=AIGenerationRead)
async def get_generation(
    generation_id: UUID, db: AsyncSession = Depends(get_db)
) -> AIGeneration:
    record = await generation_service.load_generation_with_product(db, generation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return record


@router.post(
    "/generations/{generation_id}/retry",
    response_model=AIGenerationRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_generation(
    generation_id: UUID, db: AsyncSession = Depends(get_db)
) -> AIGeneration:
    record = await generation_service.load_generation_with_product(db, generation_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Generation not found")

    if record.status in (GenerationStatus.queued, GenerationStatus.processing):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Generation is still in progress",
        )

    try:
        await generation_service.retry_generation_record(db, record)
    except generation_service.QueueUnavailableError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gagal memasukkan job ke antrian",
        ) from None

    loaded = await generation_service.load_generation_with_product(db, record.id)
    assert loaded is not None
    return loaded
