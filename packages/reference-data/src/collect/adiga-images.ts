import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/adiga";
const DEFAULT_RAW_DIR = ".reference-data/raw/adiga-images";
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+manual admin-curated use; public pages only)";

type Options = {
  repoRoot: string;
  publicDir: string;
  rawDir: string;
  years: number[] | null;
  limit: number | null;
  delayMs: number;
  force: boolean;
};

type DetailManifest = {
  provider: "adiga";
  artifactType: "university_selection_html";
  year: number;
  unvCd: string;
  universityName: string;
  sourceUrl: string;
  rawPath: string;
  imageUrls: string[];
  status: string;
};

type ImageOccurrence = {
  occurrenceId: string;
  year: number;
  unvCd: string;
  universityName: string;
  detailSourceUrl: string;
  detailRawPath: string;
  imageUrl: string;
  imageUrlSha256: string;
  canonicalImageKey: string;
};

type UniqueImage = {
  provider: "adiga";
  artifactType: "adiga_unique_image";
  imageUrl: string;
  imageUrlSha256: string;
  canonicalImageKey: string;
  urlHost: string;
  urlPathname: string;
  sourceReferenceCount: number;
  years: number[];
  universityCount: number;
  firstYear: number | null;
  firstUnvCd: string;
  firstUniversityName: string;
  fetchedAt: string;
  httpStatus: number | null;
  contentType: string;
  detectedImageKind: string;
  width: number | null;
  height: number | null;
  rawImagePath: string;
  sha256: string;
  bytes: number;
  status: "downloaded" | "reused_existing_file" | "fetch_failed" | "not_image_response";
  error?: string;
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  const detailManifests = await loadDetailManifests(options);
  const occurrences = collectOccurrences(detailManifests);
  const uniqueGroups = groupOccurrencesByUrl(occurrences);
  const selectedGroups =
    options.limit === null ? uniqueGroups : uniqueGroups.slice(0, options.limit);

  const uniqueImages: UniqueImage[] = [];
  for (const [index, group] of selectedGroups.entries()) {
    const uniqueImage = await fetchUniqueImage(group, options);
    uniqueImages.push(uniqueImage);
    console.log(
      [
        `adiga image ${index + 1}/${selectedGroups.length}`,
        `status=${uniqueImage.status}`,
        `bytes=${uniqueImage.bytes}`,
        `kind=${uniqueImage.detectedImageKind || "unknown"}`,
        `refs=${uniqueImage.sourceReferenceCount}`,
        `key=${uniqueImage.canonicalImageKey}`,
      ].join(" "),
    );
    if (options.delayMs > 0 && index < selectedGroups.length - 1) {
      await sleep(options.delayMs);
    }
  }

  const uniqueByUrlHash = new Map(uniqueImages.map((row) => [row.imageUrlSha256, row]));
  const sourceReferences = occurrences
    .filter((row) => uniqueByUrlHash.has(row.imageUrlSha256))
    .map((row) => {
      const image = uniqueByUrlHash.get(row.imageUrlSha256);
      return {
        provider: "adiga",
        artifactType: "adiga_image_source_reference",
        ...row,
        rawImagePath: image?.rawImagePath ?? "",
        imageSha256: image?.sha256 ?? "",
        imageBytes: image?.bytes ?? 0,
        detectedImageKind: image?.detectedImageKind ?? "",
        width: image?.width ?? null,
        height: image?.height ?? null,
        downloadStatus: image?.status ?? "fetch_failed",
      };
    });

  await writeJsonl(path.join(options.publicDir, "adiga_unique_image_manifest.jsonl"), uniqueImages);
  await writeJsonl(
    path.join(options.publicDir, "adiga_image_source_references.jsonl"),
    sourceReferences,
  );
  await writeCsv(
    path.join(options.publicDir, "adiga_image_source_references.csv"),
    sourceReferences,
    [
      "year",
      "unvCd",
      "universityName",
      "canonicalImageKey",
      "detectedImageKind",
      "width",
      "height",
      "imageBytes",
      "downloadStatus",
      "rawImagePath",
      "detailRawPath",
      "imageUrl",
    ],
  );

  const summary = summarize(detailManifests, occurrences, uniqueImages, sourceReferences.length);
  await writeFile(
    path.join(options.publicDir, "adiga_image_download_summary.json"),
    `${JSON.stringify(summary, null, 2)}\n`,
  );
}

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: process.cwd(),
    publicDir: DEFAULT_PUBLIC_DIR,
    rawDir: DEFAULT_RAW_DIR,
    years: null,
    limit: null,
    delayMs: 50,
    force: false,
  };

  for (const arg of args) {
    if (arg === "--") continue;
    if (arg.startsWith("--years=")) {
      options.years = parseNumberList(arg.slice("--years=".length));
    } else if (arg.startsWith("--limit=")) {
      options.limit = Number(arg.slice("--limit=".length));
    } else if (arg.startsWith("--delay-ms=")) {
      options.delayMs = Number(arg.slice("--delay-ms=".length));
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--raw-dir=")) {
      options.rawDir = arg.slice("--raw-dir=".length);
    } else if (arg === "--force") {
      options.force = true;
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
    publicDir: resolveFromRoot(repoRoot, options.publicDir),
    rawDir: resolveFromRoot(repoRoot, options.rawDir),
  };
}

