# AI-Roundtable 설계 문서

- 작성일: 2026-10-12
- 상태: 사용자 검토 대기
- 범위: 개인용 토론 도구 MVP (공개 서비스 확장은 범위 밖, 확장 여지만 확보)

## 1. 목적과 범위

### 목적
사용자가 질문을 입력하면 여러 AI(기본: GPT, Claude, Gemini, Grok)가 독립적으로 의견을 내고, 서로 검토·반박·수정한 뒤, 판정 AI가 **하나의 통합된 최선의 의견**을 만들어 준다. 핵심 가치는 토론 과정의 관람이 아니라 **통합된 결과**이다.

### 사용 대상
- 현재: 사용자 본인 1명이 쓰는 개인 도구.
- 이후: 공개 서비스로 확장 예정. 이번 MVP에서는 로그인·과금·사용량 제한을 구현하지 않되, 확장 지점(`user_id` 컬럼, API 키 관리 모듈 분리)을 남겨 둔다.

### 비용 원칙
- **추가 비용 0원.** 구독 없이 각 회사의 무료 제공량(무료 등급·체험 크레딧)만 사용한다. 유료 결제로 넘어가는 경로는 만들지 않는다.
- 토론 1회당 금액 상한은 두지 않는다. 종료는 판정 AI의 수렴·정체 판단과 사용자 중단으로만 이루어진다.
- 2026-10 조사 기준(제3자 자료, 실제 조건은 각 콘솔에서 확인 필요): 지속 무료는 Gemini(Flash 계열, 일일 한도)뿐이고, GPT·Claude·Grok은 1회성 체험 크레딧이다. 따라서 소진 감지와 슬롯 교체가 핵심 기능이다.

### 범위 밖
- 로그인, 다중 사용자, 과금, 사용량 제한
- AI 코드 리뷰·검증 하네스(별도 프로젝트로 다룸)
- 웹 검색 등 외부 사실 확인 도구
- 화면에서 API 키 직접 입력

## 2. 핵심 요구사항

1. 질문마다 참여 AI 슬롯을 1~4개 선택한다(기본: 4개 모두).
2. 1라운드 의견은 다른 AI의 영향 없이 독립적으로 생성한다.
3. 라운드 수 상한은 없다. 판정 AI가 `수렴` 또는 `정체`로 판단하거나 사용자가 중단하면 끝난다.
4. 결과는 다수결이 아닌 하나의 통합 의견이며, 억지로 합의로 표시하지 않는다(`합의` / `조건부·부분 합의` / `미합의`).
5. 4개 참여 슬롯과 1개 판정 슬롯은 각각 회사·모델을 설정에서 바꿀 수 있다.
6. 무료 제공량이 소진되면 **어느 AI가 왜 소진됐는지** 사용자에게 알린다.

## 3. 아키텍처

```
[Next.js 프론트엔드] ──HTTP / SSE──▶ [FastAPI 백엔드]
                                        ├── orchestrator (토론 진행, 백그라운드 작업)
                                        ├── judge (판정 슬롯)
                                        ├── providers (슬롯별 모델 연결)
                                        ├── usage (사용량·소진 판정)
                                        └── storage (SQLite)
```

- 백엔드: Python FastAPI. 토론은 백그라운드 작업으로 실행되어 라운드가 길어져도 요청 시간 제한에 걸리지 않는다.
- 프론트엔드: Next.js(TypeScript).
- 실시간 전달: SSE(Server-Sent Events). 과정 관람이 핵심이 아니므로 WebSocket 대신 단순한 단방향 전달을 사용한다.
- 저장소: SQLite. 공개 서비스 확장 시 PostgreSQL로 이전 가능하도록 ORM(SQLAlchemy/SQLModel)을 통해 접근한다.

## 4. 토론 흐름

### 4.1 시작
- 사용자가 질문을 입력하고 참여 슬롯을 1~4개 선택한다.
- `소진` 상태인 슬롯은 선택할 수 없다. 판정 슬롯이 `소진`이면 토론을 시작할 수 없다.

### 4.2 1라운드: 독립 의견
- 선택된 참여 AI들을 동시에(병렬) 호출한다. 입력은 질문뿐이며 다른 AI의 응답을 포함하지 않는다.
- 응답 형식(구조화된 JSON):
  - `position`: 한 줄 결론
  - `reasons`: 근거 목록
  - `conditions`: 전제 조건·한계
  - `confidence`: 확신도(0~1)

