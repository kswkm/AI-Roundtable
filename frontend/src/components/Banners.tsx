import { providerLabel } from "@/lib/format";
import type { DebateDetail } from "@/lib/types";

export function Banners({ debate }: { debate: DebateDetail }) {
  const dropouts = debate.dropouts ?? [];
  const unfinishedInterrupt = debate.status === "interrupted" && debate.ended_at === null;
  if (debate.status !== "paused" && !unfinishedInterrupt && dropouts.length === 0) return null;

  return (
    <div>
      {debate.status === "paused" && (
        <p className="notice notice-warn">
          일시정지: {debate.pause_reason ?? "사유 없음"}. 설정에서 판정 AI 슬롯을 바꾼 뒤 이어하기를 누르세요.
        </p>
      )}
      {unfinishedInterrupt && (
        <p className="notice notice-warn">
          중단됨: {debate.pause_reason ?? "사유 없음"}. 이어하기를 누르면 마지막 완료 라운드 다음부터 진행합니다.
        </p>
      )}
      {dropouts.map((dropout) => (
        <p key={`${dropout.label}-${dropout.round}`} className="notice notice-warn">
          {`⚠️ ${providerLabel(dropout.provider)} (${dropout.model}) — ${dropout.reason}. ${dropout.round}라운드부터 토론에서 제외됐어요. 설정에서 다른 모델로 바꿀 수 있어요.`}
        </p>
      ))}
    </div>
  );
}
