import Link from "next/link";
import { DEBATE_STATUS_LABEL, GRADE_LABEL, formatDateTime } from "@/lib/format";
import type { DebateSummary } from "@/lib/types";

export function HistoryTable({ debates }: { debates: DebateSummary[] }) {
  if (debates.length === 0) return <p className="muted">아직 토론 기록이 없습니다.</p>;
  return (
    <table>
      <thead>
        <tr>
          <th>질문</th>
          <th>상태</th>
          <th>결론</th>
          <th>시작</th>
        </tr>
      </thead>
      <tbody>
        {debates.map((debate) => (
          <tr key={debate.id}>
            <td className="question-cell">
              <Link href={`/debates/${debate.id}`}>{debate.question}</Link>
            </td>
            <td>{DEBATE_STATUS_LABEL[debate.status]}</td>
            <td>{debate.grade ? GRADE_LABEL[debate.grade] : "—"}</td>
            <td>{formatDateTime(debate.started_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
