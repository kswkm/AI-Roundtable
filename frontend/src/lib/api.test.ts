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
