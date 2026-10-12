import { describe, expect, it } from "vitest";
import { makeSlot } from "@/test/fixtures";
import { canResume, formatDateTime, formatPercent, providerLabel, slotUnavailableReason } from "./format";

describe("format", () => {
  it("UTC Z 시간을 서울 시간으로 표시한다", () => {
    expect(formatDateTime("2026-10-12T05:00:00Z")).toContain("14:00");
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
