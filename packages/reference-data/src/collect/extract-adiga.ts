import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const DEFAULT_YEARS = [2021, 2022, 2023, 2024, 2025, 2026, 2027];
const DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/adiga";
const DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/adiga/extracted";

type Options = {
  repoRoot: string;
  years: number[];
  publicDir: string;
  outputDir: string;
  limit: number | null;
  unvCds: Set<string> | null;
};

type DetailManifest = {
  provider: "adiga";
  artifactType: "university_selection_html";
  year: number;
  unvCd: string;
  universityName: string;
  sourceUrl: string;
  rawPath: string;
  sha256: string;
  bytes: number;
  imageUrls: string[];
  status: "fetched" | "fetch_failed";
};

type SectionBoundary = {
  id: string;
  start: number;
  end: number;
  label: string;
};

type ExtractedTable = {
  provider: "adiga";
  artifactType: "adiga_extracted_table";
  year: number;
  unvCd: string;
  universityName: string;
  sourceUrl: string;
  rawPath: string;
  sectionId: string | null;
  sectionLabel: string | null;
  tableIndex: number;
  tableRole: TableRole;
  rows: number;
  cols: number;
  headerText: string;
  textSnippet: string;
  tableSha256: string;
  grid: string[][];
};

type TableRole =
  | "csat_outcome"
  | "csat_rule"
  | "student_outcome"
  | "student_rule"
  | "common"
  | "other";

type OutcomeCandidate = {
  provider: "adiga";
  artifactType: "adiga_csat_outcome_candidate";
  year: number;
  unvCd: string;
  universityName: string;
  sourceUrl: string;
  rawPath: string;
  sectionId: string | null;
  tableIndex: number;
  rowIndex: number;
  recruitmentGroup: "ga" | "na" | "da" | null;
  recruitmentGroupText: string | null;
  admissionUnitName: string;
  quota: number | null;
  competitionRate: number | null;
  additionalPass: number | null;
  convertedScore50Cut: number | null;
  convertedScore70Cut: number | null;
  totalScore: number | null;
  percentile70Average: number | null;
  percentile50BySubjectJson: string;
  percentile70BySubjectJson: string;
  mathSelectionRatioJson: string;
  sourceConfidence: "parsed_candidate";
};

type OutcomeColumns = {
  group: number | null;
  unit: number;
  quota: number | null;
  competition: number | null;
  additionalPass: number | null;
  converted50: number | null;
  converted70: number | null;
  totalScore: number | null;
  percentileAverage70: number | null;
  percentile50Subjects: Record<string, number>;
  percentile70Subjects: Record<string, number>;
  mathSelectionRatios: Record<string, number>;
};

async function main() {
  const options = withResolvedPaths(parseArgs(process.argv.slice(2)));
  await mkdir(options.outputDir, { recursive: true });

  const summaryYears: Array<{
    year: number;
    manifests: number;
    fetched: number;
    tables: number;
    csatOutcomeTables: number;
    csatOutcomeCandidates: number;
  }> = [];

  for (const year of options.years) {
    const manifests = await loadManifestYear(options.publicDir, year);
    const filtered = manifests
      .filter((manifest) => manifest.status === "fetched")
      .filter((manifest) => !options.unvCds || options.unvCds.has(manifest.unvCd))
      .slice(0, options.limit ?? undefined);

    const yearTables: ExtractedTable[] = [];
    const yearOutcomes: OutcomeCandidate[] = [];

    for (const manifest of filtered) {
      const rawAbsolutePath = path.join(options.repoRoot, manifest.rawPath);
      const html = await readFile(rawAbsolutePath, "utf8");
      const tables = extractTablesFromHtml(html, manifest);
      yearTables.push(...tables);

      for (const table of tables) {
        const outcomes = extractCsatOutcomeCandidates(table);
        yearOutcomes.push(...outcomes);
      }
    }

    await writeJsonl(
      path.join(options.outputDir, `adiga_extracted_tables_${year}.jsonl`),
      yearTables,
    );
    await writeCsv(
      path.join(options.outputDir, `adiga_csat_outcome_candidates_${year}.csv`),
      yearOutcomes,
      outcomeHeaders,
    );

    summaryYears.push({
      year,
      manifests: manifests.length,
      fetched: filtered.length,
      tables: yearTables.length,
      csatOutcomeTables: yearTables.filter((table) => table.tableRole === "csat_outcome")
        .length,
      csatOutcomeCandidates: yearOutcomes.length,
    });

    console.log(
      [
        `adiga extract year=${year}`,
        `fetched=${filtered.length}/${manifests.length}`,
        `tables=${yearTables.length}`,
        `csat_outcomes=${yearOutcomes.length}`,
      ].join(" "),
    );
  }

  const summary = {
    provider: "adiga",
    generatedAt: new Date().toISOString(),
    years: summaryYears,
    totals: {
      tables: summaryYears.reduce((sum, year) => sum + year.tables, 0),
      csatOutcomeTables: summaryYears.reduce(
        (sum, year) => sum + year.csatOutcomeTables,
        0,
      ),
      csatOutcomeCandidates: summaryYears.reduce(
        (sum, year) => sum + year.csatOutcomeCandidates,
        0,
      ),
    },
    notes: [
      "HTML tables are expanded with rowspan/colspan so merged recruitment-group cells can be reviewed row by row.",
      "Outcome rows are parsed candidates, not verified production AdmissionUnit/HistoricalOutcome records.",
      "Image-only tables remain preserved through raw HTML/image URL manifests and need OCR/manual curation before use.",
    ],
  };

  await writeFile(
    path.join(options.outputDir, "adiga_extraction_summary.json"),
    `${JSON.stringify(summary, null, 2)}\n`,
  );
}

