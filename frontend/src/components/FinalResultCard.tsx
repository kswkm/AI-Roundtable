import { GRADE_LABEL, providerLabel } from "@/lib/format";
import type { FinalResult, Grade, Participant } from "@/lib/types";

interface Props {
  result: FinalResult;
  grade: Grade | null;
  participants: Participant[];
}

function describeLabel(label: string, participants: Participant[]): string {
  const participant = participants.find((item) => item.label === label);
  return participant ? `참여자 ${label} (${providerLabel(participant.provider)} · ${participant.model})` : `참여자 ${label}`;
}

function List({ items }: { items: string[] }) {
  return (
    <ul>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

export function FinalResultCard({ result, grade, participants }: Props) {
  return (
    <section className="panel final-card stack" aria-label="최종 통합 의견">
      <div className="row">
        <h2 style={{ margin: 0 }}>최종 통합 의견</h2>
        {grade && <span className="badge badge-accent">{GRADE_LABEL[grade]}</span>}
      </div>
      {result.final_opinion ? (
        <p className="final-opinion">{result.final_opinion}</p>
      ) : (
        <p className="muted">통합할 발언이 없습니다.</p>
      )}
      {result.key_reasons && result.key_reasons.length > 0 && (
        <div>
          <strong>핵심 근거</strong>
          <List items={result.key_reasons} />
        </div>
      )}
      {result.dissents && result.dissents.length > 0 && (
        <div>
          <strong>남은 이견</strong>
          <List items={result.dissents.map((dissent) => `${describeLabel(dissent.label, participants)}: ${dissent.reason}`)} />
        </div>
      )}
      {result.uncertainties && result.uncertainties.length > 0 && (
        <div>
          <strong>불확실성·전제 조건</strong>
          <List items={result.uncertainties} />
        </div>
      )}
      <div>
        <strong>제외된 AI</strong>
        {result.dropouts.length === 0 ? (
          <p className="muted">제외된 AI 없음</p>
        ) : (
          <List
            items={result.dropouts.map(
              (dropout) =>
                `참여자 ${dropout.label} · ${providerLabel(dropout.provider)} (${dropout.model}) — ${dropout.round}라운드, ${dropout.reason}`,
            )}
          />
        )}
      </div>
      <p className="muted">종료 사유: {result.end_reason}</p>
    </section>
  );
}
