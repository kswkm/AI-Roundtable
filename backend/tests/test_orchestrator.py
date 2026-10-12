import json

from fakes import (
    ALL_KEYS,
    ScriptedProvider,
    critique_json,
    eval_json,
    final_json,
    no_sleep,
    op_json,
    review_json,
)
from roundtable.debate.caller import SlotCaller
from roundtable.debate.events import EventBus
from roundtable.debate.orchestrator import Orchestrator, build_participants
from roundtable.providers.base import CreditsExhausted, DailyQuotaExhausted, ProviderError
from roundtable.slots.service import JUDGE_SLOT_ID, SlotService
from roundtable.storage.db import init_db, make_engine
from roundtable.storage.store import DebateStore
from roundtable.usage.recorder import UsageRecorder


class Harness:
    def __init__(self, tmp_path, participants: dict[int, list], judge: list):
        engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
        init_db(engine)
        self.slots = SlotService(engine, environ=ALL_KEYS)
        self.slots.seed_defaults()
        self.usage = UsageRecorder(engine)
        self.store = DebateStore(engine)
        self.bus = EventBus()
        self.fakes = {sid: ScriptedProvider(script, name=f"slot{sid}") for sid, script in participants.items()}
        self.fakes[JUDGE_SLOT_ID] = ScriptedProvider(judge, name="judge")
        self.sleeps: list[float] = []

        async def sleep(seconds):
            self.sleeps.append(seconds)

        caller = SlotCaller(self.slots, self.usage, lambda slot, key: self.fakes[slot.id], sleep=sleep)
        self.orch = Orchestrator(self.store, caller, self.bus)
        self.events = []

    def create(self, slot_ids=None, stall_threshold=2, question="질문") -> int:
        ids = slot_ids or sorted(sid for sid in self.fakes if sid != JUDGE_SLOT_ID)
        participants = build_participants([self.slots.get(sid) for sid in ids])
        return self.store.create_debate(question, participants, stall_threshold)

    async def run(self, debate_id: int) -> None:
        queue = self.bus.subscribe(debate_id)
        await self.orch.run(debate_id)
        while not queue.empty():
            self.events.append(queue.get_nowait())
        self.bus.unsubscribe(debate_id, queue)

    def event_types(self):
        return [e.type for e in self.events]

    def detail(self, debate_id):
        return self.store.detail(debate_id)


def test_build_participants_labels_in_order(tmp_path):
    h = Harness(tmp_path, {}, [])
    participants = build_participants([h.slots.get(3), h.slots.get(1)])
    assert participants == [
        {"label": "A", "slot_id": 3, "provider": "gemini", "model": "gemini-2.5-flash"},
        {"label": "B", "slot_id": 1, "provider": "openai", "model": "gpt-4o-mini"},
    ]


async def test_converges_in_round_one(tmp_path):
    h = Harness(tmp_path, {1: [op_json("찬성")], 2: [op_json("찬성")]}, [eval_json("converged"), final_json()])
    debate_id = h.create()

    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "converged"
    assert detail["grade"] == "consensus"
    assert detail["result"]["final_opinion"] == "통합 의견"
    assert detail["result"]["end_reason"] == "수렴"
    assert detail["result"]["dropouts"] == []
    assert detail["ended_at"] is not None
    assert [m["label"] for m in detail["rounds"][0]["messages"]] == ["A", "B"]
    assert detail["rounds"][0]["messages"][1]["provider"] == "anthropic"
    assert h.event_types() == ["round_started", "message", "message", "judge_evaluated", "finished"]
    assert h.usage.summary("openai", "gpt-4o-mini")["total_requests"] == 1


