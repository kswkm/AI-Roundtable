from fakes import ScriptedProvider
from roundtable.providers.base import CreditsExhausted
from roundtable.slots.service import SlotService
from roundtable.smoke import run_smoke
from roundtable.storage.db import init_db, make_engine


async def test_run_smoke_reports_each_slot(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    slots = SlotService(engine, environ={"OPENAI_API_KEY": "k", "ANTHROPIC_API_KEY": "k"})
    slots.seed_defaults()
    fakes = {1: ScriptedProvider(['{"ok": true}']), 2: ScriptedProvider([CreditsExhausted("credit balance is too low")])}

    lines = await run_smoke(slots, lambda slot, key: fakes[slot.id])

    assert len(lines) == 5
    assert lines[0].startswith("[1] openai (gpt-4o-mini): 성공")
    assert "입력 10 / 출력 5 토큰" in lines[0]
    assert lines[1] == "[2] anthropic (claude-haiku-4-5): 실패 — CreditsExhausted: credit balance is too low"
    assert lines[2] == "[3] gemini (gemini-2.5-flash): 건너뜀 — GEMINI_API_KEY 없음"
    assert slots.get(2).status == "available"  # smoke는 슬롯 상태를 바꾸지 않는다


async def test_run_smoke_continues_after_unexpected_error(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    slots = SlotService(engine, environ={"OPENAI_API_KEY": "k", "ANTHROPIC_API_KEY": "k"})
    slots.seed_defaults()
    fakes = {1: ScriptedProvider([RuntimeError("boom")]), 2: ScriptedProvider(['{"ok": true}'])}

    lines = await run_smoke(slots, lambda slot, key: fakes[slot.id])

    assert lines[0] == "[1] openai (gpt-4o-mini): 실패 — RuntimeError: boom"
    assert lines[1].startswith("[2] anthropic (claude-haiku-4-5): 성공")
    assert len(lines) == 5
