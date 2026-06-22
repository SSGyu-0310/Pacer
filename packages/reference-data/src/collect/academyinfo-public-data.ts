import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import { request as httpsRequest } from "node:https";
import path from "node:path";

const BASE_URL = "https://www.academyinfo.go.kr";
const CURRENT_POPUP_PATH = "/popup/main0810/list.do";
const PREVIOUS_POPUP_PATH = "/popup/main0820/list.do?schlDivCd=02&svyYr=";
const DEFAULT_RAW_DIR = ".reference-data/raw/academyinfo-public-data";
const DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/academyinfo";
const DEFAULT_ITEM_DIVS = ["01", "04", "02", "03", "05"];
const DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025];
const USER_AGENT =
  "Pacer reference-data collector/0.1 (+official Academyinfo public data popup)";

type Options = {
  repoRoot: string;
  rawDir: string;
  publicDir: string;
  itemDivs: string[];
  years: number[];
  schlDivCd: string;
  download: boolean;
  delayMs: number;
  maxDownloads: number | null;
};

type JsonRecord = Record<string, unknown>;

type DataListResponse = {
  ajaxList2?: AcademyItem[];
  ajaxList3?: AcademyItem[];
  ajaxList4?: AcademyItem[];
  ajaxList5?: YearAvailability[];
  ajaxList6?: KindAvailability[];
  pramMap?: JsonRecord;
};

type AcademyItem = {
  pgm_id?: string;
  pgm_kor_shrt_nm?: string;
  pgm_estn_nm?: string;
  uppr_pgm_id?: string;
  pgm_clft_cd?: string;
  item_id?: number;
  schl_div_cd?: string;
  dept?: number;
  recursive_level?: string;
  pdf_use_yn?: string | null;
  smry_chrt_yn?: string | null;
  item_smry_nm?: string | null;
  pgm_use_stt_dt?: string;
  pgm_use_end_dt?: string;
};

type YearAvailability = {
  item_id?: number;
  svy_yr?: string;
  schl_div_cd?: string;
  pbnf_bse_dtm?: number;
  pbnf_svc_yn?: string;
  num?: number;
};

type KindAvailability = {
  item_id?: number;
  item_mstr_id?: number;
  schl_div_cd?: string;
  svy_yr?: string;
  acif_dta_rqst_knd_cd?: string;
};

type CatalogRow = {
  provider: "academyinfo";
  artifactType: "academyinfo_public_data_item";
  sourceEndpoint: "main0810";
  itemDivCd: string;
  itemListKey: "ajaxList2" | "ajaxList3" | "ajaxList4";
  itemId: number;
  schoolDivisionCode: string | null;
  programId: string | null;
  parentProgramId: string | null;
  programClassCode: string | null;
  depth: number | null;
  recursiveLevel: string | null;
  programShortName: string;
  programExtendedName: string;
  itemSummaryName: string;
  pdfUseYn: string | null;
  summaryChartYn: string | null;
  programUseStartDate: string | null;
  programUseEndDate: string | null;
  availableSurveyYears: string[];
  currentOutputKindCodes: string[];
  currentOutputKindLabels: string[];
  relevanceRole: RelevanceRole;
  pacerTargets: string[];
  sourceUrl: string;
  collectedAt: string;
};

type RelevantItemRow = CatalogRow & {
  requestedSurveyYears: number[];
  previousOutputKindCodesByYear: Record<string, string[]>;
};

type DownloadManifestRow = {
  provider: "academyinfo";
  artifactType: "academyinfo_public_data_zip";
  itemId: number;
  itemDivCd: string;
  relevanceRole: RelevanceRole;
  pacerTargets: string[];
  surveyYear: number;
  schoolDivisionCode: string;
  outputKindCode: string;
  outputKindLabel: string;
  requestEndpoint: "main0810" | "main0820";
  selectReqListUrl: string;
  selectReqRstUrl: string | null;
  downloadUrl: string | null;
  academyinfoPath: string | null;
  academyinfoFileName: string | null;
  downloadTokenFileName: string | null;
  rawZipPath: string | null;
  sha256: string | null;
  bytes: number | null;
  contentType: string | null;
  contentDisposition: string | null;
  status:
    | "listed"
    | "listed_no_file"
    | "downloaded"
    | "download_skipped"
    | "request_failed"
    | "download_failed";
  error?: string;
  requestedAt: string;
  fetchedAt: string | null;
};

type RelevanceRole =
  | "admission_type_selection_result"
  | "freshman_fill_status"
  | "student_fill_rate"
  | "transfer_selection_result"
  | "dropout_status"
  | "freshman_high_school_type"
  | "admissions_officer_status"
  | "admissions_document_evaluation_load"
  | "admissions_fee_revenue"
  | "admissions_fee_expense"
  | "contract_department_status"
  | "not_admissions_related";

type ReqListItem = {
  colvalue1?: string;
  colvalue2?: number;
  colvalue3?: string;
  colvalue4?: string;
  colvalue12?: string | null;
  colvalue13?: string | null;
  sql_yn?: string;
};

type SelectReqListResponse = {
  resultList1?: ReqListItem[];
  M_CODE?: number;
  M_RTME?: string;
};

