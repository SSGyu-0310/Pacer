import { randomUUID } from "node:crypto";
import { cookies } from "next/headers";

export const ANON_COOKIE = "anon_session_id";
export const ANON_MAX_AGE = 60 * 60 * 24 * 180; // 180일

export async function getAnonSessionId(): Promise<string | null> {
  const store = await cookies();
  return store.get(ANON_COOKIE)?.value ?? null;
}

/**
 * 익명 세션 식별자 조회/생성 (§9.2). 가입 전 데이터는 이 id로 묶인다.
 * 새로 생성한 경우 setCookie=true → 라우트가 응답 쿠키에 심는다.
 */
export async function getOrCreateAnonSessionId(): Promise<{
  id: string;
  setCookie: boolean;
}> {
  const existing = await getAnonSessionId();
  if (existing) return { id: existing, setCookie: false };
  return { id: randomUUID(), setCookie: true };
}
