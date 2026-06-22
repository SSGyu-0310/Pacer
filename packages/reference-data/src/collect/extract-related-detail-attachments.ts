import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const DEFAULT_YEAR = 2027;
const DEFAULT_RELATED_DETAIL_MANIFEST =
  "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027_related_detail.jsonl";
const DEFAULT_PUBLIC_DIR =
  "packages/reference-data/data/public/university-admission-sites";

const FILE_EXTENSIONS = new Set([
  "pdf",
  "hwp",
  "hwpx",
  "xls",
  "xlsx",
  "doc",
  "docx",
  "ppt",
  "pptx",
  "zip",
]);

type Options = {
  repoRoot: string;
  year: number;
  manifestPath: string;
  publicDir: string;
  limit: number | null;
  includeNonOkHtml: boolean;
  outputSuffix: string;
};

type RelatedDetailManifest = {
  provider: string;
  artifactType: string;
  year: number;
  unvCd: string;
  universityName: string;
  campus: string;
  sourceLinkRole: string;
  sourceLinkText?: string;
  attachmentRole: string;
  linkText: string;
  sourceCandidateUrl: string;
  attachmentUrl?: string;
  finalUrl: string;
  rawPath: string;
  sha256: string;
  bytes: number;
  httpStatus: number | null;
  contentType: string | null;
  fileExtension: string;
  detectedKind?: string;
  status: string;
};

type NestedAttachmentCandidate = {
  provider: "university-admission-office";
  artifactType: "admission_related_detail_attachment_candidate";
  year: number;
  unvCd: string;
  universityName: string;
  campus: string;
  sourceLinkRole: string;
  sourceLinkText: string;
  sourceCandidateUrl: string;
  detailRawPath: string;
  attachmentRole: string;
  linkText: string;
  hrefRaw: string;
  resolvedUrl: string;
  hostname: string;
  fileExtension: string;
  keywordHits: string;
  extractionSource: string;
};

async function main() {
  const rawArgs = process.argv.slice(2);
  if (wantsHelp(rawArgs)) {
    printHelp();
    return;
  }

  const options = withResolvedPaths(parseArgs(rawArgs));
  await mkdir(options.publicDir, { recursive: true });

  let detailRows = (await loadJsonl(options.manifestPath))
    .filter((row) => Number(row.year) === options.year)
    .filter((row) => row.status === "fetched")
    .filter((row) => isHtmlDetailSource(row))
    .filter((row) => options.includeNonOkHtml || isHttpOk(row.httpStatus));

  if (options.limit !== null) {
    detailRows = detailRows.slice(0, options.limit);
  }

  const allCandidates: NestedAttachmentCandidate[] = [];
  const sourceRows = [];

  for (const [index, row] of detailRows.entries()) {
    const rawPath = path.resolve(options.repoRoot, row.rawPath);
    if (!existsSync(rawPath)) {
      sourceRows.push(sourceSummaryRow(row, 0, "missing_raw_file"));
      continue;
    }

    const html = await readFile(rawPath, "utf8");
    const detailUrl = sourceDetailUrl(row);
    const candidates = extractNestedCandidates(html, row, detailUrl);
    allCandidates.push(...candidates);
    sourceRows.push(sourceSummaryRow(row, candidates.length, "extracted"));

    console.log(
      [
        `related detail attachment extraction year=${options.year}`,
        `index=${index + 1}/${detailRows.length}`,
        `unvCd=${row.unvCd}`,
        `http=${row.httpStatus ?? ""}`,
        `candidates=${candidates.length}`,
      ].join(" "),
    );
  }

  const dedupedCandidates = dedupeCandidates(allCandidates);
  const outputSuffixSegment = options.outputSuffix ? `_${options.outputSuffix}` : "";
  const candidatesPath = path.join(
    options.publicDir,
    `university_admission_related_detail_attachment_candidates_${options.year}${outputSuffixSegment}.csv`,
  );
  const sourceManifestPath = path.join(
    options.publicDir,
    `university_admission_related_detail_sources_manifest_${options.year}${outputSuffixSegment}.jsonl`,
  );
  const summaryPath = path.join(
    options.publicDir,
    `university_admission_related_detail_extraction_summary_${options.year}${outputSuffixSegment}.json`,
  );

  await writeCsv(candidatesPath, dedupedCandidates, [
    "provider",
    "artifactType",
    "year",
    "unvCd",
    "universityName",
    "campus",
    "sourceLinkRole",
    "sourceLinkText",
    "sourceCandidateUrl",
    "detailRawPath",
    "attachmentRole",
    "linkText",
    "hrefRaw",
    "resolvedUrl",
    "hostname",
    "fileExtension",
    "keywordHits",
    "extractionSource",
  ]);
  await writeJsonl(sourceManifestPath, sourceRows);

  const summary = {
    provider: "university-admission-office",
    generatedAt: new Date().toISOString(),
    year: options.year,
    outputSuffix: options.outputSuffix || null,
    sourceManifestPath: toRepoRelative(options.manifestPath, options.repoRoot),
    sourceRelatedDetailRows: detailRows.length,
    sourceRowsWithCandidates: sourceRows.filter((row) => row.candidateCount > 0).length,
    nestedAttachmentCandidates: dedupedCandidates.length,
    rawNestedAttachmentCandidates: allCandidates.length,
    bySourceLinkRole: countBy(sourceRows, "sourceLinkRole"),
    bySourceHttpStatus: countBy(
      sourceRows.map((row) => ({ ...row, httpStatus: String(row.httpStatus ?? "") })),
      "httpStatus",
    ),
    byExtractionStatus: countBy(sourceRows, "extractionStatus"),
    byAttachmentRole: countBy(dedupedCandidates, "attachmentRole"),
    byAttachmentFileExtension: countBy(dedupedCandidates, "fileExtension"),
    byExtractionSource: countBy(dedupedCandidates, "extractionSource"),
    notes: [
      "Related-detail HTML is a second-pass crawl target discovered from high-priority admission-office pages.",
      "Nested candidates are still crawl targets, not verified AdmissionRule or HistoricalOutcome records.",
      "JavaScript/onClick/data attribute URLs are extracted heuristically and require fetch validation.",
    ],
  };
  await writeFile(summaryPath, `${JSON.stringify(summary, null, 2)}\n`, "utf8");

  console.log(
    "related detail attachment extraction complete. " +
      `sources=${summary.sourceRelatedDetailRows} ` +
      `candidates=${summary.nestedAttachmentCandidates} ` +
      `output=${toRepoRelative(candidatesPath, options.repoRoot)}`,
  );
}

