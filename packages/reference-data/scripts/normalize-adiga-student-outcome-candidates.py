#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT_GLOB = (
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_extracted_tables_*.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/foundation"

OUTPUT_JSONL = "foundation_adiga_student_outcome_review_candidates.jsonl"
OUTPUT_CSV = "foundation_adiga_student_outcome_review_candidates.csv"
OUTPUT_SUMMARY = "foundation_adiga_student_outcome_review_candidates_summary.json"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_paths = resolve_globs(repo_root, args.input_glob)
    rows: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []
    for path in input_paths:
        table_count = 0
        row_count = 0
        for table in read_jsonl(path):
            if normalize_text(table.get("tableRole")) != "student_outcome":
                continue
            table_count += 1
            extracted = extract_student_outcome_rows(table)
            row_count += len(extracted)
            rows.extend(extracted)
        source_summaries.append(
            {
                "path": to_repo_relative(path, repo_root),
                "sha256": sha256_file(path),
                "studentOutcomeTables": table_count,
                "candidateRows": row_count,
            }
        )

    rows.sort(
        key=lambda row: (
            int_or_none(row.get("year")) or 9999,
            normalize_text(row.get("universityName")),
            int_or_none(row.get("tableIndex")) or 9999,
            int_or_none(row.get("rowIndex")) or 9999,
            int_or_none(row.get("blockIndex")) or 9999,
            normalize_text(row.get("admissionUnitName")),
        )
    )
    write_jsonl(output_dir / OUTPUT_JSONL, rows)
    write_csv(output_dir / OUTPUT_CSV, rows)
    summary = summarize(repo_root, input_paths, source_summaries, rows)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "adiga student outcome review candidates complete. "
        f"sources={len(input_paths)} rows={len(rows)} "
        f"tables={summary['tables']['studentOutcome']} "
        f"withQuotaCompetition={summary['rows']['withQuotaAndCompetition']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


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


def resolve_globs(repo_root: Path, pattern: str) -> list[Path]:
    path = Path(pattern)
    absolute_pattern = str(path if path.is_absolute() else repo_root / path)
    return [Path(match) for match in sorted(glob.glob(absolute_pattern))]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def extract_student_outcome_rows(table: dict[str, Any]) -> list[dict[str, Any]]:
    grid = clean_grid(table.get("grid"))
    if len(grid) < 2:
        return []
    blocks = infer_blocks(grid)
    candidates: list[dict[str, Any]] = []
    for block_index, block in enumerate(blocks, start=1):
        first_row = first_data_row(grid, block["unit"])
        if first_row is None:
            continue
        for row_index in range(first_row, len(grid)):
            row = grid[row_index]
            unit_name = clean_cell(value_at(row, block["unit"]))
            if not is_likely_admission_unit_name(unit_name):
                continue
            candidate = make_candidate(table, grid, row, row_index, block, block_index, unit_name)
            if candidate_has_signal(candidate):
                candidates.append(candidate)
    return candidates


