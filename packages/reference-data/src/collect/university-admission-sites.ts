import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const DEFAULT_YEAR = 2027;
const DEFAULT_INVENTORY =
  "packages/reference-data/data/public/adiga/extracted/adiga_official_site_candidates.csv";
const DEFAULT_RAW_DIR = ".reference-data/raw/university-admission-sites";
const DEFAULT_PUBLIC_DIR =
  "packages/reference-data/data/public/university-admission-sites";
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+manual admin-curated use; public admission office pages only)";
const execFileAsync = promisify(execFile);
const EXCLUDED_EXTERNAL_HELPER_HOST_HINTS = [
  "jinhak",
  "jinhakapply",
  "uway",
  "uwayapply",
  "telegr",
  "01consulting",
  "nesin",
  "go3.co.kr",
];

type Options = {
  repoRoot: string;
  year: number;
  inventoryPath: string;
  rawDir: string;
  publicDir: string;
  limit: number | null;
  unvCds: Set<string> | null;
  delayMs: number;
  timeoutMs: number;
  outputSuffix: string | null;
  userAgent: string;
  fallbackCurl: boolean;
};

type SiteInventoryRow = {
  provider: string;
  artifactType: string;
  year: string;
  unvCd: string;
  universityName: string;
  campus: string;
  linkType: string;
  label: string;
  rawUrl: string;
  normalizedUrl: string;
  hostname: string;
  sourceUrl: string;
  rawPath: string;
  confidence: string;
  status: string;
  extractedAt: string;
};

type HomepageManifest = {
  provider: "university-admission-office";
  artifactType: "admission_homepage_html";
  year: number;
  unvCd: string;
  universityName: string;
  campus: string;
  sourceHomepageUrl: string;
  finalHomepageUrl: string;
  sourceInventoryUrl: string;
  fetchedAt: string;
  rawPath: string;
  sha256: string;
  bytes: number;
  httpStatus: number | null;
  contentType: string | null;
  linkCandidateCount: number;
  status: "fetched" | "fetch_failed";
  fetchBackend?: "node_fetch" | "curl";
  error?: string;
};

type LinkCandidate = {
  provider: "university-admission-office";
  artifactType: "admission_site_link_candidate";
  year: number;
  unvCd: string;
  universityName: string;
  campus: string;
  sourceHomepageUrl: string;
  finalHomepageUrl: string;
  rawPath: string;
  linkRole: LinkRole;
  linkText: string;
  hrefRaw: string;
  resolvedUrl: string;
  hostname: string;
  fileExtension: string;
  keywordHits: string;
};