async def test_round_one_is_independent_and_review_is_anonymized(tmp_path):
    h = Harness(
        tmp_path,
        {1: [op_json("POS-ONE"), review_json("POS-ONE")], 2: [op_json("POS-TWO"), review_json("POS-TWO")]},
        [eval_json("progressing", issues=["쟁점X"]), eval_json("converged"), final_json()],
    )
    debate_id = h.create()

    await h.run(debate_id)

    first_round = h.fakes[1].prompt(0)
    assert "POS-TWO" not in first_round
    second_round = h.fakes[1].prompt(1)
    assert "[참여자 B]" in second_round and "POS-TWO" in second_round
    assert "쟁점X" in second_round
    assert "claude-haiku-4-5" not in second_round and "anthropic" not in second_round
    assert h.detail(debate_id)["status"] == "converged"


async def test_stalls_after_threshold_consecutive_rounds(tmp_path):
    ops = [op_json("A"), review_json("A"), review_json("A"), review_json("A")]
    h = Harness(
        tmp_path,
        {1: list(ops), 2: list(ops)},
        [eval_json("stalled"), eval_json("progressing"), eval_json("stalled"), eval_json("stalled"),
         final_json(grade="no_consensus")],
    )
    debate_id = h.create(stall_threshold=2)

    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "stalled"
    assert detail["grade"] == "no_consensus"
    assert detail["result"]["end_reason"] == "정체"
    assert [r["number"] for r in detail["rounds"]] == [1, 2, 3, 4]  # 2라운드의 progressing이 정체 횟수를 초기화


async def test_user_stop_finishes_after_current_round(tmp_path):
    h = Harness(tmp_path, {1: [op_json("A")], 2: [op_json("B")]}, [])
    debate_id = h.create()

    def evaluate_and_stop(_messages):
        h.orch.request_stop(debate_id)
        return eval_json("progressing")

    h.fakes[JUDGE_SLOT_ID].script = [evaluate_and_stop, final_json(grade="partial")]

    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "stopped"
    assert detail["result"]["end_reason"] == "사용자 중단"
    assert len(detail["rounds"]) == 1


async def test_exhausted_participant_is_dropped_and_debate_continues(tmp_path):
    h = Harness(
        tmp_path,
        {
            1: [op_json("A"), review_json("A")],
            2: [op_json("B"), CreditsExhausted("credit balance is too low")],
            3: [op_json("C"), review_json("C")],
        },
        [eval_json("progressing"), eval_json("converged"), final_json()],
    )
    debate_id = h.create()

    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "converged"
    assert detail["dropouts"] == [
        {"label": "B", "provider": "anthropic", "model": "claude-haiku-4-5", "round": 2, "reason": "무료 크레딧 소진"}
    ]
    assert detail["result"]["dropouts"] == detail["dropouts"]
    assert "participant_dropped" in h.event_types()
    assert h.slots.get(2).status == "exhausted"
    round_two_judge_prompt = h.fakes[JUDGE_SLOT_ID].prompt(1)
    assert "[참여자 B]" not in round_two_judge_prompt.split("직전 라운드 의견")[0]


async def test_single_remaining_participant_switches_to_critique_mode(tmp_path):
    h = Harness(
        tmp_path,
        {
            1: [op_json("A"), review_json("A"), review_json("A-수정")],
            2: [op_json("B"), DailyQuotaExhausted("day")],
        },
        [eval_json("progressing"), eval_json("progressing"), critique_json(), eval_json("converged"), final_json()],
    )
    debate_id = h.create()

    await h.run(debate_id)

    third_round = h.fakes[1].prompt(2)
    assert "약점-1" in third_round and "반론-1" in third_round
    assert "[참여자 B]" not in third_round
    assert h.detail(debate_id)["status"] == "converged"
    assert h.detail(debate_id)["dropouts"][0]["reason"] == "일일 무료 한도 소진"


async def test_single_participant_debate_uses_judge_as_critic(tmp_path):
    h = Harness(
        tmp_path,
        {1: [op_json("A"), review_json("A2")]},
        [eval_json("progressing"), critique_json(weaknesses=["근거 부족"]), eval_json("converged"), final_json()],
    )
    debate_id = h.create(slot_ids=[1])

    await h.run(debate_id)

    assert "근거 부족" in h.fakes[1].prompt(1)
    assert h.detail(debate_id)["status"] == "converged"


