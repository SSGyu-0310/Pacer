import { createCycleRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { z } from "zod";
import {
  getAnonSessionId,
  getOrCreateAnonSessionId,
  ANON_COOKIE,
  ANON_MAX_AGE,
} from "@/lib/anon-session";
import { getCurrentAppUser } from "@/lib/authz";
import { getCycleService } from "@/lib/container";
import { badRequest, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** §10.1 입시 사이클 생성 — 익명 세션 포함. 라우트는 얇은 어댑터. */
export async function POST(req: Request): Promise<NextResponse> {
  const json: unknown = await req.json().catch(() => null);
  const parsed = createCycleRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const anon = await getOrCreateAnonSessionId();
  const user = await getCurrentAppUser();
  const result = await getCycleService().getOrCreateCycle({
    userId: user?.id ?? null,
    anonSessionId: anon.id,
    admissionYear: parsed.data.admission_year,
    gradeStatus: parsed.data.grade_status,
    track: parsed.data.track,
  });

  const res = NextResponse.json(
    { cycle_id: result.cycle.id, status: result.created ? "created" : "reused" },
    { status: result.created ? 201 : 200 },
  );
  if (anon.setCookie) {
    res.cookies.set(ANON_COOKIE, anon.id, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      maxAge: ANON_MAX_AGE,
    });
  }
  return res;
}

/** 현재 익명 세션 또는 로그인 사용자의 cycle 복원 — PWA 재방문/dashboard 시작점. */
export async function GET(req: Request): Promise<NextResponse> {
  const parsed = z
    .object({ admission_year: z.coerce.number().int() })
    .safeParse(Object.fromEntries(new URL(req.url).searchParams));
  if (!parsed.success) return badRequest(parsed.error);

  const service = getCycleService();

  const anonSessionId = await getAnonSessionId();
  const anonCycle = anonSessionId
    ? await service.getCycleForAnonSession({
        anonSessionId,
        admissionYear: parsed.data.admission_year,
      })
    : null;
  const user = await getCurrentAppUser();
  const cycle =
    anonCycle ??
    (user
      ? await service.getCycleForUser({
          userId: user.id,
          admissionYear: parsed.data.admission_year,
        })
      : null);
  if (!cycle) return notFound();

  return NextResponse.json({
    cycle_id: cycle.id,
    admission_year: cycle.admissionYear,
    grade_status: cycle.gradeStatus,
    track: cycle.track,
  });
}
