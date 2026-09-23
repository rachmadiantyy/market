import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.providers.ai.base import AIProvider, AIProviderConfigError, AIProviderError

logger = get_logger(__name__)

MAX_ERROR_DETAIL = 300


def redact(value: str, secrets: tuple[str, ...] = ()) -> str:
    """Remove credential material from a string before logging/raising."""
    redacted = value
    candidates = set(secrets)
    if settings.ai_api_key:
        candidates.add(settings.ai_api_key)
    for secret in candidates:
        if secret:
            redacted = redacted.replace(secret, "***")
    return redacted


def _safe_detail(response: httpx.Response, secrets: tuple[str, ...]) -> str:
    try:
        text = response.text
    except Exception:  # noqa: BLE001
        return ""
    return redact(text, secrets)[:MAX_ERROR_DETAIL]


class OpenAICompatibleProvider(AIProvider):
    """Provider for any OpenAI-compatible /chat/completions endpoint."""

    name = "openai_compatible"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str,
        timeout: int,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _ensure_configured(self) -> None:
        if not self._api_key:
            raise AIProviderConfigError("AI_API_KEY is not configured")
        if not self.model:
            raise AIProviderConfigError("AI_MODEL is not configured")

    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self._ensure_configured()

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.9,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self._base_url}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(url, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise AIProviderError("AI provider request timed out") from exc
        except httpx.HTTPError as exc:
            raise AIProviderError(f"AI provider connection error: {type(exc).__name__}") from exc

        if response.status_code >= 400:
            detail = _safe_detail(response, (self._api_key,))
            logger.warning("AI provider returned %s: %s", response.status_code, detail)
            raise AIProviderError(
                f"AI provider returned HTTP {response.status_code}: {detail}"
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("AI provider returned an unexpected response shape") from exc

        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("AI provider returned an empty completion")

        return content
