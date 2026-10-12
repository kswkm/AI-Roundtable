import json

import pytest

from helpers import load_fixture, mock_client
from roundtable.providers.anthropic import AnthropicProvider
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    ProviderError,
    ProviderResponse,
    RateLimited,
)

MESSAGES = [
    ChatMessage("system", "sys-1"),
    ChatMessage("system", "sys-2"),
    ChatMessage("user", "question"),
    ChatMessage("assistant", "draft"),
    ChatMessage("user", "fix it"),
]


def make(client):
    return AnthropicProvider("claude-haiku-4-5", "sk-ant-test", client)


async def test_success_joins_text_blocks_and_moves_system_out():
    captured = []
    payload = {
        "content": [{"type": "text", "text": '{"a":'}, {"type": "text", "text": " 1}"}],
        "usage": {"input_tokens": 20, "output_tokens": 4},
    }
    async with mock_client(200, payload, capture=captured) as client:
        response = await make(client).complete(MESSAGES, {"type": "object"})

    assert response == ProviderResponse('{"a": 1}', 20, 4)
    request = captured[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "sk-ant-test"
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body["system"] == "sys-1\n\nsys-2"
    assert body["max_tokens"] == 4096
    assert body["messages"] == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "draft"},
        {"role": "user", "content": "fix it"},
    ]


async def test_low_credit_balance_is_credits_exhausted():
    async with mock_client(400, load_fixture("anthropic_credit_balance.json")) as client:
        with pytest.raises(CreditsExhausted, match="credit balance is too low"):
            await make(client).complete(MESSAGES)


async def test_rate_limit_is_rate_limited():
    async with mock_client(429, load_fixture("anthropic_rate_limit.json"), headers={"retry-after": "20"}) as client:
        with pytest.raises(RateLimited) as info:
            await make(client).complete(MESSAGES)
    assert info.value.retry_after == 20.0


async def test_overloaded_is_provider_error():
    async with mock_client(529, load_fixture("anthropic_overloaded.json")) as client:
        with pytest.raises(ProviderError, match="HTTP 529"):
            await make(client).complete(MESSAGES)


async def test_malformed_success_is_provider_error():
    async with mock_client(200, {"unexpected": True}) as client:
        with pytest.raises(ProviderError, match="해석할 수 없음"):
            await make(client).complete(MESSAGES)


async def test_malformed_usage_is_provider_error():
    payload = {
        "content": [{"type": "text", "text": "hi"}],
        "usage": {"input_tokens": None, "output_tokens": 1},
    }
    async with mock_client(200, payload) as client:
        with pytest.raises(ProviderError, match="해석할 수 없음"):
            await make(client).complete(MESSAGES)