function extractTablesFromHtml(
  html: string,
  manifest: DetailManifest,
): ExtractedTable[] {
  const sections = findSectionBoundaries(html);
  const tableMatches = [...html.matchAll(/<table\b[\s\S]*?<\/table>/gi)];

  return tableMatches.map((match, index) => {
    const tableHtml = match[0] ?? "";
    const position = match.index ?? 0;
    const section = findSectionForPosition(sections, position);
    const grid = parseTable(tableHtml);
    const text = tableTextFromGrid(grid);
    const role = classifyTable(section?.id ?? null, text);

    return {
      provider: "adiga",
      artifactType: "adiga_extracted_table",
      year: manifest.year,
      unvCd: manifest.unvCd,
      universityName: manifest.universityName,
      sourceUrl: manifest.sourceUrl,
      rawPath: manifest.rawPath,
      sectionId: section?.id ?? null,
      sectionLabel: section?.label ?? null,
      tableIndex: index + 1,
      tableRole: role,
      rows: grid.length,
      cols: maxCols(grid),
      headerText: headerText(grid),
      textSnippet: text.slice(0, 500),
      tableSha256: sha256(tableHtml),
      grid,
    };
  });
}

function findSectionBoundaries(html: string): SectionBoundary[] {
  const matches = [...html.matchAll(/id="(?<id>con_\d+)"/g)]
    .map((match) => ({
      id: match.groups?.id ?? "",
      start: match.index ?? 0,
    }))
    .filter((match) => match.id.length > 0);

  return matches.map((match, index) => {
    const next = matches[index + 1];
    return {
      id: match.id,
      start: match.start,
      end: next?.start ?? html.length,
      label: sectionLabel(match.id),
    };
  });
}

function findSectionForPosition(
  sections: SectionBoundary[],
  position: number,
): SectionBoundary | null {
  return (
    sections.find((section) => position >= section.start && position < section.end) ??
    null
  );
}

function sectionLabel(id: string): string {
  const labels: Record<string, string> = {
    con_11: "공통",
    con_21: "학생부종합전형 주요사항",
    con_22: "학생부종합전형 입시결과",
    con_23: "학생부종합전형 추가자료",
    con_24: "학생부종합전형 추가자료",
    con_25: "학생부종합전형 추가자료",
    con_26: "학생부종합전형 추가자료",
    con_31: "학생부교과전형 주요사항",
    con_32: "학생부교과전형 입시결과",
    con_41: "수능위주전형 주요사항",
    con_42: "수능위주전형 입시결과",
  };

  return labels[id] ?? id;
}