type LinkRole =
  | "regular_admission_guide"
  | "admission_result"
  | "competition_rate"
  | "recruitment_notice"
  | "admission_related";

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  let sites = (await loadInventory(options.inventoryPath))
    .filter((row) => Number(row.year) === options.year)
    .filter((row) => row.linkType === "admission_homepage")
    .filter((row) => row.status === "parsed_candidate")
    .filter((row) => !options.unvCds || options.unvCds.has(row.unvCd));

  sites = dedupeInventoryRows(sites);
  if (options.limit !== null) {
    sites = sites.slice(0, options.limit);
  }

  const manifests: HomepageManifest[] = [];
  const allLinks: LinkCandidate[] = [];

  for (const [index, site] of sites.entries()) {
    const result = await collectHomepage(site, options);
    manifests.push(result.manifest);
    allLinks.push(...result.links);

    console.log(
      [
        `university admission site year=${options.year}`,
        `index=${index + 1}/${sites.length}`,
        `unvCd=${site.unvCd}`,
        `status=${result.manifest.status}`,
        `http=${result.manifest.httpStatus ?? ""}`,
        `bytes=${result.manifest.bytes}`,
        `links=${result.links.length}`,
      ].join(" "),
    );

    if (options.delayMs > 0 && index < sites.length - 1) {
      await sleep(options.delayMs);
    }
  }

  const outputSuffixSegment = outputSuffixPart(options);
  const manifestPath = path.join(
    options.publicDir,
    `university_admission_homepage_manifest_${options.year}${outputSuffixSegment}.jsonl`,
  );
  const linksPath = path.join(
    options.publicDir,
    `university_admission_link_candidates_${options.year}${outputSuffixSegment}.csv`,
  );
  const summaryPath = path.join(
    options.publicDir,
    options.outputSuffix
      ? `university_admission_sites_summary_${options.outputSuffix}.json`
      : "university_admission_sites_summary.json",
  );
  const yearSummaryPath = path.join(
    options.publicDir,
    `university_admission_sites_summary_${options.year}${outputSuffixSegment}.json`,
  );

  await writeJsonl(manifestPath, manifests);
  await writeCsv(linksPath, dedupeLinkCandidates(allLinks), [
    "provider",
    "artifactType",
    "year",
    "unvCd",
    "universityName",
    "campus",
    "sourceHomepageUrl",
    "finalHomepageUrl",
    "rawPath",
    "linkRole",
    "linkText",
    "hrefRaw",
    "resolvedUrl",
    "hostname",
    "fileExtension",
    "keywordHits",
  ]);

  const summary = {
    provider: "university-admission-office",
    generatedAt: new Date().toISOString(),
    year: options.year,
    attempted: sites.length,
    fetched: manifests.filter((row) => row.status === "fetched").length,
    failed: manifests.filter((row) => row.status === "fetch_failed").length,
    linkCandidates: dedupeLinkCandidates(allLinks).length,
    byLinkRole: countBy(dedupeLinkCandidates(allLinks), "linkRole"),
    byFileExtension: countBy(dedupeLinkCandidates(allLinks), "fileExtension"),
    outputSuffix: options.outputSuffix,
    notes: [
      "Homepage HTML is fetched from Adiga 입시홈페이지 URL candidates.",
      "Link candidates are keyword-filtered hints for subsequent official PDF/HWP/XLSX crawling and are not verified AdmissionRule records.",
    ],
  };

  const summaryJson = `${JSON.stringify(summary, null, 2)}\n`;
  await writeFile(summaryPath, summaryJson, "utf8");
  await writeFile(yearSummaryPath, summaryJson, "utf8");
}

async function collectHomepage(site: SiteInventoryRow, options: Options) {
  const fetchedAt = new Date().toISOString();
  const yearDir = path.join(options.rawDir, String(options.year), site.unvCd);
  await mkdir(yearDir, { recursive: true });
  const rawPath = path.join(
    yearDir,
    options.outputSuffix
      ? `admission-homepage-${options.outputSuffix}.html`
      : "admission-homepage.html",
  );

  try {
    const response = await fetchHomepage(site.normalizedUrl, options);
    const body = response.body;
    await writeFile(rawPath, body, "utf8");

    const repoRelativeRawPath = toRepoRelative(rawPath, options.repoRoot);
    const finalHomepageUrl = response.finalUrl || site.normalizedUrl;
    const links = extractLinkCandidates(body, site, finalHomepageUrl, repoRelativeRawPath);

    return {
      manifest: {
        provider: "university-admission-office",
        artifactType: "admission_homepage_html",
        year: options.year,
        unvCd: site.unvCd,
        universityName: site.universityName,
        campus: site.campus,
        sourceHomepageUrl: site.normalizedUrl,
        finalHomepageUrl,
        sourceInventoryUrl: site.sourceUrl,
        fetchedAt,
        rawPath: repoRelativeRawPath,
        sha256: sha256(body),
        bytes: Buffer.byteLength(body),
        httpStatus: response.httpStatus,
        contentType: response.contentType,
        linkCandidateCount: links.length,
        status: "fetched",
        fetchBackend: response.backend,
      } satisfies HomepageManifest,
      links,
    };
  } catch (error) {
    return {
      manifest: {
        provider: "university-admission-office",
        artifactType: "admission_homepage_html",
        year: options.year,
        unvCd: site.unvCd,
        universityName: site.universityName,
        campus: site.campus,
        sourceHomepageUrl: site.normalizedUrl,
        finalHomepageUrl: "",
        sourceInventoryUrl: site.sourceUrl,
        fetchedAt,
        rawPath: toRepoRelative(rawPath, options.repoRoot),
        sha256: "",
        bytes: 0,
        httpStatus: null,
        contentType: null,
        linkCandidateCount: 0,
        status: "fetch_failed",
        error: errorMessage(error),
      } satisfies HomepageManifest,
      links: [] as LinkCandidate[],
    };
  }
}

