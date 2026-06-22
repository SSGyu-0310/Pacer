import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE_URL = "https://www.kcue.or.kr";
const BOARD_PATH = "/news/sub02/sub01.php";
const DEFAULT_RAW_DIR = ".reference-data/raw/kcue-admissions-press";
const DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/kcue";
const DEFAULT_QUERIES = [
  "대학입학전형시행계획",
  "대학입학전형 기본사항",
  "대입전형 기본사항",
  "전형기본사항",
  "정시모집",
  "수시모집",
  "공통원서",
  "대입상담",
];
const DEFAULT_MAX_PAGES = 8;
const DEFAULT_MIN_POSTED_YEAR = 2021;
const DEFAULT_MAX_POSTED_YEAR = 2026;
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+official KCUE admissions press pages)";

type Options = {
  repoRoot: string;
  rawDir: string;
  publicDir: string;
  queries: string[];
  maxPages: number;
  minPostedYear: number;
  maxPostedYear: number;
  download: boolean;
  delayMs: number;
};

type PressPost = {
  provider: "kcue";
  artifactType: "kcue_admissions_press_post";
  idx: string;
  queries: string[];
  pages: number[];
  title: string;
  postRole: PostRole;
  academicYear: number | null;
  postedDate: string | null;
  postedYear: number | null;
  writer: string | null;
  viewCount: number | null;
  listUrls: string[];
  viewUrl: string;
  rawViewPath: string | null;
  bodyTextPreview: string;
  embeddedPdfUrls: string[];
  attachments: PressAttachment[];
  listedAt: string;
  fetchedAt: string | null;
  status: "listed" | "view_fetched" | "view_fetch_failed";
  error?: string;
};

type PressAttachment = {
  provider: "kcue";
  artifactType: "kcue_admissions_press_attachment";
  idx: string;
  title: string;
  postRole: PostRole;
  academicYear: number | null;
  postedDate: string | null;
  attachmentIndex: number;
  attachmentTitle: string;
  attachmentRole: AttachmentRole;
  expectedExtension: string;
  sourceUrl: string;
  viewUrl: string;
  fetchedAt: string | null;
  rawPath: string | null;
  sha256: string | null;
  bytes: number | null;
  contentType: string | null;
  status: "listed" | "downloaded" | "download_failed";
  error?: string;
};

type ListPostCandidate = {
  query: string;
  page: number;
  listUrl: string;
  idx: string;
  title: string;
  postedDate: string | null;
  writer: string | null;
  viewCount: number | null;
  viewUrl: string;
};

type PostRole =
  | "implementation_plan"
  | "admission_policy_basics"
  | "regular_admission_application"
  | "regular_admission_counseling"
  | "early_admission_application"
  | "early_admission_counseling"
  | "admission_consulting"
  | "admission_info_portal"
  | "other_admissions_press";

