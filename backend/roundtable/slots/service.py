import os
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta

from sqlalchemy import Engine
from sqlmodel import Session, select

from roundtable.clock import utcnow
from roundtable.providers.base import (
    CreditsExhausted,
    DailyQuotaExhausted,
    ProviderFailure,
    RateLimited,
)
from roundtable.providers.registry import PROVIDER_IDS
from roundtable.storage.models import Slot

PARTICIPANT_SLOT_IDS = (1, 2, 3, 4)
JUDGE_SLOT_ID = 5
DEFAULT_RATE_LIMIT_WAIT = 60.0

DEFAULT_SLOTS = [
    {"id": 1, "kind": "participant", "provider": "openai", "model": "gpt-4o-mini", "api_key_env": "OPENAI_API_KEY"},
    {"id": 2, "kind": "participant", "provider": "anthropic", "model": "claude-haiku-4-5", "api_key_env": "ANTHROPIC_API_KEY"},
    {"id": 3, "kind": "participant", "provider": "gemini", "model": "gemini-2.5-flash", "api_key_env": "GEMINI_API_KEY"},
    {"id": 4, "kind": "participant", "provider": "xai", "model": "grok-3-mini", "api_key_env": "XAI_API_KEY"},
    {"id": JUDGE_SLOT_ID, "kind": "judge", "provider": "gemini", "model": "gemini-2.5-flash-lite", "api_key_env": "GEMINI_API_KEY"},
]


class SlotService:
    def __init__(
        self,
        engine: Engine,
        now: Callable[[], datetime] = utcnow,
        environ: Mapping[str, str] = os.environ,
    ) -> None:
        self._engine = engine
        self._now = now
        self._environ = environ

    def _session(self) -> Session:
        return Session(self._engine, expire_on_commit=False)

    def seed_defaults(self) -> None:
        with self._session() as session:
            for default in DEFAULT_SLOTS:
                if session.get(Slot, default["id"]) is None:
                    session.add(Slot(**default))
            session.commit()

    def list(self) -> list[Slot]:
        with self._session() as session:
            slots = list(session.exec(select(Slot).order_by(Slot.id)).all())
            for slot in slots:
                self._refresh(session, slot)
            session.commit()
            return slots

    def get(self, slot_id: int) -> Slot:
        with self._session() as session:
            slot = session.get(Slot, slot_id)
            if slot is None:
                raise KeyError(slot_id)
            self._refresh(session, slot)
            session.commit()
            return slot

    def _refresh(self, session: Session, slot: Slot) -> None:
        if (
            slot.status != "available"
            and slot.status_until is not None
            and self._now() >= slot.status_until
        ):
            slot.status = "available"
            slot.status_until = None
            slot.status_reason = None
            session.add(slot)

    def api_key(self, slot: Slot) -> str | None:
        return self._environ.get(slot.api_key_env) or None

    def key_present(self, slot: Slot) -> bool:
        return self.api_key(slot) is not None

    def is_usable(self, slot_id: int) -> bool:
        slot = self.get(slot_id)
        return slot.status != "exhausted" and self.key_present(slot)

    def mark_failure(self, slot_id: int, failure: ProviderFailure) -> None:
        now = self._now()
        if isinstance(failure, RateLimited):
            status = "rate_limited"
            until = now + timedelta(seconds=failure.retry_after or DEFAULT_RATE_LIMIT_WAIT)
        elif isinstance(failure, DailyQuotaExhausted):
            status = "exhausted"
            until = failure.reset_at or now + timedelta(days=1)
        elif isinstance(failure, CreditsExhausted):
            status = "exhausted"
            until = None
        else:
            return
        with self._session() as session:
            slot = session.get(Slot, slot_id)
            slot.status = status
            slot.status_until = until
            slot.status_reason = failure.message or type(failure).__name__
            session.add(slot)
            session.commit()

    def mark_ok(self, slot_id: int) -> None:
        with self._session() as session:
            slot = session.get(Slot, slot_id)
            if slot.status == "rate_limited":
                slot.status = "available"
                slot.status_until = None
                slot.status_reason = None
                session.add(slot)
                session.commit()

    def update(
        self,
        slot_id: int,
        *,
        provider: str,
        model: str,
        api_key_env: str,
        known_limit: dict | None = None,
    ) -> Slot:
        if provider not in PROVIDER_IDS:
            raise ValueError(f"알 수 없는 제공 회사: {provider}")
        with self._session() as session:
            slot = session.get(Slot, slot_id)
            if slot is None:
                raise KeyError(slot_id)
            slot.provider = provider
            slot.model = model
            slot.api_key_env = api_key_env
            slot.known_limit = known_limit
            slot.status = "available"
            slot.status_until = None
            slot.status_reason = None
            session.add(slot)
            session.commit()
            return slot
