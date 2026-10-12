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
    expect(screen.getByText(/해제 예상: .*14:00/)).toBeInTheDocument();
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
