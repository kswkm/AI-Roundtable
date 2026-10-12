import type { AppConfig, DebateDetail, DebateSummary, Slot, UpdateSlotInput } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

const UNREACHABLE =
  "백엔드 서버에 연결할 수 없습니다. 백엔드가 127.0.0.1:8000에서 실행 중인지 확인하세요.";

export function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "알 수 없는 오류가 발생했습니다";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  if (!response.ok) {
    let message = `요청이 실패했습니다 (HTTP ${response.status})`;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
    } catch {
      // 본문이 JSON이 아니면 기본 메시지를 쓴다
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as T;
}

function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  return request<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
}

export const listSlots = () => request<Slot[]>("/slots");
export const updateSlot = (id: number, input: UpdateSlotInput) => send<Slot>("PUT", `/slots/${id}`, input);
export const getConfig = () => request<AppConfig>("/config");
export const updateConfig = (stallThreshold: number) =>
  send<AppConfig>("PUT", "/config", { stall_threshold: stallThreshold });
export const createDebate = (question: string, slotIds: number[]) =>
  send<{ id: number }>("POST", "/debates", { question, slot_ids: slotIds });
export const listDebates = () => request<DebateSummary[]>("/debates");
export const getDebate = (id: number) => request<DebateDetail>(`/debates/${id}`);
export const stopDebate = async (id: number) => {
  await send<unknown>("POST", `/debates/${id}/stop`);
};
export const resumeDebate = async (id: number) => {
  await send<unknown>("POST", `/debates/${id}/resume`);
};
export const eventsUrl = (id: number) => `${API_BASE}/debates/${id}/events`;