async function loadDetailManifests(options: Options): Promise<DetailManifest[]> {
  const files = (await readdir(options.publicDir))
    .filter((file) => /^adiga_selection_manifest_\d{4}\.jsonl$/.test(file))
    .filter((file) => {
      if (!options.years) return true;
      const year = Number(file.match(/(\d{4})/)?.[1] ?? 0);
      return options.years.includes(year);
    })
    .sort();
  const rows: DetailManifest[] = [];
  for (const file of files) {
    const content = await readFile(path.join(options.publicDir, file), "utf8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed) continue;
      rows.push(JSON.parse(trimmed) as DetailManifest);
    }
  }
  return rows;
}

function collectOccurrences(detailRows: DetailManifest[]): ImageOccurrence[] {
  const occurrences: ImageOccurrence[] = [];
  for (const detail of detailRows) {
    if (detail.status !== "fetched") continue;
    for (const [imageIndex, imageUrl] of (detail.imageUrls ?? []).entries()) {
      if (!isUsableImageUrl(imageUrl)) continue;
      const imageUrlSha256 = sha256(imageUrl);
      const canonicalImageKey = canonicalImageKeyFor(imageUrl);
      occurrences.push({
        occurrenceId: sha256(
          [detail.year, detail.unvCd, detail.rawPath, imageIndex, imageUrl].join("|"),
        ),
        year: detail.year,
        unvCd: detail.unvCd,
        universityName: detail.universityName,
        detailSourceUrl: detail.sourceUrl,
        detailRawPath: detail.rawPath,
        imageUrl,
        imageUrlSha256,
        canonicalImageKey,
      });
    }
  }
  return occurrences;
}

function groupOccurrencesByUrl(occurrences: ImageOccurrence[]): ImageOccurrence[][] {
  const groups = new Map<string, ImageOccurrence[]>();
  for (const occurrence of occurrences) {
    const group = groups.get(occurrence.imageUrl) ?? [];
    group.push(occurrence);
    groups.set(occurrence.imageUrl, group);
  }
  return [...groups.values()].sort((left, right) => {
    const leftFirst = firstOccurrence(left);
    const rightFirst = firstOccurrence(right);
    return (
      leftFirst.year - rightFirst.year ||
      leftFirst.canonicalImageKey.localeCompare(rightFirst.canonicalImageKey) ||
      leftFirst.imageUrl.localeCompare(rightFirst.imageUrl)
    );
  });
}

