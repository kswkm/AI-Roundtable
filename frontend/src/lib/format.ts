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

const DATE_TIME = new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short", hourCycle: "h23" });

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
