"""Shared fixtures for Telegram bot tests.

Uses a FakeTelegramClient (no network) plus the real PostgreSQL test database
and in-memory Redis from the root conftest.
"""

import pytest
import pytest_asyncio

from app.core.config import settings
from app.services.telegram.client import TelegramClient
from app.services.telegram.handlers import BotContext
from app.services.telegram.state import ConversationStore

ADMIN_USER_ID = "111111"
ADMIN_CHAT_ID = "111111"
OTHER_USER_ID = "999999"
OTHER_CHAT_ID = "999999"


class FakeTelegramClient(TelegramClient):
    """Records outgoing calls instead of hitting the Bot API."""

    def __init__(self, *, files: dict[str, bytes] | None = None) -> None:
        super().__init__(token="fake-token")
        self.messages: list[dict] = []
        self.callback_answers: list[dict] = []
        self.files = files or {}
        self.get_file_calls: list[str] = []
        self.download_calls: list[str] = []
        self.fail_get_file_for: set[str] = set()

    async def send_message(
        self, chat_id, text, *, reply_markup=None, parse_mode=None
    ) -> dict:
        record = {
            "chat_id": str(chat_id),
            "text": text,
            "reply_markup": reply_markup,
            "parse_mode": parse_mode,
        }
        self.messages.append(record)
        return {"message_id": len(self.messages)}

    async def answer_callback_query(self, callback_query_id, text=None) -> dict:
        self.callback_answers.append(
            {"callback_query_id": callback_query_id, "text": text}
        )
        return {"ok": True}

    async def get_file(self, file_id: str) -> dict:
        from app.services.telegram.client import TelegramError

        self.get_file_calls.append(file_id)
        if file_id in self.fail_get_file_for:
            raise TelegramError("Gagal mengunduh file (HTTP 400).")
        return {"file_id": file_id, "file_path": f"files/{file_id}"}

    async def download_file(self, file_path: str) -> bytes:
        from app.services.media_storage import MediaDownloadError

        self.download_calls.append(file_path)
        if file_path not in self.files:
            raise MediaDownloadError("File tidak ditemukan di Telegram.")
        return self.files[file_path]

    # --- assertions helpers ---

    def last_text(self) -> str:
        return self.messages[-1]["text"] if self.messages else ""

    def texts(self) -> list[str]:
        return [m["text"] for m in self.messages]

    def clear(self) -> None:
        self.messages.clear()
        self.callback_answers.clear()


@pytest.fixture
def bot_settings(monkeypatch):
    """Configure authorization and limits for tests."""
    monkeypatch.setattr(settings, "telegram_admin_user_id", ADMIN_USER_ID)
    monkeypatch.setattr(settings, "telegram_admin_chat_id", "")
    monkeypatch.setattr(settings, "telegram_bot_token", "fake-token")
    monkeypatch.setattr(settings, "telegram_state_ttl_seconds", 3600)
    return settings


@pytest_asyncio.fixture
async def bot_ctx(session_factory, fake_redis, bot_settings, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path / "uploads"))
    client = FakeTelegramClient()
    ctx = BotContext(
        client=client,
        session_factory=session_factory,
        store=ConversationStore(),
        settings=settings,
    )
    return ctx


def message_update(
    text: str | None = None,
    *,
    user_id: str = ADMIN_USER_ID,
    chat_id: str = ADMIN_CHAT_ID,
    photo: bool = False,
    video: bool = False,
    video_mime: str = "video/mp4",
    file_id: str = "file-1",
    file_size: int = 1024,
    file_name: str | None = "clip.mp4",
    update_id: int = 1,
) -> dict:
    message: dict = {
        "message_id": update_id,
        "chat": {"id": int(chat_id), "type": "private"},
        "from": {"id": int(user_id), "is_bot": False, "first_name": "Tester"},
    }
    if text is not None:
        message["text"] = text
    if photo:
        message["photo"] = [
            {"file_id": f"{file_id}-small", "file_size": 128, "width": 90, "height": 90},
            {"file_id": file_id, "file_size": file_size, "width": 1280, "height": 720},
        ]
    if video:
        message["video"] = {
            "file_id": file_id,
            "file_size": file_size,
            "mime_type": video_mime,
            "file_name": file_name,
        }
    return {"update_id": update_id, "message": message}


def callback_update(
    data: str,
    *,
    user_id: str = ADMIN_USER_ID,
    chat_id: str = ADMIN_CHAT_ID,
    callback_id: str = "cb-1",
    update_id: int = 1,
) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": callback_id,
            "from": {"id": int(user_id), "is_bot": False, "first_name": "Tester"},
            "message": {
                "message_id": 1,
                "chat": {"id": int(chat_id), "type": "private"},
            },
            "data": data,
        },
    }
