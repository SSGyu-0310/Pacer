import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const DEFAULT_YEAR = 2027;
const DEFAULT_ATTACHMENT_CANDIDATES =
  "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_candidates_2027.csv";
const DEFAULT_RAW_DIR = ".reference-data/raw/university-admission-sites";
const DEFAULT_PUBLIC_DIR =
  "packages/reference-data/data/public/university-admission-sites";
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+manual admin-curated use; public admission office attachments only)";
const execFileAsync = promisify(execFile);
const DEFAULT_EXCLUDED_ATTACHMENT_HOSTS = new Set([
  "adobe.com",
  "get.adobe.com",
  "www.adobe.com",
  "cosmosfarm.com",
  "hancom.com",
  "help.hancom.com",
  "www.hancom.com",
  "microsoft.com",
  "support.microsoft.com",
  "windows.microsoft.com",
  "www.microsoft.com",
  "wordpress.org",
  "www.cosmosfarm.com",
  "www.wordpress.org",
]);

const DEFAULT_EXCLUDED_SOURCE_HOSTS = new Set([
  "cosmosfarm.com",
  "wordpress.org",
  "www.cosmosfarm.com",
  "www.wordpress.org",
]);

const DEFAULT_EXCLUDED_EXTERNAL_HELPER_HOST_HINTS = [
  "jinhak",
  "jinhakapply",
  "uway",
  "uwayapply",
  "telegr",
  "01consulting",
  "nesin",
  "go3.co.kr",
];

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
  attachmentCandidatesPath: string;
  rawDir: string;
  publicDir: string;
  roles: Set<string>;
  limit: number | null;
  unvCds: Set<string> | null;
  delayMs: number;
  timeoutMs: number;
  outputSuffix: string | null;
  includeExternalHelperLinks: boolean;
  userAgent: string;
  fallbackCurl: boolean;
};

type AttachmentCandidateRow = {
  provider: string;
  artifactType: string;
  year: string;
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
};

