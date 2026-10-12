import asyncio

import httpx
import pytest

from fakes import ALL_KEYS, ScriptedProvider, eval_json, final_json, no_sleep, op_json
from roundtable.api.app import create_app
from roundtable.api.services import build_services
from roundtable.debate.orchestrator import build_participants
from roundtable.providers.base import CreditsExhausted
from roundtable.slots.service import JUDGE_SLOT_ID


class Api:
    def __init__(self, tmp_path, environ=ALL_KEYS):
        self.fakes: dict[int, ScriptedProvider] = {}
        self.services = build_services(
            f"sqlite:///{tmp_path / 'api.db'}",
            environ=environ,
            provider_factory=lambda slot, key: self.fakes[slot.id],
            sleep=no_sleep,
        )
        self.app = create_app(self.services)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test")


@pytest.fixture
def api(tmp_path):
    return Api(tmp_path)


async def test_create_debate_runs_to_completion(api):
    api.fakes.update({1: ScriptedProvider([op_json("찬성")]), 2: ScriptedProvider([op_json("찬성")]),
                      JUDGE_SLOT_ID: ScriptedProvider([eval_json("converged"), final_json()])})
    async with api.client() as client:
        response = await client.post("/debates", json={"question": "  자동 배포해도 되는가?  ", "slot_ids": [1, 2]})
        assert response.status_code == 201
        debate_id = response.json()["id"]
        await api.services.orchestrator.wait(debate_id)

        detail = (await client.get(f"/debates/{debate_id}")).json()
        listing = (await client.get("/debates")).json()

    assert detail["question"] == "자동 배포해도 되는가?"
    assert detail["status"] == "converged"
    assert detail["result"]["final_opinion"] == "통합 의견"
    assert [p["label"] for p in detail["participants"]] == ["A", "B"]
    assert len(detail["rounds"][0]["messages"]) == 2
    assert listing[0]["id"] == debate_id and listing[0]["grade"] == "consensus"


@pytest.mark.parametrize(
    "body",
    [
        {"question": "   ", "slot_ids": [1]},
        {"question": "가" * 4001, "slot_ids": [1]},
        {"question": "q", "slot_ids": [1, 1]},
        {"question": "q", "slot_ids": [5]},
        {"question": "q", "slot_ids": []},
        {"question": "q", "slot_ids": [1, 2, 3, 4, 4]},
    ],
)
async def test_create_rejects_invalid_input(api, body):
    async with api.client() as client:
        assert (await client.post("/debates", json=body)).status_code == 422


async def test_create_rejects_exhausted_participant(api):
    api.services.slots.mark_failure(2, CreditsExhausted("credit balance is too low"))
    async with api.client() as client:
        response = await client.post("/debates", json={"question": "q", "slot_ids": [1, 2]})
    assert response.status_code == 409
    assert "anthropic" in response.json()["detail"]
    assert "credit balance is too low" in response.json()["detail"]


async def test_create_rejects_exhausted_judge(api):
    api.services.slots.mark_failure(JUDGE_SLOT_ID, CreditsExhausted("x"))
    async with api.client() as client:
        response = await client.post("/debates", json={"question": "q", "slot_ids": [1]})
    assert response.status_code == 409
    assert "판정 AI" in response.json()["detail"]


async def test_create_rejects_missing_key(tmp_path):
    api = Api(tmp_path, environ={k: v for k, v in ALL_KEYS.items() if k != "XAI_API_KEY"})
    async with api.client() as client:
        response = await client.post("/debates", json={"question": "q", "slot_ids": [4]})
    assert response.status_code == 409
    assert "XAI_API_KEY" in response.json()["detail"]


async def test_get_unknown_debate_is_404(api):
    async with api.client() as client:
        assert (await client.get("/debates/999")).status_code == 404
        assert (await client.get("/debates/999/events")).status_code == 404


async def test_sse_streams_events_in_order(api):
    services = api.services
    debate_id = services.store.create_debate("질문", build_participants([services.slots.get(1)]), 2)
    api.fakes.update({1: ScriptedProvider([op_json("찬성합니다")]),
                      JUDGE_SLOT_ID: ScriptedProvider([eval_json("converged"), final_json()])})
    async with api.client() as client:
        request = asyncio.create_task(client.get(f"/debates/{debate_id}/events"))
        for _ in range(200):
            if services.bus.subscriber_count(debate_id):
                break
            await asyncio.sleep(0.01)
        services.orchestrator.start(debate_id)
        response = await request

    assert response.headers["content-type"].startswith("text/event-stream")
    types = [line.removeprefix("event: ") for line in response.text.splitlines() if line.startswith("event: ")]
    assert types == ["round_started", "message", "judge_evaluated", "finished"]
    assert "찬성합니다" in response.text  # 한국어가 이스케이프되지 않음
    assert services.bus.subscriber_count(debate_id) == 0


async def test_sse_for_finished_debate_sends_status_only(api):
    services = api.services
    debate_id = services.store.create_debate("q", build_participants([services.slots.get(1)]), 2)
    services.store.update(debate_id, status="converged")
    async with api.client() as client:
        response = await client.get(f"/debates/{debate_id}/events")
    assert "event: status" in response.text
    assert '"converged"' in response.text