async function fetchUniqueImage(group: ImageOccurrence[], options: Options): Promise<UniqueImage> {
  const first = firstOccurrence(group);
  const url = new URL(first.imageUrl);
  const rawPath = path.join(
    options.rawDir,
    rawSubdirFor(first.canonicalImageKey),
    `${safeFilename(first.canonicalImageKey)}_${first.imageUrlSha256.slice(0, 12)}.bin`,
  );
  await mkdir(path.dirname(rawPath), { recursive: true });
  const years = uniqueSorted(group.map((row) => row.year));
  const universityCount = new Set(group.map((row) => `${row.year}:${row.unvCd}`)).size;
  const commonFields = {
    provider: "adiga" as const,
    artifactType: "adiga_unique_image" as const,
    imageUrl: first.imageUrl,
    imageUrlSha256: first.imageUrlSha256,
    canonicalImageKey: first.canonicalImageKey,
    urlHost: url.host,
    urlPathname: url.pathname,
    sourceReferenceCount: group.length,
    years,
    universityCount,
    firstYear: years[0] ?? null,
    firstUnvCd: first.unvCd,
    firstUniversityName: first.universityName,
    fetchedAt: new Date().toISOString(),
  };

  if (!options.force && existsSync(rawPath)) {
    const buffer = await readFile(rawPath);
    const detected = detectImage(buffer, "");
    return {
      ...commonFields,
      httpStatus: null,
      contentType: "",
      detectedImageKind: detected.kind,
      width: detected.width,
      height: detected.height,
      rawImagePath: toRepoRelative(rawPath, options.repoRoot),
      sha256: sha256Buffer(buffer),
      bytes: buffer.length,
      status: "reused_existing_file",
    };
  }

  try {
    const response = await fetch(first.imageUrl, {
      headers: { "User-Agent": USER_AGENT },
    });
    if (!response.ok) {
      return {
        ...commonFields,
        httpStatus: response.status,
        contentType: response.headers.get("content-type") ?? "",
        detectedImageKind: "",
        width: null,
        height: null,
        rawImagePath: "",
        sha256: "",
        bytes: 0,
        status: "fetch_failed",
        error: `HTTP ${response.status}`,
      };
    }

    const buffer = Buffer.from(await response.arrayBuffer());
    const contentType = response.headers.get("content-type") ?? "";
    const detected = detectImage(buffer, contentType);
    if (!detected.kind || detected.kind === "html") {
      return {
        ...commonFields,
        httpStatus: response.status,
        contentType,
        detectedImageKind: detected.kind,
        width: detected.width,
        height: detected.height,
        rawImagePath: "",
        sha256: sha256Buffer(buffer),
        bytes: buffer.length,
        status: "not_image_response",
        error: "Response body is not a recognized image.",
      };
    }

    await writeFile(rawPath, buffer);
    return {
      ...commonFields,
      httpStatus: response.status,
      contentType,
      detectedImageKind: detected.kind,
      width: detected.width,
      height: detected.height,
      rawImagePath: toRepoRelative(rawPath, options.repoRoot),
      sha256: sha256Buffer(buffer),
      bytes: buffer.length,
      status: "downloaded",
    };
  } catch (error) {
    return {
      ...commonFields,
      httpStatus: null,
      contentType: "",
      detectedImageKind: "",
      width: null,
      height: null,
      rawImagePath: "",
      sha256: "",
      bytes: 0,
      status: "fetch_failed",
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function detectImage(buffer: Buffer, contentType: string): { kind: string; width: number | null; height: number | null } {
  if (buffer.length >= 24 && buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
    return {
      kind: "png",
      width: buffer.readUInt32BE(16),
      height: buffer.readUInt32BE(20),
    };
  }
  if (buffer.length >= 10 && buffer.subarray(0, 6).toString("ascii").match(/^GIF8[79]a$/)) {
    return {
      kind: "gif",
      width: buffer.readUInt16LE(6),
      height: buffer.readUInt16LE(8),
    };
  }
  if (buffer.length >= 26 && buffer.subarray(0, 2).toString("ascii") === "BM") {
    return {
      kind: "bmp",
      width: Math.abs(buffer.readInt32LE(18)),
      height: Math.abs(buffer.readInt32LE(22)),
    };
  }
  if (buffer.length >= 4 && buffer[0] === 0xff && buffer[1] === 0xd8) {
    const jpegSize = jpegDimensions(buffer);
    return { kind: "jpeg", width: jpegSize.width, height: jpegSize.height };
  }
  const prefix = buffer.subarray(0, 256).toString("utf8").trimStart().toLowerCase();
  if (prefix.startsWith("<svg")) return { kind: "svg", width: null, height: null };
  if (prefix.startsWith("<!doctype html") || prefix.startsWith("<html")) {
    return { kind: "html", width: null, height: null };
  }
  if (contentType.includes("image/")) {
    return { kind: contentType.split("image/")[1]?.split(";")[0] ?? "image", width: null, height: null };
  }
  return { kind: "", width: null, height: null };
}

function jpegDimensions(buffer: Buffer): { width: number | null; height: number | null } {
  let offset = 2;
  while (offset + 9 < buffer.length) {
    if (buffer[offset] !== 0xff) break;
    const marker = buffer.readUInt8(offset + 1);
    const length = buffer.readUInt16BE(offset + 2);
    if (length < 2) break;
    if (
      marker >= 0xc0 &&
      marker <= 0xcf &&
      ![0xc4, 0xc8, 0xcc].includes(marker)
    ) {
      return {
        height: buffer.readUInt16BE(offset + 5),
        width: buffer.readUInt16BE(offset + 7),
      };
    }
    offset += 2 + length;
  }
  return { width: null, height: null };
}

function canonicalImageKeyFor(imageUrl: string): string {
  const url = new URL(imageUrl);
  const fileId = url.searchParams.get("fileId");
  const fileSn = url.searchParams.get("fileSn");
  if (fileId) return `fileId_${fileId}_fileSn_${fileSn ?? "0"}`;
  const fileInfo = url.searchParams.get("file_info");
  if (fileInfo) return `fileInfo_${fileInfo}`;
  return `url_${sha256(imageUrl).slice(0, 24)}`;
}

function isUsableImageUrl(imageUrl: string): boolean {
  try {
    const url = new URL(imageUrl);
    const fileId = url.searchParams.get("fileId");
    const fileInfo = url.searchParams.get("file_info");
    if (fileId) return /^\d+$/.test(fileId);
    if (fileInfo) return /^[\w.\-가-힣]+$/.test(fileInfo);
    return false;
  } catch {
    return false;
  }
}

function rawSubdirFor(canonicalImageKey: string): string {
  const digest = sha256(canonicalImageKey);
  return path.join(digest.slice(0, 2), digest.slice(2, 4));
}

function summarize(
  detailManifests: DetailManifest[],
  occurrences: ImageOccurrence[],
  uniqueImages: UniqueImage[],
  sourceReferenceRows: number,
) {
  const byYear = new Map<number, { detailRows: number; sourceReferences: number; uniqueImageUrls: Set<string> }>();
  for (const row of detailManifests) {
    const current = byYear.get(row.year) ?? {
      detailRows: 0,
      sourceReferences: 0,
      uniqueImageUrls: new Set<string>(),
    };
    current.detailRows += 1;
    byYear.set(row.year, current);
  }
  for (const occurrence of occurrences) {
    const current = byYear.get(occurrence.year) ?? {
      detailRows: 0,
      sourceReferences: 0,
      uniqueImageUrls: new Set<string>(),
    };
    current.sourceReferences += 1;
    current.uniqueImageUrls.add(occurrence.imageUrl);
    byYear.set(occurrence.year, current);
  }

  return {
    provider: "adiga",
    generatedAt: new Date().toISOString(),
    detailManifestRows: detailManifests.length,
    sourceImageReferences: occurrences.length,
    skippedTemplateLikeImageReferences:
      detailManifests.reduce((sum, row) => sum + (row.imageUrls?.length ?? 0), 0) -
      occurrences.length,
    sourceReferenceRows,
    uniqueImageUrls: uniqueImages.length,
    downloadedUniqueImages: uniqueImages.filter(
      (row) => row.status === "downloaded" || row.status === "reused_existing_file",
    ).length,
    failedUniqueImages: uniqueImages.filter((row) => row.status === "fetch_failed").length,
    notImageResponses: uniqueImages.filter((row) => row.status === "not_image_response").length,
    uniqueContentSha256: new Set(
      uniqueImages.filter((row) => row.sha256).map((row) => row.sha256),
    ).size,
    totalImageBytes: uniqueImages.reduce((sum, row) => sum + row.bytes, 0),
    byStatus: countBy(uniqueImages, "status"),
    byDetectedImageKind: countBy(uniqueImages, "detectedImageKind"),
    byYear: [...byYear.entries()]
      .sort(([left], [right]) => left - right)
      .map(([year, row]) => ({
        year,
        detailRows: row.detailRows,
        sourceReferences: row.sourceReferences,
        uniqueImageUrls: row.uniqueImageUrls.size,
      })),
    notes: [
      "Images are downloaded from image URLs embedded in Adiga selection-detail HTML manifests.",
      "Most repeated images are common guide/icons; source references preserve every university/year occurrence.",
      "Image content is evidence-only and requires OCR or human review before promotion to structured admission data.",
    ],
  };
}

function countBy<T extends Record<string, unknown>>(rows: T[], key: keyof T) {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const value = String(row[key] ?? "");
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .map(([value, count]) => ({ value, count }));
}

async function writeJsonl(filePath: string, rows: unknown[]) {
  await writeFile(filePath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
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
  const text = Array.isArray(value) ? value.join(";") : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function parseNumberList(value: string): number[] {
  return value
    .split(",")
    .map((item) => Number(item.trim()))
    .filter((item) => Number.isFinite(item));
}

function uniqueSorted(values: number[]): number[] {
  return [...new Set(values)].sort((left, right) => left - right);
}

function safeFilename(value: string): string {
  const cleaned = value.replace(/[^\w.()\-가-힣]+/g, "_").replace(/_+/g, "_");
  return cleaned.replace(/^_+|_+$/g, "").slice(0, 140) || "image";
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

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

function sha256Buffer(value: Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

async function sleep(ms: number) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

function firstOccurrence(group: ImageOccurrence[]): ImageOccurrence {
  const first = group[0];
  if (!first) {
    throw new Error("Expected image occurrence group to be non-empty.");
  }
  return first;
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