function extractNestedCandidates(
  html: string,
  source: RelatedDetailManifest,
  detailUrl: string,
) {
  const candidates: NestedAttachmentCandidate[] = [];
  const anchorPattern =
    /<a\b(?<attrs>[\s\S]*?)>(?<label>[\s\S]*?)<\/a>/gi;

  for (const match of html.matchAll(anchorPattern)) {
    const attrs = match.groups?.attrs ?? "";
    const linkText = stripTags(decodeHtml(match.groups?.label ?? ""));
    const candidatesFromAnchor = candidateUrlsFromAttributes(attrs, detailUrl);

    for (const candidateUrl of candidatesFromAnchor) {
      const keywordHits = keywordHitsFor(linkText, candidateUrl.resolvedUrl);
      const attachmentRole = classifyAttachment(
        linkText,
        candidateUrl.resolvedUrl,
        keywordHits,
      );
      if (!attachmentRole) continue;

      candidates.push({
        provider: "university-admission-office",
        artifactType: "admission_related_detail_attachment_candidate",
        year: Number(source.year),
        unvCd: source.unvCd,
        universityName: source.universityName,
        campus: source.campus,
        sourceLinkRole: source.sourceLinkRole,
        sourceLinkText: sourceText(source),
        sourceCandidateUrl: detailUrl,
        detailRawPath: source.rawPath,
        attachmentRole,
        linkText,
        hrefRaw: candidateUrl.raw,
        resolvedUrl: candidateUrl.resolvedUrl,
        hostname: new URL(candidateUrl.resolvedUrl).hostname,
        fileExtension: fileExtensionFor(candidateUrl.resolvedUrl),
        keywordHits: keywordHits.join("|"),
        extractionSource: candidateUrl.source,
      });
    }
  }

  return dedupeCandidates(candidates);
}

function candidateUrlsFromAttributes(attrs: string, detailUrl: string) {
  const candidates: Array<{ raw: string; resolvedUrl: string; source: string }> = [];
  const directAttributes = [
    "href",
    "data-url",
    "data-href",
    "data-file-url",
    "data-download-url",
    "data-link",
  ];

  for (const attrName of directAttributes) {
    const raw = extractAttribute(attrs, attrName);
    addCandidateUrl(candidates, raw, detailUrl, attrName);
  }

  const onclick = extractAttribute(attrs, "onclick");
  if (onclick) {
    for (const raw of extractUrlLikeArguments(onclick)) {
      addCandidateUrl(candidates, raw, detailUrl, "onclick");
    }
  }

  for (const candidate of structuredDownloadUrlsFromAttributes(attrs, onclick)) {
    addCandidateUrl(candidates, candidate.raw, detailUrl, candidate.source);
  }

  return candidates;
}

