#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_WORKBOOK_SHEETS = (
    "packages/reference-data/data/public/academyinfo/extracted/"
    "academyinfo_workbook_sheets_manifest.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/academyinfo/extracted"

CONTEXT_LABEL_PATTERNS = [
    ("survey_period", r"기준연도"),
    ("school_division", r"학교종류"),
    ("establishment_type", r"설립구분"),
    ("region", r"지역"),
    ("school_status", r"(?:^| > )상태(?:$| > )"),
    ("university_name", r"학교명|대학명|(?:^| > )학교(?:$| > )"),
    ("college_name", r"단과대학"),
    ("department_name", r"학과(?!특성|상태)|모집단위|전공"),
    ("program_shift", r"(?:^| > )구분(?:$| > )"),
    ("department_feature", r"학과특성"),
    ("department_status", r"학과상태"),
    ("quota_category", r"정원구분"),
    ("admission_track", r"전형유형"),
    ("admission_name_major", r"전형명.*대분류"),
    ("admission_name_middle", r"전형명.*중분류"),
    ("admission_name_minor", r"전형명.*소분류"),
    ("recruitment_period", r"모집시기"),
]
BASE_CONTEXT_TERMS = re.compile(
    r"기준연도|학교종류|설립구분|지역|(?:^| > )상태(?:$| > )|학교명|대학명|(?:^| > )학교(?:$| > )|"
    r"단과대학|학과|모집단위|전공|구분|학과특성|학과상태|정원구분|전형유형|전형명|모집시기"
)
METRIC_TERMS = re.compile(
    r"모집인원|등록인원|등록률|입학정원|지원자|입학자|재학생|충원율|학생정원|"
    r"학생모집정지|중도탈락|입학자수|학생수|비율|수입|지출|납부|총액|"
    r"사정관|평가|건수|전임|위촉|교수|전환|정규직|입학전형료|정원내|정원외"
)
TARGET_BY_ROLE = {
    "admission_type_selection_result": ["HistoricalOutcome", "ReferenceDataReview"],
    "freshman_fill_status": ["HistoricalOutcome", "ReferenceDataReview"],
    "student_fill_rate": ["ReferenceDataReview"],
    "transfer_selection_result": ["HistoricalOutcome", "ReferenceDataReview"],
    "dropout_status": ["ReferenceDataReview"],
    "freshman_high_school_type": ["ReferenceDataReview"],
    "contract_department_status": ["AdmissionRule", "ReferenceDataReview"],
    "admissions_fee_revenue": ["AdmissionRule", "ReferenceDataReview"],
    "admissions_fee_expense": ["AdmissionRule", "ReferenceDataReview"],
    "admissions_officer_status": ["AdmissionRule", "ReferenceDataReview"],
    "admissions_document_evaluation_load": ["AdmissionRule", "ReferenceDataReview"],
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    sheet_manifest_path = resolve(repo_root, args.workbook_sheets)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sheet_rows = load_jsonl(sheet_manifest_path)
    row_candidates: list[dict[str, Any]] = []
    column_label_rows: list[dict[str, Any]] = []
    for sheet in sheet_rows:
        if str(sheet.get("status") or "") != "extracted":
            continue
        csv_path_raw = str(sheet.get("csvPath") or "")
        if not csv_path_raw:
            continue
        csv_path = repo_root / csv_path_raw
        if not csv_path.exists():
            continue
        rows = read_csv_rows(csv_path)
        column_label_row = make_column_label_row(sheet, rows)
        if column_label_row:
            column_label_rows.append(column_label_row)
        row_candidates.extend(extract_candidates_for_sheet(sheet, rows, args))

    jsonl_path = output_dir / "academyinfo_row_candidates.jsonl"
    csv_path = output_dir / "academyinfo_row_candidates.csv"
    labels_path = output_dir / "academyinfo_sheet_column_labels.jsonl"
    summary_path = output_dir / "academyinfo_row_candidates_summary.json"
    write_jsonl(labels_path, column_label_rows)
    write_jsonl(jsonl_path, row_candidates)
    write_csv_index(csv_path, row_candidates)
    summary = summarize(sheet_rows, column_label_rows, row_candidates)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "academyinfo row candidate extraction complete. "
        f"sheets={summary['sourceSheets']} rowCandidates={summary['rowCandidates']} "
        f"metricValues={summary['metricValues']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workbook-sheets", default=DEFAULT_WORKBOOK_SHEETS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-metrics-per-row", type=int, default=80)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = []
    raw_args = __import__("sys").argv[1:]
    if raw_args[:1] == ["--"]:
        raw_args = raw_args[1:]
    args.extend(raw_args)
    return args


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while True:
        if (current / "pnpm-workspace.yaml").exists():
            return current
        if current.parent == current:
            return start.resolve()
        current = current.parent


def resolve(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [[normalize_cell(cell) for cell in row] for row in csv.reader(handle)]


def make_column_label_row(sheet: dict[str, Any], rows: list[list[str]]) -> dict[str, Any] | None:
    data_start_index = detect_data_start_index(rows)
    if data_start_index is None:
        return None
    header_start_index = detect_header_start_index(rows, data_start_index)
    header_rows = rows[header_start_index:data_start_index]
    column_labels = build_column_labels(header_rows, max_cols(rows))
    context_columns = context_column_indexes(column_labels)
    context_col_count = leading_context_column_count(column_labels, context_columns)
    label_sha = column_label_sha(column_labels)
    return {
        "provider": "academyinfo",
        "artifactType": "academyinfo_sheet_column_labels",
        "surveyYear": sheet.get("surveyYear"),
        "itemId": sheet.get("itemId"),
        "itemDivCd": sheet.get("itemDivCd"),
        "relevanceRole": sheet.get("relevanceRole"),
        "outputKindCode": sheet.get("outputKindCode"),
        "outputKindLabel": sheet.get("outputKindLabel"),
        "sheetName": sheet.get("sheetName"),
        "csvPath": sheet.get("csvPath"),
        "headerStartRow": header_start_index + 1,
        "dataStartRow": data_start_index + 1,
        "contextColumnCount": context_col_count,
        "contextColumns": {key: value + 1 for key, value in context_columns.items()},
        "columnLabels": column_labels,
        "columnLabelSetSha256": label_sha,
    }


def extract_candidates_for_sheet(
    sheet: dict[str, Any],
    rows: list[list[str]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    data_start_index = detect_data_start_index(rows)
    if data_start_index is None:
        return []

    header_start_index = detect_header_start_index(rows, data_start_index)
    header_rows = rows[header_start_index:data_start_index]
    column_labels = build_column_labels(header_rows, max_cols(rows))
    label_sha = column_label_sha(column_labels)
    context_columns = context_column_indexes(column_labels)
    context_col_count = leading_context_column_count(column_labels, context_columns)
    context_values: dict[int, str] = {}
    candidates: list[dict[str, Any]] = []

    for row_index_0, row in enumerate(rows[data_start_index:], start=data_start_index):
        cells = pad_row([normalize_cell(cell) for cell in row], len(column_labels))
        if not any(cells):
            continue
        filled_cells = fill_context_cells(cells, context_values, context_col_count, context_columns)
        remember_context_values(context_values, cells, context_col_count, context_columns)

        context = extract_context(column_labels, filled_cells)
        metric_values = extract_metric_values(
            column_labels,
            filled_cells,
            context_columns,
            max_metrics=args.max_metrics_per_row,
        )
        if not is_candidate_row(context, metric_values):
            continue

        candidate = make_candidate(
            sheet=sheet,
            row_index=row_index_0 + 1,
            data_start_row=data_start_index + 1,
            header_start_row=header_start_index + 1,
            column_labels=column_labels,
            column_label_sha=label_sha,
            context=context,
            metric_values=metric_values,
            row=filled_cells,
        )
        candidates.append(candidate)

    return candidates


def detect_data_start_index(rows: list[list[str]]) -> int | None:
    for index, row in enumerate(rows):
        cells = [normalize_cell(cell) for cell in row]
        if len(cells) < 2:
            continue
        if cells[1] == "대학교" and count_numeric_cells(cells) >= 1:
            return index
        if re.match(r"^20\d{2}(?:\d{2})?(?:\s*년\s*(?:상반기|하반기)?)?$", cells[0]) and (
            "대학교" in cells[:3] or count_numeric_cells(cells) >= 2
        ):
            return index
    return None


def detect_header_start_index(rows: list[list[str]], data_start_index: int) -> int:
    for index in range(data_start_index):
        if any("기준연도" in normalize_cell(cell) for cell in rows[index]):
            return index
    return max(0, data_start_index - 4)


def build_column_labels(header_rows: list[list[str]], width: int) -> list[str]:
    filled_header_rows = [fill_header_row(pad_row(row, width)) for row in header_rows]
    labels: list[str] = []
    for col_index in range(width):
        parts: list[str] = []
        for row in filled_header_rows:
            value = normalize_cell(row[col_index])
            if not value:
                continue
            if parts and parts[-1] == value:
                continue
            parts.append(value)
        labels.append(" > ".join(parts) if parts else f"col_{col_index + 1}")
    return labels


def fill_header_row(row: list[str]) -> list[str]:
    filled: list[str] = []
    current = ""
    for value in row:
        cell = normalize_cell(value)
        if cell:
            current = cell
            filled.append(cell)
        else:
            filled.append(current)
    return filled


def context_column_indexes(column_labels: list[str]) -> dict[str, int]:
    indexes: dict[str, int] = {}
    for field, pattern in CONTEXT_LABEL_PATTERNS:
        regex = re.compile(pattern)
        for index, label in enumerate(column_labels):
            if field in indexes:
                break
            if regex.search(label):
                indexes[field] = index
    return indexes


def leading_context_column_count(
    column_labels: list[str],
    context_columns: dict[str, int],
) -> int:
    first_metric = len(column_labels)
    for index, label in enumerate(column_labels):
        if METRIC_TERMS.search(label) and not BASE_CONTEXT_TERMS.search(label):
            first_metric = index
            break
    explicit_context_max = max(context_columns.values(), default=-1) + 1
    return max(first_metric, explicit_context_max)


def fill_context_cells(
    cells: list[str],
    context_values: dict[int, str],
    context_col_count: int,
    context_columns: dict[str, int],
) -> list[str]:
    filled = list(cells)
    carry_indexes = set(range(min(context_col_count, len(filled))))
    carry_indexes.update(context_columns.values())
    for index in carry_indexes:
        if index < len(filled) and not filled[index] and context_values.get(index):
            filled[index] = context_values[index]
    return filled


def remember_context_values(
    context_values: dict[int, str],
    cells: list[str],
    context_col_count: int,
    context_columns: dict[str, int],
) -> None:
    carry_indexes = set(range(min(context_col_count, len(cells))))
    carry_indexes.update(context_columns.values())
    for index in carry_indexes:
        if index >= len(cells):
            continue
        value = cells[index]
        if value:
            context_values[index] = value


def extract_context(column_labels: list[str], cells: list[str]) -> dict[str, str]:
    indexes = context_column_indexes(column_labels)
    context: dict[str, str] = {}
    for field, index in indexes.items():
        if index < len(cells):
            context[field] = cells[index]
    return context


def extract_metric_values(
    column_labels: list[str],
    cells: list[str],
    context_columns: dict[str, int],
    max_metrics: int,
) -> list[dict[str, Any]]:
    context_index_set = set(context_columns.values())
    metrics: list[dict[str, Any]] = []
    for index, value in enumerate(cells):
        if index in context_index_set:
            continue
        if not value or value in {"-", "–", "—"}:
            continue
        numeric_value = parse_number_or_none(value)
        if numeric_value is None:
            continue
        metrics.append(
            {
                "colIndex": index + 1,
                "raw": value,
                "value": numeric_value,
            }
        )
        if len(metrics) >= max_metrics:
            break
    return metrics


def is_candidate_row(context: dict[str, str], metric_values: list[dict[str, Any]]) -> bool:
    if not metric_values:
        return False
    if context.get("school_division") != "대학교":
        return False
    if not context.get("university_name"):
        return False
    return True


def make_candidate(
    *,
    sheet: dict[str, Any],
    row_index: int,
    data_start_row: int,
    header_start_row: int,
    column_labels: list[str],
    column_label_sha: str,
    context: dict[str, str],
    metric_values: list[dict[str, Any]],
    row: list[str],
) -> dict[str, Any]:
    relevance_role = str(sheet.get("relevanceRole") or "")
    payload = {
        "csvPath": sheet.get("csvPath"),
        "rowIndex": row_index,
        "context": context,
        "metrics": metric_values,
    }
    candidate_sha = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    row_text = " | ".join(cell for cell in row if cell)
    return {
        "provider": "academyinfo",
        "artifactType": "academyinfo_row_candidate",
        "surveyYear": sheet.get("surveyYear"),
        "itemId": sheet.get("itemId"),
        "itemDivCd": sheet.get("itemDivCd"),
        "relevanceRole": relevance_role,
        "pacerTargets": sheet.get("pacerTargets") or TARGET_BY_ROLE.get(relevance_role, []),
        "outputKindCode": sheet.get("outputKindCode"),
        "outputKindLabel": sheet.get("outputKindLabel"),
        "sheetName": sheet.get("sheetName"),
        "rowIndex": row_index,
        "dataStartRow": data_start_row,
        "headerStartRow": header_start_row,
        "observedSurveyPeriod": context.get("survey_period", ""),
        "universityName": context.get("university_name", ""),
        "region": context.get("region", ""),
        "establishmentType": context.get("establishment_type", ""),
        "schoolStatus": context.get("school_status", ""),
        "departmentName": context.get("department_name", ""),
        "collegeName": context.get("college_name", ""),
        "admissionTrack": context.get("admission_track", ""),
        "admissionNameMajor": context.get("admission_name_major", ""),
        "admissionNameMiddle": context.get("admission_name_middle", ""),
        "admissionNameMinor": context.get("admission_name_minor", ""),
        "quotaCategory": context.get("quota_category", ""),
        "recruitmentPeriod": context.get("recruitment_period", ""),
        "programShift": context.get("program_shift", ""),
        "context": context,
        "metricCount": len(metric_values),
        "metricValues": metric_values,
        "columnLabelSetSha256": column_label_sha,
        "rowPreview": row_text[:900],
        "sourceZipPath": sheet.get("sourceZipPath"),
        "academyinfoFileName": sheet.get("academyinfoFileName"),
        "innerWorkbookName": sheet.get("innerWorkbookName"),
        "innerWorkbookSha256": sheet.get("innerWorkbookSha256"),
        "csvPath": sheet.get("csvPath"),
        "sheetSha256": sheet.get("sha256"),
        "candidateSha256": candidate_sha,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "status": "candidate",
        "reviewRequired": True,
    }


def normalize_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("\ufeff", "")).strip()


def parse_number_or_none(value: str) -> float | None:
    text = normalize_cell(value)
    if not re.fullmatch(r"[-+]?\d[\d,]*(?:\.\d+)?%?", text):
        return None
    return float(text.rstrip("%").replace(",", ""))


def count_numeric_cells(cells: list[str]) -> int:
    return sum(1 for cell in cells if parse_number_or_none(cell) is not None)


def max_cols(rows: list[list[str]]) -> int:
    return max((len(row) for row in rows), default=0)


def column_label_sha(column_labels: list[str]) -> str:
    return hashlib.sha256(
        json.dumps(column_labels, ensure_ascii=False, sort_keys=False).encode("utf-8")
    ).hexdigest()


def pad_row(row: list[str], width: int) -> list[str]:
    if len(row) >= width:
        return row[:width]
    return [*row, *([""] * (width - len(row)))]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "surveyYear",
        "observedSurveyPeriod",
        "itemId",
        "relevanceRole",
        "outputKindLabel",
        "rowIndex",
        "universityName",
        "region",
        "departmentName",
        "admissionTrack",
        "admissionNameMajor",
        "admissionNameMiddle",
        "admissionNameMinor",
        "metricCount",
        "columnLabelSetSha256",
        "csvPath",
        "candidateSha256",
        "rowPreview",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def summarize(
    sheet_rows: list[dict[str, Any]],
    column_label_rows: list[dict[str, Any]],
    row_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "academyinfo",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceSheets": len(sheet_rows),
        "columnLabelSets": len(column_label_rows),
        "uniqueColumnLabelSetSha256": len(
            {row["columnLabelSetSha256"] for row in column_label_rows}
        ),
        "rowCandidates": len(row_candidates),
        "uniqueCandidateSha256": len({row["candidateSha256"] for row in row_candidates}),
        "metricValues": sum(int(row.get("metricCount") or 0) for row in row_candidates),
        "universities": len({row.get("universityName") for row in row_candidates if row.get("universityName")}),
        "departments": len({row.get("departmentName") for row in row_candidates if row.get("departmentName")}),
        "bySurveyYear": count_by(row_candidates, "surveyYear"),
        "byRelevanceRole": count_by(row_candidates, "relevanceRole"),
        "byOutputKind": count_by(row_candidates, "outputKindLabel"),
        "notes": [
            "Rows are review candidates derived from official Academyinfo public XLSX sheets.",
            "Blank merged-label context cells are filled forward for school/department/admission context only.",
            "Academyinfo rows are auxiliary evidence and must be reviewed before promotion into operational AdmissionRule or HistoricalOutcome data.",
        ],
    }


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


if __name__ == "__main__":
    main()
