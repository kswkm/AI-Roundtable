"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { QuestionForm } from "@/components/QuestionForm";
import { createDebate, errorMessage, listSlots } from "@/lib/api";
import type { Slot } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSlots().then(setSlots, (caught) => setError(errorMessage(caught)));
  }, []);

  async function start(question: string, slotIds: number[]) {
    const { id } = await createDebate(question, slotIds);
    router.push(`/debates/${id}`);
  }

  return (
    <>
      <h1>
        여러 AI에게 묻고, <span className="gradient-text">하나의 결론</span>으로
      </h1>
      <p className="muted">참여 AI들이 서로 검토·반박한 뒤 판정 AI가 통합 의견을 만듭니다.</p>
      <ErrorNotice message={error} />
      {slots === null && !error && <p className="muted">슬롯 정보를 불러오는 중…</p>}
      {slots && (
        <section className="panel">
          <QuestionForm slots={slots} onSubmit={start} />
        </section>
      )}
    </>
  );
}
