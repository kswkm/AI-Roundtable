import pytest

from fakes import ScriptedProvider, op_json
from roundtable.debate.caller import CallResult, SlotCaller, SlotUnavailable
from roundtable.debate.schemas import Opinion
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    DailyQuotaExhausted,
    ProviderError,
    RateLimited,
)
from roundtable.slots.service import SlotService
from roundtable.storage.db import init_db, make_engine
from roundtable.usage.recorder import UsageRecorder

MESSAGES = [ChatMessage("user", "q")]


class Setup:
    def __init__(self, tmp_path, script, environ=None):
        engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
        init_db(engine)
        self.slots = SlotService(engine, environ=environ if environ is not None else {"OPENAI_API_KEY": "k"})
        self.slots.seed_defaults()
        self.usage = UsageRecorder(engine)
        self.fake = ScriptedProvider(script)
        self.sleeps: list[float] = []
        self.keys: list[str] = []

        async def sleep(seconds):
            self.sleeps.append(seconds)

        def factory(slot, api_key):
            self.keys.append(api_key)
            return self.fake

        self.caller = SlotCaller(self.slots, self.usage, factory, sleep=sleep)

    def outcomes(self):
        return self.usage.summary("openai", "gpt-4o-mini")


async def test_success_records_usage_and_returns_result(tmp_path):
    s = Setup(tmp_path, ["hello"])
    result = await s.caller.call(1, MESSAGES, debate_id=7)
    assert isinstance(result, CallResult)
    assert (result.text, result.provider, result.model) == ("hello", "openai", "gpt-4o-mini")
    assert (result.input_tokens, result.output_tokens) == (10, 5)
    assert s.keys == ["k"]
    assert s.outcomes()["total_requests"] == 1


async def test_rate_limit_waits_then_retries(tmp_path):
    s = Setup(tmp_path, [RateLimited("slow", 5), RateLimited("slow"), "ok"])
    result = await s.caller.call(1, MESSAGES, debate_id=None)
    assert result.text == "ok"
    assert s.sleeps == [5, 2.0]  # 두 번째는 retry_after가 없으므로 1 * 2**1
    assert s.slots.get(1).status == "available"  # 성공하면 속도 제한 해제


async def test_rate_limit_that_never_ends_becomes_provider_error(tmp_path):
    s = Setup(tmp_path, [RateLimited("slow", 1)] * 7)
    with pytest.raises(ProviderError, match="속도 제한이 계속됨"):
        await s.caller.call(1, MESSAGES, debate_id=None)
    assert len(s.sleeps) == 6


async def test_provider_error_retries_three_times(tmp_path):
    s = Setup(tmp_path, [ProviderError("500")] * 3)
    with pytest.raises(ProviderError, match="500"):
        await s.caller.call(1, MESSAGES, debate_id=None)
    assert s.sleeps == [1.0, 2.0]
    assert len(s.fake.calls) == 3


async def test_provider_error_then_success(tmp_path):
    s = Setup(tmp_path, [ProviderError("500"), "ok"])
    assert (await s.caller.call(1, MESSAGES, debate_id=None)).text == "ok"


async def test_credits_exhausted_marks_slot_and_raises(tmp_path):
    s = Setup(tmp_path, [CreditsExhausted("no credits")])
    with pytest.raises(CreditsExhausted):
        await s.caller.call(1, MESSAGES, debate_id=None)
    slot = s.slots.get(1)
    assert (slot.status, slot.status_reason) == ("exhausted", "no credits")
    assert s.sleeps == []


async def test_daily_quota_marks_slot_and_raises(tmp_path):
    s = Setup(tmp_path, [DailyQuotaExhausted("day")])
    with pytest.raises(DailyQuotaExhausted):
        await s.caller.call(1, MESSAGES, debate_id=None)
    assert s.slots.get(1).status == "exhausted"


async def test_exhausted_slot_is_unavailable_without_calling(tmp_path):
    s = Setup(tmp_path, ["unused"])
    s.slots.mark_failure(1, CreditsExhausted("no credits"))
    with pytest.raises(SlotUnavailable) as info:
        await s.caller.call(1, MESSAGES, debate_id=None)
    assert info.value.slot_id == 1
    assert info.value.reason == "no credits"
    assert s.fake.calls == []


async def test_missing_key_is_unavailable(tmp_path):
    s = Setup(tmp_path, ["unused"], environ={})
    with pytest.raises(SlotUnavailable, match="OPENAI_API_KEY"):
        await s.caller.call(1, MESSAGES, debate_id=None)


async def test_call_json_parses(tmp_path):
    s = Setup(tmp_path, [op_json("찬성")])
    opinion, result = await s.caller.call_json(1, MESSAGES, Opinion, debate_id=None)
    assert opinion.position == "찬성"
    assert result.input_tokens == 10


async def test_call_json_retries_once_on_format_violation(tmp_path):
    s = Setup(tmp_path, ["형식 없는 답", op_json("찬성")])
    opinion, result = await s.caller.call_json(1, MESSAGES, Opinion, debate_id=None)
    assert opinion.position == "찬성"
    assert (result.input_tokens, result.output_tokens) == (20, 10)
    retry_prompt = s.fake.calls[1]
    assert retry_prompt[-2] == ChatMessage("assistant", "형식 없는 답")
    assert "형식이 아닙니다" in retry_prompt[-1].content


async def test_call_json_gives_up_after_second_violation(tmp_path):
    s = Setup(tmp_path, ["나쁨", "또 나쁨"])
    with pytest.raises(ProviderError, match="응답 형식 위반"):
        await s.caller.call_json(1, MESSAGES, Opinion, debate_id=None)
    assert len(s.fake.calls) == 2
