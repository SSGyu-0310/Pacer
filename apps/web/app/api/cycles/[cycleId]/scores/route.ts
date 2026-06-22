import { saveScoresRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getScoreService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** §10.2 성적 저장 — 검증 통과 시 저장, 경고는 응답에 포함. */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = saveScoresRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const { examScore, warnings } = await getScoreService().saveScores(cycleId, {
      examType: parsed.data.exam_type,
      scoreStatus: parsed.data.score_status,
      scores: parsed.data.scores.map((s) => ({
        subject: s.subject,
        selection: s.selection,
        rawScore: s.raw_score,
        standardScore: s.standard_score,
        percentile: s.percentile,
        grade: s.grade,
      })),
    });
    return NextResponse.json(
      {
        exam_score_id: examScore.id,
        validation: { valid: true, warnings },
      },
      { status: 201 },
    );
  } catch (e) {
    return fromDomainError(e);
  }
}