type AttachmentArtifactManifest = {
  provider: "university-admission-office";
  artifactType: "admission_attachment_artifact";
  year: number;
  unvCd: string;
  universityName: string;
  campus: string;
  sourceLinkRole: string;
  attachmentRole: string;
  linkText: string;
  sourceCandidateUrl: string;
  attachmentUrl: string;
  canonicalAttachmentUrl?: string;
  finalUrl: string;
  fetchedAt: string;
  rawPath: string;
  sha256: string;
  bytes: number;
  httpStatus: number | null;
  contentType: string | null;
  contentDisposition: string | null;
  suggestedFilename: string;
  fileExtension: string;
  detectedKind: "file" | "html" | "unknown";
  status: "fetched" | "fetch_failed";
  fetchBackend?: "node_fetch" | "curl";
  error?: string;
  reusedFromUrlCache?: boolean;
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  let candidates = (await loadAttachmentCandidates(options.attachmentCandidatesPath))
    .filter((row) => Number(row.year) === options.year)
    .filter((row) => options.roles.has(row.attachmentRole))
    .filter((row) => !options.unvCds || options.unvCds.has(row.unvCd));

  const candidateCountBeforeExclusions = candidates.length;
  if (!options.includeExternalHelperLinks) {
    candidates = candidates.filter((row) => !isExcludedExternalHelperLink(row));
  }
  const excludedExternalHelperLinks = candidateCountBeforeExclusions - candidates.length;

  candidates = dedupeCandidates(candidates);
  if (options.limit !== null) {
    candidates = candidates.slice(0, options.limit);
  }

  const manifests: AttachmentArtifactManifest[] = [];
  const collectedByResolvedUrl = new Map<string, AttachmentArtifactManifest>();

  for (const [index, candidate] of candidates.entries()) {
    const cacheKey = cacheKeyForResolvedUrl(attachmentUrlForCandidate(candidate));
    const cachedManifest = collectedByResolvedUrl.get(cacheKey);
    const manifest = cachedManifest
      ? manifestFromCachedAttachment(candidate, options, cachedManifest)
      : await collectAttachment(candidate, options);
    if (!cachedManifest) {
      collectedByResolvedUrl.set(cacheKey, manifest);
    }
    manifests.push(manifest);

    console.log(
      [
        `university admission attachment year=${options.year}`,
        `index=${index + 1}/${candidates.length}`,
        `unvCd=${candidate.unvCd}`,
        `role=${candidate.attachmentRole}`,
        `status=${manifest.status}`,
        `kind=${manifest.detectedKind}`,
        `http=${manifest.httpStatus ?? ""}`,
        `ext=${manifest.fileExtension}`,
        `bytes=${manifest.bytes}`,
        `reused=${manifest.reusedFromUrlCache ? "true" : "false"}`,
      ].join(" "),
    );

    if (options.delayMs > 0 && index < candidates.length - 1) {
      await sleep(options.delayMs);
    }
  }

  const outputSuffix = outputSuffixFor(options);
  const outputSuffixSegment = outputSuffix ? `_${outputSuffix}` : "";
  const manifestPath = path.join(
    options.publicDir,
    `university_admission_attachment_artifact_manifest_${options.year}${outputSuffixSegment}.jsonl`,
  );
  const summaryPath = path.join(
    options.publicDir,
    `university_admission_attachment_artifacts_summary${outputSuffixSegment}.json`,
  );
  const yearSummaryPath = path.join(
    options.publicDir,
    `university_admission_attachment_artifacts_summary_${options.year}${outputSuffixSegment}.json`,
  );

  await writeJsonl(manifestPath, manifests);

  const summary = {
    provider: "university-admission-office",
    generatedAt: new Date().toISOString(),
    year: options.year,
    roles: [...options.roles].sort(),
    outputSuffix,
    skippedExternalHelperLinks: excludedExternalHelperLinks,
    excludedExternalHelperHosts: options.includeExternalHelperLinks
      ? []
      : [...DEFAULT_EXCLUDED_ATTACHMENT_HOSTS].sort(),
    excludedExternalHelperHostHints: options.includeExternalHelperLinks
      ? []
      : [...DEFAULT_EXCLUDED_EXTERNAL_HELPER_HOST_HINTS].sort(),
    attempted: candidates.length,
    fetched: manifests.filter((row) => row.status === "fetched").length,
    failed: manifests.filter((row) => row.status === "fetch_failed").length,
    fileArtifacts: manifests.filter(
      (row) => row.status === "fetched" && row.detectedKind === "file",
    ).length,
    reusedFromUrlCache: manifests.filter((row) => row.reusedFromUrlCache).length,
    httpOkFileArtifacts: manifests.filter(
      (row) =>
        row.status === "fetched" &&
        row.detectedKind === "file" &&
        row.httpStatus !== null &&
        row.httpStatus >= 200 &&
        row.httpStatus < 300,
    ).length,
    htmlArtifacts: manifests.filter(
      (row) => row.status === "fetched" && row.detectedKind === "html",
    ).length,
    bySourceLinkRole: countBy(manifests, "sourceLinkRole"),
    byAttachmentRole: countBy(manifests, "attachmentRole"),
    byDetectedKind: countBy(manifests, "detectedKind"),
    byHttpStatus: countBy(
      manifests.map((row) => ({ ...row, httpStatus: String(row.httpStatus ?? "") })),
      "httpStatus",
    ),
    byFileExtension: countBy(manifests, "fileExtension"),
    notes: [
      "Attachment artifacts are fetched from detail-page attachment candidates.",
      "Fetched files are raw source artifacts and require human verification before production use.",
      "HTML artifacts usually indicate a file route that requires extra parameters, cookies, or a board-specific downloader.",
    ],
  };

  const summaryJson = `${JSON.stringify(summary, null, 2)}\n`;
  await writeFile(summaryPath, summaryJson, "utf8");
  await writeFile(yearSummaryPath, summaryJson, "utf8");
}

function isExcludedExternalHelperLink(row: AttachmentCandidateRow): boolean {
  const attachmentHost =
    row.hostname.toLowerCase() || hostnameFor(attachmentUrlForCandidate(row));
  if (isExcludedExternalHelperHost(attachmentHost, DEFAULT_EXCLUDED_ATTACHMENT_HOSTS)) {
    return true;
  }
  const sourceHost = hostnameFor(row.sourceCandidateUrl);
  return isExcludedExternalHelperHost(sourceHost, DEFAULT_EXCLUDED_SOURCE_HOSTS);
}

function isExcludedExternalHelperHost(hostname: string, exactHosts: Set<string>) {
  const normalized = hostname.toLowerCase();
  return (
    exactHosts.has(normalized) ||
    DEFAULT_EXCLUDED_EXTERNAL_HELPER_HOST_HINTS.some((hint) => normalized.includes(hint))
  );
}

