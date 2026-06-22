import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE_URL = "https://www.suneung.re.kr";
const BOARD_ID = "1500230";
const MENU_ID = "0302";
const SITE_ID = "suneung";
const DEFAULT_RAW_DIR = ".reference-data/raw/kice-suneung-press";
const DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/kice";
const DEFAULT_QUERIES = ["채점 결과", "모의평가 채점"];
const DEFAULT_MAX_PAGES = 5;
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+official KICE suneung press pages)";

type ExamType = "csat" | "june_mock" | "september_mock" | "other";

type Options = {
  repoRoot: string;
  rawDir: string;
  publicDir: string;
  queries: string[];
  maxPages: number;
  download: boolean;
};

type PressPost = {
  provider: "kice-suneung";
  artifactType: "suneung_press_post";
  query: string;
  page: number;
  boardID: string;
  boardSeq: string;
  title: string;
  academicYear: number | null;
  examType: ExamType;
  postedDate: string | null;
  listUrl: string;
  viewUrl: string;
  files: PressFile[];
};

type PressFile = {
  fileSeq: string;
  fileTitle: string;
  fileKind: FileKind;
  sourceUrl: string;
};

type FileKind =
  | "press_hwp"
  | "grade_cut_standard_score_xlsx"
  | "standard_score_distribution_xlsx"
  | "absolute_grade_cut_xlsx"
  | "other";

type ManifestRow = {
  provider: "kice-suneung";
  artifactType: "suneung_press_attachment";
  boardID: string;
  boardSeq: string;
  title: string;
  academicYear: number | null;
  examType: ExamType;
  postedDate: string | null;
  fileSeq: string;
  fileTitle: string;
  fileKind: FileKind;
  sourceUrl: string;
  viewUrl: string;
  listedAt: string;
  fetchedAt: string | null;
  rawPath: string | null;
  sha256: string | null;
  bytes: number | null;
  contentType: string | null;
  status: "listed" | "downloaded" | "download_failed";
  error?: string;
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  const postsBySeq = new Map<string, PressPost>();

  for (const query of options.queries) {
    for (let page = 1; page <= options.maxPages; page += 1) {
      const listUrl = buildListUrl(query, page);
      const html = await fetchText(listUrl);
      await writeRawListPage(options.rawDir, query, page, html);

      const posts = parseListPage(html, query, page, listUrl);
      for (const post of posts) {
        const existing = postsBySeq.get(post.boardSeq);
        if (!existing) {
          postsBySeq.set(post.boardSeq, post);
        } else {
          existing.files = dedupeFiles([...existing.files, ...post.files]);
        }
      }

      if (posts.length === 0 && page > 1) break;
    }
  }

  const posts = [...postsBySeq.values()].sort(comparePosts);
  const rows: ManifestRow[] = [];

  for (const post of posts) {
    for (const file of post.files) {
      rows.push(await collectFile(post, file, options));
    }
  }

  await writeJsonl(
    path.join(options.publicDir, "kice_suneung_press_manifest.jsonl"),
    rows,
  );
  await writeFile(
    path.join(options.publicDir, "kice_suneung_press_summary.json"),
    `${JSON.stringify(summarize(rows), null, 2)}\n`,
  );

  console.log(
    [
      "kice suneung press collection complete.",
      `posts=${posts.length}`,
      `attachments=${rows.length}`,
      `downloaded=${rows.filter((row) => row.status === "downloaded").length}`,
      `failed=${rows.filter((row) => row.status === "download_failed").length}`,
    ].join(" "),
  );
}

