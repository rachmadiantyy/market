from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import (
    AIContentType,
    AIPlatform,
    ContentStatus,
    ContentType,
    GenerationStatus,
    MediaType,
    ProductStatus,
)

PROMPT_MIN_LENGTH = 3
PROMPT_MAX_LENGTH = 2000
VARIATIONS_MIN = 1
VARIATIONS_MAX = 20


class ProductMediaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    media_type: MediaType
    file_path: str
    mime_type: str
    file_size: int
    source: str
    url: str
    created_at: datetime


class ProductBase(BaseModel):
    name: str
    description: str | None = None
    source_url: str | None = None
    affiliate_url: str | None = None
    image_url: str | None = None
    price: float | None = None
    currency: str = "IDR"
    commission: float | None = None
    category: str | None = None
    target_audience: str | None = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    source_url: str | None = None
    affiliate_url: str | None = None
    image_url: str | None = None
    price: float | None = None
    currency: str | None = None
    commission: float | None = None
    category: str | None = None
    target_audience: str | None = None
    status: ProductStatus | None = None


class ProductRead(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: ProductStatus
    media: list[ProductMediaRead] = []
    created_at: datetime
    updated_at: datetime


class ContentItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID | None
    content_type: ContentType
    status: ContentStatus
    title: str | None
    body: str | None
    media_url: str | None
    scheduled_at: datetime | None
    created_at: datetime


class ContentGenerateRequest(BaseModel):
    product_id: UUID
    content_type: ContentType = ContentType.text
    prompt: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    queue: str
    task: str
    status: str
    created_at: datetime


# --- AI generation ---


class AIGenerateRequest(BaseModel):
    prompt: str = Field(min_length=PROMPT_MIN_LENGTH, max_length=PROMPT_MAX_LENGTH)
    product_id: UUID | None = None
    content_type: AIContentType = AIContentType.caption
    platform: AIPlatform = AIPlatform.tiktok
    variations: int = Field(default=3, ge=VARIATIONS_MIN, le=VARIATIONS_MAX)

    @field_validator("prompt")
    @classmethod
    def _validate_prompt(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("prompt must not be empty")
        return cleaned


class AIResultVariation(BaseModel):
    """A single generated variation (validated provider output)."""

    index: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=5000)


class AIResultPayload(BaseModel):
    """Validated structure stored in AIGeneration.result."""

    variations: list[AIResultVariation] = Field(min_length=1, max_length=VARIATIONS_MAX)


class AIGenerationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID | None
    product_name: str | None = None
    type: AIContentType
    platform: AIPlatform
    variations: int
    prompt: str
    status: GenerationStatus
    result: AIResultPayload | None = None
    error_message: str | None = None
    model: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
