import { SLOT_STATUS_LABEL, slotUnavailableReason } from "@/lib/format";
import type { Slot } from "@/lib/types";

export function SlotBadge({ slot }: { slot: Slot }) {
  const tone = !slot.key_present || slot.status === "exhausted" ? "bad" : slot.status === "rate_limited" ? "warn" : "ok";
  const text = slot.key_present ? SLOT_STATUS_LABEL[slot.status] : "키 없음";
  const title = slotUnavailableReason(slot) ?? slot.status_reason ?? undefined;
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {text}
    </span>
  );
}
