"use client";

import { useEffect, useState } from "react";
import { ErrorNotice } from "@/components/ErrorNotice";
import { SlotEditor } from "@/components/SlotEditor";
import { StallThresholdForm } from "@/components/StallThresholdForm";
import { errorMessage, getConfig, listSlots, updateConfig, updateSlot } from "@/lib/api";
import type { AppConfig, Slot } from "@/lib/types";

export default function SettingsPage() {
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listSlots(), getConfig()]).then(
      ([loadedSlots, loadedConfig]) => {
        setSlots(loadedSlots);
        setConfig(loadedConfig);
      },
      (caught) => setError(errorMessage(caught)),
    );
  }, []);

  return (
    <>
      <h1>설정</h1>
      <ErrorNotice message={error} />
      {(!slots || !config) && !error && <p className="muted">설정을 불러오는 중…</p>}
      {slots && config && (
        <div className="stack">
          <StallThresholdForm
            value={config.stall_threshold}
            onSave={async (value) => setConfig(await updateConfig(value))}
          />
          {slots.map((slot) => (
            <SlotEditor key={slot.id} slot={slot} providers={config.providers} onSave={(input) => updateSlot(slot.id, input)} />
          ))}
        </div>
      )}
    </>
  );
}