### 4.3 판정 AI 평가 (매 라운드 뒤)
- 입력: 이번 라운드 모든 의견.
- 출력:
  - `status`: `converged`(수렴) / `progressing`(진행 중) / `stalled`(정체)
  - `issues`: 의견이 갈리는 지점, 근거가 약한 지점
  - `draft`: 현재까지의 통합안 초안
- **수렴:** 모든 참여자가 받아들일 수 있는 하나의 의견이 나온 상태. 조건부 동의도 포함한다.
- **정체:** N라운드 연속으로 입장 변화와 새로운 논거가 모두 없는 상태. N의 기본값은 2이며 설정에서 바꿀 수 있다.
- `progressing`이면 다음 라운드로 넘어간다.

### 4.4 2라운드 이후: 상호 검토
- 각 참여 AI가 받는 입력:
  - 다른 참여자들의 직전 의견. 모델 이름 대신 `참여자 A/B/C`로 가린다(브랜드 편향 방지). 이름표는 토론 내내 고정이다.
  - 판정 AI의 쟁점 목록
  - 자기 자신의 직전 의견
- 응답 형식: 4.2의 필드 + `changes`(무엇을 왜 바꿨는지 또는 왜 유지했는지) + `rebuttals`(다른 의견에 대한 반박·보완).

### 4.5 종료와 최종 결과
- 종료 조건: 판정 `converged` 또는 `stalled`, 사용자 "중단" 버튼, 참여 AI 전원 소진(4.7).
- 판정 AI가 최종 결과를 작성한다.
  - `final_opinion`: 통합된 최종 의견
  - `grade`: `consensus`(합의) / `partial`(조건부·부분 합의) / `no_consensus`(미합의)
  - `key_reasons`: 핵심 근거
  - `dissents`: 남은 이견(어느 참여자가 어떤 이유로)
  - `uncertainties`: 확인되지 않은 사실, 전제 조건
  - `dropouts`: 토론 중 빠진 AI와 그 라운드·이유

### 4.6 1개 모드
- 참여 AI가 1개이면 판정 AI가 비판자 역할을 맡는다.
- 흐름: 독립 의견 → 판정 AI가 약점·반론 제시 → AI가 수정 → 판정 평가를 반복한다. 종료 조건은 4.5와 같다.

### 4.7 토론 중 참여자 감소
- 참여 AI가 소진되거나 2라운드 연속 실패하면 토론에서 빠지고 나머지로 계속한다.
- 남은 참여 AI가 1개가 되면 자동으로 1개 모드로 바뀐다.
- 남은 참여 AI가 0개가 되면 판정 AI가 지금까지의 의견으로 통합안을 만들고, 상태는 `interrupted`, 이유는 "모든 참여 AI 소진"으로 기록한다.

## 5. 구성 요소

### 5.1 백엔드 디렉터리

```
backend/
├── providers/
│   ├── base.py           # Provider 인터페이스, 오류 종류
│   ├── openai_compat.py  # GPT, Grok, OpenRouter, Groq (OpenAI 호환 방식)
│   ├── anthropic.py      # Claude
│   └── gemini.py         # Gemini
├── slots/                # 슬롯 설정·상태 관리
├── debate/
│   ├── orchestrator.py   # 라운드 진행 (4장)
│   ├── judge.py          # 라운드 평가, 비판(1개 모드), 최종 통합
│   └── prompts.py        # 프롬프트, 응답 형식 정의
├── usage/                # 호출 기록, 소진 판정, 사용량 추정
├── storage/              # SQLite 모델, 저장소 접근
├── api/                  # HTTP 엔드포인트, SSE
└── main.py
```

### 5.2 Provider 인터페이스
- 모든 연결 모듈은 `complete(messages, response_schema) -> ProviderResponse(text, input_tokens, output_tokens)` 하나를 구현한다.
- 실패 시 다음 오류 중 하나를 발생시킨다.
  - `RateLimited(retry_after)`: 일시적 속도 제한
  - `DailyQuotaExhausted(reset_at)`: 일일 한도 소진
  - `CreditsExhausted`: 크레딧 소진
  - `ProviderError`: 기타 오류(네트워크, 서버 오류, 시간 초과)
- `orchestrator`와 `judge`는 이 인터페이스에만 의존한다. 따라서 가짜 Provider로 전체 흐름을 테스트할 수 있다.

