import asyncio
import json

from app.providers.ai.base import AIProvider, AIProviderConfigError

# Returned by the provider so a fresh clone can run the whole pipeline
# end-to-end before real credentials are configured.
_MOCK_DELAY_SECONDS = 0.4


class MockProvider(AIProvider):
    """Deterministic local provider used for development and tests.

    It echoes back the number of variations requested by the prompt builder,
    producing a JSON array so the pipeline can be exercised without network
    access.
    """

    name = "mock"

    def __init__(self, *, model: str = "mock-model", simulate_failure: bool = False) -> None:
        self.model = model
        self._simulate_failure = simulate_failure

    async def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        if self._simulate_failure:
            raise AIProviderConfigError("mock provider configured to fail")

        await asyncio.sleep(_MOCK_DELAY_SECONDS)

        count = 1
        for line in user_prompt.splitlines():
            if line.strip().lower().startswith("jumlah variasi:"):
                try:
                    count = int(line.split(":", 1)[1].strip())
                except ValueError:
                    count = 1
                break
        count = max(1, min(count, 20))

        variations = [
            f"[MOCK variasi {i}] Ringkasan hasil generasi untuk pengujian pipeline."
            for i in range(1, count + 1)
        ]
        return json.dumps({"variations": variations}, ensure_ascii=False)
