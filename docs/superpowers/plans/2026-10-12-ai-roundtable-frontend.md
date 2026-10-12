# AI-Roundtable 프론트엔드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 완성된 FastAPI 백엔드를 쓰는 Next.js 화면 4개(질문, 토론 결과, 기록, 설정)를 만든다.

**Architecture:** `frontend/` 아래 Next.js App Router 앱. 모든 화면은 클라이언트 컴포넌트이며 브라우저에서 백엔드(`http://127.0.0.1:8000`)를 직접 호출한다(CORS 허용 출처 `http://localhost:3000`). 화면 로직은 `src/components/`의 순수 컴포넌트에 두고 `src/app/**/page.tsx`는 데이터 로딩과 연결만 한다. 실시간 진행은 SSE 이벤트를 받을 때마다 `GET /debates/{id}`로 다시 불러오는 방식(단순·견고)으로 처리한다.

**Tech Stack:** Next.js 15.5.27, React 19.3.0, TypeScript 5.9.3, Vitest 3.2.7 + Testing Library(React 16.3.3, DOM 10.4.2, jest-dom 6.10.0, user-event 14.6.7) + jsdom 26.1.0. 스타일은 Tailwind 없이 `globals.css` 한 파일(CSS 변수).

**Spec:** `docs/superpowers/specs/2026-10-12-ai-roundtable-design.md` (§3 아키텍처, §4 토론 흐름, §5.5 프론트엔드 화면, §7.2 소진 시 동작, §7.3 연결 끊김, §8 프론트엔드 테스트)

## Global Constraints

- 추가 비용 0원: 자동 테스트는 실제 백엔드·실제 AI API를 절대 호출하지 않는다. `fetch`와 `EventSource`는 테스트에서 가짜로 바꾼다.
- 모든 명령은 `frontend/` 디렉터리에서 `npm run ...`으로 실행한다. 패키지 버전은 이 문서의 `package.json` 그대로 고정한다(`^`, `~` 금지).
- 화면에 보이는 문자열은 한국어로 쓴다. 회사 이름(OpenAI 등)과 모델 이름은 원문 그대로.
- API 키 값은 화면에 절대 표시하지 않는다. 화면에는 "연결됨/없음"만 표시한다(백엔드도 `key_present`만 준다).
- 개발 서버는 `next dev -H localhost -p 3000`으로만 띄운다(백엔드 CORS가 `http://localhost:3000`만 허용, 인증 없는 로컬 앱).
- 백엔드 주소는 `NEXT_PUBLIC_API_BASE`, 기본값 `http://127.0.0.1:8000`.
- 백엔드 시간 값은 끝에 `Z`가 붙은 UTC다. 화면에는 브라우저 지역 시간으로 바꿔 표시한다.
- 백엔드 오류 응답은 `{"detail": "<한국어 문자열>"}`이다. 실패 시 이 문자열을 그대로 보여 준다.
- 판정 결과가 없는 라운드(`judge_eval: null`, 1명 토론의 1라운드 등)는 "평가 없음"으로 표시하고 오류로 취급하지 않는다.
- 결론 등급 표기: `consensus`=합의, `partial`=조건부·부분 합의, `no_consensus`=미합의. 억지로 합의처럼 보이게 꾸미지 않는다.
- 모든 커밋 메시지 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` 줄을 붙인다.

## Review Focus

1. 백엔드가 꺼져 있을 때: 빈 화면이나 영어 예외 대신 "백엔드 서버에 연결할 수 없습니다…" 한국어 안내가 보여야 한다. → Task 1 `api.test.ts`의 네트워크 실패 테스트, Task 2 홈 화면 오류 표시.
2. 토론 중 SSE 연결이 끊길 때: 다시 불러오고, 아직 진행 중이면 재연결해야 한다(§7.3). → Task 3 `useDebate.test.ts`의 onerror 재연결 테스트.
3. 409/422 거절(소진 슬롯, 판정 AI 소진 상태에서 이어하기, 잘못된 키 이름): 백엔드의 한국어 `detail`이 버튼 근처에 보여야 한다. → Task 2 제출 실패 테스트, Task 4 이어하기 실패 테스트, Task 6 저장 실패 테스트.
4. 발언이 하나도 없이 끝난 토론(`result`에 `final_opinion` 없음, `grade: null`): 최종 카드가 깨지지 않고 "통합할 발언이 없습니다"와 종료 사유를 보여야 한다. → Task 4 `FinalResultCard` 테스트.
5. 일시정지·재시작 중단 토론: 이어하기 버튼과 사유 배너가 보이고, 진행 중 토론에는 중단 버튼만 보여야 한다. → Task 4 `ProgressHeader`·`Banners` 테스트.

---

## File Structure

```
frontend/
├── package.json, tsconfig.json, next.config.ts, vitest.config.ts, vitest.setup.ts, next-env.d.ts
└── src/
    ├── app/
    │   ├── layout.tsx            # 공통 레이아웃, 상단 메뉴
    │   ├── globals.css           # 어두운 테마(배너와 같은 보라·자홍 강조)
    │   ├── page.tsx              # 질문 화면 (/)
    │   ├── debates/[id]/page.tsx # 토론 결과 화면
    │   ├── history/page.tsx      # 기록 화면
    │   └── settings/page.tsx     # 설정 화면
    ├── lib/
    │   ├── types.ts              # 백엔드 응답 타입
    │   ├── api.ts                # fetch 래퍼 + 엔드포인트 함수
    │   ├── format.ts             # 한국어 표시 문자열, 날짜, 판정 도우미
    │   └── useDebate.ts          # 토론 상세 + SSE 실시간 갱신 훅
    └── components/
        ├── ErrorNotice.tsx
        ├── SlotBadge.tsx
        ├── QuestionForm.tsx
        ├── ProgressHeader.tsx
        ├── Banners.tsx
        ├── FinalResultCard.tsx
        ├── RoundList.tsx
        ├── HistoryTable.tsx
        ├── SlotEditor.tsx
        └── StallThresholdForm.tsx
```

테스트는 대상 파일 옆에 `*.test.ts(x)`로 둔다.

---

### Task 1: 프로젝트 뼈대, 공통 타입, API 클라이언트, 표시 도우미

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/next.config.ts`, `frontend/vitest.config.ts`, `frontend/vitest.setup.ts`, `frontend/next-env.d.ts`
- Create: `frontend/src/app/layout.tsx`, `frontend/src/app/globals.css`, `frontend/src/app/page.tsx`(임시)
- Create: `frontend/src/lib/types.ts`, `frontend/src/lib/api.ts`, `frontend/src/lib/format.ts`, `frontend/src/components/ErrorNotice.tsx`, `frontend/src/components/SlotBadge.tsx`
- Create: `frontend/src/test/fixtures.ts` (테스트용 데이터 생성 함수 — 테스트 파일이 아니므로 다른 테스트에서 가져와도 테스트가 중복 실행되지 않는다)
- Modify: `.gitignore` (루트) — `*.tsbuildinfo` 추가
- Test: `frontend/src/lib/api.test.ts`, `frontend/src/lib/format.test.ts`

**Interfaces:**
- Produces (`types.ts`): `Slot`, `SlotStatus`, `UsageSummary`, `DebateStatus`, `Grade`, `Opinion`, `JudgeEval`, `Message`, `Round`, `Participant`, `Dropout`, `FinalResult`, `DebateDetail`, `DebateSummary`, `AppConfig`, `UpdateSlotInput`
- Produces (`api.ts`): `API_BASE: string`, `class ApiError(status: number, message: string)`, `errorMessage(error: unknown): string`, `listSlots(): Promise<Slot[]>`, `updateSlot(id: number, input: UpdateSlotInput): Promise<Slot>`, `getConfig(): Promise<AppConfig>`, `updateConfig(stallThreshold: number): Promise<AppConfig>`, `createDebate(question: string, slotIds: number[]): Promise<{ id: number }>`, `listDebates(): Promise<DebateSummary[]>`, `getDebate(id: number): Promise<DebateDetail>`, `stopDebate(id: number): Promise<void>`, `resumeDebate(id: number): Promise<void>`, `eventsUrl(id: number): string`
- Produces (`format.ts`): `DEBATE_STATUS_LABEL`, `GRADE_LABEL`, `JUDGE_STATUS_LABEL`, `SLOT_STATUS_LABEL`, `providerLabel(id: string): string`, `formatDateTime(iso: string | null): string`, `formatPercent(ratio: number | null): string`, `canResume(debate: Pick<DebateDetail, "status" | "ended_at">): boolean`, `slotUnavailableReason(slot: Slot): string | null`
- Produces: `<ErrorNotice message={string | null} />`, `<SlotBadge slot={Slot} />`, `makeSlot(overrides?: Partial<Slot>): Slot` (`src/test/fixtures.ts`)

- [ ] **Step 1: 설정 파일 작성**

`frontend/package.json`:

```json
{
  "name": "ai-roundtable-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev -H localhost -p 3000",
    "build": "next build",
    "start": "next start -H localhost -p 3000",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "15.5.27",
    "react": "19.3.0",
    "react-dom": "19.3.0"
  },
  "devDependencies": {
    "@testing-library/dom": "10.4.2",
    "@testing-library/jest-dom": "6.10.0",
    "@testing-library/react": "16.3.3",
    "@testing-library/user-event": "14.6.7",
    "@types/node": "22.20.5",
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "4.7.0",
    "jsdom": "26.1.0",
    "typescript": "5.9.3",
    "vitest": "3.2.7"
  }
}
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "es2022"],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "types": ["node", "vitest/globals", "@testing-library/jest-dom"],
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

`frontend/next.config.ts`:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ESLint는 쓰지 않는다. 타입 검사는 npm run typecheck로 한다.
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
```

`frontend/vitest.config.ts`:

```ts
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    env: { TZ: "Asia/Seoul" },
  },
});
```

`frontend/vitest.setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
```

`frontend/next-env.d.ts`:

```ts
/// <reference types="next" />
/// <reference types="next/image-types/global" />

// NOTE: This file should not be edited
// see https://nextjs.org/docs/app/api-reference/config/typescript for more information.
```

(`next build`/`next dev`가 이 파일을 다시 쓸 수 있다. 그러면 Next가 쓴 내용 그대로 커밋한다.)

루트 `.gitignore` 끝에 한 줄 추가:

```
*.tsbuildinfo
```

- [ ] **Step 2: 의존성 설치**

Run: `cd frontend && npm install`
Expected: `added N packages`, 오류 없음. `package-lock.json`이 생긴다(커밋 대상).

- [ ] **Step 3: 공통 타입 작성**

`frontend/src/lib/types.ts`:

