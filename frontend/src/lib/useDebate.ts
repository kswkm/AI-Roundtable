"use client";

import { useCallback, useEffect, useState } from "react";
import { errorMessage, eventsUrl, getDebate } from "./api";
import type { DebateDetail } from "./types";

export interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent) => void): void;
  close(): void;
  onerror: ((event: Event) => void) | null;
}

export const DEBATE_EVENT_TYPES = [
  "round_started", "message", "judge_evaluated", "participant_dropped", "paused", "finished", "error", "status",
] as const;
const TERMINAL_EVENT_TYPES: readonly string[] = ["paused", "finished", "error", "status"];

const browserEventSource = (url: string): EventSourceLike => new EventSource(url);

interface Options {
  createEventSource?: (url: string) => EventSourceLike;
  reconnectMs?: number;
}

export function useDebate(id: number, { createEventSource = browserEventSource, reconnectMs = 2000 }: Options = {}) {
  const [debate, setDebate] = useState<DebateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [generation, setGeneration] = useState(0);

  const refresh = useCallback(async (): Promise<DebateDetail | null> => {
    try {
      const next = await getDebate(id);
      setDebate(next);
      setError(null);
      return next;
    } catch (caught) {
      setError(errorMessage(caught));
      return null;
    }
  }, [id]);

  useEffect(() => {
    let disposed = false;
    let source: EventSourceLike | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;

    const close = () => {
      source?.close();
      source = null;
      setLive(false);
    };

    const connect = async () => {
      const current = await refresh();
      if (disposed || current === null || current.status !== "running") return;
      const opened = createEventSource(eventsUrl(id));
      source = opened;
      setLive(true);
      for (const type of DEBATE_EVENT_TYPES) {
        opened.addEventListener(type, () => {
          if (source !== opened) return;
          if (TERMINAL_EVENT_TYPES.includes(type)) close();
          void refresh();
        });
      }
      opened.onerror = () => {
        if (source !== opened) return;
        close();
        if (!disposed) retry = setTimeout(() => void connect(), reconnectMs);
      };
    };

    void connect();
    return () => {
      disposed = true;
      clearTimeout(retry);
      close();
    };
  }, [id, refresh, createEventSource, reconnectMs, generation]);

  const reconnect = useCallback(() => setGeneration((value) => value + 1), []);

  return { debate, error, live, refresh, reconnect };
}
