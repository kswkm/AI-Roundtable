import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from roundtable.api.services import Services
from roundtable.debate.events import TERMINAL_EVENTS
from roundtable.debate.orchestrator import build_participants
from roundtable.providers.registry import PROVIDER_IDS
from roundtable.slots.service import JUDGE_SLOT_ID, PARTICIPANT_SLOT_IDS
from roundtable.storage.models import Slot

router = APIRouter()
PING_SECONDS = 15


def _services(request: Request) -> Services:
    return request.app.state.services


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class CreateDebateBody(BaseModel):
    question: str = Field(max_length=4000)
    slot_ids: list[int] = Field(min_length=1, max_length=4)

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("질문을 입력하세요")
        return value

    @field_validator("slot_ids")
    @classmethod
    def _valid_slots(cls, value: list[int]) -> list[int]:
        if len(set(value)) != len(value):
            raise ValueError("같은 슬롯을 두 번 선택할 수 없습니다")
        if any(slot_id not in PARTICIPANT_SLOT_IDS for slot_id in value):
            raise ValueError("참여 슬롯은 1~4번만 선택할 수 있습니다")
        return value


class UpdateSlotBody(BaseModel):
    provider: str
    model: str = Field(min_length=1)
    api_key_env: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    known_limit: dict[str, int] | None = None


class UpdateConfigBody(BaseModel):
    stall_threshold: int = Field(ge=1, le=10)


def _ensure_usable(services: Services, slot: Slot, role: str) -> None:
    name = f"{role} {slot.provider} ({slot.model})"
    if slot.status == "exhausted":
        raise HTTPException(409, f"{name}: {slot.status_reason or '무료 제공량 소진'}")
    if not services.slots.key_present(slot):
        raise HTTPException(409, f"{name}: {slot.api_key_env} 환경변수가 없습니다")


def _slot_view(services: Services, slot: Slot) -> dict:
    return {
        "id": slot.id,
        "kind": slot.kind,
        "provider": slot.provider,
        "model": slot.model,
        "api_key_env": slot.api_key_env,
        "key_present": services.slots.key_present(slot),
        "status": slot.status,
        "status_until": _iso(slot.status_until),
        "status_reason": slot.status_reason,
        "known_limit": slot.known_limit,
        "usage": services.usage.summary(slot.provider, slot.model),
        "usage_estimate": services.usage.estimate(slot),
    }


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/debates", status_code=201)
async def create_debate(body: CreateDebateBody, request: Request) -> dict:
    services = _services(request)
    slots = [services.slots.get(slot_id) for slot_id in body.slot_ids]
    for slot in slots:
        _ensure_usable(services, slot, "참여 AI")
    _ensure_usable(services, services.slots.get(JUDGE_SLOT_ID), "판정 AI")
    debate_id = services.store.create_debate(
        body.question, build_participants(slots), services.config.stall_threshold()
    )
    services.orchestrator.start(debate_id)
    return {"id": debate_id}


@router.get("/debates")
async def list_debates(request: Request) -> list[dict]:
    return [
        {
            "id": d.id, "question": d.question, "status": d.status, "grade": d.grade,
            "started_at": _iso(d.started_at), "ended_at": _iso(d.ended_at),
        }
        for d in _services(request).store.list_debates()
    ]


@router.get("/debates/{debate_id}")
async def get_debate(debate_id: int, request: Request) -> dict:
    detail = _services(request).store.detail(debate_id)
    if detail is None:
        raise HTTPException(404, "토론을 찾을 수 없습니다")
    return detail


@router.get("/debates/{debate_id}/events")
async def debate_events(debate_id: int, request: Request) -> StreamingResponse:
    services = _services(request)
    if services.store.get(debate_id) is None:
        raise HTTPException(404, "토론을 찾을 수 없습니다")
    queue = services.bus.subscribe(debate_id)  # 상태 확인 전에 구독해서 이벤트를 놓치지 않는다

    async def stream():
        try:
            debate = services.store.get(debate_id)
            if debate.status != "running":
                yield _sse("status", {"status": debate.status})
                return
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_SECONDS)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _sse(event.type, event.data)
                if event.type in TERMINAL_EVENTS:
                    return
        finally:
            services.bus.unsubscribe(debate_id, queue)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.post("/debates/{debate_id}/stop", status_code=202)
async def stop_debate(debate_id: int, request: Request) -> dict:
    services = _services(request)
    if services.store.get(debate_id) is None:
        raise HTTPException(404, "토론을 찾을 수 없습니다")
    if not services.orchestrator.is_running(debate_id):
        raise HTTPException(409, "진행 중인 토론이 아닙니다")
    services.orchestrator.request_stop(debate_id)
    return {"status": "stopping"}


@router.post("/debates/{debate_id}/resume", status_code=202)
async def resume_debate(debate_id: int, request: Request) -> dict:
    services = _services(request)
    debate = services.store.get(debate_id)
    if debate is None:
        raise HTTPException(404, "토론을 찾을 수 없습니다")
    resumable = debate.status == "paused" or (
        debate.status == "interrupted" and debate.ended_at is None
    )
    if not resumable or services.orchestrator.is_running(debate_id):
        raise HTTPException(409, "이어할 수 있는 토론이 아닙니다")
    _ensure_usable(services, services.slots.get(JUDGE_SLOT_ID), "판정 AI")
    services.orchestrator.start(debate_id)
    return {"status": "resuming"}


@router.get("/slots")
async def list_slots(request: Request) -> list[dict]:
    services = _services(request)
    return [_slot_view(services, slot) for slot in services.slots.list()]


@router.put("/slots/{slot_id}")
async def update_slot(slot_id: int, body: UpdateSlotBody, request: Request) -> dict:
    services = _services(request)
    try:
        slot = services.slots.update(
            slot_id, provider=body.provider, model=body.model,
            api_key_env=body.api_key_env, known_limit=body.known_limit,
        )
    except KeyError:
        raise HTTPException(404, "슬롯을 찾을 수 없습니다") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return _slot_view(services, slot)


@router.get("/config")
async def get_config(request: Request) -> dict:
    return {
        "stall_threshold": _services(request).config.stall_threshold(),
        "providers": list(PROVIDER_IDS),
    }


@router.put("/config")
async def update_config(body: UpdateConfigBody, request: Request) -> dict:
    _services(request).config.set_stall_threshold(body.stall_threshold)
    return await get_config(request)
