import httpx
import pytest

from roundtable.providers.anthropic import AnthropicProvider
from roundtable.providers.gemini import GeminiProvider
from roundtable.providers.openai_compat import OpenAICompatProvider
from roundtable.providers.registry import PROVIDER_IDS, build_provider


async def test_build_provider_for_each_id():
    async with httpx.AsyncClient() as client:
        xai = build_provider("xai", "grok-3-mini", "k", client)
        assert isinstance(xai, OpenAICompatProvider)
        assert xai.base_url == "https://api.x.ai/v1"
        assert xai.name == "xai"
        assert build_provider("groq", "m", "k", client).base_url == "https://api.groq.com/openai/v1"
        assert isinstance(build_provider("anthropic", "m", "k", client), AnthropicProvider)
        assert isinstance(build_provider("gemini", "m", "k", client), GeminiProvider)


async def test_unknown_provider_raises():
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="알 수 없는 제공 회사"):
            build_provider("nope", "m", "k", client)


def test_provider_ids():
    assert PROVIDER_IDS == ("openai", "xai", "openrouter", "groq", "anthropic", "gemini")