```ts
export type SlotStatus = "available" | "rate_limited" | "exhausted";

export interface UsageSummary {
  today_requests: number;
  today_tokens: number;
  total_requests: number;
  total_tokens: number;
}

export interface Slot {
  id: number;
  kind: "participant" | "judge";
  provider: string;
  model: string;
  api_key_env: string;
  key_present: boolean;
  status: SlotStatus;
  status_until: string | null;
  status_reason: string | null;
  known_limit: Record<string, number> | null;
  usage: UsageSummary;
  usage_estimate: number | null;
}

export type DebateStatus = "running" | "paused" | "converged" | "stalled" | "stopped" | "interrupted";
export type Grade = "consensus" | "partial" | "no_consensus";

export interface Opinion {
  position: string;
  reasons: string[];
  conditions: string[];
  confidence: number;
  changes?: string;
  rebuttals?: string[];
}

export interface JudgeEval {
  status: "converged" | "progressing" | "stalled";
  issues: string[];
  draft: string;
}

export interface Message {
  label: string;
  provider: string;
  model: string;
  content: Opinion | null;
  error: string | null;
  input_tokens: number;
  output_tokens: number;
  latency_ms: number;
}

export interface Round {
  number: number;
  judge_eval: JudgeEval | null;
  completed_at: string | null;
  messages: Message[];
}

export interface Participant {
  label: string;
  slot_id: number;
  provider: string;
  model: string;
}

export interface Dropout {
  label: string;
  provider: string;
  model: string;
  round: number;
  reason: string;
}

export interface FinalResult {
  final_opinion?: string;
  grade?: Grade;
  key_reasons?: string[];
  dissents?: { label: string; reason: string }[];
  uncertainties?: string[];
  dropouts: Dropout[];
  end_reason: string;
}

export interface DebateDetail {
  id: number;
  question: string;
  status: DebateStatus;
  grade: Grade | null;
  result: FinalResult | null;
  participants: Participant[];
  dropouts: Dropout[] | null;
  stall_threshold: number;
  pause_reason: string | null;
  started_at: string | null;
  ended_at: string | null;
  rounds: Round[];
}

export interface DebateSummary {
  id: number;
  question: string;
  status: DebateStatus;
  grade: Grade | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface AppConfig {
  stall_threshold: number;
  providers: string[];
}

export interface UpdateSlotInput {
  provider: string;
  model: string;
  api_key_env: string;
  known_limit: Record<string, number> | null;
}
```

- [ ] **Step 4: API 클라이언트 실패 테스트 작성**

`frontend/src/lib/api.test.ts`:

```ts
import { describe, expect, it, vi } from "vitest";
import { API_BASE, ApiError, createDebate, errorMessage, eventsUrl, getDebate, stopDebate } from "./api";

function mockFetch(response: Partial<Response> | Error) {
  const fn = vi.fn(async () => {
    if (response instanceof Error) throw response;
    return response as Response;
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function jsonResponse(status: number, body: unknown): Partial<Response> {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

describe("api", () => {
  it("GET은 JSON을 돌려주고 Content-Type을 보내지 않는다", async () => {
    const fetchMock = mockFetch(jsonResponse(200, { id: 3, rounds: [] }));
    const debate = await getDebate(3);
    expect(debate.id).toBe(3);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${API_BASE}/debates/3`);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
  });

  it("POST는 JSON 본문과 Content-Type을 보낸다", async () => {
    const fetchMock = mockFetch(jsonResponse(201, { id: 7 }));
    await expect(createDebate("질문", [1, 2])).resolves.toEqual({ id: 7 });
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
    expect(JSON.parse(init.body as string)).toEqual({ question: "질문", slot_ids: [1, 2] });
  });

  it("오류 응답의 한국어 detail을 ApiError 메시지로 쓴다", async () => {
    mockFetch(jsonResponse(409, { detail: "판정 AI gemini (x): 무료 크레딧 소진" }));
    const error = await stopDebate(1).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).message).toBe("판정 AI gemini (x): 무료 크레딧 소진");
  });

  it("detail이 없으면 HTTP 상태 코드로 안내한다", async () => {
    mockFetch({ ok: false, status: 500, json: async () => { throw new Error("not json"); } });
    await expect(getDebate(1)).rejects.toThrow("요청이 실패했습니다 (HTTP 500)");
  });

  it("서버에 연결할 수 없으면 한국어 안내를 준다", async () => {
    mockFetch(new TypeError("Failed to fetch"));
    const error = await getDebate(1).catch((e: unknown) => e);
    expect((error as ApiError).status).toBe(0);
    expect(errorMessage(error)).toContain("백엔드 서버에 연결할 수 없습니다");
  });

  it("errorMessage는 알 수 없는 값도 문자열로 만든다", () => {
    expect(errorMessage("x")).toBe("알 수 없는 오류가 발생했습니다");
  });

  it("eventsUrl은 SSE 주소를 만든다", () => {
    expect(eventsUrl(5)).toBe(`${API_BASE}/debates/5/events`);
  });
});
```

- [ ] **Step 5: 테스트가 실패하는지 확인**

Run: `cd frontend && npm test -- src/lib/api.test.ts`
Expected: FAIL — `Failed to resolve import "./api"`

- [ ] **Step 6: API 클라이언트 구현**

`frontend/src/lib/api.ts`:

```ts
import type { AppConfig, DebateDetail, DebateSummary, Slot, UpdateSlotInput } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const UNREACHABLE =
  "백엔드 서버에 연결할 수 없습니다. 백엔드가 127.0.0.1:8000에서 실행 중인지 확인하세요.";

