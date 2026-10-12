# AI-Roundtable 백엔드 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 여러 AI가 독립 의견 → 상호 검토 → 판정 AI 통합을 거쳐 하나의 최종 의견을 만드는 토론 백엔드(FastAPI + SQLite)를 만든다. 무료 제공량 소진을 감지·표시하고, 끝나지 않은 토론을 이어할 수 있어야 한다.

**Architecture:** `providers`(회사별 HTTP 연결, 오류를 4종으로 분류) → `SlotCaller`(슬롯 상태 확인, 재시도, 사용량 기록, JSON 파싱) → `Orchestrator`(라운드 진행, 판정, 탈락·일시정지·이어하기) → `api`(HTTP + SSE). 모든 상태는 SQLite에 즉시 저장한다. 오케스트레이터는 Provider 인터페이스에만 의존하므로 가짜 Provider로 전체 흐름을 테스트한다.

**Tech Stack:** Python 3.13, uv, FastAPI, uvicorn, httpx(회사 API 직접 호출, 테스트는 `httpx.MockTransport`), SQLModel(SQLite), pydantic v2, python-dotenv, tzdata, pytest, pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-10-12-ai-roundtable-design.md`

**범위:** 이 계획은 백엔드만 다룬다. 프론트엔드(Next.js 화면 4개)는 이 계획이 끝난 뒤 별도 계획 `2026-10-12-ai-roundtable-frontend.md`로 작성한다.

## Global Constraints

- 추가 비용 0원: **자동 테스트는 실제 API를 절대 호출하지 않는다.** 가짜 Provider(`tests/fakes.py`) 또는 `httpx.MockTransport`만 쓴다.
- API 키는 `backend/.env`에만 둔다. `.env`와 `*.db`는 Git에 커밋하지 않는다.
- 모든 명령은 `backend/` 디렉터리에서 `uv run ...`으로 실행한다.
- 시간 값은 앱 전체에서 **naive UTC**(`roundtable.clock.utcnow()`)로 통일한다. SQLite가 시간대를 저장하지 않기 때문이다.
- 사용자에게 보이는 문자열(오류 사유, 탈락 사유, HTTP 오류 메시지)은 한국어로 쓴다.
- 정체 기준 기본값 2(설정 범위 1~10), 호출당 시간 제한 120초, `ProviderError` 최대 3회 시도(대기 1초, 2초), 형식 위반 시 1회 재요청.
- 참여 슬롯 id는 1~4, 판정 슬롯 id는 5.
- 모든 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 줄을 붙인다(예: `git commit -m "feat: ..." -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`).

### 스펙 대비 구현 결정 (스펙이 열어 둔 세부)

- 패키지 경로: 스펙의 `backend/providers/...`는 `backend/roundtable/providers/...`로 둔다(설치 가능한 패키지 이름 `roundtable`).
- `debates` 테이블에 `dropouts`(JSON)와 `pending_status`(최종 정리 직전 판정 AI가 소진됐을 때 끝날 상태)를 추가한다.
- 정체 기준 설정 저장용 `app_config` 테이블과 `GET/PUT /config` 엔드포인트를 추가한다(스펙 5.5 설정 화면 요구).
- SSE에 `status` 이벤트를 추가한다. 이미 끝난 토론에 연결하면 현재 상태 하나만 보내고 닫는다.
- 속도 제한은 최대 6회까지 기다린 뒤에도 계속되면 `ProviderError`로 바꾼다(무한 대기 방지).
- 판정 AI가 `ProviderError`(3회 실패)를 내도 소진과 같이 일시정지한다.
- 사용자 중단은 진행 중인 라운드가 끝난 뒤 적용된다. 일시정지된 토론은 중단 대상이 아니다.
- 모델 기본값(`gpt-4o-mini`, `claude-haiku-4-5`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, `grok-3-mini`)은 설정에서 바꿀 수 있는 초기값이다. 실제 사용 가능 여부는 Task 12의 `smoke` 명령으로 확인한다.

## Review Focus

1. 모델이 JSON을 코드 펜스(```json)나 설명 문장으로 감싸서 답함 → 정상 파싱되어야 한다. (Task 8 `test_parse_handles_fenced_and_wrapped_json`)
2. 모델이 확신도를 백분율(예: 85)로 답함 → 0.85로 받아들여야 하고, 150 같은 값은 형식 위반이어야 한다. (Task 8 `test_confidence_percent_is_normalized`)
3. 공백만 있는 질문, 4000자 초과 질문, 같은 슬롯 중복 선택, 판정 슬롯(5번)을 참여자로 선택 → 422로 거절해야 한다. (Task 11 `test_create_rejects_invalid_input`)
4. Gemini가 안전 필터 등으로 `candidates` 없이 200을 돌려줌 → 빈 문자열로 성공 처리하지 말고 `ProviderError`(재시도 대상)여야 한다. (Task 4 `test_empty_candidates_is_provider_error`)
5. 한국어 발언이 SSE로 전달될 때 `\uXXXX`로 이스케이프되지 않고 UTF-8 그대로 전달되어야 한다. (Task 11 `test_sse_streams_events_in_order`)

---

## File Structure

```
.gitignore                          # .env, *.db, .venv, __pycache__, node_modules, .next
backend/
├── pyproject.toml
├── .env.example
├── README.md
├── roundtable/
│   ├── __init__.py
│   ├── clock.py                    # utcnow()
│   ├── main.py                     # 실제 실행용 앱 (uvicorn 진입점)
│   ├── smoke.py                    # 실제 API 연결 확인 명령 (수동)
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py                 # ChatMessage, ProviderResponse, 오류 4종, Provider 프로토콜
│   │   ├── _http.py                # post_json, error_message, retry_after_seconds
│   │   ├── openai_compat.py        # GPT, Grok, OpenRouter, Groq
│   │   ├── anthropic.py            # Claude
│   │   ├── gemini.py               # Gemini
│   │   └── registry.py             # PROVIDER_IDS, build_provider
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── models.py               # SQLModel 테이블 6개
│   │   ├── db.py                   # make_engine, init_db
│   │   ├── store.py                # DebateStore
│   │   └── config.py               # ConfigStore (정체 기준)
│   ├── slots/
│   │   ├── __init__.py
│   │   └── service.py              # SlotService, 기본 슬롯
│   ├── usage/
│   │   ├── __init__.py
│   │   └── recorder.py             # UsageRecorder
│   ├── debate/
│   │   ├── __init__.py
│   │   ├── schemas.py              # Opinion, JudgeEval, FinalResult..., parse_json_model
│   │   ├── prompts.py              # 프롬프트 생성 함수
│   │   ├── caller.py               # SlotCaller, SlotUnavailable, CallResult
│   │   ├── events.py               # EventBus
│   │   └── orchestrator.py         # Orchestrator, build_participants
│   └── api/
│       ├── __init__.py
│       ├── services.py             # Services, build_services
│       ├── routes.py               # 엔드포인트
│       └── app.py                  # create_app
└── tests/
    ├── helpers.py                  # load_fixture, mock_client
    ├── fakes.py                    # ScriptedProvider, JSON 응답 생성기
    ├── fixtures/                   # 회사별 실제 오류 응답 예시
    └── test_*.py
```

---

### Task 1: 프로젝트 뼈대 + Provider 기본 타입 + HTTP 헬퍼

**Files:**
- Create: `.gitignore`, `backend/pyproject.toml`, `backend/.env.example`
- Create: `backend/roundtable/__init__.py`, `backend/roundtable/clock.py`
- Create: `backend/roundtable/providers/__init__.py`, `backend/roundtable/providers/base.py`, `backend/roundtable/providers/_http.py`
- Create: `backend/tests/helpers.py`
- Test: `backend/tests/test_http.py`

**Interfaces:**
- Produces:
  - `roundtable.clock.utcnow() -> datetime` (naive UTC)
  - `roundtable.providers.base`: `ChatMessage(role: str, content: str)`, `ProviderResponse(text: str, input_tokens: int, output_tokens: int)`, `ProviderFailure(message)`, `RateLimited(message, retry_after: float | None)`, `DailyQuotaExhausted(message, reset_at: datetime | None)`, `CreditsExhausted(message)`, `ProviderError(message)`, `Provider` 프로토콜(`name: str`, `model: str`, `async complete(messages: list[ChatMessage], response_schema: dict | None = None) -> ProviderResponse`)
  - `roundtable.providers._http`: `TIMEOUT_SECONDS = 120.0`, `async post_json(client, url, headers, body) -> httpx.Response`, `error_message(response) -> str`, `retry_after_seconds(response) -> float | None`
  - `tests/helpers.py`: `load_fixture(name) -> dict`, `mock_client(status, payload=None, *, headers=None, text=None, capture=None) -> httpx.AsyncClient`

- [ ] **Step 1: 뼈대 파일 작성**

`.gitignore` (저장소 루트):

```gitignore
.env
*.db
.venv/
__pycache__/
.pytest_cache/
node_modules/
.next/
```

`backend/pyproject.toml`:

```toml
[project]
name = "roundtable"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "httpx>=0.27",
  "sqlmodel>=0.0.22",
  "pydantic>=2.8",
  "python-dotenv>=1.0",
  "tzdata>=2024.1",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.24"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["roundtable"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]
```

`backend/.env.example`:

```dotenv
# 각 회사 콘솔에서 발급한 무료 API 키를 넣으세요. 이 파일을 .env로 복사해서 사용합니다.
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GEMINI_API_KEY=
XAI_API_KEY=
# 슬롯을 무료 대체 모델로 바꿀 때 사용
OPENROUTER_API_KEY=
GROQ_API_KEY=
# ROUNDTABLE_DB=sqlite:///./roundtable.db
```

`backend/roundtable/__init__.py`, `backend/roundtable/providers/__init__.py`: 빈 파일.

`backend/roundtable/clock.py`:

```python
from datetime import UTC, datetime


def utcnow() -> datetime:
    """naive UTC. SQLite가 시간대를 저장하지 않으므로 앱 전체에서 naive UTC로 통일한다."""
    return datetime.now(UTC).replace(tzinfo=None)
```

- [ ] **Step 2: 의존성 설치**

Run: `cd backend && uv sync`
Expected: `.venv/`와 `uv.lock`이 생성되고 오류 없이 끝난다.

- [ ] **Step 3: 실패하는 테스트 작성**

`backend/tests/helpers.py`:

```python
import json
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def mock_client(
    status: int,
    payload: dict | None = None,
    *,
    headers: dict[str, str] | None = None,
    text: str | None = None,
    capture: list[httpx.Request] | None = None,
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        if text is not None:
            return httpx.Response(status, text=text, headers=headers)
        return httpx.Response(status, json=payload, headers=headers)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))
```

`backend/tests/test_http.py`:

```python
import httpx
import pytest

from roundtable.providers._http import error_message, post_json, retry_after_seconds
from roundtable.providers.base import DailyQuotaExhausted, ProviderError, RateLimited


def client_with(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_post_json_wraps_network_error():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    async with client_with(handler) as client:
        with pytest.raises(ProviderError, match="네트워크 오류"):
            await post_json(client, "https://example.test/x", {}, {})


async def test_post_json_wraps_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    async with client_with(handler) as client:
        with pytest.raises(ProviderError, match="시간 초과"):
            await post_json(client, "https://example.test/x", {}, {})


async def test_post_json_sends_json_body_and_headers():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    async with client_with(handler) as client:
        response = await post_json(client, "https://example.test/x", {"X-Key": "k"}, {"a": 1})

    assert response.status_code == 200
    assert seen[0].headers["x-key"] == "k"
    assert seen[0].content == b'{"a":1}' or seen[0].content == b'{"a": 1}'


def test_error_message_reads_nested_error():
    assert error_message(httpx.Response(429, json={"error": {"message": "slow down"}})) == "slow down"


def test_error_message_reads_string_error():
    assert error_message(httpx.Response(400, json={"error": "bad"})) == "bad"


def test_error_message_falls_back_to_text():
    assert error_message(httpx.Response(500, text="Internal Server Error")) == "Internal Server Error"


def test_retry_after_seconds():
    assert retry_after_seconds(httpx.Response(429, headers={"retry-after": "12"})) == 12.0
    assert retry_after_seconds(httpx.Response(429)) is None
    assert retry_after_seconds(httpx.Response(429, headers={"retry-after": "soon"})) is None


def test_failures_keep_their_details():
    assert RateLimited("m", 3.0).retry_after == 3.0
    assert RateLimited("m").message == "m"
    assert DailyQuotaExhausted("d").reset_at is None
```