function classifyTable(sectionId: string | null, text: string): TableRole {
  const compact = text.replace(/[\/\s]+/g, "");
  const looksLikeOutcomeTable =
    compact.includes("모집단위") &&
    compact.includes("모집인원") &&
    compact.includes("경쟁률");
  const looksLikeCsatAverageOutcome =
    sectionId === "con_42" &&
    compact.includes("모집단위") &&
    (compact.includes("지원인원") || compact.includes("지원")) &&
    (compact.includes("등록인원") || compact.includes("등록")) &&
    compact.includes("평균") &&
    compact.includes("표준") &&
    compact.includes("수능백분위점수");

  const looksLikeCsatOutcome =
    (looksLikeOutcomeTable || looksLikeCsatAverageOutcome) &&
    (looksLikeCsatAverageOutcome ||
      compact.includes("대학별환산") ||
      compact.includes("환산점수") ||
      compact.includes("환산등급") ||
      compact.includes("50%cut") ||
      compact.includes("70%cut") ||
      compact.includes("백분위")) &&
    (compact.includes("수능") || sectionId === "con_42" || sectionId === "con_41");

  if (sectionId === "con_42" && looksLikeOutcomeTable) return "csat_outcome";
  if (looksLikeCsatOutcome) return "csat_outcome";
  if (sectionId?.startsWith("con_4") || compact.includes("수능성적산출방법")) {
    return "csat_rule";
  }
  if (sectionId === "con_11") return "common";
  if (sectionId?.startsWith("con_2")) {
    return compact.includes("최종등록자") || compact.includes("경쟁률")
      ? "student_outcome"
      : "student_rule";
  }
  if (sectionId?.startsWith("con_3")) {
    return compact.includes("최종등록자") || compact.includes("경쟁률")
      ? "student_outcome"
      : "student_rule";
  }

  return "other";
}

function parseTable(tableHtml: string): string[][] {
  const rowMatches = [...tableHtml.matchAll(/<tr\b[^>]*>[\s\S]*?<\/tr>/gi)];
  const grid: string[][] = [];

  for (let rowIndex = 0; rowIndex < rowMatches.length; rowIndex += 1) {
    const rowHtml = rowMatches[rowIndex]?.[0] ?? "";
    const row = ensureRow(grid, rowIndex);
    const cellMatches = [
      ...rowHtml.matchAll(/<(td|th)\b(?<attrs>[^>]*)>[\s\S]*?<\/\1>/gi),
    ];
    let colIndex = 0;

    for (const cellMatch of cellMatches) {
      while (row[colIndex] !== undefined) colIndex += 1;

      const attrs = cellMatch.groups?.attrs ?? "";
      const cellHtml = cellMatch[0] ?? "";
      const rowSpan = parseSpan(attrs, "rowspan");
      const colSpan = parseSpan(attrs, "colspan");
      const value = htmlToText(cellHtml);

      for (let rowOffset = 0; rowOffset < rowSpan; rowOffset += 1) {
        const targetRow = ensureRow(grid, rowIndex + rowOffset);
        for (let colOffset = 0; colOffset < colSpan; colOffset += 1) {
          targetRow[colIndex + colOffset] = value;
        }
      }

      colIndex += colSpan;
    }
  }

  const width = maxCols(grid);
  return grid.map((row) =>
    Array.from({ length: width }, (_, index) => row[index] ?? ""),
  );
}

function ensureRow(grid: string[][], index: number): string[] {
  const existing = grid[index];
  if (existing) return existing;

  const row: string[] = [];
  grid[index] = row;
  return row;
}

function parseSpan(attrs: string, name: "rowspan" | "colspan"): number {
  const match = attrs.match(new RegExp(`${name}\\s*=\\s*["']?(\\d+)`, "i"));
  return match?.[1] ? Number(match[1]) : 1;
}