### 5.3 슬롯
- 참여 슬롯 4개(1~4)와 판정 슬롯 1개.
- 슬롯 필드: 회사, 모델 이름, API 키 환경변수 이름, 상태, 상태 해제 예상 시각, 상태 사유, 알려진 무료 한도(선택, 예: 하루 요청 500회).
- 기본값:
  - 슬롯 1~4: GPT, Claude, Gemini(Flash), Grok
  - 판정 슬롯: Gemini Flash-Lite. 참여 Gemini와 다른 모델을 써서 일일 한도를 공유하지 않게 하고, 참가자와 판정자를 분리해 편향을 줄인다.
- API 키는 `.env`에만 저장하고 Git에 커밋하지 않는다(`.gitignore`). 화면에는 "연결됨/없음"만 표시한다.

### 5.4 HTTP 엔드포인트

| 요청 | 설명 |
|---|---|
| `POST /debates` | 토론 시작 (`question`, `slot_ids`) |
| `GET /debates` | 토론 기록 목록 |
| `GET /debates/{id}` | 토론 상세 (라운드, 발언, 결과) |
| `GET /debates/{id}/events` | SSE 진행 이벤트 |
| `POST /debates/{id}/stop` | 사용자 중단 |
| `POST /debates/{id}/resume` | 일시정지·재시작으로 멈춘 토론 이어하기 |
| `GET /slots` | 슬롯 설정·상태·사용량 |
| `PUT /slots/{id}` | 슬롯 모델 변경 (변경 시 `소진` 상태 해제) |

SSE 이벤트 종류: `round_started`, `message`, `judge_evaluated`, `participant_dropped`, `paused`, `finished`, `error`.

### 5.5 프론트엔드 화면
1. **질문 화면 (`/`)**: 질문 입력란, 참여 슬롯 체크박스 4개(기본 전체 선택), 슬롯별 상태 배지. 소진 슬롯은 비활성화된다. 판정 슬롯이 소진되면 시작 버튼이 비활성화되고 이유를 표시한다.
2. **토론 결과 화면 (`/debates/[id]`)**: 상단 진행 상태(라운드 번호, 판정 상태), 소진·제외 배너, 중단·이어하기 버튼. 종료 후 최종 통합 의견 카드(결론 등급, 근거, 남은 이견, 불확실성, 제외된 AI)를 가장 크게 표시한다. 그 아래 라운드별 발언은 접힌 상태로 둔다.
3. **기록 화면 (`/history`)**: 지난 토론 목록(질문, 상태, 결론 등급, 날짜).
4. **설정 화면 (`/settings`)**: 슬롯별 회사·모델 지정, 판정 슬롯 지정, 정체 기준 N, 슬롯별 상태·사유·해제 예상 시각, 오늘·누적 사용량과 무료 한도 대비 추정치.

## 6. 데이터 (SQLite)

| 테이블 | 주요 필드 |
|---|---|
| `slots` | `id`, `kind`(participant/judge), `provider`, `model`, `api_key_env`, `status`(available/rate_limited/exhausted), `status_until`, `status_reason`, `known_limit`(JSON, 선택) |
| `debates` | `id`, `user_id`(NULL, 확장용), `question`, `status`(running/paused/converged/stalled/stopped/interrupted), `grade`, `result`(JSON), `participants`(슬롯 스냅샷 JSON: 이름표, 회사, 모델), `stall_threshold`, `started_at`, `ended_at`, `pause_reason` |
| `rounds` | `id`, `debate_id`, `number`, `judge_eval`(JSON: status, issues, draft), `completed_at` |
| `messages` | `id`, `round_id`, `label`(A/B/C/D), `provider`, `model`, `content`(JSON), `input_tokens`, `output_tokens`, `latency_ms`, `error` |
| `usage_log` | `id`, `provider`, `model`, `debate_id`, `called_at`, `input_tokens`, `output_tokens`, `outcome`(ok/rate_limited/quota/credits/error) |

- 발언과 판정 결과는 생성될 때마다 즉시 저장한다.
- 사용량 추정치는 `usage_log` 집계를 `known_limit`과 비교해 계산하며, 화면에는 "추정"으로 표시한다. 실제 소진 여부는 API 오류로만 확정한다.

## 7. 오류와 제공량 처리

### 7.1 오류 처리 규칙

