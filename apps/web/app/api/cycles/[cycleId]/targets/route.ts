import { saveTargetRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getTargetRepository } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** §10.3 목표 저장 — 시험 시점별 1건 upsert(목표는 성적 따라 바뀐다 §9.5). */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = saveTargetRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    await getTargetRepository().save({
      cycleId,
      examType: parsed.data.exam_type,
      targetUniversities: parsed.data.target_universities,
      targetMajorGroups: parsed.data.target_major_groups,
      preferredRegions: parsed.data.preferred_regions,
      riskProfile: parsed.data.risk_profile,
      susiJungsiPreference: parsed.data.susi_jungsi_preference,
    });
    return NextResponse.json({ status: "saved" }, { status: 201 });
  } catch (e) {
    return fromDomainError(e);
  }
}
