"use client";

import { useEffect, useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { HistoryTable } from "@/components/HistoryTable";
import { errorMessage, listDebates } from "@/lib/api";
import type { DebateSummary } from "@/lib/types";

export default function HistoryPage() {
  const [debates, setDebates] = useState<DebateSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listDebates().then(setDebates, (caught) => setError(errorMessage(caught)));
  }, []);

  return (
    <>
      <h1>토론 기록</h1>
      <ErrorNotice message={error} />
      {debates === null && !error && <p className="muted">기록을 불러오는 중…</p>}
      {debates && (
        <section className="panel">
          <HistoryTable debates={debates} />
        </section>
      )}
    </>
  );
}
