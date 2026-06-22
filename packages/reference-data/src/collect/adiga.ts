import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE_URL = "https://www.adiga.kr";
const MENU_ID = "PCUVTINF2000";
const DEFAULT_YEARS = [2023, 2024, 2025, 2026, 2027];
const DEFAULT_RAW_DIR = ".reference-data/raw/adiga";
const DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/adiga";
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+manual admin-curated use; public pages only)";

type Options = {
  repoRoot: string;
  years: number[];
  limit: number | null;
  unvCds: Set<string> | null;
  rawDir: string;
  publicDir: string;
  delayMs: number;
  downloadImages: boolean;
  details: boolean;
};

type UniversityRow = {
  year: number;
  unvCd: string;
  universityName: string;
  campus: string | null;
  resultCount: number | null;
  sourceUrl: string;
};

type DetailManifest = {
  provider: "adiga";
  artifactType: "university_selection_html";
  year: number;
  unvCd: string;
  universityName: string;
  sourceUrl: string;
  fetchedAt: string;
  rawPath: string;
  sha256: string;
  bytes: number;
  imageUrls: string[];
  downloadedImages: string[];
  failedImageUrls: string[];
  indicators: {
    hasCsatTrack: boolean;
    finalRegistrantMentions: number;
    percentileMentions: number;
    convertedScoreMentions: number;
  };
  status: "fetched" | "fetch_failed";
  error?: string;
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  const allManifests: DetailManifest[] = [];

  for (const year of options.years) {
    const listUrl = universityListUrl(year);
    const listHtml = await fetchText(listUrl);
    const listDir = path.join(options.rawDir, String(year));
    await mkdir(listDir, { recursive: true });
    await writeFile(path.join(listDir, "univView.html"), listHtml);

    let universities = parseUniversityList(listHtml, year, listUrl);
    if (options.unvCds) {
      universities = universities.filter((row) => options.unvCds?.has(row.unvCd));
    }
    if (options.limit !== null) {
      universities = universities.slice(0, options.limit);
    }

    const universityCsvPath = path.join(
      options.publicDir,
      `adiga_universities_${year}.csv`,
    );
    await writeCsv(universityCsvPath, universities, [
      "year",
      "unvCd",
      "universityName",
      "campus",
      "resultCount",
      "sourceUrl",
    ]);

    console.log(
      `adiga universities year=${year} count=${universities.length} source=${listUrl}`,
    );

    if (!options.details) continue;

    const manifests: DetailManifest[] = [];
    for (const [index, university] of universities.entries()) {
      const manifest = await collectDetail(university, options);
      manifests.push(manifest);
      allManifests.push(manifest);

      console.log(
        [
          `adiga detail year=${year}`,
          `index=${index + 1}/${universities.length}`,
          `unvCd=${university.unvCd}`,
          `status=${manifest.status}`,
          `bytes=${manifest.bytes}`,
          `images=${manifest.imageUrls.length}`,
        ].join(" "),
      );

      if (options.delayMs > 0 && index < universities.length - 1) {
        await sleep(options.delayMs);
      }
    }

    const manifestPath = path.join(
      options.publicDir,
      `adiga_selection_manifest_${year}.jsonl`,
    );
    await writeJsonl(manifestPath, manifests);
  }

  const summaryManifests = await readExistingManifests(options.publicDir);
  if (summaryManifests.length > 0) {
    const summary = summarize(summaryManifests);
    await writeFile(
      path.join(options.publicDir, "adiga_collection_summary.json"),
      `${JSON.stringify(summary, null, 2)}\n`,
    );
  }
}

