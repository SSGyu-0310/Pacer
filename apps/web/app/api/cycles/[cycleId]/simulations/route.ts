import { SIMULATION_NOTICE, runSimulationRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getSimulationService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * §7.9 점수 시뮬레이션 (P1) — 가상 점수로 엔진을 서버에서 재실행한다.
 * 결과는 저장되지 않으며(일회성), 환산식·입결 원문은 응답에 포함되지 않는다(§8.1).
 * §7.9 주의 문구를 모든 응답에 동봉한다.
 */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = runSimulationRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const result = await getSimulationService().run(
      cycleId,
      parsed.data.exam_score_id,
      parsed.data.adjustments.map((a) => ({
        subject: a.subject,
        gradeDelta: a.grade_delta,
        percentileDelta: a.percentile_delta,
        standardScoreDelta: a.standard_score_delta,
        override: a.override
          ? {
              standardScore: a.override.standard_score,
              percentile: a.override.percentile,
              grade: a.override.grade,
            }
          : undefined,
      })),
    );

    return NextResponse.json({
      baseline_band_distribution: result.baselineDistribution,
      simulated_band_distribution: result.simulatedDistribution,
      moved_to_match_or_better: result.movedToMatchOrBetter,
      band_changes: result.bandChanges.map((c) => ({
        unit_id: c.unit.unitId,
        university: c.unit.university,
        unit_name: c.unit.unitName,
        from_band: c.fromBand,
        to_band: c.toBand,
      })),
      target_approach: {
        baseline: result.targetApproach.baseline,
        simulated: result.targetApproach.simulated,
      },
      most_efficient_subject: result.mostEfficientSubject,
      caution_subjects: result.cautionSubjects,
      notice: SIMULATION_NOTICE,
    });
  } catch (e) {
    return fromDomainError(e);
  }
}
