import httpx
import pytest

from roundtable.providers._http import error_message, post_json, retry_after_seconds
from roundtable.providers.base import DailyQuotaExhausted, ProviderError, RateLimited


def client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_post_json_wraps_network_error():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    async with client_with(handler) as client:
        with pytest.raises(ProviderError, match="네트워크 오류"):
            await post_json(client, "https://example.test/x", {}, {})


async def test_post_json_wraps_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    async with client_with(handler) as client:
        with pytest.raises(ProviderError, match="시간 초과"):
            await post_json(client, "https://example.test/x", {}, {})


async def test_post_json_sends_json_body_and_headers():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    async with client_with(handler) as client:
        response = await post_json(client, "https://example.test/x", {"X-Key": "k"}, {"a": 1})

    assert response.status_code == 200
    assert seen[0].headers["x-key"] == "k"
    assert seen[0].content == b'{"a":1}' or seen[0].content == b'{"a": 1}'


def test_error_message_reads_nested_error():
    assert error_message(httpx.Response(429, json={"error": {"message": "slow down"}})) == "slow down"


def test_error_message_reads_string_error():
    assert error_message(httpx.Response(400, json={"error": "bad"})) == "bad"


def test_error_message_falls_back_to_text():
    assert error_message(httpx.Response(500, text="Internal Server Error")) == "Internal Server Error"


def test_retry_after_seconds():
    assert retry_after_seconds(httpx.Response(429, headers={"retry-after": "12"})) == 12.0
    assert retry_after_seconds(httpx.Response(429)) is None
    assert retry_after_seconds(httpx.Response(429, headers={"retry-after": "soon"})) is None


def test_failures_keep_their_details():
    assert RateLimited("m", 3.0).retry_after == 3.0
    assert RateLimited("m").message == "m"
    assert DailyQuotaExhausted("d").reset_at is None