async function collectDetail(
  university: UniversityRow,
  options: Options,
): Promise<DetailManifest> {
  const sourceUrl = selectionUrl(university.year, university.unvCd);
  const fetchedAt = new Date().toISOString();
  const yearDir = path.join(options.rawDir, String(university.year), university.unvCd);
  await mkdir(yearDir, { recursive: true });
  const rawPath = path.join(yearDir, "selection.html");

  try {
    const html = await fetchText(sourceUrl);
    await writeFile(rawPath, html);

    const imageUrls = extractImageUrls(html);
    const imageDownloadResult = options.downloadImages
      ? await downloadImages(imageUrls, yearDir)
      : { downloadedImages: [], failedImageUrls: [] };

    return {
      provider: "adiga",
      artifactType: "university_selection_html",
      year: university.year,
      unvCd: university.unvCd,
      universityName: university.universityName,
      sourceUrl,
      fetchedAt,
      rawPath: toRepoRelative(rawPath, options.repoRoot),
      sha256: sha256(html),
      bytes: Buffer.byteLength(html),
      imageUrls,
      downloadedImages: imageDownloadResult.downloadedImages.map((imagePath) =>
        toRepoRelative(imagePath, options.repoRoot),
      ),
      failedImageUrls: imageDownloadResult.failedImageUrls,
      indicators: {
        hasCsatTrack: html.includes("수능위주전형"),
        finalRegistrantMentions: countMatches(html, /최종등록자/g),
        percentileMentions: countMatches(html, /백분위/g),
        convertedScoreMentions: countMatches(html, /대학별\s*환산/g),
      },
      status: "fetched",
    };
  } catch (error) {
    return {
      provider: "adiga",
      artifactType: "university_selection_html",
      year: university.year,
      unvCd: university.unvCd,
      universityName: university.universityName,
      sourceUrl,
      fetchedAt,
      rawPath: toRepoRelative(rawPath, options.repoRoot),
      sha256: "",
      bytes: 0,
      imageUrls: [],
      downloadedImages: [],
      failedImageUrls: [],
      indicators: {
        hasCsatTrack: false,
        finalRegistrantMentions: 0,
        percentileMentions: 0,
        convertedScoreMentions: 0,
      },
      status: "fetch_failed",
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function parseUniversityList(
  html: string,
  year: number,
  sourceUrl: string,
): UniversityRow[] {
  const rows: UniversityRow[] = [];
  const pattern =
    /<input[^>]*class="[^"]*\bunivGroupInput\b[^"]*"[^>]*value="(?<unvCd>\d+)"[^>]*>\s*<label[^>]*>(?<label>[\s\S]*?)<\/label>/g;

  for (const match of html.matchAll(pattern)) {
    const unvCd = match.groups?.unvCd;
    const label = match.groups?.label;
    if (!unvCd || !label) continue;

    const normalized = stripTags(label).replace(/\s+/g, " ").trim();
    const resultCountMatch = normalized.match(/(?<count>\d+)건$/);
    const withoutCount = normalized.replace(/\s*\d+건$/, "").trim();
    const campusMatch = withoutCount.match(/^(?<name>.+?)\[(?<campus>.+)]$/);

    rows.push({
      year,
      unvCd,
      universityName: campusMatch?.groups?.name?.trim() ?? withoutCount,
      campus: campusMatch?.groups?.campus?.trim() ?? null,
      resultCount: resultCountMatch?.groups?.count
        ? Number(resultCountMatch.groups.count)
        : null,
      sourceUrl,
    });
  }

  return rows;
}

function extractImageUrls(html: string): string[] {
  const urls = new Set<string>();
  const pattern = /<img\b[^>]*\bsrc="(?<url>[^"]+)"/g;
  for (const match of html.matchAll(pattern)) {
    const url = match.groups?.url;
    if (!url) continue;
    const decoded = decodeHtmlEntities(url);
    if (decoded.startsWith("/static/")) continue;
    urls.add(toAbsoluteUrl(decoded));
  }
  return [...urls].sort();
}

async function downloadImages(
  urls: string[],
  yearDir: string,
): Promise<{ downloadedImages: string[]; failedImageUrls: string[] }> {
  const imageDir = path.join(yearDir, "images");
  await mkdir(imageDir, { recursive: true });
  const downloadedImages: string[] = [];
  const failedImageUrls: string[] = [];

  for (const url of urls) {
    const parsed = new URL(url);
    const fileId = parsed.searchParams.get("fileId") ?? sha256(url).slice(0, 16);
    const fileSn = parsed.searchParams.get("fileSn") ?? "0";
    const filename = `${fileId}_${fileSn}.bin`;
    const outputPath = path.join(imageDir, filename);
    try {
      const response = await fetch(url, {
        headers: { "User-Agent": USER_AGENT },
      });
      if (!response.ok) {
        failedImageUrls.push(url);
        continue;
      }
      const buffer = Buffer.from(await response.arrayBuffer());
      await writeFile(outputPath, buffer);
      downloadedImages.push(outputPath);
    } catch {
      failedImageUrls.push(url);
    }
  }

  return { downloadedImages, failedImageUrls };
}

async function fetchText(url: string): Promise<string> {
  const response = await fetch(url, {
    headers: { "User-Agent": USER_AGENT },
  });
  if (!response.ok) {
    throw new Error(`fetch failed ${response.status} ${url}`);
  }
  return response.text();
}

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: process.cwd(),
    years: DEFAULT_YEARS,
    limit: null,
    unvCds: null,
    rawDir: DEFAULT_RAW_DIR,
    publicDir: DEFAULT_PUBLIC_DIR,
    delayMs: 500,
    downloadImages: false,
    details: true,
  };

  for (const arg of args) {
    if (arg === "--") continue;

    if (arg.startsWith("--years=")) {
      options.years = parseNumberList(arg.slice("--years=".length));
    } else if (arg.startsWith("--limit=")) {
      options.limit = Number(arg.slice("--limit=".length));
    } else if (arg.startsWith("--unv-cds=")) {
      options.unvCds = new Set(parseStringList(arg.slice("--unv-cds=".length)));
    } else if (arg.startsWith("--raw-dir=")) {
      options.rawDir = arg.slice("--raw-dir=".length);
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--delay-ms=")) {
      options.delayMs = Number(arg.slice("--delay-ms=".length));
    } else if (arg === "--download-images") {
      options.downloadImages = true;
    } else if (arg === "--no-details") {
      options.details = false;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  return options;
}

function withResolvedPaths(options: Options): Options {
  const repoRoot = findRepoRoot(process.env.INIT_CWD ?? process.cwd());
  return {
    ...options,
    repoRoot,
    rawDir: resolveFromRoot(repoRoot, options.rawDir),
    publicDir: resolveFromRoot(repoRoot, options.publicDir),
  };
}

function resolveFromRoot(repoRoot: string, value: string): string {
  return path.isAbsolute(value) ? value : path.join(repoRoot, value);
}

function toRepoRelative(filePath: string, repoRoot: string): string {
  return path.relative(repoRoot, filePath);
}

function findRepoRoot(startDir: string): string {
  let current = path.resolve(startDir);
  while (true) {
    if (existsSync(path.join(current, "pnpm-workspace.yaml"))) return current;

    const parent = path.dirname(current);
    if (parent === current) return path.resolve(startDir);
    current = parent;
  }
}

function parseNumberList(value: string): number[] {
  return parseStringList(value).map((item) => Number(item));
}

function parseStringList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function universityListUrl(year: number): string {
  return `${BASE_URL}/ucp/uvt/uni/univView.do?menuId=${MENU_ID}&searchSyr=${year}`;
}

function selectionUrl(year: number, unvCd: string): string {
  return `${BASE_URL}/ucp/uvt/uni/univDetailSelection.do?menuId=${MENU_ID}&searchSyr=${year}&unvCd=${unvCd}`;
}

function toAbsoluteUrl(url: string): string {
  return url.startsWith("http") ? url : `${BASE_URL}${url}`;
}

function stripTags(value: string): string {
  return decodeHtmlEntities(value.replace(/<[^>]+>/g, " "));
}

function decodeHtmlEntities(value: string): string {
  return value
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&nbsp;", " ");
}

function countMatches(value: string, pattern: RegExp): number {
  return [...value.matchAll(pattern)].length;
}

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

async function writeCsv<T extends Record<string, unknown>>(
  filePath: string,
  rows: T[],
  headers: (keyof T)[],
) {
  const output = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvCell(row[header])).join(",")),
  ].join("\n");
  await writeFile(filePath, `${output}\n`);
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

