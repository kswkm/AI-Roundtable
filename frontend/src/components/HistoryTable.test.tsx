import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HistoryTable } from "./HistoryTable";

describe("HistoryTable", () => {
  it("질문, 상태, 결론 등급, 날짜를 보여 주고 상세로 연결한다", () => {
    render(
      <HistoryTable
        debates={[
          { id: 2, question: "자동 배포해도 되나요?", status: "converged", grade: "consensus", started_at: "2026-10-12T05:00:00Z", ended_at: "2026-10-12T05:10:00Z" },
          { id: 1, question: "모노레포가 나을까요?", status: "paused", grade: null, started_at: "2026-10-11T00:00:00Z", ended_at: null },
        ]}
      />,
    );
    expect(screen.getByRole("link", { name: "자동 배포해도 되나요?" })).toHaveAttribute("href", "/debates/2");
    expect(screen.getByText("수렴")).toBeInTheDocument();
    expect(screen.getByText("합의")).toBeInTheDocument();
    expect(screen.getByText("일시정지")).toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(1);
    expect(screen.getByText(/14:00/)).toBeInTheDocument();
  });

  it("기록이 없으면 안내 문구를 보여 준다", () => {
    render(<HistoryTable debates={[]} />);
    expect(screen.getByText("아직 토론 기록이 없습니다.")).toBeInTheDocument();
  });
});
