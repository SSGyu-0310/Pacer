import { createCompetitorSignalRequest, examType } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getCompetitorSignalService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * §10.7 외부 서비스 결과 저장 (P2) — ★ 수동 입력 전용, 자동 스크래핑 금지(§7.7.4).
 * 사용자가 진학사/고속성장/텔레그노시스에서 직접 본 값을 옮겨 적는 경로만 존재한다.
 */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = createCompetitorSignalRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const signal = await getCompetitorSignalService().create(cycleId, {
      examType: parsed.data.exam_type,
      provider: parsed.data.provider,
      unitId: parsed.data.unit_id,
      valueType: parsed.data.value_type,
      value: parsed.data.value,
    });
    return NextResponse.json(
      { signal_id: signal.id, status: "saved" },
      { status: 201 },
    );
  } catch (e) {
    return fromDomainError(e);
  }
}

/** 입력한 외부 도구 결과 목록 — ?exam_type= 으로 필터(교차검증 리포트 전 확인용) */
export async function GET(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  const raw = new URL(req.url).searchParams.get("exam_type");
  const parsedExam = raw === null ? null : examType.safeParse(raw);
  if (parsedExam && !parsedExam.success) {
    return NextResponse.json({ error: "invalid_exam_type" }, { status: 400 });
  }

  try {
    const signals = await getCompetitorSignalService().list(
      cycleId,
      parsedExam?.success ? parsedExam.data : undefined,
    );
    return NextResponse.json({
      signals: signals.map((s) => ({
        signal_id: s.id,
        exam_type: s.examType,
        provider: s.provider,
        unit_id: s.unitId,
        value_type: s.valueType,
        value: s.value,
      })),
    });
  } catch (e) {
    return fromDomainError(e);
  }
}