async function writeJsonl(filePath: string, rows: DetailManifest[]) {
  await writeFile(filePath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

async function readExistingManifests(publicDir: string): Promise<DetailManifest[]> {
  const files = await readdir(publicDir);
  const manifestFiles = files
    .filter((file) => /^adiga_selection_manifest_\d{4}\.jsonl$/.test(file))
    .sort();
  const manifests: DetailManifest[] = [];

  for (const file of manifestFiles) {
    const content = await readFile(path.join(publicDir, file), "utf8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (trimmed.length === 0) continue;
      manifests.push(JSON.parse(trimmed) as DetailManifest);
    }
  }

  return manifests;
}

function summarize(manifests: DetailManifest[]) {
  const byYear = new Map<number, DetailManifest[]>();
  for (const manifest of manifests) {
    const current = byYear.get(manifest.year) ?? [];
    current.push(manifest);
    byYear.set(manifest.year, current);
  }

  return {
    provider: "adiga",
    generatedAt: new Date().toISOString(),
    years: [...byYear.entries()]
      .sort(([a], [b]) => a - b)
      .map(([year, rows]) => ({
        year,
        artifacts: rows.length,
        fetched: rows.filter((row) => row.status === "fetched").length,
        fetchFailed: rows.filter((row) => row.status === "fetch_failed").length,
        bytes: rows.reduce((sum, row) => sum + row.bytes, 0),
        withCsatTrack: rows.filter((row) => row.indicators.hasCsatTrack).length,
        imageUrls: rows.reduce((sum, row) => sum + row.imageUrls.length, 0),
      })),
  };
}

async function sleep(ms: number) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
