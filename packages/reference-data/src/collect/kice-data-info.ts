import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const BASE_URL = "https://data.kice.re.kr";
const DEFAULT_RAW_DIR = ".reference-data/raw/kice-data-info";
const DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/kice";
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+manual admin-curated use; public data-info only)";

type Options = {
  repoRoot: string;
  rawDir: string;
  publicDir: string;
  pageSize: number;
  maxPages: number;
  query: RegExp;
  downloadAttachments: boolean;
};

type DataInfoItem = {
  seq: number;
  title: string;
  content?: string;
  createdAt?: string;
  updatedAt?: string;
  attachments?: Attachment[];
};

type Attachment = {
  seq: number;
  hash: string;
  originalFname: string;
  fileSize: number;
  mimeType: string;
  url: string;
};

type ManifestRow = {
  provider: "kice-data-info";
  artifactType: "data_info_attachment";
  seq: number;
  title: string;
  createdAt: string | null;
  updatedAt: string | null;
  attachmentSeq: number;
  originalFname: string;
  mimeType: string;
  fileSize: number;
  sourceUrl: string;
  fetchedAt: string;
  rawPath: string | null;
  sha256: string | null;
  status: "listed" | "downloaded" | "download_failed";
  error?: string;
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  const rows: ManifestRow[] = [];

  for (let page = 1; page <= options.maxPages; page++) {
    const list = await fetchJson<{ data?: DataInfoItem[] }>(
      `${BASE_URL}/api/data-info/list?page=${page}&pageSize=${options.pageSize}`,
    );
    const items = list.data ?? [];
    await writeFile(
      path.join(options.rawDir, `data-info-page-${page}.json`),
      `${JSON.stringify(list, null, 2)}\n`,
    );
    if (items.length === 0) break;

    for (const item of items) {
      if (!options.query.test(item.title)) continue;
      for (const attachment of item.attachments ?? []) {
        rows.push(await collectAttachment(item, attachment, options));
      }
    }
  }

  await writeJsonl(path.join(options.publicDir, "kice_data_info_manifest.jsonl"), rows);
  await writeFile(
    path.join(options.publicDir, "kice_data_info_summary.json"),
    `${JSON.stringify(summarize(rows), null, 2)}\n`,
  );

  console.log(
    [
      "kice data-info collection complete.",
      `attachments=${rows.length}`,
      `downloaded=${rows.filter((row) => row.status === "downloaded").length}`,
      `failed=${rows.filter((row) => row.status === "download_failed").length}`,
    ].join(" "),
  );
}

async function collectAttachment(
  item: DataInfoItem,
  attachment: Attachment,
  options: Options,
): Promise<ManifestRow> {
  const sourceUrl = toAbsoluteUrl(attachment.url);
  const fetchedAt = new Date().toISOString();
  const safeName = attachment.originalFname.replace(/[^\w.-가-힣]+/g, "_");
  const outputDir = path.join(options.rawDir, String(item.seq));
  const outputPath = path.join(outputDir, `${attachment.hash}-${safeName}`);

  if (!options.downloadAttachments) {
    return baseRow(item, attachment, sourceUrl, fetchedAt, null, null, "listed");
  }

  try {
    await mkdir(outputDir, { recursive: true });
    const response = await fetch(sourceUrl, { headers: { "User-Agent": USER_AGENT } });
    if (!response.ok) throw new Error(`download failed ${response.status}`);

    const bytes = Buffer.from(await response.arrayBuffer());
    await writeFile(outputPath, bytes);
    return baseRow(
      item,
      attachment,
      sourceUrl,
      fetchedAt,
      toRepoRelative(outputPath, options.repoRoot),
      sha256(bytes),
      "downloaded",
    );
  } catch (error) {
    return {
      ...baseRow(item, attachment, sourceUrl, fetchedAt, null, null, "download_failed"),
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function baseRow(
  item: DataInfoItem,
  attachment: Attachment,
  sourceUrl: string,
  fetchedAt: string,
  rawPath: string | null,
  hash: string | null,
  status: ManifestRow["status"],
): ManifestRow {
  return {
    provider: "kice-data-info",
    artifactType: "data_info_attachment",
    seq: item.seq,
    title: item.title,
    createdAt: item.createdAt ?? null,
    updatedAt: item.updatedAt ?? null,
    attachmentSeq: attachment.seq,
    originalFname: attachment.originalFname,
    mimeType: attachment.mimeType,
    fileSize: attachment.fileSize,
    sourceUrl,
    fetchedAt,
    rawPath,
    sha256: hash,
    status,
  };
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
  if (!response.ok) throw new Error(`fetch failed ${response.status} ${url}`);
  return response.json() as Promise<T>;
}

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: process.cwd(),
    rawDir: DEFAULT_RAW_DIR,
    publicDir: DEFAULT_PUBLIC_DIR,
    pageSize: 100,
    maxPages: 10,
    query: /대학수학능력시험|모의평가|채점 결과/,
    downloadAttachments: true,
  };

  for (const arg of args) {
    if (arg === "--") continue;
    if (arg.startsWith("--raw-dir=")) {
      options.rawDir = arg.slice("--raw-dir=".length);
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--page-size=")) {
      options.pageSize = Number(arg.slice("--page-size=".length));
    } else if (arg.startsWith("--max-pages=")) {
      options.maxPages = Number(arg.slice("--max-pages=".length));
    } else if (arg.startsWith("--query=")) {
      options.query = new RegExp(arg.slice("--query=".length));
    } else if (arg === "--no-download") {
      options.downloadAttachments = false;
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

function toAbsoluteUrl(url: string): string {
  return url.startsWith("http") ? url : `${BASE_URL}${url}`;
}

function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

async function writeJsonl(filePath: string, rows: ManifestRow[]) {
  await writeFile(filePath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

function summarize(rows: ManifestRow[]) {
  return {
    provider: "kice-data-info",
    generatedAt: new Date().toISOString(),
    attachments: rows.length,
    downloaded: rows.filter((row) => row.status === "downloaded").length,
    downloadFailed: rows.filter((row) => row.status === "download_failed").length,
    listed: rows.filter((row) => row.status === "listed").length,
    bytes: rows.reduce((sum, row) => sum + row.fileSize, 0),
    titles: [...new Set(rows.map((row) => row.title))],
  };
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
