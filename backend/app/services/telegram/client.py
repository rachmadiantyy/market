"""Telegram Bot API client.

The bot token is read from settings at call time and never logged. Error
payloads coming back from Telegram are passed through `redact()` so a token can
never leak into logs, database rows, or user-visible messages.
"""

from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.ai.openai_compatible import redact

logger = get_logger(__name__)


class TelegramError(Exception):
    """A Telegram API call failed. Message is safe to show/log."""


class TelegramAuthError(TelegramError):
    """The bot token was rejected (401/404)."""


def _redact(text: str) -> str:
    token = settings.telegram_bot_token
    return redact(text, (token,) if token else ())


@dataclass
class TelegramUpdate:
    update_id: int
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class TelegramMessage:
    chat_id: str
    user_id: str
    text: str | None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def chat_type(self) -> str:
        return str(self.raw.get("chat", {}).get("type", "private"))

    def photo(self) -> dict[str, Any] | None:
        photos = self.raw.get("photo")
        if isinstance(photos, list) and photos:
            # Telegram sends ascending sizes; the last is the largest.
            largest = max(photos, key=lambda p: p.get("file_size") or 0)
            return largest
        return None

    def video(self) -> dict[str, Any] | None:
        video = self.raw.get("video")
        return video if isinstance(video, dict) else None

    def document(self) -> dict[str, Any] | None:
        document = self.raw.get("document")
        return document if isinstance(document, dict) else None


class TelegramClient:
    def __init__(self, token: str | None = None, *, timeout: int = 60) -> None:
        self._token = token if token is not None else settings.telegram_bot_token
        self._timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _url(self, method: str) -> str:
        base = settings.telegram_api_base.rstrip("/")
        # Built per-call; never stored on the instance or logged.
        return f"{base}/bot{self._token}/{method}"

    def file_url(self, file_path: str) -> str:
        base = settings.telegram_api_base.rstrip("/")
        return f"{base}/file/bot{self._token}/{file_path.lstrip('/')}"

    async def _call(
        self, method: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not self._token:
            raise TelegramError("TELEGRAM_BOT_TOKEN belum dikonfigurasi.")

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self._url(method), json=payload or {})
        except httpx.HTTPError as exc:
            raise TelegramError(
                f"Koneksi ke Telegram gagal: {type(exc).__name__}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramError("Respons Telegram bukan JSON yang valid.") from exc

        if not data.get("ok"):
            description = _redact(str(data.get("description") or "unknown error"))
            if response.status_code in (401, 404):
                raise TelegramAuthError(
                    f"Bot token ditolak oleh Telegram: {description}"
                )
            raise TelegramError(
                f"Telegram error ({response.status_code}): {description}"
            )

        return data.get("result") or {}

    async def get_me(self) -> dict[str, Any]:
        return await self._call("getMe")

    async def send_message(
        self,
        chat_id: str | int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"chat_id": str(chat_id), "text": text}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        return await self._call("sendMessage", payload)

    async def answer_callback_query(
        self, callback_query_id: str, text: str | None = None
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        return await self._call("answerCallbackQuery", payload)

    async def get_updates(
        self, offset: int | None = None, timeout: int | None = None
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": timeout if timeout is not None else settings.telegram_poll_timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            payload["offset"] = offset
        result = await self._call("getUpdates", payload)
        return result if isinstance(result, list) else []

    async def get_file(self, file_id: str) -> dict[str, Any]:
        return await self._call("getFile", {"file_id": file_id})

    async def download_file(self, file_path: str) -> bytes:
        """Download a file from the Bot API file endpoint.

        Size enforcement happens in media_storage; this only streams bytes.
        """
        if not self._token:
            raise TelegramError("TELEGRAM_BOT_TOKEN belum dikonfigurasi.")

        url = self.file_url(file_path)
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise TelegramError(
                f"Gagal mengunduh file: {type(exc).__name__}"
            ) from exc

        if response.status_code >= 400:
            raise TelegramError(
                f"Gagal mengunduh file (HTTP {response.status_code})."
            )
        return response.content
