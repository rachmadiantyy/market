"""Telegram bot service package.

Kept intentionally light at import time so the FastAPI app can query bot
configuration without pulling in the whole runtime.
"""

from app.core.config import settings


def bot_token_configured() -> bool:
    """Whether a bot token is present (used by the health endpoint)."""
    return bool(settings.telegram_bot_token)


__all__ = ["bot_token_configured"]
