"use client";

import { type FormEvent, useState } from "react";
import { errorMessage } from "@/lib/api";
import { ErrorNotice } from "./ErrorNotice";

export function StallThresholdForm({ value, onSave }: { value: number; onSave: (value: number) => Promise<void> }) {
  const [text, setText] = useState(String(value));
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaved(false);
    const parsed = Number(text);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 10) {
      setError("1~10 사이의 정수를 입력하세요");
      return;
    }
    setError(null);
    try {
      await onSave(parsed);
      setSaved(true);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <form className="panel stack" noValidate onSubmit={handleSubmit}>
      <label>
        <span className="muted">정체 기준 (연속 라운드 수, 1~10)</span>
        <input
          aria-label="정체 기준 (연속 라운드 수, 1~10)"
          type="number"
          min={1}
          max={10}
          value={text}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <p className="muted">판정 AI가 이 횟수만큼 연속으로 "정체"라고 보면 토론을 마칩니다. 새 토론부터 적용됩니다.</p>
      <ErrorNotice message={error} />
      {saved && (
        <p className="muted" role="status">
          저장했습니다
        </p>
      )}
      <div className="row">
        <button type="submit">정체 기준 저장</button>
      </div>
    </form>
  );
}
