import type { Cycle, User } from "@pacer/core";
import { cookies } from "next/headers";
import { ANON_COOKIE } from "@/lib/anon-session";
import { getAuthService, getCycleService } from "@/lib/container";
import { getCurrentSupabaseUser } from "@/lib/supabase/server";

/**
 * 사이클 소유권 확인 — 익명 세션 쿠키 또는 Supabase 로그인 사용자와 대조 (§9.2).
 * 불일치/부재는 모두 null(라우트에서 404) — 존재 여부를 노출하지 않는다.
 */
export async function authorizeCycle(cycleId: string): Promise<Cycle | null> {
  const cycle = await getCycleService().getCycle(cycleId);
  if (!cycle) return null;

  const store = await cookies();
  const anonId = store.get(ANON_COOKIE)?.value;

  if (cycle.anonSessionId && anonId === cycle.anonSessionId) return cycle;
  if (cycle.userId) {
    const user = await getCurrentAppUser();
    if (user?.id === cycle.userId) return cycle;
  }

  return null;
}

export async function getCurrentAppUser(): Promise<User | null> {
  const supabaseUser = await getCurrentSupabaseUser();
  if (!supabaseUser) return null;
  return getAuthService().getUserBySupabaseId(supabaseUser.id);
}
