import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025, 2026, 2027];
const DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/adiga";
const DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/adiga/extracted";

type Options = {
  repoRoot: string;
  years: number[];
  publicDir: string;
  outputDir: string;
};

type DetailManifest = {
  provider: "adiga";
  artifactType: "university_selection_html";
  year: number;
  unvCd: string;
  universityName: string;
  sourceUrl: string;
  rawPath: string;
  status: "fetched" | "fetch_failed";
};

type UniversityRow = {
  year: string;
  unvCd: string;
  universityName: string;
  campus: string;
  resultCount: string;
  sourceUrl: string;
};

type OfficialSiteCandidate = {
  provider: "adiga";
  artifactType: "adiga_official_site_candidate";
  year: number;
  unvCd: string;
  universityName: string;
  campus: string;
  linkType: "homepage" | "admission_homepage";
  label: string;
  rawUrl: string;
  normalizedUrl: string;
  hostname: string;
  sourceUrl: string;
  rawPath: string;
  confidence: "direct_adiga_university_header";
  status: "parsed_candidate" | "invalid_url";
  extractedAt: string;
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.outputDir, { recursive: true });

  const rows: OfficialSiteCandidate[] = [];
  const yearsSummary: Array<{
    year: number;
    manifests: number;
    fetched: number;
    universitiesWithHomepage: number;
    universitiesWithAdmissionHomepage: number;
    candidates: number;
  }> = [];

  for (const year of options.years) {
    const manifests = await loadManifestYear(options.publicDir, year);
    const campusByUnvCd = await loadCampusByUnvCd(options.publicDir, year);
    const yearRows: OfficialSiteCandidate[] = [];

    for (const manifest of manifests.filter((row) => row.status === "fetched")) {
      const rawAbsolutePath = path.join(options.repoRoot, manifest.rawPath);
      const html = await readFile(rawAbsolutePath, "utf8");
      const campus = campusByUnvCd.get(manifest.unvCd) ?? "";
      yearRows.push(...extractOfficialSiteCandidates(html, manifest, campus));
    }

    rows.push(...yearRows);

    const homepageUnvCds = new Set(
      yearRows.filter((row) => row.linkType === "homepage").map((row) => row.unvCd),
    );
    const admissionHomepageUnvCds = new Set(
      yearRows
        .filter((row) => row.linkType === "admission_homepage")
        .map((row) => row.unvCd),
    );

    yearsSummary.push({
      year,
      manifests: manifests.length,
      fetched: manifests.filter((row) => row.status === "fetched").length,
      universitiesWithHomepage: homepageUnvCds.size,
      universitiesWithAdmissionHomepage: admissionHomepageUnvCds.size,
      candidates: yearRows.length,
    });

    console.log(
      [
        `adiga official sites year=${year}`,
        `candidates=${yearRows.length}`,
        `homepage_universities=${homepageUnvCds.size}`,
        `admission_homepage_universities=${admissionHomepageUnvCds.size}`,
      ].join(" "),
    );
  }

  const dedupedRows = dedupeRows(rows);
  await writeCsv(
    path.join(options.outputDir, "adiga_official_site_candidates.csv"),
    dedupedRows,
    [
      "provider",
      "artifactType",
      "year",
      "unvCd",
      "universityName",
      "campus",
      "linkType",
      "label",
      "rawUrl",
      "normalizedUrl",
      "hostname",
      "sourceUrl",
      "rawPath",
      "confidence",
      "status",
      "extractedAt",
    ],
  );

  const summary = {
    provider: "adiga",
    generatedAt: new Date().toISOString(),
    years: yearsSummary,
    totals: {
      candidates: dedupedRows.length,
      homepageCandidates: dedupedRows.filter((row) => row.linkType === "homepage")
        .length,
      admissionHomepageCandidates: dedupedRows.filter(
        (row) => row.linkType === "admission_homepage",
      ).length,
      invalidUrlCandidates: dedupedRows.filter((row) => row.status === "invalid_url")
        .length,
    },
    notes: [
      "Official site candidates are extracted from Adiga university detail page header links labelled 홈페이지 or 입시홈페이지.",
      "These are source candidates for admission-office crawling, not verified canonical university AdmissionRule sources.",
    ],
  };

  await writeFile(
    path.join(options.outputDir, "adiga_official_site_summary.json"),
    `${JSON.stringify(summary, null, 2)}\n`,
  );
}

