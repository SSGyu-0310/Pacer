import { readFileSync } from "node:fs";
import path from "node:path";

const REPO_ROOT = process.cwd().replace(/\/apps\/web$/, "");
const CORE_FILE = path.resolve(REPO_ROOT, "packages/reference-data/data/review/core-universities.json");

let cache: string[] | null = null;

/** 핵심대 프리셋의 universityId 목록. 비어 있으면 큐를 전체로 둔다. */
export function getCoreUniversityIds(): string[] {
  if (cache) return cache;
  try {
    const json = JSON.parse(readFileSync(CORE_FILE, "utf8")) as { universityIds?: unknown };
    cache = Array.isArray(json.universityIds) ? json.universityIds.filter((v): v is string => typeof v === "string") : [];
  } catch {
    cache = [];
  }
  return cache;
}