function structuredDownloadUrlsFromAttributes(attrs: string, onclick: string) {
  const candidates: Array<{ raw: string; source: string }> = [];
  if (!/\bfileDown\s*\(\s*this\s*\)/i.test(onclick)) {
    return candidates;
  }

  const boardSeq = extractAttribute(attrs, "data-boardseq");
  const siteNo = extractAttribute(attrs, "data-siteno");
  const bbsSeq = extractAttribute(attrs, "data-bbsseq");
  const fileSeq = extractAttribute(attrs, "data-fileseq");
  if (boardSeq && siteNo && bbsSeq && fileSeq) {
    const params = new URLSearchParams({
      GBN: "X01",
      BOARD_SEQ: boardSeq,
      SITE_NO: siteNo,
      BBS_SEQ: bbsSeq,
      FILE_SEQ: fileSeq,
    });
    candidates.push({
      raw: `/ajaxfile/FR_SVC/FileDown.do?${params.toString()}`,
      source: "onclick_data_fileDown",
    });
  }

  return candidates;
}

function addCandidateUrl(
  candidates: Array<{ raw: string; resolvedUrl: string; source: string }>,
  raw: string,
  detailUrl: string,
  source: string,
) {
  const cleaned = cleanCandidateUrl(raw);
  if (!cleaned) return;
  if (cleaned.startsWith("#")) return;
  if (/^(mailto|tel):/i.test(cleaned)) return;
  if (/^javascript:\s*$/i.test(cleaned)) return;
  if (/^javascript:/i.test(cleaned)) {
    for (const argument of extractUrlLikeArguments(cleaned)) {
      addCandidateUrl(candidates, argument, detailUrl, source);
    }
    return;
  }

  const resolvedUrl = resolveUrl(cleaned.replace(/^javascript:/i, ""), detailUrl);
  if (!resolvedUrl) return;
  candidates.push({ raw, resolvedUrl, source });
}

function extractUrlLikeArguments(value: string) {
  const values: string[] = [];
  for (const match of value.matchAll(/["'](?<value>[^"']+)["']/g)) {
    const candidate = match.groups?.value ?? "";
    if (isUrlLike(candidate)) values.push(candidate);
  }
  for (const match of value.matchAll(/(?:location\.href|window\.open)\s*=\s*["'](?<value>[^"']+)["']/g)) {
    const candidate = match.groups?.value ?? "";
    if (isUrlLike(candidate)) values.push(candidate);
  }
  return values;
}