function extractCsatOutcomeCandidates(table: ExtractedTable): OutcomeCandidate[] {
  if (table.tableRole !== "csat_outcome") return [];
  if (table.grid.length < 2 || table.cols < 6) return [];

  const columns = inferOutcomeColumns(table.grid);
  if (!columns) return [];

  const firstDataRow = findFirstOutcomeDataRow(table.grid, columns.unit);
  if (firstDataRow === null) return [];

  const candidates: OutcomeCandidate[] = [];
  let previousGroupText: string | null = null;

  for (let rowIndex = firstDataRow; rowIndex < table.grid.length; rowIndex += 1) {
    const rawRow = table.grid[rowIndex];
    if (!rawRow) continue;

    const row = normalizeOutcomeDataRow(rawRow, columns, previousGroupText, table.cols);
    const groupText = columns.group === null ? null : cleanCell(row[columns.group]);
    if (groupText && isRecruitmentGroupText(groupText)) {
      previousGroupText = groupText;
    }

    const unitName = cleanCell(row[columns.unit]);
    if (!isLikelyAdmissionUnitName(unitName)) continue;

    const quota = parseNumberCell(valueAt(row, columns.quota));
    const competitionRate = parseCompetitionRate(valueAt(row, columns.competition));
    const additionalPass = parseIntegerCell(valueAt(row, columns.additionalPass));
    const convertedScore50Cut = parseNumberCell(valueAt(row, columns.converted50));
    const convertedScore70Cut = parseNumberCell(valueAt(row, columns.converted70));
    const totalScore = parseNumberCell(valueAt(row, columns.totalScore));
    const percentile70Average = parseNumberCell(
      valueAt(row, columns.percentileAverage70),
    );
    const percentile50BySubject = valuesBySubject(
      row,
      columns.percentile50Subjects,
    );
    const percentile70BySubject = valuesBySubject(
      row,
      columns.percentile70Subjects,
    );
    const mathSelectionRatio = valuesBySubject(row, columns.mathSelectionRatios);

    if (
      quota === null &&
      competitionRate === null &&
      additionalPass === null &&
      convertedScore70Cut === null &&
      percentile70Average === null &&
      Object.keys(percentile70BySubject).length === 0
    ) {
      continue;
    }

    const recruitmentGroupText =
      groupText && isRecruitmentGroupText(groupText) ? groupText : previousGroupText;

    candidates.push({
      provider: "adiga",
      artifactType: "adiga_csat_outcome_candidate",
      year: table.year,
      unvCd: table.unvCd,
      universityName: table.universityName,
      sourceUrl: table.sourceUrl,
      rawPath: table.rawPath,
      sectionId: table.sectionId,
      tableIndex: table.tableIndex,
      rowIndex: rowIndex + 1,
      recruitmentGroup: normalizeRecruitmentGroup(recruitmentGroupText),
      recruitmentGroupText,
      admissionUnitName: unitName,
      quota,
      competitionRate,
      additionalPass,
      convertedScore50Cut,
      convertedScore70Cut,
      totalScore,
      percentile70Average,
      percentile50BySubjectJson: JSON.stringify(percentile50BySubject),
      percentile70BySubjectJson: JSON.stringify(percentile70BySubject),
      mathSelectionRatioJson: JSON.stringify(mathSelectionRatio),
      sourceConfidence: "parsed_candidate",
    });
  }

  return candidates;
}

