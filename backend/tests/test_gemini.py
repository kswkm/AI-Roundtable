import json
from datetime import datetime

import pytest

from helpers import load_fixture, mock_client
from roundtable.providers.base import (
    ChatMessage,
    DailyQuotaExhausted,
    ProviderError,
    ProviderResponse,
    RateLimited,
)
from roundtable.providers.gemini import GeminiProvider, next_pacific_midnight

MESSAGES = [
    ChatMessage("system", "sys"),
    ChatMessage("user", "question"),
    ChatMessage("assistant", "draft"),
    ChatMessage("user", "fix it"),
]
NOW = datetime(2026, 10, 12, 20, 0)  # naive UTC = 태평양 시간 10월 12일 13:00 (PDT)


def make(client):
    return GeminiProvider("gemini-2.5-flash", "g-test", client, now=lambda: NOW)


async def test_success_maps_roles_and_skips_thought_parts():
    captured = []
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": '{"a": 1}'}]}}
        ],
        "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 6, "thoughtsTokenCount": 4},
    }
    async with mock_client(200, payload, capture=captured) as client:
        response = await make(client).complete(MESSAGES, {"type": "object"})

    assert response == ProviderResponse('{"a": 1}', 30, 10)
    request = captured[0]
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert request.headers["x-goog-api-key"] == "g-test"
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["generationConfig"] == {"responseMimeType": "application/json"}


async def test_daily_quota_is_daily_quota_exhausted_until_pacific_midnight():
    async with mock_client(429, load_fixture("gemini_daily_quota.json")) as client:
        with pytest.raises(DailyQuotaExhausted) as info:
            await make(client).complete(MESSAGES)
    assert info.value.reset_at == datetime(2026, 10, 13, 7, 0)


async def test_minute_quota_is_rate_limited_with_retry_delay():
    async with mock_client(429, load_fixture("gemini_minute_quota.json")) as client:
        with pytest.raises(RateLimited) as info:
            await make(client).complete(MESSAGES)
    assert info.value.retry_after == 17.0


async def test_empty_candidates_is_provider_error():
    payload = {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 5}}
    async with mock_client(200, payload) as client:
        with pytest.raises(ProviderError, match="빈 응답"):
            await make(client).complete(MESSAGES)


async def test_server_error_is_provider_error():
    async with mock_client(503, {"error": {"code": 503, "message": "The model is overloaded."}}) as client:
        with pytest.raises(ProviderError, match="HTTP 503"):
            await make(client).complete(MESSAGES)


def test_next_pacific_midnight_handles_standard_time():
    # 2026-12-01 10:00 UTC = 태평양 시간 02:00 (PST, UTC-8) → 다음 자정은 12-02 08:00 UTC
    assert next_pacific_midnight(datetime(2026, 12, 1, 10, 0)) == datetime(2026, 12, 2, 8, 0)


async def test_malformed_usage_is_provider_error():
    for usage in ({"promptTokenCount": None, "candidatesTokenCount": 3}, {"promptTokenCount": 1, "candidatesTokenCount": "many"}):
        payload = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}], "usageMetadata": usage}
        async with mock_client(200, payload) as client:
            with pytest.raises(ProviderError, match="해석할 수 없음"):
                await make(client).complete(MESSAGES)
