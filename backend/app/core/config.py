from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "affiliate-ai"
    app_env: Literal["development", "staging", "production"] = "development"
    timezone: str = "Asia/Jakarta"

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    secret_key: str = Field(default="change-me", min_length=1)
    cors_origins: str = "http://localhost:3000"

    database_url: str = "postgresql+asyncpg://affiliate:affiliate@postgres:5432/affiliate"
    redis_url: str = "redis://redis:6379/0"

    ai_provider: str = "openai"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_timeout_seconds: int = 60
    ai_max_retries: int = 3
    ai_text_model: str = ""
    ai_image_model: str = ""

    telegram_bot_token: str = ""
    telegram_admin_chat_id: str = ""
    telegram_admin_user_id: str = ""
    telegram_poll_timeout: int = 30
    telegram_heartbeat_file: str = "/tmp/telegram_bot_heartbeat"
    telegram_state_ttl_seconds: int = 3600
    telegram_api_base: str = "https://api.telegram.org"
    frontend_base_url: str = "http://localhost:3000"

    uploads_dir: str = "uploads"
    media_url_prefix: str = "/media"
    media_max_file_size_mb: int = 20
    media_allowed_image_types: str = "image/jpeg,image/png,image/webp,image/gif"
    media_allowed_video_types: str = "video/mp4,video/quicktime,video/webm"

    @field_validator("database_url")
    @classmethod
    def _force_async_driver(cls, value: str) -> str:
        """Accept bare postgresql:// URLs by switching to the asyncpg driver."""
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+asyncpg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+asyncpg://", 1)
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def resolved_ai_model(self) -> str:
        """AI_MODEL wins; fall back to the legacy AI_TEXT_MODEL for compatibility."""
        return self.ai_model or self.ai_text_model

    @property
    def media_max_file_size_bytes(self) -> int:
        return max(1, self.media_max_file_size_mb) * 1024 * 1024

    @property
    def allowed_image_types(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.media_allowed_image_types.split(",")
            if item.strip()
        }

    @property
    def allowed_video_types(self) -> set[str]:
        return {
            item.strip().lower()
            for item in self.media_allowed_video_types.split(",")
            if item.strip()
        }

    @property
    def telegram_admin_user_ids(self) -> set[str]:
        return {
            item.strip()
            for item in self.telegram_admin_user_id.split(",")
            if item.strip()
        }

    @property
    def telegram_admin_chat_ids(self) -> set[str]:
        return {
            item.strip()
            for item in self.telegram_admin_chat_id.split(",")
            if item.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
