from roundtable.storage.config import ConfigStore
from roundtable.storage.db import init_db, make_engine
from roundtable.storage.store import DebateStore

PARTS = [
    {"label": "A", "slot_id": 1, "provider": "openai", "model": "m1"},
    {"label": "B", "slot_id": 2, "provider": "anthropic", "model": "m2"},
]
EVAL = {"status": "progressing", "issues": ["x"], "draft": "d"}


def make(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    return DebateStore(engine), engine


def test_create_and_get(tmp_path):
    store, _ = make(tmp_path)
    debate_id = store.create_debate("질문", PARTS, 2)
    debate = store.get(debate_id)
    assert debate.status == "running"
    assert debate.question == "질문"
    assert debate.participants == PARTS
    assert debate.dropouts == []
    assert debate.stall_threshold == 2
    assert debate.user_id is None
    assert store.get(999) is None


def test_update_sets_fields(tmp_path):
    store, _ = make(tmp_path)
    debate_id = store.create_debate("q", PARTS, 2)
    store.update(debate_id, status="paused", pause_reason="판정 AI 소진", dropouts=[{"label": "B"}])
    debate = store.get(debate_id)
    assert (debate.status, debate.pause_reason, debate.dropouts) == ("paused", "판정 AI 소진", [{"label": "B"}])


def test_completed_rounds_skip_incomplete_rounds_and_failed_messages(tmp_path):
    store, _ = make(tmp_path)
    debate_id = store.create_debate("q", PARTS, 2)
    r1 = store.add_round(debate_id, 1)
    store.add_message(r1, label="A", provider="openai", model="m1", content={"position": "x"})
    store.add_message(r1, label="B", provider="anthropic", model="m2", content=None, error="오류")
    store.complete_round(r1, EVAL)
    r2 = store.add_round(debate_id, 2)
    store.add_message(r2, label="A", provider="openai", model="m1", content={"position": "y"})

    completed = store.completed_rounds(debate_id)

    assert len(completed) == 1
    assert completed[0].number == 1
    assert completed[0].judge_eval == EVAL
    assert completed[0].contents == {"A": {"position": "x"}}


def test_delete_incomplete_rounds_removes_round_and_messages(tmp_path):
    store, _ = make(tmp_path)
    debate_id = store.create_debate("q", PARTS, 2)
    r1 = store.add_round(debate_id, 1)
    store.complete_round(r1, EVAL)
    r2 = store.add_round(debate_id, 2)
    store.add_message(r2, label="A", provider="openai", model="m1", content={"position": "y"})

    store.delete_incomplete_rounds(debate_id)

    assert [r["number"] for r in store.detail(debate_id)["rounds"]] == [1]


def test_mark_running_as_interrupted(tmp_path):
    store, _ = make(tmp_path)
    running = store.create_debate("q1", PARTS, 2)
    done = store.create_debate("q2", PARTS, 2)
    store.update(done, status="converged")

    assert store.mark_running_as_interrupted() == 1
    assert store.get(running).status == "interrupted"
    assert store.get(running).pause_reason == "서버 재시작"
    assert store.get(done).status == "converged"


def test_detail_includes_rounds_and_messages(tmp_path):
    store, _ = make(tmp_path)
    debate_id = store.create_debate("q", PARTS, 2)
    r1 = store.add_round(debate_id, 1)
    store.add_message(
        r1, label="A", provider="openai", model="m1", content={"position": "x"},
        input_tokens=10, output_tokens=5, latency_ms=300,
    )
    store.complete_round(r1, EVAL)

    detail = store.detail(debate_id)

    assert detail["id"] == debate_id
    assert detail["status"] == "running"
    assert isinstance(detail["started_at"], str)
    assert detail["ended_at"] is None
    round_ = detail["rounds"][0]
    assert round_["number"] == 1
    assert round_["judge_eval"] == EVAL
    assert round_["messages"] == [
        {"label": "A", "provider": "openai", "model": "m1", "content": {"position": "x"},
         "error": None, "input_tokens": 10, "output_tokens": 5, "latency_ms": 300}
    ]
    assert store.detail(999) is None


def test_list_debates_newest_first(tmp_path):
    store, _ = make(tmp_path)
    first = store.create_debate("q1", PARTS, 2)
    second = store.create_debate("q2", PARTS, 2)
    assert [d.id for d in store.list_debates()] == [second, first]


def test_config_store_default_and_set(tmp_path):
    _, engine = make(tmp_path)
    config = ConfigStore(engine)
    assert config.stall_threshold() == 2
    config.set_stall_threshold(3)
    assert config.stall_threshold() == 3
    config.set_stall_threshold(4)
    assert config.stall_threshold() == 4
