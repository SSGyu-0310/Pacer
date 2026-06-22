import { createApplicationPlanRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getApplicationPlanService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * §10.8 원서 조합 생성 (P2) — 최신 분석 결과 기반으로 엔진이 가/나/다군 조합을
 * 만든다(§7.10 전략 매트릭스). 요약은 결정적 문구이며 단정 표현을 쓰지 않는다.
 * LLM 설명(application_plan_report)은 §10.6 리포트 경로로 별도 생성.
 */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = createApplicationPlanRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const { planId, combination, skippedUnitIds } =
      await getApplicationPlanService().create(
        cycleId,
        parsed.data.plan_type,
        parsed.data.candidate_unit_ids,
      );

    // §10.8 응답 형태 — plans 배열(초기 버전은 요청 전략 1건)
    return NextResponse.json(
      {
        plan_id: planId,
        plans: [
          {
            strategy: combination.strategy,
            ga: combination.picks.ga.unit?.unitId ?? null,
            na: combination.picks.na.unit?.unitId ?? null,
            da: combination.picks.da.unit?.unitId ?? null,
            summary: combination.summary,
          },
        ],
        overall_risk: combination.overallRisk,
        riskiest_group: combination.riskiestGroup,
        most_stable_group: combination.mostStableGroup,
        warnings: combination.warnings,
        skipped_unit_ids: skippedUnitIds,
      },
      { status: 201 },
    );
  } catch (e) {
    return fromDomainError(e);
  }
}