type SelectReqRstResponse = {
  resultList?: {
    schlDivCd?: string;
    itemDivCd?: string;
    svyYr?: string;
    all?: string;
    fp?: string;
    fn?: string;
    sn?: string;
    searchValue?: string;
    sel?: string;
    exist?: string | number;
    selFileArr?: string[];
  };
  M_CODE?: number;
  M_RTME?: string;
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.rawDir, { recursive: true });
  await mkdir(options.publicDir, { recursive: true });

  const collectedAt = new Date().toISOString();
  await collectStaticPages(options);
  const currentDataByItemDiv = await collectCurrentDataLists(options);
  const previousDataByYearAndItemDiv = await collectPreviousDataLists(options);
  const catalogRows = buildCatalogRows(currentDataByItemDiv, collectedAt);
  const relevantRows = buildRelevantRows(
    catalogRows,
    previousDataByYearAndItemDiv,
    options.years,
  );

  const manifestRows = await collectDownloads(
    relevantRows,
    currentDataByItemDiv,
    previousDataByYearAndItemDiv,
    options,
  );

  await writeJsonl(
    path.join(options.publicDir, "academyinfo_public_data_item_catalog.jsonl"),
    catalogRows,
  );
  await writeCsv(
    path.join(options.publicDir, "academyinfo_public_data_item_catalog.csv"),
    catalogRows,
    [
      "provider",
      "artifactType",
      "sourceEndpoint",
      "itemDivCd",
      "itemListKey",
      "itemId",
      "schoolDivisionCode",
      "programId",
      "parentProgramId",
      "programClassCode",
      "depth",
      "programShortName",
      "programExtendedName",
      "itemSummaryName",
      "availableSurveyYears",
      "currentOutputKindCodes",
      "currentOutputKindLabels",
      "relevanceRole",
      "pacerTargets",
      "sourceUrl",
      "collectedAt",
    ],
  );
  await writeJsonl(
    path.join(options.publicDir, "academyinfo_admissions_relevant_items.jsonl"),
    relevantRows,
  );
  await writeCsv(
    path.join(options.publicDir, "academyinfo_admissions_relevant_items.csv"),
    relevantRows,
    [
      "itemDivCd",
      "itemId",
      "programExtendedName",
      "itemSummaryName",
      "relevanceRole",
      "pacerTargets",
      "availableSurveyYears",
      "currentOutputKindCodes",
      "currentOutputKindLabels",
      "requestedSurveyYears",
      "previousOutputKindCodesByYear",
      "sourceUrl",
    ],
  );
  await writeJsonl(
    path.join(options.publicDir, "academyinfo_public_data_download_manifest.jsonl"),
    manifestRows,
  );
  await writeCsv(
    path.join(options.publicDir, "academyinfo_public_data_download_manifest.csv"),
    manifestRows,
    [
      "itemId",
      "itemDivCd",
      "relevanceRole",
      "surveyYear",
      "schoolDivisionCode",
      "outputKindCode",
      "outputKindLabel",
      "requestEndpoint",
      "academyinfoPath",
      "academyinfoFileName",
      "downloadTokenFileName",
      "rawZipPath",
      "sha256",
      "bytes",
      "contentType",
      "status",
      "error",
      "requestedAt",
      "fetchedAt",
    ],
  );

  const summary = summarize(
    options,
    catalogRows,
    relevantRows,
    manifestRows,
    currentDataByItemDiv,
    previousDataByYearAndItemDiv,
  );
  await writeFile(
    path.join(options.publicDir, "academyinfo_public_data_summary.json"),
    `${JSON.stringify(summary, null, 2)}\n`,
    "utf8",
  );
  await writeReadme(options.publicDir);

  console.log(
    [
      "academyinfo public data collection complete.",
      `catalogItems=${catalogRows.length}`,
      `relevantItems=${relevantRows.length}`,
      `downloadRows=${manifestRows.length}`,
      `downloaded=${manifestRows.filter((row) => row.status === "downloaded").length}`,
      `failed=${manifestRows.filter((row) => row.status.endsWith("failed")).length}`,
    ].join(" "),
  );
}

async function collectStaticPages(options: Options): Promise<void> {
  const pagesDir = path.join(options.rawDir, "pages");
  await mkdir(pagesDir, { recursive: true });
  const currentHtml = await fetchText(`${BASE_URL}${CURRENT_POPUP_PATH}`);
  await writeFile(path.join(pagesDir, "main0810-list.html"), currentHtml, "utf8");
  const previousHtml = await fetchText(`${BASE_URL}${PREVIOUS_POPUP_PATH}`);
  await writeFile(path.join(pagesDir, "main0820-list.html"), previousHtml, "utf8");
  const ipn = await postFormJson<JsonRecord>("/popup/main0810/selectIPN.do", []);
  await writeFile(path.join(pagesDir, "main0810-selectIPN.json"), jsonText(ipn), "utf8");
}