def clean_grid(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    rows: list[list[str]] = []
    for row in value:
        if isinstance(row, list):
            rows.append([clean_cell(cell) for cell in row])
    return rows


def infer_blocks(grid: list[list[str]]) -> list[dict[str, Any]]:
    width = max_cols(grid)
    unit_columns = [
        column
        for column in range(width)
        if re.search(r"모집\s*/?\s*단위|모집단위", column_header(grid, column))
    ]
    if not unit_columns:
        return []
    blocks: list[dict[str, Any]] = []
    for index, unit_col in enumerate(unit_columns):
        end_col = unit_columns[index + 1] if index + 1 < len(unit_columns) else width
        if end_col - unit_col < 3:
            continue
        blocks.append(
            {
                "unit": unit_col,
                "end": end_col,
                "screeningName": infer_screening_name(grid, unit_col, end_col),
                "quota": find_column(grid, unit_col, end_col, r"모집\s*/?\s*인원|모집인원"),
                "competition": find_column(grid, unit_col, end_col, r"경쟁률"),
                "additionalPass": find_column(grid, unit_col, end_col, r"충원"),
                "converted70": find_converted_score_70_column(grid, unit_col, end_col),
                "convertedMax": find_column(grid, unit_col, end_col, r"최고점|만점|총점"),
                "studentGrade50": find_student_grade_column(grid, unit_col, end_col, "50"),
                "studentGrade70": find_student_grade_column(grid, unit_col, end_col, "70"),
            }
        )
    return blocks


def infer_screening_name(grid: list[list[str]], start: int, end: int) -> str:
    header_rows = grid[: min(3, len(grid))]
    values: list[str] = []
    for row in header_rows:
        for column in range(start + 1, end):
            value = clean_cell(value_at(row, column))
            if not value or is_header_noise(value):
                continue
            values.append(value)
        if values:
            break
    return normalize_text(values[0]) if values else ""


def find_column(grid: list[list[str]], start: int, end: int, pattern: str) -> int | None:
    compiled = re.compile(pattern)
    for column in range(start, end):
        if compiled.search(column_header(grid, column)):
            return column
    return None


def find_converted_score_70_column(grid: list[list[str]], start: int, end: int) -> int | None:
    percent_pattern = re.compile(r"70\s*%|70%|70\s*퍼센트")
    converted_score_signal = re.compile(r"대학별\s*환산|환산점수|전형총점|반영총점")
    grade_signal = re.compile(r"교과성적|내신|등급|환산등급")
    for column in range(start, end):
        header = column_header(grid, column)
        if percent_pattern.search(header) and converted_score_signal.search(header) and not grade_signal.search(header):
            return column
    for column in range(start, end):
        header = column_header(grid, column)
        if converted_score_signal.search(header) and not grade_signal.search(header):
            return column
    return None


def find_student_grade_column(grid: list[list[str]], start: int, end: int, percent: str) -> int | None:
    percent_pattern = re.compile(rf"{percent}\s*%|{percent}%|{percent}\s*퍼센트")
    grade_signal = re.compile(r"학생부|교과성적|내신|등급|환산등급")
    converted_score_signal = re.compile(r"대학별\s*환산|환산점수|최고점|만점|총점")
    fallback_signal = re.compile(r"환산등급|학생부.*등급|교과성적")
    for column in range(start, end):
        header = column_header(grid, column)
        if not percent_pattern.search(header):
            continue
        if grade_signal.search(header) and not converted_score_signal.search(header):
            return column
    for column in range(start, end):
        header = column_header(grid, column)
        if fallback_signal.search(header) and not converted_score_signal.search(header):
            return column
    return None


def column_header(grid: list[list[str]], column: int) -> str:
    return normalize_text(" ".join(value_at(row, column) for row in grid[: min(4, len(grid))]))


def first_data_row(grid: list[list[str]], unit_col: int) -> int | None:
    for row_index, row in enumerate(grid):
        unit = clean_cell(value_at(row, unit_col))
        if is_likely_admission_unit_name(unit):
            return row_index
    return None


def make_candidate(
    table: dict[str, Any],
    grid: list[list[str]],
    row: list[str],
    row_index: int,
    block: dict[str, Any],
    block_index: int,
    unit_name: str,
) -> dict[str, Any]:
    quota_raw = value_at(row, block["quota"])
    competition_raw = value_at(row, block["competition"])
    additional_raw = value_at(row, block["additionalPass"])
    converted70_raw = value_at(row, block["converted70"])
    converted_max_raw = value_at(row, block["convertedMax"])
    grade50_raw = value_at(row, block["studentGrade50"])
    grade70_raw = value_at(row, block["studentGrade70"])
    metric_values = metric_values_for(
        {
            "quota": quota_raw,
            "competitionRate": competition_raw,
            "additionalPass": additional_raw,
            "convertedScore70Cut": converted70_raw,
            "convertedScoreMax": converted_max_raw,
            "studentGrade50Cut": grade50_raw,
            "studentGrade70Cut": grade70_raw,
        }
    )
    candidate_key = {
        "year": int_or_none(table.get("year")),
        "unvCd": normalize_text(table.get("unvCd")),
        "tableSha256": normalize_text(table.get("tableSha256")),
        "rowIndex": row_index + 1,
        "blockIndex": block_index,
        "unitName": unit_name,
    }
    candidate_id = hashlib.sha256(
        json.dumps(candidate_key, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    quota = number_or_none(quota_raw)
    competition = number_or_none(competition_raw)
    additional = number_or_none(additional_raw)
    converted70 = number_or_none(converted70_raw)
    grade50 = number_or_none(grade50_raw)
    grade70 = number_or_none(grade70_raw)
    return {
        "studentOutcomeCandidateId": candidate_id,
        "provider": "adiga",
        "artifactType": "foundation_adiga_student_outcome_review_candidate",
        "evidenceTarget": "HistoricalOutcome",
        "pacerTargets": "HistoricalOutcome|AdmissionUnit|ReferenceDataReview",
        "year": int_or_none(table.get("year")) or "",
        "unvCd": normalize_text(table.get("unvCd")),
        "universityName": normalize_text(table.get("universityName")),
        "admissionTrack": "student_record",
        "screeningName": normalize_text(block.get("screeningName")),
        "admissionUnitName": unit_name,
        "admissionUnitCanonicalCandidate": canonical_unit_name(unit_name),
        "quota": quota if quota is not None else "",
        "competitionRate": competition if competition is not None else "",
        "additionalPass": additional if additional is not None else "",
        "convertedScore70Cut": converted70 if converted70 is not None else "",
        "convertedScoreMax": number_or_none(converted_max_raw) or "",
        "studentGrade50Cut": grade50 if grade50 is not None else "",
        "studentGrade70Cut": grade70 if grade70 is not None else "",
        "quotaRaw": normalize_text(quota_raw),
        "competitionRateRaw": normalize_text(competition_raw),
        "additionalPassRaw": normalize_text(additional_raw),
        "convertedScore70CutRaw": normalize_text(converted70_raw),
        "convertedScoreMaxRaw": normalize_text(converted_max_raw),
        "studentGrade50CutRaw": normalize_text(grade50_raw),
        "studentGrade70CutRaw": normalize_text(grade70_raw),
        "metricValuesJson": json.dumps(metric_values, ensure_ascii=False, sort_keys=True),
        "metricCount": len(metric_values),
        "hasQuotaAndCompetition": bool(quota is not None and competition is not None),
        "hasStudentOutcomeScore": bool(converted70 is not None or grade50 is not None or grade70 is not None),
        "maskedOrApproximateValues": bool(any(metric.get("valueStatus") != "exact" for metric in metric_values)),
        "sourceConfidence": "parsed_candidate",
        "sourceUrl": normalize_text(table.get("sourceUrl")),
        "rawPath": normalize_text(table.get("rawPath")),
        "sectionId": normalize_text(table.get("sectionId")),
        "sectionLabel": normalize_text(table.get("sectionLabel")),
        "tableIndex": int_or_none(table.get("tableIndex")) or "",
        "rowIndex": row_index + 1,
        "blockIndex": block_index,
        "tableSha256": normalize_text(table.get("tableSha256")),
        "rowText": normalize_text(" ".join(row))[:700],
        "tableHeaderText": normalize_text(table.get("headerText"))[:700],
        "reviewStatus": "needs_human_verification",
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }


def metric_values_for(raw_values: dict[str, str]) -> list[dict[str, Any]]:
    labels = {
        "quota": "모집인원",
        "competitionRate": "경쟁률",
        "additionalPass": "충원",
        "convertedScore70Cut": "대학별환산_70컷",
        "convertedScoreMax": "대학별환산_최고점",
        "studentGrade50Cut": "학생부등급_50컷",
        "studentGrade70Cut": "학생부등급_70컷",
    }
    metrics: list[dict[str, Any]] = []
    for field, raw in raw_values.items():
        value = number_or_none(raw)
        if value is None:
            continue
        text = normalize_text(raw)
        metrics.append(
            {
                "field": field,
                "label": labels[field],
                "raw": text,
                "value": value,
                "valueStatus": "masked_or_rounded" if re.search(r"[xX×]", text) else "exact",
            }
        )
    return metrics


def candidate_has_signal(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("quota")
        or candidate.get("competitionRate")
        or candidate.get("additionalPass")
        or candidate.get("convertedScore70Cut")
        or candidate.get("studentGrade50Cut")
        or candidate.get("studentGrade70Cut")
    )


def is_likely_admission_unit_name(value: str) -> bool:
    text = normalize_text(value)
    if not text:
        return False
    if text in {"-", "해당없음", "없음", "전체", "계", "합계", "소계"}:
        return False
    if is_all_admission_units_value(text):
        return True
    if is_header_noise(text):
        return False
    if number_or_none(text) is not None:
        return False
    return bool(re.search(r"[가-힣]", text))


def is_all_admission_units_value(value: str) -> bool:
    compact = re.sub(r"[\s/]+", "", value)
    return compact in {"전모집단위", "전체모집단위"}


def is_header_noise(value: str) -> bool:
    if is_all_admission_units_value(value):
        return False
    compact = re.sub(r"\s+", "", value)
    return bool(
        compact in {
            "모집단위",
            "모집인원",
            "경쟁률",
            "충원인원",
            "충원합격순위",
            "대학별환산",
            "환산점수",
            "최종등록자",
            "학생부교과성적",
            "구분",
            "계열",
        }
        or re.search(r"최종등록자|대학별환산|학생부.*등급|모집단위|모집인원|경쟁률|충원", value)
    )


def max_cols(grid: list[list[str]]) -> int:
    return max((len(row) for row in grid), default=0)


def value_at(row: list[str], column: int | None) -> str:
    if column is None:
        return ""
    return row[column] if 0 <= column < len(row) else ""


def clean_cell(value: Any) -> str:
    text = (
        normalize_text(value)
        .replace(" /", "/")
        .replace("/ ", "/")
        .replace("/", " / ")
        .replace("7 0%", "70%")
        .strip()
    )
    return re.sub(r"(^/\s*|\s*/$)", "", text).strip()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_unit_name(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("·", "").replace("/", ""))


def number_or_none(value: Any) -> float | None:
    text = normalize_text(value).replace(",", "")
    text = re.sub(r"(?<=\d)\.\s+(?=\d)", ".", text)
    if not text or text in {"-", "–", "—", "/"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    return float(match.group(0)) if match else None


def int_or_none(value: Any) -> int | None:
    number = number_or_none(value)
    return int(number) if number is not None else None


def summarize(
    repo_root: Path,
    input_paths: list[Path],
    source_summaries: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_adiga_student_outcome_review_candidates_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in input_paths
        ],
        "sources": source_summaries,
        "tables": {
            "studentOutcome": sum(int(row["studentOutcomeTables"]) for row in source_summaries),
        },
        "rows": {
            "total": len(rows),
            "withQuotaAndCompetition": sum(1 for row in rows if row.get("hasQuotaAndCompetition")),
            "withStudentOutcomeScore": sum(1 for row in rows if row.get("hasStudentOutcomeScore")),
            "maskedOrApproximate": sum(1 for row in rows if row.get("maskedOrApproximateValues")),
        },
        "byYear": dict(sorted(Counter(str(row.get("year")) for row in rows).items())),
        "topUniversities": counter_rows(Counter(str(row.get("universityName")) for row in rows), 30),
        "notes": [
            "Rows preserve public Adiga student-record outcome tables as review candidates, not verified operational HistoricalOutcome records.",
            "Masked values such as 3.0X are kept in raw fields and marked masked_or_rounded in metricValuesJson.",
            "This artifact intentionally stays separate from CSAT-track HistoricalOutcome candidates until schema and human verification policy decide how to promote student-record outcomes.",
        ],
    }


def counter_rows(counter: Counter[str], limit: int = 20) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in counter.most_common(limit)
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "studentOutcomeCandidateId",
        "provider",
        "artifactType",
        "evidenceTarget",
        "pacerTargets",
        "year",
        "unvCd",
        "universityName",
        "admissionTrack",
        "screeningName",
        "admissionUnitName",
        "admissionUnitCanonicalCandidate",
        "quota",
        "competitionRate",
        "additionalPass",
        "convertedScore70Cut",
        "convertedScoreMax",
        "studentGrade50Cut",
        "studentGrade70Cut",
        "quotaRaw",
        "competitionRateRaw",
        "additionalPassRaw",
        "convertedScore70CutRaw",
        "convertedScoreMaxRaw",
        "studentGrade50CutRaw",
        "studentGrade70CutRaw",
        "metricValuesJson",
        "metricCount",
        "hasQuotaAndCompetition",
        "hasStudentOutcomeScore",
        "maskedOrApproximateValues",
        "sourceConfidence",
        "sourceUrl",
        "rawPath",
        "sectionId",
        "sectionLabel",
        "tableIndex",
        "rowIndex",
        "blockIndex",
        "tableSha256",
        "rowText",
        "tableHeaderText",
        "reviewStatus",
        "extractedAt",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
