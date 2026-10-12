"""토론 흐름(스펙 4장): 독립 의견 → 판정 → 상호 검토 반복 → 최종 통합."""

import asyncio
from dataclasses import dataclass

from roundtable.clock import utcnow
from roundtable.debate import prompts
from roundtable.debate.caller import CallResult, SlotCaller, SlotUnavailable
from roundtable.debate.events import EventBus
from roundtable.debate.schemas import Critique, FinalResult, JudgeEval, Opinion, ReviewedOpinion
from roundtable.providers.base import (
    CreditsExhausted,
    DailyQuotaExhausted,
    ProviderError,
    ProviderFailure,
)
from roundtable.slots.service import JUDGE_SLOT_ID
from roundtable.storage.models import Slot
from roundtable.storage.store import DebateStore

LABELS = "ABCD"
MAX_CONSECUTIVE_FAILURES = 2
END_REASONS = {
    "converged": "수렴",
    "stalled": "정체",
    "stopped": "사용자 중단",
    "interrupted": "모든 참여 AI 소진",
}


def build_participants(slots: list[Slot]) -> list[dict]:
    return [
        {"label": LABELS[index], "slot_id": slot.id, "provider": slot.provider, "model": slot.model}
        for index, slot in enumerate(slots)
    ]


def describe_failure(exc: Exception) -> str:
    if isinstance(exc, DailyQuotaExhausted):
        return "일일 무료 한도 소진"
    if isinstance(exc, CreditsExhausted):
        return "무료 크레딧 소진"
    if isinstance(exc, SlotUnavailable):
        return exc.reason
    if isinstance(exc, ProviderFailure):
        return f"오류: {exc.message}"
    return f"오류: {exc}"


@dataclass
class Participant:
    label: str
    slot_id: int
    provider: str
    model: str
    active: bool = True
    failures: int = 0


@dataclass
class _State:
    debate_id: int
    question: str
    participants: list[Participant]
    dropouts: list[dict]
    latest: dict[str, Opinion]
    evals: list[JudgeEval]
    stall_threshold: int

    def active(self) -> list[Participant]:
        return [p for p in self.participants if p.active]

    def is_active(self, label: str) -> bool:
        return any(p.label == label and p.active for p in self.participants)


