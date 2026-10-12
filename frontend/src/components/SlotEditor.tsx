"use client";

import { type FormEvent, useState } from "react";
import { errorMessage } from "@/lib/api";
import { defaultKeyEnv, formatDateTime, formatPercent, providerLabel } from "@/lib/format";
import type { Slot, UpdateSlotInput } from "@/lib/types";
import { ErrorNotice } from "./ErrorNotice";
import { SlotBadge } from "./SlotBadge";

interface Props {
  slot: Slot;
  providers: string[];
  onSave: (input: UpdateSlotInput) => Promise<Slot>;
}

const NUMBER = new Intl.NumberFormat("ko-KR");

export function SlotEditor({ slot: initial, providers, onSave }: Props) {
  const [slot, setSlot] = useState(initial);
  const [provider, setProvider] = useState(initial.provider);
  const [model, setModel] = useState(initial.model);
  const [keyEnv, setKeyEnv] = useState(initial.api_key_env);
  const [limit, setLimit] = useState(initial.known_limit?.requests_per_day?.toString() ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const title = slot.kind === "judge" ? "판정 슬롯" : `참여 슬롯 ${slot.id}`;
  const providerOptions = providers.includes(provider) ? providers : [provider, ...providers];

  function handleProviderChange(next: string) {
    const nextDefault = defaultKeyEnv(next);
    if (nextDefault && (keyEnv.trim() === "" || keyEnv === defaultKeyEnv(provider))) setKeyEnv(nextDefault);
    setProvider(next);
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    const parsedLimit = Number.parseInt(limit, 10);
    try {
      const updated = await onSave({
        provider,
        model: model.trim(),
        api_key_env: keyEnv.trim(),
        known_limit: limit.trim() === "" || Number.isNaN(parsedLimit) ? null : { requests_per_day: parsedLimit },
      });
      setSlot(updated);
      setSaved(true);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel stack">
      <div className="row">
        <h2 style={{ margin: 0 }}>{title}</h2>
        <SlotBadge slot={slot} />
      </div>
      <p className="muted">
        현재: {providerLabel(slot.provider)} · {slot.model}
      </p>
      {slot.status_reason && <p className="muted">사유: {slot.status_reason}</p>}
      {slot.status_until && <p className="muted">해제 예상: {formatDateTime(slot.status_until)}</p>}
      <p className="muted">
        API 키: {slot.key_present ? "연결됨" : "없음"} ({slot.api_key_env})
      </p>
      <p className="muted">
        {`오늘 ${NUMBER.format(slot.usage.today_requests)}회 · ${NUMBER.format(slot.usage.today_tokens)}토큰 / 누적 ${NUMBER.format(slot.usage.total_requests)}회 · ${NUMBER.format(slot.usage.total_tokens)}토큰`}
      </p>
      {slot.usage_estimate !== null && <p className="muted">무료 한도 대비 추정 {formatPercent(slot.usage_estimate)}</p>}

      <form className="stack" onSubmit={handleSubmit}>
        <label>
          <span className="muted">회사</span>
          <select aria-label="회사" value={provider} onChange={(event) => handleProviderChange(event.target.value)}>
            {providerOptions.map((option) => (
              <option key={option} value={option}>
                {providerLabel(option)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="muted">모델</span>
          <input aria-label="모델" value={model} onChange={(event) => setModel(event.target.value)} />
        </label>
        <label>
          <span className="muted">API 키 환경변수</span>
          <input aria-label="API 키 환경변수" value={keyEnv} onChange={(event) => setKeyEnv(event.target.value)} />
        </label>
        <label>
          <span className="muted">하루 요청 한도 (선택)</span>
          <input
            aria-label="하루 요청 한도 (선택)"
            type="number"
            min={1}
            value={limit}
            onChange={(event) => setLimit(event.target.value)}
          />
        </label>
        <p className="muted">저장하면 이 슬롯의 소진·속도 제한 상태가 풀립니다. 키 값은 backend/.env에만 넣으세요.</p>
        <ErrorNotice message={error} />
        {saved && (
          <p className="muted" role="status">
            저장했습니다
          </p>
        )}
        <div className="row">
          <button type="submit" disabled={saving}>
            {saving ? "저장하는 중…" : "저장"}
          </button>
        </div>
      </form>
    </section>
  );
}
