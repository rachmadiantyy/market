"""Redis-backed conversation state.

State lives in Redis (not process memory) so the bot survives a restart.
A TTL guarantees abandoned conversations expire instead of leaking forever.
"""

import enum
import json
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger(__name__)

STATE_KEY_PREFIX = "telegram:state"
LAST_PRODUCT_PREFIX = "telegram:last_product"


class AddStep(str, enum.Enum):
    """Steps of the /add conversation."""

    name = "name"
    affiliate_url = "affiliate_url"
    price = "price"
    commission = "commission"
    category = "category"
    target_audience = "target_audience"
    description = "description"
    media = "media"


# Order of the conversation; media is handled as a special collection step.
ADD_STEPS: list[AddStep] = [
    AddStep.name,
    AddStep.affiliate_url,
    AddStep.price,
    AddStep.commission,
    AddStep.category,
    AddStep.target_audience,
    AddStep.description,
    AddStep.media,
]

# Steps the user may skip with /skip.
OPTIONAL_STEPS = {
    AddStep.affiliate_url,
    AddStep.price,
    AddStep.commission,
    AddStep.category,
    AddStep.target_audience,
    AddStep.description,
}


def _state_key(user_id: str) -> str:
    return f"{STATE_KEY_PREFIX}:{user_id}"


def _last_product_key(user_id: str) -> str:
    return f"{LAST_PRODUCT_PREFIX}:{user_id}"


@dataclass
class ConversationState:
    """In-progress /add conversation."""

    user_id: str
    step: AddStep
    data: dict[str, Any] = field(default_factory=dict)
    product_id: str | None = None
    images: int = 0
    videos: int = 0

    def to_json(self) -> str:
        return json.dumps(
            {
                "user_id": self.user_id,
                "step": self.step.value,
                "data": self.data,
                "product_id": self.product_id,
                "images": self.images,
                "videos": self.videos,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str) -> "ConversationState":
        payload = json.loads(raw)
        return cls(
            user_id=str(payload["user_id"]),
            step=AddStep(payload["step"]),
            data=payload.get("data") or {},
            product_id=payload.get("product_id"),
            images=int(payload.get("images") or 0),
            videos=int(payload.get("videos") or 0),
        )


class ConversationStore:
    """Persists conversation state in Redis."""

    def __init__(self, ttl: int | None = None) -> None:
        self._ttl = ttl if ttl is not None else settings.telegram_state_ttl_seconds

    async def get(self, user_id: str) -> ConversationState | None:
        raw = await get_redis().get(_state_key(user_id))
        if not raw:
            return None
        try:
            state = ConversationState.from_json(raw)
        except (ValueError, KeyError):
            logger.warning("Discarding corrupt telegram state for user %s", user_id)
            await self.clear(user_id)
            return None
        # Refresh the TTL on every interaction.
        await get_redis().expire(_state_key(user_id), self._ttl)
        return state

    async def save(self, state: ConversationState) -> None:
        await get_redis().set(_state_key(state.user_id), state.to_json(), ex=self._ttl)

    async def clear(self, user_id: str) -> None:
        await get_redis().delete(_state_key(user_id))

    async def set_last_product(self, user_id: str, product_id: str) -> None:
        await get_redis().set(_last_product_key(user_id), product_id, ex=self._ttl)

    async def get_last_product(self, user_id: str) -> str | None:
        value = await get_redis().get(_last_product_key(user_id))
        return str(value) if value else None