class JudgePause(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


Outcome = tuple[Opinion, CallResult] | Exception


class Orchestrator:
    def __init__(
        self,
        store: DebateStore,
        caller: SlotCaller,
        bus: EventBus,
        judge_slot_id: int = JUDGE_SLOT_ID,
    ) -> None:
        self._store = store
        self._caller = caller
        self._bus = bus
        self._judge_slot_id = judge_slot_id
        self._tasks: dict[int, asyncio.Task] = {}
        self._stop_requested: set[int] = set()

    # ---- 실행 관리 ----

    def start(self, debate_id: int) -> asyncio.Task:
        existing = self._tasks.get(debate_id)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(self.run(debate_id))
        self._tasks[debate_id] = task

        def _cleanup(done: asyncio.Task) -> None:
            if self._tasks.get(debate_id) is done:
                del self._tasks[debate_id]

        task.add_done_callback(_cleanup)
        return task

    async def wait(self, debate_id: int) -> None:
        task = self._tasks.get(debate_id)
        if task is not None:
            await task

    def is_running(self, debate_id: int) -> bool:
        task = self._tasks.get(debate_id)
        return task is not None and not task.done()

    def request_stop(self, debate_id: int) -> None:
        self._stop_requested.add(debate_id)

    async def run(self, debate_id: int) -> None:
        try:
            await self._run(debate_id)
        except asyncio.CancelledError:
            try:
                self._store.update(debate_id, status="interrupted", pause_reason="내부 오류: 실행이 취소됨")
            finally:
                self._bus.publish(debate_id, "error", {"message": "내부 오류: 실행이 취소됨"})
            raise
        except Exception as exc:  # 예상하지 못한 오류도 토론 상태에 남긴다
            try:
                self._store.update(debate_id, status="interrupted", pause_reason=f"내부 오류: {exc}")
            finally:
                self._bus.publish(debate_id, "error", {"message": f"내부 오류: {exc}"})
        finally:
            self._stop_requested.discard(debate_id)

    # ---- 토론 흐름 ----

    async def _run(self, debate_id: int) -> None:
        debate = self._store.get(debate_id)
        self._store.delete_incomplete_rounds(debate_id)
        self._store.update(debate_id, status="running", pause_reason=None)

        dropped = {d["label"] for d in debate.dropouts}
        participants = [
            Participant(
                label=p["label"], slot_id=p["slot_id"], provider=p["provider"],
                model=p["model"], active=p["label"] not in dropped,
            )
            for p in debate.participants
        ]
        latest: dict[str, Opinion] = {}
        evals: list[JudgeEval] = []
        last_number = 0
        for completed in self._store.completed_rounds(debate_id):
            last_number = completed.number
            for label, content in completed.contents.items():
                latest[label] = Opinion.model_validate(content)
            if completed.judge_eval is not None:
                evals.append(JudgeEval.model_validate(completed.judge_eval))
        state = _State(
            debate_id, debate.question, participants, list(debate.dropouts),
            latest, evals, debate.stall_threshold,
        )

        if debate.pending_status:
            await self._finish(state, debate.pending_status)
            return

        stall_count = 0
        for evaluation in reversed(evals):
            if evaluation.status != "stalled":
                break
            stall_count += 1

        number = last_number + 1
        while True:
            if debate_id in self._stop_requested:
                await self._finish(state, "stopped")
                return
            active = state.active()
            if not active:
                await self._finish(state, "interrupted")
                return
            try:
                evaluation = await self._play_round(state, number, active)
            except JudgePause as pause:
                self._pause(state, pause.reason)
                return
            if evaluation is not None:
                if evaluation.status == "converged":
                    await self._finish(state, "converged")
                    return
                stall_count = stall_count + 1 if evaluation.status == "stalled" else 0
                if stall_count >= state.stall_threshold:
                    await self._finish(state, "stalled")
                    return
            number += 1

    async def _play_round(
        self, state: _State, number: int, active: list[Participant]
    ) -> JudgeEval | None:
        round_id = self._store.add_round(state.debate_id, number)
        self._bus.publish(
            state.debate_id, "round_started",
            {"round": number, "participants": [p.label for p in active]},
        )

        critique_issues: list[str] | None = None
        if len(active) == 1 and active[0].label in state.latest:
            critique, _ = await self._judge(
                state, prompts.critique_messages(state.question, state.latest[active[0].label]), Critique
            )
            critique_issues = critique.weaknesses + critique.counterarguments

        previous = dict(state.latest)
        outcomes = await asyncio.gather(
            *(self._speak(state, p, previous, critique_issues) for p in active)
        )
        produced = 0
        for participant, outcome in zip(active, outcomes):
            produced += self._record(state, round_id, number, participant, outcome)

        if produced == 0:
            self._store.complete_round(round_id, None)
            return None

        if len(state.active()) == 1 and critique_issues is None:
            # 비평을 받지 않은 단독 참여자는 수렴 판정 대상이 아니다. 다음 라운드에서 비평을 받는다.
            self._store.complete_round(round_id, None)
            return None

        current = {p.label: state.latest[p.label] for p in state.active() if p.label in state.latest}
        previous_for_judge = {label: previous[label] for label in current if label in previous} or None
        evaluation, _ = await self._judge(
            state, prompts.judge_eval_messages(state.question, current, previous_for_judge), JudgeEval
        )
        self._store.complete_round(round_id, evaluation.model_dump())
        state.evals.append(evaluation)
        self._bus.publish(
            state.debate_id, "judge_evaluated", {"round": number, **evaluation.model_dump()}
        )
        return evaluation

    async def _speak(
        self,
        state: _State,
        participant: Participant,
        previous: dict[str, Opinion],
        critique_issues: list[str] | None,
    ) -> Outcome:
        if participant.label not in previous:
            messages = prompts.opinion_messages(state.question)
            model_cls: type[Opinion] = Opinion
        else:
            if critique_issues is not None:
                others: dict[str, Opinion] = {}
                issues = critique_issues
            else:
                others = {
                    label: opinion for label, opinion in previous.items()
                    if label != participant.label and state.is_active(label)
                }
                issues = state.evals[-1].issues if state.evals else []
            messages = prompts.review_messages(
                state.question, previous[participant.label], others, issues
            )
            model_cls = ReviewedOpinion
        try:
            return await self._caller.call_json(
                participant.slot_id, messages, model_cls, debate_id=state.debate_id
            )
        except (ProviderFailure, SlotUnavailable) as exc:
            return exc

    def _record(
        self,
        state: _State,
        round_id: int,
        number: int,
        participant: Participant,
        outcome: Outcome,
    ) -> int:
        if isinstance(outcome, tuple):
            opinion, result = outcome
            content = opinion.model_dump()
            self._store.add_message(
                round_id, label=participant.label, provider=result.provider, model=result.model,
                content=content, input_tokens=result.input_tokens,
                output_tokens=result.output_tokens, latency_ms=result.latency_ms,
            )
            state.latest[participant.label] = opinion
            participant.failures = 0
            self._bus.publish(
                state.debate_id, "message",
                {"round": number, "label": participant.label, "content": content},
            )
            return 1

        reason = describe_failure(outcome)
        self._store.add_message(
            round_id, label=participant.label, provider=participant.provider,
            model=participant.model, content=None, error=reason,
        )
        if isinstance(outcome, (DailyQuotaExhausted, CreditsExhausted, SlotUnavailable)):
            self._drop(state, participant, number, reason)
        else:
            participant.failures += 1
            if participant.failures >= MAX_CONSECUTIVE_FAILURES:
                self._drop(state, participant, number, f"2라운드 연속 실패: {reason}")
        return 0

    def _drop(self, state: _State, participant: Participant, number: int, reason: str) -> None:
        participant.active = False
        dropout = {
            "label": participant.label, "provider": participant.provider,
            "model": participant.model, "round": number, "reason": reason,
        }
        state.dropouts.append(dropout)
        self._store.update(state.debate_id, dropouts=list(state.dropouts))
        self._bus.publish(state.debate_id, "participant_dropped", dropout)

    async def _judge(self, state: _State, messages, model_cls):
        try:
            return await self._caller.call_json(
                self._judge_slot_id, messages, model_cls, debate_id=state.debate_id
            )
        except (DailyQuotaExhausted, CreditsExhausted, SlotUnavailable) as exc:
            raise JudgePause(f"판정 AI {describe_failure(exc)}") from exc
        except ProviderError as exc:
            raise JudgePause(f"판정 AI 오류: {exc.message}") from exc

    def _pause(self, state: _State, reason: str) -> None:
        self._store.update(state.debate_id, status="paused", pause_reason=reason)
        self._bus.publish(state.debate_id, "paused", {"reason": reason})

    async def _finish(self, state: _State, status: str) -> None:
        end_reason = END_REASONS[status]
        if not state.latest:
            self._store.update(
                state.debate_id, status=status, grade=None, pending_status=None,
                result={"dropouts": state.dropouts, "end_reason": end_reason}, ended_at=utcnow(),
            )
            self._bus.publish(state.debate_id, "finished", {"status": status, "grade": None})
            return
        try:
            final, _ = await self._judge(
                state,
                prompts.final_messages(
                    state.question, state.latest, state.evals[-1] if state.evals else None, end_reason
                ),
                FinalResult,
            )
        except JudgePause as pause:
            self._store.update(state.debate_id, pending_status=status)
            self._pause(state, pause.reason)
            return
        result = final.model_dump() | {"dropouts": state.dropouts, "end_reason": end_reason}
        self._store.update(
            state.debate_id, status=status, grade=final.grade, result=result,
            pending_status=None, pause_reason=None, ended_at=utcnow(),
        )
        self._bus.publish(state.debate_id, "finished", {"status": status, "grade": final.grade})