export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "알 수 없는 오류가 발생했습니다";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  if (!response.ok) {
    let message = `요청이 실패했습니다 (HTTP ${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      // 본문이 JSON이 아니면 기본 메시지를 쓴다
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
}

export const listSlots = () => request<Slot[]>("/slots");
export const updateSlot = (id: number, input: UpdateSlotInput) => send<Slot>("PUT", `/slots/${id}`, input);
export const getConfig = () => request<AppConfig>("/config");
export const updateConfig = (stallThreshold: number) =>
  send<AppConfig>("PUT", "/config", { stall_threshold: stallThreshold });
export const createDebate = (question: string, slotIds: number[]) =>
  send<{ id: number }>("POST", "/debates", { question, slot_ids: slotIds });
export const listDebates = () => request<DebateSummary[]>("/debates");
export const getDebate = (id: number) => request<DebateDetail>(`/debates/${id}`);
export const stopDebate = async (id: number) => {
  await send<unknown>("POST", `/debates/${id}/stop`);
};
export const resumeDebate = async (id: number) => {
  await send<unknown>("POST", `/debates/${id}/resume`);
};
export const eventsUrl = (id: number) => `${API_BASE}/debates/${id}/events`;
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd frontend && npm test -- src/lib/api.test.ts`
Expected: PASS (7 tests)

- [ ] **Step 8: 표시 도우미 실패 테스트 작성**

`frontend/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { makeSlot } from "@/test/fixtures";
import { canResume, formatDateTime, formatPercent, providerLabel, slotUnavailableReason } from "./format";

describe("format", () => {
  it("UTC Z 시간을 서울 시간으로 표시한다", () => {
    expect(formatDateTime("2026-10-12T05:00:00Z")).toContain("오후 2:00");
  });

  it("빈 값이나 잘못된 시간은 대시로 표시한다", () => {
    expect(formatDateTime(null)).toBe("—");
    expect(formatDateTime("not-a-date")).toBe("—");
  });

  it("비율을 퍼센트로 바꾼다", () => {
    expect(formatPercent(0.4)).toBe("40%");
    expect(formatPercent(null)).toBe("—");
  });

  it("알려진 회사는 이름으로, 모르는 회사는 원문으로 보여 준다", () => {
    expect(providerLabel("xai")).toBe("xAI Grok");
    expect(providerLabel("mystery")).toBe("mystery");
  });

  it("일시정지와 끝나지 않은 중단만 이어할 수 있다", () => {
    expect(canResume({ status: "paused", ended_at: null })).toBe(true);
    expect(canResume({ status: "interrupted", ended_at: null })).toBe(true);
    expect(canResume({ status: "interrupted", ended_at: "2026-10-12T05:00:00Z" })).toBe(false);
    expect(canResume({ status: "converged", ended_at: "2026-10-12T05:00:00Z" })).toBe(false);
    expect(canResume({ status: "running", ended_at: null })).toBe(false);
  });

  it("키가 없거나 소진된 슬롯은 쓸 수 없는 이유를 준다", () => {
    expect(slotUnavailableReason(makeSlot())).toBeNull();
    expect(slotUnavailableReason(makeSlot({ status: "rate_limited" }))).toBeNull();
    expect(slotUnavailableReason(makeSlot({ key_present: false }))).toBe("OPENAI_API_KEY 키 없음");
    expect(slotUnavailableReason(makeSlot({ status: "exhausted", status_reason: "무료 크레딧 소진: x" }))).toBe(
      "무료 크레딧 소진: x",
    );
    expect(slotUnavailableReason(makeSlot({ status: "exhausted" }))).toBe("무료 제공량 소진");
  });
});
```

`frontend/src/test/fixtures.ts`:

```ts
import type { Slot } from "@/lib/types";

export function makeSlot(overrides: Partial<Slot> = {}): Slot {
  return {
    id: 1, kind: "participant", provider: "openai", model: "gpt-4o-mini", api_key_env: "OPENAI_API_KEY",
    key_present: true, status: "available", status_until: null, status_reason: null, known_limit: null,
    usage: { today_requests: 0, today_tokens: 0, total_requests: 0, total_tokens: 0 }, usage_estimate: null,
    ...overrides,
  };
}
```

- [ ] **Step 9: 테스트가 실패하는지 확인**

Run: `cd frontend && npm test -- src/lib/format.test.ts`
Expected: FAIL — `Failed to resolve import "./format"`

- [ ] **Step 10: 표시 도우미 구현**

`frontend/src/lib/format.ts`:

```ts
import type { DebateDetail, DebateStatus, Grade, JudgeEval, Slot, SlotStatus } from "./types";

export const DEBATE_STATUS_LABEL: Record<DebateStatus, string> = {
  running: "진행 중",
  paused: "일시정지",
  converged: "수렴",
  stalled: "정체",
  stopped: "사용자 중단",
  interrupted: "중단됨",
};

export const GRADE_LABEL: Record<Grade, string> = {
  consensus: "합의",
  partial: "조건부·부분 합의",
  no_consensus: "미합의",
};

export const JUDGE_STATUS_LABEL: Record<JudgeEval["status"], string> = {
  converged: "수렴",
  progressing: "진행 중",
  stalled: "정체",
};

export const SLOT_STATUS_LABEL: Record<SlotStatus, string> = {
  available: "사용 가능",
  rate_limited: "속도 제한",
  exhausted: "소진",
};

const PROVIDER_LABEL: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Anthropic",
  gemini: "Google Gemini",
  xai: "xAI Grok",
  openrouter: "OpenRouter",
  groq: "Groq",
};

export function providerLabel(id: string): string {
  return PROVIDER_LABEL[id] ?? id;
}

const DATE_TIME = new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" });

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "—" : DATE_TIME.format(date);
}

export function formatPercent(ratio: number | null): string {
  return ratio === null ? "—" : `${Math.round(ratio * 100)}%`;
}

export function canResume(debate: Pick<DebateDetail, "status" | "ended_at">): boolean {
  return debate.status === "paused" || (debate.status === "interrupted" && debate.ended_at === null);
}

export function slotUnavailableReason(slot: Slot): string | null {
  if (!slot.key_present) return `${slot.api_key_env} 키 없음`;
  if (slot.status === "exhausted") return slot.status_reason ?? "무료 제공량 소진";
  return null;
}
```

- [ ] **Step 11: 테스트 통과 확인**

Run: `cd frontend && npm test -- src/lib/format.test.ts`
Expected: PASS (6 tests)

- [ ] **Step 12: 공통 컴포넌트, 레이아웃, 테마 작성**

`frontend/src/components/ErrorNotice.tsx`:

```tsx
export function ErrorNotice({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <p className="notice notice-error" role="alert">
      {message}
    </p>
  );
}
```

`frontend/src/components/SlotBadge.tsx`:

```tsx
import { SLOT_STATUS_LABEL, slotUnavailableReason } from "@/lib/format";
import type { Slot } from "@/lib/types";

export function SlotBadge({ slot }: { slot: Slot }) {
  const tone = !slot.key_present || slot.status === "exhausted" ? "bad" : slot.status === "rate_limited" ? "warn" : "ok";
  const text = slot.key_present ? SLOT_STATUS_LABEL[slot.status] : "키 없음";
  const title = slotUnavailableReason(slot) ?? slot.status_reason ?? undefined;
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {text}
    </span>
  );
}
```

`frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Roundtable",
  description: "여러 AI가 토론해 하나의 통합 의견을 만드는 개인용 도구",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>
        <header className="topbar">
          <Link href="/" className="brand">
            <span className="brand-mark" aria-hidden="true" />
            Roundtable
          </Link>
          <nav className="nav">
            <Link href="/">질문</Link>
            <Link href="/history">기록</Link>
            <Link href="/settings">설정</Link>
          </nav>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
```

`frontend/src/app/globals.css`:

```css
:root {
  --bg: #0b0a14;
  --panel: rgba(255, 255, 255, 0.04);
  --panel-strong: rgba(255, 255, 255, 0.07);
  --border: rgba(255, 255, 255, 0.1);
  --text: #f3f1fa;
  --muted: #a39fb8;
  --accent-1: #a855f7;
  --accent-2: #ec4899;
  --ok: #34d399;
  --warn: #fbbf24;
  --bad: #f87171;
  --radius: 14px;
  color-scheme: dark;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: radial-gradient(1200px 600px at 10% -10%, rgba(168, 85, 247, 0.18), transparent 60%),
    radial-gradient(900px 500px at 110% 10%, rgba(236, 72, 153, 0.12), transparent 60%), var(--bg);
  color: var(--text);
  font-family: "Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif;
  line-height: 1.6;
  min-height: 100vh;
}

a { color: inherit; }

.topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px; border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 10px; font-weight: 800; font-size: 20px; text-decoration: none; }
.brand-mark {
  width: 18px; height: 18px; border-radius: 50%;
  background: conic-gradient(var(--accent-1), var(--accent-2), #f97316, #3b82f6, var(--accent-1));
}
.nav { display: flex; gap: 18px; }
.nav a { color: var(--muted); text-decoration: none; }
.nav a:hover { color: var(--text); }

.container { max-width: 960px; margin: 0 auto; padding: 32px 16px 64px; }

h1 { font-size: 28px; margin: 0 0 16px; }
h2 { font-size: 20px; margin: 24px 0 12px; }
.gradient-text {
  background: linear-gradient(90deg, var(--accent-1), var(--accent-2));
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.muted { color: var(--muted); }

.panel { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.panel + .panel { margin-top: 16px; }
.stack { display: flex; flex-direction: column; gap: 12px; }
.row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }

textarea, input, select {
  width: 100%; background: var(--panel-strong); color: var(--text);
  border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; font: inherit;
}
textarea { min-height: 120px; resize: vertical; }
input[type="checkbox"] { width: auto; }
label { display: block; }

button {
  border: 0; border-radius: 10px; padding: 10px 18px; font: inherit; font-weight: 700; cursor: pointer;
  color: white; background: linear-gradient(90deg, var(--accent-1), var(--accent-2));
}
button.secondary { background: var(--panel-strong); border: 1px solid var(--border); }
button:disabled { opacity: 0.4; cursor: not-allowed; }

.badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 13px; font-weight: 700; }
.badge-ok { background: rgba(52, 211, 153, 0.15); color: var(--ok); }
.badge-warn { background: rgba(251, 191, 36, 0.15); color: var(--warn); }
.badge-bad { background: rgba(248, 113, 113, 0.15); color: var(--bad); }
.badge-accent { background: rgba(168, 85, 247, 0.2); color: #d8b4fe; }

.notice { border-radius: 10px; padding: 12px 14px; margin: 12px 0; }
.notice-error { background: rgba(248, 113, 113, 0.12); border: 1px solid rgba(248, 113, 113, 0.4); }
.notice-warn { background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.35); }

.slot-option { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; background: var(--panel-strong); }
.slot-option[data-disabled="true"] { opacity: 0.5; }

.final-card { border: 1px solid rgba(168, 85, 247, 0.5); background: linear-gradient(160deg, rgba(168, 85, 247, 0.12), rgba(236, 72, 153, 0.06)); }
.final-opinion { font-size: 18px; white-space: pre-wrap; }

details.round { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px; }
details.round + details.round { margin-top: 10px; }
details.round summary { cursor: pointer; font-weight: 700; }
.message { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 12px; }

table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; font-size: 14px; }
.question-cell { max-width: 420px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
```

`frontend/src/app/page.tsx` (Task 2에서 교체할 임시 화면):

```tsx
export default function HomePage() {
  return <h1>Roundtable</h1>;
}
```

- [ ] **Step 13: 전체 테스트·타입 검사·빌드 확인**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: 테스트 13개 PASS, 타입 오류 없음, `next build`가 `✓ Compiled successfully`로 끝남. (빌드는 `.next/`를 만들며 Git에 올라가지 않는다.)

- [ ] **Step 14: 커밋**

```bash
git add .gitignore frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/next.config.ts \
  frontend/vitest.config.ts frontend/vitest.setup.ts frontend/next-env.d.ts frontend/src
git commit -m "feat: scaffold frontend with API client, types and dark theme

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: 질문 화면 (`/`)

**Files:**
- Create: `frontend/src/components/QuestionForm.tsx`
- Modify: `frontend/src/app/page.tsx` (임시 화면 교체)
- Test: `frontend/src/components/QuestionForm.test.tsx`

**Interfaces:**
- Consumes: `Slot` (types), `slotUnavailableReason`, `providerLabel` (format), `SlotBadge`, `ErrorNotice`, `listSlots`, `createDebate`, `errorMessage` (api)
- Produces: `<QuestionForm slots={Slot[]} onSubmit={(question: string, slotIds: number[]) => Promise<void>} />`

- [ ] **Step 1: 실패 테스트 작성** (설계 문서 §8: 소진 슬롯 비활성화, 판정 슬롯 소진 시 시작 버튼 비활성화)

`frontend/src/components/QuestionForm.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeSlot } from "@/test/fixtures";
import type { Slot } from "@/lib/types";
import { QuestionForm } from "./QuestionForm";

function slots(overrides: Record<number, Partial<Slot>> = {}): Slot[] {
  const base: Slot[] = [
    makeSlot({ id: 1, provider: "openai", model: "gpt-4o-mini" }),
    makeSlot({ id: 2, provider: "anthropic", model: "claude-haiku-4-5", api_key_env: "ANTHROPIC_API_KEY" }),
    makeSlot({ id: 3, provider: "gemini", model: "gemini-2.5-flash", api_key_env: "GEMINI_API_KEY" }),
    makeSlot({ id: 4, provider: "xai", model: "grok-3-mini", api_key_env: "XAI_API_KEY" }),
    makeSlot({ id: 5, kind: "judge", provider: "gemini", model: "gemini-2.5-flash-lite", api_key_env: "GEMINI_API_KEY" }),
  ];
  return base.map((slot) => ({ ...slot, ...overrides[slot.id] }));
}

