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
