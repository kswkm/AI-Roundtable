"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Banners } from "@/components/Banners";
import { ErrorNotice } from "@/components/ErrorNotice";
import { FinalResultCard } from "@/components/FinalResultCard";
import { ProgressHeader } from "@/components/ProgressHeader";
import { RoundList } from "@/components/RoundList";
import { errorMessage, resumeDebate, stopDebate } from "@/lib/api";
import { useDebate } from "@/lib/useDebate";

export default function DebatePage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { debate, error, live, refresh, reconnect } = useDebate(id);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function run(action: () => Promise<void>, after: () => void) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      after();
    } catch (caught) {
      setActionError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!Number.isInteger(id) || id <= 0) return <ErrorNotice message="잘못된 토론 주소입니다." />;
  if (!debate) return error ? <ErrorNotice message={error} /> : <p className="muted">토론을 불러오는 중…</p>;

  return (
    <div className="stack">
      <ProgressHeader
        debate={debate}
        live={live}
        busy={busy}
        onStop={() => void run(() => stopDebate(id), () => void refresh())}
        onResume={() => void run(() => resumeDebate(id), reconnect)}
      />
      <ErrorNotice message={actionError ?? error} />
      <Banners debate={debate} />
      {debate.result && <FinalResultCard result={debate.result} grade={debate.grade} participants={debate.participants} />}
      <h2>라운드별 발언</h2>
      <RoundList rounds={debate.rounds} participants={debate.participants} />
    </div>
  );
}
