from datetime import datetime, timedelta

import pytest

from roundtable.providers.base import CreditsExhausted, DailyQuotaExhausted, ProviderError, RateLimited
from roundtable.slots.service import JUDGE_SLOT_ID, SlotService
from roundtable.storage.db import init_db, make_engine

START = datetime(2026, 10, 12, 12, 0)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def make(tmp_path, environ=None):
    engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    clock = Clock()
    service = SlotService(engine, now=clock, environ=environ if environ is not None else {"OPENAI_API_KEY": "k"})
    service.seed_defaults()
    return service, clock


def test_seed_defaults_creates_five_slots_once(tmp_path):
    service, _ = make(tmp_path)
    service.seed_defaults()
    slots = service.list()
    assert [s.id for s in slots] == [1, 2, 3, 4, 5]
    assert [s.provider for s in slots] == ["openai", "anthropic", "gemini", "xai", "gemini"]
    judge = service.get(JUDGE_SLOT_ID)
    assert (judge.kind, judge.model) == ("judge", "gemini-2.5-flash-lite")
    assert service.get(3).model == "gemini-2.5-flash"
    assert all(s.status == "available" for s in slots)


def test_get_unknown_slot_raises(tmp_path):
    service, _ = make(tmp_path)
    with pytest.raises(KeyError):
        service.get(9)


def test_key_presence(tmp_path):
    service, _ = make(tmp_path, environ={"OPENAI_API_KEY": "k", "ANTHROPIC_API_KEY": ""})
    assert service.api_key(service.get(1)) == "k"
    assert service.key_present(service.get(1)) is True
    assert service.key_present(service.get(2)) is False  # 빈 값은 없는 것으로 본다
    assert service.is_usable(1) is True
    assert service.is_usable(2) is False


def test_rate_limited_auto_releases(tmp_path):
    service, clock = make(tmp_path)
    service.mark_failure(1, RateLimited("slow", 30))
    slot = service.get(1)
    assert (slot.status, slot.status_until, slot.status_reason) == ("rate_limited", START + timedelta(seconds=30), "요청 한도 초과: slow")
    assert service.is_usable(1) is True  # 속도 제한은 기다리면 되므로 사용 가능
    clock.advance(seconds=31)
    assert service.get(1).status == "available"
    assert service.get(1).status_reason is None


def test_rate_limited_without_retry_after_uses_default_wait(tmp_path):
    service, _ = make(tmp_path)
    service.mark_failure(1, RateLimited("slow"))
    assert service.get(1).status_until == START + timedelta(seconds=60)


def test_daily_quota_exhausted_until_reset(tmp_path):
    service, clock = make(tmp_path)
    service.mark_failure(1, DailyQuotaExhausted("day", reset_at=START + timedelta(hours=5)))
    assert service.get(1).status == "exhausted"
    assert service.is_usable(1) is False
    clock.advance(hours=5)
    assert service.get(1).status == "available"


def test_credits_exhausted_never_auto_releases(tmp_path):
    service, clock = make(tmp_path)
    service.mark_failure(1, CreditsExhausted("no credits"))
    clock.advance(days=30)
    slot = service.list()[0]
    assert (slot.status, slot.status_until, slot.status_reason) == ("exhausted", None, "무료 크레딧 소진: no credits")


def test_provider_error_does_not_change_status(tmp_path):
    service, _ = make(tmp_path)
    service.mark_failure(1, ProviderError("500"))
    assert service.get(1).status == "available"


def test_mark_ok_clears_rate_limit_only(tmp_path):
    service, _ = make(tmp_path)
    service.mark_failure(1, RateLimited("slow", 30))
    service.mark_ok(1)
    assert service.get(1).status == "available"
    service.mark_failure(2, CreditsExhausted("x"))
    service.mark_ok(2)
    assert service.get(2).status == "exhausted"


def test_update_resets_status_and_validates_provider(tmp_path):
    service, _ = make(tmp_path)
    service.mark_failure(2, CreditsExhausted("x"))
    slot = service.update(
        2, provider="openrouter", model="meta-llama/llama-3.3-70b-instruct:free",
        api_key_env="OPENROUTER_API_KEY", known_limit={"requests_per_day": 50},
    )
    assert (slot.provider, slot.status, slot.status_reason) == ("openrouter", "available", None)
    assert service.get(2).known_limit == {"requests_per_day": 50}
    with pytest.raises(ValueError, match="알 수 없는 제공 회사"):
        service.update(2, provider="nope", model="m", api_key_env="X")
    with pytest.raises(KeyError):
        service.update(9, provider="openai", model="m", api_key_env="X")


def test_mark_failure_and_mark_ok_unknown_slot_raises_key_error(tmp_path):
    service, _ = make(tmp_path)
    with pytest.raises(KeyError):
        service.mark_failure(9, RateLimited("slow"))
    with pytest.raises(KeyError):
        service.mark_ok(9)


def test_rate_limited_does_not_overwrite_credits_exhausted(tmp_path):
    service, clock = make(tmp_path)
    service.mark_failure(1, CreditsExhausted("no credits"))
    service.mark_failure(1, RateLimited("slow", 30))
    clock.advance(days=30)
    slot = service.get(1)
    assert (slot.status, slot.status_until, slot.status_reason) == ("exhausted", None, "무료 크레딧 소진: no credits")


def test_rate_limited_does_not_shorten_daily_quota_window(tmp_path):
    service, clock = make(tmp_path)
    reset_at = START + timedelta(hours=5)
    service.mark_failure(1, DailyQuotaExhausted("day", reset_at=reset_at))
    service.mark_failure(1, RateLimited("slow", 30))
    slot = service.get(1)
    assert (slot.status, slot.status_until, slot.status_reason) == ("exhausted", reset_at, "일일 한도 소진: day")
