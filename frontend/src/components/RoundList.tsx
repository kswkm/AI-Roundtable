import { JUDGE_STATUS_LABEL, formatPercent, providerLabel } from "@/lib/format";
import type { Message, Participant, Round } from "@/lib/types";

function MessageView({ message }: { message: Message }) {
  const header = `참여자 ${message.label} · ${providerLabel(message.provider)} (${message.model})`;
  if (message.content === null) {
    return (
      <div className="message">
        <strong>{header}</strong>
        <p className="muted">응답 실패: {message.error ?? "알 수 없는 오류"}</p>
      </div>
    );
  }
  const opinion = message.content;
  return (
    <div className="message">
      <strong>{header}</strong>
      <p>{opinion.position}</p>
      {opinion.reasons.length > 0 && (
        <ul>
          {opinion.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
      {opinion.conditions.length > 0 && <p className="muted">전제·한계: {opinion.conditions.join(" / ")}</p>}
      {opinion.changes && <p>바꾼 점: {opinion.changes}</p>}
      {opinion.rebuttals && opinion.rebuttals.length > 0 && (
        <p className="muted">반박·보완: {opinion.rebuttals.join(" / ")}</p>
      )}
      <p className="muted">확신도 {formatPercent(opinion.confidence)}</p>
    </div>
  );
}

export function RoundList({ rounds }: { rounds: Round[]; participants: Participant[] }) {
  if (rounds.length === 0) return <p className="muted">아직 완료된 발언이 없습니다.</p>;
  return (
    <div>
      {rounds.map((round) => (
        <details key={round.number} className="round">
          <summary>
            {round.number}라운드 · 판정: {round.judge_eval ? JUDGE_STATUS_LABEL[round.judge_eval.status] : "평가 없음"}
          </summary>
          {round.messages.map((message, index) => (
            <MessageView key={`${message.label}-${index}`} message={message} />
          ))}
          {round.judge_eval && (
            <div className="message">
              <strong>판정 AI</strong>
              {round.judge_eval.issues.length > 0 && (
                <ul>
                  {round.judge_eval.issues.map((issue) => (
                    <li key={issue}>{issue}</li>
                  ))}
                </ul>
              )}
              {round.judge_eval.draft && <p className="muted">통합안 초안: {round.judge_eval.draft}</p>}
            </div>
          )}
        </details>
      ))}
    </div>
  );
}
