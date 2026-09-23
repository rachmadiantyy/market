"""AI visual generation. Provider wiring is deferred to a later phase."""

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


async def generate_image(prompt: str) -> str:
    if not settings.ai_api_key:
        raise RuntimeError("AI_API_KEY is not configured")
    logger.info("generate_image called (provider not yet implemented)")
    raise NotImplementedError("Image generation provider not implemented yet")