function isUrlLike(value: string) {
  const normalized = decodeHtml(value).trim();
  return (
    /^https?:\/\//i.test(normalized) ||
    normalized.startsWith("/") ||
    normalized.startsWith("./") ||
    normalized.startsWith("../") ||
    /[?&](file|atch|attach|download|down|seq|ntt|board|bbs|fileKey|streFileNm|orignlFileNm)=/i.test(normalized) ||
    /\.(pdf|hwp|hwpx|xls|xlsx|doc|docx|ppt|pptx|zip)(?:$|[?#])/i.test(normalized) ||
    /\.(do|jsp|php|asp|aspx|html?|es)(?:$|[?#])/i.test(normalized)
  );
}

function classifyAttachment(
  linkText: string,
  url: string,
  keywordHits: string[],
) {
  const haystack = compact(`${linkText} ${decodeURIComponentSafe(url)}`).toLowerCase();
  const extension = fileExtensionFor(url);
  if (FILE_EXTENSIONS.has(extension)) return "direct_file";
  if (
    haystack.includes("filedown") ||
    haystack.includes("filedownload") ||
    haystack.includes("download") ||
    haystack.includes("downfile") ||
    haystack.includes("downloadfile") ||
    haystack.includes("다운로드") ||
    haystack.includes("첨부") ||
    haystack.includes("파일")
  ) {
    return "file_download_route";
  }
  if (keywordHits.length > 0) return "related_detail";
  return null;
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
    "첨부",
    "다운로드",
    "파일",
  ];
  return keywords.filter((keyword) => haystack.includes(keyword));
}

function sourceSummaryRow(
  row: RelatedDetailManifest,
  candidateCount: number,
  extractionStatus: string,
) {
  return {
    provider: "university-admission-office",
    artifactType: "admission_related_detail_source",
    year: row.year,
    unvCd: row.unvCd,
    universityName: row.universityName,
    campus: row.campus,
    sourceLinkRole: row.sourceLinkRole,
    sourceLinkText: sourceText(row),
    sourceCandidateUrl: sourceDetailUrl(row),
    finalUrl: row.finalUrl,
    rawPath: row.rawPath,
    rawSha256: row.sha256,
    bytes: row.bytes,
    httpStatus: row.httpStatus,
    contentType: row.contentType,
    candidateCount,
    extractionStatus,
    extractedAt: new Date().toISOString(),
  };
}

function isHtmlDetailSource(row: RelatedDetailManifest) {
  if (row.detectedKind === "html") return true;
  if (row.artifactType === "admission_detail_html") return true;
  const extension = (row.fileExtension || "").toLowerCase();
  const contentType = (row.contentType || "").toLowerCase();
  return extension === "html" || extension === "htm" || contentType.includes("text/html");
}

function sourceText(row: RelatedDetailManifest) {
  return row.linkText || row.sourceLinkText || "";
}

function sourceDetailUrl(row: RelatedDetailManifest) {
  return row.finalUrl || row.attachmentUrl || row.sourceCandidateUrl;
}

function isHttpOk(status: number | null) {
  return status !== null && status >= 200 && status < 300;
}

async function loadJsonl(filePath: string) {
  const text = await readFile(filePath, "utf8");
  return text
    .split("\n")
    .filter((line) => line.trim())
    .map((line) => JSON.parse(line)) as RelatedDetailManifest[];
}

function dedupeCandidates(rows: NestedAttachmentCandidate[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = [
      row.year,
      row.unvCd,
      row.sourceCandidateUrl,
      row.attachmentRole,
      row.resolvedUrl,
      row.linkText,
    ].join("|");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function extractAttribute(attrs: string, name: string) {
  const pattern = new RegExp(`${name}\\s*=\\s*(?:"(?<double>[^"]*)"|'(?<single>[^']*)'|(?<bare>[^\\s>]+))`, "i");
  const match = attrs.match(pattern);
  return decodeHtml(match?.groups?.double ?? match?.groups?.single ?? match?.groups?.bare ?? "");
}

function cleanCandidateUrl(value: string) {
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

async function writeJsonl(filePath: string, rows: Record<string, unknown>[]) {
  await writeFile(
    filePath,
    `${rows.map((row) => JSON.stringify(sanitizeJsonlValue(row))).join("\n")}\n`,
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

function sanitizeJsonlValue(value: unknown): unknown {
  if (typeof value === "string") {
    return value.replace(/[\u0000-\u001f\u007f-\u009f]+/g, " ").trim();
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeJsonlValue(item));
  }
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, sanitizeJsonlValue(item)]),
    );
  }
  return value;
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

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: findRepoRoot(process.cwd()),
    year: DEFAULT_YEAR,
    manifestPath: DEFAULT_RELATED_DETAIL_MANIFEST,
    publicDir: DEFAULT_PUBLIC_DIR,
    limit: null,
    includeNonOkHtml: false,
    outputSuffix: "",
  };

  const normalizedArgs = args[0] === "--" ? args.slice(1) : args;
  for (const arg of normalizedArgs) {
    if (arg.startsWith("--year=")) {
      options.year = Number(arg.slice("--year=".length));
    } else if (arg.startsWith("--manifest=")) {
      options.manifestPath = arg.slice("--manifest=".length);
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--limit=")) {
      options.limit = Number(arg.slice("--limit=".length));
    } else if (arg === "--include-non-ok-html") {
      options.includeNonOkHtml = true;
    } else if (arg.startsWith("--output-suffix=")) {
      options.outputSuffix = sanitizeOutputSuffix(arg.slice("--output-suffix=".length));
    }
  }

  return options;
}

function wantsHelp(args: string[]) {
  const normalizedArgs = args[0] === "--" ? args.slice(1) : args;
  return normalizedArgs.includes("--help") || normalizedArgs.includes("-h");
}

function printHelp() {
  console.log(`Usage: tsx src/collect/extract-related-detail-attachments.ts [options]

Options:
  --year=YYYY              Admission year to process. Default: ${DEFAULT_YEAR}
  --manifest=PATH          related_detail fetch manifest JSONL.
  --public-dir=PATH        Public output directory.
  --limit=N                Process only the first N fetched detail rows.
  --include-non-ok-html    Also parse non-2xx HTML responses.
  --output-suffix=VALUE    Append a safe suffix to output filenames.
  -h, --help               Show this help.
`);
}

function sanitizeOutputSuffix(value: string) {
  return value.trim().replace(/[^a-zA-Z0-9_-]/g, "_").replace(/^_+|_+$/g, "");
}

function withResolvedPaths(options: Options): Options {
  const repoRoot = options.repoRoot;
  return {
    ...options,
    manifestPath: path.resolve(repoRoot, options.manifestPath),
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