function manifestFromCachedAttachment(
  candidate: AttachmentCandidateRow,
  options: Options,
  cached: AttachmentArtifactManifest,
): AttachmentArtifactManifest {
  const attachmentUrl = attachmentUrlForCandidate(candidate);
  return {
    provider: "university-admission-office",
    artifactType: "admission_attachment_artifact",
    year: options.year,
    unvCd: candidate.unvCd,
    universityName: candidate.universityName,
    campus: candidate.campus,
    sourceLinkRole: candidate.sourceLinkRole,
    attachmentRole: candidate.attachmentRole,
    linkText: candidate.linkText,
    sourceCandidateUrl: candidate.sourceCandidateUrl,
    attachmentUrl,
    canonicalAttachmentUrl:
      cached.canonicalAttachmentUrl ?? cacheKeyForResolvedUrl(attachmentUrl),
    finalUrl: cached.finalUrl,
    fetchedAt: cached.fetchedAt,
    rawPath: cached.rawPath,
    sha256: cached.sha256,
    bytes: cached.bytes,
    httpStatus: cached.httpStatus,
    contentType: cached.contentType,
    contentDisposition: cached.contentDisposition,
    suggestedFilename: cached.suggestedFilename,
    fileExtension: cached.fileExtension,
    detectedKind: cached.detectedKind,
    status: cached.status,
    ...(cached.error ? { error: cached.error } : {}),
    ...(cached.fetchBackend ? { fetchBackend: cached.fetchBackend } : {}),
    reusedFromUrlCache: true,
  };
}

async function collectAttachment(
  candidate: AttachmentCandidateRow,
  options: Options,
): Promise<AttachmentArtifactManifest> {
  const fetchedAt = new Date().toISOString();
  const attachmentUrl = attachmentUrlForCandidate(candidate);
  const canonicalAttachmentUrl = cacheKeyForResolvedUrl(attachmentUrl);
  const sourceHash = sha256(canonicalAttachmentUrl).slice(0, 16);
  const yearDir = path.join(
    options.rawDir,
    String(options.year),
    candidate.unvCd,
    "attachments",
  );
  await mkdir(yearDir, { recursive: true });

  try {
    const response = await fetchAttachment(attachmentUrl, options);
    const buffer = response.buffer;
    const contentType = response.contentType;
    const contentDisposition = response.contentDisposition;
    const suggestedFilename = filenameFromContentDisposition(contentDisposition);
    const finalUrl = response.finalUrl || candidate.resolvedUrl;
    const suggestedExtension = fileExtensionForFilename(suggestedFilename);
    const detectedKind = detectKind(
      finalUrl,
      contentType,
      candidate.fileExtension,
      suggestedExtension,
      buffer,
    );
    const extension = detectExtension(
      finalUrl,
      contentType,
      candidate.fileExtension,
      suggestedExtension,
      detectedKind,
      buffer,
    );
    const rawPath = path.join(yearDir, `${sourceHash}.${extension || "bin"}`);

    await writeFile(rawPath, buffer);

    return {
      provider: "university-admission-office",
      artifactType: "admission_attachment_artifact",
      year: options.year,
      unvCd: candidate.unvCd,
      universityName: candidate.universityName,
      campus: candidate.campus,
      sourceLinkRole: candidate.sourceLinkRole,
      attachmentRole: candidate.attachmentRole,
      linkText: candidate.linkText,
      sourceCandidateUrl: candidate.sourceCandidateUrl,
      attachmentUrl,
      canonicalAttachmentUrl,
      finalUrl,
      fetchedAt,
      rawPath: toRepoRelative(rawPath, options.repoRoot),
      sha256: sha256Buffer(buffer),
      bytes: buffer.byteLength,
      httpStatus: response.httpStatus,
      contentType,
      contentDisposition,
      suggestedFilename,
      fileExtension: extension,
      detectedKind,
      status: "fetched",
      fetchBackend: response.backend,
    };
  } catch (error) {
    return {
      provider: "university-admission-office",
      artifactType: "admission_attachment_artifact",
      year: options.year,
      unvCd: candidate.unvCd,
      universityName: candidate.universityName,
      campus: candidate.campus,
      sourceLinkRole: candidate.sourceLinkRole,
      attachmentRole: candidate.attachmentRole,
      linkText: candidate.linkText,
      sourceCandidateUrl: candidate.sourceCandidateUrl,
      attachmentUrl,
      canonicalAttachmentUrl,
      finalUrl: "",
      fetchedAt,
      rawPath: toRepoRelative(path.join(yearDir, `${sourceHash}.bin`), options.repoRoot),
      sha256: "",
      bytes: 0,
      httpStatus: null,
      contentType: null,
      contentDisposition: null,
      suggestedFilename: "",
      fileExtension: "",
      detectedKind: "unknown",
      status: "fetch_failed",
      error: errorMessage(error),
    };
  }
}

