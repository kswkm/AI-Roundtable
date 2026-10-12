import type { Slot } from "@/lib/types";

export function makeSlot(overrides: Partial<Slot> = {}): Slot {
  return {
    id: 1, kind: "participant", provider: "openai", model: "gpt-4o-mini", api_key_env: "OPENAI_API_KEY",
    key_present: true, status: "available", status_until: null, status_reason: null, known_limit: null,
    usage: { today_requests: 0, today_tokens: 0, total_requests: 0, total_tokens: 0 }, usage_estimate: null,
    ...overrides,
  };
}
