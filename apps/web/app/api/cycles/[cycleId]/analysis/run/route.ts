import { runAnalysisRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getAnalysisService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * §10.4 분석 실행 — AnalysisService.run (§17.3).
 * 계산은 전부 서버의 엔진에서 — 환산식/입결 원문은 응답에 포함하지 않는다 (§8.1).
 */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = runAnalysisRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const result = await getAnalysisService().run(
      cycleId,
      parsed.data.exam_score_id,
      parsed.data.analysis_type,
    );
    return NextResponse.json({
      analysis_snapshot_id: result.snapshotId,
      status: "completed" as const,
      band_distribution: result.bandDistribution,
    });
  } catch (e) {
    return fromDomainError(e);
  }
}
