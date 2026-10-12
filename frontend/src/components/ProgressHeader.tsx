import { DEBATE_STATUS_LABEL, JUDGE_STATUS_LABEL, canResume, formatDateTime } from "@/lib/format";
import type { DebateDetail } from "@/lib/types";

interface Props {
  debate: DebateDetail;
  live: boolean;
  busy: boolean;
  onStop: () => void;
  onResume: () => void;
}

export function ProgressHeader({ debate, live, busy, onStop, onResume }: Props) {
  const lastRound = debate.rounds.at(-1)?.number ?? 0;
  const lastEval = [...debate.rounds].reverse().find((round) => round.judge_eval !== null)?.judge_eval ?? null;
  const tone = debate.status === "running" ? "accent" : debate.status === "paused" || debate.status === "interrupted" ? "warn" : "ok";

  return (
    <section className="panel stack">
      <h1>{debate.question}</h1>
      <div className="row">
        <span className={`badge badge-${tone}`}>{DEBATE_STATUS_LABEL[debate.status]}</span>
        <span>라운드 {lastRound}</span>
        <span className="muted">최근 판정: {lastEval ? JUDGE_STATUS_LABEL[lastEval.status] : "평가 없음"}</span>
        {live && <span className="badge badge-ok">실시간 연결됨</span>}
        <span className="muted">시작 {formatDateTime(debate.started_at)}</span>
      </div>
      <div className="row">
        {debate.status === "running" && (
          <button type="button" className="secondary" disabled={busy} onClick={onStop}>
            중단
          </button>
        )}
        {canResume(debate) && (
          <button type="button" disabled={busy} onClick={onResume}>
            이어하기
          </button>
        )}
      </div>
    </section>
  );
}
