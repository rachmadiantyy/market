from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import AnalyticsEvent, ContentItem, Job, Product
from app.services import queue

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/summary")
async def summary(db: AsyncSession = Depends(get_db)) -> dict:
    products = await db.scalar(select(func.count()).select_from(Product))
    content = await db.scalar(select(func.count()).select_from(ContentItem))
    jobs = await db.scalar(select(func.count()).select_from(Job))
    events = await db.scalar(select(func.count()).select_from(AnalyticsEvent))
    revenue = await db.scalar(select(func.coalesce(func.sum(AnalyticsEvent.value), 0)))

    return {
        "products": products or 0,
        "content_items": content or 0,
        "jobs": jobs or 0,
        "events": events or 0,
        "tracked_value": float(revenue or 0),
        "queue_depth": await queue.queue_depth("default"),
    }