- [ ] **Step 4: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_http.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.providers._http'`

- [ ] **Step 5: 구현**

`backend/roundtable/providers/base.py`:

```python
"""모든 모델 연결 모듈이 따르는 공통 인터페이스와 오류 종류."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    input_tokens: int
    output_tokens: int


class ProviderFailure(Exception):
    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


class RateLimited(ProviderFailure):
    """일시적 속도 제한. retry_after 초 뒤 다시 시도할 수 있다."""

    def __init__(self, message: str = "", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class DailyQuotaExhausted(ProviderFailure):
    """일일 한도 소진. reset_at(naive UTC)에 다시 쓸 수 있다."""

    def __init__(self, message: str = "", reset_at: datetime | None = None) -> None:
        super().__init__(message)
        self.reset_at = reset_at


class CreditsExhausted(ProviderFailure):
    """체험 크레딧 소진. 자동으로 풀리지 않는다."""


class ProviderError(ProviderFailure):
    """네트워크 오류, 서버 오류, 시간 초과, 해석할 수 없는 응답."""


class Provider(Protocol):
    name: str
    model: str

    async def complete(
        self, messages: list[ChatMessage], response_schema: dict | None = None
    ) -> ProviderResponse: ...
```

`backend/roundtable/providers/_http.py`:

```python
import httpx

from roundtable.providers.base import ProviderError

TIMEOUT_SECONDS = 120.0


async def post_json(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], body: dict
) -> httpx.Response:
    try:
        return await client.post(url, headers=headers, json=body, timeout=TIMEOUT_SECONDS)
    except httpx.TimeoutException as exc:
        raise ProviderError(f"시간 초과 ({TIMEOUT_SECONDS:.0f}초)") from exc
    except httpx.HTTPError as exc:
        raise ProviderError(f"네트워크 오류: {exc}") from exc


def error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:500]
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    if isinstance(error, str):
        return error
    return str(data)[:500]


def retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_http.py -v`
Expected: PASS (8 passed)

- [ ] **Step 7: 커밋**

```bash
git add .gitignore backend/pyproject.toml backend/uv.lock backend/.env.example backend/roundtable backend/tests
git commit -m "feat: scaffold backend with provider base types and HTTP helper" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: OpenAI 호환 Provider (GPT, Grok, OpenRouter, Groq)

**Files:**
- Create: `backend/roundtable/providers/openai_compat.py`
- Create: `backend/tests/fixtures/openai_insufficient_quota.json`, `openai_rate_limit.json`, `openrouter_402.json`, `xai_no_credits.json`
- Test: `backend/tests/test_openai_compat.py`

**Interfaces:**
- Consumes: Task 1의 `ChatMessage`, `ProviderResponse`, 오류 4종, `post_json`, `error_message`, `retry_after_seconds`
- Produces: `OpenAICompatProvider(name: str, model: str, api_key: str, base_url: str, client: httpx.AsyncClient)` — 속성 `name`, `model`, `base_url`; `classify_openai_error(response) -> ProviderFailure`

- [ ] **Step 1: 오류 응답 예시 파일 작성**

`backend/tests/fixtures/openai_insufficient_quota.json`:

```json
{"error": {"message": "You exceeded your current quota, please check your plan and billing details.", "type": "insufficient_quota", "param": null, "code": "insufficient_quota"}}
```

`backend/tests/fixtures/openai_rate_limit.json`:

```json
{"error": {"message": "Rate limit reached for gpt-4o-mini on requests per min (RPM): Limit 3, Used 3, Requested 1.", "type": "requests", "param": null, "code": "rate_limit_exceeded"}}
```

`backend/tests/fixtures/openrouter_402.json`:

```json
{"error": {"message": "Insufficient credits. Add more using https://openrouter.ai/credits", "code": 402}}
```

`backend/tests/fixtures/xai_no_credits.json`:

```json
{"error": "Your team has either used all available credits or reached its monthly spending limit. To continue making API requests, please purchase more credits or raise your spending limit."}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/test_openai_compat.py`:

```python
import json

import pytest

from helpers import load_fixture, mock_client
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    ProviderError,
    ProviderResponse,
    RateLimited,
)
from roundtable.providers.openai_compat import OpenAICompatProvider

MESSAGES = [ChatMessage("system", "sys"), ChatMessage("user", "hi, answer in JSON")]


def make(client):
    return OpenAICompatProvider("openai", "gpt-4o-mini", "sk-test", "https://api.openai.com/v1", client)


async def test_success_returns_text_and_usage():
    captured = []
    payload = {
        "choices": [{"message": {"content": '{"a": 1}'}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 3},
    }
    async with mock_client(200, payload, capture=captured) as client:
        response = await make(client).complete(MESSAGES, {"type": "object"})

    assert response == ProviderResponse('{"a": 1}', 12, 3)
    request = captured[0]
    assert str(request.url) == "https://api.openai.com/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer sk-test"
    body = json.loads(request.content)
    assert body["model"] == "gpt-4o-mini"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi, answer in JSON"},
    ]


async def test_no_schema_means_no_json_mode():
    captured = []
    payload = {"choices": [{"message": {"content": "ok"}}], "usage": {}}
    async with mock_client(200, payload, capture=captured) as client:
        response = await make(client).complete(MESSAGES)
    assert "response_format" not in json.loads(captured[0].content)
    assert response == ProviderResponse("ok", 0, 0)


async def test_insufficient_quota_is_credits_exhausted():
    async with mock_client(429, load_fixture("openai_insufficient_quota.json")) as client:
        with pytest.raises(CreditsExhausted, match="exceeded your current quota"):
            await make(client).complete(MESSAGES)


async def test_rate_limit_is_rate_limited_with_retry_after():
    async with mock_client(429, load_fixture("openai_rate_limit.json"), headers={"retry-after": "7"}) as client:
        with pytest.raises(RateLimited) as info:
            await make(client).complete(MESSAGES)
    assert info.value.retry_after == 7.0


async def test_openrouter_402_is_credits_exhausted():
    async with mock_client(402, load_fixture("openrouter_402.json")) as client:
        with pytest.raises(CreditsExhausted):
            await make(client).complete(MESSAGES)


async def test_xai_no_credits_is_credits_exhausted():
    async with mock_client(429, load_fixture("xai_no_credits.json")) as client:
        with pytest.raises(CreditsExhausted, match="used all available credits"):
            await make(client).complete(MESSAGES)


async def test_server_error_is_provider_error():
    async with mock_client(500, text="Internal Server Error") as client:
        with pytest.raises(ProviderError, match="HTTP 500"):
            await make(client).complete(MESSAGES)


async def test_malformed_success_is_provider_error():
    async with mock_client(200, {"choices": []}) as client:
        with pytest.raises(ProviderError, match="해석할 수 없음"):
            await make(client).complete(MESSAGES)
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_openai_compat.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.providers.openai_compat'`

- [ ] **Step 4: 구현**

`backend/roundtable/providers/openai_compat.py`:

```python
"""OpenAI Chat Completions 호환 API (OpenAI, xAI, OpenRouter, Groq)."""

import httpx

from roundtable.providers._http import error_message, post_json, retry_after_seconds
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    ProviderError,
    ProviderFailure,
    ProviderResponse,
    RateLimited,
)

CREDIT_KEYWORDS = (
    "insufficient_quota",
    "exceeded your current quota",
    "insufficient credits",
    "available credits",
    "spending limit",
    "billing",
)


class OpenAICompatProvider:
    def __init__(
        self, name: str, model: str, api_key: str, base_url: str, client: httpx.AsyncClient
    ) -> None:
        self.name = name
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    async def complete(
        self, messages: list[ChatMessage], response_schema: dict | None = None
    ) -> ProviderResponse:
        body: dict = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if response_schema is not None:
            body["response_format"] = {"type": "json_object"}
        response = await post_json(
            self._client,
            f"{self.base_url}/chat/completions",
            {"Authorization": f"Bearer {self._api_key}"},
            body,
        )
        if response.status_code != 200:
            raise classify_openai_error(response)
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError("응답 형식을 해석할 수 없음") from exc
        return ProviderResponse(
            text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
        )


def classify_openai_error(response: httpx.Response) -> ProviderFailure:
    status = response.status_code
    message = error_message(response)
    lowered = f"{message} {response.text}".lower()
    if status == 402:
        return CreditsExhausted(message)
    if status in (400, 403, 429) and any(keyword in lowered for keyword in CREDIT_KEYWORDS):
        return CreditsExhausted(message)
    if status == 429:
        return RateLimited(message, retry_after_seconds(response))
    return ProviderError(f"HTTP {status}: {message}")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_openai_compat.py -v`
Expected: PASS (8 passed)

- [ ] **Step 6: 커밋**