async function collectCurrentDataLists(
  options: Options,
): Promise<Map<string, DataListResponse>> {
  const rows = new Map<string, DataListResponse>();
  const outputDir = path.join(options.rawDir, "select-data", "main0810");
  await mkdir(outputDir, { recursive: true });

  for (const itemDivCd of options.itemDivs) {
    const response = await postFormJson<DataListResponse>("/popup/main0810/selectDataList.do", [
      ["schlDivCd", options.schlDivCd],
      ["itemDivCd", itemDivCd],
      ["svyYr", ""],
      ["all", ""],
      ["fp", ""],
      ["fn", ""],
      ["sn", ""],
      ["searchValue", ""],
    ]);
    rows.set(itemDivCd, response);
    await writeFile(
      path.join(outputDir, `selectDataList-${itemDivCd}.json`),
      jsonText(response),
      "utf8",
    );
  }

  return rows;
}

async function collectPreviousDataLists(
  options: Options,
): Promise<Map<string, DataListResponse>> {
  const rows = new Map<string, DataListResponse>();
  const previousYears = options.years.filter((year) => year <= 2022);
  if (previousYears.length === 0) return rows;

  const outputDir = path.join(options.rawDir, "select-data", "main0820");
  await mkdir(outputDir, { recursive: true });

  for (const year of previousYears) {
    for (const itemDivCd of options.itemDivs) {
      const response = await postFormJson<DataListResponse>("/popup/main0820/selectDataList.do", [
        ["schlDivCd", options.schlDivCd],
        ["itemDivCd", itemDivCd],
        ["svyYr", String(year)],
        ["searchValue", ""],
      ]);
      rows.set(previousKey(year, itemDivCd), response);
      await writeFile(
        path.join(outputDir, `selectDataList-${itemDivCd}-${year}.json`),
        jsonText(response),
        "utf8",
      );
    }
  }

  return rows;
}

function buildCatalogRows(
  currentDataByItemDiv: Map<string, DataListResponse>,
  collectedAt: string,
): CatalogRow[] {
  const rows: CatalogRow[] = [];
  const seen = new Set<string>();

  for (const [itemDivCd, data] of currentDataByItemDiv) {
    const yearsByItem = groupYears(data.ajaxList5 ?? []);
    const kindsByItem = groupKinds(data.ajaxList6 ?? []);
    for (const itemListKey of ["ajaxList2", "ajaxList3", "ajaxList4"] as const) {
      for (const item of data[itemListKey] ?? []) {
        const itemId = numberValue(item.item_id);
        if (!itemId) continue;
        const key = `${itemDivCd}:${itemListKey}:${itemId}:${item.pgm_id ?? ""}`;
        if (seen.has(key)) continue;
        seen.add(key);
        const labelText = itemLabelText(item);
        const relevanceRole = classifyRelevance(labelText);
        const currentKinds = kindsByItem.get(itemId) ?? [];
        rows.push({
          provider: "academyinfo",
          artifactType: "academyinfo_public_data_item",
          sourceEndpoint: "main0810",
          itemDivCd,
          itemListKey,
          itemId,
          schoolDivisionCode: stringOrNull(item.schl_div_cd),
          programId: stringOrNull(item.pgm_id),
          parentProgramId: stringOrNull(item.uppr_pgm_id),
          programClassCode: stringOrNull(item.pgm_clft_cd),
          depth: numberOrNull(item.dept),
          recursiveLevel: stringOrNull(item.recursive_level),
          programShortName: textValue(item.pgm_kor_shrt_nm),
          programExtendedName: textValue(item.pgm_estn_nm),
          itemSummaryName: textValue(item.item_smry_nm),
          pdfUseYn: stringOrNull(item.pdf_use_yn),
          summaryChartYn: stringOrNull(item.smry_chrt_yn),
          programUseStartDate: stringOrNull(item.pgm_use_stt_dt),
          programUseEndDate: stringOrNull(item.pgm_use_end_dt),
          availableSurveyYears: [...(yearsByItem.get(itemId) ?? [])],
          currentOutputKindCodes: currentKinds,
          currentOutputKindLabels: currentKinds.map(kindLabel),
          relevanceRole,
          pacerTargets: pacerTargetsFor(relevanceRole),
          sourceUrl: `${BASE_URL}${CURRENT_POPUP_PATH}`,
          collectedAt,
        });
      }
    }
  }

  return rows.sort((a, b) => {
    if (a.itemDivCd !== b.itemDivCd) return a.itemDivCd.localeCompare(b.itemDivCd);
    if (a.itemId !== b.itemId) return a.itemId - b.itemId;
    return a.programExtendedName.localeCompare(b.programExtendedName);
  });
}

function buildRelevantRows(
  catalogRows: CatalogRow[],
  previousDataByYearAndItemDiv: Map<string, DataListResponse>,
  requestedYears: number[],
): RelevantItemRow[] {
  return catalogRows
    .filter((row) => row.relevanceRole !== "not_admissions_related")
    .map((row) => {
      const previousOutputKindCodesByYear: Record<string, string[]> = {};
      for (const year of requestedYears.filter((value) => value <= 2022)) {
        const data = previousDataByYearAndItemDiv.get(previousKey(year, row.itemDivCd));
        const kinds = groupKinds(data?.ajaxList6 ?? []).get(row.itemId) ?? [];
        previousOutputKindCodesByYear[String(year)] = kinds;
      }
      return {
        ...row,
        requestedSurveyYears: requestedYears,
        previousOutputKindCodesByYear,
      };
    });
}

