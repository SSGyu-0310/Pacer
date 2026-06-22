import type { StrategyReport } from "@pacer/core";
import { AI_USAGE_NOTICE, DISCLAIMER, createReportRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getReportService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * §10.6 AI 리포트 생성 — ReportService.generate.
 * 게이트웨이가 §11.3 스키마·§11.4 금지어·§13.3 면책 문구를 보장한 결과만 저장·반환된다.
 * AI 사용 고지(§13.4)는 응답에 별도 필드로 동봉한다.
 */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = createReportRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const r = await getReportService().generate({
      cycleId,
      examScoreId: parsed.data.exam_score_id,
      analysisSnapshotId: parsed.data.analysis_snapshot_id,
      reportType: parsed.data.report_type,
    });
    return NextResponse.json(serializeReport(r), { status: 201 });
  } catch (e) {
    return fromDomainError(e);
  }
}

/** 저장된 리포트 조회 — reportId가 없으면 cycle의 최신 리포트. */
export async function GET(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  const reportId = new URL(req.url).searchParams.get("reportId");
  try {
    const report = reportId
      ? await getReportService().getReport(cycleId, reportId)
      : await getReportService().getLatestReport(cycleId);
    return NextResponse.json(serializeReport(report));
  } catch (e) {
    return fromDomainError(e);
  }
}

function serializeReport(
  r:
    | {
        reportId: string;
        content: StrategyReport["content"];
        modelName: string;
        promptVersion: string;
      }
    | StrategyReport,
) {
  const reportId = "reportId" in r ? r.reportId : r.id;
  return {
    report_id: reportId,
    content: {
      one_line_summary: r.content.oneLineSummary,
      student_summary: r.content.studentSummary,
      parent_summary: r.content.parentSummary,
      strengths: r.content.strengths.map((s) => ({
        title: s.title,
        description: s.description,
        reason_code: s.reasonCode,
      })),
      weaknesses: r.content.weaknesses.map((w) => ({
        title: w.title,
        description: w.description,
        reason_code: w.reasonCode,
      })),
      recommended_actions: r.content.recommendedActions,
      warnings: r.content.warnings,
      next_cta: r.content.nextCta,
    },
    model_name: r.modelName,
    prompt_version: r.promptVersion,
    disclaimer: DISCLAIMER,
    ai_usage_notice: AI_USAGE_NOTICE,
  };
}
