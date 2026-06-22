import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";

const DEFAULT_YEAR = 2027;
const DEFAULT_LINK_CANDIDATES =
  "packages/reference-data/data/public/university-admission-sites/university_admission_link_candidates_2027.csv";
const DEFAULT_RAW_DIR = ".reference-data/raw/university-admission-sites";
const DEFAULT_PUBLIC_DIR =
  "packages/reference-data/data/public/university-admission-sites";
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+manual admin-curated use; public admission office artifacts only)";
const execFileAsync = promisify(execFile);

const DEFAULT_ROLES = [
  "regular_admission_guide",
  "admission_result",
  "competition_rate",
  "recruitment_notice",
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

const OUT_OF_SCOPE_ATTACHMENT_PATTERN =
  /대학\s*요람|교육\s*만족도|편입|외국인|대학원|시간제|평생교육|계약학과|산업체|생활관|기숙사|장학|등록금|교통|오시는\s*길|캠퍼스|교직원|채용|입학식|학위수여|졸업|yoram|edu[_-]?level|survey|transfer|foreigner|graduate|dorm|tuition|campus|employment/i;

const EXCLUDED_EXTERNAL_HELPER_HOST_HINTS = [
  "jinhak",
  "uwayapply",
  "uway",
  "telegr",
  "01consulting",
  "nesin",
  "apply",
];

type Options = {
  repoRoot: string;
  year: number;
  linkCandidatesPath: string;
  rawDir: string;
  publicDir: string;
  roles: Set<string>;
  limit: number | null;
  unvCds: Set<string> | null;
  delayMs: number;
  timeoutMs: number;
  outputSuffix: string;
  userAgent: string;
  fallbackCurl: boolean;
};

type LinkCandidateRow = {
  provider: string;
  artifactType: string;
  year: string;
  unvCd: string;
  universityName: string;
  campus: string;
  sourceHomepageUrl: string;
  finalHomepageUrl: string;
  rawPath: string;
  linkRole: string;
  linkText: string;
  hrefRaw: string;
  resolvedUrl: string;
  hostname: string;
  fileExtension: string;
  keywordHits: string;
};

type ArtifactManifest = {
  provider: "university-admission-office";
  artifactType: "admission_detail_html" | "admission_direct_file";
  year: number;
  unvCd: string;
  universityName: string;
  campus: string;
  sourceLinkRole: string;
  sourceLinkText: string;
  sourceCandidateUrl: string;
  finalUrl: string;
  fetchedAt: string;
  rawPath: string;
  sha256: string;
  bytes: number;
  httpStatus: number | null;
  contentType: string | null;
  fileExtension: string;
  attachmentCandidateCount: number;
  status: "fetched" | "fetch_failed";
  fetchBackend?: "node_fetch" | "curl";
  error?: string;
};

type AttachmentCandidate = {
  provider: "university-admission-office";
  artifactType: "admission_attachment_link_candidate";
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
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  let linkCandidates = (await loadLinkCandidates(options.linkCandidatesPath))
    .filter((row) => Number(row.year) === options.year)
    .filter((row) => options.roles.has(row.linkRole))
    .filter((row) => !options.unvCds || options.unvCds.has(row.unvCd));

  linkCandidates = dedupeLinkCandidateRows(linkCandidates);
  if (options.limit !== null) {
    linkCandidates = linkCandidates.slice(0, options.limit);
  }

  const manifests: ArtifactManifest[] = [];
  const attachmentCandidates: AttachmentCandidate[] = [];

  for (const [index, candidate] of linkCandidates.entries()) {
    const result = await collectCandidate(candidate, options);
    manifests.push(result.manifest);
    attachmentCandidates.push(...result.attachments);

    console.log(
      [
        `university admission artifact year=${options.year}`,
        `index=${index + 1}/${linkCandidates.length}`,
        `unvCd=${candidate.unvCd}`,
        `role=${candidate.linkRole}`,
        `status=${result.manifest.status}`,
        `type=${result.manifest.artifactType}`,
        `http=${result.manifest.httpStatus ?? ""}`,
        `bytes=${result.manifest.bytes}`,
        `attachments=${result.attachments.length}`,
      ].join(" "),
    );

    if (options.delayMs > 0 && index < linkCandidates.length - 1) {
      await sleep(options.delayMs);
    }
  }

  const manifestPath = path.join(
    options.publicDir,
    `university_admission_link_artifact_manifest_${options.year}${outputSuffixPart(options)}.jsonl`,
  );
  const attachmentsPath = path.join(
    options.publicDir,
    `university_admission_attachment_candidates_${options.year}${outputSuffixPart(options)}.csv`,
  );
  const summaryPath = path.join(
    options.publicDir,
    options.outputSuffix
      ? `university_admission_artifacts_summary_${options.outputSuffix}.json`
      : "university_admission_artifacts_summary.json",
  );
  const yearSummaryPath = path.join(
    options.publicDir,
    `university_admission_artifacts_summary_${options.year}${outputSuffixPart(options)}.json`,
  );

  const dedupedAttachments = dedupeAttachmentCandidates(attachmentCandidates);
  await writeJsonl(manifestPath, manifests);
  await writeCsv(attachmentsPath, dedupedAttachments, [
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
  ]);

  const summary = {
    provider: "university-admission-office",
    generatedAt: new Date().toISOString(),
    year: options.year,
    roles: [...options.roles].sort(),
    attempted: linkCandidates.length,
    fetched: manifests.filter((row) => row.status === "fetched").length,
    failed: manifests.filter((row) => row.status === "fetch_failed").length,
    detailHtmlArtifacts: manifests.filter(
      (row) => row.status === "fetched" && row.artifactType === "admission_detail_html",
    ).length,
    directFileArtifacts: manifests.filter(
      (row) => row.status === "fetched" && row.artifactType === "admission_direct_file",
    ).length,
    attachmentCandidates: dedupedAttachments.length,
    bySourceLinkRole: countBy(manifests, "sourceLinkRole"),
    byArtifactType: countBy(manifests, "artifactType"),
    byArtifactStatus: countBy(manifests, "status"),
    byHttpStatus: countBy(
      manifests.map((row) => ({ ...row, httpStatus: String(row.httpStatus ?? "") })),
      "httpStatus",
    ),
    byFileExtension: countBy(manifests, "fileExtension"),
    byAttachmentRole: countBy(dedupedAttachments, "attachmentRole"),
    byAttachmentFileExtension: countBy(dedupedAttachments, "fileExtension"),
    outputSuffix: options.outputSuffix || null,
    notes: [
      "Direct file links are saved as raw artifacts.",
      "HTML/detail links are saved as raw artifacts and scanned for attachment/file-download candidates.",
      "Attachment candidates are crawl targets and are not verified production AdmissionRule or HistoricalOutcome records.",
    ],
  };

  const summaryJson = `${JSON.stringify(summary, null, 2)}\n`;
  await writeFile(summaryPath, summaryJson, "utf8");
  await writeFile(yearSummaryPath, summaryJson, "utf8");
}

async function collectCandidate(candidate: LinkCandidateRow, options: Options) {
  const fetchedAt = new Date().toISOString();
  const sourceHash = sha256(candidate.resolvedUrl).slice(0, 16);
  const yearDir = path.join(
    options.rawDir,
    String(options.year),
    candidate.unvCd,
    options.outputSuffix ? `link-artifacts-${options.outputSuffix}` : "link-artifacts",
  );
  await mkdir(yearDir, { recursive: true });

  try {
    let response = await fetchArtifact(candidate.resolvedUrl, options);
    let buffer = response.buffer;
    let contentType = response.contentType;
    let finalUrl = response.finalUrl || candidate.resolvedUrl;
    let extension = detectArtifactExtension(finalUrl, contentType, candidate.fileExtension);
    let isHtml = isHtmlArtifact(finalUrl, contentType, candidate.fileExtension, buffer);

    if (isHtml) {
      const html = decodedBufferText(buffer, contentType);
      const metaRefreshUrl = extractMetaRefreshUrl(html, finalUrl);
      if (
        metaRefreshUrl &&
        metaRefreshUrl !== finalUrl &&
        !isExcludedExternalHelperLinkUrl(metaRefreshUrl)
      ) {
        response = await fetchArtifact(metaRefreshUrl, options);
        buffer = response.buffer;
        contentType = response.contentType;
        finalUrl = response.finalUrl || metaRefreshUrl;
        extension = detectArtifactExtension(finalUrl, contentType, candidate.fileExtension);
        isHtml = isHtmlArtifact(finalUrl, contentType, candidate.fileExtension, buffer);
      }
    }

    const rawPath = path.join(yearDir, `${sourceHash}.${isHtml ? "html" : extension || "bin"}`);

    await writeFile(rawPath, buffer);

    const repoRelativeRawPath = toRepoRelative(rawPath, options.repoRoot);
    const html = isHtml ? decodedBufferText(buffer, contentType) : "";
    const attachments = isHtml
      ? extractAttachmentCandidates(html, candidate, finalUrl, repoRelativeRawPath)
      : [];

    return {
      manifest: {
        provider: "university-admission-office",
        artifactType: isHtml ? "admission_detail_html" : "admission_direct_file",
        year: options.year,
        unvCd: candidate.unvCd,
        universityName: candidate.universityName,
        campus: candidate.campus,
        sourceLinkRole: candidate.linkRole,
        sourceLinkText: candidate.linkText,
        sourceCandidateUrl: candidate.resolvedUrl,
        finalUrl,
        fetchedAt,
        rawPath: repoRelativeRawPath,
        sha256: sha256Buffer(buffer),
        bytes: buffer.byteLength,
        httpStatus: response.httpStatus,
        contentType,
        fileExtension: isHtml ? "html" : extension,
        attachmentCandidateCount: attachments.length,
        status: "fetched",
        fetchBackend: response.backend,
      } satisfies ArtifactManifest,
      attachments,
    };
  } catch (error) {
    return {
      manifest: {
        provider: "university-admission-office",
        artifactType: "admission_detail_html",
        year: options.year,
        unvCd: candidate.unvCd,
        universityName: candidate.universityName,
        campus: candidate.campus,
        sourceLinkRole: candidate.linkRole,
        sourceLinkText: candidate.linkText,
        sourceCandidateUrl: candidate.resolvedUrl,
        finalUrl: "",
        fetchedAt,
        rawPath: toRepoRelative(path.join(yearDir, `${sourceHash}.html`), options.repoRoot),
        sha256: "",
        bytes: 0,
        httpStatus: null,
        contentType: null,
        fileExtension: "",
        attachmentCandidateCount: 0,
        status: "fetch_failed",
        error: errorMessage(error),
      } satisfies ArtifactManifest,
      attachments: [] as AttachmentCandidate[],
    };
  }
}

function extractAttachmentCandidates(
  html: string,
  source: LinkCandidateRow,
  detailUrl: string,
  detailRawPath: string,
) {
  const candidates: AttachmentCandidate[] = [];
  const anchorPattern =
    /<a\b(?<attrs>[\s\S]*?)>(?<label>[\s\S]*?)<\/a>/gi;

  for (const match of html.matchAll(anchorPattern)) {
    const attrs = match.groups?.attrs ?? "";
    const hrefRaw = extractAttribute(attrs, "href");
    if (!hrefRaw || hrefRaw.startsWith("#")) {
      continue;
    }

    const linkText = stripTags(decodeHtml(match.groups?.label ?? ""));
    for (const candidateUrl of resolveCandidateUrlsFromHref(hrefRaw, detailUrl)) {
      if (isExcludedExternalHelperLinkUrl(candidateUrl.resolvedUrl)) continue;

      const fileExtension = fileExtensionFor(candidateUrl.resolvedUrl);
      const keywordHits = keywordHitsFor(linkText, candidateUrl.resolvedUrl);
      const attachmentRole = classifyAttachment(linkText, candidateUrl.resolvedUrl, keywordHits);

      if (!attachmentRole) continue;

      candidates.push({
        provider: "university-admission-office",
        artifactType: "admission_attachment_link_candidate",
        year: Number(source.year),
        unvCd: source.unvCd,
        universityName: source.universityName,
        campus: source.campus,
        sourceLinkRole: source.linkRole,
        sourceLinkText: source.linkText,
        sourceCandidateUrl: source.resolvedUrl,
        detailRawPath,
        attachmentRole,
        linkText,
        hrefRaw: candidateUrl.raw,
        resolvedUrl: candidateUrl.resolvedUrl,
        hostname: new URL(candidateUrl.resolvedUrl).hostname,
        fileExtension,
        keywordHits: keywordHits.join("|"),
      });
    }
  }

  for (const scriptCandidate of extractScriptNavigationCandidates(html, detailUrl)) {
    if (isExcludedExternalHelperLinkUrl(scriptCandidate.resolvedUrl)) continue;

    const fileExtension = fileExtensionFor(scriptCandidate.resolvedUrl);
    const keywordHits = keywordHitsFor(scriptCandidate.linkText, scriptCandidate.resolvedUrl);
    const attachmentRole = classifyAttachment(
      scriptCandidate.linkText,
      scriptCandidate.resolvedUrl,
      keywordHits,
    );

    if (!attachmentRole) continue;

    candidates.push({
      provider: "university-admission-office",
      artifactType: "admission_attachment_link_candidate",
      year: Number(source.year),
      unvCd: source.unvCd,
      universityName: source.universityName,
      campus: source.campus,
      sourceLinkRole: source.linkRole,
      sourceLinkText: source.linkText,
      sourceCandidateUrl: source.resolvedUrl,
      detailRawPath,
      attachmentRole,
      linkText: scriptCandidate.linkText,
      hrefRaw: scriptCandidate.raw,
      resolvedUrl: scriptCandidate.resolvedUrl,
      hostname: new URL(scriptCandidate.resolvedUrl).hostname,
      fileExtension,
      keywordHits: keywordHits.join("|"),
    });
  }

  return dedupeAttachmentCandidates(candidates);
}

function extractMetaRefreshUrl(html: string, detailUrl: string) {
  for (const match of html.matchAll(/<meta\b(?<attrs>[^>]*)>/gi)) {
    const attrs = match.groups?.attrs ?? "";
    const httpEquiv = extractAttribute(attrs, "http-equiv").toLowerCase();
    if (httpEquiv !== "refresh") continue;

    const content = extractAttribute(attrs, "content");
    const urlMatch = content.match(/(?:^|;)\s*url\s*=\s*(?<url>.+?)\s*$/i);
    const rawUrl = urlMatch?.groups?.url?.replace(/^["']|["']$/g, "") ?? "";
    if (!rawUrl) continue;

    return resolveUrl(cleanHref(rawUrl), detailUrl);
  }

  return null;
}

function extractScriptNavigationCandidates(html: string, detailUrl: string) {
  const patterns = [
    {
      label: "script location href",
      pattern:
        /(?:document\.|self\.|window\.|top\.|parent\.)?location(?:\.href)?\s*=\s*["'](?<url>[^"']+)["']/gi,
    },
    {
      label: "script location replace",
      pattern: /location\.replace\(\s*["'](?<url>[^"']+)["']/gi,
    },
    {
      label: "script window open",
      pattern: /window\.open\(\s*["'](?<url>[^"']+)["']/gi,
    },
    {
      label: "script tcontrol href",
      pattern: /TControl\.setHref\(\s*["'](?<url>[^"']+)["']/gi,
    },
  ];
  const candidates: Array<{ raw: string; resolvedUrl: string; linkText: string }> = [];

  for (const { label, pattern } of patterns) {
    for (const match of html.matchAll(pattern)) {
      const raw = match.groups?.url ?? "";
      const resolvedUrl = resolveUrl(cleanHref(raw), detailUrl);
      if (resolvedUrl) {
        candidates.push({ raw, resolvedUrl, linkText: label });
      }
    }
  }

  return candidates;
}

function isExcludedExternalHelperLinkUrl(url: string) {
  try {
    const parsed = new URL(url);
    const hostname = parsed.hostname.toLowerCase();
    return EXCLUDED_EXTERNAL_HELPER_HOST_HINTS.some((hint) => hostname.includes(hint));
  } catch {
    return false;
  }
}

function resolveCandidateUrlsFromHref(hrefRaw: string, detailUrl: string) {
  const cleaned = cleanHref(hrefRaw);
  if (!cleaned) return [];
  if (/^(mailto|tel):/i.test(cleaned)) return [];
  if (/^javascript:\s*$/i.test(cleaned)) return [];
  if (/^javascript:/i.test(cleaned)) {
    return extractUrlLikeArguments(cleaned)
      .map((raw) => ({ raw, resolvedUrl: resolveUrl(raw, detailUrl) }))
      .filter((row): row is { raw: string; resolvedUrl: string } => Boolean(row.resolvedUrl));
  }
  const resolvedUrl = resolveUrl(cleaned, detailUrl);
  return resolvedUrl ? [{ raw: hrefRaw, resolvedUrl }] : [];
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
  if (isOutOfScopeAttachment(linkText, url)) return null;
  if (FILE_EXTENSIONS.has(extension)) return "direct_file";
  if (
    haystack.includes("filedown") ||
    haystack.includes("download") ||
    haystack.includes("다운로드") ||
    haystack.includes("첨부") ||
    haystack.includes("파일")
  ) {
    return "file_download_route";
  }
  if (isAdmissionLikeUrl(url)) return "related_detail";
  if (keywordHits.length > 0) return "related_detail";
  return null;
}

function isOutOfScopeAttachment(linkText: string, url: string) {
  const haystack = compact(`${linkText} ${decodeURIComponentSafe(url)}`).toLowerCase();
  return OUT_OF_SCOPE_ATTACHMENT_PATTERN.test(haystack);
}

function isAdmissionLikeUrl(url: string) {
  try {
    const parsed = new URL(url);
    const haystack = compact(`${parsed.hostname} ${parsed.pathname}`);
    return ["admission", "enter", "entra", "ent", "ipsi", "iphak", "intro.uway"].some(
      (hint) => haystack.includes(hint),
    );
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
    "첨부",
    "다운로드",
    "파일",
  ];
  return keywords.filter((keyword) => haystack.includes(keyword));
}

function isHtmlArtifact(
  url: string,
  contentType: string | null,
  originalExtension: string,
  buffer: Buffer,
) {
  const extension = fileExtensionFor(url) || originalExtension.toLowerCase();
  if (FILE_EXTENSIONS.has(extension)) return false;
  if (contentType?.toLowerCase().includes("text/html")) return true;
  if (contentType?.toLowerCase().includes("application/xhtml")) return true;
  if (contentType?.toLowerCase().includes("text/plain")) {
    return buffer.subarray(0, 200).toString("utf8").includes("<html");
  }
  return buffer.subarray(0, 200).toString("utf8").toLowerCase().includes("<!doctype html") ||
    buffer.subarray(0, 200).toString("utf8").toLowerCase().includes("<html");
}

function detectArtifactExtension(
  url: string,
  contentType: string | null,
  originalExtension: string,
) {
  const extension = fileExtensionFor(url) || originalExtension.toLowerCase();
  if (FILE_EXTENSIONS.has(extension)) return extension;
  const normalizedContentType = contentType?.toLowerCase() ?? "";
  if (normalizedContentType.includes("pdf")) return "pdf";
  if (normalizedContentType.includes("hwp")) return "hwp";
  if (normalizedContentType.includes("spreadsheet")) return "xlsx";
  if (normalizedContentType.includes("excel")) return "xls";
  if (normalizedContentType.includes("zip")) return "zip";
  return extension || "bin";
}

async function fetchWithTimeout(url: string, timeoutMs: number, userAgent: string) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, {
      headers: {
        "User-Agent": userAgent,
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf,application/octet-stream,*/*;q=0.8",
      },
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function fetchArtifact(url: string, options: Options) {
  try {
    const response = await fetchWithTimeout(url, options.timeoutMs, options.userAgent);
    return {
      buffer: Buffer.from(await response.arrayBuffer()),
      finalUrl: response.url || url,
      httpStatus: response.status,
      contentType: response.headers.get("content-type"),
      backend: "node_fetch" as const,
    };
  } catch (fetchError) {
    if (!options.fallbackCurl) throw fetchError;
    try {
      return await fetchArtifactWithCurl(url, options);
    } catch (curlError) {
      throw new Error(
        `${errorMessage(fetchError)}; curl fallback failed: ${errorMessage(curlError)}`,
      );
    }
  }
}

function decodedBufferText(buffer: Buffer, contentType: string | null) {
  const charset = charsetForBuffer(buffer, contentType ?? "");
  return new TextDecoder(charset, { fatal: false }).decode(buffer);
}

function charsetForBuffer(buffer: Buffer, contentType: string) {
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

async function fetchArtifactWithCurl(url: string, options: Options) {
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
      `${marker.toString("utf8")}%{http_code}\t%{url_effective}\t%{content_type}`,
      url,
    ],
    {
      encoding: "buffer",
      maxBuffer: 50 * 1024 * 1024,
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
  const [statusText = "", finalUrl = url, contentType = ""] = meta.split("\t");
  return {
    buffer,
    finalUrl: finalUrl || url,
    httpStatus: Number(statusText) || null,
    contentType: contentType || null,
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

async function loadLinkCandidates(filePath: string) {
  return parseCsv(await readFile(filePath, "utf8")) as LinkCandidateRow[];
}

function dedupeLinkCandidateRows(rows: LinkCandidateRow[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.year}|${row.unvCd}|${row.linkRole}|${row.resolvedUrl}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function dedupeAttachmentCandidates(rows: AttachmentCandidate[]) {
  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.year}|${row.unvCd}|${row.sourceCandidateUrl}|${row.resolvedUrl}|${row.linkText}`;
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

function sha256Buffer(value: Buffer) {
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
    linkCandidatesPath: DEFAULT_LINK_CANDIDATES,
    rawDir: DEFAULT_RAW_DIR,
    publicDir: DEFAULT_PUBLIC_DIR,
    roles: new Set(DEFAULT_ROLES),
    limit: null,
    unvCds: null,
    delayMs: 100,
    timeoutMs: 10000,
    outputSuffix: "",
    userAgent: USER_AGENT,
    fallbackCurl: false,
  };

  for (const arg of args) {
    if (arg.startsWith("--year=")) {
      options.year = Number(arg.slice("--year=".length));
    } else if (arg.startsWith("--link-candidates=")) {
      options.linkCandidatesPath = arg.slice("--link-candidates=".length);
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
    } else if (arg === "--all-roles") {
      options.roles = new Set([
        ...DEFAULT_ROLES,
        "admission_related",
      ]);
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
  return value.trim().replace(/[^a-zA-Z0-9_-]/g, "_").replace(/^_+|_+$/g, "");
}

function withResolvedPaths(options: Options): Options {
  const repoRoot = options.repoRoot;
  return {
    ...options,
    linkCandidatesPath: path.resolve(repoRoot, options.linkCandidatesPath),
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