async def test_stop_requires_running_debate(api, monkeypatch):
    services = api.services
    debate_id = services.store.create_debate("q", build_participants([services.slots.get(1)]), 2)
    async with api.client() as client:
        assert (await client.post(f"/debates/{debate_id}/stop")).status_code == 409
        requested = []
        monkeypatch.setattr(services.orchestrator, "is_running", lambda _id: True)
        monkeypatch.setattr(services.orchestrator, "request_stop", requested.append)
        response = await client.post(f"/debates/{debate_id}/stop")
    assert response.status_code == 202
    assert requested == [debate_id]


async def test_resume_paused_debate(api):
    services = api.services
    debate_id = services.store.create_debate("q", build_participants([services.slots.get(1)]), 2)
    services.store.update(debate_id, status="paused", pause_reason="판정 AI 무료 크레딧 소진")
    api.fakes.update({1: ScriptedProvider([op_json("A")]),
                      JUDGE_SLOT_ID: ScriptedProvider([eval_json("converged"), final_json()])})
    async with api.client() as client:
        response = await client.post(f"/debates/{debate_id}/resume")
        assert response.status_code == 202
        await services.orchestrator.wait(debate_id)
        assert (await client.post(f"/debates/{debate_id}/resume")).status_code == 409
    assert services.store.get(debate_id).status == "converged"


async def test_resume_rejects_when_judge_exhausted(api):
    services = api.services
    debate_id = services.store.create_debate("q", build_participants([services.slots.get(1)]), 2)
    services.store.update(debate_id, status="paused")
    services.slots.mark_failure(JUDGE_SLOT_ID, CreditsExhausted("x"))
    async with api.client() as client:
        response = await client.post(f"/debates/{debate_id}/resume")
    assert response.status_code == 409
    assert "판정 AI" in response.json()["detail"]


async def test_slots_list_and_update(api):
    async with api.client() as client:
        slots = (await client.get("/slots")).json()
        assert [s["id"] for s in slots] == [1, 2, 3, 4, 5]
        assert slots[0]["key_present"] is True
        assert slots[0]["usage"] == {"today_requests": 0, "today_tokens": 0, "total_requests": 0, "total_tokens": 0}
        assert slots[0]["usage_estimate"] is None

        response = await client.put("/slots/2", json={
            "provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct:free",
            "api_key_env": "OPENROUTER_API_KEY", "known_limit": {"requests_per_day": 50},
        })
        assert response.status_code == 200
        updated = response.json()
        assert (updated["provider"], updated["status"], updated["key_present"]) == ("openrouter", "available", False)
        assert updated["usage_estimate"] == 0.0

        assert (await client.put("/slots/2", json={"provider": "nope", "model": "m", "api_key_env": "X"})).status_code == 422
        assert (await client.put("/slots/2", json={"provider": "openai", "model": "m", "api_key_env": "bad-name"})).status_code == 422
        assert (await client.put("/slots/9", json={"provider": "openai", "model": "m", "api_key_env": "OPENAI_API_KEY"})).status_code == 404


async def test_config_get_and_update_controls_new_debates(api):
    api.fakes.update({1: ScriptedProvider([op_json("A")]),
                      JUDGE_SLOT_ID: ScriptedProvider([eval_json("converged"), final_json()])})
    async with api.client() as client:
        config = (await client.get("/config")).json()
        assert config["stall_threshold"] == 2
        assert "openrouter" in config["providers"]
        assert (await client.put("/config", json={"stall_threshold": 3})).json()["stall_threshold"] == 3
        assert (await client.put("/config", json={"stall_threshold": 0})).status_code == 422
        debate_id = (await client.post("/debates", json={"question": "q", "slot_ids": [1]})).json()["id"]
        await api.services.orchestrator.wait(debate_id)
    assert api.services.store.get(debate_id).stall_threshold == 3


async def test_build_services_marks_running_debates_interrupted(tmp_path):
    first = Api(tmp_path)
    debate_id = first.services.store.create_debate("q", [], 2)
    second = Api(tmp_path)  # 같은 DB로 서버 재시작을 흉내 낸다
    assert second.services.store.get(debate_id).status == "interrupted"


async def test_validation_errors_are_korean(api):
    async with api.client() as client:
        long_q = await client.post("/debates", json={"question": "가" * 4001, "slot_ids": [1]})
        blank = await client.post("/debates", json={"question": "  ", "slot_ids": [1]})
        dup = await client.post("/debates", json={"question": "q", "slot_ids": [1, 1]})
    for response in (long_q, blank, dup):
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, str)
        assert "String should" not in detail and "Value error" not in detail
    assert "질문을 입력하세요" in blank.json()["detail"]
    assert "question" in long_q.json()["detail"]


async def test_slot_key_env_must_end_with_api_key(api):
    body = {"provider": "openai", "model": "m"}
    async with api.client() as client:
        bad = await client.put("/slots/1", json={**body, "api_key_env": "AWS_SECRET_ACCESS_KEY"})
        good = await client.put("/slots/1", json={**body, "api_key_env": "MY_OPENAI_API_KEY"})
    assert bad.status_code == 422
    assert "api_key_env" in bad.json()["detail"]
    assert good.status_code == 200


async def test_rejects_untrusted_host_header(api):
    async with api.client() as client:
        rebound = await client.get("/slots", headers={"Host": "evil.example"})
        normal = await client.get("/slots")

    assert rebound.status_code == 400
    assert normal.status_code == 200
