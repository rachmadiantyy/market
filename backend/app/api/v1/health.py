from fastapi import APIRouter
from sqlalchemy import text

from app.core.config import settings
from app.core.database import engine
from app.core.redis import ping_redis
from app.core.time import now
from app.services.telegram import bot_token_configured

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "time": now().isoformat(), "timezone": settings.timezone}


@router.get("/health/ready")
async def readiness() -> dict:
    db_ok = False
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    redis_ok = await ping_redis()

    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "database": db_ok,
        "redis": redis_ok,
        "telegram_configured": bot_token_configured(),
        "time": now().isoformat(),
    }
