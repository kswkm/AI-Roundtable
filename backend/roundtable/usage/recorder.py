from collections.abc import Callable
from datetime import datetime

from sqlalchemy import Engine
from sqlmodel import Session, select

from roundtable.clock import utcnow
from roundtable.storage.models import Slot, UsageLog


class UsageRecorder:
    def __init__(self, engine: Engine, now: Callable[[], datetime] = utcnow) -> None:
        self._engine = engine
        self._now = now

    def record(
        self,
        *,
        provider: str,
        model: str,
        debate_id: int | None,
        input_tokens: int,
        output_tokens: int,
        outcome: str,
    ) -> None:
        with Session(self._engine) as session:
            session.add(UsageLog(
                provider=provider, model=model, debate_id=debate_id, called_at=self._now(),
                input_tokens=input_tokens, output_tokens=output_tokens, outcome=outcome,
            ))
            session.commit()

    def summary(self, provider: str, model: str) -> dict[str, int]:
        day_start = self._now().replace(hour=0, minute=0, second=0, microsecond=0)
        with Session(self._engine) as session:
            rows = session.exec(
                select(UsageLog).where(UsageLog.provider == provider, UsageLog.model == model)
            ).all()
        today = [row for row in rows if row.called_at >= day_start]

        def requests(items):
            return sum(1 for item in items if item.outcome == "ok")

        def tokens(items):
            return sum(item.input_tokens + item.output_tokens for item in items)

        return {
            "today_requests": requests(today),
            "today_tokens": tokens(today),
            "total_requests": requests(rows),
            "total_tokens": tokens(rows),
        }

    def estimate(self, slot: Slot) -> float | None:
        limit = (slot.known_limit or {}).get("requests_per_day")
        if not limit:
            return None
        return self.summary(slot.provider, slot.model)["today_requests"] / limit