async def test_all_participants_exhausted_without_opinions_interrupts(tmp_path):
    h = Harness(tmp_path, {1: [CreditsExhausted("no credits")]}, [])
    debate_id = h.create(slot_ids=[1])

    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "interrupted"
    assert detail["grade"] is None
    assert detail["ended_at"] is not None
    assert detail["result"]["end_reason"] == "모든 참여 AI 소진"
    assert detail["result"]["dropouts"][0]["label"] == "A"
    assert h.event_types()[-1] == "finished"
    assert h.fakes[JUDGE_SLOT_ID].calls == []


async def test_all_participants_exhausted_after_opinions_still_synthesizes(tmp_path):
    h = Harness(
        tmp_path,
        {1: [op_json("A"), CreditsExhausted("x")], 2: [op_json("B"), CreditsExhausted("x")]},
        [eval_json("progressing"), final_json(grade="partial")],
    )
    debate_id = h.create()

    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "interrupted"
    assert detail["grade"] == "partial"
    assert detail["result"]["final_opinion"] == "통합 의견"
    assert detail["result"]["end_reason"] == "모든 참여 AI 소진"


async def test_provider_errors_skip_a_round_then_drop_after_two(tmp_path):
    h = Harness(
        tmp_path,
        {
            1: [op_json("A"), review_json("A"), review_json("A")],
            2: [op_json("B")] + [ProviderError("HTTP 500")] * 6,
        },
        [eval_json("progressing"), eval_json("progressing"), eval_json("converged"), final_json()],
    )
    debate_id = h.create()

    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert h.sleeps == [1.0, 2.0, 1.0, 2.0]
    assert detail["rounds"][1]["messages"][1]["error"] == "오류: HTTP 500"
    assert detail["dropouts"][0]["round"] == 3
    assert detail["dropouts"][0]["reason"].startswith("2라운드 연속 실패")
    assert detail["status"] == "converged"


async def test_judge_exhausted_pauses_and_resume_replays_round(tmp_path):
    h = Harness(
        tmp_path,
        {1: [op_json("A"), review_json("A"), review_json("A")], 2: [op_json("B"), review_json("B"), review_json("B")]},
        [eval_json("progressing"), DailyQuotaExhausted("day")],
    )
    debate_id = h.create()

    await h.run(debate_id)

    paused = h.store.get(debate_id)
    assert paused.status == "paused"
    assert paused.pause_reason == "판정 AI 일일 무료 한도 소진"
    assert h.event_types()[-1] == "paused"
    assert h.slots.get(JUDGE_SLOT_ID).status == "exhausted"

    h.slots.update(JUDGE_SLOT_ID, provider="gemini", model="gemini-2.5-flash", api_key_env="GEMINI_API_KEY")
    h.fakes[JUDGE_SLOT_ID] = ScriptedProvider([eval_json("converged"), final_json()], name="judge2")
    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "converged"
    assert detail["pause_reason"] is None
    assert [r["number"] for r in detail["rounds"]] == [1, 2]
    assert len(detail["rounds"][1]["messages"]) == 2  # 끝나지 않았던 2라운드는 지우고 다시 진행


async def test_judge_exhausted_at_final_keeps_pending_status(tmp_path):
    h = Harness(tmp_path, {1: [op_json("A")], 2: [op_json("B")]}, [eval_json("converged"), CreditsExhausted("x")])
    debate_id = h.create()

    await h.run(debate_id)

    paused = h.store.get(debate_id)
    assert (paused.status, paused.pending_status) == ("paused", "converged")

    h.slots.update(JUDGE_SLOT_ID, provider="gemini", model="gemini-2.5-flash", api_key_env="GEMINI_API_KEY")
    h.fakes[JUDGE_SLOT_ID] = ScriptedProvider([final_json()], name="judge2")
    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "converged"
    assert detail["result"]["final_opinion"] == "통합 의견"
    assert len(detail["rounds"]) == 1
    assert h.store.get(debate_id).pending_status is None