function errorMessage(error: unknown) {
  if (!(error instanceof Error)) return String(error);
  const cause = (error as Error & { cause?: unknown }).cause;
  if (!cause) return error.message;
  if (cause instanceof Error) return `${error.message}: ${cause.message}`;
  return `${error.message}: ${String(cause)}`;
}

function extractLinkCandidates(
  html: string,
  site: SiteInventoryRow,
  finalHomepageUrl: string,
  rawPath: string,
) {
  const links: LinkCandidate[] = [];
  const anchorPattern =
    /<a\b(?<attrs>[\s\S]*?)>(?<label>[\s\S]*?)<\/a>/gi;

  for (const match of html.matchAll(anchorPattern)) {
    const attrs = match.groups?.attrs ?? "";
    const hrefRaw = extractAttribute(attrs, "href");
    if (!hrefRaw || hrefRaw.startsWith("#") || hrefRaw.toLowerCase().startsWith("javascript:")) {
      continue;
    }

    const resolvedUrl = resolveUrl(cleanHref(hrefRaw), finalHomepageUrl);
    if (!resolvedUrl) continue;
    if (isExcludedExternalHelperLinkUrl(resolvedUrl)) continue;

    const linkText = stripTags(decodeHtml(match.groups?.label ?? ""));
    const keywordHits = keywordHitsFor(linkText, resolvedUrl);
    const fileExtension = fileExtensionFor(resolvedUrl);
    const linkRole = classifyLink(linkText, resolvedUrl, keywordHits);
    if (!linkRole) continue;

    const hostname = new URL(resolvedUrl).hostname;
    links.push({
      provider: "university-admission-office",
      artifactType: "admission_site_link_candidate",
      year: Number(site.year),
      unvCd: site.unvCd,
      universityName: site.universityName,
      campus: site.campus,
      sourceHomepageUrl: site.normalizedUrl,
      finalHomepageUrl,
      rawPath,
      linkRole,
      linkText,
      hrefRaw,
      resolvedUrl,
      hostname,
      fileExtension,
      keywordHits: keywordHits.join("|"),
    });
  }

  return dedupeLinkCandidates(links);
}

function classifyLink(
  linkText: string,
  url: string,
  keywordHits: string[],
): LinkRole | null {
  const haystack = compact(`${linkText} ${decodeURIComponentSafe(url)}`);
  if (keywordHits.length === 0) return null;
  if (haystack.includes("입시결과") || haystack.includes("입학결과") || haystack.includes("전형결과")) {
    return "admission_result";
  }
  if (haystack.includes("경쟁률")) {
    return "competition_rate";
  }
  if (haystack.includes("정시") && (haystack.includes("모집요강") || haystack.includes("전형요강") || haystack.includes("요강"))) {
    return "regular_admission_guide";
  }
  if (haystack.includes("모집요강") || haystack.includes("전형요강")) {
    return "recruitment_notice";
  }
  return "admission_related";
}

function isExcludedExternalHelperLinkUrl(url: string) {
  try {
    const hostname = new URL(url).hostname.toLowerCase();
    return EXCLUDED_EXTERNAL_HELPER_HOST_HINTS.some((hint) => hostname.includes(hint));
  } catch {
    return false;
  }
}

function keywordHitsFor(linkText: string, url: string) {
  const haystack = compact(`${linkText} ${decodeURIComponentSafe(url)}`);
  const keywords = [
    "정시",
    "모집요강",
    "전형요강",
    "입시결과",
    "입학결과",
    "전형결과",
    "경쟁률",
    "충원",
    "합격",
    "수능",
    "대학입학",
    "입학",
  ];
  return keywords.filter((keyword) => haystack.includes(keyword));
}