function inferOutcomeColumns(grid: string[][]): OutcomeColumns | null {
  const width = maxCols(grid);
  const unit = findLastHeaderColumn(grid, /모집\s*단위/);
  if (unit === null) return null;
  const csatAverageColumn = findHeaderColumn(grid, /평균/);
  const csatStddevColumn = findHeaderColumn(grid, /표준\s*\/?\s*편차/);
  const hasCsatAverageShape =
    width <= 10 &&
    csatAverageColumn !== null &&
    csatStddevColumn !== null &&
    findHeaderColumn(grid, /지원\s*인원|지원/) !== null &&
    findHeaderColumn(grid, /등록\s*인원|등록/) !== null;

  if (hasCsatAverageShape) {
    return {
      group: findHeaderColumn(grid, /^구분$|모집\s*군/),
      unit,
      quota:
        findHeaderColumn(grid, /모집\s*\/?\s*인원/) ??
        findHeaderColumn(grid, /^모집$/) ??
        unit + 2,
      competition: null,
      additionalPass: null,
      converted50: null,
      converted70: null,
      totalScore: null,
      percentileAverage70: csatAverageColumn,
      percentile50Subjects: {},
      percentile70Subjects: {},
      mathSelectionRatios: {},
    };
  }

  if (width >= 20) {
    return {
      group: findHeaderColumn(grid, /^구분$/) ?? 0,
      unit,
      quota:
        findHeaderColumn(grid, /최종\s*\(A\+B\)/) ??
        findHeaderColumn(grid, /모집\s*\/?\s*인원/) ??
        unit + 1,
      competition: findHeaderColumn(grid, /경쟁률/) ?? unit + 4,
      additionalPass: findHeaderColumn(grid, /충원/) ?? unit + 5,
      converted50: findHeaderColumn(grid, /최종\s*등록자\s*50%\s*cut/) ?? null,
      converted70: findHeaderColumn(grid, /최종\s*등록자\s*70%\s*cut/) ?? null,
      totalScore: findHeaderColumn(grid, /총점\s*\(\s*수능\s*\)|최고점\s*\/?\s*\(?\s*수능\s*\)?/),
      percentileAverage70: null,
      percentile50Subjects: subjectColumns(grid, /최종등록자\s*50%|50%\s*학생/),
      percentile70Subjects: subjectColumns(grid, /최종등록자\s*70%|70%\s*학생/),
      mathSelectionRatios: mathSelectionColumns(grid),
    };
  }

  if (width >= 11) {
    return {
      group: findHeaderColumn(grid, /^구분$/) ?? 0,
      unit,
      quota: findHeaderColumn(grid, /모집\s*\/?\s*인원/) ?? unit + 1,
      competition: findHeaderColumn(grid, /경쟁률/) ?? unit + 2,
      additionalPass: findHeaderColumn(grid, /충원/) ?? unit + 3,
      converted50: null,
      converted70: findHeaderColumn(grid, /대학별\s*환산|환산점수/) ?? unit + 4,
      totalScore: findHeaderColumn(grid, /최고점\s*\/?\s*\(?\s*수능\s*\)?/) ?? unit + 5,
      percentileAverage70: findHeaderColumn(grid, /평균/) ?? unit + 9,
      percentile50Subjects: {},
      percentile70Subjects: subjectColumns(grid, /백분위\s*70%|70%\s*cut|70%\s*학생/),
      mathSelectionRatios: {},
    };
  }

  return {
    group: findHeaderColumn(grid, /^구분$/) ?? 0,
    unit,
    quota: findHeaderColumn(grid, /모집\s*\/?\s*인원/) ?? unit + 1,
    competition: findHeaderColumn(grid, /경쟁률/) ?? unit + 2,
    additionalPass: findHeaderColumn(grid, /충원/) ?? unit + 3,
    converted50: null,
    converted70: findHeaderColumn(grid, /대학별|환산/) ?? unit + 4,
    totalScore: unit + 5,
    percentileAverage70: unit + 6,
    percentile50Subjects: {},
    percentile70Subjects: {},
    mathSelectionRatios: {},
  };
}

function findHeaderColumn(grid: string[][], pattern: RegExp): number | null {
  const rowsToScan = grid.slice(0, Math.min(5, grid.length));
  const width = maxCols(rowsToScan);

  for (let column = 0; column < width; column += 1) {
    const text = rowsToScan
      .map((row) => row[column] ?? "")
      .filter(Boolean)
      .join(" ");
    if (headerMatches(text, pattern)) return column;
  }

  return null;
}

function findLastHeaderColumn(grid: string[][], pattern: RegExp): number | null {
  const rowsToScan = grid.slice(0, Math.min(5, grid.length));
  const width = maxCols(rowsToScan);

  for (let column = width - 1; column >= 0; column -= 1) {
    const text = rowsToScan
      .map((row) => row[column] ?? "")
      .filter(Boolean)
      .join(" ");
    if (headerMatches(text, pattern)) return column;
  }

  return null;
}

function subjectColumns(grid: string[][], groupPattern: RegExp): Record<string, number> {
  const rowsToScan = grid.slice(0, Math.min(5, grid.length));
  const width = maxCols(rowsToScan);
  const subjects: Record<string, number> = {};

  for (let column = 0; column < width; column += 1) {
    const header = rowsToScan.map((row) => row[column] ?? "").join(" ");
    if (!headerMatches(header, groupPattern)) continue;

    const finalLabel = rowsToScan
      .map((row) => row[column] ?? "")
      .reverse()
      .find((value) => subjectKey(value) !== null);
    const key = subjectKey(finalLabel ?? "");
    if (key) subjects[key] = column;
  }

  return subjects;
}