async def test_restart_recovery_continues_from_last_completed_round(tmp_path):
    h = Harness(tmp_path, {1: [review_json("A")], 2: [review_json("B")]}, [eval_json("converged"), final_json()])
    debate_id = h.create()
    r1 = h.store.add_round(debate_id, 1)
    h.store.add_message(r1, label="A", provider="openai", model="gpt-4o-mini", content=json.loads(op_json("A")))
    h.store.add_message(r1, label="B", provider="anthropic", model="claude-haiku-4-5", content=json.loads(op_json("B")))
    h.store.complete_round(r1, json.loads(eval_json("progressing", issues=["쟁점-R"])))
    r2 = h.store.add_round(debate_id, 2)
    h.store.add_message(r2, label="A", provider="openai", model="gpt-4o-mini", content=json.loads(review_json("A")))

    assert h.store.mark_running_as_interrupted() == 1
    await h.run(debate_id)

    detail = h.detail(debate_id)
    assert detail["status"] == "converged"
    assert [r["number"] for r in detail["rounds"]] == [1, 2]
    assert len(detail["rounds"][1]["messages"]) == 2
    resumed_prompt = h.fakes[1].prompt(0)
    assert "B의 근거" in resumed_prompt and "쟁점-R" in resumed_prompt


async def test_unexpected_exception_marks_interrupted_and_publishes_error(tmp_path):
    h = Harness(tmp_path, {1: [op_json("A")]}, [])
    debate_id = h.create(slot_ids=[1])

    def explode(_messages):
        raise RuntimeError("boom")

    h.fakes[JUDGE_SLOT_ID].script = [explode]

    await h.run(debate_id)

    debate = h.store.get(debate_id)
    assert debate.status == "interrupted"
    assert "boom" in debate.pause_reason
    assert h.event_types()[-1] == "error"


async def test_start_and_wait(tmp_path):
    h = Harness(tmp_path, {1: [op_json("A")]}, [eval_json("converged"), final_json()])
    debate_id = h.create(slot_ids=[1])

    h.orch.start(debate_id)
    assert h.orch.is_running(debate_id)
    await h.orch.wait(debate_id)

    assert not h.orch.is_running(debate_id)
    assert h.store.get(debate_id).status == "converged"


async def test_double_start_runs_only_once(tmp_path):
    h = Harness(tmp_path, {1: [op_json("A")]}, [eval_json("converged"), final_json()])
    debate_id = h.create(slot_ids=[1])

    first = h.orch.start(debate_id)
    second = h.orch.start(debate_id)
    assert first is second
    await h.orch.wait(debate_id)

    assert not h.orch.is_running(debate_id)
    assert len(h.fakes[1].calls) == 1


async def test_cancel_marks_interrupted_and_publishes_terminal_event(tmp_path):
    import asyncio

    h = Harness(tmp_path, {1: [op_json("A")]}, [])
    debate_id = h.create(slot_ids=[1])
    gate = asyncio.Event()

    class Hanging:
        async def complete(self, messages, response_schema=None):
            await gate.wait()

    h.fakes[1] = Hanging()
    queue = h.bus.subscribe(debate_id)
    task = h.orch.start(debate_id)
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert h.store.get(debate_id).status == "interrupted"
    types = []
    while not queue.empty():
        types.append(queue.get_nowait().type)
    assert types[-1] == "error"


async def test_error_event_published_even_if_store_update_fails(tmp_path):
    h = Harness(tmp_path, {1: [op_json("A")]}, [])
    debate_id = h.create(slot_ids=[1])
    h.fakes[JUDGE_SLOT_ID].script = [lambda _m: (_ for _ in ()).throw(RuntimeError("boom"))]
    real_update = h.store.update

    def update(did, **fields):
        if fields.get("status") == "interrupted":
            raise OSError("db down")
        return real_update(did, **fields)

    h.store.update = update
    queue = h.bus.subscribe(debate_id)
    try:
        await h.orch.run(debate_id)
    except OSError:
        pass
    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    assert events[-1].type == "error"
    assert "내부 오류" in events[-1].data["message"]
