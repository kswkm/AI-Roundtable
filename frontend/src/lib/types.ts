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
