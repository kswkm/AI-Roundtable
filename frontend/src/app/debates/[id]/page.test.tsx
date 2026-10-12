import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, resumeDebate, stopDebate } from "@/lib/api";
import type { DebateDetail } from "@/lib/types";
import DebatePage from "./page";

const hooks = vi.hoisted(() => ({ refresh: vi.fn(), reconnect: vi.fn() }));
const state = vi.hoisted(() => ({ debate: null as DebateDetail | null }));

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "7" }) }));
vi.mock("@/lib/useDebate", () => ({
  useDebate: () => ({ debate: state.debate, error: null, live: false, refresh: hooks.refresh, reconnect: hooks.reconnect }),
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, resumeDebate: vi.fn(), stopDebate: vi.fn() };
});

const pausedDebate: DebateDetail = {
  id: 7, question: "자동 배포해도 되나요?", status: "paused", grade: null, result: null,
  participants: [{ label: "A", slot_id: 1, provider: "openai", model: "gpt-4o-mini" }],
  dropouts: [], stall_threshold: 2, pause_reason: "판정 AI 일일 한도 소진: quota",
  started_at: "2026-10-12T05:00:00Z", ended_at: null, rounds: [],
};

describe("DebatePage resume wiring", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    state.debate = pausedDebate;
  });

  it("이어하기가 실패하면 서버 메시지를 보여 주고 재연결하지 않는다", async () => {
    vi.mocked(resumeDebate).mockRejectedValueOnce(new ApiError(409, "이어할 수 있는 토론이 아닙니다"));
    render(<DebatePage />);
    await userEvent.click(screen.getByRole("button", { name: "이어하기" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("이어할 수 있는 토론이 아닙니다");
    expect(hooks.reconnect).not.toHaveBeenCalled();
  });

  it("이어하기가 성공하면 재연결한다", async () => {
    vi.mocked(resumeDebate).mockResolvedValueOnce(undefined);
    render(<DebatePage />);
    await userEvent.click(screen.getByRole("button", { name: "이어하기" }));
    expect(hooks.reconnect).toHaveBeenCalled();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("중단이 성공하면 중단 요청 안내를 보여 준다", async () => {
    state.debate = { ...pausedDebate, status: "running", pause_reason: null };
    vi.mocked(stopDebate).mockResolvedValueOnce(undefined);
    render(<DebatePage />);
    await userEvent.click(screen.getByRole("button", { name: "중단" }));
    expect(await screen.findByText(/중단 요청됨 — 이번 라운드가 끝나면/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "중단" })).not.toBeInTheDocument();
  });
});