async function collectFile(
  post: PressPost,
  file: PressFile,
  options: Options,
): Promise<ManifestRow> {
  const listedAt = new Date().toISOString();

  if (!options.download) {
    return baseRow(post, file, listedAt, null, null, null, null, null, "listed");
  }

  const rawDir = path.join(
    options.rawDir,
    String(post.academicYear ?? "unknown"),
    post.examType,
  );
  await mkdir(rawDir, { recursive: true });

  try {
    const response = await fetch(file.sourceUrl, {
      headers: { "User-Agent": USER_AGENT },
    });
    if (!response.ok) throw new Error(`download failed ${response.status}`);

    const bytes = Buffer.from(await response.arrayBuffer());
    if (bytes.length === 0) throw new Error("downloaded empty file");

    const contentType = response.headers.get("content-type");
    const filename =
      contentDispositionFilename(response.headers.get("content-disposition")) ??
      file.fileTitle;
    const outputPath = path.join(
      rawDir,
      `${file.fileSeq}-${safeFilename(filename)}`,
    );
    await writeFile(outputPath, bytes);

    return baseRow(
      post,
      file,
      listedAt,
      new Date().toISOString(),
      toRepoRelative(outputPath, options.repoRoot),
      sha256(bytes),
      bytes.length,
      contentType,
      "downloaded",
    );
  } catch (error) {
    return {
      ...baseRow(
        post,
        file,
        listedAt,
        new Date().toISOString(),
        null,
        null,
        null,
        null,
        "download_failed",
      ),
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function baseRow(
  post: PressPost,
  file: PressFile,
  listedAt: string,
  fetchedAt: string | null,
  rawPath: string | null,
  hash: string | null,
  bytes: number | null,
  contentType: string | null,
  status: ManifestRow["status"],
): ManifestRow {
  return {
    provider: "kice-suneung",
    artifactType: "suneung_press_attachment",
    boardID: post.boardID,
    boardSeq: post.boardSeq,
    title: post.title,
    academicYear: post.academicYear,
    examType: post.examType,
    postedDate: post.postedDate,
    fileSeq: file.fileSeq,
    fileTitle: file.fileTitle,
    fileKind: file.fileKind,
    sourceUrl: file.sourceUrl,
    viewUrl: post.viewUrl,
    listedAt,
    fetchedAt,
    rawPath,
    sha256: hash,
    bytes,
    contentType,
    status,
  };
}

function parseListPage(
  html: string,
  query: string,
  page: number,
  listUrl: string,
): PressPost[] {
  const rows = [...html.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)].map(
    (match) => match[0] ?? "",
  );
  const posts: PressPost[] = [];

  for (const row of rows) {
    if (!row.includes("goView(") || !row.includes("fn_fileDown(")) continue;

    const viewMatch = row.match(
      /goView\('(?<boardID>\d+)','(?<boardSeq>\d+)'[^)]*\)/,
    );
    const boardID = viewMatch?.groups?.boardID;
    const boardSeq = viewMatch?.groups?.boardSeq;
    if (!boardID || !boardSeq) continue;

    const title =
      decodeHtmlEntities(row.match(/<a\b[^>]*\btitle="(?<title>[^"]+)"/)?.groups?.title)
        ?.trim() ?? titleFromRow(row);
    if (!isScoreResultTitle(title)) continue;

    const postedDate = row.match(/<td>(?<date>\d{4}-\d{2}-\d{2})<\/td>/)?.groups
      ?.date ?? null;
    const files = parseFiles(row);
    if (files.length === 0) continue;

    posts.push({
      provider: "kice-suneung",
      artifactType: "suneung_press_post",
      query,
      page,
      boardID,
      boardSeq,
      title,
      academicYear: academicYearFromTitle(title),
      examType: examTypeFromTitle(title),
      postedDate,
      listUrl,
      viewUrl: `${BASE_URL}/boardCnts/view.do?boardID=${boardID}&boardSeq=${boardSeq}&m=${MENU_ID}&s=${SITE_ID}`,
      files,
    });
  }

  return posts;
}

function parseFiles(rowHtml: string): PressFile[] {
  const fileMatches = [
    ...rowHtml.matchAll(
      /fn_fileDown\('(?<fileSeq>[a-f0-9]+)'\);"\s+title='(?<title>[^']+)'/gi,
    ),
  ];

  return fileMatches
    .map((match) => {
      const fileSeq = match.groups?.fileSeq;
      const title = match.groups?.title;
      if (!fileSeq || !title) return null;
      const fileTitle = decodeHtmlEntities(title);
      return {
        fileSeq,
        fileTitle,
        fileKind: fileKindFromTitle(fileTitle),
        sourceUrl: `${BASE_URL}/boardCnts/fileDown.do?fileSeq=${fileSeq}`,
      };
    })
    .filter((file): file is PressFile => file !== null);
}

function dedupeFiles(files: PressFile[]): PressFile[] {
  const seen = new Set<string>();
  const result: PressFile[] = [];

  for (const file of files) {
    if (seen.has(file.fileSeq)) continue;
    seen.add(file.fileSeq);
    result.push(file);
  }

  return result;
}

function isScoreResultTitle(title: string): boolean {
  return (
    title.includes("대학수학능력시험") &&
    title.includes("채점") &&
    title.includes("결과") &&
    !title.includes("재채점")
  );
}

function academicYearFromTitle(title: string): number | null {
  const match = title.match(/(?<year>\d{4})학년도/);
  return match?.groups?.year ? Number(match.groups.year) : null;
}

function examTypeFromTitle(title: string): ExamType {
  if (title.includes("6월 모의평가")) return "june_mock";
  if (title.includes("9월 모의평가")) return "september_mock";
  if (title.includes("대학수학능력시험")) return "csat";
  return "other";
}

function fileKindFromTitle(title: string): FileKind {
  const compact = title.replace(/\s+|_/g, "");
  if (/\.hwp$/i.test(title) && /채점결과|보도자료/.test(compact)) return "press_hwp";
  if (compact.includes("등급구분점수절대평가영역")) {
    return "absolute_grade_cut_xlsx";
  }
  if (compact.includes("등급구분표준점수")) return "grade_cut_standard_score_xlsx";
  if (compact.includes("표준점수도수분포") || compact.includes("표준섬수도수분포")) {
    return "standard_score_distribution_xlsx";
  }
  return "other";
}

function titleFromRow(rowHtml: string): string {
  return htmlToText(rowHtml)
    .replace(/\s+/g, " ")
    .trim();
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
  await writeFile(
    path.join(queryDir, `${safeFilename(query)}-page-${page}.html`),
    html,
  );
}

function buildListUrl(query: string, page: number): string {
  const params = new URLSearchParams({
    boardID: BOARD_ID,
    m: MENU_ID,
    s: SITE_ID,
    searchType: "S",
    searchStr: query,
    page: String(page),
  });
  return `${BASE_URL}/boardCnts/list.do?${params.toString()}`;
}

function comparePosts(a: PressPost, b: PressPost): number {
  return (
    (b.academicYear ?? 0) - (a.academicYear ?? 0) ||
    examTypeSort(a.examType) - examTypeSort(b.examType) ||
    (b.postedDate ?? "").localeCompare(a.postedDate ?? "")
  );
}

function examTypeSort(examType: ExamType): number {
  const order: Record<ExamType, number> = {
    csat: 0,
    september_mock: 1,
    june_mock: 2,
    other: 3,
  };
  return order[examType];
}

function contentDispositionFilename(header: string | null): string | null {
  if (!header) return null;
  const encoded = header.match(/filename\*?=(?:UTF-8'')?(?<name>[^;]+)/i)?.groups
    ?.name;
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
    download: true,
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

function safeFilename(value: string): string {
  return value
    .replace(/[^\w.()\-가-힣]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function htmlToText(html: string): string {
  return decodeHtmlEntities(
    html
      .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
      .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
      .replace(/<br\s*\/?>/gi, " ")
      .replace(/<[^>]+>/g, " "),
  )
    .replace(/\s+/g, " ")
    .trim();
}

function decodeHtmlEntities(value: string | undefined): string {
  return (value ?? "")
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&nbsp;", " ")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">");
}

async function writeJsonl<T>(filePath: string, rows: T[]) {
  await writeFile(filePath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

function summarize(rows: ManifestRow[]) {
  const byAcademicYear = new Map<number | "unknown", ManifestRow[]>();
  const byExamType = new Map<ExamType, ManifestRow[]>();

  for (const row of rows) {
    const yearKey = row.academicYear ?? "unknown";
    byAcademicYear.set(yearKey, [...(byAcademicYear.get(yearKey) ?? []), row]);
    byExamType.set(row.examType, [...(byExamType.get(row.examType) ?? []), row]);
  }

  return {
    provider: "kice-suneung",
    generatedAt: new Date().toISOString(),
    posts: new Set(rows.map((row) => row.boardSeq)).size,
    attachments: rows.length,
    downloaded: rows.filter((row) => row.status === "downloaded").length,
    downloadFailed: rows.filter((row) => row.status === "download_failed").length,
    listed: rows.filter((row) => row.status === "listed").length,
    bytes: rows.reduce((sum, row) => sum + (row.bytes ?? 0), 0),
    byAcademicYear: [...byAcademicYear.entries()]
      .sort(([a], [b]) => String(b).localeCompare(String(a)))
      .map(([academicYear, yearRows]) => ({
        academicYear,
        posts: new Set(yearRows.map((row) => row.boardSeq)).size,
        attachments: yearRows.length,
        downloaded: yearRows.filter((row) => row.status === "downloaded").length,
      })),
    byExamType: [...byExamType.entries()].map(([examType, examRows]) => ({
      examType,
      posts: new Set(examRows.map((row) => row.boardSeq)).size,
      attachments: examRows.length,
      downloaded: examRows.filter((row) => row.status === "downloaded").length,
    })),
    byFileKind: summarizeByFileKind(rows),
  };
}

function summarizeByFileKind(rows: ManifestRow[]) {
  const byKind = new Map<FileKind, ManifestRow[]>();
  for (const row of rows) {
    byKind.set(row.fileKind, [...(byKind.get(row.fileKind) ?? []), row]);
  }

  return [...byKind.entries()].map(([fileKind, kindRows]) => ({
    fileKind,
    attachments: kindRows.length,
    downloaded: kindRows.filter((row) => row.status === "downloaded").length,
  }));
}

function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
