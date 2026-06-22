import { DISCLAIMER } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getAnalysisService, getScoreService } from "@/lib/container";
import { fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * §10.5 분석 결과 조회.
 * 결과(구간·신뢰도·reason code)만 전달 — 환산식/입결 원문 노출 금지 (§8.1).
 * 면책 문구(§13.3)는 모든 결과 응답에 동봉한다.
 */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ snapshotId: string }> },
): Promise<NextResponse> {
  const { snapshotId } = await ctx.params;

  try {
    const service = getAnalysisService();
    const meta = await service.getSnapshotMeta(snapshotId);
    const cycle = await authorizeCycle(meta.cycleId);
    if (!cycle) return notFound();

    const results = await service.getResults(snapshotId);
    // 본인 입력 점수(과목·표준점수·백분위) — 분포 시각화용. 환산식/입결이 아닌
    // 사용자 자신의 데이터이므로 §8.1 비노출 원칙에 저촉되지 않는다.
    const examScore = await getScoreService().getById(meta.examScoreId);
    return NextResponse.json({
      snapshot_id: snapshotId,
      exam_type: examScore.examType,
      track: cycle.track,
      subject_scores: examScore.scores.map((s) => ({
        subject: s.subject,
        selection: s.selection ?? null,
        standard_score: s.standardScore ?? null,
        percentile: s.percentile ?? null,
        grade: s.grade ?? null,
      })),
      results: results.map((r) => ({
        unit_id: r.unit.unitId,
        university: r.unit.university,
        unit_name: r.unit.unitName,
        recruitment_group: r.unit.recruitmentGroup,
        band: r.band,
        confidence: r.confidence,
        score_gap: r.scoreGap,
        reason_codes: r.reasonCodes,
        warnings: r.warnings,
      })),
      disclaimer: DISCLAIMER,
    });
  } catch (e) {
    return fromDomainError(e);
  }
}
