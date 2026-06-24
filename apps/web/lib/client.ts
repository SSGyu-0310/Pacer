"use client";

/** P0 클라이언트 공통 — 로컬 진행상태 저장/HTTP 헬퍼 (페이지별 중복 제거) */

export const STORAGE_KEY = "pacer:p0";
export { ADMISSION_YEAR } from "@/lib/constants";

export type StoredState = {
  cycleId?: string;
  examScoreId?: string;
  snapshotId?: string;
  reportId?: string;
  report?: unknown;
};

export function readStoredState(): StoredState | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredState;
  } catch {
    return null;
  }
}

export function writeStoredState(next: StoredState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

/** POST JSON — 서버 메시지가 있으면 그대로 노출(없으면 상태코드 포함 일반 문구) */
export async function postJson<T = unknown>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { message?: string } | null;
    throw new Error(data?.message ?? `요청 실패(${res.status})`);
  }
  return (await res.json()) as T;
}