type AttachmentRole =
  | "implementation_plan_press_pdf"
  | "implementation_plan_press_hwp"
  | "implementation_plan_key_points_pdf"
  | "implementation_plan_key_points_hwp"
  | "admission_policy_basics_pdf"
  | "admission_policy_basics_hwp"
  | "regular_admission_application_press"
  | "regular_admission_counseling_press"
  | "early_admission_application_press"
  | "early_admission_counseling_press"
  | "admission_consulting_press"
  | "admission_press_other";

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  const candidatesByIdx = new Map<string, ListPostCandidate[]>();

  for (const query of options.queries) {
    for (let page = 1; page <= options.maxPages; page += 1) {
      const listUrl = buildListUrl(query, page);
      const html = await fetchText(listUrl);
      await writeRawListPage(options.rawDir, query, page, html);

      const candidates = parseListPage(html, query, page, listUrl).filter((candidate) =>
        isWithinPostedYear(candidate.postedDate, options),
      );
      for (const candidate of candidates) {
        const existing = candidatesByIdx.get(candidate.idx) ?? [];
        candidatesByIdx.set(candidate.idx, [...existing, candidate]);
      }

      const pageCount = maxPaginationPage(html);
      if (pageCount !== null && page >= pageCount) break;
      if (candidates.length === 0 && page > 1) break;
    }
  }

  const posts: PressPost[] = [];
  const attachments: PressAttachment[] = [];

  for (const [index, [idx, candidates]] of [...candidatesByIdx.entries()].entries()) {
    const post = await collectPost(idx, candidates, options);
    posts.push(post);
    attachments.push(...post.attachments);

    console.log(
      [
        "kcue admissions press",
        `index=${index + 1}/${candidatesByIdx.size}`,
        `idx=${idx}`,
        `role=${post.postRole}`,
        `status=${post.status}`,
        `attachments=${post.attachments.length}`,
        `downloaded=${post.attachments.filter((row) => row.status === "downloaded").length}`,
      ].join(" "),
    );

    if (options.delayMs > 0 && index < candidatesByIdx.size - 1) {
      await sleep(options.delayMs);
    }
  }

  const sortedPosts = posts.sort(comparePosts);
  const sortedAttachments = attachments.sort(compareAttachments);

  await writeJsonl(
    path.join(options.publicDir, "kcue_admissions_press_posts_manifest.jsonl"),
    sortedPosts,
  );
  await writeJsonl(
    path.join(options.publicDir, "kcue_admissions_press_attachment_manifest.jsonl"),
    sortedAttachments,
  );
  await writeFile(
    path.join(options.publicDir, "kcue_admissions_press_summary.json"),
    `${JSON.stringify(summarize(sortedPosts, sortedAttachments, options), null, 2)}\n`,
    "utf8",
  );
  await writeReadme(options.publicDir);

  console.log(
    [
      "kcue admissions press collection complete.",
      `posts=${sortedPosts.length}`,
      `attachments=${sortedAttachments.length}`,
      `downloaded=${sortedAttachments.filter((row) => row.status === "downloaded").length}`,
      `failed=${sortedAttachments.filter((row) => row.status === "download_failed").length}`,
    ].join(" "),
  );
}

