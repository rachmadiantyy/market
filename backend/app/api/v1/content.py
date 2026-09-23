from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import ContentItem, ContentStatus, ContentType, Job
from app.schemas import ContentGenerateRequest, ContentItemRead, JobRead
from app.services import queue

router = APIRouter(prefix="/content", tags=["content"])


@router.get("", response_model=list[ContentItemRead])
async def list_content(db: AsyncSession = Depends(get_db)) -> list[ContentItem]:
    result = await db.execute(
        select(ContentItem).order_by(ContentItem.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("/generate", response_model=JobRead, status_code=status.HTTP_202_ACCEPTED)
async def request_generation(
    payload: ContentGenerateRequest, db: AsyncSession = Depends(get_db)
) -> Job:
    content = ContentItem(
        product_id=payload.product_id,
        content_type=payload.content_type,
        status=ContentStatus.queued,
        prompt=payload.prompt,
    )
    db.add(content)
    await db.flush()

    task = (
        "generate_text"
        if payload.content_type == ContentType.text
        else "generate_image"
    )
    job = Job(queue="default", task=task, payload={"content_id": str(content.id)})
    db.add(job)
    await db.commit()
    await db.refresh(job)

    await queue.enqueue(
        "default",
        task,
        {"job_id": str(job.id), "content_id": str(content.id)},
    )
    return job