async function collectDownloads(
  relevantRows: RelevantItemRow[],
  currentDataByItemDiv: Map<string, DataListResponse>,
  previousDataByYearAndItemDiv: Map<string, DataListResponse>,
  options: Options,
): Promise<DownloadManifestRow[]> {
  const rows: DownloadManifestRow[] = [];
  let attempts = 0;

  for (const item of relevantRows) {
    for (const year of options.years) {
      const kindCodes = outputKindsForYear(
        item,
        year,
        currentDataByItemDiv,
        previousDataByYearAndItemDiv,
      );
      for (const kindCode of kindCodes) {
        if (options.maxDownloads !== null && attempts >= options.maxDownloads) {
          rows.push(baseDownloadRow(item, year, kindCode, "download_skipped", options));
          continue;
        }
        attempts += 1;
        const row = await collectSingleDownload(item, year, kindCode, options);
        rows.push(row);
        console.log(
          [
            "academyinfo public data",
            `item=${item.itemId}`,
            `year=${year}`,
            `kind=${kindCode}`,
            `status=${row.status}`,
            row.bytes === null ? "" : `bytes=${row.bytes}`,
          ]
            .filter(Boolean)
            .join(" "),
        );
        if (options.delayMs > 0) await sleep(options.delayMs);
      }
    }
  }

  return rows;
}

async function collectSingleDownload(
  item: RelevantItemRow,
  year: number,
  kindCode: string,
  options: Options,
): Promise<DownloadManifestRow> {
  const requestEndpoint = year <= 2022 ? "main0820" : "main0810";
  const requestedAt = new Date().toISOString();
  const baseRow = baseDownloadRow(item, year, kindCode, "listed", options, requestEndpoint);

  try {
    const reqList = await requestFileList(item, year, kindCode, requestEndpoint, options);
    const listed = reqList.resultList1?.[0];
    if (!listed?.colvalue12 || !listed.colvalue13) {
      return {
        ...baseRow,
        status: "listed_no_file",
        requestedAt,
        error: reqList.M_RTME ? String(reqList.M_RTME) : undefined,
      };
    }

    const sel = `${listed.colvalue2 ?? item.itemId}^^${listed.colvalue12}^^${listed.colvalue13}`;
    const reqRst = await postFormJson<SelectReqRstResponse>("/popup/main0810/selectReqRst.do", [
      ["schlDivCd", options.schlDivCd],
      ["itemDivCd", item.itemDivCd],
      ["svyYr", String(year)],
      ["all", options.schlDivCd],
      ["fp", ""],
      ["fn", ""],
      ["sn", ""],
      ["searchValue", ""],
      ["sel", sel],
    ]);
    const result = reqRst.resultList;
    if (!result || String(result.exist ?? "") !== "1" || !result.fp || !result.fn || !result.sn) {
      return {
        ...baseRow,
        academyinfoPath: listed.colvalue12,
        academyinfoFileName: listed.colvalue13,
        selectReqRstUrl: `${BASE_URL}/popup/main0810/selectReqRst.do`,
        status: "listed_no_file",
        requestedAt,
        error: reqRst.M_RTME ? String(reqRst.M_RTME) : "selectReqRst returned no file token",
      };
    }

    if (!options.download) {
      return {
        ...baseRow,
        academyinfoPath: listed.colvalue12,
        academyinfoFileName: listed.colvalue13,
        selectReqRstUrl: `${BASE_URL}/popup/main0810/selectReqRst.do`,
        downloadUrl: `${BASE_URL}/popup/main0810/download.do`,
        downloadTokenFileName: result.sn,
        status: "download_skipped",
        requestedAt,
      };
    }

    const form = [
      ["schlDivCd", options.schlDivCd],
      ["itemDivCd", item.itemDivCd],
      ["svyYr", String(result.svyYr ?? year)],
      ["all", options.schlDivCd],
      ["fp", result.fp],
      ["fn", result.fn],
      ["sn", result.sn],
      ["searchValue", ""],
      ["sel", sel],
    ] satisfies [string, string][];
    const outputDir = path.join(
      options.rawDir,
      "downloads",
      String(year),
      String(item.itemId),
      kindCode,
    );
    const existingZip = await findExistingZip(outputDir, options.repoRoot);
    if (existingZip) {
      return {
        ...baseRow,
        academyinfoPath: listed.colvalue12,
        academyinfoFileName: listed.colvalue13,
        selectReqRstUrl: `${BASE_URL}/popup/main0810/selectReqRst.do`,
        downloadUrl: `${BASE_URL}/popup/main0810/download.do`,
        downloadTokenFileName: result.sn,
        rawZipPath: existingZip.rawZipPath,
        sha256: existingZip.sha256,
        bytes: existingZip.bytes,
        status: "downloaded",
        requestedAt,
        fetchedAt: new Date().toISOString(),
      };
    }

    let download = await postFormBytes("/popup/main0810/download.do", form);
    if (!isZipArchive(download.bytes)) {
      download = await postFormBytesWithHttps("/popup/main0810/download.do", form);
    }
    const bytes = download.bytes;
    if (!isZipArchive(bytes)) {
      return {
        ...baseRow,
        academyinfoPath: listed.colvalue12,
        academyinfoFileName: listed.colvalue13,
        selectReqRstUrl: `${BASE_URL}/popup/main0810/selectReqRst.do`,
        downloadUrl: `${BASE_URL}/popup/main0810/download.do`,
        downloadTokenFileName: result.sn,
        status: "download_failed",
        bytes: bytes.length,
        contentType: download.contentType,
        contentDisposition: download.contentDisposition,
        requestedAt,
        fetchedAt: new Date().toISOString(),
        error: "download response was not a zip archive",
      };
    }

    const outputPath = path.join(
      outputDir,
      safeFilename(result.sn || `${item.itemId}-${year}-${kindCode}.zip`),
    );
    await mkdir(path.dirname(outputPath), { recursive: true });
    await writeFile(outputPath, bytes);

    return {
      ...baseRow,
      academyinfoPath: listed.colvalue12,
      academyinfoFileName: listed.colvalue13,
      selectReqRstUrl: `${BASE_URL}/popup/main0810/selectReqRst.do`,
      downloadUrl: `${BASE_URL}/popup/main0810/download.do`,
      downloadTokenFileName: result.sn,
      rawZipPath: toRepoRelative(outputPath, options.repoRoot),
      sha256: sha256(bytes),
      bytes: bytes.length,
      contentType: download.contentType,
      contentDisposition: download.contentDisposition,
      status: "downloaded",
      requestedAt,
      fetchedAt: new Date().toISOString(),
    };
  } catch (error) {
    return {
      ...baseRow,
      status: "request_failed",
      requestedAt,
      error: error instanceof Error ? error.message : String(error),
    };
  }
}

