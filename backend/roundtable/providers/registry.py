import httpx

from roundtable.providers.anthropic import AnthropicProvider
from roundtable.providers.base import Provider
from roundtable.providers.gemini import GeminiProvider
from roundtable.providers.openai_compat import OpenAICompatProvider

OPENAI_COMPAT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
}
PROVIDER_IDS: tuple[str, ...] = (*OPENAI_COMPAT_BASE_URLS, "anthropic", "gemini")


def build_provider(provider: str, model: str, api_key: str, client: httpx.AsyncClient) -> Provider:
    if provider in OPENAI_COMPAT_BASE_URLS:
        return OpenAICompatProvider(
            provider, model, api_key, OPENAI_COMPAT_BASE_URLS[provider], client
        )
    if provider == "anthropic":
        return AnthropicProvider(model, api_key, client)
    if provider == "gemini":
        return GeminiProvider(model, api_key, client)
    raise ValueError(f"알 수 없는 제공 회사: {provider}")
