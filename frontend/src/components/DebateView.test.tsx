import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { DebateDetail, FinalResult, Participant } from "@/lib/types";
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

  it("완료되지 않은 라운드는 평가 없음 대신 진행 중으로 보여 준다", () => {
    render(
      <RoundList
        rounds={[{ number: 3, judge_eval: null, completed_at: null, messages: [] }]}
        participants={participants}
      />,
    );
    expect(screen.getByText("3라운드 · 판정: 진행 중…")).toBeInTheDocument();
  });

  it("같은 문구의 근거가 두 번 와도 둘 다 보여 주고 key 경고가 없다", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const rounds = debate().rounds;
    rounds[0].messages[0].content = {
      position: "중복 근거", reasons: ["같은 근거", "같은 근거"], conditions: [], confidence: 0.5,
    };
    render(<RoundList rounds={rounds} participants={participants} />);
    expect(screen.getAllByText("같은 근거")).toHaveLength(2);
    expect(consoleError.mock.calls.some((args) => String(args[0]).includes("same key"))).toBe(false);
  });
});

describe("FinalResultCard extras", () => {
  it("합의가 아닌 미합의 결과는 미합의 배지만 보여 준다", () => {
    render(<FinalResultCard grade="no_consensus" participants={participants} result={{ dropouts: [], end_reason: "정체" }} />);
    expect(screen.getByText("미합의", { selector: ".badge" })).toBeInTheDocument();
    expect(screen.queryByText("합의", { selector: ".badge" })).not.toBeInTheDocument();
  });

  it("중복된 핵심 근거도 모두 보여 주고 key 경고가 없다", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <FinalResultCard
        grade="consensus"
        participants={participants}
        result={{ key_reasons: ["같은 근거", "같은 근거"], dropouts: [], end_reason: "수렴" }}
      />,
    );
    expect(screen.getAllByText("같은 근거")).toHaveLength(2);
    expect(consoleError.mock.calls.some((args) => String(args[0]).includes("same key"))).toBe(false);
  });

  it("dropouts가 없는 결과도 깨지지 않고 제외된 AI 없음을 보여 준다", () => {
    render(
      <FinalResultCard grade={null} participants={participants} result={{ end_reason: "수렴" } as FinalResult} />,
    );
    expect(screen.getByText("제외된 AI 없음")).toBeInTheDocument();
  });
});
