from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from roundtable.clock import utcnow
from roundtable.storage.models import Debate, Message, Round

RESTART_REASON = "서버 재시작"


@dataclass(frozen=True)
class CompletedRound:
    number: int
    judge_eval: dict | None
    contents: dict[str, dict]  # label -> 성공한 발언 내용


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() + "Z" if value is not None else None


class DebateStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _session(self) -> Session:
        return Session(self._engine, expire_on_commit=False)

    def create_debate(self, question: str, participants: list[dict], stall_threshold: int) -> int:
        with self._session() as session:
            debate = Debate(
                question=question, participants=participants, stall_threshold=stall_threshold
            )
            session.add(debate)
            session.commit()
            return debate.id

    def get(self, debate_id: int) -> Debate | None:
        with self._session() as session:
            return session.get(Debate, debate_id)

    def list_debates(self) -> list[Debate]:
        with self._session() as session:
            return list(session.exec(select(Debate).order_by(col(Debate.id).desc())).all())

    def update(self, debate_id: int, **fields) -> None:
        with self._session() as session:
            debate = session.get(Debate, debate_id)
            if debate is None:
                raise KeyError(debate_id)
            for name, value in fields.items():
                setattr(debate, name, value)
            session.add(debate)
            session.commit()

    def add_round(self, debate_id: int, number: int) -> int:
        with self._session() as session:
            round_ = Round(debate_id=debate_id, number=number)
            session.add(round_)
            session.commit()
            return round_.id

    def add_message(
        self,
        round_id: int,
        *,
        label: str,
        provider: str,
        model: str,
        content: dict | None,
        error: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
    ) -> int:
        with self._session() as session:
            message = Message(
                round_id=round_id, label=label, provider=provider, model=model,
                content=content, error=error, input_tokens=input_tokens,
                output_tokens=output_tokens, latency_ms=latency_ms,
            )
            session.add(message)
            session.commit()
            return message.id

    def complete_round(self, round_id: int, judge_eval: dict | None) -> None:
        with self._session() as session:
            round_ = session.get(Round, round_id)
            round_.judge_eval = judge_eval
            round_.completed_at = utcnow()
            session.add(round_)
            session.commit()

    def completed_rounds(self, debate_id: int) -> list[CompletedRound]:
        with self._session() as session:
            rounds = session.exec(
                select(Round)
                .where(Round.debate_id == debate_id, col(Round.completed_at).is_not(None))
                .order_by(Round.number)
            ).all()
            result = []
            for round_ in rounds:
                messages = session.exec(select(Message).where(Message.round_id == round_.id)).all()
                contents = {m.label: m.content for m in messages if m.content is not None}
                result.append(CompletedRound(round_.number, round_.judge_eval, contents))
            return result

    def delete_incomplete_rounds(self, debate_id: int) -> None:
        with self._session() as session:
            rounds = session.exec(
                select(Round).where(Round.debate_id == debate_id, col(Round.completed_at).is_(None))
            ).all()
            for round_ in rounds:
                for message in session.exec(select(Message).where(Message.round_id == round_.id)).all():
                    session.delete(message)
                session.delete(round_)
            session.commit()

    def mark_running_as_interrupted(self) -> int:
        with self._session() as session:
            running = session.exec(select(Debate).where(Debate.status == "running")).all()
            for debate in running:
                debate.status = "interrupted"
                debate.pause_reason = RESTART_REASON
                session.add(debate)
            session.commit()
            return len(running)

    def detail(self, debate_id: int) -> dict | None:
        with self._session() as session:
            debate = session.get(Debate, debate_id)
            if debate is None:
                return None
            rounds = session.exec(
                select(Round).where(Round.debate_id == debate_id).order_by(Round.number)
            ).all()
            round_views = []
            for round_ in rounds:
                messages = session.exec(
                    select(Message).where(Message.round_id == round_.id).order_by(Message.id)
                ).all()
                round_views.append({
                    "number": round_.number,
                    "judge_eval": round_.judge_eval,
                    "completed_at": _iso(round_.completed_at),
                    "messages": [
                        {
                            "label": m.label, "provider": m.provider, "model": m.model,
                            "content": m.content, "error": m.error,
                            "input_tokens": m.input_tokens, "output_tokens": m.output_tokens,
                            "latency_ms": m.latency_ms,
                        }
                        for m in messages
                    ],
                })
            return {
                "id": debate.id,
                "question": debate.question,
                "status": debate.status,
                "grade": debate.grade,
                "result": debate.result,
                "participants": debate.participants,
                "dropouts": debate.dropouts,
                "stall_threshold": debate.stall_threshold,
                "pause_reason": debate.pause_reason,
                "started_at": _iso(debate.started_at),
                "ended_at": _iso(debate.ended_at),
                "rounds": round_views,
            }
