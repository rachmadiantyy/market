from app.core.config import settings
from app.providers.ai.base import AIProvider, AIProviderConfigError
from app.providers.ai.mock import MockProvider
from app.providers.ai.openai_compatible import OpenAICompatibleProvider

# Providers that speak the OpenAI /chat/completions protocol.
_OPENAI_COMPATIBLE = {
    "openai",
    "openai_compatible",
    "deepseek",
    "groq",
    "openrouter",
    "together",
    "ollama",
    "lmstudio",
    "custom",
}

_DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "together": "https://api.together.xyz/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
}


def get_ai_provider() -> AIProvider:
    """Build the provider selected by the AI_PROVIDER environment variable."""
    provider_name = (settings.ai_provider or "openai").strip().lower()
    model = settings.resolved_ai_model

    if provider_name == "mock":
        return MockProvider(model=model or "mock-model")

    if provider_name in _OPENAI_COMPATIBLE:
        base_url = settings.ai_base_url or _DEFAULT_BASE_URLS.get(provider_name)
        if not base_url:
            raise AIProviderConfigError(
                f"AI_BASE_URL is required for provider '{provider_name}'"
            )
        return OpenAICompatibleProvider(
            api_key=settings.ai_api_key,
            model=model,
            base_url=base_url,
            timeout=settings.ai_timeout_seconds,
        )

    raise AIProviderConfigError(f"Unsupported AI_PROVIDER: {provider_name}")