function baseDownloadRow(
  item: RelevantItemRow,
  surveyYear: number,
  outputKindCode: string,
  status: DownloadManifestRow["status"],
  options: Options,
  requestEndpoint: "main0810" | "main0820" = surveyYear <= 2022 ? "main0820" : "main0810",
): DownloadManifestRow {
  return {
    provider: "academyinfo",
    artifactType: "academyinfo_public_data_zip",
    itemId: item.itemId,
    itemDivCd: item.itemDivCd,
    relevanceRole: item.relevanceRole,
    pacerTargets: item.pacerTargets,
    surveyYear,
    schoolDivisionCode: options.schlDivCd,
    outputKindCode,
    outputKindLabel: kindLabel(outputKindCode),
    requestEndpoint,
    selectReqListUrl: `${BASE_URL}/popup/${requestEndpoint}/selectReqList.do`,
    selectReqRstUrl: null,
    downloadUrl: null,
    academyinfoPath: null,
    academyinfoFileName: null,
    downloadTokenFileName: null,
    rawZipPath: null,
    sha256: null,
    bytes: null,
    contentType: null,
    contentDisposition: null,
    status,
    requestedAt: new Date().toISOString(),
    fetchedAt: null,
  };
}

async function requestFileList(
  item: RelevantItemRow,
  year: number,
  kindCode: string,
  endpoint: "main0810" | "main0820",
  options: Options,
): Promise<SelectReqListResponse> {
  if (endpoint === "main0810") {
    return postFormJson<SelectReqListResponse>("/popup/main0810/selectReqList.do", [
      ["itemDivCd", item.itemDivCd],
      ["svyYr", ""],
      ["fp", ""],
      ["fn", ""],
      ["sn", ""],
      ["all", `${item.itemId}^^${kindCode}`],
      ["all", `${item.itemId}^^${year}`],
      ["all", `${item.itemId}^^${options.schlDivCd}^^${year}`],
    ]);
  }

  return postFormJson<SelectReqListResponse>("/popup/main0820/selectReqList.do", [
    ["itemDivCd", item.itemDivCd],
    ["schlDivCd", options.schlDivCd],
    ["svyYr", String(year)],
    [`all-${item.itemId}-${year}`, `${item.itemId}-${kindCode}.${year}.${options.schlDivCd}`],
  ]);
}

function outputKindsForYear(
  item: RelevantItemRow,
  year: number,
  currentDataByItemDiv: Map<string, DataListResponse>,
  previousDataByYearAndItemDiv: Map<string, DataListResponse>,
): string[] {
  if (year <= 2022) {
    const data = previousDataByYearAndItemDiv.get(previousKey(year, item.itemDivCd));
    return groupKinds(data?.ajaxList6 ?? []).get(item.itemId) ?? [];
  }

  const data = currentDataByItemDiv.get(item.itemDivCd);
  const currentKinds = groupKinds(data?.ajaxList6 ?? []).get(item.itemId) ?? [];
  return currentKinds.length > 0 ? currentKinds : item.currentOutputKindCodes;
}

function groupYears(rows: YearAvailability[]): Map<number, string[]> {
  const grouped = new Map<number, Set<string>>();
  for (const row of rows) {
    const itemId = numberValue(row.item_id);
    const year = textValue(row.svy_yr);
    if (!itemId || !year) continue;
    const set = grouped.get(itemId) ?? new Set<string>();
    set.add(year);
    grouped.set(itemId, set);
  }
  return new Map([...grouped].map(([key, set]) => [key, [...set].sort()]));
}