| 오류 | 처리 | 슬롯 상태 |
|---|---|---|
| `RateLimited` | `retry_after`(없으면 지수 백오프)만큼 기다린 뒤 재시도 | `rate_limited`, `status_until` 지나면 자동 해제 |
| `DailyQuotaExhausted` | 해당 슬롯 오늘 사용 중지 | `exhausted`, `reset_at`에 자동 해제 |
| `CreditsExhausted` | 해당 슬롯 사용 중지 | `exhausted`, 자동 해제 없음. 슬롯 모델 변경 시 해제 |
| `ProviderError` | 최대 3회 재시도(지수 백오프). 호출당 시간 제한 120초 | 변경 없음 |

- 응답이 형식을 어기면 형식 교정을 요청하며 1회 재요청한다. 그래도 어기면 `ProviderError`로 처리한다.
- `ProviderError`로 3회 모두 실패하면 그 참여자는 해당 라운드를 건너뛴다. 2라운드 연속 실패하면 토론에서 제외한다.
- 회사별 오류 응답(HTTP 상태 코드, 오류 코드·메시지)을 위 네 종류로 분류하는 규칙은 각 연결 모듈에 둔다.

### 7.2 소진 시 동작
- 참여 AI 소진: 해당 참여자를 제외하고 계속한다(4.7). `participant_dropped` 이벤트로 배너를 띄운다.
  - 예: "⚠️ Claude (claude-haiku) — 무료 크레딧 소진. 3라운드부터 토론에서 제외됐어요. 설정에서 다른 모델로 바꿀 수 있어요."
- 판정 AI 소진: 토론을 `paused`로 바꾸고 알린다. 다른 모델로 몰래 대체하지 않는다. 사용자가 판정 슬롯을 바꾸면 `resume`으로 이어간다.
- 최종 결과에는 항상 제외된 AI와 그 라운드·이유를 표시한다.

### 7.3 연결 끊김과 재시작
- 브라우저가 끊겨도 토론은 서버에서 계속된다. 다시 접속하면 `GET /debates/{id}`로 현재 상태를 불러오고 SSE에 다시 연결한다.
- 서버가 시작될 때 `running` 상태의 토론을 `interrupted`(사유: 재시작)로 바꾼다. "이어하기"를 누르면 마지막으로 완료된 라운드 다음부터 진행하며, 완료되지 않은 라운드의 발언은 버린다.

## 8. 테스트

모든 자동 테스트는 미리 정한 응답·오류 대본을 따르는 가짜 Provider를 사용하며 실제 API를 호출하지 않는다.

### 백엔드 (pytest)
- 토론 흐름: 1라운드 입력에 다른 AI 응답이 없는지, 2라운드부터 이름표로 가려진 의견이 전달되는지, 수렴 종료, N라운드 연속 정체 종료, 사용자 중단 시 통합안 생성, 1개 모드에서 판정 AI의 비판자 역할.
- 소진·오류: 참여 AI 1개 소진 시 제외 후 계속, 1개로 줄면 1개 모드 전환, 0개면 `interrupted`, 판정 AI 소진 시 `paused`와 이어하기, 속도 제한 대기 후 재시도, 기타 오류 3회 재시도와 2라운드 연속 실패 시 제외, 형식 위반 시 1회 재요청.
- 연결 모듈: 회사별 실제 오류 응답 예시(fixture 파일)가 네 가지 오류 종류로 올바르게 분류되는지.
- 저장·복구: 재시작 후 `interrupted` 전환과 마지막 완료 라운드부터 이어하기.
- API: 엔드포인트 요청·응답, SSE 이벤트 순서.

### 프론트엔드
- 컴포넌트 테스트: 소진 슬롯 비활성화, 판정 슬롯 소진 시 시작 버튼 비활성화, 최종 결과 카드와 접히는 라운드 기록 표시.

### 수동 확인
- `smoke` 명령: 슬롯마다 아주 짧은 요청을 1회씩 보내 키·연결을 확인한다. 무료 제공량을 아끼기 위해 사용자가 직접 실행할 때만 동작한다.

## 9. 향후 확장 (이번 범위 밖)
- 공개 서비스: 로그인, `user_id` 활용, 사용자별 API 키, 사용량 제한·과금, PostgreSQL 이전, 유료 API 전환.
- 외부 사실 확인(웹 검색) 도구.
- AI 코드 리뷰·검증 하네스.
