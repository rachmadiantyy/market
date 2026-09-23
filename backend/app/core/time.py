from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def app_tz() -> ZoneInfo:
    return ZoneInfo(settings.timezone)


def now() -> datetime:
    """Current time in the app timezone (default Asia/Jakarta)."""
    return datetime.now(app_tz())


def to_app_tz(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(app_tz())
