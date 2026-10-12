from datetime import datetime, timedelta

from roundtable.storage.db import init_db, make_engine
from roundtable.storage.models import Slot
from roundtable.usage.recorder import UsageRecorder


def make(tmp_path, clock):
    engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    return UsageRecorder(engine, now=lambda: clock[0])


def test_summary_counts_today_and_total(tmp_path):
    clock = [datetime(2026, 10, 11, 23, 0)]
    usage = make(tmp_path, clock)
    usage.record(provider="gemini", model="f", debate_id=1, input_tokens=10, output_tokens=5, outcome="ok")
    clock[0] = datetime(2026, 10, 12, 9, 0)
    usage.record(provider="gemini", model="f", debate_id=1, input_tokens=10, output_tokens=5, outcome="ok")
    usage.record(provider="gemini", model="f", debate_id=1, input_tokens=20, output_tokens=0, outcome="ok")
    usage.record(provider="gemini", model="f", debate_id=1, input_tokens=0, output_tokens=0, outcome="error")
    usage.record(provider="openai", model="g", debate_id=1, input_tokens=99, output_tokens=99, outcome="ok")

    assert usage.summary("gemini", "f") == {
        "today_requests": 2, "today_tokens": 35, "total_requests": 3, "total_tokens": 50,
    }


def test_estimate_uses_known_daily_limit(tmp_path):
    clock = [datetime(2026, 10, 12, 9, 0)]
    usage = make(tmp_path, clock)
    for _ in range(2):
        usage.record(provider="gemini", model="f", debate_id=None, input_tokens=1, output_tokens=1, outcome="ok")
    with_limit = Slot(id=3, kind="participant", provider="gemini", model="f", api_key_env="K", known_limit={"requests_per_day": 4})
    without_limit = Slot(id=3, kind="participant", provider="gemini", model="f", api_key_env="K")

    assert usage.estimate(with_limit) == 0.5
    assert usage.estimate(without_limit) is None
    clock[0] += timedelta(days=1)
    assert usage.estimate(with_limit) == 0.0
