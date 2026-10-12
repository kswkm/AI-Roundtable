"""OpenAI Chat Completions 호환 API (OpenAI, xAI, OpenRouter, Groq)."""

import httpx

from roundtable.providers._http import error_message, post_json, retry_after_seconds
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    ProviderError,
    ProviderFailure,
    ProviderResponse,
    RateLimited,
)

CREDIT_KEYWORDS = (
    "insufficient_quota",
    "exceeded your current quota",
    "insufficient credits",
    "available credits",
    "spending limit",
    "billing",
)


class OpenAICompatProvider:
    def __init__(
        self, name: str, model: str, api_key: str, base_url: str, client: httpx.AsyncClient
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    async def complete(
        self, messages: list[ChatMessage], response_schema: dict | None = None
    ) -> ProviderResponse:
        body: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if response_schema is not None:
            body["response_format"] = {"type": "json_object"}
        response = await post_json(
            self._client,
            f"{self.base_url}/chat/completions",
            {"Authorization": f"Bearer {self._api_key}"},
            body,
        )
        if response.status_code != 200:
            raise classify_openai_error(response)
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens", 0))
            output_tokens = int(usage.get("completion_tokens", 0))
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("응답 형식을 해석할 수 없음") from exc
        return ProviderResponse(text, input_tokens, output_tokens)


def classify_openai_error(response: httpx.Response) -> ProviderFailure:
    status = response.status_code
    message = error_message(response)
    lowered = f"{message} {response.text}".lower()
    if status == 402:
        return CreditsExhausted(message)
    if status in (400, 403, 429) and any(keyword in lowered for keyword in CREDIT_KEYWORDS):
        return CreditsExhausted(message)
    if status == 429:
        return RateLimited(message, retry_after_seconds(response))
    return ProviderError(f"HTTP {status}: {message}")
