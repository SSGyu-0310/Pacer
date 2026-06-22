import type { Cycle } from "@pacer/core";
import { cookies } from "next/headers";
import { ANON_COOKIE } from "@/lib/anon-session";
import { getCycleService } from "@/lib/container";

/**
 * 사이클 소유권 확인 — 익명 세션 쿠키와 대조 (§9.2).
 * 불일치/부재는 모두 null(라우트에서 404) — 존재 여부를 노출하지 않는다.
 * 가입 사용자 인증(P1)은 여기서 세션 검사로 확장한다.
 */
export async function authorizeCycle(cycleId: string): Promise<Cycle | null> {
  const cycle = await getCycleService().getCycle(cycleId);
  if (!cycle) return null;

  const store = await cookies();
  const anonId = store.get(ANON_COOKIE)?.value;

  if (cycle.anonSessionId && anonId === cycle.anonSessionId) return cycle;
  return null;
}
