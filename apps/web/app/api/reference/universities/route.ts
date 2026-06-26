import { prisma } from "@pacer/db";
import type { CoreReviewTier } from "@pacer/shared";
import { NextResponse } from "next/server";
import { getCoreUniversityMetadata } from "@/lib/admin-core";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ADMISSION_YEAR = 2027;
const DEFAULT_LIMIT = 20;
const MAX_LIMIT = 80;
const INITIAL_GROUPS = {
  "ㄱ": ["ㄱ", "ㄲ"],
  "ㄴ-ㅂ": ["ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ"],
  "ㅅ": ["ㅅ", "ㅆ"],
  "ㅇ-ㅈ": ["ㅇ", "ㅈ", "ㅉ"],
  "ㅊ-ㅎ": ["ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"],
} as const;
const CHOSEONG = [
  "ㄱ",
  "ㄲ",
  "ㄴ",
  "ㄷ",
  "ㄸ",
  "ㄹ",
  "ㅁ",
  "ㅂ",
  "ㅃ",
  "ㅅ",
  "ㅆ",
  "ㅇ",
  "ㅈ",
  "ㅉ",
  "ㅊ",
  "ㅋ",
  "ㅌ",
  "ㅍ",
  "ㅎ",
] as const;
const UNIVERSITY_ALIASES: Record<string, string[]> = {
  고려대학교: ["고대"],
  성균관대학교: ["성대"],
  이화여자대학교: ["이대", "이화여대"],
  중앙대학교: ["중대"],
  건국대학교: ["건대"],
  숙명여자대학교: ["숙대"],
  홍익대학교: ["홍대"],
  한국외국어대학교: ["외대", "한국외대"],
  서울시립대학교: ["시립대"],
  한국과학기술원: ["카이스트", "kaist"],
  포항공과대학교: ["포스텍", "postech"],
  울산과학기술원: ["유니스트", "unist"],
  광주과학기술원: ["지스트", "gist"],
  대구경북과학기술원: ["디지스트", "dgist"],
};

export async function GET(req: Request): Promise<NextResponse> {
  const url = new URL(req.url);
  const q = url.searchParams.get("q")?.trim() ?? "";
  const initialGroup = url.searchParams.get("initial_group")?.trim() ?? "";
  const limit = clampLimit(url.searchParams.get("limit"));
  const metadata = getCoreUniversityMetadata();

  const universities = await prisma.university.findMany({
    where: {
      admissionUnits: {
        some: {
          year: ADMISSION_YEAR,
          active: true,
        },
      },
    },
    select: {
      id: true,
      name: true,
      campus: true,
      displayOrder: true,
    },
  });
  const initials = initialGroupInitials(initialGroup);
  const normalizedQuery = normalizeSearch(q);
  const filtered = universities
    .map((university) => ({
      university,
      matchRank: normalizedQuery ? universitySearchRank(university, normalizedQuery) : 0,
    }))
    .filter(({ university, matchRank }) => {
      if (normalizedQuery) return matchRank !== null;
      if (!initials) return true;
      return initials.has(koreanInitial(university.name));
    });

  const counts = filtered.length
    ? await prisma.admissionUnit.groupBy({
        by: ["universityId"],
        where: {
          universityId: { in: filtered.map(({ university }) => university.id) },
          year: ADMISSION_YEAR,
          active: true,
        },
        _count: { _all: true },
      })
    : [];
  const unitCountByUniversityId = new Map(
    counts.map((count) => [count.universityId, count._count._all]),
  );

  const rows = mergeDuplicateDisplayNames(filtered
    .map(({ university, matchRank }) => {
      const coreTier = metadata.tierByUniversityId.get(university.id) ?? null;
      return {
        id: university.id,
        related_ids: [university.id],
        name: university.name,
        campus: university.campus,
        display_name: displayUniversityName(university),
        core_tier: coreTier,
        unit_count: unitCountByUniversityId.get(university.id) ?? 0,
        matchRank: matchRank ?? 0,
        sortKey: coreSortKey(coreTier),
        displayOrder: university.displayOrder,
      };
    }))
    .sort((a, b) => {
      if (a.matchRank !== b.matchRank) return a.matchRank - b.matchRank;
      if (a.sortKey !== b.sortKey) return a.sortKey - b.sortKey;
      if (a.displayOrder !== b.displayOrder) return a.displayOrder - b.displayOrder;
      return a.display_name.localeCompare(b.display_name, "ko");
    })
    .slice(0, limit)
    .map(
      ({
        matchRank: _matchRank,
        sortKey: _sortKey,
        displayOrder: _displayOrder,
        ...row
      }) => row,
    );

  return NextResponse.json({ universities: rows });
}

function clampLimit(value: string | null): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_LIMIT;
  return Math.min(Math.max(Math.trunc(parsed), 1), MAX_LIMIT);
}

function displayUniversityName(university: { name: string; campus: string | null }): string {
  return university.campus ? `${university.name} (${university.campus})` : university.name;
}

function initialGroupInitials(group: string): Set<string> | null {
  const initials = INITIAL_GROUPS[group as keyof typeof INITIAL_GROUPS];
  return initials ? new Set(initials) : null;
}

function koreanInitial(value: string): string {
  const first = value.trim().charAt(0);
  const code = first.charCodeAt(0);
  if (code < 0xac00 || code > 0xd7a3) return first.toUpperCase();
  return CHOSEONG[Math.floor((code - 0xac00) / 588)] ?? first;
}

function universitySearchRank(
  university: { name: string; campus: string | null },
  query: string,
): number | null {
  const fields = universitySearchFields(university);
  if (fields.some((field) => field === query)) return 0;
  if (fields.some((field) => field.startsWith(query))) return 1;
  if (fields.some((field) => field.includes(query))) return 2;
  return null;
}

function universitySearchFields(university: { name: string; campus: string | null }): string[] {
  const base = stripUniversitySuffix(university.name);
  const aliases = [
    university.name,
    displayUniversityName(university),
    base,
    `${base}대`,
    ...(university.campus ? [university.campus] : []),
    ...(UNIVERSITY_ALIASES[university.name] ?? []),
  ];
  return [...new Set(aliases.map(normalizeSearch).filter(Boolean))];
}

function normalizeSearch(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/[()\[\]\s·.,-]/g, "")
    .toLowerCase();
}

function stripUniversitySuffix(name: string): string {
  return name.replace(/대학교$/, "").replace(/대학$/, "");
}

interface UniversityResponseRow {
  id: string;
  related_ids: string[];
  name: string;
  campus: string | null;
  display_name: string;
  core_tier: CoreReviewTier | null;
  unit_count: number;
  matchRank: number;
  sortKey: number;
  displayOrder: number;
}

function mergeDuplicateDisplayNames(rows: UniversityResponseRow[]): UniversityResponseRow[] {
  const byDisplayName = new Map<string, UniversityResponseRow>();
  for (const row of rows) {
    const current = byDisplayName.get(row.display_name);
    if (!current) {
      byDisplayName.set(row.display_name, { ...row });
      continue;
    }
    current.related_ids = [...new Set([...current.related_ids, ...row.related_ids])];
    current.unit_count += row.unit_count;
    current.matchRank = Math.min(current.matchRank, row.matchRank);
    if (row.sortKey < current.sortKey) {
      current.core_tier = row.core_tier;
      current.sortKey = row.sortKey;
    }
    if (row.displayOrder < current.displayOrder) {
      current.id = row.id;
      current.name = row.name;
      current.campus = row.campus;
      current.displayOrder = row.displayOrder;
    }
  }
  return [...byDisplayName.values()];
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
