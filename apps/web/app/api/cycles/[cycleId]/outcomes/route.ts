import { submitOutcomeRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getOutcomeService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * §7.11 합불 결과 수집 (P2/Phase4) — 데이터 해자.
 * 인증자료는 선택 제출(§7.11 개인정보 원칙) — 파일 업로드는 별도 경로, 여기엔 URL만.
 */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = submitOutcomeRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const { outcomeId } = await getOutcomeService().submit(cycleId, {
      unitId: parsed.data.unit_id,
      applied: parsed.data.applied,
      result: parsed.data.result,
      waitlistNumber: parsed.data.waitlist_number ?? null,
      registered: parsed.data.registered ?? null,
      evidenceFileUrl: parsed.data.evidence_file_url ?? null,
    });
    return NextResponse.json(
      { outcome_id: outcomeId, status: "saved" },
      { status: 201 },
    );
  } catch (e) {
    return fromDomainError(e);
  }
}

/** 제출한 합불 결과 목록 */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const outcomes = await getOutcomeService().list(cycleId);
    return NextResponse.json({
      outcomes: outcomes.map((o) => ({
        outcome_id: o.id,
        unit_id: o.unitId,
        applied: o.applied,
        result: o.result,
        waitlist_number: o.waitlistNumber,
        registered: o.registered,
      })),
    });
  } catch (e) {
    return fromDomainError(e);
  }
}