function groupKinds(rows: KindAvailability[]): Map<number, string[]> {
  const grouped = new Map<number, Set<string>>();
  for (const row of rows) {
    const itemId = numberValue(row.item_id);
    const kind = textValue(row.acif_dta_rqst_knd_cd);
    if (!itemId || !kind) continue;
    const set = grouped.get(itemId) ?? new Set<string>();
    set.add(kind);
    grouped.set(itemId, set);
  }
  return new Map([...grouped].map(([key, set]) => [key, [...set].sort()]));
}

function classifyRelevance(labelText: string): RelevanceRole {
  if (/입학전형 유형별 선발 결과/.test(labelText)) return "admission_type_selection_result";
  if (/신입생 충원 현황/.test(labelText)) return "freshman_fill_status";
  if (/재학생 충원율/.test(labelText)) return "student_fill_rate";
  if (/편입학 선발 결과/.test(labelText)) return "transfer_selection_result";
  if (/중도탈락 학생 현황/.test(labelText) && !/외국/.test(labelText)) return "dropout_status";
  if (/신입생의 출신 고등학교 유형별 현황/.test(labelText)) return "freshman_high_school_type";
  if (/전임 입학사정관 현황/.test(labelText)) return "admissions_officer_status";
  if (/입학전형에서 서류평가를 담당한 평가자/.test(labelText)) {
    return "admissions_document_evaluation_load";
  }
  if (/입학전형료 수입 현황/.test(labelText)) return "admissions_fee_revenue";
  if (/입학전형.*지출 현황|입학전형료 지출 현황/.test(labelText)) {
    return "admissions_fee_expense";
  }
  if (/계약학과 및 계약정원제/.test(labelText)) return "contract_department_status";
  return "not_admissions_related";
}

function pacerTargetsFor(role: RelevanceRole): string[] {
  switch (role) {
    case "admission_type_selection_result":
    case "freshman_fill_status":
    case "transfer_selection_result":
      return ["HistoricalOutcome", "ReferenceDataReview"];
    case "student_fill_rate":
    case "dropout_status":
    case "freshman_high_school_type":
      return ["ReferenceDataReview"];
    case "admissions_officer_status":
    case "admissions_document_evaluation_load":
    case "admissions_fee_revenue":
    case "admissions_fee_expense":
    case "contract_department_status":
      return ["AdmissionRule", "ReferenceDataReview"];
    case "not_admissions_related":
      return [];
  }
}

function itemLabelText(item: AcademyItem): string {
  return [
    item.pgm_estn_nm,
    item.pgm_kor_shrt_nm,
    item.item_smry_nm,
    item.recursive_level,
  ]
    .map((value) => textValue(value))
    .filter(Boolean)
    .join(" ");
}

function kindLabel(code: string): string {
  if (code === "10") return "학교별";
  if (code === "20") return "학과별";
  return `출력구분 ${code}`;
}

async function fetchText(url: string): Promise<string> {
  const response = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
  if (!response.ok) throw new Error(`fetch failed ${response.status} ${url}`);
  return response.text();
}

async function postFormJson<T>(pathname: string, entries: [string, string][]): Promise<T> {
  const response = await postFormWithRetry(pathname, entries, 3);
  if (!response.ok) {
    throw new Error(`post failed ${response.status} ${BASE_URL}${pathname}`);
  }
  return response.json() as Promise<T>;
}

async function postFormBytes(
  pathname: string,
  entries: [string, string][],
): Promise<{
  bytes: Buffer;
  contentType: string | null;
  contentDisposition: string | null;
}> {
  try {
    const response = await postFormWithRetry(pathname, entries, 3);
    if (!response.ok) {
      throw new Error(`post failed ${response.status} ${BASE_URL}${pathname}`);
    }
    const bytes = Buffer.from(await response.arrayBuffer());
    return {
      bytes,
      contentType: response.headers.get("content-type"),
      contentDisposition: response.headers.get("content-disposition"),
    };
  } catch {
    return postFormBytesWithHttps(pathname, entries);
  }
}