function detectKind(
  url: string,
  contentType: string | null,
  originalExtension: string,
  suggestedExtension: string,
  buffer: Buffer,
): AttachmentArtifactManifest["detectedKind"] {
  const extension =
    preferredKnownExtension(url, suggestedExtension, originalExtension) ||
    magicExtensionFor(buffer);
  const normalizedContentType = contentType?.toLowerCase() ?? "";
  if (normalizedContentType.includes("text/html") || normalizedContentType.includes("application/xhtml")) {
    return "html";
  }
  const prefix = buffer.subarray(0, 200).toString("utf8").toLowerCase();
  if (prefix.includes("<!doctype html") || prefix.includes("<html")) return "html";
  if (FILE_EXTENSIONS.has(extension)) return "file";
  if (
    normalizedContentType.includes("pdf") ||
    normalizedContentType.includes("hwp") ||
    normalizedContentType.includes("spreadsheet") ||
    normalizedContentType.includes("excel") ||
    normalizedContentType.includes("zip") ||
     normalizedContentType.includes("octet-stream")
  ) {
    return "file";
  }
  return "unknown";
}

function detectExtension(
  url: string,
  contentType: string | null,
  originalExtension: string,
  suggestedExtension: string,
  detectedKind: AttachmentArtifactManifest["detectedKind"],
  buffer: Buffer,
) {
  const extension =
    preferredKnownExtension(url, suggestedExtension, originalExtension) ||
    magicExtensionFor(buffer);
  if (FILE_EXTENSIONS.has(extension)) return extension;
  if (detectedKind === "html") return "html";
  const normalizedContentType = contentType?.toLowerCase() ?? "";
  if (normalizedContentType.includes("pdf")) return "pdf";
  if (normalizedContentType.includes("hwp")) return "hwp";
  if (normalizedContentType.includes("spreadsheet")) return "xlsx";
  if (normalizedContentType.includes("excel")) return "xls";
  if (normalizedContentType.includes("zip")) return "zip";
  return extension || fileExtensionFor(url) || originalExtension.toLowerCase() || "bin";
}

function preferredKnownExtension(
  url: string,
  suggestedExtension: string,
  originalExtension: string,
) {
  const urlExtension = fileExtensionFor(url);
  if (FILE_EXTENSIONS.has(urlExtension)) return urlExtension;
  if (FILE_EXTENSIONS.has(suggestedExtension)) return suggestedExtension;
  const normalizedOriginalExtension = originalExtension.toLowerCase();
  if (FILE_EXTENSIONS.has(normalizedOriginalExtension)) return normalizedOriginalExtension;
  return "";
}

function magicExtensionFor(buffer: Buffer) {
  if (buffer.length >= 4 && buffer.subarray(0, 4).toString("latin1") === "%PDF") {
    return "pdf";
  }
  if (
    buffer.length >= 8 &&
    buffer[0] === 0xd0 &&
    buffer[1] === 0xcf &&
    buffer[2] === 0x11 &&
    buffer[3] === 0xe0 &&
    buffer[4] === 0xa1 &&
    buffer[5] === 0xb1 &&
    buffer[6] === 0x1a &&
    buffer[7] === 0xe1
  ) {
    const headerText = buffer.subarray(0, Math.min(buffer.length, 131072)).toString("latin1");
    if (headerText.includes("HWP Document")) return "hwp";
    if (headerText.includes("PowerPoint")) return "ppt";
    if (headerText.includes("WordDocument") || headerText.includes("Microsoft Word")) return "doc";
    if (headerText.includes("Workbook") || headerText.includes("Microsoft Excel")) return "xls";
    return "xls";
  }
  if (buffer.length >= 4 && buffer[0] === 0x50 && buffer[1] === 0x4b) {
    const headerText = buffer.subarray(0, Math.min(buffer.length, 262144)).toString("latin1");
    if (headerText.includes("word/")) return "docx";
    if (headerText.includes("ppt/")) return "pptx";
    if (headerText.includes("xl/")) return "xlsx";
    if (headerText.includes("mimetypeapplication/hwp+zip")) return "hwpx";
    return "zip";
  }
  return "";
}