```bash
git add backend/roundtable/providers/openai_compat.py backend/tests/test_openai_compat.py backend/tests/fixtures
git commit -m "feat: add OpenAI-compatible provider with error classification" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Anthropic Provider (Claude)

**Files:**
- Create: `backend/roundtable/providers/anthropic.py`
- Create: `backend/tests/fixtures/anthropic_credit_balance.json`, `anthropic_rate_limit.json`, `anthropic_overloaded.json`
- Test: `backend/tests/test_anthropic.py`

**Interfaces:**
- Consumes: Task 1의 타입과 HTTP 헬퍼
- Produces: `AnthropicProvider(model: str, api_key: str, client: httpx.AsyncClient, max_tokens: int = 4096)` — `name == "anthropic"`; `classify_anthropic_error(response) -> ProviderFailure`

- [ ] **Step 1: 오류 응답 예시 파일 작성**

`backend/tests/fixtures/anthropic_credit_balance.json`:

```json
{"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."}}
```

`backend/tests/fixtures/anthropic_rate_limit.json`:

```json
{"type": "error", "error": {"type": "rate_limit_error", "message": "Number of request tokens has exceeded your per-minute rate limit."}}
```

`backend/tests/fixtures/anthropic_overloaded.json`:

```json
{"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/test_anthropic.py`:

```python
import json

import pytest

from helpers import load_fixture, mock_client
from roundtable.providers.anthropic import AnthropicProvider
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    ProviderError,
    ProviderResponse,
    RateLimited,
)

MESSAGES = [
    ChatMessage("system", "sys-1"),
    ChatMessage("system", "sys-2"),
    ChatMessage("user", "question"),
    ChatMessage("assistant", "draft"),
    ChatMessage("user", "fix it"),
]


def make(client):
    return AnthropicProvider("claude-haiku-4-5", "sk-ant-test", client)


async def test_success_joins_text_blocks_and_moves_system_out():
    captured = []
    payload = {
        "content": [{"type": "text", "text": '{"a":'}, {"type": "text", "text": " 1}"}],
        "usage": {"input_tokens": 20, "output_tokens": 4},
    }
    async with mock_client(200, payload, capture=captured) as client:
        response = await make(client).complete(MESSAGES, {"type": "object"})

    assert response == ProviderResponse('{"a": 1}', 20, 4)
    request = captured[0]
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "sk-ant-test"
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body["system"] == "sys-1\n\nsys-2"
    assert body["max_tokens"] == 4096
    assert body["messages"] == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "draft"},
        {"role": "user", "content": "fix it"},
    ]


async def test_low_credit_balance_is_credits_exhausted():
    async with mock_client(400, load_fixture("anthropic_credit_balance.json")) as client:
        with pytest.raises(CreditsExhausted, match="credit balance is too low"):
            await make(client).complete(MESSAGES)


async def test_rate_limit_is_rate_limited():
    async with mock_client(429, load_fixture("anthropic_rate_limit.json"), headers={"retry-after": "20"}) as client:
        with pytest.raises(RateLimited) as info:
            await make(client).complete(MESSAGES)
    assert info.value.retry_after == 20.0


async def test_overloaded_is_provider_error():
    async with mock_client(529, load_fixture("anthropic_overloaded.json")) as client:
        with pytest.raises(ProviderError, match="HTTP 529"):
            await make(client).complete(MESSAGES)


async def test_malformed_success_is_provider_error():
    async with mock_client(200, {"unexpected": True}) as client:
        with pytest.raises(ProviderError, match="해석할 수 없음"):
            await make(client).complete(MESSAGES)
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_anthropic.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.providers.anthropic'`

- [ ] **Step 4: 구현**

`backend/roundtable/providers/anthropic.py`:

```python
"""Anthropic Messages API (Claude). JSON 모드가 없으므로 JSON 형식은 프롬프트로만 요청한다."""

import httpx

from roundtable.providers._http import error_message, post_json, retry_after_seconds
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    ProviderError,
    ProviderFailure,
    ProviderResponse,
    RateLimited,
)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self, model: str, api_key: str, client: httpx.AsyncClient, max_tokens: int = 4096
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client
        self._max_tokens = max_tokens

    async def complete(
        self, messages: list[ChatMessage], response_schema: dict | None = None
    ) -> ProviderResponse:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        body: dict = {
            "model": self.model,
            "max_tokens": self._max_tokens,
            "messages": [
                {"role": m.role, "content": m.content} for m in messages if m.role != "system"
            ],
        }
        if system:
            body["system"] = system
        response = await post_json(
            self._client,
            ANTHROPIC_URL,
            {"x-api-key": self._api_key, "anthropic-version": ANTHROPIC_VERSION},
            body,
        )
        if response.status_code != 200:
            raise classify_anthropic_error(response)
        try:
            data = response.json()
            text = "".join(
                block.get("text", "") for block in data["content"] if block.get("type") == "text"
            )
            usage = data.get("usage") or {}
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProviderError("응답 형식을 해석할 수 없음") from exc
        return ProviderResponse(
            text, int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))
        )


def classify_anthropic_error(response: httpx.Response) -> ProviderFailure:
    status = response.status_code
    message = error_message(response)
    lowered = message.lower()
    if "credit balance" in lowered or "billing" in lowered:
        return CreditsExhausted(message)
    if status == 429:
        return RateLimited(message, retry_after_seconds(response))
    return ProviderError(f"HTTP {status}: {message}")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_anthropic.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: 커밋**

```bash
git add backend/roundtable/providers/anthropic.py backend/tests/test_anthropic.py backend/tests/fixtures
git commit -m "feat: add Anthropic provider with error classification" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Gemini Provider + Provider 레지스트리

**Files:**
- Create: `backend/roundtable/providers/gemini.py`, `backend/roundtable/providers/registry.py`
- Create: `backend/tests/fixtures/gemini_daily_quota.json`, `gemini_minute_quota.json`
- Test: `backend/tests/test_gemini.py`, `backend/tests/test_registry.py`

**Interfaces:**
- Consumes: Task 1~3
- Produces:
  - `GeminiProvider(model: str, api_key: str, client: httpx.AsyncClient, now: Callable[[], datetime] = utcnow)` — `name == "gemini"`
  - `next_pacific_midnight(now: datetime) -> datetime` (입력·출력 모두 naive UTC)
  - `registry.PROVIDER_IDS: tuple[str, ...] == ("openai", "xai", "openrouter", "groq", "anthropic", "gemini")`
  - `registry.OPENAI_COMPAT_BASE_URLS: dict[str, str]`
  - `registry.build_provider(provider: str, model: str, api_key: str, client: httpx.AsyncClient) -> Provider` (알 수 없는 회사면 `ValueError`)

- [ ] **Step 1: 오류 응답 예시 파일 작성**

`backend/tests/fixtures/gemini_daily_quota.json`:

```json
{"error": {"code": 429, "message": "You exceeded your current quota, please check your plan and billing details.", "status": "RESOURCE_EXHAUSTED", "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests", "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash"}, "quotaValue": "250"}]}, {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "32s"}]}}
```

`backend/tests/fixtures/gemini_minute_quota.json`:

```json
{"error": {"code": 429, "message": "You exceeded your current quota, please check your plan and billing details.", "status": "RESOURCE_EXHAUSTED", "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests", "quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "quotaDimensions": {"location": "global", "model": "gemini-2.5-flash"}, "quotaValue": "10"}]}, {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"}]}}
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/test_gemini.py`:

```python
import json
from datetime import datetime

import pytest

from helpers import load_fixture, mock_client
from roundtable.providers.base import (
    ChatMessage,
    DailyQuotaExhausted,
    ProviderError,
    ProviderResponse,
    RateLimited,
)
from roundtable.providers.gemini import GeminiProvider, next_pacific_midnight

MESSAGES = [
    ChatMessage("system", "sys"),
    ChatMessage("user", "question"),
    ChatMessage("assistant", "draft"),
    ChatMessage("user", "fix it"),
]
NOW = datetime(2026, 10, 12, 20, 0)  # naive UTC = 태평양 시간 10월 12일 13:00 (PDT)


def make(client):
    return GeminiProvider("gemini-2.5-flash", "g-test", client, now=lambda: NOW)


async def test_success_maps_roles_and_skips_thought_parts():
    captured = []
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": '{"a": 1}'}]}}
        ],
        "usageMetadata": {"promptTokenCount": 30, "candidatesTokenCount": 6, "thoughtsTokenCount": 4},
    }
    async with mock_client(200, payload, capture=captured) as client:
        response = await make(client).complete(MESSAGES, {"type": "object"})

    assert response == ProviderResponse('{"a": 1}', 30, 10)
    request = captured[0]
    assert str(request.url) == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert request.headers["x-goog-api-key"] == "g-test"
    body = json.loads(request.content)
    assert body["systemInstruction"] == {"parts": [{"text": "sys"}]}
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user"]
    assert body["generationConfig"] == {"responseMimeType": "application/json"}


async def test_daily_quota_is_daily_quota_exhausted_until_pacific_midnight():
    async with mock_client(429, load_fixture("gemini_daily_quota.json")) as client:
        with pytest.raises(DailyQuotaExhausted) as info:
            await make(client).complete(MESSAGES)
    assert info.value.reset_at == datetime(2026, 10, 13, 7, 0)


async def test_minute_quota_is_rate_limited_with_retry_delay():
    async with mock_client(429, load_fixture("gemini_minute_quota.json")) as client:
        with pytest.raises(RateLimited) as info:
            await make(client).complete(MESSAGES)
    assert info.value.retry_after == 17.0


async def test_empty_candidates_is_provider_error():
    payload = {"promptFeedback": {"blockReason": "SAFETY"}, "usageMetadata": {"promptTokenCount": 5}}
    async with mock_client(200, payload) as client:
        with pytest.raises(ProviderError, match="빈 응답"):
            await make(client).complete(MESSAGES)


async def test_server_error_is_provider_error():
    async with mock_client(503, {"error": {"code": 503, "message": "The model is overloaded."}}) as client:
        with pytest.raises(ProviderError, match="HTTP 503"):
            await make(client).complete(MESSAGES)


def test_next_pacific_midnight_handles_standard_time():
    # 2026-12-01 10:00 UTC = 태평양 시간 02:00 (PST, UTC-8) → 다음 자정은 12-02 08:00 UTC
    assert next_pacific_midnight(datetime(2026, 12, 1, 10, 0)) == datetime(2026, 12, 2, 8, 0)
```

`backend/tests/test_registry.py`:

```python
import httpx
import pytest

from roundtable.providers.anthropic import AnthropicProvider
from roundtable.providers.gemini import GeminiProvider
from roundtable.providers.openai_compat import OpenAICompatProvider
from roundtable.providers.registry import PROVIDER_IDS, build_provider


async def test_build_provider_for_each_id():
    async with httpx.AsyncClient() as client:
        xai = build_provider("xai", "grok-3-mini", "k", client)
        assert isinstance(xai, OpenAICompatProvider)
        assert xai.base_url == "https://api.x.ai/v1"
        assert xai.name == "xai"
        assert build_provider("groq", "m", "k", client).base_url == "https://api.groq.com/openai/v1"
        assert isinstance(build_provider("anthropic", "m", "k", client), AnthropicProvider)
        assert isinstance(build_provider("gemini", "m", "k", client), GeminiProvider)


async def test_unknown_provider_raises():
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="알 수 없는 제공 회사"):
            build_provider("nope", "m", "k", client)


def test_provider_ids():
    assert PROVIDER_IDS == ("openai", "xai", "openrouter", "groq", "anthropic", "gemini")
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_gemini.py tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.providers.gemini'`

- [ ] **Step 4: 구현**

`backend/roundtable/providers/gemini.py`:

```python
"""Google Gemini generateContent API. 무료 등급의 일일 한도는 태평양 시간 자정에 초기화된다."""

from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx

from roundtable.clock import utcnow
from roundtable.providers._http import error_message, post_json
from roundtable.providers.base import (
    ChatMessage,
    DailyQuotaExhausted,
    ProviderError,
    ProviderFailure,
    ProviderResponse,
    RateLimited,
)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
PACIFIC = ZoneInfo("America/Los_Angeles")


def next_pacific_midnight(now: datetime) -> datetime:
    local = now.replace(tzinfo=UTC).astimezone(PACIFIC)
    midnight = datetime.combine(local.date() + timedelta(days=1), time(0), tzinfo=PACIFIC)
    return midnight.astimezone(UTC).replace(tzinfo=None)


class GeminiProvider:
    name = "gemini"

    def __init__(
        self,
        model: str,
        api_key: str,
        client: httpx.AsyncClient,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self.model = model
        self._api_key = api_key
        self._client = client
        self._now = now

    async def complete(
        self, messages: list[ChatMessage], response_schema: dict | None = None
    ) -> ProviderResponse:
        system = "\n\n".join(m.content for m in messages if m.role == "system")
        body: dict = {
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
                if m.role != "system"
            ]
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if response_schema is not None:
            body["generationConfig"] = {"responseMimeType": "application/json"}
        response = await post_json(
            self._client,
            GEMINI_URL.format(model=self.model),
            {"x-goog-api-key": self._api_key},
            body,
        )
        if response.status_code != 200:
            raise self._classify(response)
        try:
            data = response.json()
            candidates = data.get("candidates") or []
            usage = data.get("usageMetadata") or {}
        except (ValueError, AttributeError) as exc:
            raise ProviderError("응답 형식을 해석할 수 없음") from exc
        if not candidates:
            raise ProviderError("빈 응답 (안전 필터 등으로 차단되었을 수 있음)")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        output_tokens = int(usage.get("candidatesTokenCount", 0)) + int(
            usage.get("thoughtsTokenCount", 0)
        )
        return ProviderResponse(text, int(usage.get("promptTokenCount", 0)), output_tokens)

    def _classify(self, response: httpx.Response) -> ProviderFailure:
        message = error_message(response)
        if response.status_code != 429:
            return ProviderError(f"HTTP {response.status_code}: {message}")
        try:
            details = response.json().get("error", {}).get("details", [])
        except (ValueError, AttributeError):
            details = []
        quota_ids = [
            violation.get("quotaId", "")
            for detail in details
            for violation in detail.get("violations", [])
        ]
        if any("PerDay" in quota_id for quota_id in quota_ids):
            return DailyQuotaExhausted(message, next_pacific_midnight(self._now()))
        retry_after = None
        for detail in details:
            delay = detail.get("retryDelay")
            if isinstance(delay, str) and delay.endswith("s"):
                try:
                    retry_after = float(delay[:-1])
                except ValueError:
                    pass
        return RateLimited(message, retry_after)
```

`backend/roundtable/providers/registry.py`:

```python
import httpx

from roundtable.providers.anthropic import AnthropicProvider
from roundtable.providers.base import Provider
from roundtable.providers.gemini import GeminiProvider
from roundtable.providers.openai_compat import OpenAICompatProvider

OPENAI_COMPAT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "xai": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
}
PROVIDER_IDS: tuple[str, ...] = (*OPENAI_COMPAT_BASE_URLS, "anthropic", "gemini")


def build_provider(provider: str, model: str, api_key: str, client: httpx.AsyncClient) -> Provider:
    if provider in OPENAI_COMPAT_BASE_URLS:
        return OpenAICompatProvider(
            provider, model, api_key, OPENAI_COMPAT_BASE_URLS[provider], client
        )
    if provider == "anthropic":
        return AnthropicProvider(model, api_key, client)
    if provider == "gemini":
        return GeminiProvider(model, api_key, client)
    raise ValueError(f"알 수 없는 제공 회사: {provider}")
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_gemini.py tests/test_registry.py -v`
Expected: PASS (9 passed)

- [ ] **Step 6: 커밋**

```bash
git add backend/roundtable/providers backend/tests/test_gemini.py backend/tests/test_registry.py backend/tests/fixtures
git commit -m "feat: add Gemini provider and provider registry" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 저장소 (SQLite 테이블, DebateStore, ConfigStore)

**Files:**
- Create: `backend/roundtable/storage/__init__.py` (빈 파일), `models.py`, `db.py`, `store.py`, `config.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Consumes: `roundtable.clock.utcnow`
- Produces:
  - 테이블: `Slot`, `Debate`, `Round`(`debate_round`), `Message`(`debate_message`), `UsageLog`, `AppConfig` (필드는 아래 코드)
  - `make_engine(url: str) -> Engine`, `init_db(engine) -> None`
  - `CompletedRound(number: int, judge_eval: dict | None, contents: dict[str, dict])`
  - `DebateStore(engine)`: `create_debate(question: str, participants: list[dict], stall_threshold: int) -> int`, `get(debate_id) -> Debate | None`, `list_debates() -> list[Debate]`(최신순), `update(debate_id, **fields) -> None`, `add_round(debate_id, number) -> int`, `add_message(round_id, *, label, provider, model, content: dict | None, error: str | None = None, input_tokens=0, output_tokens=0, latency_ms=0) -> int`, `complete_round(round_id, judge_eval: dict | None) -> None`, `completed_rounds(debate_id) -> list[CompletedRound]`, `delete_incomplete_rounds(debate_id) -> None`, `mark_running_as_interrupted() -> int`, `detail(debate_id) -> dict | None`
  - `ConfigStore(engine)`: `stall_threshold() -> int`(기본 2), `set_stall_threshold(value: int) -> None`
  - `participants` 원소 형식: `{"label": "A", "slot_id": 1, "provider": "openai", "model": "gpt-4o-mini"}`
  - `dropouts` 원소 형식: `{"label", "provider", "model", "round": int, "reason": str}`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_store.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.storage'`

- [ ] **Step 3: 구현**

`backend/roundtable/storage/models.py`:

```python
from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from roundtable.clock import utcnow


class Slot(SQLModel, table=True):
    id: int = Field(primary_key=True)  # 1~4 참여, 5 판정
    kind: str  # "participant" | "judge"
    provider: str
    model: str
    api_key_env: str
    status: str = "available"  # "available" | "rate_limited" | "exhausted"
    status_until: datetime | None = None
    status_reason: str | None = None
    known_limit: dict | None = Field(default=None, sa_column=Column(JSON))


class Debate(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str | None = None  # 공개 서비스 확장용
    question: str
    # "running" | "paused" | "converged" | "stalled" | "stopped" | "interrupted"
    status: str = "running"
    grade: str | None = None  # "consensus" | "partial" | "no_consensus"
    result: dict | None = Field(default=None, sa_column=Column(JSON))
    participants: list = Field(default_factory=list, sa_column=Column(JSON))
    dropouts: list = Field(default_factory=list, sa_column=Column(JSON))
    stall_threshold: int = 2
    pending_status: str | None = None
    pause_reason: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    ended_at: datetime | None = None


class Round(SQLModel, table=True):
    __tablename__ = "debate_round"

    id: int | None = Field(default=None, primary_key=True)
    debate_id: int = Field(foreign_key="debate.id", index=True)
    number: int
    judge_eval: dict | None = Field(default=None, sa_column=Column(JSON))
    completed_at: datetime | None = None


class Message(SQLModel, table=True):
    __tablename__ = "debate_message"

    id: int | None = Field(default=None, primary_key=True)
    round_id: int = Field(foreign_key="debate_round.id", index=True)
    label: str
    provider: str
    model: str
    content: dict | None = Field(default=None, sa_column=Column(JSON))
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    error: str | None = None


class UsageLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    provider: str = Field(index=True)
    model: str
    debate_id: int | None = None
    called_at: datetime = Field(default_factory=utcnow, index=True)
    input_tokens: int = 0
    output_tokens: int = 0
    outcome: str  # "ok" | "rate_limited" | "quota" | "credits" | "error"


class AppConfig(SQLModel, table=True):
    key: str = Field(primary_key=True)
    value: str
```

`backend/roundtable/storage/db.py`:

```python
from sqlalchemy import Engine
from sqlmodel import SQLModel, create_engine

from roundtable.storage import models  # noqa: F401  테이블 등록


def make_engine(url: str) -> Engine:
    return create_engine(url, connect_args={"check_same_thread": False})


def init_db(engine: Engine) -> None:
    SQLModel.metadata.create_all(engine)
```

`backend/roundtable/storage/store.py`:

```python
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
    return value.isoformat() if value is not None else None


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
```

`backend/roundtable/storage/config.py`:

```python
from sqlalchemy import Engine
from sqlmodel import Session

from roundtable.storage.models import AppConfig

STALL_THRESHOLD_KEY = "stall_threshold"
DEFAULT_STALL_THRESHOLD = 2


class ConfigStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def stall_threshold(self) -> int:
        with Session(self._engine) as session:
            row = session.get(AppConfig, STALL_THRESHOLD_KEY)
            return int(row.value) if row is not None else DEFAULT_STALL_THRESHOLD

    def set_stall_threshold(self, value: int) -> None:
        with Session(self._engine) as session:
            row = session.get(AppConfig, STALL_THRESHOLD_KEY) or AppConfig(key=STALL_THRESHOLD_KEY, value="")
            row.value = str(value)
            session.add(row)
            session.commit()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_store.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/roundtable/storage backend/tests/test_store.py
git commit -m "feat: add SQLite storage for debates, rounds, messages and config" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 슬롯 서비스 (기본 슬롯, 상태 전환, 자동 해제)

**Files:**
- Create: `backend/roundtable/slots/__init__.py` (빈 파일), `backend/roundtable/slots/service.py`
- Test: `backend/tests/test_slots.py`

**Interfaces:**
- Consumes: `Slot` 테이블, `PROVIDER_IDS`, 오류 4종, `utcnow`
- Produces:
  - 상수: `PARTICIPANT_SLOT_IDS = (1, 2, 3, 4)`, `JUDGE_SLOT_ID = 5`, `DEFAULT_RATE_LIMIT_WAIT = 60.0`, `DEFAULT_SLOTS: list[dict]`
  - `SlotService(engine, now: Callable[[], datetime] = utcnow, environ: Mapping[str, str] = os.environ)`: `seed_defaults() -> None`, `list() -> list[Slot]`, `get(slot_id) -> Slot`(없으면 `KeyError`), `api_key(slot) -> str | None`, `key_present(slot) -> bool`, `is_usable(slot_id) -> bool`, `mark_failure(slot_id, failure: ProviderFailure) -> None`, `mark_ok(slot_id) -> None`, `update(slot_id, *, provider, model, api_key_env, known_limit=None) -> Slot`(알 수 없는 회사면 `ValueError`)
  - `list()`/`get()`은 반환 전에 해제 시각이 지난 상태를 `available`로 되돌린다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_slots.py`:

```python
from datetime import datetime, timedelta

import pytest

from roundtable.providers.base import CreditsExhausted, DailyQuotaExhausted, ProviderError, RateLimited
from roundtable.slots.service import JUDGE_SLOT_ID, SlotService
from roundtable.storage.db import init_db, make_engine

START = datetime(2026, 10, 12, 12, 0)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


def make(tmp_path, environ=None):
    engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    clock = Clock()
    service = SlotService(engine, now=clock, environ=environ if environ is not None else {"OPENAI_API_KEY": "k"})
    service.seed_defaults()
    return service, clock


def test_seed_defaults_creates_five_slots_once(tmp_path):
    service, _ = make(tmp_path)
    service.seed_defaults()
    slots = service.list()
    assert [s.id for s in slots] == [1, 2, 3, 4, 5]
    assert [s.provider for s in slots] == ["openai", "anthropic", "gemini", "xai", "gemini"]
    judge = service.get(JUDGE_SLOT_ID)
    assert (judge.kind, judge.model) == ("judge", "gemini-2.5-flash-lite")
    assert service.get(3).model == "gemini-2.5-flash"
    assert all(s.status == "available" for s in slots)


def test_get_unknown_slot_raises(tmp_path):
    service, _ = make(tmp_path)
    with pytest.raises(KeyError):
        service.get(9)


def test_key_presence(tmp_path):
    service, _ = make(tmp_path, environ={"OPENAI_API_KEY": "k", "ANTHROPIC_API_KEY": ""})
    assert service.api_key(service.get(1)) == "k"
    assert service.key_present(service.get(1)) is True
    assert service.key_present(service.get(2)) is False  # 빈 값은 없는 것으로 본다
    assert service.is_usable(1) is True
    assert service.is_usable(2) is False


def test_rate_limited_auto_releases(tmp_path):
    service, clock = make(tmp_path)
    service.mark_failure(1, RateLimited("slow", 30))
    slot = service.get(1)
    assert (slot.status, slot.status_until, slot.status_reason) == ("rate_limited", START + timedelta(seconds=30), "slow")
    assert service.is_usable(1) is True  # 속도 제한은 기다리면 되므로 사용 가능
    clock.advance(seconds=31)
    assert service.get(1).status == "available"
    assert service.get(1).status_reason is None


def test_rate_limited_without_retry_after_uses_default_wait(tmp_path):
    service, _ = make(tmp_path)
    service.mark_failure(1, RateLimited("slow"))
    assert service.get(1).status_until == START + timedelta(seconds=60)


def test_daily_quota_exhausted_until_reset(tmp_path):
    service, clock = make(tmp_path)
    service.mark_failure(1, DailyQuotaExhausted("day", reset_at=START + timedelta(hours=5)))
    assert service.get(1).status == "exhausted"
    assert service.is_usable(1) is False
    clock.advance(hours=5)
    assert service.get(1).status == "available"


def test_credits_exhausted_never_auto_releases(tmp_path):
    service, clock = make(tmp_path)
    service.mark_failure(1, CreditsExhausted("no credits"))
    clock.advance(days=30)
    slot = service.list()[0]
    assert (slot.status, slot.status_until, slot.status_reason) == ("exhausted", None, "no credits")


def test_provider_error_does_not_change_status(tmp_path):
    service, _ = make(tmp_path)
    service.mark_failure(1, ProviderError("500"))
    assert service.get(1).status == "available"


def test_mark_ok_clears_rate_limit_only(tmp_path):
    service, _ = make(tmp_path)
    service.mark_failure(1, RateLimited("slow", 30))
    service.mark_ok(1)
    assert service.get(1).status == "available"
    service.mark_failure(2, CreditsExhausted("x"))
    service.mark_ok(2)
    assert service.get(2).status == "exhausted"


def test_update_resets_status_and_validates_provider(tmp_path):
    service, _ = make(tmp_path)
    service.mark_failure(2, CreditsExhausted("x"))
    slot = service.update(
        2, provider="openrouter", model="meta-llama/llama-3.3-70b-instruct:free",
        api_key_env="OPENROUTER_API_KEY", known_limit={"requests_per_day": 50},
    )
    assert (slot.provider, slot.status, slot.status_reason) == ("openrouter", "available", None)
    assert service.get(2).known_limit == {"requests_per_day": 50}
    with pytest.raises(ValueError, match="알 수 없는 제공 회사"):
        service.update(2, provider="nope", model="m", api_key_env="X")
    with pytest.raises(KeyError):
        service.update(9, provider="openai", model="m", api_key_env="X")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_slots.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.slots'`

- [ ] **Step 3: 구현**

`backend/roundtable/slots/service.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_slots.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/roundtable/slots backend/tests/test_slots.py
git commit -m "feat: add slot service with quota status transitions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 사용량 기록 (UsageRecorder)

**Files:**
- Create: `backend/roundtable/usage/__init__.py` (빈 파일), `backend/roundtable/usage/recorder.py`
- Test: `backend/tests/test_usage.py`

**Interfaces:**
- Consumes: `UsageLog`, `Slot` 테이블
- Produces: `UsageRecorder(engine, now=utcnow)`: `record(*, provider, model, debate_id: int | None, input_tokens: int, output_tokens: int, outcome: str) -> None`, `summary(provider, model) -> dict[str, int]`(키: `today_requests`, `today_tokens`, `total_requests`, `total_tokens`; 요청 수는 `outcome == "ok"`만 셈, "오늘"은 UTC 날짜), `estimate(slot) -> float | None`(`known_limit["requests_per_day"]` 대비 오늘 요청 비율)

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_usage.py`:

```python
from datetime import datetime, timedelta

from roundtable.storage.db import init_db, make_engine
from roundtable.storage.models import Slot
from roundtable.usage.recorder import UsageRecorder


def make(tmp_path, clock):
    engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
    init_db(engine)
    return UsageRecorder(engine, now=lambda: clock[0])


def test_summary_counts_today_and_total(tmp_path):
    clock = [datetime(2026, 10, 11, 23, 0)]
    usage = make(tmp_path, clock)
    usage.record(provider="gemini", model="f", debate_id=1, input_tokens=10, output_tokens=5, outcome="ok")
    clock[0] = datetime(2026, 10, 12, 9, 0)
    usage.record(provider="gemini", model="f", debate_id=1, input_tokens=10, output_tokens=5, outcome="ok")
    usage.record(provider="gemini", model="f", debate_id=1, input_tokens=20, output_tokens=0, outcome="ok")
    usage.record(provider="gemini", model="f", debate_id=1, input_tokens=0, output_tokens=0, outcome="error")
    usage.record(provider="openai", model="g", debate_id=1, input_tokens=99, output_tokens=99, outcome="ok")

    assert usage.summary("gemini", "f") == {
        "today_requests": 2, "today_tokens": 35, "total_requests": 3, "total_tokens": 50,
    }


def test_estimate_uses_known_daily_limit(tmp_path):
    clock = [datetime(2026, 10, 12, 9, 0)]
    usage = make(tmp_path, clock)
    for _ in range(2):
        usage.record(provider="gemini", model="f", debate_id=None, input_tokens=1, output_tokens=1, outcome="ok")
    with_limit = Slot(id=3, kind="participant", provider="gemini", model="f", api_key_env="K", known_limit={"requests_per_day": 4})
    without_limit = Slot(id=3, kind="participant", provider="gemini", model="f", api_key_env="K")

    assert usage.estimate(with_limit) == 0.5
    assert usage.estimate(without_limit) is None
    clock[0] += timedelta(days=1)
    assert usage.estimate(with_limit) == 0.0
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_usage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.usage'`

- [ ] **Step 3: 구현**

`backend/roundtable/usage/recorder.py`:

```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_usage.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/roundtable/usage backend/tests/test_usage.py
git commit -m "feat: add usage recorder with daily estimates" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: 응답 형식(schemas)과 프롬프트

**Files:**
- Create: `backend/roundtable/debate/__init__.py` (빈 파일), `backend/roundtable/debate/schemas.py`, `backend/roundtable/debate/prompts.py`
- Test: `backend/tests/test_schemas.py`, `backend/tests/test_prompts.py`

**Interfaces:**
- Consumes: `ChatMessage`
- Produces:
  - `Opinion(position: str, reasons: list[str], conditions: list[str] = [], confidence: float)` — 1 < confidence ≤ 100이면 100으로 나눈다
  - `ReviewedOpinion(Opinion)` + `changes: str`, `rebuttals: list[str] = []`
  - `JudgeEval(status: Literal["converged","progressing","stalled"], issues: list[str] = [], draft: str = "")`
  - `Critique(weaknesses: list[str], counterarguments: list[str] = [])`
  - `Dissent(label: str, reason: str)`
  - `FinalResult(final_opinion: str, grade: Literal["consensus","partial","no_consensus"], key_reasons: list[str], dissents: list[Dissent] = [], uncertainties: list[str] = [])`
  - `parse_json_model(text: str, model_cls: type[T]) -> T` (실패 시 `ValueError`)
  - `prompts.json_instruction(model_cls) -> str`, `format_opinion(opinion) -> str`, `opinion_messages(question) -> list[ChatMessage]`, `review_messages(question, own: Opinion, others: dict[str, Opinion], issues: list[str]) -> list[ChatMessage]`, `judge_eval_messages(question, opinions: dict[str, Opinion], previous: dict[str, Opinion] | None) -> list[ChatMessage]`, `critique_messages(question, opinion: Opinion) -> list[ChatMessage]`, `final_messages(question, opinions: dict[str, Opinion], last_eval: JudgeEval | None, end_reason: str) -> list[ChatMessage]`
  - 다른 참여자는 항상 `[참여자 {label}]` 형식으로만 표시하고 회사·모델 이름은 넣지 않는다.

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_schemas.py`:

```python
import pytest

from roundtable.debate.schemas import FinalResult, JudgeEval, Opinion, ReviewedOpinion, parse_json_model

OPINION = '{"position": "찬성", "reasons": ["r"], "conditions": [], "confidence": 0.8}'


def test_parse_plain_json():
    assert parse_json_model(OPINION, Opinion).position == "찬성"


def test_parse_handles_fenced_and_wrapped_json():
    fenced = f"```json\n{OPINION}\n```"
    wrapped = f"제 의견은 다음과 같습니다.\n{OPINION}\n이상입니다."
    assert parse_json_model(fenced, Opinion).confidence == 0.8
    assert parse_json_model(wrapped, Opinion).position == "찬성"


def test_parse_rejects_missing_json_and_missing_fields():
    with pytest.raises(ValueError):
        parse_json_model("JSON이 없습니다", Opinion)
    with pytest.raises(ValueError):
        parse_json_model('{"position": "찬성"}', Opinion)
    with pytest.raises(ValueError):
        parse_json_model('{"position": "찬성", "reasons": [}', Opinion)


def test_confidence_percent_is_normalized():
    assert parse_json_model('{"position": "p", "reasons": [], "confidence": 85}', Opinion).confidence == 0.85
    assert parse_json_model('{"position": "p", "reasons": [], "confidence": 1}', Opinion).confidence == 1.0
    with pytest.raises(ValueError):
        parse_json_model('{"position": "p", "reasons": [], "confidence": 150}', Opinion)


def test_reviewed_opinion_is_an_opinion():
    reviewed = parse_json_model(
        '{"position": "p", "reasons": [], "confidence": 0.5, "changes": "유지", "rebuttals": ["b"]}',
        ReviewedOpinion,
    )
    assert isinstance(reviewed, Opinion)
    assert Opinion.model_validate(reviewed.model_dump()).position == "p"


def test_judge_eval_and_final_result_reject_unknown_values():
    with pytest.raises(ValueError):
        parse_json_model('{"status": "done"}', JudgeEval)
    with pytest.raises(ValueError):
        parse_json_model('{"final_opinion": "x", "grade": "majority", "key_reasons": []}', FinalResult)
```

`backend/tests/test_prompts.py`:

```python
from roundtable.debate import prompts
from roundtable.debate.schemas import JudgeEval, Opinion

A = Opinion(position="POS-A", reasons=["근거-A"], confidence=0.7)
B = Opinion(position="POS-B", reasons=["근거-B"], conditions=["조건-B"], confidence=0.6)


def text(messages):
    return "\n".join(m.content for m in messages)


def test_opinion_messages_contain_only_question():
    messages = prompts.opinion_messages("자동 배포해도 되는가?")
    assert [m.role for m in messages] == ["system", "user"]
    body = text(messages)
    assert "자동 배포해도 되는가?" in body
    assert "독립적인 의견" in body
    assert "JSON" in body
    assert "[참여자" not in body


def test_review_messages_show_others_by_label_and_issues():
    body = text(prompts.review_messages("Q", A, {"B": B}, ["쟁점-1"]))
    assert "POS-A" in body  # 자기 직전 의견
    assert "[참여자 B]" in body and "POS-B" in body and "조건-B" in body
    assert "쟁점-1" in body
    assert "changes" in body


def test_review_messages_without_others_is_single_mode():
    body = text(prompts.review_messages("Q", A, {}, ["약점-1"]))
    assert "[참여자" not in body
    assert "약점-1" in body


def test_judge_eval_messages_forbid_stalled_without_previous():
    first = text(prompts.judge_eval_messages("Q", {"A": A, "B": B}, None))
    later = text(prompts.judge_eval_messages("Q", {"A": A}, {"A": B}))
    assert "stalled를 쓰지 마세요" in first
    assert "stalled를 쓰지 마세요" not in later
    assert "직전 라운드 의견" in later
    assert prompts.JUDGE_SYSTEM == prompts.judge_eval_messages("Q", {"A": A}, None)[0].content


def test_critique_and_final_messages():
    assert "weaknesses" in text(prompts.critique_messages("Q", A))
    final = text(prompts.final_messages("Q", {"A": A}, JudgeEval(status="stalled", issues=["남은 쟁점"], draft="초안-X"), "정체"))
    assert "토론 종료 사유: 정체" in final
    assert "남은 쟁점" in final and "초안-X" in final
    assert "no_consensus" in final
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_schemas.py tests/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.debate'`

- [ ] **Step 3: 구현**

`backend/roundtable/debate/schemas.py`:

```python
from typing import Literal, TypeVar

from pydantic import BaseModel, Field, field_validator


class Opinion(BaseModel):
    position: str
    reasons: list[str]
    conditions: list[str] = []
    confidence: float = Field(ge=0, le=1)

    @field_validator("confidence", mode="before")
    @classmethod
    def _percent_to_fraction(cls, value):
        if isinstance(value, (int, float)) and not isinstance(value, bool) and 1 < value <= 100:
            return value / 100
        return value


class ReviewedOpinion(Opinion):
    changes: str
    rebuttals: list[str] = []


class JudgeEval(BaseModel):
    status: Literal["converged", "progressing", "stalled"]
    issues: list[str] = []
    draft: str = ""


class Critique(BaseModel):
    weaknesses: list[str]
    counterarguments: list[str] = []


class Dissent(BaseModel):
    label: str
    reason: str


class FinalResult(BaseModel):
    final_opinion: str
    grade: Literal["consensus", "partial", "no_consensus"]
    key_reasons: list[str]
    dissents: list[Dissent] = []
    uncertainties: list[str] = []


T = TypeVar("T", bound=BaseModel)


def parse_json_model(text: str, model_cls: type[T]) -> T:
    """응답에서 첫 '{'부터 마지막 '}'까지를 JSON으로 읽는다. 코드 펜스나 앞뒤 설명문을 허용한다."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("JSON 객체를 찾을 수 없음")
    return model_cls.model_validate_json(text[start : end + 1])
```

`backend/roundtable/debate/prompts.py`:

```python
import json

from pydantic import BaseModel

from roundtable.debate.schemas import Critique, FinalResult, JudgeEval, Opinion, ReviewedOpinion
from roundtable.providers.base import ChatMessage

LANGUAGE_RULE = "질문에 쓰인 언어로 답하세요."
PARTICIPANT_SYSTEM = (
    "당신은 여러 AI가 함께하는 토론의 참여자입니다. 근거를 갖춰 정직하게 판단하세요. "
    "더 나은 논거를 만나면 입장을 바꾸되, 근거 없이 다수 의견에 동조하지 마세요. " + LANGUAGE_RULE
)
JUDGE_SYSTEM = (
    "당신은 여러 AI의 토론을 평가하는 판정자입니다. 다수결이 아니라 근거의 타당성으로 판단하세요. "
    "실제로 합의되지 않았다면 합의되었다고 쓰지 마세요. " + LANGUAGE_RULE
)


def json_instruction(model_cls: type[BaseModel]) -> str:
    schema = json.dumps(model_cls.model_json_schema(), ensure_ascii=False)
    return f"다른 텍스트 없이, 다음 JSON Schema를 따르는 JSON 객체 하나만 출력하세요.\n{schema}"


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "(없음)"


def format_opinion(opinion: Opinion) -> str:
    return (
        f"입장: {opinion.position}\n"
        f"근거:\n{_bullets(opinion.reasons)}\n"
        f"전제 조건·한계:\n{_bullets(opinion.conditions)}\n"
        f"확신도: {opinion.confidence:.2f}"
    )


def _labeled(opinions: dict[str, Opinion]) -> str:
    return "\n\n".join(f"[참여자 {label}]\n{format_opinion(op)}" for label, op in opinions.items())


def _participant(user_text: str) -> list[ChatMessage]:
    return [ChatMessage("system", PARTICIPANT_SYSTEM), ChatMessage("user", user_text)]


def _judge(user_text: str) -> list[ChatMessage]:
    return [ChatMessage("system", JUDGE_SYSTEM), ChatMessage("user", user_text)]


def opinion_messages(question: str) -> list[ChatMessage]:
    return _participant(
        f"질문:\n{question}\n\n"
        "다른 참여자의 의견을 보기 전에 당신의 독립적인 의견을 제시하세요.\n\n"
        + json_instruction(Opinion)
    )


def review_messages(
    question: str, own: Opinion, others: dict[str, Opinion], issues: list[str]
) -> list[ChatMessage]:
    sections = [f"질문:\n{question}", f"당신의 직전 의견:\n{format_opinion(own)}"]
    if others:
        sections.append(f"다른 참여자들의 의견:\n{_labeled(others)}")
    sections.append(f"검토할 쟁점과 반론:\n{_bullets(issues)}")
    sections.append(
        "위 내용을 검토해 입장을 수정하거나 유지하세요. changes에는 무엇을 왜 바꿨는지, "
        "또는 왜 유지했는지 쓰고, rebuttals에는 다른 의견에 대한 반박이나 보완을 쓰세요.\n\n"
        + json_instruction(ReviewedOpinion)
    )
    return _participant("\n\n".join(sections))


def judge_eval_messages(
    question: str, opinions: dict[str, Opinion], previous: dict[str, Opinion] | None
) -> list[ChatMessage]:
    sections = [f"질문:\n{question}", f"이번 라운드 의견:\n{_labeled(opinions)}"]
    if previous:
        sections.append(f"직전 라운드 의견:\n{_labeled(previous)}")
    no_previous_rule = "" if previous else " 직전 라운드 의견이 없으므로 stalled를 쓰지 마세요."
    sections.append(
        "토론 상태를 평가하세요.\n"
        "- converged: 모든 참여자가 받아들일 수 있는 하나의 의견이 나왔습니다. 조건부 동의도 포함합니다.\n"
        f"- stalled: 직전 라운드와 비교해 입장 변화도 새로운 논거도 없습니다.{no_previous_rule}\n"
        "- progressing: 그 외의 경우입니다.\n"
        "issues에는 의견이 갈리는 지점과 근거가 약한 지점을, draft에는 지금까지의 통합안 초안을 쓰세요.\n\n"
        + json_instruction(JudgeEval)
    )
    return _judge("\n\n".join(sections))


def critique_messages(question: str, opinion: Opinion) -> list[ChatMessage]:
    return _judge(
        f"질문:\n{question}\n\n참여자의 의견:\n{format_opinion(opinion)}\n\n"
        "이 의견의 약점(weaknesses)과 가능한 반론(counterarguments)을 제시하세요. "
        "참여자가 의견을 개선할 수 있도록 구체적으로 쓰세요.\n\n"
        + json_instruction(Critique)
    )


def final_messages(
    question: str,
    opinions: dict[str, Opinion],
    last_eval: JudgeEval | None,
    end_reason: str,
) -> list[ChatMessage]:
    sections = [f"질문:\n{question}", f"참여자들의 최종 의견:\n{_labeled(opinions)}"]
    if last_eval is not None:
        sections.append(
            f"마지막 판정 쟁점:\n{_bullets(last_eval.issues)}\n"
            f"마지막 통합안 초안:\n{last_eval.draft or '(없음)'}"
        )
    sections.append(
        f"토론 종료 사유: {end_reason}\n\n"
        "토론 결과를 하나의 통합된 최선의 의견(final_opinion)으로 정리하세요. "
        "grade는 consensus(합의), partial(조건부·부분 합의), no_consensus(미합의) 중 실제 상태를 고르세요. "
        "key_reasons에는 핵심 근거를, dissents에는 동의하지 않는 참여자(label)와 그 이유를, "
        "uncertainties에는 확인되지 않은 사실과 전제 조건을 쓰세요.\n\n"
        + json_instruction(FinalResult)
    )
    return _judge("\n\n".join(sections))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_schemas.py tests/test_prompts.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: 커밋**

```bash
git add backend/roundtable/debate backend/tests/test_schemas.py backend/tests/test_prompts.py
git commit -m "feat: add debate response schemas and prompts" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: 슬롯 호출기 (SlotCaller: 재시도, 소진 처리, 형식 재요청)

**Files:**
- Create: `backend/roundtable/debate/caller.py`
- Create: `backend/tests/fakes.py`
- Test: `backend/tests/test_caller.py`

**Interfaces:**
- Consumes: `SlotService`(Task 6), `UsageRecorder`(Task 7), `parse_json_model`, `json_instruction`(Task 8), 오류 4종
- Produces:
  - `ProviderFactory = Callable[[Slot, str], Provider]` (슬롯, API 키 → Provider)
  - `SlotUnavailable(slot_id: int, reason: str)` 예외 — 속성 `slot_id`, `reason`
  - `CallResult(text, provider, model, input_tokens, output_tokens, latency_ms)` (frozen dataclass)
  - `SlotCaller(slots, usage, provider_factory, sleep=asyncio.sleep)`: `async call(slot_id, messages, *, debate_id) -> CallResult`, `async call_json(slot_id, messages, model_cls, *, debate_id) -> tuple[model, CallResult]`
  - 상수: `MAX_ERROR_ATTEMPTS = 3`, `MAX_RATE_LIMIT_WAITS = 6`, `BACKOFF_BASE_SECONDS = 1.0`
  - `call`이 다시 던지는 예외: `DailyQuotaExhausted`, `CreditsExhausted`(슬롯을 소진 처리한 뒤), `ProviderError`(3회 실패 또는 속도 제한 6회 초과), `SlotUnavailable`(이미 소진 또는 키 없음)
  - `tests/fakes.py`: `ScriptedProvider(script, name="fake", model="fake-model")` — `calls: list[list[ChatMessage]]`, `prompt(index) -> str`; 대본 항목은 문자열, 예외, 또는 `messages -> str` 함수. JSON 생성기 `op_json`, `review_json`, `eval_json`, `critique_json`, `final_json`; `ALL_KEYS`; `no_sleep`

- [ ] **Step 1: 가짜 Provider 작성**

`backend/tests/fakes.py`:

```python
import json

from roundtable.providers.base import ChatMessage, ProviderResponse

ALL_KEYS = {
    "OPENAI_API_KEY": "k",
    "ANTHROPIC_API_KEY": "k",
    "GEMINI_API_KEY": "k",
    "XAI_API_KEY": "k",
}


async def no_sleep(_seconds: float) -> None:
    return None


class ScriptedProvider:
    """미리 정한 대본대로 응답하거나 오류를 내는 가짜 Provider. 실제 API를 호출하지 않는다."""

    def __init__(self, script, name: str = "fake", model: str = "fake-model") -> None:
        self.name = name
        self.model = model
        self.script = list(script)
        self.calls: list[list[ChatMessage]] = []

    async def complete(self, messages, response_schema=None) -> ProviderResponse:
        self.calls.append(list(messages))
        if not self.script:
            raise AssertionError(f"{self.name}: 대본이 끝났는데 호출됨")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        text = item(messages) if callable(item) else item
        return ProviderResponse(text, 10, 5)

    def prompt(self, index: int) -> str:
        return "\n".join(m.content for m in self.calls[index])


def op_json(position: str, *, confidence: float = 0.7) -> str:
    return json.dumps(
        {"position": position, "reasons": [f"{position}의 근거"], "conditions": [], "confidence": confidence},
        ensure_ascii=False,
    )


def review_json(position: str, changes: str = "유지") -> str:
    data = json.loads(op_json(position))
    data |= {"changes": changes, "rebuttals": []}
    return json.dumps(data, ensure_ascii=False)


def eval_json(status: str, issues=(), draft: str = "초안") -> str:
    return json.dumps({"status": status, "issues": list(issues), "draft": draft}, ensure_ascii=False)


def critique_json(weaknesses=("약점-1",), counterarguments=("반론-1",)) -> str:
    return json.dumps(
        {"weaknesses": list(weaknesses), "counterarguments": list(counterarguments)}, ensure_ascii=False
    )


def final_json(grade: str = "consensus", final_opinion: str = "통합 의견") -> str:
    return json.dumps(
        {"final_opinion": final_opinion, "grade": grade, "key_reasons": ["핵심 근거"],
         "dissents": [], "uncertainties": ["불확실성"]},
        ensure_ascii=False,
    )
```

- [ ] **Step 2: 실패하는 테스트 작성**

`backend/tests/test_caller.py`:

```python
import pytest

from fakes import ScriptedProvider, op_json
from roundtable.debate.caller import CallResult, SlotCaller, SlotUnavailable
from roundtable.debate.schemas import Opinion
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    DailyQuotaExhausted,
    ProviderError,
    RateLimited,
)
from roundtable.slots.service import SlotService
from roundtable.storage.db import init_db, make_engine
from roundtable.usage.recorder import UsageRecorder

MESSAGES = [ChatMessage("user", "q")]


class Setup:
    def __init__(self, tmp_path, script, environ=None):
        engine = make_engine(f"sqlite:///{tmp_path / 't.db'}")
        init_db(engine)
        self.slots = SlotService(engine, environ=environ if environ is not None else {"OPENAI_API_KEY": "k"})
        self.slots.seed_defaults()
        self.usage = UsageRecorder(engine)
        self.fake = ScriptedProvider(script)
        self.sleeps: list[float] = []
        self.keys: list[str] = []

        async def sleep(seconds):
            self.sleeps.append(seconds)

        def factory(slot, api_key):
            self.keys.append(api_key)
            return self.fake

        self.caller = SlotCaller(self.slots, self.usage, factory, sleep=sleep)

    def outcomes(self):
        return self.usage.summary("openai", "gpt-4o-mini")


async def test_success_records_usage_and_returns_result(tmp_path):
    s = Setup(tmp_path, ["hello"])
    result = await s.caller.call(1, MESSAGES, debate_id=7)
    assert isinstance(result, CallResult)
    assert (result.text, result.provider, result.model) == ("hello", "openai", "gpt-4o-mini")
    assert (result.input_tokens, result.output_tokens) == (10, 5)
    assert s.keys == ["k"]
    assert s.outcomes()["total_requests"] == 1


async def test_rate_limit_waits_then_retries(tmp_path):
    s = Setup(tmp_path, [RateLimited("slow", 5), RateLimited("slow"), "ok"])
    result = await s.caller.call(1, MESSAGES, debate_id=None)
    assert result.text == "ok"
    assert s.sleeps == [5, 2.0]  # 두 번째는 retry_after가 없으므로 1 * 2**1
    assert s.slots.get(1).status == "available"  # 성공하면 속도 제한 해제


async def test_rate_limit_that_never_ends_becomes_provider_error(tmp_path):
    s = Setup(tmp_path, [RateLimited("slow", 1)] * 7)
    with pytest.raises(ProviderError, match="속도 제한이 계속됨"):
        await s.caller.call(1, MESSAGES, debate_id=None)
    assert len(s.sleeps) == 6


async def test_provider_error_retries_three_times(tmp_path):
    s = Setup(tmp_path, [ProviderError("500")] * 3)
    with pytest.raises(ProviderError, match="500"):
        await s.caller.call(1, MESSAGES, debate_id=None)
    assert s.sleeps == [1.0, 2.0]
    assert len(s.fake.calls) == 3


async def test_provider_error_then_success(tmp_path):
    s = Setup(tmp_path, [ProviderError("500"), "ok"])
    assert (await s.caller.call(1, MESSAGES, debate_id=None)).text == "ok"


async def test_credits_exhausted_marks_slot_and_raises(tmp_path):
    s = Setup(tmp_path, [CreditsExhausted("no credits")])
    with pytest.raises(CreditsExhausted):
        await s.caller.call(1, MESSAGES, debate_id=None)
    slot = s.slots.get(1)
    assert (slot.status, slot.status_reason) == ("exhausted", "no credits")
    assert s.sleeps == []


async def test_daily_quota_marks_slot_and_raises(tmp_path):
    s = Setup(tmp_path, [DailyQuotaExhausted("day")])
    with pytest.raises(DailyQuotaExhausted):
        await s.caller.call(1, MESSAGES, debate_id=None)
    assert s.slots.get(1).status == "exhausted"


async def test_exhausted_slot_is_unavailable_without_calling(tmp_path):
    s = Setup(tmp_path, ["unused"])
    s.slots.mark_failure(1, CreditsExhausted("no credits"))
    with pytest.raises(SlotUnavailable) as info:
        await s.caller.call(1, MESSAGES, debate_id=None)
    assert info.value.slot_id == 1
    assert info.value.reason == "no credits"
    assert s.fake.calls == []


async def test_missing_key_is_unavailable(tmp_path):
    s = Setup(tmp_path, ["unused"], environ={})
    with pytest.raises(SlotUnavailable, match="OPENAI_API_KEY"):
        await s.caller.call(1, MESSAGES, debate_id=None)


async def test_call_json_parses(tmp_path):
    s = Setup(tmp_path, [op_json("찬성")])
    opinion, result = await s.caller.call_json(1, MESSAGES, Opinion, debate_id=None)
    assert opinion.position == "찬성"
    assert result.input_tokens == 10


async def test_call_json_retries_once_on_format_violation(tmp_path):
    s = Setup(tmp_path, ["형식 없는 답", op_json("찬성")])
    opinion, result = await s.caller.call_json(1, MESSAGES, Opinion, debate_id=None)
    assert opinion.position == "찬성"
    assert (result.input_tokens, result.output_tokens) == (20, 10)
    retry_prompt = s.fake.calls[1]
    assert retry_prompt[-2] == ChatMessage("assistant", "형식 없는 답")
    assert "형식이 아닙니다" in retry_prompt[-1].content


async def test_call_json_gives_up_after_second_violation(tmp_path):
    s = Setup(tmp_path, ["나쁨", "또 나쁨"])
    with pytest.raises(ProviderError, match="응답 형식 위반"):
        await s.caller.call_json(1, MESSAGES, Opinion, debate_id=None)
    assert len(s.fake.calls) == 2
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_caller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.debate.caller'`

- [ ] **Step 4: 구현**

`backend/roundtable/debate/caller.py`:

```python
"""슬롯 하나를 호출한다. 슬롯 상태 확인, 재시도, 사용량 기록, JSON 파싱을 맡는다."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from roundtable.debate.prompts import json_instruction
from roundtable.debate.schemas import parse_json_model
from roundtable.providers.base import (
    ChatMessage,
    CreditsExhausted,
    DailyQuotaExhausted,
    Provider,
    ProviderError,
    RateLimited,
)
from roundtable.slots.service import SlotService
from roundtable.storage.models import Slot
from roundtable.usage.recorder import UsageRecorder

MAX_ERROR_ATTEMPTS = 3
MAX_RATE_LIMIT_WAITS = 6
BACKOFF_BASE_SECONDS = 1.0
JSON_MODE = {"type": "object"}

ProviderFactory = Callable[[Slot, str], Provider]
Sleep = Callable[[float], Awaitable[None]]
T = TypeVar("T", bound=BaseModel)


class SlotUnavailable(Exception):
    def __init__(self, slot_id: int, reason: str) -> None:
        super().__init__(reason)
        self.slot_id = slot_id
        self.reason = reason


@dataclass(frozen=True)
class CallResult:
    text: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class SlotCaller:
    def __init__(
        self,
        slots: SlotService,
        usage: UsageRecorder,
        provider_factory: ProviderFactory,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._slots = slots
        self._usage = usage
        self._factory = provider_factory
        self._sleep = sleep

    async def call(
        self, slot_id: int, messages: list[ChatMessage], *, debate_id: int | None
    ) -> CallResult:
        slot = self._slots.get(slot_id)
        if slot.status == "exhausted":
            raise SlotUnavailable(slot_id, slot.status_reason or "무료 제공량 소진")
        api_key = self._slots.api_key(slot)
        if api_key is None:
            raise SlotUnavailable(slot_id, f"{slot.api_key_env} 환경변수가 없음")
        provider = self._factory(slot, api_key)
        errors = waits = 0
        started = time.monotonic()
        while True:
            try:
                response = await provider.complete(messages, JSON_MODE)
            except RateLimited as failure:
                self._log(slot, debate_id, "rate_limited")
                self._slots.mark_failure(slot_id, failure)
                waits += 1
                if waits > MAX_RATE_LIMIT_WAITS:
                    raise ProviderError(f"속도 제한이 계속됨: {failure.message}") from failure
                await self._sleep(failure.retry_after or BACKOFF_BASE_SECONDS * 2 ** (waits - 1))
                continue
            except DailyQuotaExhausted as failure:
                self._log(slot, debate_id, "quota")
                self._slots.mark_failure(slot_id, failure)
                raise
            except CreditsExhausted as failure:
                self._log(slot, debate_id, "credits")
                self._slots.mark_failure(slot_id, failure)
                raise
            except ProviderError:
                self._log(slot, debate_id, "error")
                errors += 1
                if errors >= MAX_ERROR_ATTEMPTS:
                    raise
                await self._sleep(BACKOFF_BASE_SECONDS * 2 ** (errors - 1))
                continue
            self._log(slot, debate_id, "ok", response.input_tokens, response.output_tokens)
            self._slots.mark_ok(slot_id)
            return CallResult(
                text=response.text,
                provider=slot.provider,
                model=slot.model,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=int((time.monotonic() - started) * 1000),
            )

    async def call_json(
        self,
        slot_id: int,
        messages: list[ChatMessage],
        model_cls: type[T],
        *,
        debate_id: int | None,
    ) -> tuple[T, CallResult]:
        first = await self.call(slot_id, messages, debate_id=debate_id)
        try:
            return parse_json_model(first.text, model_cls), first
        except ValueError:
            pass
        retry_messages = [
            *messages,
            ChatMessage("assistant", first.text),
            ChatMessage("user", "직전 응답이 요구한 형식이 아닙니다. " + json_instruction(model_cls)),
        ]
        second = await self.call(slot_id, retry_messages, debate_id=debate_id)
        combined = CallResult(
            text=second.text,
            provider=second.provider,
            model=second.model,
            input_tokens=first.input_tokens + second.input_tokens,
            output_tokens=first.output_tokens + second.output_tokens,
            latency_ms=first.latency_ms + second.latency_ms,
        )
        try:
            return parse_json_model(second.text, model_cls), combined
        except ValueError as exc:
            raise ProviderError(f"응답 형식 위반 (재요청 후에도): {exc}") from exc

    def _log(
        self,
        slot: Slot,
        debate_id: int | None,
        outcome: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        self._usage.record(
            provider=slot.provider, model=slot.model, debate_id=debate_id,
            input_tokens=input_tokens, output_tokens=output_tokens, outcome=outcome,
        )
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_caller.py -v`
Expected: PASS (12 passed)

- [ ] **Step 6: 커밋**

```bash
git add backend/roundtable/debate/caller.py backend/tests/fakes.py backend/tests/test_caller.py
git commit -m "feat: add slot caller with retry, quota handling and format retry" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: 이벤트 버스 + 토론 진행기 (Orchestrator)

**Files:**
- Create: `backend/roundtable/debate/events.py`, `backend/roundtable/debate/orchestrator.py`
- Test: `backend/tests/test_events.py`, `backend/tests/test_orchestrator.py`

**Interfaces:**
- Consumes: `DebateStore`(Task 5), `SlotService`·`JUDGE_SLOT_ID`(Task 6), `UsageRecorder`(Task 7), schemas·prompts(Task 8), `SlotCaller`·`SlotUnavailable`(Task 9), 오류 4종
- Produces:
  - `events.Event(type: str, data: dict)`, `events.TERMINAL_EVENTS = frozenset({"finished", "paused", "error"})`
  - `EventBus()`: `subscribe(debate_id) -> asyncio.Queue[Event]`, `unsubscribe(debate_id, queue) -> None`, `subscriber_count(debate_id) -> int`, `publish(debate_id, type, data) -> None`
  - 이벤트 종류와 데이터: `round_started {"round", "participants"}`, `message {"round", "label", "content"}`, `judge_evaluated {"round", "status", "issues", "draft"}`, `participant_dropped {"label", "provider", "model", "round", "reason"}`, `paused {"reason"}`, `finished {"status", "grade"}`, `error {"message"}`
  - `orchestrator.LABELS = "ABCD"`, `build_participants(slots: list[Slot]) -> list[dict]`, `describe_failure(exc) -> str`
  - `END_REASONS = {"converged": "수렴", "stalled": "정체", "stopped": "사용자 중단", "interrupted": "모든 참여 AI 소진"}`
  - `Orchestrator(store, caller, bus, judge_slot_id=JUDGE_SLOT_ID)`: `start(debate_id) -> asyncio.Task`, `async wait(debate_id) -> None`, `is_running(debate_id) -> bool`, `request_stop(debate_id) -> None`, `async run(debate_id) -> None`(새 토론과 이어하기 모두 처리)
  - 최종 `debates.result` 형식: `FinalResult` 필드 + `"dropouts": list[dict]`, `"end_reason": str`. 의견이 하나도 없으면 `{"dropouts": [...], "end_reason": ...}`만 저장하고 `grade`는 `None`.

- [ ] **Step 1: 이벤트 버스 테스트 작성**

`backend/tests/test_events.py`:

```python
from roundtable.debate.events import Event, EventBus


async def test_publish_reaches_only_subscribers_of_that_debate():
    bus = EventBus()
    first = bus.subscribe(1)
    other = bus.subscribe(2)
    bus.publish(1, "message", {"label": "A"})
    assert first.get_nowait() == Event("message", {"label": "A"})
    assert other.empty()


async def test_unsubscribe_and_count():
    bus = EventBus()
    queue = bus.subscribe(1)
    assert bus.subscriber_count(1) == 1
    bus.unsubscribe(1, queue)
    assert bus.subscriber_count(1) == 0
    bus.publish(1, "message", {})  # 구독자가 없어도 오류 없음
    assert queue.empty()
```

- [ ] **Step 2: 토론 진행기 테스트 작성**

`backend/tests/test_orchestrator.py`:

```python
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
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_events.py tests/test_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.debate.events'`

- [ ] **Step 4: 이벤트 버스 구현**

`backend/roundtable/debate/events.py`:

```python
import asyncio
from collections import defaultdict
from dataclasses import dataclass

TERMINAL_EVENTS = frozenset({"finished", "paused", "error"})


@dataclass(frozen=True)
class Event:
    type: str
    data: dict


class EventBus:
    """토론별 SSE 구독자에게 진행 이벤트를 전달한다. 프로세스 안에서만 동작한다."""

    def __init__(self) -> None:
        self._subscribers: dict[int, set[asyncio.Queue[Event]]] = defaultdict(set)

    def subscribe(self, debate_id: int) -> asyncio.Queue[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._subscribers[debate_id].add(queue)
        return queue

    def unsubscribe(self, debate_id: int, queue: asyncio.Queue[Event]) -> None:
        subscribers = self._subscribers.get(debate_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            del self._subscribers[debate_id]

    def subscriber_count(self, debate_id: int) -> int:
        return len(self._subscribers.get(debate_id, ()))

    def publish(self, debate_id: int, type: str, data: dict) -> None:
        for queue in list(self._subscribers.get(debate_id, ())):
            queue.put_nowait(Event(type, data))
```

- [ ] **Step 5: 토론 진행기 구현**

`backend/roundtable/debate/orchestrator.py`:

```python
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
        task = asyncio.create_task(self.run(debate_id))
        self._tasks[debate_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(debate_id, None))
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
        except Exception as exc:  # 예상하지 못한 오류도 토론 상태에 남긴다
            self._store.update(debate_id, status="interrupted", pause_reason=f"내부 오류: {exc}")
            self._bus.publish(debate_id, "error", {"message": str(exc)})
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
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_events.py tests/test_orchestrator.py -v`
Expected: PASS (18 passed)

- [ ] **Step 7: 전체 테스트 확인**

Run: `cd backend && uv run pytest -q`
Expected: 모든 테스트 PASS

- [ ] **Step 8: 커밋**

```bash
git add backend/roundtable/debate/events.py backend/roundtable/debate/orchestrator.py backend/tests/test_events.py backend/tests/test_orchestrator.py
git commit -m "feat: add debate orchestrator with dropouts, pause and resume" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: HTTP API (토론, SSE, 슬롯, 설정)

**Files:**
- Create: `backend/roundtable/api/__init__.py` (빈 파일), `backend/roundtable/api/services.py`, `backend/roundtable/api/routes.py`, `backend/roundtable/api/app.py`
- Test: `backend/tests/test_api.py`

**Interfaces:**
- Consumes: Task 5~10 전부
- Produces:
  - `Services(store, slots, usage, config, bus, orchestrator)` (dataclass)
  - `build_services(db_url: str, *, environ: Mapping[str, str], provider_factory: ProviderFactory, sleep=asyncio.sleep) -> Services` — DB 초기화, 기본 슬롯 생성, `running` 토론을 `interrupted`로 전환
  - `create_app(services: Services, *, on_shutdown: Callable[[], Awaitable[None]] | None = None) -> FastAPI` — CORS `http://localhost:3000` 허용
  - 엔드포인트(스펙 5.4 + `/config`):
    - `POST /debates` `{"question": str, "slot_ids": [int]}` → 201 `{"id": int}`; 422(형식), 409(슬롯 소진·키 없음, 판정 AI 소진)
    - `GET /debates` → `[{"id","question","status","grade","started_at","ended_at"}]`
    - `GET /debates/{id}` → `DebateStore.detail()` 형식, 404
    - `GET /debates/{id}/events` → `text/event-stream`; 진행 중이면 이벤트를 보내다가 `finished`/`paused`/`error` 뒤 닫음, 이미 끝났으면 `status {"status": ...}` 하나 보내고 닫음; 15초마다 `: ping`
    - `POST /debates/{id}/stop` → 202 `{"status": "stopping"}`, 409(진행 중 아님)
    - `POST /debates/{id}/resume` → 202 `{"status": "resuming"}`, 409(이어할 수 없음, 판정 AI 사용 불가)
    - `GET /slots` → `[{"id","kind","provider","model","api_key_env","key_present","status","status_until","status_reason","known_limit","usage","usage_estimate"}]`
    - `PUT /slots/{id}` `{"provider","model","api_key_env","known_limit"?}` → 슬롯 보기, 404, 422
    - `GET /config` → `{"stall_threshold": int, "providers": [str]}`; `PUT /config` `{"stall_threshold": 1~10}`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_api.py`:

```python
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
        assert (await client.put("/slots/9", json={"provider": "openai", "model": "m", "api_key_env": "X"})).status_code == 404


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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.api'`

- [ ] **Step 3: 구현**

`backend/roundtable/api/services.py`:

```python
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass

from roundtable.debate.caller import ProviderFactory, Sleep, SlotCaller
from roundtable.debate.events import EventBus
from roundtable.debate.orchestrator import Orchestrator
from roundtable.slots.service import SlotService
from roundtable.storage.config import ConfigStore
from roundtable.storage.db import init_db, make_engine
from roundtable.storage.store import DebateStore
from roundtable.usage.recorder import UsageRecorder


@dataclass
class Services:
    store: DebateStore
    slots: SlotService
    usage: UsageRecorder
    config: ConfigStore
    bus: EventBus
    orchestrator: Orchestrator


def build_services(
    db_url: str,
    *,
    environ: Mapping[str, str],
    provider_factory: ProviderFactory,
    sleep: Sleep = asyncio.sleep,
) -> Services:
    engine = make_engine(db_url)
    init_db(engine)
    slots = SlotService(engine, environ=environ)
    slots.seed_defaults()
    usage = UsageRecorder(engine)
    store = DebateStore(engine)
    store.mark_running_as_interrupted()
    bus = EventBus()
    caller = SlotCaller(slots, usage, provider_factory, sleep=sleep)
    return Services(
        store=store, slots=slots, usage=usage, config=ConfigStore(engine),
        bus=bus, orchestrator=Orchestrator(store, caller, bus),
    )
```

`backend/roundtable/api/routes.py`:

```python
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
```

`backend/roundtable/api/app.py`:

```python
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from roundtable.api.routes import router
from roundtable.api.services import Services

FRONTEND_ORIGINS = ["http://localhost:3000"]


def create_app(
    services: Services, *, on_shutdown: Callable[[], Awaitable[None]] | None = None
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        if on_shutdown is not None:
            await on_shutdown()

    app = FastAPI(title="AI-Roundtable", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_methods=["*"], allow_headers=["*"]
    )
    app.state.services = services
    app.include_router(router)
    return app
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_api.py -v`
Expected: PASS (19 passed — 매개변수화된 입력 검증 6건 포함)

- [ ] **Step 5: 전체 테스트 확인**

Run: `cd backend && uv run pytest -q`
Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add backend/roundtable/api backend/tests/test_api.py
git commit -m "feat: add HTTP API with SSE, slots and config endpoints" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: 실행 진입점, smoke 명령, README

**Files:**
- Create: `backend/roundtable/main.py`, `backend/roundtable/smoke.py`, `backend/README.md`
- Test: `backend/tests/test_smoke.py`

**Interfaces:**
- Consumes: `build_services`, `create_app`(Task 11), `build_provider`(Task 4), `SlotService`(Task 6)
- Produces:
  - `roundtable.main:app` (uvicorn 진입점, DB 경로는 `ROUNDTABLE_DB` 환경변수, 기본 `sqlite:///./roundtable.db`)
  - `smoke.run_smoke(slots: SlotService, provider_factory: ProviderFactory) -> list[str]` — 슬롯마다 한 줄: `건너뜀`, `성공`, `실패`
  - 명령: `uv run python -m roundtable.smoke`

- [ ] **Step 1: 실패하는 테스트 작성**

`backend/tests/test_smoke.py`:

```python
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
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd backend && uv run pytest tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'roundtable.smoke'`

- [ ] **Step 3: 구현**

`backend/roundtable/smoke.py`:

```python
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
```

`backend/roundtable/main.py`:

```python
"""실행: uv run uvicorn roundtable.main:app --port 8000"""

import os

import httpx
from dotenv import load_dotenv

from roundtable.api.app import create_app
from roundtable.api.services import build_services
from roundtable.providers.registry import build_provider

load_dotenv()

_client = httpx.AsyncClient()
services = build_services(
    os.environ.get("ROUNDTABLE_DB", "sqlite:///./roundtable.db"),
    environ=os.environ,
    provider_factory=lambda slot, key: build_provider(slot.provider, slot.model, key, _client),
)
app = create_app(services, on_shutdown=_client.aclose)
```

`backend/README.md`:

````markdown
# AI-Roundtable 백엔드

여러 AI가 독립 의견 → 상호 검토 → 판정 AI 통합을 거쳐 하나의 최종 의견을 만드는 토론 서버입니다.

## 준비

1. [uv](https://docs.astral.sh/uv/)를 설치합니다.
2. 의존성을 설치합니다.
   ```bash
   cd backend
   uv sync
   ```
3. `.env.example`을 `.env`로 복사하고, 무료로 발급받은 API 키를 넣습니다. 키가 없는 슬롯은 선택할 수 없습니다.

## 연결 확인 (실제 API 호출, 슬롯마다 1회)

```bash
uv run python -m roundtable.smoke
```

`실패 — CreditsExhausted`가 나오면 그 회사의 무료 크레딧이 없는 상태입니다. 설정에서 다른 무료 모델로 바꾸세요
(예: `PUT /slots/2` 로 `openrouter`의 `:free` 모델).

## 서버 실행

```bash
uv run uvicorn roundtable.main:app --port 8000
```

API 문서: http://localhost:8000/docs

## 테스트 (실제 API를 호출하지 않음)

```bash
uv run pytest
```
````

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd backend && uv run pytest tests/test_smoke.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 전체 테스트 확인**

Run: `cd backend && uv run pytest -q`
Expected: 모든 테스트 PASS

- [ ] **Step 6: 서버가 뜨는지 수동 확인 (실제 API 호출 없음)**

Run (Git Bash 기준): `cd backend && ROUNDTABLE_DB=sqlite:///./check.db uv run uvicorn roundtable.main:app --port 8000` 를 백그라운드로 띄운 뒤 `curl http://localhost:8000/slots`
Expected: 슬롯 5개 JSON. 확인 후 서버를 종료하고 `backend/check.db`를 삭제한다(`*.db`는 `.gitignore`로 커밋되지 않음).

- [ ] **Step 7: 커밋**

```bash
git add backend/roundtable/main.py backend/roundtable/smoke.py backend/README.md backend/tests/test_smoke.py
git commit -m "feat: add server entrypoint, smoke command and README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