async function collectPost(
  idx: string,
  candidates: ListPostCandidate[],
  options: Options,
): Promise<PressPost> {
  const representative = candidates.sort(compareListCandidates)[0]!;
  const listedAt = new Date().toISOString();
  const queries = [...new Set(candidates.map((candidate) => candidate.query))].sort();
  const pages = [...new Set(candidates.map((candidate) => candidate.page))].sort(
    (a, b) => a - b,
  );
  const listUrls = [...new Set(candidates.map((candidate) => candidate.listUrl))].sort();

  try {
    const html = await fetchText(representative.viewUrl);
    const rawViewPath = path.join(options.rawDir, "views", `${idx}.html`);
    await mkdir(path.dirname(rawViewPath), { recursive: true });
    await writeFile(rawViewPath, html, "utf8");

    const title = cleanTitle(parseViewTitle(html) || representative.title);
    const postedDate = parseViewField(html, "작성일") ?? representative.postedDate;
    const academicYear = academicYearFromText(`${title} ${htmlToText(html).slice(0, 2000)}`);
    const postRole = postRoleFromTitle(title);
    const bodyTextPreview = parseBodyTextPreview(html);
    const embeddedPdfUrls = parseEmbeddedPdfUrls(html);
    const rawAttachments = parseAttachments(html, representative.viewUrl);
    const attachments = await collectAttachments(
      {
        idx,
        title,
        postRole,
        academicYear,
        postedDate,
        viewUrl: representative.viewUrl,
      },
      rawAttachments,
      options,
    );

    return {
      provider: "kcue",
      artifactType: "kcue_admissions_press_post",
      idx,
      queries,
      pages,
      title,
      postRole,
      academicYear,
      postedDate,
      postedYear: postedYearFromDate(postedDate),
      writer: parseViewField(html, "작성자") ?? representative.writer,
      viewCount: numberFromText(parseViewField(html, "조회")) ?? representative.viewCount,
      listUrls,
      viewUrl: representative.viewUrl,
      rawViewPath: toRepoRelative(rawViewPath, options.repoRoot),
      bodyTextPreview,
      embeddedPdfUrls,
      attachments,
      listedAt,
      fetchedAt: new Date().toISOString(),
      status: "view_fetched",
    };
  } catch (error) {
    return {
      provider: "kcue",
      artifactType: "kcue_admissions_press_post",
      idx,
      queries,
      pages,
      title: cleanTitle(representative.title),
      postRole: postRoleFromTitle(representative.title),
      academicYear: academicYearFromText(representative.title),
      postedDate: representative.postedDate,
      postedYear: postedYearFromDate(representative.postedDate),
      writer: representative.writer,
      viewCount: representative.viewCount,
      listUrls,
      viewUrl: representative.viewUrl,
      rawViewPath: null,
      bodyTextPreview: "",
      embeddedPdfUrls: [],
      attachments: [],
      listedAt,
      fetchedAt: new Date().toISOString(),
      status: "view_fetch_failed",
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

async function collectAttachments(
  post: {
    idx: string;
    title: string;
    postRole: PostRole;
    academicYear: number | null;
    postedDate: string | null;
    viewUrl: string;
  },
  rawAttachments: { title: string; sourceUrl: string }[],
  options: Options,
): Promise<PressAttachment[]> {
  const rows: PressAttachment[] = [];

  for (const [index, rawAttachment] of rawAttachments.entries()) {
    const attachmentTitle = cleanTitle(rawAttachment.title);
    const expectedExtension = extensionFromTitle(attachmentTitle);
    const baseRow: PressAttachment = {
      provider: "kcue",
      artifactType: "kcue_admissions_press_attachment",
      idx: post.idx,
      title: post.title,
      postRole: post.postRole,
      academicYear: post.academicYear,
      postedDate: post.postedDate,
      attachmentIndex: index + 1,
      attachmentTitle,
      attachmentRole: attachmentRoleFromTitle(attachmentTitle, post.postRole),
      expectedExtension,
      sourceUrl: rawAttachment.sourceUrl,
      viewUrl: post.viewUrl,
      fetchedAt: null,
      rawPath: null,
      sha256: null,
      bytes: null,
      contentType: null,
      status: "listed",
    };

    if (!options.download) {
      rows.push(baseRow);
      continue;
    }

    try {
      const response = await fetch(rawAttachment.sourceUrl, {
        headers: {
          "User-Agent": USER_AGENT,
          Referer: post.viewUrl,
        },
      });
      if (!response.ok) throw new Error(`download failed ${response.status}`);
      const bytes = Buffer.from(await response.arrayBuffer());
      if (bytes.length === 0) throw new Error("downloaded empty file");

      const contentType = response.headers.get("content-type");
      const headerFilename = contentDispositionFilename(
        response.headers.get("content-disposition"),
      );
      const fileExtension =
        extensionFromTitle(headerFilename ?? "") ||
        expectedExtension ||
        extensionFromContentType(contentType) ||
        extensionFromMagicBytes(bytes) ||
        "bin";
      const outputDir = path.join(
        options.rawDir,
        "attachments",
        String(post.academicYear ?? postedYearFromDate(post.postedDate) ?? "unknown"),
        post.idx,
      );
      await mkdir(outputDir, { recursive: true });
      const outputPath = path.join(
        outputDir,
        `${String(index + 1).padStart(2, "0")}-${safeFilename(
          headerFilename ?? attachmentTitle,
        )}${hasExtension(headerFilename ?? attachmentTitle) ? "" : `.${fileExtension}`}`,
      );
      await writeFile(outputPath, bytes);

      rows.push({
        ...baseRow,
        fetchedAt: new Date().toISOString(),
        rawPath: toRepoRelative(outputPath, options.repoRoot),
        sha256: sha256(bytes),
        bytes: bytes.length,
        contentType,
        status: "downloaded",
      });
    } catch (error) {
      rows.push({
        ...baseRow,
        fetchedAt: new Date().toISOString(),
        status: "download_failed",
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return rows;
}

function parseListPage(
  html: string,
  query: string,
  page: number,
  listUrl: string,
): ListPostCandidate[] {
  return [...html.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)]
    .map((match) => match[0] ?? "")
    .map((row): ListPostCandidate | null => {
      const hrefMatch = row.match(
        /<a\b[^>]*href=(["'])(?<href>[^"']*?at=view&idx=(?<idx>\d+)[^"']*)\1[^>]*>(?<title>[\s\S]*?)<\/a>/i,
      );
      const idx = hrefMatch?.groups?.idx;
      const href = hrefMatch?.groups?.href;
      const titleHtml = hrefMatch?.groups?.title;
      if (!idx || !href || !titleHtml) return null;

      const title = cleanTitle(htmlToText(titleHtml));
      if (!isRelevantAdmissionsTitle(title)) return null;

      const cells = [...row.matchAll(/<td\b[^>]*class=(["'])(?<klass>[^"']+)\1[^>]*>(?<text>[\s\S]*?)<\/td>/gi)];
      const writer = cellText(cells, "news_writer");
      const postedDate = cellText(cells, "news_date");
      const viewCount = numberFromText(cellText(cells, "news_count"));

      return {
        query,
        page,
        listUrl,
        idx,
        title,
        postedDate,
        writer,
        viewCount,
        viewUrl: resolveUrl(href),
      };
    })
    .filter((candidate): candidate is ListPostCandidate => candidate !== null);
}

function parseAttachments(
  html: string,
  viewUrl: string,
): { title: string; sourceUrl: string }[] {
  const rows = [...html.matchAll(/<a\b[^>]*href=(["'])(?<href>[^"']*?at=download[^"']*)\1[^>]*>(?<text>[\s\S]*?)<\/a>/gi)]
    .map((match) => {
      const href = match.groups?.href;
      const text = match.groups?.text;
      if (!href || !text) return null;
      return {
        title: cleanAttachmentTitle(htmlToText(text)),
        sourceUrl: new URL(href, viewUrl).toString(),
      };
    })
    .filter((row): row is { title: string; sourceUrl: string } => row !== null);

  const seen = new Set<string>();
  return rows.filter((row) => {
    const key = `${row.sourceUrl}|${row.title}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function parseEmbeddedPdfUrls(html: string): string[] {
  const urls = [...html.matchAll(/<iframe\b[^>]*\bsrc=(["'])(?<src>[^"']+\.pdf[^"']*)\1/gi)]
    .map((match) => match.groups?.src)
    .filter((src): src is string => Boolean(src))
    .map((src) => resolveUrl(src));
  return [...new Set(urls)];
}

function parseViewTitle(html: string): string | null {
  return htmlToText(
    html.match(/<span\b[^>]*class=(["'])subject-name\1[^>]*>(?<title>[\s\S]*?)<\/span>/i)
      ?.groups?.title,
  );
}

function parseViewField(html: string, label: string): string | null {
  const pattern = new RegExp(
    `<li\\b[^>]*>[\\s\\S]*?<span\\b[^>]*class=(["'])title\\1[^>]*>\\s*${escapeRegex(
      label,
    )}\\s*<\\/span>[\\s\\S]*?<p\\b[^>]*class=(["'])text\\2[^>]*>(?<value>[\\s\\S]*?)<\\/p>[\\s\\S]*?<\\/li>`,
    "i",
  );
  const value = html.match(pattern)?.groups?.value;
  const text = htmlToText(value);
  return text || null;
}

function parseBodyTextPreview(html: string): string {
  const body = html.match(/<div\b[^>]*class=(["'])text-box\1[^>]*>(?<body>[\s\S]*?)<iframe\b/i)
    ?.groups?.body;
  const fallback = html.match(/<div\b[^>]*class=(["'])text-box\1[^>]*>(?<body>[\s\S]*?)<\/div>/i)
    ?.groups?.body;
  return normalizeSpace(htmlToText(body ?? fallback ?? "")).slice(0, 2000);
}

function buildListUrl(query: string, page: number): string {
  const params = new URLSearchParams({
    pagenumber: String(page),
    sn: "s1",
    st: query,
  });
  return `${BASE_URL}${BOARD_PATH}?${params.toString()}`;
}

async function fetchText(url: string): Promise<string> {
  const response = await fetch(url, {
    headers: { "User-Agent": USER_AGENT },
  });
  if (!response.ok) throw new Error(`fetch failed ${response.status} ${url}`);
  return response.text();
}

async function writeRawListPage(
  rawDir: string,
  query: string,
  page: number,
  html: string,
) {
  const queryDir = path.join(rawDir, "list-pages");
  await mkdir(queryDir, { recursive: true });
  await writeFile(path.join(queryDir, `${safeFilename(query)}-page-${page}.html`), html);
}

function maxPaginationPage(html: string): number | null {
  const pages = [...html.matchAll(/javascript:goPage\((?<page>\d+)\)/g)]
    .map((match) => Number(match.groups?.page))
    .filter((value) => Number.isFinite(value));
  return pages.length > 0 ? Math.max(...pages) : null;
}

function isWithinPostedYear(candidateDate: string | null, options: Options): boolean {
  const year = postedYearFromDate(candidateDate);
  if (year === null) return true;
  return year >= options.minPostedYear && year <= options.maxPostedYear;
}

function isRelevantAdmissionsTitle(title: string): boolean {
  return /(대학입학전형|대입전형|정시모집|수시모집|공통원서|대입상담|입시|입학전형)/.test(
    compactText(title),
  );
}

function postRoleFromTitle(title: string): PostRole {
  const compact = compactText(title);
  if (compact.includes("대학입학전형시행계획")) return "implementation_plan";
  if (compact.includes("기본사항")) return "admission_policy_basics";
  if (compact.includes("정시모집") && /집중상담|상담/.test(compact)) {
    return "regular_admission_counseling";
  }
  if (compact.includes("정시모집")) return "regular_admission_application";
  if (compact.includes("수시모집") && /집중상담|상담/.test(compact)) {
    return "early_admission_counseling";
  }
  if (compact.includes("수시모집")) return "early_admission_application";
  if (compact.includes("대입상담")) return "admission_consulting";
  if (compact.includes("대입정보포털")) return "admission_info_portal";
  return "other_admissions_press";
}

function attachmentRoleFromTitle(
  title: string,
  postRole: PostRole,
): AttachmentRole {
  const extension = extensionFromTitle(title);
  if (postRole === "implementation_plan" && title.includes("주요사항")) {
    return extension === "pdf"
      ? "implementation_plan_key_points_pdf"
      : "implementation_plan_key_points_hwp";
  }
  if (postRole === "implementation_plan") {
    return extension === "pdf"
      ? "implementation_plan_press_pdf"
      : "implementation_plan_press_hwp";
  }
  if (postRole === "admission_policy_basics") {
    return extension === "pdf" ? "admission_policy_basics_pdf" : "admission_policy_basics_hwp";
  }
  if (postRole === "regular_admission_counseling") return "regular_admission_counseling_press";
  if (postRole === "regular_admission_application") return "regular_admission_application_press";
  if (postRole === "early_admission_counseling") return "early_admission_counseling_press";
  if (postRole === "early_admission_application") return "early_admission_application_press";
  if (postRole === "admission_consulting") return "admission_consulting_press";
  return "admission_press_other";
}

function academicYearFromText(text: string): number | null {
  const match = text.match(/(?<year>20\d{2})학년도/);
  return match?.groups?.year ? Number(match.groups.year) : null;
}

function postedYearFromDate(value: string | null): number | null {
  const year = value?.match(/^(?<year>20\d{2})-/)?.groups?.year;
  return year ? Number(year) : null;
}

function extensionFromTitle(title: string): string {
  const matches = [...title.matchAll(/\.([a-z][a-z0-9]{1,5})(?:\s|\)|$)/gi)];
  return matches.at(-1)?.[1]?.toLowerCase() ?? "";
}

function extensionFromContentType(contentType: string | null): string {
  if (!contentType) return "";
  if (contentType.includes("pdf")) return "pdf";
  if (contentType.includes("hwp")) return "hwp";
  if (contentType.includes("msword")) return "doc";
  if (contentType.includes("spreadsheet")) return "xlsx";
  if (contentType.includes("zip")) return "zip";
  return "";
}

function extensionFromMagicBytes(bytes: Buffer): string {
  if (bytes.subarray(0, 4).toString("latin1") === "%PDF") return "pdf";
  if (bytes.subarray(0, 8).toString("hex") === "d0cf11e0a1b11ae1") return "hwp";
  if (bytes.subarray(0, 4).toString("hex") === "504b0304") return "zip";
  return "";
}

function hasExtension(value: string): boolean {
  return /\.[a-z0-9]{2,5}$/i.test(value);
}

function cellText(
  cells: RegExpMatchArray[],
  className: string,
): string | null {
  const cell = cells.find((match) => match.groups?.klass?.split(/\s+/).includes(className));
  const text = htmlToText(cell?.groups?.text);
  return text || null;
}

function compareListCandidates(a: ListPostCandidate, b: ListPostCandidate): number {
  return (
    (b.postedDate ?? "").localeCompare(a.postedDate ?? "") ||
    a.query.localeCompare(b.query) ||
    a.page - b.page
  );
}

function comparePosts(a: PressPost, b: PressPost): number {
  return (
    (b.postedDate ?? "").localeCompare(a.postedDate ?? "") ||
    (b.academicYear ?? 0) - (a.academicYear ?? 0) ||
    a.title.localeCompare(b.title)
  );
}

function compareAttachments(a: PressAttachment, b: PressAttachment): number {
  return (
    (b.postedDate ?? "").localeCompare(a.postedDate ?? "") ||
    a.idx.localeCompare(b.idx) ||
    a.attachmentIndex - b.attachmentIndex
  );
}

function contentDispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const encoded = header.match(/filename\*?=(?:UTF-8'')?(?<name>[^;]+)/i)?.groups?.name;
  if (!encoded) return null;

  const withoutQuotes = encoded.trim().replace(/^"|"$/g, "");
  try {
    return decodeURIComponent(withoutQuotes);
  } catch {
    return withoutQuotes;
  }
}

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: process.cwd(),
    rawDir: DEFAULT_RAW_DIR,
    publicDir: DEFAULT_PUBLIC_DIR,
    queries: DEFAULT_QUERIES,
    maxPages: DEFAULT_MAX_PAGES,
    minPostedYear: DEFAULT_MIN_POSTED_YEAR,
    maxPostedYear: DEFAULT_MAX_POSTED_YEAR,
    download: true,
    delayMs: 75,
  };

  for (const arg of args) {
    if (arg === "--") continue;
    if (arg.startsWith("--raw-dir=")) {
      options.rawDir = arg.slice("--raw-dir=".length);
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--queries=")) {
      options.queries = parseStringList(arg.slice("--queries=".length));
    } else if (arg.startsWith("--max-pages=")) {
      options.maxPages = Number(arg.slice("--max-pages=".length));
    } else if (arg.startsWith("--min-posted-year=")) {
      options.minPostedYear = Number(arg.slice("--min-posted-year=".length));
    } else if (arg.startsWith("--max-posted-year=")) {
      options.maxPostedYear = Number(arg.slice("--max-posted-year=".length));
    } else if (arg.startsWith("--delay-ms=")) {
      options.delayMs = Number(arg.slice("--delay-ms=".length));
    } else if (arg === "--no-download") {
      options.download = false;
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

function parseStringList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
}

function resolveUrl(value: string): string {
  return new URL(value, BASE_URL).toString();
}

function safeFilename(value: string): string {
  const cleaned = value
    .replace(/[^\w.()\-가-힣]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
  return cleaned.slice(0, 180) || "attachment";
}

function cleanTitle(value: string): string {
  return normalizeSpace(value.replace(/\bnew\b/gi, ""));
}

function cleanAttachmentTitle(value: string): string {
  return normalizeSpace(value.replace(/^\s*첨부파일\s*/g, ""));
}

function htmlToText(html: string | undefined): string {
  return decodeHtmlEntities(
    (html ?? "")
      .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
      .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
      .replace(/<br\s*\/?>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  );
}

function decodeHtmlEntities(value: string): string {
  return value
    .replace(/&#(?<code>\d+);/g, (_, code: string) => String.fromCharCode(Number(code)))
    .replace(/&#x(?<code>[a-f0-9]+);/gi, (_, code: string) =>
      String.fromCharCode(Number.parseInt(code, 16)),
    )
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&nbsp;", " ")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">");
}

function normalizeSpace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function compactText(value: string): string {
  return value.replace(/\s+/g, "");
}

function numberFromText(value: string | null): number | null {
  if (!value) return null;
  const normalized = value.replace(/[^\d]/g, "");
  return normalized ? Number(normalized) : null;
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function writeJsonl<T>(filePath: string, rows: T[]) {
  await writeFile(filePath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

async function writeReadme(publicDir: string) {
  const text = `# KCUE Admissions Press Public Manifests

한국대학교육협의회 보도자료 중 대입전형/정시/수시/공통원서/상담 관련 원문 수집 manifest.

Raw list/view HTML and downloaded attachments are stored under \`.reference-data/raw/kcue-admissions-press/\` and are not committed.

## Files

- \`kcue_admissions_press_posts_manifest.jsonl\`: one row per fetched KCUE admissions-related press post.
- \`kcue_admissions_press_attachment_manifest.jsonl\`: one row per downloaded or listed press attachment.
- \`kcue_admissions_press_summary.json\`: latest collection summary.

These rows are source-preserving candidates. Promotion to AdmissionSchedule, AdmissionRule, or service copy requires source review.
`;
  await writeFile(path.join(publicDir, "README.md"), text, "utf8");
}

function summarize(
  posts: PressPost[],
  attachments: PressAttachment[],
  options: Options,
) {
  return {
    provider: "kcue",
    generatedAt: new Date().toISOString(),
    source: `${BASE_URL}${BOARD_PATH}`,
    queries: options.queries,
    minPostedYear: options.minPostedYear,
    maxPostedYear: options.maxPostedYear,
    posts: posts.length,
    postsFetched: posts.filter((row) => row.status === "view_fetched").length,
    postFetchFailures: posts.filter((row) => row.status === "view_fetch_failed").length,
    attachments: attachments.length,
    downloaded: attachments.filter((row) => row.status === "downloaded").length,
    downloadFailed: attachments.filter((row) => row.status === "download_failed").length,
    listedOnly: attachments.filter((row) => row.status === "listed").length,
    bytes: attachments.reduce((sum, row) => sum + (row.bytes ?? 0), 0),
    uniqueAttachmentSha256: new Set(
      attachments.map((row) => row.sha256).filter((value): value is string => Boolean(value)),
    ).size,
    byPostedYear: countBy(posts, (row) => row.postedYear ?? "unknown"),
    byAcademicYear: countBy(posts, (row) => row.academicYear ?? "unknown"),
    byPostRole: countBy(posts, (row) => row.postRole),
    byAttachmentRole: countBy(attachments, (row) => row.attachmentRole),
    byExpectedExtension: countBy(attachments, (row) => row.expectedExtension || "unknown"),
    byAttachmentStatus: countBy(attachments, (row) => row.status),
    notes: [
      "KCUE press posts are title-search results for admissions-related keywords.",
      "Attachments are downloaded through the official KCUE at=download route when available.",
      "Rows are source-preserving candidates, not verified production AdmissionRule or HistoricalOutcome records.",
    ],
  };
}

function countBy<T>(rows: T[], getValue: (row: T) => string | number): { value: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const value = String(getValue(row));
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([value, count]) => ({ value, count }));
}

function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