describe("QuestionForm", () => {
  it("쓸 수 있는 참여 슬롯 4개가 기본으로 모두 선택된다", () => {
    render(<QuestionForm slots={slots()} onSubmit={vi.fn()} />);
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes).toHaveLength(4);
    for (const box of boxes) expect(box).toBeChecked();
  });

  it("소진되거나 키가 없는 슬롯은 선택할 수 없고 이유를 보여 준다", () => {
    render(
      <QuestionForm
        slots={slots({ 2: { status: "exhausted", status_reason: "무료 크레딧 소진: billing" }, 4: { key_present: false } })}
        onSubmit={vi.fn()}
      />,
    );
    const claude = screen.getByRole("checkbox", { name: /claude-haiku-4-5/ });
    const grok = screen.getByRole("checkbox", { name: /grok-3-mini/ });
    expect(claude).toBeDisabled();
    expect(claude).not.toBeChecked();
    expect(grok).toBeDisabled();
    expect(screen.getByText("무료 크레딧 소진: billing")).toBeInTheDocument();
    expect(screen.getByText("XAI_API_KEY 키 없음")).toBeInTheDocument();
  });

  it("판정 슬롯이 소진되면 시작 버튼이 꺼지고 이유가 보인다", async () => {
    render(
      <QuestionForm slots={slots({ 5: { status: "exhausted", status_reason: "일일 한도 소진: quota" } })} onSubmit={vi.fn()} />,
    );
    await userEvent.type(screen.getByLabelText("질문"), "자동 배포해도 되나요?");
    expect(screen.getByRole("button", { name: "토론 시작" })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("판정 AI를 쓸 수 없어 토론을 시작할 수 없습니다: 일일 한도 소진: quota");
  });

  it("질문이 비어 있거나 참여 슬롯이 하나도 없으면 시작할 수 없다", async () => {
    render(<QuestionForm slots={slots()} onSubmit={vi.fn()} />);
    const start = screen.getByRole("button", { name: "토론 시작" });
    expect(start).toBeDisabled();
    await userEvent.type(screen.getByLabelText("질문"), "   ");
    expect(start).toBeDisabled();
    await userEvent.type(screen.getByLabelText("질문"), "질문");
    expect(start).toBeEnabled();
    for (const box of screen.getAllByRole("checkbox")) await userEvent.click(box);
    expect(start).toBeDisabled();
  });

  it("다듬은 질문과 선택한 슬롯 번호로 제출한다", async () => {
    const onSubmit = vi.fn(async () => {});
    render(<QuestionForm slots={slots()} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByLabelText("질문"), "  자동 배포해도 되나요?  ");
    await userEvent.click(screen.getByRole("checkbox", { name: /gpt-4o-mini/ }));
    await userEvent.click(screen.getByRole("button", { name: "토론 시작" }));
    expect(onSubmit).toHaveBeenCalledWith("자동 배포해도 되나요?", [2, 3, 4]);
  });

  it("제출이 거절되면 백엔드 메시지를 보여 주고 다시 시도할 수 있다", async () => {
    const onSubmit = vi.fn(async () => {
      throw new Error("참여 AI anthropic (claude-haiku-4-5): 무료 크레딧 소진");
    });
    render(<QuestionForm slots={slots()} onSubmit={onSubmit} />);
    await userEvent.type(screen.getByLabelText("질문"), "질문");
    await userEvent.click(screen.getByRole("button", { name: "토론 시작" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("무료 크레딧 소진"));
    expect(screen.getByRole("button", { name: "토론 시작" })).toBeEnabled();
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd frontend && npm test -- src/components/QuestionForm.test.tsx`
Expected: FAIL — `Failed to resolve import "./QuestionForm"`

- [ ] **Step 3: 컴포넌트 구현**

`frontend/src/components/QuestionForm.tsx`:

```tsx
"use client";

import { type FormEvent, useState } from "react";
import { errorMessage } from "@/lib/api";
import { providerLabel, slotUnavailableReason } from "@/lib/format";
import type { Slot } from "@/lib/types";
import { ErrorNotice } from "./ErrorNotice";
import { SlotBadge } from "./SlotBadge";

interface Props {
  slots: Slot[];
  onSubmit: (question: string, slotIds: number[]) => Promise<void>;
}

export function QuestionForm({ slots, onSubmit }: Props) {
  const participants = slots.filter((slot) => slot.kind === "participant");
  const judge = slots.find((slot) => slot.kind === "judge");
  const judgeProblem = judge ? slotUnavailableReason(judge) : "판정 슬롯 정보를 불러오지 못했습니다";

  const [question, setQuestion] = useState("");
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(participants.filter((slot) => slotUnavailableReason(slot) === null).map((slot) => slot.id)),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = question.trim();
  const canStart = trimmed !== "" && selected.size > 0 && judgeProblem === null && !submitting;

  function toggle(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canStart) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(trimmed, participants.filter((slot) => selected.has(slot.id)).map((slot) => slot.id));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <label>
        <span className="muted">질문</span>
        <textarea
          aria-label="질문"
          value={question}
          maxLength={4000}
          placeholder="여러 AI의 의견을 듣고 싶은 질문을 입력하세요"
          onChange={(event) => setQuestion(event.target.value)}
        />
      </label>

      <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="muted">참여 AI (1~4개)</legend>
        {participants.map((slot) => {
          const problem = slotUnavailableReason(slot);
          return (
            <label key={slot.id} className="slot-option" data-disabled={problem !== null}>
              <input
                type="checkbox"
                checked={selected.has(slot.id)}
                disabled={problem !== null}
                onChange={() => toggle(slot.id)}
              />
              <span>
                {providerLabel(slot.provider)} · {slot.model}
              </span>
              <SlotBadge slot={slot} />
              {problem && <span className="muted">{problem}</span>}
            </label>
          );
        })}
      </fieldset>

      {judge && (
        <p className="muted">
          판정 AI: {providerLabel(judge.provider)} · {judge.model} <SlotBadge slot={judge} />
        </p>
      )}
      {judgeProblem && <ErrorNotice message={`판정 AI를 쓸 수 없어 토론을 시작할 수 없습니다: ${judgeProblem}`} />}
      <ErrorNotice message={error} />

      <div className="row">
        <button type="submit" disabled={!canStart}>
          {submitting ? "시작하는 중…" : "토론 시작"}
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd frontend && npm test -- src/components/QuestionForm.test.tsx`
Expected: PASS (6 tests)

- [ ] **Step 5: 질문 화면 연결**

`frontend/src/app/page.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { QuestionForm } from "@/components/QuestionForm";
import { createDebate, errorMessage, listSlots } from "@/lib/api";
import type { Slot } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSlots().then(setSlots, (caught) => setError(errorMessage(caught)));
  }, []);

  async function start(question: string, slotIds: number[]) {
    const { id } = await createDebate(question, slotIds);
    router.push(`/debates/${id}`);
  }

  return (
    <>
      <h1>
        여러 AI에게 묻고, <span className="gradient-text">하나의 결론</span>으로
      </h1>
      <p className="muted">참여 AI들이 서로 검토·반박한 뒤 판정 AI가 통합 의견을 만듭니다.</p>
      <ErrorNotice message={error} />
      {slots === null && !error && <p className="muted">슬롯 정보를 불러오는 중…</p>}
      {slots && (
        <section className="panel">
          <QuestionForm slots={slots} onSubmit={start} />
        </section>
      )}
    </>
  );
}
```

- [ ] **Step 6: 전체 테스트·타입 검사**

Run: `cd frontend && npm test && npm run typecheck`
Expected: PASS (19 tests), 타입 오류 없음

- [ ] **Step 7: 커밋**

```bash
git add frontend/src/components/QuestionForm.tsx frontend/src/components/QuestionForm.test.tsx frontend/src/app/page.tsx
git commit -m "feat: add question screen with slot selection

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: 토론 실시간 갱신 훅 (`useDebate`)

**Files:**
- Create: `frontend/src/lib/useDebate.ts`
- Test: `frontend/src/lib/useDebate.test.ts`

**Interfaces:**
- Consumes: `getDebate`, `eventsUrl`, `errorMessage` (api), `DebateDetail` (types)
- Produces:
  - `interface EventSourceLike { addEventListener(type: string, listener: (event: MessageEvent) => void): void; close(): void; onerror: ((event: Event) => void) | null }`
  - `const DEBATE_EVENT_TYPES: readonly string[]` — `round_started`, `message`, `judge_evaluated`, `participant_dropped`, `paused`, `finished`, `error`, `status`
  - `function useDebate(id: number, options?: { createEventSource?: (url: string) => EventSourceLike; reconnectMs?: number }): { debate: DebateDetail | null; error: string | null; live: boolean; refresh: () => Promise<DebateDetail | null>; reconnect: () => void }`

동작 규칙(§7.3):
- 처음에 `GET /debates/{id}`를 부른다. 상태가 `running`일 때만 SSE에 연결한다.
- SSE 이벤트를 받을 때마다 상세를 다시 불러온다. `paused`, `finished`, `error`, `status`를 받으면 연결을 닫는다(서버도 이 뒤에 스트림을 끝낸다).
- 연결 오류(`onerror`)가 나면 연결을 닫고 `reconnectMs`(기본 2000ms) 뒤에 다시 불러온다. 그때도 `running`이면 다시 연결한다.
- `reconnect()`는 이어하기 직후 쓴다. 상세를 다시 불러오고 진행 중이면 연결한다.
- 언마운트되면 연결과 타이머를 모두 정리한다.

- [ ] **Step 1: 실패 테스트 작성**

`frontend/src/lib/useDebate.test.ts`:

```ts
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import type { DebateDetail } from "./types";
import { type EventSourceLike, useDebate } from "./useDebate";

vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  getDebate: vi.fn(),
}));
const getDebate = vi.mocked(api.getDebate);

class FakeSource implements EventSourceLike {
  static created: FakeSource[] = [];
  listeners = new Map<string, ((event: MessageEvent) => void)[]>();
  onerror: ((event: Event) => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeSource.created.push(this);
  }
  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }
  close() {
    this.closed = true;
  }
  emit(type: string) {
    for (const listener of this.listeners.get(type) ?? []) listener(new MessageEvent(type, { data: "{}" }));
  }
}

const createEventSource = (url: string) => new FakeSource(url);

function detail(status: DebateDetail["status"]): DebateDetail {
  return {
    id: 1, question: "q", status, grade: null, result: null, participants: [], dropouts: [], stall_threshold: 2,
    pause_reason: null, started_at: "2026-10-12T05:00:00Z", ended_at: null, rounds: [],
  };
}

beforeEach(() => {
  FakeSource.created = [];
  getDebate.mockReset();
});

describe("useDebate", () => {
  it("끝난 토론에는 SSE를 연결하지 않는다", async () => {
    getDebate.mockResolvedValue(detail("converged"));
    const { result } = renderHook(() => useDebate(1, { createEventSource }));
    await waitFor(() => expect(result.current.debate?.status).toBe("converged"));
    expect(FakeSource.created).toHaveLength(0);
    expect(result.current.live).toBe(false);
  });

  it("진행 중이면 연결하고, 이벤트마다 다시 불러오고, 종료 이벤트에서 닫는다", async () => {
    getDebate.mockResolvedValue(detail("running"));
    const { result } = renderHook(() => useDebate(1, { createEventSource }));
    await waitFor(() => expect(FakeSource.created).toHaveLength(1));
    const source = FakeSource.created[0];
    expect(source.url).toBe(api.eventsUrl(1));
    expect(result.current.live).toBe(true);

    act(() => source.emit("message"));
    await waitFor(() => expect(getDebate).toHaveBeenCalledTimes(2));

    getDebate.mockResolvedValue(detail("converged"));
    act(() => source.emit("finished"));
    await waitFor(() => expect(result.current.debate?.status).toBe("converged"));
    expect(source.closed).toBe(true);
    expect(result.current.live).toBe(false);
  });

  it("연결이 끊기면 다시 불러온 뒤 아직 진행 중이면 재연결한다", async () => {
    getDebate.mockResolvedValue(detail("running"));
    renderHook(() => useDebate(1, { createEventSource, reconnectMs: 10 }));
    await waitFor(() => expect(FakeSource.created).toHaveLength(1));
    act(() => FakeSource.created[0].onerror?.(new Event("error")));
    expect(FakeSource.created[0].closed).toBe(true);
    await waitFor(() => expect(FakeSource.created).toHaveLength(2));
  });

  it("상세를 못 불러오면 한국어 오류를 보여 준다", async () => {
    getDebate.mockRejectedValue(new api.ApiError(404, "토론을 찾을 수 없습니다"));
    const { result } = renderHook(() => useDebate(1, { createEventSource }));
    await waitFor(() => expect(result.current.error).toBe("토론을 찾을 수 없습니다"));
    expect(FakeSource.created).toHaveLength(0);
  });

  it("reconnect는 이어하기 뒤 다시 연결한다", async () => {
    getDebate.mockResolvedValue(detail("paused"));
    const { result } = renderHook(() => useDebate(1, { createEventSource }));
    await waitFor(() => expect(result.current.debate?.status).toBe("paused"));
    expect(FakeSource.created).toHaveLength(0);
    getDebate.mockResolvedValue(detail("running"));
    act(() => result.current.reconnect());
    await waitFor(() => expect(FakeSource.created).toHaveLength(1));
  });

  it("언마운트하면 연결을 닫는다", async () => {
    getDebate.mockResolvedValue(detail("running"));
    const { unmount } = renderHook(() => useDebate(1, { createEventSource }));
    await waitFor(() => expect(FakeSource.created).toHaveLength(1));
    unmount();
    expect(FakeSource.created[0].closed).toBe(true);
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd frontend && npm test -- src/lib/useDebate.test.ts`
Expected: FAIL — `Failed to resolve import "./useDebate"`

- [ ] **Step 3: 훅 구현**

`frontend/src/lib/useDebate.ts`:

```ts
"use client";

import { useCallback, useEffect, useState } from "react";
import { errorMessage, eventsUrl, getDebate } from "./api";
import type { DebateDetail } from "./types";

export interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent) => void): void;
  close(): void;
  onerror: ((event: Event) => void) | null;
}

export const DEBATE_EVENT_TYPES = [
  "round_started", "message", "judge_evaluated", "participant_dropped", "paused", "finished", "error", "status",
] as const;
const TERMINAL_EVENT_TYPES: readonly string[] = ["paused", "finished", "error", "status"];

const browserEventSource = (url: string): EventSourceLike => new EventSource(url);

interface Options {
  createEventSource?: (url: string) => EventSourceLike;
  reconnectMs?: number;
}

export function useDebate(id: number, { createEventSource = browserEventSource, reconnectMs = 2000 }: Options = {}) {
  const [debate, setDebate] = useState<DebateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [generation, setGeneration] = useState(0);

  const refresh = useCallback(async (): Promise<DebateDetail | null> => {
    try {
      const next = await getDebate(id);
      setDebate(next);
      setError(null);
      return next;
    } catch (caught) {
      setError(errorMessage(caught));
      return null;
    }
  }, [id]);

  useEffect(() => {
    let disposed = false;
    let source: EventSourceLike | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const close = () => {
      source?.close();
      source = null;
      setLive(false);
    };

    const connect = async () => {
      const current = await refresh();
      if (disposed || current === null || current.status !== "running") return;
      const opened = createEventSource(eventsUrl(id));
      source = opened;
      setLive(true);
      for (const type of DEBATE_EVENT_TYPES) {
        opened.addEventListener(type, () => {
          if (source !== opened) return;
          if (TERMINAL_EVENT_TYPES.includes(type)) close();
          void refresh();
        });
      }
      opened.onerror = () => {
        if (source !== opened) return;
        close();
        if (!disposed) retry = setTimeout(() => void connect(), reconnectMs);
      };
    };

    void connect();
    return () => {
      disposed = true;
      clearTimeout(retry);
      close();
    };
  }, [id, refresh, createEventSource, reconnectMs, generation]);

  const reconnect = useCallback(() => setGeneration((value) => value + 1), []);

  return { debate, error, live, refresh, reconnect };
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd frontend && npm test -- src/lib/useDebate.test.ts`
Expected: PASS (6 tests), 경고 없음

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/lib/useDebate.ts frontend/src/lib/useDebate.test.ts
git commit -m "feat: add debate hook with SSE live refresh and reconnect

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: 토론 결과 화면 (`/debates/[id]`)

**Files:**
- Create: `frontend/src/components/ProgressHeader.tsx`, `frontend/src/components/Banners.tsx`, `frontend/src/components/FinalResultCard.tsx`, `frontend/src/components/RoundList.tsx`
- Create: `frontend/src/app/debates/[id]/page.tsx`
- Test: `frontend/src/components/DebateView.test.tsx`

**Interfaces:**
- Consumes: `DebateDetail`, `Round`, `FinalResult`, `Grade`, `Participant`, `Dropout` (types); `DEBATE_STATUS_LABEL`, `GRADE_LABEL`, `JUDGE_STATUS_LABEL`, `providerLabel`, `formatDateTime`, `formatPercent`, `canResume` (format); `useDebate` (Task 3); `stopDebate`, `resumeDebate`, `errorMessage` (api); `ErrorNotice`
- Produces:
  - `<ProgressHeader debate={DebateDetail} live={boolean} busy={boolean} onStop={() => void} onResume={() => void} />`
  - `<Banners debate={DebateDetail} />`
  - `<FinalResultCard result={FinalResult} grade={Grade | null} participants={Participant[]} />`
  - `<RoundList rounds={Round[]} participants={Participant[]} />`

화면 규칙(§5.5, §7.2):
- 상단: 질문, 상태 배지, "라운드 N"(마지막 라운드 번호, 없으면 0), 최근 판정 상태(판정이 있는 마지막 라운드, 없으면 "평가 없음"), 실시간 연결 표시.
- 진행 중이면 "중단" 버튼만, 이어할 수 있으면(`canResume`) "이어하기" 버튼만 보인다.
- 배너: 일시정지 사유, 재시작 등으로 끝나지 않은 중단 사유, 제외된 AI마다 §7.2 형식 문구.
- 결과가 있으면 최종 카드를 가장 위(라운드 기록보다 먼저) 크게 보여 준다. 라운드는 `<details>`로 접힌 상태.

- [ ] **Step 1: 실패 테스트 작성**

`frontend/src/components/DebateView.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DebateDetail, Participant } from "@/lib/types";
import { Banners } from "./Banners";
import { FinalResultCard } from "./FinalResultCard";
import { ProgressHeader } from "./ProgressHeader";
import { RoundList } from "./RoundList";

const participants: Participant[] = [
  { label: "A", slot_id: 1, provider: "openai", model: "gpt-4o-mini" },
  { label: "B", slot_id: 2, provider: "anthropic", model: "claude-haiku-4-5" },
];

function debate(overrides: Partial<DebateDetail> = {}): DebateDetail {
  return {
    id: 1, question: "자동 배포해도 되나요?", status: "running", grade: null, result: null, participants,
    dropouts: [], stall_threshold: 2, pause_reason: null, started_at: "2026-10-12T05:00:00Z", ended_at: null,
    rounds: [
      {
        number: 1, judge_eval: null, completed_at: "2026-10-12T05:01:00Z",
        messages: [
          {
            label: "A", provider: "openai", model: "gpt-4o-mini", error: null, input_tokens: 10, output_tokens: 20,
            latency_ms: 900, content: { position: "점진 배포가 낫다", reasons: ["위험 분산"], conditions: ["모니터링"], confidence: 0.8 },
          },
          {
            label: "B", provider: "anthropic", model: "claude-haiku-4-5", content: null, input_tokens: 0, output_tokens: 0,
            latency_ms: 0, error: "무료 크레딧 소진: billing",
          },
        ],
      },
      {
        number: 2, completed_at: "2026-10-12T05:02:00Z",
        judge_eval: { status: "progressing", issues: ["롤백 기준이 불명확"], draft: "점진 배포 초안" },
        messages: [
          {
            label: "A", provider: "openai", model: "gpt-4o-mini", error: null, input_tokens: 10, output_tokens: 20,
            latency_ms: 900,
            content: {
              position: "점진 배포", reasons: ["위험 분산"], conditions: [], confidence: 0.85,
              changes: "롤백 기준 추가", rebuttals: ["전면 배포는 위험"],
            },
          },
        ],
      },
    ],
    ...overrides,
  };
}

describe("ProgressHeader", () => {
  it("진행 상태, 라운드 번호, 최근 판정을 보여 주고 진행 중이면 중단 버튼만 둔다", async () => {
    const onStop = vi.fn();
    render(<ProgressHeader debate={debate()} live busy={false} onStop={onStop} onResume={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "자동 배포해도 되나요?" })).toBeInTheDocument();
    expect(screen.getByText("진행 중", { selector: ".badge" })).toBeInTheDocument();
    expect(screen.getByText("라운드 2")).toBeInTheDocument();
    expect(screen.getByText("최근 판정: 진행 중")).toBeInTheDocument();
    expect(screen.getByText("실시간 연결됨")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "이어하기" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "중단" }));
    expect(onStop).toHaveBeenCalled();
  });

  it("일시정지면 이어하기 버튼만 보이고, busy면 비활성화된다", () => {
    const { rerender } = render(
      <ProgressHeader debate={debate({ status: "paused" })} live={false} busy={false} onStop={vi.fn()} onResume={vi.fn()} />,
    );
    expect(screen.queryByRole("button", { name: "중단" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "이어하기" })).toBeEnabled();
    rerender(<ProgressHeader debate={debate({ status: "paused" })} live={false} busy onStop={vi.fn()} onResume={vi.fn()} />);
    expect(screen.getByRole("button", { name: "이어하기" })).toBeDisabled();
  });

  it("라운드가 없고 판정도 없으면 라운드 0과 평가 없음을 보여 준다", () => {
    render(<ProgressHeader debate={debate({ rounds: [] })} live={false} busy={false} onStop={vi.fn()} onResume={vi.fn()} />);
    expect(screen.getByText("라운드 0")).toBeInTheDocument();
    expect(screen.getByText("최근 판정: 평가 없음")).toBeInTheDocument();
  });
});

describe("Banners", () => {
  it("일시정지 사유와 제외된 AI를 알린다", () => {
    render(
      <Banners
        debate={debate({
          status: "paused",
          pause_reason: "판정 AI 일일 한도 소진: quota",
          dropouts: [{ label: "B", provider: "anthropic", model: "claude-haiku-4-5", round: 3, reason: "무료 크레딧 소진: billing" }],
        })}
      />,
    );
    expect(screen.getByText(/일시정지: 판정 AI 일일 한도 소진: quota/)).toBeInTheDocument();
    expect(
      screen.getByText(
        "⚠️ Anthropic (claude-haiku-4-5) — 무료 크레딧 소진: billing. 3라운드부터 토론에서 제외됐어요. 설정에서 다른 모델로 바꿀 수 있어요.",
      ),
    ).toBeInTheDocument();
  });

  it("끝나지 않은 중단은 사유와 이어하기 안내를 보여 준다", () => {
    render(<Banners debate={debate({ status: "interrupted", pause_reason: "서버 재시작", ended_at: null })} />);
    expect(screen.getByText(/중단됨: 서버 재시작/)).toBeInTheDocument();
  });

  it("dropouts가 null이어도 깨지지 않는다", () => {
    const { container } = render(<Banners debate={debate({ dropouts: null })} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("FinalResultCard", () => {
  it("결론 등급, 통합 의견, 근거, 이견, 불확실성, 제외된 AI를 모두 보여 준다", () => {
    render(
      <FinalResultCard
        grade="partial"
        participants={participants}
        result={{
          final_opinion: "점진 배포를 하되 롤백 기준을 먼저 정한다",
          grade: "partial",
          key_reasons: ["위험 분산"],
          dissents: [{ label: "B", reason: "속도가 더 중요" }],
          uncertainties: ["트래픽 규모 미확인"],
          dropouts: [{ label: "B", provider: "anthropic", model: "claude-haiku-4-5", round: 3, reason: "무료 크레딧 소진" }],
          end_reason: "수렴",
        }}
      />,
    );
    expect(screen.getByText("조건부·부분 합의")).toBeInTheDocument();
    expect(screen.getByText("점진 배포를 하되 롤백 기준을 먼저 정한다")).toBeInTheDocument();
    expect(screen.getByText("위험 분산")).toBeInTheDocument();
    expect(screen.getByText("참여자 B (Anthropic · claude-haiku-4-5): 속도가 더 중요")).toBeInTheDocument();
    expect(screen.getByText("트래픽 규모 미확인")).toBeInTheDocument();
    expect(screen.getByText("참여자 B · Anthropic (claude-haiku-4-5) — 3라운드, 무료 크레딧 소진")).toBeInTheDocument();
    expect(screen.getByText("종료 사유: 수렴")).toBeInTheDocument();
  });

  it("발언 없이 끝난 결과도 깨지지 않고 종료 사유를 보여 준다", () => {
    render(
      <FinalResultCard grade={null} participants={participants} result={{ dropouts: [], end_reason: "모든 참여 AI 소진" }} />,
    );
    expect(screen.getByText("통합할 발언이 없습니다.")).toBeInTheDocument();
    expect(screen.getByText("종료 사유: 모든 참여 AI 소진")).toBeInTheDocument();
    expect(screen.getByText("제외된 AI 없음")).toBeInTheDocument();
  });
});

describe("RoundList", () => {
  it("라운드는 접힌 상태로 두고 안에 발언과 판정을 담는다", () => {
    const { container } = render(<RoundList rounds={debate().rounds} participants={participants} />);
    const rounds = container.querySelectorAll("details");
    expect(rounds).toHaveLength(2);
    for (const round of rounds) expect(round).not.toHaveAttribute("open");
    expect(screen.getByText("1라운드 · 판정: 평가 없음")).toBeInTheDocument();
    expect(screen.getByText("2라운드 · 판정: 진행 중")).toBeInTheDocument();

    expect(screen.getByText("바꾼 점: 롤백 기준 추가")).toBeInTheDocument();
    expect(screen.getByText("반박·보완: 전면 배포는 위험")).toBeInTheDocument();
    expect(screen.getByText("롤백 기준이 불명확")).toBeInTheDocument();
    expect(screen.getByText("확신도 85%")).toBeInTheDocument();
  });

  it("실패한 발언은 오류 사유를 보여 준다", () => {
    render(<RoundList rounds={debate().rounds} participants={participants} />);
    expect(screen.getByText("응답 실패: 무료 크레딧 소진: billing")).toBeInTheDocument();
  });

  it("라운드가 없으면 안내 문구를 보여 준다", () => {
    render(<RoundList rounds={[]} participants={participants} />);
    expect(screen.getByText("아직 완료된 발언이 없습니다.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd frontend && npm test -- src/components/DebateView.test.tsx`
Expected: FAIL — `Failed to resolve import "./Banners"`

- [ ] **Step 3: 컴포넌트 구현**

`frontend/src/components/ProgressHeader.tsx`:

```tsx
import { DEBATE_STATUS_LABEL, JUDGE_STATUS_LABEL, canResume, formatDateTime } from "@/lib/format";
import type { DebateDetail } from "@/lib/types";

interface Props {
  debate: DebateDetail;
  live: boolean;
  busy: boolean;
  onStop: () => void;
  onResume: () => void;
}

export function ProgressHeader({ debate, live, busy, onStop, onResume }: Props) {
  const lastRound = debate.rounds.at(-1)?.number ?? 0;
  const lastEval = [...debate.rounds].reverse().find((round) => round.judge_eval !== null)?.judge_eval ?? null;
  const tone = debate.status === "running" ? "accent" : debate.status === "paused" || debate.status === "interrupted" ? "warn" : "ok";

  return (
    <section className="panel stack">
      <h1>{debate.question}</h1>
      <div className="row">
        <span className={`badge badge-${tone}`}>{DEBATE_STATUS_LABEL[debate.status]}</span>
        <span>라운드 {lastRound}</span>
        <span className="muted">최근 판정: {lastEval ? JUDGE_STATUS_LABEL[lastEval.status] : "평가 없음"}</span>
        {live && <span className="badge badge-ok">실시간 연결됨</span>}
        <span className="muted">시작 {formatDateTime(debate.started_at)}</span>
      </div>
      <div className="row">
        {debate.status === "running" && (
          <button type="button" className="secondary" disabled={busy} onClick={onStop}>
            중단
          </button>
        )}
        {canResume(debate) && (
          <button type="button" disabled={busy} onClick={onResume}>
            이어하기
          </button>
        )}
      </div>
    </section>
  );
}
```

`frontend/src/components/Banners.tsx`:

```tsx
import { providerLabel } from "@/lib/format";
import type { DebateDetail } from "@/lib/types";

export function Banners({ debate }: { debate: DebateDetail }) {
  const dropouts = debate.dropouts ?? [];
  const unfinishedInterrupt = debate.status === "interrupted" && debate.ended_at === null;
  if (debate.status !== "paused" && !unfinishedInterrupt && dropouts.length === 0) return null;

  return (
    <div>
      {debate.status === "paused" && (
        <p className="notice notice-warn">
          일시정지: {debate.pause_reason ?? "사유 없음"}. 설정에서 판정 AI 슬롯을 바꾼 뒤 이어하기를 누르세요.
        </p>
      )}
      {unfinishedInterrupt && (
        <p className="notice notice-warn">
          중단됨: {debate.pause_reason ?? "사유 없음"}. 이어하기를 누르면 마지막 완료 라운드 다음부터 진행합니다.
        </p>
      )}
      {dropouts.map((dropout) => (
        <p key={`${dropout.label}-${dropout.round}`} className="notice notice-warn">
          {`⚠️ ${providerLabel(dropout.provider)} (${dropout.model}) — ${dropout.reason}. ${dropout.round}라운드부터 토론에서 제외됐어요. 설정에서 다른 모델로 바꿀 수 있어요.`}
        </p>
      ))}
    </div>
  );
}
```

`frontend/src/components/FinalResultCard.tsx`:

```tsx
import { GRADE_LABEL, providerLabel } from "@/lib/format";
import type { FinalResult, Grade, Participant } from "@/lib/types";

interface Props {
  result: FinalResult;
  grade: Grade | null;
  participants: Participant[];
}

function describeLabel(label: string, participants: Participant[]): string {
  const participant = participants.find((item) => item.label === label);
  return participant ? `참여자 ${label} (${providerLabel(participant.provider)} · ${participant.model})` : `참여자 ${label}`;
}

function List({ items }: { items: string[] }) {
  return (
    <ul>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function FinalResultCard({ result, grade, participants }: Props) {
  return (
    <section className="panel final-card stack" aria-label="최종 통합 의견">
      <div className="row">
        <h2 style={{ margin: 0 }}>최종 통합 의견</h2>
        {grade && <span className="badge badge-accent">{GRADE_LABEL[grade]}</span>}
      </div>
      {result.final_opinion ? (
        <p className="final-opinion">{result.final_opinion}</p>
      ) : (
        <p className="muted">통합할 발언이 없습니다.</p>
      )}
      {result.key_reasons && result.key_reasons.length > 0 && (
        <div>
          <strong>핵심 근거</strong>
          <List items={result.key_reasons} />
        </div>
      )}
      {result.dissents && result.dissents.length > 0 && (
        <div>
          <strong>남은 이견</strong>
          <List items={result.dissents.map((dissent) => `${describeLabel(dissent.label, participants)}: ${dissent.reason}`)} />
        </div>
      )}
      {result.uncertainties && result.uncertainties.length > 0 && (
        <div>
          <strong>불확실성·전제 조건</strong>
          <List items={result.uncertainties} />
        </div>
      )}
      <div>
        <strong>제외된 AI</strong>
        {result.dropouts.length === 0 ? (
          <p className="muted">제외된 AI 없음</p>
        ) : (
          <List
            items={result.dropouts.map(
              (dropout) =>
                `참여자 ${dropout.label} · ${providerLabel(dropout.provider)} (${dropout.model}) — ${dropout.round}라운드, ${dropout.reason}`,
            )}
          />
        )}
      </div>
      <p className="muted">종료 사유: {result.end_reason}</p>
    </section>
  );
}
```

`frontend/src/components/RoundList.tsx`:

```tsx
import { JUDGE_STATUS_LABEL, formatPercent, providerLabel } from "@/lib/format";
import type { Message, Participant, Round } from "@/lib/types";

function MessageView({ message }: { message: Message }) {
  const header = `참여자 ${message.label} · ${providerLabel(message.provider)} (${message.model})`;
  if (message.content === null) {
    return (
      <div className="message">
        <strong>{header}</strong>
        <p className="muted">응답 실패: {message.error ?? "알 수 없는 오류"}</p>
      </div>
    );
  }
  const opinion = message.content;
  return (
    <div className="message">
      <strong>{header}</strong>
      <p>{opinion.position}</p>
      {opinion.reasons.length > 0 && (
        <ul>
          {opinion.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {opinion.conditions.length > 0 && <p className="muted">전제·한계: {opinion.conditions.join(" / ")}</p>}
      {opinion.changes && <p>바꾼 점: {opinion.changes}</p>}
      {opinion.rebuttals && opinion.rebuttals.length > 0 && (
        <p className="muted">반박·보완: {opinion.rebuttals.join(" / ")}</p>
      )}
      <p className="muted">확신도 {formatPercent(opinion.confidence)}</p>
    </div>
  );
}

export function RoundList({ rounds }: { rounds: Round[]; participants: Participant[] }) {
  if (rounds.length === 0) return <p className="muted">아직 완료된 발언이 없습니다.</p>;
  return (
    <div>
      {rounds.map((round) => (
        <details key={round.number} className="round">
          <summary>
            {round.number}라운드 · 판정: {round.judge_eval ? JUDGE_STATUS_LABEL[round.judge_eval.status] : "평가 없음"}
          </summary>
          {round.messages.map((message, index) => (
            <MessageView key={`${message.label}-${index}`} message={message} />
          ))}
          {round.judge_eval && (
            <div className="message">
              <strong>판정 AI</strong>
              {round.judge_eval.issues.length > 0 && (
                <ul>
                  {round.judge_eval.issues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              )}
              {round.judge_eval.draft && <p className="muted">통합안 초안: {round.judge_eval.draft}</p>}
            </div>
          )}
        </details>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd frontend && npm test -- src/components/DebateView.test.tsx`
Expected: PASS (11 tests)

- [ ] **Step 5: 토론 결과 화면 연결**

`frontend/src/app/debates/[id]/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Banners } from "@/components/Banners";
import { ErrorNotice } from "@/components/ErrorNotice";
import { FinalResultCard } from "@/components/FinalResultCard";
import { ProgressHeader } from "@/components/ProgressHeader";
import { RoundList } from "@/components/RoundList";
import { errorMessage, resumeDebate, stopDebate } from "@/lib/api";
import { useDebate } from "@/lib/useDebate";

export default function DebatePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { debate, error, live, refresh, reconnect } = useDebate(id);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function run(action: () => Promise<void>, after: () => void) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      after();
    } catch (caught) {
      setActionError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!Number.isInteger(id) || id <= 0) return <ErrorNotice message="잘못된 토론 주소입니다." />;
  if (!debate) return error ? <ErrorNotice message={error} /> : <p className="muted">토론을 불러오는 중…</p>;

  return (
    <div className="stack">
      <ProgressHeader
        debate={debate}
        live={live}
        busy={busy}
        onStop={() => void run(() => stopDebate(id), () => void refresh())}
        onResume={() => void run(() => resumeDebate(id), reconnect)}
      />
      <ErrorNotice message={actionError ?? error} />
      <Banners debate={debate} />
      {debate.result && <FinalResultCard result={debate.result} grade={debate.grade} participants={debate.participants} />}
      <h2>라운드별 발언</h2>
      <RoundList rounds={debate.rounds} participants={debate.participants} />
    </div>
  );
}
```

- [ ] **Step 6: 전체 테스트·타입 검사**

Run: `cd frontend && npm test && npm run typecheck`
Expected: PASS (36 tests), 타입 오류 없음

- [ ] **Step 7: 커밋**

```bash
git add frontend/src/components/ProgressHeader.tsx frontend/src/components/Banners.tsx \
  frontend/src/components/FinalResultCard.tsx frontend/src/components/RoundList.tsx \
  frontend/src/components/DebateView.test.tsx "frontend/src/app/debates/[id]/page.tsx"
git commit -m "feat: add debate screen with progress, banners, final result and rounds

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: 기록 화면 (`/history`)

**Files:**
- Create: `frontend/src/components/HistoryTable.tsx`, `frontend/src/app/history/page.tsx`
- Test: `frontend/src/components/HistoryTable.test.tsx`

**Interfaces:**
- Consumes: `DebateSummary` (types), `DEBATE_STATUS_LABEL`, `GRADE_LABEL`, `formatDateTime` (format), `listDebates`, `errorMessage` (api), `ErrorNotice`
- Produces: `<HistoryTable debates={DebateSummary[]} />`

- [ ] **Step 1: 실패 테스트 작성**

`frontend/src/components/HistoryTable.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HistoryTable } from "./HistoryTable";

describe("HistoryTable", () => {
  it("질문, 상태, 결론 등급, 날짜를 보여 주고 상세로 연결한다", () => {
    render(
      <HistoryTable
        debates={[
          { id: 2, question: "자동 배포해도 되나요?", status: "converged", grade: "consensus", started_at: "2026-10-12T05:00:00Z", ended_at: "2026-10-12T05:10:00Z" },
          { id: 1, question: "모노레포가 나을까요?", status: "paused", grade: null, started_at: "2026-10-11T00:00:00Z", ended_at: null },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "자동 배포해도 되나요?" })).toHaveAttribute("href", "/debates/2");
    expect(screen.getByText("수렴")).toBeInTheDocument();
    expect(screen.getByText("합의")).toBeInTheDocument();
    expect(screen.getByText("일시정지")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(1);
    expect(screen.getByText(/오후 2:00/)).toBeInTheDocument();
  });

  it("기록이 없으면 안내 문구를 보여 준다", () => {
    render(<HistoryTable debates={[]} />);
    expect(screen.getByText("아직 토론 기록이 없습니다.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd frontend && npm test -- src/components/HistoryTable.test.tsx`
Expected: FAIL — `Failed to resolve import "./HistoryTable"`

- [ ] **Step 3: 구현**

`frontend/src/components/HistoryTable.tsx`:

```tsx
import Link from "next/link";
import { DEBATE_STATUS_LABEL, GRADE_LABEL, formatDateTime } from "@/lib/format";
import type { DebateSummary } from "@/lib/types";

export function HistoryTable({ debates }: { debates: DebateSummary[] }) {
  if (debates.length === 0) return <p className="muted">아직 토론 기록이 없습니다.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>질문</th>
          <th>상태</th>
          <th>결론</th>
          <th>시작</th>
        </tr>
      </thead>
      <tbody>
        {debates.map((debate) => (
          <tr key={debate.id}>
            <td className="question-cell">
              <Link href={`/debates/${debate.id}`}>{debate.question}</Link>
            </td>
            <td>{DEBATE_STATUS_LABEL[debate.status]}</td>
            <td>{debate.grade ? GRADE_LABEL[debate.grade] : "—"}</td>
            <td>{formatDateTime(debate.started_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

`frontend/src/app/history/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { HistoryTable } from "@/components/HistoryTable";
import { errorMessage, listDebates } from "@/lib/api";
import type { DebateSummary } from "@/lib/types";

export default function HistoryPage() {
  const [debates, setDebates] = useState<DebateSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDebates().then(setDebates, (caught) => setError(errorMessage(caught)));
  }, []);

  return (
    <>
      <h1>토론 기록</h1>
      <ErrorNotice message={error} />
      {debates === null && !error && <p className="muted">기록을 불러오는 중…</p>}
      {debates && (
        <section className="panel">
          <HistoryTable debates={debates} />
        </section>
      )}
    </>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd frontend && npm test -- src/components/HistoryTable.test.tsx && npm run typecheck`
Expected: PASS (2 tests), 타입 오류 없음

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/components/HistoryTable.tsx frontend/src/components/HistoryTable.test.tsx frontend/src/app/history/page.tsx
git commit -m "feat: add history screen

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: 설정 화면 (`/settings`)

**Files:**
- Create: `frontend/src/components/SlotEditor.tsx`, `frontend/src/components/StallThresholdForm.tsx`, `frontend/src/app/settings/page.tsx`
- Test: `frontend/src/components/Settings.test.tsx`

**Interfaces:**
- Consumes: `Slot`, `UpdateSlotInput`, `AppConfig` (types); `providerLabel`, `formatDateTime`, `formatPercent` (format); `SlotBadge`, `ErrorNotice`; `listSlots`, `updateSlot`, `getConfig`, `updateConfig`, `errorMessage` (api)
- Produces:
  - `<SlotEditor slot={Slot} providers={string[]} onSave={(input: UpdateSlotInput) => Promise<Slot>} />`
  - `<StallThresholdForm value={number} onSave={(value: number) => Promise<void>} />`

화면 규칙(§5.5, §5.3): 슬롯별 회사·모델·키 환경변수·하루 요청 한도(선택) 수정, 상태·사유·해제 예상 시각, 키 "연결됨/없음"(값은 절대 안 보임), 오늘·누적 사용량, 한도 대비 "추정" 비율. 모델을 바꾸면 소진 상태가 풀린다는 안내. 정체 기준 N(1~10).

- [ ] **Step 1: 실패 테스트 작성**

`frontend/src/components/Settings.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeSlot } from "@/test/fixtures";
import { SlotEditor } from "./SlotEditor";
import { StallThresholdForm } from "./StallThresholdForm";

const providers = ["openai", "anthropic", "gemini", "xai", "openrouter", "groq"];

describe("SlotEditor", () => {
  it("상태, 사유, 해제 예상 시각, 키 연결 여부, 사용량과 추정치를 보여 준다", () => {
    render(
      <SlotEditor
        providers={providers}
        onSave={vi.fn()}
        slot={makeSlot({
          id: 3, provider: "gemini", model: "gemini-2.5-flash", api_key_env: "GEMINI_API_KEY",
          status: "rate_limited", status_reason: "요청 한도 초과: slow down", status_until: "2026-10-12T05:00:00Z",
          known_limit: { requests_per_day: 250 }, usage_estimate: 0.4,
          usage: { today_requests: 100, today_tokens: 5000, total_requests: 900, total_tokens: 40000 },
        })}
      />,
    );
    expect(screen.getByRole("heading", { name: "참여 슬롯 3" })).toBeInTheDocument();
    expect(screen.getByText("속도 제한")).toBeInTheDocument();
    expect(screen.getByText("사유: 요청 한도 초과: slow down")).toBeInTheDocument();
    expect(screen.getByText(/해제 예상: .*오후 2:00/)).toBeInTheDocument();
    expect(screen.getByText("API 키: 연결됨 (GEMINI_API_KEY)")).toBeInTheDocument();
    expect(screen.getByText("오늘 100회 · 5,000토큰 / 누적 900회 · 40,000토큰")).toBeInTheDocument();
    expect(screen.getByText("무료 한도 대비 추정 40%")).toBeInTheDocument();
  });

  it("키가 없으면 없음으로 표시한다", () => {
    render(<SlotEditor providers={providers} onSave={vi.fn()} slot={makeSlot({ key_present: false })} />);
    expect(screen.getByText("API 키: 없음 (OPENAI_API_KEY)")).toBeInTheDocument();
  });

  it("수정한 값으로 저장하고, 한도를 비우면 null로 보낸다", async () => {
    const onSave = vi.fn(async () => makeSlot({ id: 2, provider: "openrouter", model: "meta-llama/llama-3.3-70b-instruct:free" }));
    render(<SlotEditor providers={providers} onSave={onSave} slot={makeSlot({ id: 2, known_limit: { requests_per_day: 50 } })} />);
    await userEvent.selectOptions(screen.getByLabelText("회사"), "openrouter");
    await userEvent.clear(screen.getByLabelText("모델"));
    await userEvent.type(screen.getByLabelText("모델"), "meta-llama/llama-3.3-70b-instruct:free");
    await userEvent.clear(screen.getByLabelText("API 키 환경변수"));
    await userEvent.type(screen.getByLabelText("API 키 환경변수"), "OPENROUTER_API_KEY");
    await userEvent.clear(screen.getByLabelText("하루 요청 한도 (선택)"));
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(onSave).toHaveBeenCalledWith({
      provider: "openrouter", model: "meta-llama/llama-3.3-70b-instruct:free",
      api_key_env: "OPENROUTER_API_KEY", known_limit: null,
    });
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("저장했습니다"));
  });

  it("하루 한도를 입력하면 requests_per_day로 보낸다", async () => {
    const onSave = vi.fn(async () => makeSlot());
    render(<SlotEditor providers={providers} onSave={onSave} slot={makeSlot()} />);
    await userEvent.type(screen.getByLabelText("하루 요청 한도 (선택)"), "500");
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    expect(onSave).toHaveBeenCalledWith(expect.objectContaining({ known_limit: { requests_per_day: 500 } }));
  });

  it("저장이 거절되면 백엔드 메시지를 보여 준다", async () => {
    const onSave = vi.fn(async () => {
      throw new Error("입력값이 올바르지 않습니다: api_key_env");
    });
    render(<SlotEditor providers={providers} onSave={onSave} slot={makeSlot()} />);
    await userEvent.click(screen.getByRole("button", { name: "저장" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("입력값이 올바르지 않습니다: api_key_env"));
  });

  it("판정 슬롯은 판정 슬롯으로 표시한다", () => {
    render(<SlotEditor providers={providers} onSave={vi.fn()} slot={makeSlot({ id: 5, kind: "judge" })} />);
    expect(screen.getByRole("heading", { name: "판정 슬롯" })).toBeInTheDocument();
  });
});

describe("StallThresholdForm", () => {
  it("1~10 사이 값을 저장한다", async () => {
    const onSave = vi.fn(async () => {});
    render(<StallThresholdForm value={2} onSave={onSave} />);
    const input = screen.getByLabelText("정체 기준 (연속 라운드 수, 1~10)");
    expect(input).toHaveValue(2);
    await userEvent.clear(input);
    await userEvent.type(input, "3");
    await userEvent.click(screen.getByRole("button", { name: "정체 기준 저장" }));
    expect(onSave).toHaveBeenCalledWith(3);
  });

  it("범위를 벗어나면 저장하지 않고 안내한다", async () => {
    const onSave = vi.fn(async () => {});
    render(<StallThresholdForm value={2} onSave={onSave} />);
    const input = screen.getByLabelText("정체 기준 (연속 라운드 수, 1~10)");
    await userEvent.clear(input);
    await userEvent.type(input, "11");
    await userEvent.click(screen.getByRole("button", { name: "정체 기준 저장" }));
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("1~10 사이의 정수를 입력하세요");
  });
});
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `cd frontend && npm test -- src/components/Settings.test.tsx`
Expected: FAIL — `Failed to resolve import "./SlotEditor"`

- [ ] **Step 3: 구현**

`frontend/src/components/SlotEditor.tsx`:

```tsx
"use client";

import { type FormEvent, useState } from "react";
import { errorMessage } from "@/lib/api";
import { formatDateTime, formatPercent, providerLabel } from "@/lib/format";
import type { Slot, UpdateSlotInput } from "@/lib/types";
import { ErrorNotice } from "./ErrorNotice";
import { SlotBadge } from "./SlotBadge";

interface Props {
  slot: Slot;
  providers: string[];
  onSave: (input: UpdateSlotInput) => Promise<Slot>;
}

const NUMBER = new Intl.NumberFormat("ko-KR");

export function SlotEditor({ slot: initial, providers, onSave }: Props) {
  const [slot, setSlot] = useState(initial);
  const [provider, setProvider] = useState(initial.provider);
  const [model, setModel] = useState(initial.model);
  const [keyEnv, setKeyEnv] = useState(initial.api_key_env);
  const [limit, setLimit] = useState(initial.known_limit?.requests_per_day?.toString() ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const title = slot.kind === "judge" ? "판정 슬롯" : `참여 슬롯 ${slot.id}`;
  const providerOptions = providers.includes(provider) ? providers : [provider, ...providers];

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    const parsedLimit = Number.parseInt(limit, 10);
    try {
      const updated = await onSave({
        provider,
        model: model.trim(),
        api_key_env: keyEnv.trim(),
        known_limit: limit.trim() === "" || Number.isNaN(parsedLimit) ? null : { requests_per_day: parsedLimit },
      });
      setSlot(updated);
      setSaved(true);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel stack">
      <div className="row">
        <h2 style={{ margin: 0 }}>{title}</h2>
        <SlotBadge slot={slot} />
      </div>
      <p className="muted">
        현재: {providerLabel(slot.provider)} · {slot.model}
      </p>
      {slot.status_reason && <p className="muted">사유: {slot.status_reason}</p>}
      {slot.status_until && <p className="muted">해제 예상: {formatDateTime(slot.status_until)}</p>}
      <p className="muted">
        API 키: {slot.key_present ? "연결됨" : "없음"} ({slot.api_key_env})
      </p>
      <p className="muted">
        {`오늘 ${NUMBER.format(slot.usage.today_requests)}회 · ${NUMBER.format(slot.usage.today_tokens)}토큰 / 누적 ${NUMBER.format(slot.usage.total_requests)}회 · ${NUMBER.format(slot.usage.total_tokens)}토큰`}
      </p>
      {slot.usage_estimate !== null && <p className="muted">무료 한도 대비 추정 {formatPercent(slot.usage_estimate)}</p>}

      <form className="stack" onSubmit={handleSubmit}>
        <label>
          <span className="muted">회사</span>
          <select aria-label="회사" value={provider} onChange={(event) => setProvider(event.target.value)}>
            {providerOptions.map((option) => (
              <option key={option} value={option}>
                {providerLabel(option)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="muted">모델</span>
          <input aria-label="모델" value={model} onChange={(event) => setModel(event.target.value)} />
        </label>
        <label>
          <span className="muted">API 키 환경변수</span>
          <input aria-label="API 키 환경변수" value={keyEnv} onChange={(event) => setKeyEnv(event.target.value)} />
        </label>
        <label>
          <span className="muted">하루 요청 한도 (선택)</span>
          <input
            aria-label="하루 요청 한도 (선택)"
            type="number"
            min={1}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
        <p className="muted">회사나 모델을 바꾸면 이 슬롯의 소진 상태가 풀립니다. 키 값은 backend/.env에만 넣으세요.</p>
        <ErrorNotice message={error} />
        {saved && (
          <p className="muted" role="status">
            저장했습니다
          </p>
        )}
        <div className="row">
          <button type="submit" disabled={saving}>
            {saving ? "저장하는 중…" : "저장"}
          </button>
        </div>
      </form>
    </section>
  );
}
```

`frontend/src/components/StallThresholdForm.tsx`:

```tsx
"use client";

import { type FormEvent, useState } from "react";
import { errorMessage } from "@/lib/api";
import { ErrorNotice } from "./ErrorNotice";

export function StallThresholdForm({ value, onSave }: { value: number; onSave: (value: number) => Promise<void> }) {
  const [text, setText] = useState(String(value));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    const parsed = Number(text);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 10) {
      setError("1~10 사이의 정수를 입력하세요");
      return;
    }
    setError(null);
    try {
      await onSave(parsed);
      setSaved(true);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <form className="panel stack" onSubmit={handleSubmit}>
      <label>
        <span className="muted">정체 기준 (연속 라운드 수, 1~10)</span>
        <input
          aria-label="정체 기준 (연속 라운드 수, 1~10)"
          type="number"
          min={1}
          max={10}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <p className="muted">판정 AI가 이 횟수만큼 연속으로 "정체"라고 보면 토론을 마칩니다. 새 토론부터 적용됩니다.</p>
      <ErrorNotice message={error} />
      {saved && (
        <p className="muted" role="status">
          저장했습니다
        </p>
      )}
      <div className="row">
        <button type="submit">정체 기준 저장</button>
      </div>
    </form>
  );
}
```

`frontend/src/app/settings/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { SlotEditor } from "@/components/SlotEditor";
import { StallThresholdForm } from "@/components/StallThresholdForm";
import { errorMessage, getConfig, listSlots, updateConfig, updateSlot } from "@/lib/api";
import type { AppConfig, Slot } from "@/lib/types";

export default function SettingsPage() {
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listSlots(), getConfig()]).then(
      ([loadedSlots, loadedConfig]) => {
        setSlots(loadedSlots);
        setConfig(loadedConfig);
      },
      (caught) => setError(errorMessage(caught)),
    );
  }, []);

  return (
    <>
      <h1>설정</h1>
      <ErrorNotice message={error} />
      {(!slots || !config) && !error && <p className="muted">설정을 불러오는 중…</p>}
      {slots && config && (
        <div className="stack">
          <StallThresholdForm
            value={config.stall_threshold}
            onSave={async (value) => setConfig(await updateConfig(value))}
          />
          {slots.map((slot) => (
            <SlotEditor key={slot.id} slot={slot} providers={config.providers} onSave={(input) => updateSlot(slot.id, input)} />
          ))}
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd frontend && npm test -- src/components/Settings.test.tsx && npm run typecheck`
Expected: PASS (8 tests), 타입 오류 없음

- [ ] **Step 5: 커밋**

```bash
git add frontend/src/components/SlotEditor.tsx frontend/src/components/StallThresholdForm.tsx \
  frontend/src/components/Settings.test.tsx frontend/src/app/settings/page.tsx
git commit -m "feat: add settings screen for slots and stall threshold

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: 빌드 확인, 실행 안내, 수동 연결 확인

**Files:**
- Create: `frontend/README.md`
- Modify: `README.md` (루트) — "빠른 시작"에 프론트엔드 단계 추가, "상태" 줄과 로드맵 체크 갱신

**Interfaces:**
- Consumes: Task 1~6 결과물 전체
- Produces: 문서만

- [ ] **Step 1: 전체 검증**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Expected: 테스트 46개 PASS(경고 없음), 타입 오류 없음, 빌드 성공(라우트 `/`, `/debates/[id]`, `/history`, `/settings`가 빌드 출력에 보임)

- [ ] **Step 2: `frontend/README.md` 작성**

```markdown
# AI-Roundtable 프론트엔드

Next.js로 만든 화면 4개입니다: 질문(`/`), 토론 결과(`/debates/[id]`), 기록(`/history`), 설정(`/settings`).

## 실행

1. 백엔드를 먼저 실행합니다 (`backend/README.md` 참고, `--host 127.0.0.1 --port 8000`).
2. 의존성을 설치하고 개발 서버를 띄웁니다.
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
3. 브라우저에서 **http://localhost:3000** 을 엽니다. (`127.0.0.1:3000`으로 열면 백엔드가 CORS로 거절합니다.)

백엔드 주소를 바꾸려면 `NEXT_PUBLIC_API_BASE` 환경변수를 지정하세요 (기본 `http://127.0.0.1:8000`).

## 테스트 (백엔드·실제 AI를 호출하지 않음)

```bash
npm test
npm run typecheck
```
```

- [ ] **Step 3: 루트 `README.md` 갱신**

`README.md`에서 다음 세 곳을 고친다.

1. 상태 줄을 다음으로 바꾼다:

```markdown
> **상태:** MVP 완성 — 백엔드(FastAPI, 테스트 134개)와 프론트엔드(Next.js, 테스트 46개).
```

2. "빠른 시작"의 4번 항목 뒤에 다음 5번 항목을 추가한다:

```markdown
5. 다른 터미널에서 화면을 띄우고 브라우저로 **http://localhost:3000** 을 엽니다.
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
```

3. 로드맵의 프론트엔드 줄을 `- [x] 프론트엔드 (Next.js): 질문 입력, 실시간 진행 화면, 최종 결과, 슬롯 설정`으로 바꾸고, "프로젝트 구조" 코드 블록 맨 아래(`docs/superpowers/` 위)에 다음 두 줄을 넣는다:

```
frontend/
  src/           Next.js 화면(app), 컴포넌트, API 클라이언트·SSE 훅(lib)
```

- [ ] **Step 4: 수동 연결 확인 (실제 AI 호출 없음)**

백엔드와 프론트엔드를 띄워 화면이 백엔드 데이터를 받는지만 확인한다. **토론 시작 버튼은 누르지 않는다**(실제 AI를 호출함).

```bash
cd backend && ROUNDTABLE_DB=sqlite:///./check.db uv run uvicorn roundtable.main:app --host 127.0.0.1 --port 8000   # 터미널 1
cd frontend && npm run build && npm run start                                                                        # 터미널 2
curl -s http://localhost:3000/ | grep -o "<title>[^<]*</title>"
curl -s -H "Origin: http://localhost:3000" http://127.0.0.1:8000/slots -D - -o /dev/null | grep -i "access-control-allow-origin"
```

Expected: `<title>Roundtable</title>`와 `access-control-allow-origin: http://localhost:3000`. 확인 후 두 서버를 끄고 `backend/check.db`를 지운다.

- [ ] **Step 5: 커밋**

```bash
git add frontend/README.md README.md
git commit -m "docs: add frontend run guide and update service README

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
