from abc import ABC, abstractmethod


class AIProviderError(Exception):
    """Raised when a provider call fails (network, auth, rate limit, ...)."""


class AIProviderConfigError(AIProviderError):
    """Raised when the provider is misconfigured (e.g. missing API key)."""


class AIResponseError(Exception):
    """Raised when a provider response cannot be validated."""


class AIProvider(ABC):
    """Abstraction over an AI text-generation backend.

    Implementations must never expose credentials in raised errors.
    """

    name: str = "base"
    model: str = ""

    @abstractmethod
    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        """Return the raw text completion for the given prompts."""
        raise NotImplementedError