function extractAttribute(attrs: string, name: string) {
  const pattern = new RegExp(`${name}\\s*=\\s*(?:"(?<double>[^"]*)"|'(?<single>[^']*)'|(?<bare>[^\\s>]+))`, "i");
  const match = attrs.match(pattern);
  return decodeHtml(match?.groups?.double ?? match?.groups?.single ?? match?.groups?.bare ?? "");
}

function cleanHref(value: string) {
  return decodeHtml(value).replace(/\\\//g, "/").trim();
}

function resolveUrl(href: string, baseUrl: string) {
  try {
    const url = new URL(href, baseUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.toString();
  } catch {
    return null;
  }
}

function fileExtensionFor(url: string) {
  try {
    const pathname = new URL(url).pathname.toLowerCase();
    const match = pathname.match(/\.([a-z0-9]+)(?:$|[;/?#])/);
    return match?.[1] ?? "";
  } catch {
    return "";
  }
}

async function fetchWithTimeout(url: string, timeoutMs: number, userAgent: string) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      headers: {
        "User-Agent": userAgent,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchHomepage(url: string, options: Options) {
  try {
    const response = await fetchWithTimeout(url, options.timeoutMs, options.userAgent);
    const body = await decodedResponseText(response);
    return {
      body,
      finalUrl: response.url || url,
      httpStatus: response.status,
      contentType: response.headers.get("content-type"),
      backend: "node_fetch" as const,
    };
  } catch (fetchError) {
    if (!options.fallbackCurl) throw fetchError;
    try {
      return await fetchHomepageWithCurl(url, options);
    } catch (curlError) {
      throw new Error(
        `${errorMessage(fetchError)}; curl fallback failed: ${errorMessage(curlError)}`,
      );
    }
  }
}

async function decodedResponseText(response: Response) {
  const buffer = Buffer.from(await response.arrayBuffer());
  const contentType = response.headers.get("content-type") ?? "";
  const charset = charsetForResponse(buffer, contentType);
  return new TextDecoder(charset, { fatal: false }).decode(buffer);
}

function charsetForResponse(buffer: Buffer, contentType: string) {
  const headerMatch = contentType.match(/charset=([^;\s]+)/i);
  const headerCharset = normalizeCharset(headerMatch?.[1] ?? "");
  if (headerCharset) return headerCharset;

  const asciiHead = buffer.subarray(0, 4096).toString("latin1");
  const metaMatch =
    asciiHead.match(/<meta[^>]+charset=["']?\s*([^"'\s/>]+)/i) ??
    asciiHead.match(/<meta[^>]+content=["'][^"']*charset=([^"'\s;]+)/i);
  return normalizeCharset(metaMatch?.[1] ?? "") || "utf-8";
}

function normalizeCharset(value: string) {
  const normalized = value.trim().toLowerCase().replace(/^["']|["']$/g, "");
  if (!normalized) return "";
  if (["euc-kr", "ks_c_5601-1987", "ks_c_5601", "cp949", "ms949"].includes(normalized)) {
    return "euc-kr";
  }
  if (["utf8", "utf-8"].includes(normalized)) return "utf-8";
  return normalized;
}

async function fetchHomepageWithCurl(url: string, options: Options) {
  const marker = "\n__PACER_CURL_META__";
  const maxTimeSeconds = Math.max(1, Math.ceil(options.timeoutMs / 1000));
  const { stdout } = await execFileAsync(
    "curl",
    [
      "-L",
      "-sS",
      "--max-time",
      String(maxTimeSeconds),
      "-A",
      options.userAgent,
      "-w",
      `${marker}%{http_code}\t%{url_effective}\t%{content_type}`,
      url,
    ],
    {
      encoding: "utf8",
      maxBuffer: 20 * 1024 * 1024,
    },
  );
  const markerIndex = stdout.lastIndexOf(marker);
  if (markerIndex < 0) {
    throw new Error("curl fallback did not return metadata");
  }
  const body = stdout.slice(0, markerIndex);
  const meta = stdout.slice(markerIndex + marker.length);
  const [statusText = "", finalUrl = url, contentType = ""] = meta.split("\t");
  return {
    body,
    finalUrl: finalUrl || url,
    httpStatus: Number(statusText) || null,
    contentType: contentType || null,
    backend: "curl" as const,
  };
}

async function loadInventory(inventoryPath: string) {
  return parseCsv(await readFile(inventoryPath, "utf8")) as SiteInventoryRow[];
}

function dedupeInventoryRows(rows: SiteInventoryRow[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.year}|${row.unvCd}|${row.normalizedUrl}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function dedupeLinkCandidates(rows: LinkCandidate[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.year}|${row.unvCd}|${row.resolvedUrl}|${row.linkText}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function parseCsv(text: string) {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(Boolean);
  const headers = parseCsvLine(lines[0] ?? "");
  return lines.slice(1).map((line) => {
    const values = parseCsvLine(line);
    return Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]));
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

async function writeJsonl(filePath: string, rows: Record<string, unknown>[]) {
  await writeFile(
    filePath,
    `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`,
    "utf8",
  );
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

function countBy<T extends Record<string, unknown>>(rows: T[], key: keyof T) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const value = String(row[key] ?? "");
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, count }));
}

function sha256(value: string) {
  return createHash("sha256").update(value).digest("hex");
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

function decodeURIComponentSafe(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function compact(value: string) {
  return value.replace(/\s+/g, "");
}

function toRepoRelative(filePath: string, repoRoot: string) {
  return path.relative(repoRoot, filePath);
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: findRepoRoot(process.cwd()),
    year: DEFAULT_YEAR,
    inventoryPath: DEFAULT_INVENTORY,
    rawDir: DEFAULT_RAW_DIR,
    publicDir: DEFAULT_PUBLIC_DIR,
    limit: null,
    unvCds: null,
    delayMs: 150,
    timeoutMs: 12000,
    outputSuffix: null,
    userAgent: USER_AGENT,
    fallbackCurl: false,
  };

  for (const arg of args) {
    if (arg.startsWith("--year=")) {
      options.year = Number(arg.slice("--year=".length));
    } else if (arg.startsWith("--inventory=")) {
      options.inventoryPath = arg.slice("--inventory=".length);
    } else if (arg.startsWith("--raw-dir=")) {
      options.rawDir = arg.slice("--raw-dir=".length);
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--limit=")) {
      options.limit = Number(arg.slice("--limit=".length));
    } else if (arg.startsWith("--unv-cds=")) {
      options.unvCds = new Set(
        arg
          .slice("--unv-cds=".length)
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
      );
    } else if (arg.startsWith("--delay-ms=")) {
      options.delayMs = Number(arg.slice("--delay-ms=".length));
    } else if (arg.startsWith("--timeout-ms=")) {
      options.timeoutMs = Number(arg.slice("--timeout-ms=".length));
    } else if (arg.startsWith("--output-suffix=")) {
      options.outputSuffix = sanitizeOutputSuffix(arg.slice("--output-suffix=".length));
    } else if (arg.startsWith("--user-agent=")) {
      options.userAgent = arg.slice("--user-agent=".length);
    } else if (arg === "--fallback-curl") {
      options.fallbackCurl = true;
    }
  }

  return options;
}

function outputSuffixPart(options: Options) {
  return options.outputSuffix ? `_${options.outputSuffix}` : "";
}

function sanitizeOutputSuffix(value: string) {
  const normalized = value.trim().replace(/[^a-zA-Z0-9_-]+/g, "_").replace(/^_+|_+$/g, "");
  if (!normalized) {
    throw new Error("output suffix must contain at least one alphanumeric, dash, or underscore character");
  }
  return normalized;
}

function withResolvedPaths(options: Options): Options {
  const repoRoot = options.repoRoot;
  return {
    ...options,
    inventoryPath: path.resolve(repoRoot, options.inventoryPath),
    rawDir: path.resolve(repoRoot, options.rawDir),
    publicDir: path.resolve(repoRoot, options.publicDir),
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

main()
  .then(() => {
    process.exit(0);
  })
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
