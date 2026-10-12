"use client";

import { type FormEvent, useState } from "react";
import { errorMessage } from "@/lib/api";
import { providerLabel, slotUnavailableReason } from "@/lib/format";
import type { Slot } from "@/lib/types";
import { ErrorNotice } from "./ErrorNotice";
import { SlotBadge } from "./SlotBadge";

interface Props {
  slots: Slot[];
  onSubmit: (question: string, slotIds: number[]) => Promise<void>;
}

export function QuestionForm({ slots, onSubmit }: Props) {
  const participants = slots.filter((slot) => slot.kind === "participant");
  const judge = slots.find((slot) => slot.kind === "judge");
  const judgeProblem = judge ? slotUnavailableReason(judge) : "판정 슬롯 정보를 불러오지 못했습니다";

  const [question, setQuestion] = useState("");
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(participants.filter((slot) => slotUnavailableReason(slot) === null).map((slot) => slot.id)),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const trimmed = question.trim();
  const canStart = trimmed !== "" && selected.size > 0 && judgeProblem === null && !submitting;

  function toggle(id: number) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!canStart) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(trimmed, participants.filter((slot) => selected.has(slot.id)).map((slot) => slot.id));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="stack" onSubmit={handleSubmit}>
      <label>
        <span className="muted">질문</span>
        <textarea
          aria-label="질문"
          value={question}
          maxLength={4000}
          placeholder="여러 AI의 의견을 듣고 싶은 질문을 입력하세요"
          onChange={(event) => setQuestion(event.target.value)}
        />
      </label>

      <fieldset className="stack" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="muted">참여 AI (1~4개)</legend>
        {participants.map((slot) => {
          const problem = slotUnavailableReason(slot);
          return (
            <label key={slot.id} className="slot-option" data-disabled={problem !== null}>
              <input
                type="checkbox"
                checked={selected.has(slot.id)}
                disabled={problem !== null}
                onChange={() => toggle(slot.id)}
              />
              <span>
                {providerLabel(slot.provider)} · {slot.model}
              </span>
              <SlotBadge slot={slot} />
              {problem && <span className="muted">{problem}</span>}
            </label>
          );
        })}
      </fieldset>

      {judge && (
        <p className="muted">
          판정 AI: {providerLabel(judge.provider)} · {judge.model} <SlotBadge slot={judge} />
        </p>
      )}
      {judgeProblem && <ErrorNotice message={`판정 AI를 쓸 수 없어 토론을 시작할 수 없습니다: ${judgeProblem}`} />}
      <ErrorNotice message={error} />

      <div className="row">
        <button type="submit" disabled={!canStart}>
          {submitting ? "시작하는 중…" : "토론 시작"}
        </button>
      </div>
    </form>
  );
}
