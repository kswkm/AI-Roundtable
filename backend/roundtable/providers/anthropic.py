"""Anthropic Messages API (Claude). JSON 모드가 없으므로 JSON 형식은 프롬프트로만 요청한다."""

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

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self, model: str, api_key: str, client: httpx.AsyncClient, max_tokens: int = 4096
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client
        self._max_tokens = max_tokens

    async def complete(
        self, messages: list[ChatMessage], response_schema: dict | None = None
    ) -> ProviderResponse:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        body: dict = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages if m.role != "system"
            ],
        }
        if system:
            body["system"] = system
        response = await post_json(
            self._client,
            ANTHROPIC_URL,
            {"x-api-key": self._api_key, "anthropic-version": ANTHROPIC_VERSION},
            body,
        )
        if response.status_code != 200:
            raise classify_anthropic_error(response)
        try:
            data = response.json()
            text = "".join(
                block.get("text", "") for block in data["content"] if block.get("type") == "text"
            )
            usage = data.get("usage") or {}
            input_tokens = int(usage.get("input_tokens", 0))
            output_tokens = int(usage.get("output_tokens", 0))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderError("응답 형식을 해석할 수 없음") from exc
        return ProviderResponse(text, input_tokens, output_tokens)


def classify_anthropic_error(response: httpx.Response) -> ProviderFailure:
    status = response.status_code
    message = error_message(response)
    lowered = message.lower()
    if "credit balance" in lowered or "billing" in lowered:
        return CreditsExhausted(message)
    if status == 429:
        return RateLimited(message, retry_after_seconds(response))
    return ProviderError(f"HTTP {status}: {message}")
