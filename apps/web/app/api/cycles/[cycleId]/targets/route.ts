import { prisma } from "@pacer/db";
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
    const resolvedTargets = await resolveReferenceTargets({
      admissionYear: cycle.admissionYear,
      targetUniversityIds: parsed.data.target_university_ids,
      targetUnitIds: parsed.data.target_unit_ids,
      legacyTargetUniversities: parsed.data.target_universities,
      legacyTargetMajorGroups: parsed.data.target_major_groups,
    });
    if (!resolvedTargets.ok) {
      return NextResponse.json(
        { error: "invalid_reference_target", message: resolvedTargets.message },
        { status: 400 },
      );
    }

    await getTargetRepository().save({
      cycleId,
      examType: parsed.data.exam_type,
      targetUniversities: resolvedTargets.targetUniversities,
      targetUniversityIds: resolvedTargets.targetUniversityIds,
      targetMajorGroups: resolvedTargets.targetMajorGroups,
      targetUnitIds: resolvedTargets.targetUnitIds,
      preferredRegions: parsed.data.preferred_regions,
      riskProfile: parsed.data.risk_profile,
      susiJungsiPreference: parsed.data.susi_jungsi_preference,
    });
    return NextResponse.json({ status: "saved" }, { status: 201 });
  } catch (e) {
    return fromDomainError(e);
  }
}

async function resolveReferenceTargets(input: {
  admissionYear: number;
  targetUniversityIds: string[];
  targetUnitIds: string[];
  legacyTargetUniversities: string[];
  legacyTargetMajorGroups: string[];
}): Promise<
  | {
      ok: true;
      targetUniversities: string[];
      targetUniversityIds: string[];
      targetMajorGroups: string[];
      targetUnitIds: string[];
    }
  | { ok: false; message: string }
> {
  const targetUnitIds = unique(input.targetUnitIds);
  const requestedUniversityIds = unique(input.targetUniversityIds);

  const selectedUnits = targetUnitIds.length
    ? await prisma.admissionUnit.findMany({
        where: {
          id: { in: targetUnitIds },
          year: input.admissionYear,
          active: true,
        },
        include: { university: true },
      })
    : [];
  if (selectedUnits.length !== targetUnitIds.length) {
    return { ok: false, message: "선택한 모집단위를 찾을 수 없습니다" };
  }

  const unitUniversityIds = selectedUnits.map((unit) => unit.universityId);
  const seedUniversityIds = unique([
    ...requestedUniversityIds,
    ...unitUniversityIds,
  ]);
  const selectedUniversities = seedUniversityIds.length
    ? await prisma.university.findMany({
        where: { id: { in: seedUniversityIds } },
      })
    : [];
  if (selectedUniversities.length !== seedUniversityIds.length) {
    return { ok: false, message: "선택한 대학을 찾을 수 없습니다" };
  }

  const expandedUniversities = selectedUniversities.length
    ? await prisma.university.findMany({
        where: {
          OR: selectedUniversities.map((university) => ({
            name: university.name,
            campus: university.campus,
          })),
          admissionUnits: {
            some: {
              year: input.admissionYear,
              active: true,
            },
          },
        },
      })
    : [];
  const targetUniversityIds = unique([
    ...seedUniversityIds,
    ...expandedUniversities.map((university) => university.id),
  ]);
  const universityById = new Map([
    ...selectedUniversities.map((university) => [university.id, university] as const),
    ...expandedUniversities.map((university) => [university.id, university] as const),
  ]);
  const targetUniversities = targetUniversityIds.length
    ? targetUniversityIds
        .map((id) => universityById.get(id)?.name)
        .filter((name): name is string => typeof name === "string")
    : unique(input.legacyTargetUniversities);

  const targetMajorGroups = unique([
    ...input.legacyTargetMajorGroups,
    ...selectedUnits
      .map((unit) => unit.majorGroup)
      .filter((majorGroup): majorGroup is string => Boolean(majorGroup)),
  ]);

  return {
    ok: true,
    targetUniversities,
    targetUniversityIds,
    targetMajorGroups,
    targetUnitIds,
  };
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}
