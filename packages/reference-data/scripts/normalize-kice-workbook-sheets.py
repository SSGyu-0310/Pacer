#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = "packages/reference-data/data/public/kice/extracted/kice_suneung_workbook_sheets_manifest.jsonl"
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/kice/extracted"

GRADE_CUT_FIELDS = [
    "provider",
    "artifact_type",
    "academic_year",
    "exam_type",
    "file_kind",
    "score_metric",
    "subject_area",
    "subject_name",
    "subject_name_normalized",
    "grade",
    "cut_score_raw",
    "cut_score_numeric",
    "cut_score_operator",
    "test_taker_count",
    "ratio_percent",
    "value_status",
    "board_seq",
    "file_seq",
    "file_title",
    "sheet_name",
    "source_url",
    "view_url",
    "csv_path",
    "source_row_number",
    "source_column_number",
]

DISTRIBUTION_FIELDS = [
    "provider",
    "artifact_type",
    "academic_year",
    "exam_type",
    "subject_area",
    "subject_name",
    "subject_name_normalized",
    "standard_score",
    "male_count",
    "female_count",
    "total_count",
    "cumulative_total_count",
    "value_status",
    "board_seq",
    "file_seq",
    "file_title",
    "sheet_name",
    "source_url",
    "view_url",
    "csv_path",
    "source_row_number",
    "source_column_number",
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    manifest_path = resolve(repo_root, args.manifest)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sheet_rows = load_jsonl(manifest_path)
    grade_cut_rows: list[dict[str, Any]] = []
    distribution_rows: list[dict[str, Any]] = []

    for sheet in sheet_rows:
        if sheet.get("status") != "extracted":
            continue
        csv_path_value = sheet.get("csvPath")
        if not csv_path_value:
            continue
        csv_path = repo_root / str(csv_path_value)
        rows = read_csv(csv_path)
        file_kind = str(sheet.get("fileKind") or "")

        if file_kind in {"grade_cut_standard_score_xlsx", "absolute_grade_cut_xlsx"}:
            if "등급구분점수" in str(sheet.get("sheetName") or ""):
                grade_cut_rows.extend(parse_grade_cut_rows(sheet, rows))
        elif file_kind == "standard_score_distribution_xlsx":
            if "표지" not in str(sheet.get("sheetName") or ""):
                distribution_rows.extend(parse_distribution_rows(sheet, rows))

    grade_cut_path = output_dir / "kice_grade_cut_candidates.csv"
    distribution_path = output_dir / "kice_standard_score_distribution_candidates.csv"
    summary_path = output_dir / "kice_normalized_summary.json"

    write_dict_csv(grade_cut_path, GRADE_CUT_FIELDS, grade_cut_rows)
    write_dict_csv(distribution_path, DISTRIBUTION_FIELDS, distribution_rows)

    summary = {
        "provider": "kice-suneung",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "gradeCutRows": len(grade_cut_rows),
        "standardScoreDistributionRows": len(distribution_rows),
        "gradeCutOutput": to_repo_relative(grade_cut_path, repo_root),
        "standardScoreDistributionOutput": to_repo_relative(distribution_path, repo_root),
        "gradeCutByAcademicYear": summarize_rows(grade_cut_rows, "academic_year"),
        "distributionByAcademicYear": summarize_rows(distribution_rows, "academic_year"),
        "gradeCutByExamType": summarize_rows(grade_cut_rows, "exam_type"),
        "distributionByExamType": summarize_rows(distribution_rows, "exam_type"),
        "gradeCutByFileKind": summarize_rows(grade_cut_rows, "file_kind"),
        "notes": [
            "candidate tables only; promotion to production reference data requires human verification",
            "legacy .xls attachments are included when they are present in the worksheet CSV manifest",
            "rows with official dash/blank values are retained with value_status=missing",
        ],
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "kice normalized table extraction complete. "
        f"gradeCutRows={len(grade_cut_rows)} "
        f"standardScoreDistributionRows={len(distribution_rows)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def parse_grade_cut_rows(sheet: dict[str, Any], rows: list[list[str]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    file_kind = str(sheet.get("fileKind") or "")
    score_metric = (
        "absolute_area_raw_score"
        if file_kind == "absolute_grade_cut_xlsx"
        else "standard_score"
    )

    for row_index, row in enumerate(rows):
        if normalize_cell(cell_at(row, 0)) != "등급":
            continue

        subject_starts = [
            col_index
            for col_index, value in enumerate(row[1:], start=1)
            if normalize_cell(value)
        ]
        if not subject_starts:
            continue

        subject_area = find_subject_area(rows, row_index)

        for data_index in range(row_index + 1, len(rows)):
            data_row = rows[data_index]
            first_cell = normalize_cell(cell_at(data_row, 0))
            if first_cell == "등급":
                break
            grade = parse_int(first_cell)
            if grade is None or not 1 <= grade <= 9:
                continue

            for subject_col in subject_starts:
                subject_name = normalize_subject(cell_at(row, subject_col))
                if not subject_name:
                    continue
                cut_score_raw = normalize_cell(cell_at(data_row, subject_col))
                count_raw = normalize_cell(cell_at(data_row, subject_col + 1))
                ratio_raw = normalize_cell(cell_at(data_row, subject_col + 2))
                if not any([cut_score_raw, count_raw, ratio_raw]):
                    continue

                cut_score_numeric, cut_score_operator = parse_score_value(cut_score_raw)
                count = parse_int(count_raw)
                ratio = parse_float(ratio_raw)
                value_status = (
                    "missing"
                    if cut_score_numeric is None and count is None and ratio is None
                    else "parsed"
                )

                parsed.append(
                    {
                        "provider": "kice-suneung",
                        "artifact_type": "kice_grade_cut_candidate",
                        "academic_year": sheet.get("academicYear"),
                        "exam_type": sheet.get("examType"),
                        "file_kind": file_kind,
                        "score_metric": score_metric,
                        "subject_area": subject_area,
                        "subject_name": subject_name,
                        "subject_name_normalized": compact_subject(subject_name),
                        "grade": grade,
                        "cut_score_raw": cut_score_raw,
                        "cut_score_numeric": cut_score_numeric,
                        "cut_score_operator": cut_score_operator,
                        "test_taker_count": count,
                        "ratio_percent": ratio,
                        "value_status": value_status,
                        **source_fields(sheet, data_index, subject_col),
                    }
                )

    return parsed


def parse_distribution_rows(sheet: dict[str, Any], rows: list[list[str]]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []

    for header_index, row in enumerate(rows):
        header_cells = [normalize_cell(value) for value in row]
        block_starts = [
            col_index
            for col_index, value in enumerate(header_cells)
            if value == "표준점수" and normalize_cell(cell_at(row, col_index + 1)) == "남자"
        ]
        if not block_starts:
            continue

        subject_row = rows[header_index - 1] if header_index > 0 else []
        subject_area = find_subject_area(rows, header_index)

        for data_index in range(header_index + 1, len(rows)):
            data_row = rows[data_index]
            if any(normalize_cell(value) == "표준점수" for value in data_row):
                break
            if normalize_cell(cell_at(data_row, 0)) == "계":
                break

            saw_numeric_score = False
            for subject_col in block_starts:
                subject_name = normalize_subject(cell_at(subject_row, subject_col))
                if not subject_name:
                    continue
                standard_score = parse_int(cell_at(data_row, subject_col))
                if standard_score is None:
                    continue
                saw_numeric_score = True
                male_count = parse_int(cell_at(data_row, subject_col + 1))
                female_count = parse_int(cell_at(data_row, subject_col + 2))
                total_count = parse_int(cell_at(data_row, subject_col + 3))
                cumulative_total_count = parse_int(cell_at(data_row, subject_col + 4))

                parsed.append(
                    {
                        "provider": "kice-suneung",
                        "artifact_type": "kice_standard_score_distribution_candidate",
                        "academic_year": sheet.get("academicYear"),
                        "exam_type": sheet.get("examType"),
                        "subject_area": subject_area,
                        "subject_name": subject_name,
                        "subject_name_normalized": compact_subject(subject_name),
                        "standard_score": standard_score,
                        "male_count": male_count,
                        "female_count": female_count,
                        "total_count": total_count,
                        "cumulative_total_count": cumulative_total_count,
                        "value_status": (
                            "missing"
                            if male_count is None
                            and female_count is None
                            and total_count is None
                            and cumulative_total_count is None
                            else "parsed"
                        ),
                        **source_fields(sheet, data_index, subject_col),
                    }
                )

            if not saw_numeric_score and row_is_blank(data_row):
                break

    return parsed


def source_fields(sheet: dict[str, Any], source_row_index: int, source_col_index: int) -> dict[str, Any]:
    return {
        "board_seq": sheet.get("boardSeq"),
        "file_seq": sheet.get("fileSeq"),
        "file_title": sheet.get("fileTitle"),
        "sheet_name": sheet.get("sheetName"),
        "source_url": sheet.get("sourceUrl"),
        "view_url": sheet.get("viewUrl"),
        "csv_path": sheet.get("csvPath"),
        "source_row_number": source_row_index + 1,
        "source_column_number": source_col_index + 1,
    }


def find_subject_area(rows: list[list[str]], current_index: int) -> str:
    for index in range(current_index, -1, -1):
        for value in rows[index]:
            normalized = normalize_cell(value)
            if is_subject_area(normalized):
                return normalized
    return ""


def is_subject_area(value: str) -> bool:
    if not value:
        return False
    if re.match(r"^\d+\.\s*", value):
        return True
    return "영역" in value and "도수분포" not in value and "등급 구분" not in value


def parse_score_value(value: str) -> tuple[int | None, str]:
    normalized = normalize_cell(value)
    if is_missing(normalized):
        return None, "missing"
    operator = "lt" if "미만" in normalized else "gte"
    match = re.search(r"\d+", normalized.replace(",", ""))
    if not match:
        return None, "missing"
    return int(match.group(0)), operator


def parse_int(value: Any) -> int | None:
    normalized = normalize_cell(value)
    if is_missing(normalized):
        return None
    if "미만" in normalized:
        return None
    normalized = normalized.replace(",", "")
    if re.fullmatch(r"-?\d+", normalized):
        return int(normalized)
    if re.fullmatch(r"-?\d+\.0+", normalized):
        return int(float(normalized))
    return None


def parse_float(value: Any) -> float | None:
    normalized = normalize_cell(value)
    if is_missing(normalized):
        return None
    normalized = normalized.replace(",", "")
    try:
        return float(normalized)
    except ValueError:
        return None


def is_missing(value: str) -> bool:
    return normalize_cell(value) in {"", "-", "ㅡ", "－", "–", "—"}


def normalize_subject(value: Any) -> str:
    value = normalize_cell(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def compact_subject(value: str) -> str:
    return re.sub(r"\s+", "", value)


def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def cell_at(row: list[str], index: int) -> str:
    if index < 0 or index >= len(row):
        return ""
    return row[index]


def row_is_blank(row: list[str]) -> bool:
    return all(not normalize_cell(value) for value in row)


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
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [[normalize_cell(value) for value in row] for row in csv.reader(file)]


def write_dict_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: "" if row.get(field) is None else row.get(field) for field in fields})


def summarize_rows(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counter = Counter(str(row.get(field) or "unknown") for row in rows)
    return [
        {field: key, "rows": value}
        for key, value in sorted(counter.items(), key=lambda item: item[0], reverse=True)
    ]


def to_repo_relative(path: Path, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root))


if __name__ == "__main__":
    main()
