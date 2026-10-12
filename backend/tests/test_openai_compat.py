import json

import pytest

from helpers import load_fixture, mock_client
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    ProviderError,
    ProviderResponse,
    RateLimited,
)
from roundtable.providers.openai_compat import OpenAICompatProvider

MESSAGES = [ChatMessage("system", "sys"), ChatMessage("user", "hi, answer in JSON")]


def make(client):
    return OpenAICompatProvider("openai", "gpt-4o-mini", "sk-test", "https://api.openai.com/v1", client)


async def test_success_returns_text_and_usage():
    captured = []
    payload = {
        "choices": [{"message": {"content": '{"a": 1}'}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }
    async with mock_client(200, payload, capture=captured) as client:
        response = await make(client).complete(MESSAGES, {"type": "object"})

    assert response == ProviderResponse('{"a": 1}', 12, 3)
    request = captured[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "gpt-4o-mini"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi, answer in JSON"},
    ]


async def test_no_schema_means_no_json_mode():
    captured = []
    payload = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    async with mock_client(200, payload, capture=captured) as client:
        response = await make(client).complete(MESSAGES)
    assert "response_format" not in json.loads(captured[0].content)
    assert response == ProviderResponse("ok", 0, 0)


async def test_insufficient_quota_is_credits_exhausted():
    async with mock_client(429, load_fixture("openai_insufficient_quota.json")) as client:
        with pytest.raises(CreditsExhausted, match="exceeded your current quota"):
            await make(client).complete(MESSAGES)


async def test_rate_limit_is_rate_limited_with_retry_after():
    async with mock_client(429, load_fixture("openai_rate_limit.json"), headers={"retry-after": "7"}) as client:
        with pytest.raises(RateLimited) as info:
            await make(client).complete(MESSAGES)
    assert info.value.retry_after == 7.0


async def test_openrouter_402_is_credits_exhausted():
    async with mock_client(402, load_fixture("openrouter_402.json")) as client:
        with pytest.raises(CreditsExhausted):
            await make(client).complete(MESSAGES)


async def test_xai_no_credits_is_credits_exhausted():
    async with mock_client(429, load_fixture("xai_no_credits.json")) as client:
        with pytest.raises(CreditsExhausted, match="used all available credits"):
            await make(client).complete(MESSAGES)


async def test_server_error_is_provider_error():
    async with mock_client(500, text="Internal Server Error") as client:
        with pytest.raises(ProviderError, match="HTTP 500"):
            await make(client).complete(MESSAGES)


async def test_malformed_success_is_provider_error():
    async with mock_client(200, {"choices": []}) as client:
        with pytest.raises(ProviderError, match="해석할 수 없음"):
            await make(client).complete(MESSAGES)


async def test_malformed_usage_is_provider_error():
    for usage in ({"prompt_tokens": None, "completion_tokens": 3}, {"prompt_tokens": 1, "completion_tokens": "many"}):
        payload = {"choices": [{"message": {"content": "ok"}}], "usage": usage}
        async with mock_client(200, payload) as client:
            with pytest.raises(ProviderError, match="해석할 수 없음"):
                await make(client).complete(MESSAGES)
