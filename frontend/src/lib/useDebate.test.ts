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