function mathSelectionColumns(grid: string[][]): Record<string, number> {
  const rowsToScan = grid.slice(0, Math.min(5, grid.length));
  const width = maxCols(rowsToScan);
  const columns: Record<string, number> = {};

  for (let column = 0; column < width; column += 1) {
    const header = rowsToScan.map((row) => row[column] ?? "").join(" ");
    const compact = compactHeaderText(header);
    if (!compact.includes("최종등록자수학선택과목응시비율")) continue;

    if (compact.includes("확률과통계")) columns.probabilityAndStatistics = column;
    if (compact.includes("미적분")) columns.calculus = column;
    if (compact.includes("기하")) columns.geometry = column;
  }

  return columns;
}

function headerMatches(text: string, pattern: RegExp): boolean {
  pattern.lastIndex = 0;
  if (pattern.test(text)) return true;
  pattern.lastIndex = 0;
  return pattern.test(compactHeaderText(text));
}

function compactHeaderText(text: string): string {
  return text.replace(/[\/\s]+/g, "");
}

function findFirstOutcomeDataRow(grid: string[][], unitColumn: number): number | null {
  for (let rowIndex = 0; rowIndex < grid.length; rowIndex += 1) {
    const row = grid[rowIndex];
    if (!row) continue;

    const unit = cleanCell(row[unitColumn]);
    if (isLikelyAdmissionUnitName(unit)) return rowIndex;

    const shiftedUnit = cleanCell(row[0]);
    const nextValue = cleanCell(row[unitColumn]);
    if (isLikelyAdmissionUnitName(shiftedUnit) && isNumericLike(nextValue)) {
      return rowIndex;
    }
  }

  return null;
}

function normalizeOutcomeDataRow(
  row: string[],
  columns: OutcomeColumns,
  previousGroupText: string | null,
  width: number,
): string[] {
  if (columns.group === null || columns.group !== 0 || columns.unit !== 1) {
    return Array.from({ length: width }, (_, index) => row[index] ?? "");
  }

  const first = cleanCell(row[0]);
  const second = cleanCell(row[1]);
  if (
    previousGroupText &&
    first.length > 0 &&
    !isRecruitmentGroupText(first) &&
    isLikelyAdmissionUnitName(first) &&
    isNumericLike(second)
  ) {
    const shifted = [previousGroupText, ...row];
    return Array.from({ length: width }, (_, index) => shifted[index] ?? "");
  }

  return Array.from({ length: width }, (_, index) => row[index] ?? "");
}

function valueAt(row: string[], column: number | null): string {
  if (column === null) return "";
  return row[column] ?? "";
}

function valuesBySubject(
  row: string[],
  columns: Record<string, number>,
): Record<string, number> {
  const values: Record<string, number> = {};

  for (const [key, column] of Object.entries(columns)) {
    const value = parseNumberCell(row[column] ?? "");
    if (value !== null) values[key] = value;
  }

  return values;
}

function isLikelyAdmissionUnitName(value: string): boolean {
  if (value.length === 0) return false;
  if (isRecruitmentGroupText(value)) return false;
  if (isNumericLike(value)) return false;
  const compact = compactHeaderText(value);
  if (compact === "전모집단위") return true;
  if (
    /모집단위|모집인원|구분|최종등록자|대학별|백분위|총점|선발인원|수능반영유형/.test(
      compact,
    ) ||
    value === "계열"
  ) {
    return false;
  }
  return /[가-힣]/.test(value);
}

function isRecruitmentGroupText(value: string): boolean {
  const compact = compactHeaderText(value).replace(/[()]/g, "");
  return /^[가나다]군/.test(compact) || /^정시[가나다]군?/.test(compact);
}

function normalizeRecruitmentGroup(
  value: string | null,
): "ga" | "na" | "da" | null {
  if (!value) return null;
  if (value.includes("가")) return "ga";
  if (value.includes("나")) return "na";
  if (value.includes("다")) return "da";
  return null;
}

