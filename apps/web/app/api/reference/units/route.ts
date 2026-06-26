import { prisma } from "@pacer/db";
import type { CoreReviewTier } from "@pacer/shared";
import { NextResponse } from "next/server";
import { getCoreUniversityMetadata } from "@/lib/admin-core";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ADMISSION_YEAR = 2027;
const DEFAULT_LIMIT = 30;
const MAX_LIMIT = 80;
const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export async function GET(req: Request): Promise<NextResponse> {
  const url = new URL(req.url);
  const universityId = url.searchParams.get("university_id")?.trim() ?? "";
  const q = url.searchParams.get("q")?.trim() ?? "";
  const majorGroup = url.searchParams.get("major_group")?.trim() ?? "";
  const limit = clampLimit(url.searchParams.get("limit"));
  if (universityId && !UUID_RE.test(universityId)) {
    return NextResponse.json({ units: [] });
  }
  const universityIds = universityId ? await expandUniversityIds(universityId) : [];
  if (universityId && universityIds.length === 0) {
    return NextResponse.json({ units: [] });
  }

  const units = await prisma.admissionUnit.findMany({
    where: {
      year: ADMISSION_YEAR,
      active: true,
      ...(universityIds.length ? { universityId: { in: universityIds } } : {}),
      ...(majorGroup ? { majorGroup } : {}),
      ...(q
        ? {
            OR: [
              { name: { contains: q, mode: "insensitive" } },
              { university: { name: { contains: q, mode: "insensitive" } } },
            ],
          }
        : {}),
    },
    select: {
      id: true,
      universityId: true,
      name: true,
      recruitmentGroup: true,
      majorGroup: true,
      university: {
        select: {
          name: true,
          displayOrder: true,
        },
      },
      rules: {
        where: {
          year: ADMISSION_YEAR,
          verifiedStatus: { not: "deprecated" },
        },
        orderBy: { updatedAt: "desc" },
        take: 1,
        select: {
          id: true,
          verifiedStatus: true,
        },
      },
    },
  });

  const latestRuleIds = units.flatMap((unit) =>
    unit.rules[0]?.id ? [unit.rules[0].id] : [],
  );
  const decisions = latestRuleIds.length
    ? await prisma.referenceReviewDecision.findMany({
        where: {
          targetKind: "rule",
          targetId: { in: latestRuleIds },
          supersededAt: null,
          verdict: { in: ["confirm", "edit", "flag"] },
        },
        orderBy: { reviewedAt: "desc" },
        select: {
          targetId: true,
          verdict: true,
          reviewedVerifiedStatus: true,
        },
      })
    : [];
  const decisionByRuleId = new Map<
    string,
    { verdict: string; reviewedVerifiedStatus: string | null }
  >();
  for (const decision of decisions) {
    if (!decisionByRuleId.has(decision.targetId)) {
      decisionByRuleId.set(decision.targetId, decision);
    }
  }

  const metadata = getCoreUniversityMetadata();
  const rows = units
    .map((unit) => {
      const rule = unit.rules[0] ?? null;
      const decision = rule ? decisionByRuleId.get(rule.id) : undefined;
      const readiness = analysisReadiness(rule, decision);
      const coreTier = metadata.tierByUniversityId.get(unit.universityId) ?? null;
      return {
        id: unit.id,
        university_id: unit.universityId,
        university_name: unit.university.name,
        unit_name: unit.name,
        recruitment_group: unit.recruitmentGroup,
        major_group: unit.majorGroup,
        analysis_readiness: readiness,
        sortKey: coreSortKey(coreTier),
        readinessSortKey: readinessSortKey(readiness),
        displayOrder: unit.university.displayOrder,
      };
    })
    .sort((a, b) => {
      if (a.sortKey !== b.sortKey) return a.sortKey - b.sortKey;
      if (a.readinessSortKey !== b.readinessSortKey) {
        return a.readinessSortKey - b.readinessSortKey;
      }
      if (a.displayOrder !== b.displayOrder) return a.displayOrder - b.displayOrder;
      const universityCompare = a.university_name.localeCompare(
        b.university_name,
        "ko",
      );
      if (universityCompare !== 0) return universityCompare;
      return a.unit_name.localeCompare(b.unit_name, "ko");
    })
    .slice(0, limit)
    .map(
      ({
        sortKey: _sortKey,
        readinessSortKey: _readinessSortKey,
        displayOrder: _displayOrder,
        ...row
      }) => row,
    );

  return NextResponse.json({ units: rows });
}

function clampLimit(value: string | null): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_LIMIT;
  return Math.min(Math.max(Math.trunc(parsed), 1), MAX_LIMIT);
}

async function expandUniversityIds(universityId: string): Promise<string[]> {
  const university = await prisma.university.findUnique({
    where: { id: universityId },
    select: { name: true, campus: true },
  });
  if (!university) return [];
  const rows = await prisma.university.findMany({
    where: {
      name: university.name,
      campus: university.campus,
      admissionUnits: {
        some: {
          year: ADMISSION_YEAR,
          active: true,
        },
      },
    },
    select: { id: true },
  });
  return rows.map((row) => row.id);
}

function analysisReadiness(
  rule: { id: string; verifiedStatus: string } | null,
  decision?: { verdict: string; reviewedVerifiedStatus: string | null },
): "ready" | "limited" | "unsupported" {
  if (!rule) return "unsupported";
  if (decision?.verdict === "flag") return "unsupported";
  const status = decision?.reviewedVerifiedStatus ?? rule.verifiedStatus;
  if (status === "deprecated") return "unsupported";
  return status === "verified" || status === "live" ? "ready" : "limited";
}

function readinessSortKey(readiness: "ready" | "limited" | "unsupported"): number {
  return { ready: 0, limited: 1, unsupported: 2 }[readiness];
}

function coreSortKey(tier: CoreReviewTier | null): number {
  if (!tier) return 10;
  return {
    core: 0,
    must: 1,
    if_time: 2,
    eng_special: 3,
    med_health: 4,
  }[tier];
}
