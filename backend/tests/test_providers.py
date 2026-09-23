"""AI provider tests: factory selection, failure modes, output parsing."""

import httpx
import pytest
import respx

from app.core.config import settings
from app.providers.ai import (
    MockProvider,
    OpenAICompatibleProvider,
    get_ai_provider,
)
from app.providers.ai.base import AIProviderConfigError, AIProviderError
from app.services.generation import parse_provider_output


def test_mock_provider_selected():
    original = settings.ai_provider
    try:
        settings.ai_provider = "mock"
        provider = get_ai_provider()
        assert isinstance(provider, MockProvider)
    finally:
        settings.ai_provider = original


def test_openai_provider_selected():
    original = settings.ai_provider
    try:
        settings.ai_provider = "openai"
        provider = get_ai_provider()
        assert isinstance(provider, OpenAICompatibleProvider)
    finally:
        settings.ai_provider = original


def test_unsupported_provider_raises():
    original = settings.ai_provider
    try:
        settings.ai_provider = "does-not-exist"
        with pytest.raises(AIProviderConfigError):
            get_ai_provider()
    finally:
        settings.ai_provider = original


def test_openai_provider_requires_api_key():
    provider = OpenAICompatibleProvider(
        api_key="", model="gpt-test", base_url="https://example.test/v1", timeout=5
    )
    with pytest.raises(AIProviderConfigError):
        import asyncio

        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
            provider.generate(system_prompt="s", user_prompt="u")
        )


@respx.mock
async def test_openai_provider_returns_content():
    respx.post("https://example.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"variations": ["halo"]}'}}]},
        )
    )
    provider = OpenAICompatibleProvider(
        api_key="secret-key", model="gpt-test", base_url="https://example.test/v1", timeout=5
    )
    result = await provider.generate(system_prompt="s", user_prompt="u")
    assert "halo" in result


@respx.mock
async def test_openai_provider_http_error():
    respx.post("https://example.test/v1/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": "rate limited"})
    )
    provider = OpenAICompatibleProvider(
        api_key="secret-key", model="gpt-test", base_url="https://example.test/v1", timeout=5
    )
    with pytest.raises(AIProviderError) as exc:
        await provider.generate(system_prompt="s", user_prompt="u")
    assert "429" in str(exc.value)


@respx.mock
async def test_openai_provider_error_never_leaks_api_key():
    secret = "sk-super-secret-value"
    respx.post("https://example.test/v1/chat/completions").mock(
        return_value=httpx.Response(500, text=f"upstream rejected {secret}")
    )
    provider = OpenAICompatibleProvider(
        api_key=secret, model="gpt-test", base_url="https://example.test/v1", timeout=5
    )
    with pytest.raises(AIProviderError) as exc:
        await provider.generate(system_prompt="s", user_prompt="u")
    assert secret not in str(exc.value)
    assert "***" in str(exc.value)


@respx.mock
async def test_openai_provider_malformed_response():
    respx.post("https://example.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"unexpected": True})
    )
    provider = OpenAICompatibleProvider(
        api_key="k", model="gpt-test", base_url="https://example.test/v1", timeout=5
    )
    with pytest.raises(AIProviderError):
        await provider.generate(system_prompt="s", user_prompt="u")


@respx.mock
async def test_openai_provider_timeout():
    respx.post("https://example.test/v1/chat/completions").mock(
        side_effect=httpx.ConnectTimeout("timed out")
    )
    provider = OpenAICompatibleProvider(
        api_key="k", model="gpt-test", base_url="https://example.test/v1", timeout=5
    )
    with pytest.raises(AIProviderError):
        await provider.generate(system_prompt="s", user_prompt="u")


# --- output parsing / validation ---


def test_parse_plain_json_object():
    payload = parse_provider_output('{"variations": ["satu", "dua"]}', 2)
    assert [v.text for v in payload.variations] == ["satu", "dua"]


def test_parse_bare_json_array():
    payload = parse_provider_output('["satu", "dua"]', 2)
    assert len(payload.variations) == 2


def test_parse_fenced_json():
    payload = parse_provider_output('```json\n{"variations": ["satu"]}\n```', 1)
    assert payload.variations[0].text == "satu"


def test_parse_truncates_to_expected_count():
    payload = parse_provider_output('{"variations": ["a", "b", "c", "d"]}', 2)
    assert len(payload.variations) == 2


def test_parse_numbers_variations():
    payload = parse_provider_output('{"variations": ["a", "b"]}', 5)
    assert [v.index for v in payload.variations] == [1, 2]


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "not json at all",
        '{"variations": []}',
        '{"variations": "bukan list"}',
        '{"foo": "bar"}',
        "[]",
    ],
)
def test_parse_rejects_invalid_output(raw):
    from app.providers.ai.base import AIResponseError

    with pytest.raises(AIResponseError):
        parse_provider_output(raw, 3)
