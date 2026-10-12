"""슬롯 하나를 호출한다. 슬롯 상태 확인, 재시도, 사용량 기록, JSON 파싱을 맡는다."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from roundtable.debate.prompts import json_instruction
from roundtable.debate.schemas import parse_json_model
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    DailyQuotaExhausted,
    Provider,
    ProviderError,
    RateLimited,
)
from roundtable.slots.service import SlotService
from roundtable.storage.models import Slot
from roundtable.usage.recorder import UsageRecorder

MAX_ERROR_ATTEMPTS = 3
MAX_RATE_LIMIT_WAITS = 6
BACKOFF_BASE_SECONDS = 1.0
JSON_MODE = {"type": "object"}

ProviderFactory = Callable[[Slot, str], Provider]
Sleep = Callable[[float], Awaitable[None]]
T = TypeVar("T", bound=BaseModel)


class SlotUnavailable(Exception):
    def __init__(self, slot_id: int, reason: str) -> None:
        super().__init__(reason)
        self.slot_id = slot_id
        self.reason = reason


@dataclass(frozen=True)
class CallResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class SlotCaller:
    def __init__(
        self,
        slots: SlotService,
        usage: UsageRecorder,
        provider_factory: ProviderFactory,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._slots = slots
        self._usage = usage
        self._factory = provider_factory
        self._sleep = sleep

    async def call(
        self, slot_id: int, messages: list[ChatMessage], *, debate_id: int | None
    ) -> CallResult:
        slot = self._slots.get(slot_id)
        if slot.status == "exhausted":
            raise SlotUnavailable(slot_id, slot.status_reason or "무료 제공량 소진")
        api_key = self._slots.api_key(slot)
        if api_key is None:
            raise SlotUnavailable(slot_id, f"{slot.api_key_env} 환경변수가 없음")
        provider = self._factory(slot, api_key)
        errors = waits = 0
        started = time.monotonic()
        while True:
            try:
                response = await provider.complete(messages, JSON_MODE)
            except RateLimited as failure:
                self._log(slot, debate_id, "rate_limited")
                self._slots.mark_failure(slot_id, failure)
                waits += 1
                if waits > MAX_RATE_LIMIT_WAITS:
                    raise ProviderError(f"속도 제한이 계속됨: {failure.message}") from failure
                await self._sleep(failure.retry_after or BACKOFF_BASE_SECONDS * 2 ** (waits - 1))
                continue
            except DailyQuotaExhausted as failure:
                self._log(slot, debate_id, "quota")
                self._slots.mark_failure(slot_id, failure)
                raise
            except CreditsExhausted as failure:
                self._log(slot, debate_id, "credits")
                self._slots.mark_failure(slot_id, failure)
                raise
            except ProviderError:
                self._log(slot, debate_id, "error")
                errors += 1
                if errors >= MAX_ERROR_ATTEMPTS:
                    raise
                await self._sleep(BACKOFF_BASE_SECONDS * 2 ** (errors - 1))
                continue
            self._log(slot, debate_id, "ok", response.input_tokens, response.output_tokens)
            self._slots.mark_ok(slot_id)
            return CallResult(
                text=response.text,
                provider=slot.provider,
                model=slot.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=int((time.monotonic() - started) * 1000),
            )

    async def call_json(
        self,
        slot_id: int,
        messages: list[ChatMessage],
        model_cls: type[T],
        *,
        debate_id: int | None,
    ) -> tuple[T, CallResult]:
        first = await self.call(slot_id, messages, debate_id=debate_id)
        try:
            return parse_json_model(first.text, model_cls), first
        except ValueError:
            pass
        retry_messages = [
            *messages,
            ChatMessage("assistant", first.text),
            ChatMessage("user", "직전 응답이 요구한 형식이 아닙니다. " + json_instruction(model_cls)),
        ]
        second = await self.call(slot_id, retry_messages, debate_id=debate_id)
        combined = CallResult(
            text=second.text,
            provider=second.provider,
            model=second.model,
            input_tokens=first.input_tokens + second.input_tokens,
            output_tokens=first.output_tokens + second.output_tokens,
            latency_ms=first.latency_ms + second.latency_ms,
        )
        try:
            return parse_json_model(second.text, model_cls), combined
        except ValueError as exc:
            raise ProviderError(f"응답 형식 위반 (재요청 후에도): {exc}") from exc

    def _log(
        self,
        slot: Slot,
        debate_id: int | None,
        outcome: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        self._usage.record(
            provider=slot.provider, model=slot.model, debate_id=debate_id,
            input_tokens=input_tokens, output_tokens=output_tokens, outcome=outcome,
        )
