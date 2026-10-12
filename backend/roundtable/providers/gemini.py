"""Google Gemini generateContent API. 무료 등급의 일일 한도는 태평양 시간 자정에 초기화된다."""

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from roundtable.clock import utcnow
from roundtable.providers._http import error_message, post_json
from roundtable.providers.base import (
    ChatMessage,
    DailyQuotaExhausted,
    ProviderError,
    ProviderFailure,
    ProviderResponse,
    RateLimited,
)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PACIFIC = ZoneInfo("America/Los_Angeles")


def next_pacific_midnight(now: datetime) -> datetime:
    local = now.replace(tzinfo=UTC).astimezone(PACIFIC)
    midnight = datetime.combine(local.date() + timedelta(days=1), time(0), tzinfo=PACIFIC)
    return midnight.astimezone(UTC).replace(tzinfo=None)


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        model: str,
        api_key: str,
        client: httpx.AsyncClient,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client
        self._now = now

    async def complete(
        self, messages: list[ChatMessage], response_schema: dict | None = None
    ) -> ProviderResponse:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        body: dict = {
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
                if m.role != "system"
            ]
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if response_schema is not None:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        response = await post_json(
            self._client,
            GEMINI_URL.format(model=self.model),
            {"x-goog-api-key": self._api_key},
            body,
        )
        if response.status_code != 200:
            raise self._classify(response)
        try:
            data = response.json()
            candidates = data.get("candidates") or []
            if not candidates:
                raise ProviderError("빈 응답 (안전 필터 등으로 차단되었을 수 있음)")
            parts = (candidates[0].get("content") or {}).get("parts") or []
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            usage = data.get("usageMetadata") or {}
            input_tokens = int(usage.get("promptTokenCount", 0))
            output_tokens = int(usage.get("candidatesTokenCount", 0)) + int(
                usage.get("thoughtsTokenCount", 0)
            )
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise ProviderError("응답 형식을 해석할 수 없음") from exc
        return ProviderResponse(text, input_tokens, output_tokens)

    def _classify(self, response: httpx.Response) -> ProviderFailure:
        message = error_message(response)
        if response.status_code != 429:
            return ProviderError(f"HTTP {response.status_code}: {message}")
        try:
            details = response.json().get("error", {}).get("details", [])
        except (ValueError, AttributeError):
            details = []
        quota_ids = [
            violation.get("quotaId", "")
            for detail in details
            for violation in detail.get("violations", [])
        ]
        if any("PerDay" in quota_id for quota_id in quota_ids):
            return DailyQuotaExhausted(message, next_pacific_midnight(self._now()))
        retry_after = None
        for detail in details:
            delay = detail.get("retryDelay")
            if isinstance(delay, str) and delay.endswith("s"):
                try:
                    retry_after = float(delay[:-1])
                except ValueError:
                    pass
        return RateLimited(message, retry_after)