function subjectKey(label: string): string | null {
  const normalized = label.replace(/\s+/g, "");
  const compact = normalized.replace(/\//g, "");
  if (compact === "국" || compact === "국어") return "korean";
  if (compact === "수" || compact === "수학") return "math";
  if (compact === "탐" || compact === "탐구") return "inquiry";
  if (compact === "탐1" || compact === "탐구1") return "inquiry1";
  if (compact === "탐2" || compact === "탐구2") return "inquiry2";
  if (compact === "평균") return "average";
  if (compact === "영" || compact === "영어") return "englishGrade";
  if (compact === "한" || compact === "한국사") return "historyGrade";
  return null;
}

function parseCompetitionRate(value: string): number | null {
  const normalized = cleanCell(value).replace(",", "");
  const match = normalized.match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function parseIntegerCell(value: string): number | null {
  const number = parseNumberCell(value);
  return number === null ? null : Math.trunc(number);
}

function parseNumberCell(value: string): number | null {
  const normalized = cleanCell(value).replaceAll(",", "");
  if (normalized.length === 0 || normalized === "-") return null;
  const match = normalized.match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

function isNumericLike(value: string): boolean {
  return /^[-+]?\d[\d,]*(?:\.\d+)?(?:\s*:\s*1)?$/.test(cleanCell(value));
}

function cleanCell(value: string | undefined): string {
  return (value ?? "")
    .replace(/\s+/g, " ")
    .replace(/^(?:\/\s*)+/, "")
    .replace(/(?:\s*\/)+$/, "")
    .trim();
}

function tableTextFromGrid(grid: string[][]): string {
  return grid
    .flat()
    .map(cleanCell)
    .filter(Boolean)
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
}

function headerText(grid: string[][]): string {
  return tableTextFromGrid(grid.slice(0, Math.min(4, grid.length))).slice(0, 500);
}

function maxCols(grid: string[][]): number {
  return grid.reduce((max, row) => Math.max(max, row.length), 0);
}

function htmlToText(html: string): string {
  return decodeHtmlEntities(
    html
      .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
      .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
      .replace(/<br\s*\/?>/gi, " / ")
      .replace(/<\/p>/gi, " / ")
      .replace(/<[^>]+>/g, " "),
  )
    .replace(/\s*\/\s*(?:\/\s*)+/g, " / ")
    .replace(/\s+/g, " ")
    .trim();
}

function decodeHtmlEntities(value: string): string {
  return value
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&nbsp;", " ")
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">");
}

async function loadManifestYear(
  publicDir: string,
  year: number,
): Promise<DetailManifest[]> {
  const manifestPath = path.join(publicDir, `adiga_selection_manifest_${year}.jsonl`);
  const content = await readFile(manifestPath, "utf8");
  return content
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as DetailManifest);
}

async function writeJsonl<T>(filePath: string, rows: T[]) {
  await writeFile(filePath, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

const outcomeHeaders: Array<keyof OutcomeCandidate> = [
  "provider",
  "artifactType",
  "year",
  "unvCd",
  "universityName",
  "sourceUrl",
  "rawPath",
  "sectionId",
  "tableIndex",
  "rowIndex",
  "recruitmentGroup",
  "recruitmentGroupText",
  "admissionUnitName",
  "quota",
  "competitionRate",
  "additionalPass",
  "convertedScore50Cut",
  "convertedScore70Cut",
  "totalScore",
  "percentile70Average",
  "percentile50BySubjectJson",
  "percentile70BySubjectJson",
  "mathSelectionRatioJson",
  "sourceConfidence",
];

async function writeCsv<T extends Record<string, unknown>>(
  filePath: string,
  rows: T[],
  headers: Array<keyof T>,
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

function parseArgs(args: string[]): Options {
  const options: Options = {
    repoRoot: process.cwd(),
    years: DEFAULT_YEARS,
    publicDir: DEFAULT_PUBLIC_DIR,
    outputDir: DEFAULT_OUTPUT_DIR,
    limit: null,
    unvCds: null,
  };

  for (const arg of args) {
    if (arg === "--") continue;

    if (arg.startsWith("--years=")) {
      options.years = parseNumberList(arg.slice("--years=".length));
    } else if (arg.startsWith("--public-dir=")) {
      options.publicDir = arg.slice("--public-dir=".length);
    } else if (arg.startsWith("--out-dir=")) {
      options.outputDir = arg.slice("--out-dir=".length);
    } else if (arg.startsWith("--limit=")) {
      options.limit = Number(arg.slice("--limit=".length));
    } else if (arg.startsWith("--unv-cds=")) {
      options.unvCds = new Set(parseStringList(arg.slice("--unv-cds=".length)));
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
    outputDir: resolveFromRoot(repoRoot, options.outputDir),
  };
}

function resolveFromRoot(repoRoot: string, value: string): string {
  return path.isAbsolute(value) ? value : path.join(repoRoot, value);
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

function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

void main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
