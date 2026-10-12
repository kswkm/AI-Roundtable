"""실제 API 연결 확인. 무료 제공량을 아끼기 위해 사용자가 직접 실행할 때만 동작한다.

실행: uv run python -m roundtable.smoke
"""

import asyncio
import os

import httpx
from dotenv import load_dotenv

from roundtable.debate.caller import ProviderFactory
from roundtable.providers.base import ChatMessage, ProviderFailure
from roundtable.providers.registry import build_provider
from roundtable.slots.service import SlotService
from roundtable.storage.db import init_db, make_engine

SMOKE_PROMPT = [ChatMessage("user", 'Reply with only this JSON object: {"ok": true}')]


async def run_smoke(slots: SlotService, provider_factory: ProviderFactory) -> list[str]:
    lines = []
    for slot in slots.list():
        label = f"[{slot.id}] {slot.provider} ({slot.model})"
        api_key = slots.api_key(slot)
        if api_key is None:
            lines.append(f"{label}: 건너뜀 — {slot.api_key_env} 없음")
            continue
        try:
            response = await provider_factory(slot, api_key).complete(SMOKE_PROMPT, {"type": "object"})
        except ProviderFailure as failure:
            lines.append(f"{label}: 실패 — {type(failure).__name__}: {failure.message}")
            continue
        except Exception as failure:  # 한 슬롯의 예기치 않은 오류가 나머지 슬롯을 막지 않도록
            lines.append(f"{label}: 실패 — {type(failure).__name__}: {failure}")
            continue
        lines.append(
            f"{label}: 성공 — {response.text.strip()[:60]} "
            f"(입력 {response.input_tokens} / 출력 {response.output_tokens} 토큰)"
        )
    return lines


def main() -> None:
    load_dotenv()
    engine = make_engine(os.environ.get("ROUNDTABLE_DB", "sqlite:///./roundtable.db"))
    init_db(engine)
    slots = SlotService(engine, environ=os.environ)
    slots.seed_defaults()

    async def _run() -> list[str]:
        async with httpx.AsyncClient() as client:
            return await run_smoke(
                slots, lambda slot, key: build_provider(slot.provider, slot.model, key, client)
            )

    for line in asyncio.run(_run()):
        print(line)


if __name__ == "__main__":
    main()
