"""Tests for the Telegram HTTP client and polling runtime."""

import asyncio
import json
import time
from pathlib import Path

import httpx
import pytest
import respx

from app.core.config import settings
from app.services.telegram.client import (
    TelegramAuthError,
    TelegramClient,
    TelegramError,
)
from app.services.telegram.handlers import BotContext, build_default_context
from app.services.telegram.runtime import run_polling, touch_heartbeat
from tests.telegram_helpers import FakeTelegramClient, message_update

TOKEN = "123456:SECRET-TOKEN-VALUE"
API = "https://api.telegram.org"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", TOKEN)
    monkeypatch.setattr(settings, "telegram_api_base", API)
    return settings


@respx.mock
async def test_get_me_returns_result(configured):
    respx.post(f"{API}/bot{TOKEN}/getMe").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"id": 1, "username": "bot"}})
    )
    client = TelegramClient()

    result = await client.get_me()

    assert result["username"] == "bot"


@respx.mock
async def test_send_message_payload(configured):
    route = respx.post(f"{API}/bot{TOKEN}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})
    )
    client = TelegramClient()

    await client.send_message("42", "halo", parse_mode="Markdown")

    body = json.loads(route.calls.last.request.content)
    assert body["chat_id"] == "42"
    assert body["text"] == "halo"
    assert body["parse_mode"] == "Markdown"


@respx.mock
async def test_get_updates_sends_offset(configured):
    route = respx.post(f"{API}/bot{TOKEN}/getUpdates").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": [{"update_id": 7}]})
    )
    client = TelegramClient()

    updates = await client.get_updates(offset=7)

    body = json.loads(route.calls.last.request.content)
    assert body["offset"] == 7
    assert "message" in body["allowed_updates"]
    assert updates == [{"update_id": 7}]


@respx.mock
async def test_get_file(configured):
    respx.post(f"{API}/bot{TOKEN}/getFile").mock(
        return_value=httpx.Response(
            200, json={"ok": True, "result": {"file_id": "f", "file_path": "photos/a.jpg"}}
        )
    )
    client = TelegramClient()

    result = await client.get_file("f")

    assert result["file_path"] == "photos/a.jpg"


@respx.mock
async def test_download_file(configured):
    respx.get(f"{API}/file/bot{TOKEN}/photos/a.jpg").mock(
        return_value=httpx.Response(200, content=b"binary-data")
    )
    client = TelegramClient()

    data = await client.download_file("photos/a.jpg")

    assert data == b"binary-data"


@respx.mock
async def test_auth_error_on_401(configured):
    respx.post(f"{API}/bot{TOKEN}/getMe").mock(
        return_value=httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
    )
    client = TelegramClient()

    with pytest.raises(TelegramAuthError):
        await client.get_me()


@respx.mock
async def test_error_never_leaks_token(configured):
    respx.post(f"{API}/bot{TOKEN}/getMe").mock(
        return_value=httpx.Response(
            400,
            json={"ok": False, "description": f"bad request for {TOKEN}"},
        )
    )
    client = TelegramClient()

    with pytest.raises(TelegramError) as exc:
        await client.get_me()

    assert TOKEN not in str(exc.value)
    assert "***" in str(exc.value)


@respx.mock
async def test_network_error_is_wrapped(configured):
    respx.post(f"{API}/bot{TOKEN}/getMe").mock(side_effect=httpx.ConnectError("down"))
    client = TelegramClient()

    with pytest.raises(TelegramError) as exc:
        await client.get_me()

    assert TOKEN not in str(exc.value)


async def test_unconfigured_token_raises(monkeypatch):
    monkeypatch.setattr(settings, "telegram_bot_token", "")
    client = TelegramClient(token="")

    with pytest.raises(TelegramError):
        await client.get_me()

    assert client.configured is False


def test_httpx_logging_is_silenced():
    """httpx would log the token-bearing Telegram URL at INFO level."""
    import logging

    from app.core.logging import configure_logging

    configure_logging()

    assert logging.getLogger("httpx").level >= logging.WARNING
    assert logging.getLogger("httpcore").level >= logging.WARNING


# --- runtime ---------------------------------------------------------------


def test_touch_heartbeat_writes_file(tmp_path):
    target = tmp_path / "hb" / "heartbeat"

    touch_heartbeat(str(target))

    assert target.exists()
    assert time.time() - target.stat().st_mtime < 5


class PollingFakeClient(FakeTelegramClient):
    def __init__(self, batches: list[list[dict]], *, fail_times: int = 0) -> None:
        super().__init__()
        self._batches = batches
        self._fail_times = fail_times
        self.offsets: list[int | None] = []
        self.get_me_calls = 0

    async def get_me(self) -> dict:
        self.get_me_calls += 1
        return {"id": 1, "username": "testbot"}

    async def get_updates(self, offset=None, timeout=None) -> list[dict]:
        self.offsets.append(offset)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise TelegramError("temporary failure")
        if self._batches:
            return self._batches.pop(0)
        return []


async def test_run_polling_dispatches_and_advances_offset(
    session_factory, fake_redis, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    monkeypatch.setattr(settings, "telegram_heartbeat_file", str(tmp_path / "hb"))
    monkeypatch.setattr(settings, "telegram_admin_user_id", "111111")
    client = PollingFakeClient([[message_update("/start", update_id=5)]])
    ctx = BotContext(
        client=client,
        session_factory=session_factory,
        store=build_default_context().store,
        settings=settings,
    )

    await run_polling(ctx, max_iterations=2)

    # First call has no offset; after processing update_id=5 the offset is 6.
    assert client.offsets[0] is None
    assert 6 in client.offsets
    assert any("Selamat datang" in m["text"] for m in client.messages)


async def test_run_polling_survives_errors(
    session_factory, fake_redis, monkeypatch, tmp_path
):
    monkeypatch.setattr(settings, "uploads_dir", str(tmp_path))
    monkeypatch.setattr(settings, "telegram_heartbeat_file", str(tmp_path / "hb"))
    monkeypatch.setattr(settings, "telegram_admin_user_id", "111111")
    client = PollingFakeClient([[message_update("/start", update_id=9)]], fail_times=1)
    ctx = BotContext(
        client=client,
        session_factory=session_factory,
        store=build_default_context().store,
        settings=settings,
    )

    # Should not raise even though the first getUpdates call fails.
    await asyncio.wait_for(run_polling(ctx, max_iterations=3), timeout=10)

    assert any("Selamat datang" in m["text"] for m in client.messages)
