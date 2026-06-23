import { readFileSync } from "node:fs";
import path from "node:path";
import type { CoreReviewTier } from "@pacer/shared";

const REPO_ROOT = process.cwd().replace(/\/apps\/web$/, "");
const CORE_FILE = path.resolve(REPO_ROOT, "packages/reference-data/data/review/core-universities.json");

interface CoreUniversityMetadata {
  universityIds: string[];
  tierByUniversityId: Map<string, CoreReviewTier>;
  flagByUniversityId: Map<string, string>;
}

let cache: CoreUniversityMetadata | null = null;

/** 핵심대 프리셋의 universityId 목록. 비어 있으면 큐를 전체로 둔다. */
export function getCoreUniversityIds(): string[] {
  return getCoreUniversityMetadata().universityIds;
}

export function getCoreUniversityMetadata(): CoreUniversityMetadata {
  if (cache) return cache;
  try {
    const json = JSON.parse(readFileSync(CORE_FILE, "utf8")) as {
      universityIds?: unknown;
      additions?: unknown;
      flags?: unknown;
    };
    const universityIds = Array.isArray(json.universityIds)
      ? json.universityIds.filter((v): v is string => typeof v === "string")
      : [];
    const tierByUniversityId = new Map<string, CoreReviewTier>(universityIds.map((id) => [id, "core"]));
    const additions = isRecord(json.additions) ? json.additions : {};
    for (const tier of ["must", "if_time", "eng_special", "med_health"] as const) {
      const rows = additions[tier];
      if (!Array.isArray(rows)) continue;
      for (const row of rows) {
        if (isRecord(row) && typeof row.id === "string") tierByUniversityId.set(row.id, tier);
      }
    }
    const flags = isRecord(json.flags) ? json.flags : {};
    const flagByUniversityId = new Map<string, string>();
    for (const [id, flag] of Object.entries(flags)) {
      if (typeof flag === "string") flagByUniversityId.set(id, flag);
    }
    cache = { universityIds, tierByUniversityId, flagByUniversityId };
  } catch {
    cache = { universityIds: [], tierByUniversityId: new Map(), flagByUniversityId: new Map() };
  }
  return cache;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