async function postFormWithRetry(
  pathname: string,
  entries: [string, string][],
  attempts: number,
): Promise<Response> {
  let lastError: unknown = null;
  for (let attempt = 1; attempt <= attempts; attempt += 1) {
    try {
      return await postForm(pathname, entries);
    } catch (error) {
      lastError = error;
      if (attempt < attempts) await sleep(250 * attempt);
    }
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

function postForm(pathname: string, entries: [string, string][]): Promise<Response> {
  const form = new URLSearchParams();
  for (const [key, value] of entries) form.append(key, value);
  return fetch(`${BASE_URL}${pathname}`, {
    method: "POST",
    headers: {
      "User-Agent": USER_AGENT,
      "Accept-Encoding": "identity",
      "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    },
    body: form.toString(),
  });
}

function postFormBytesWithHttps(
  pathname: string,
  entries: [string, string][],
): Promise<{
  bytes: Buffer;
  contentType: string | null;
  contentDisposition: string | null;
}> {
  const form = new URLSearchParams();
  for (const [key, value] of entries) form.append(key, value);
  const body = form.toString();
  const url = new URL(`${BASE_URL}${pathname}`);

  return new Promise((resolve, reject) => {
    const request = httpsRequest(
      {
        method: "POST",
        hostname: url.hostname,
        path: `${url.pathname}${url.search}`,
        headers: {
          "User-Agent": USER_AGENT,
          "Accept-Encoding": "identity",
          "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (response) => {
        const chunks: Buffer[] = [];
        response.on("data", (chunk: Buffer | string) => {
          chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
        });
        response.on("end", () => {
          const statusCode = response.statusCode ?? 0;
          const bytes = Buffer.concat(chunks);
          if (statusCode < 200 || statusCode >= 300) {
            reject(new Error(`https post failed ${statusCode} ${BASE_URL}${pathname}`));
            return;
          }
          resolve({
            bytes,
            contentType: headerValue(response.headers["content-type"]),
            contentDisposition: headerValue(response.headers["content-disposition"]),
          });
        });
      },
    );
    request.on("error", reject);
    request.write(body);
    request.end();
  });
}

async function findExistingZip(
  outputDir: string,
  repoRoot: string,
): Promise<{ rawZipPath: string; sha256: string; bytes: number } | null> {
  try {
    const entries = await readdir(outputDir);
    for (const zipName of entries.filter((entry) => entry.toLowerCase().endsWith(".zip"))) {
      const filePath = path.join(outputDir, zipName);
      const bytes = await readFile(filePath);
      if (!isZipArchive(bytes)) continue;
      return {
        rawZipPath: toRepoRelative(filePath, repoRoot),
        sha256: sha256(bytes),
        bytes: bytes.length,
      };
    }
    return null;
  } catch {
    return null;
  }
}

function summarize(
  options: Options,
  catalogRows: CatalogRow[],
  relevantRows: RelevantItemRow[],
  manifestRows: DownloadManifestRow[],
  currentDataByItemDiv: Map<string, DataListResponse>,
  previousDataByYearAndItemDiv: Map<string, DataListResponse>,
): JsonRecord {
  const statuses = countBy(manifestRows, (row) => row.status);
  const roles = countBy(relevantRows, (row) => row.relevanceRole);
  const years = countBy(manifestRows, (row) => String(row.surveyYear));
  return {
    provider: "academyinfo",
    officialSource: `${BASE_URL}${CURRENT_POPUP_PATH}`,
    previousDataSource: `${BASE_URL}${PREVIOUS_POPUP_PATH}`,
    schoolDivisionCode: options.schlDivCd,
    itemDivs: options.itemDivs,
    requestedYears: options.years,
    currentDataListFetches: currentDataByItemDiv.size,
    previousDataListFetches: previousDataByYearAndItemDiv.size,
    catalogItems: catalogRows.length,
    relevantItems: relevantRows.length,
    relevantRoles: roles,
    downloadRows: manifestRows.length,
    downloaded: manifestRows.filter((row) => row.status === "downloaded").length,
    failed: manifestRows.filter((row) => row.status.endsWith("failed")).length,
    downloadedBytes: manifestRows.reduce((sum, row) => sum + (row.bytes ?? 0), 0),
    statuses,
    rowsBySurveyYear: years,
    rawDir: toRepoRelative(options.rawDir, options.repoRoot),
    publicDir: toRepoRelative(options.publicDir, options.repoRoot),
    generatedAt: new Date().toISOString(),
  };
}

async function writeReadme(publicDir: string): Promise<void> {
  const readme = [
    "# Academyinfo Public Data",
    "",
    "대학알리미 `공시DATA 다운로드` 공식 팝업에서 수집한 대학 공시 항목 catalog와 입시 관련 원천 ZIP manifest다.",
    "",
    "## Files",
    "",
    "- `academyinfo_public_data_item_catalog.jsonl/.csv`: 대학알리미 공시 항목 catalog.",
    "- `academyinfo_admissions_relevant_items.jsonl/.csv`: Pacer 기준 입시 관련 보조 공시 항목.",
    "- `academyinfo_public_data_download_manifest.jsonl/.csv`: 입시 관련 항목별 survey year/output kind ZIP 다운로드 manifest.",
    "- `academyinfo_public_data_summary.json`: 수집 요약.",
    "- `extracted/academyinfo_workbook_sources_manifest.jsonl`: ZIP 안 XLSX 추출 source manifest.",
    "- `extracted/academyinfo_workbook_sheets_manifest.jsonl`: XLSX 시트별 CSV manifest.",
    "- `extracted/academyinfo_workbook_sheets_index.csv`: 검수용 시트 인덱스.",
    "- `extracted/workbook-sheets/`: 대학알리미 XLSX에서 추출한 시트별 CSV.",
    "- `extracted/academyinfo_workbook_sheets_summary.json`: workbook 시트 추출 요약.",
    "- `extracted/academyinfo_sheet_column_labels.jsonl`: 시트별 병합 헤더/컬럼 라벨 manifest.",
    "- `extracted/academyinfo_row_candidates.jsonl/.csv`: 학교/학과/전형 context와 numeric metric을 정리한 검수 후보.",
    "- `extracted/academyinfo_row_candidates_summary.json`: 행 후보 추출 요약.",
    "",
    "원문 HTML/JSON/ZIP은 `.reference-data/raw/academyinfo-public-data/` 아래에 보존한다.",
    "",
  ].join("\n");
  await writeFile(path.join(publicDir, "README.md"), readme, "utf8");
}

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: process.cwd(),
    rawDir: DEFAULT_RAW_DIR,
    publicDir: DEFAULT_PUBLIC_DIR,
    itemDivs: [...DEFAULT_ITEM_DIVS],
    years: [...DEFAULT_YEARS],
    schlDivCd: "02",
    download: true,
    delayMs: 100,
    maxDownloads: null,
  };

  for (const arg of args) {
    if (arg === "--") continue;
    if (arg.startsWith("--raw-dir=")) {
      options.rawDir = arg.slice("--raw-dir=".length);
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--item-divs=")) {
      options.itemDivs = splitList(arg.slice("--item-divs=".length));
    } else if (arg.startsWith("--years=")) {
      options.years = splitList(arg.slice("--years=".length)).map((value) => Number(value));
    } else if (arg.startsWith("--schl-div-cd=")) {
      options.schlDivCd = arg.slice("--schl-div-cd=".length);
    } else if (arg === "--no-download") {
      options.download = false;
    } else if (arg.startsWith("--delay-ms=")) {
      options.delayMs = Number(arg.slice("--delay-ms=".length));
    } else if (arg.startsWith("--max-downloads=")) {
      options.maxDownloads = Number(arg.slice("--max-downloads=".length));
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  options.years = [...new Set(options.years)].sort((a, b) => a - b);
  if (options.years.some((year) => !Number.isInteger(year))) {
    throw new Error("--years must be a comma-separated list of integer years");
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

function splitList(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function findRepoRoot(start: string): string {
  let current = path.resolve(start);
  while (true) {
    if (existsSync(path.join(current, "pnpm-workspace.yaml"))) return current;
    const parent = path.dirname(current);
    if (parent === current) return path.resolve(start);
    current = parent;
  }
}

function resolveFromRoot(repoRoot: string, value: string): string {
  return path.isAbsolute(value) ? value : path.join(repoRoot, value);
}

function toRepoRelative(value: string, repoRoot: string): string {
  return path.relative(repoRoot, value).split(path.sep).join("/");
}

function previousKey(year: number, itemDivCd: string): string {
  return `${year}:${itemDivCd}`;
}

function textValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).trim();
}

function stringOrNull(value: unknown): string | null {
  const text = textValue(value);
  return text ? text : null;
}

function numberValue(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function numberOrNull(value: unknown): number | null {
  const parsed = numberValue(value);
  return parsed || parsed === 0 ? parsed : null;
}

function isZipArchive(bytes: Buffer): boolean {
  if (bytes.length < 22 || bytes[0] !== 0x50 || bytes[1] !== 0x4b) return false;
  const eocdSignature = Buffer.from([0x50, 0x4b, 0x05, 0x06]);
  const searchStart = Math.max(0, bytes.length - 66_000);
  for (let index = bytes.length - 22; index >= searchStart; index -= 1) {
    if (bytes.subarray(index, index + 4).equals(eocdSignature)) return true;
  }
  return false;
}

function sha256(bytes: Buffer): string {
  return createHash("sha256").update(bytes).digest("hex");
}

function safeFilename(value: string): string {
  return value.replace(/[^\w.-가-힣]+/g, "_").replace(/^_+|_+$/g, "") || "download.zip";
}

function jsonText(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function headerValue(value: string | string[] | undefined): string | null {
  if (Array.isArray(value)) return value.join("; ");
  return value ?? null;
}

async function writeJsonl(filePath: string, rows: JsonRecord[]): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(
    filePath,
    `${rows.map((row) => JSON.stringify(row)).join("\n")}${rows.length ? "\n" : ""}`,
    "utf8",
  );
}

async function writeCsv(
  filePath: string,
  rows: JsonRecord[],
  columns: string[],
): Promise<void> {
  await mkdir(path.dirname(filePath), { recursive: true });
  const lines = [
    columns.join(","),
    ...rows.map((row) =>
      columns
        .map((column) => {
          const value = row[column];
          if (Array.isArray(value)) return csvEscape(value.join("|"));
          if (value && typeof value === "object") return csvEscape(JSON.stringify(value));
          return csvEscape(value ?? "");
        })
        .join(","),
    ),
  ];
  await writeFile(filePath, `${lines.join("\n")}\n`, "utf8");
}

function csvEscape(value: unknown): string {
  const text = String(value);
  if (!/[",\n\r]/.test(text)) return text;
  return `"${text.replace(/"/g, '""')}"`;
}

function countBy<T extends JsonRecord>(
  rows: T[],
  getKey: (row: T) => string | number,
): Record<string, number> {
  const counts: Record<string, number> = {};
  for (const row of rows) {
    const key = String(getKey(row));
    counts[key] = (counts[key] ?? 0) + 1;
  }
  return counts;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