function extractOfficialSiteCandidates(
  html: string,
  manifest: DetailManifest,
  campus: string,
): OfficialSiteCandidate[] {
  const candidates: OfficialSiteCandidate[] = [];
  const anchorPattern =
    /<a\b[^>]*onclick=(?<quote>["'])(?<onclick>[\s\S]*?)\k<quote>[^>]*>(?<label>[\s\S]*?)<\/a>/gi;

  for (const match of html.matchAll(anchorPattern)) {
    const onclick = decodeHtml(match.groups?.onclick ?? "");
    if (!onclick.includes("fnOpenNewUrl")) continue;

    const label = stripTags(decodeHtml(match.groups?.label ?? ""));
    const linkType = linkTypeFromLabel(label);
    if (!linkType) continue;

    const rawUrl = extractFnOpenNewUrl(onclick);
    if (!rawUrl) continue;

    const normalized = normalizeUrl(rawUrl);
    candidates.push({
      provider: "adiga",
      artifactType: "adiga_official_site_candidate",
      year: manifest.year,
      unvCd: manifest.unvCd,
      universityName: manifest.universityName,
      campus,
      linkType,
      label,
      rawUrl,
      normalizedUrl: normalized.url,
      hostname: normalized.hostname,
      sourceUrl: manifest.sourceUrl,
      rawPath: manifest.rawPath,
      confidence: "direct_adiga_university_header",
      status: normalized.valid ? "parsed_candidate" : "invalid_url",
      extractedAt: new Date().toISOString(),
    });
  }

  return candidates;
}

function linkTypeFromLabel(label: string): OfficialSiteCandidate["linkType"] | null {
  const normalized = label.replace(/\s+/g, "");
  if (normalized === "홈페이지") return "homepage";
  if (normalized === "입시홈페이지") return "admission_homepage";
  return null;
}

function extractFnOpenNewUrl(onclick: string): string | null {
  const match = onclick.match(/fnOpenNewUrl\(\s*(?<quote>["'])(?<url>.*?)\k<quote>\s*\)/);
  return match?.groups?.url ? cleanUrl(match.groups.url) : null;
}

function cleanUrl(value: string): string {
  return decodeHtml(value).replace(/\\\//g, "/").trim();
}

function normalizeUrl(value: string): { url: string; hostname: string; valid: boolean } {
  let candidate = cleanUrl(value);
  if (candidate.startsWith("//")) {
    candidate = `https:${candidate}`;
  } else if (!/^https?:\/\//i.test(candidate)) {
    candidate = `https://${candidate}`;
  }

  try {
    const url = new URL(candidate);
    return {
      url: url.toString(),
      hostname: url.hostname,
      valid: url.protocol === "http:" || url.protocol === "https:",
    };
  } catch {
    return { url: candidate, hostname: "", valid: false };
  }
}

function dedupeRows(rows: OfficialSiteCandidate[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = [
      row.year,
      row.unvCd,
      row.linkType,
      row.normalizedUrl || row.rawUrl,
    ].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

async function loadManifestYear(publicDir: string, year: number) {
  const manifestPath = path.join(publicDir, `adiga_selection_manifest_${year}.jsonl`);
  if (!existsSync(manifestPath)) return [];

  const text = await readFile(manifestPath, "utf8");
  return text
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as DetailManifest);
}

async function loadCampusByUnvCd(publicDir: string, year: number) {
  const csvPath = path.join(publicDir, `adiga_universities_${year}.csv`);
  const rows = existsSync(csvPath)
    ? parseCsv(await readFile(csvPath, "utf8"))
    : [];
  return new Map(rows.map((row) => [row.unvCd, row.campus]));
}

function parseCsv(text: string): UniversityRow[] {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(Boolean);
  const headers = parseCsvLine(lines[0] ?? "");
  return lines.slice(1).map((line) => {
    const values = parseCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])) as UniversityRow;
  });
}

function parseCsvLine(line: string) {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && inQuotes && next === '"') {
      current += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      values.push(current);
      current = "";
      continue;
    }
    current += char;
  }

  values.push(current);
  return values;
}

function stripTags(value: string) {
  return value.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
}

function decodeHtml(value: string) {
  return value
    .replace(/&quot;/g, '"')
    .replace(/&#34;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

async function writeCsv<T extends Record<string, unknown>>(
  filePath: string,
  rows: T[],
  headers: Array<keyof T & string>,
) {
  const content = [
    headers.join(","),
    ...rows.map((row) =>
      headers.map((header) => csvEscape(row[header] ?? "")).join(","),
    ),
  ].join("\n");

  await writeFile(filePath, `${content}\n`, "utf8");
}

function csvEscape(value: unknown) {
  const text = String(value);
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: findRepoRoot(process.cwd()),
    years: DEFAULT_YEARS,
    publicDir: DEFAULT_PUBLIC_DIR,
    outputDir: DEFAULT_OUTPUT_DIR,
  };

  for (const arg of args) {
    if (arg.startsWith("--years=")) {
      options.years = arg
        .slice("--years=".length)
        .split(",")
        .map((year) => Number(year.trim()))
        .filter((year) => Number.isInteger(year));
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--output-dir=")) {
      options.outputDir = arg.slice("--output-dir=".length);
    }
  }

  return options;
}

function withResolvedPaths(options: Options): Options {
  const repoRoot = options.repoRoot;
  return {
    ...options,
    repoRoot,
    publicDir: path.resolve(repoRoot, options.publicDir),
    outputDir: path.resolve(repoRoot, options.outputDir),
  };
}

function findRepoRoot(start: string): string {
  let current = path.resolve(start);
  while (true) {
    if (existsSync(path.join(current, "pnpm-workspace.yaml"))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      return path.resolve(start);
    }
    current = parent;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