function filenameFromContentDisposition(contentDisposition: string | null) {
  if (!contentDisposition) return "";
  const filenameStarMatch = contentDisposition.match(/filename\*\s*=\s*(?:"([^"]+)"|([^;]+))/i);
  const filenameStar = filenameStarMatch?.[1] ?? filenameStarMatch?.[2];
  if (filenameStar) {
    const normalized = filenameStar.trim();
    const encodedValue = normalized.includes("''")
      ? normalized.slice(normalized.indexOf("''") + 2)
      : normalized;
    return safeDecodeURIComponent(encodedValue.replace(/^['"]|['"]$/g, ""));
  }

  const filenameMatch = contentDisposition.match(/filename\s*=\s*(?:"([^"]+)"|([^;]+))/i);
  const filename = filenameMatch?.[1] ?? filenameMatch?.[2];
  return filename ? safeDecodeURIComponent(filename.trim().replace(/^['"]|['"]$/g, "")) : "";
}

async function fetchWithTimeout(url: string, timeoutMs: number, userAgent: string) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      headers: {
        "User-Agent": userAgent,
        Accept: "application/pdf,application/octet-stream,application/zip,text/html,application/xhtml+xml,*/*;q=0.8",
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchAttachment(url: string, options: Options) {
  try {
    const response = await fetchWithTimeout(url, options.timeoutMs, options.userAgent);
    return {
      buffer: Buffer.from(await response.arrayBuffer()),
      finalUrl: response.url || url,
      httpStatus: response.status,
      contentType: response.headers.get("content-type"),
      contentDisposition: response.headers.get("content-disposition"),
      backend: "node_fetch" as const,
    };
  } catch (fetchError) {
    if (!options.fallbackCurl) throw fetchError;
    try {
      return await fetchAttachmentWithCurl(url, options);
    } catch (curlError) {
      throw new Error(
        `${errorMessage(fetchError)}; curl fallback failed: ${errorMessage(curlError)}`,
      );
    }
  }
}

async function fetchAttachmentWithCurl(url: string, options: Options) {
  const marker = Buffer.from("\n__PACER_CURL_META__");
  const maxTimeSeconds = Math.max(1, Math.ceil(options.timeoutMs / 1000));
  const result = await execFileAsync(
    "curl",
    [
      "-L",
      "-sS",
      "--max-time",
      String(maxTimeSeconds),
      "-A",
      options.userAgent,
      "-w",
      `${marker.toString("utf8")}%{http_code}\t%{url_effective}\t%{content_type}\t%header{content-disposition}`,
      url,
    ],
    {
      encoding: "buffer",
      maxBuffer: 100 * 1024 * 1024,
    },
  );
  const stdout = Buffer.isBuffer(result.stdout)
    ? result.stdout
    : Buffer.from(result.stdout);
  const markerIndex = stdout.lastIndexOf(marker);
  if (markerIndex < 0) {
    throw new Error("curl fallback did not return metadata");
  }
  const buffer = stdout.subarray(0, markerIndex);
  const meta = stdout.subarray(markerIndex + marker.length).toString("utf8");
  const [statusText = "", finalUrl = url, contentType = "", contentDisposition = ""] =
    meta.split("\t");
  return {
    buffer,
    finalUrl: finalUrl || url,
    httpStatus: Number(statusText) || null,
    contentType: contentType || null,
    contentDisposition: contentDisposition || null,
    backend: "curl" as const,
  };
}

function errorMessage(error: unknown) {
  if (!(error instanceof Error)) return String(error);
  const cause = (error as Error & { cause?: unknown }).cause;
  if (!cause) return error.message;
  if (cause instanceof Error) return `${error.message}: ${cause.message}`;
  return `${error.message}: ${String(cause)}`;
}

async function loadAttachmentCandidates(filePath: string) {
  return parseCsv(await readFile(filePath, "utf8")) as AttachmentCandidateRow[];
}

function dedupeCandidates(rows: AttachmentCandidateRow[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.year}|${row.unvCd}|${row.attachmentRole}|${cacheKeyForResolvedUrl(row.resolvedUrl)}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function cacheKeyForResolvedUrl(value: string) {
  try {
    const parsed = new URL(value);
    parsed.pathname = parsed.pathname.replace(/;jsessionid=[^/?#;]*/gi, "");
    for (const key of [...parsed.searchParams.keys()]) {
      if (key.toLowerCase() === "jsessionid") {
        parsed.searchParams.delete(key);
      }
    }
    return parsed.toString();
  } catch {
    return value.replace(/;jsessionid=[^/?#;]*/gi, "");
  }
}

function hostnameFor(value: string) {
  try {
    return new URL(value).hostname.toLowerCase();
  } catch {
    return "";
  }
}

function attachmentUrlForCandidate(candidate: AttachmentCandidateRow) {
  const baseUrl = candidate.sourceCandidateUrl || candidate.resolvedUrl;
  const fromHref = firstUrlLikeJavaScriptArgument(candidate.hrefRaw, baseUrl);
  if (fromHref) return fromHref;
  const fromResolved = firstUrlLikeJavaScriptArgument(candidate.resolvedUrl, baseUrl);
  return fromResolved || candidate.resolvedUrl;
}

function firstUrlLikeJavaScriptArgument(value: string, baseUrl: string) {
  if (!/^javascript:/i.test(value) && !/file_download\s*\(/i.test(value)) return "";
  for (const raw of extractUrlLikeArguments(value)) {
    const resolved = resolveUrl(raw, baseUrl);
    if (resolved) return resolved;
  }
  return "";
}

function extractUrlLikeArguments(value: string) {
  const values: string[] = [];
  for (const match of value.matchAll(/["'](?<value>[^"']+)["']/g)) {
    const candidate = match.groups?.value ?? "";
    if (isUrlLike(candidate)) values.push(candidate);
  }
  return values;
}

function isUrlLike(value: string) {
  const normalized = safeDecodeURIComponent(decodeHtml(value)).trim();
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

function resolveUrl(value: string, baseUrl: string) {
  try {
    const url = new URL(decodeHtml(value).replace(/\\\//g, "/").trim(), baseUrl);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "";
    return url.toString();
  } catch {
    return "";
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

function fileExtensionForFilename(filename: string) {
  const match = filename.toLowerCase().match(/\.([a-z0-9]+)$/);
  return match?.[1] ?? "";
}

function safeDecodeURIComponent(value: string) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
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
    `${rows.map((row) => JSON.stringify(sanitizeJsonlValue(row))).join("\n")}\n`,
    "utf8",
  );
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

function sha256Buffer(value: Buffer) {
  return createHash("sha256").update(value).digest("hex");
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
    attachmentCandidatesPath: DEFAULT_ATTACHMENT_CANDIDATES,
    rawDir: DEFAULT_RAW_DIR,
    publicDir: DEFAULT_PUBLIC_DIR,
    roles: new Set(["direct_file"]),
    limit: null,
    unvCds: null,
    delayMs: 100,
    timeoutMs: 10000,
    outputSuffix: null,
    includeExternalHelperLinks: false,
    userAgent: USER_AGENT,
    fallbackCurl: false,
  };

  for (const arg of args) {
    if (arg.startsWith("--year=")) {
      options.year = Number(arg.slice("--year=".length));
    } else if (arg.startsWith("--attachment-candidates=")) {
      options.attachmentCandidatesPath = arg.slice("--attachment-candidates=".length);
    } else if (arg.startsWith("--raw-dir=")) {
      options.rawDir = arg.slice("--raw-dir=".length);
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--roles=")) {
      options.roles = new Set(
        arg
          .slice("--roles=".length)
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
      );
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
      options.outputSuffix = arg.slice("--output-suffix=".length);
    } else if (arg.startsWith("--user-agent=")) {
      options.userAgent = arg.slice("--user-agent=".length);
    } else if (arg === "--fallback-curl") {
      options.fallbackCurl = true;
    } else if (arg === "--include-external-helper-links") {
      options.includeExternalHelperLinks = true;
    }
  }

  return options;
}

function outputSuffixFor(options: Options) {
  if (options.outputSuffix !== null) return sanitizeOutputSuffix(options.outputSuffix);
  const roles = [...options.roles].sort();
  if (roles.length === 1 && roles[0] === "direct_file") return "";
  return sanitizeOutputSuffix(roles.join("_"));
}

function sanitizeOutputSuffix(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function withResolvedPaths(options: Options): Options {
  const repoRoot = options.repoRoot;
  return {
    ...options,
    attachmentCandidatesPath: path.resolve(repoRoot, options.attachmentCandidatesPath),
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
