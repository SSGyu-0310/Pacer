#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_WORKBOOK_SHEETS = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_workbook_sheets_manifest_2027.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"

TARGET_BY_ROW_ROLE = {
    "admission_result_row": "HistoricalOutcome",
    "competition_rate_row": "HistoricalOutcome",
    "recruitment_quota_row": "AdmissionRule",
    "screening_method_row": "AdmissionRule",
    "schedule_row": "AdmissionSchedule",
    "workbook_review_row": "ReviewQueue",
}
ADMISSION_DOMAIN_PATTERN = re.compile(
    r"모집|입시|입학|전형|정시|수시|수능|지원|경쟁률|합격|등록|충원|"
    r"모집단위|모집인원|성적|환산|백분위|등급|학생부|면접|실기|논술"
)
LIKELY_NON_ADMISSION_PATTERN = re.compile(
    r"testcard|visa|mastercard|credit\s*card|card\s*number|western\s+type|"
    r"check[-\s]?in|check[-\s]?out|passport|room|hotel|reservation|"
    r"wcc\d+|korea,\s*the\s+republic\s+of|@[a-z0-9_.+-]+|"
    r"호텔|숙박|예약번호|입실일|퇴실일|카드번호|카드소지자|룸타입|"
    r"합계금액|기본요금|전화번호|팩스|이메일",
    re.IGNORECASE,
)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    sheet_manifest_path = resolve(repo_root, args.workbook_sheets)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    sheet_rows = load_jsonl(sheet_manifest_path)
    row_candidates: list[dict[str, Any]] = []
    for sheet in sheet_rows:
        if int(sheet.get("year") or 0) != args.year:
            continue
        if str(sheet.get("status") or "") != "extracted":
            continue
        csv_path_raw = str(sheet.get("csvPath") or "")
        if not csv_path_raw:
            continue
        csv_path = repo_root / csv_path_raw
        if not csv_path.exists():
            continue
        table_rows = read_csv_rows(csv_path)
        row_candidates.extend(extract_sheet_row_candidates(sheet, table_rows, args))

    write_jsonl(
        output_dir / f"university_admission_workbook_row_candidates_{args.year}.jsonl",
        row_candidates,
    )
    write_csv_index(
        output_dir / f"university_admission_workbook_row_candidates_{args.year}.csv",
        row_candidates,
    )
    summary = summarize(args.year, sheet_rows, row_candidates)
    (output_dir / f"university_admission_workbook_row_candidates_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "university admission workbook row candidate extraction complete. "
        f"sheets={summary['sourceSheets']} rows={summary['rowCandidates']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--workbook-sheets", default=DEFAULT_WORKBOOK_SHEETS)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--context-cols", type=int, default=6)
    parser.add_argument("--header-context-rows", type=int, default=6)
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def read_csv_rows(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return [[normalize_cell(cell) for cell in row] for row in csv.reader(file)]


def extract_sheet_row_candidates(
    sheet: dict[str, Any],
    rows: list[list[str]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    context_values: dict[int, str] = {}
    previous_context_rows: list[dict[str, Any]] = []

    for row_index, row in enumerate(rows, start=1):
        cells = trim_trailing_empty(row)
        if not cells:
            continue

        filled_cells = fill_context_cells(cells, context_values, args.context_cols)
        row_text = row_text_from_cells(cells)
        filled_row_text = row_text_from_cells(filled_cells)
        numeric_values = numeric_values_for_row(cells)
        filled_numeric_values = numeric_values_for_row(filled_cells)
        row_role = detect_row_role(sheet, filled_row_text)
        row_type = detect_row_type(filled_row_text, numeric_values)

        if is_candidate_row(
            row_text=row_text,
            filled_row_text=filled_row_text,
            numeric_values=filled_numeric_values,
            row_role=row_role,
            row_type=row_type,
        ):
            candidates.append(
                make_candidate_row(
                    sheet=sheet,
                    row_index=row_index,
                    cells=cells,
                    filled_cells=filled_cells,
                    row_text=row_text,
                    filled_row_text=filled_row_text,
                    numeric_values=filled_numeric_values,
                    row_role=row_role,
                    row_type=row_type,
                    header_context_rows=previous_context_rows[-args.header_context_rows :],
                )
            )

        remember_context_values(context_values, cells, args.context_cols)
        if should_keep_as_header_context(cells, numeric_values):
            previous_context_rows.append(
                {
                    "rowIndex": row_index,
                    "cells": cells,
                    "rowText": row_text,
                }
            )

    return candidates


def normalize_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def trim_trailing_empty(row: list[str]) -> list[str]:
    last = -1
    for index, value in enumerate(row):
        if value:
            last = index
    return row[: last + 1] if last >= 0 else []


def fill_context_cells(
    cells: list[str],
    context_values: dict[int, str],
    context_cols: int,
) -> list[str]:
    filled = list(cells)
    for index in range(min(context_cols, len(filled))):
        if not filled[index] and context_values.get(index):
            filled[index] = context_values[index]
    return filled


def remember_context_values(
    context_values: dict[int, str],
    cells: list[str],
    context_cols: int,
) -> None:
    for index in range(min(context_cols, len(cells))):
        value = cells[index]
        if value and contains_hangul(value) and not looks_numeric(value):
            context_values[index] = value


def row_text_from_cells(cells: list[str]) -> str:
    return " | ".join(cell for cell in cells if cell)


def numeric_values_for_row(cells: list[str]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for index, cell in enumerate(cells):
        if not cell or cell in {"-", "–", "—"}:
            continue
        ratio_match = re.search(r"(-?\d+(?:\.\d+)?)\s*:\s*(-?\d+(?:\.\d+)?)", cell)
        if ratio_match:
            left = parse_number(ratio_match.group(1))
            right = parse_number(ratio_match.group(2))
            values.append(
                {
                    "colIndex": index + 1,
                    "raw": cell,
                    "kind": "ratio",
                    "value": left / right if right else left,
                }
            )
            continue
        number_matches = re.findall(r"-?\d[\d,]*(?:\.\d+)?", cell)
        if not number_matches:
            continue
        for match in number_matches[:3]:
            values.append(
                {
                    "colIndex": index + 1,
                    "raw": cell,
                    "kind": "number",
                    "value": parse_number(match),
                }
            )
    return values


def parse_number(value: str) -> float:
    return float(value.replace(",", ""))


def contains_hangul(value: str) -> bool:
    return bool(re.search(r"[가-힣]", value))


def looks_numeric(value: str) -> bool:
    return bool(re.fullmatch(r"[-+]?[\d,]+(?:\.\d+)?%?", value.strip()))


def detect_row_role(sheet: dict[str, Any], text: str) -> str:
    sheet_role = str(sheet.get("detectedSheetRole") or "")
    normalized = text.lower()
    if sheet_role == "competition_rate_table" or re.search(r"경쟁률|지원율|\d+\s*:\s*1", normalized):
        return "competition_rate_row"
    if sheet_role == "admission_result_table" or re.search(
        r"입시결과|입학결과|전형결과|충원|합격|등록|환산|백분위|등급|컷|평균",
        normalized,
    ):
        return "admission_result_row"
    if re.search(r"원서접수|합격자 발표|등록기간|충원합격|추가합격", normalized):
        return "schedule_row"
    if sheet_role == "recruitment_notice_table" or re.search(
        r"모집인원|모집단위|모집군|전형방법|반영비율|수능",
        normalized,
    ):
        if re.search(r"전형방법|반영비율|수능", normalized):
            return "screening_method_row"
        return "recruitment_quota_row"
    return "workbook_review_row"


def detect_row_type(text: str, numeric_values: list[dict[str, Any]]) -> str:
    if re.search(r"총|전체|합계|소계|마감|계$", text):
        return "summary_or_total_row"
    if len(numeric_values) >= 2:
        return "data_row"
    return "review_row"


def is_candidate_row(
    *,
    row_text: str,
    filled_row_text: str,
    numeric_values: list[dict[str, Any]],
    row_role: str,
    row_type: str,
) -> bool:
    if len(numeric_values) < 2:
        return False
    if not contains_hangul(filled_row_text):
        return False
    if is_likely_non_admission_row(filled_row_text):
        return False
    if row_role == "workbook_review_row" and len(numeric_values) < 4:
        return False
    if is_header_only_row(row_text, numeric_values):
        return False
    return row_type in {"data_row", "summary_or_total_row"}


def is_likely_non_admission_row(text: str) -> bool:
    admission_hits = len(ADMISSION_DOMAIN_PATTERN.findall(text))
    non_admission_hits = len(LIKELY_NON_ADMISSION_PATTERN.findall(text))
    has_email = bool(re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}", text, re.IGNORECASE))
    has_card_like_number = bool(re.search(r"\b(?:\d[ -]?){13,19}\b", text))
    return (non_admission_hits >= 3 and admission_hits <= 2) or (
        has_email and has_card_like_number and admission_hits <= 2
    )


def is_header_only_row(row_text: str, numeric_values: list[dict[str, Any]]) -> bool:
    if len(numeric_values) >= 2 and re.search(r"\d{4}학년도|20\d{2}", row_text):
        return False
    header_terms = len(re.findall(r"모집인원|지원자|지원율|평균|등급|백분위|환산|전형", row_text))
    return header_terms >= 3 and len(numeric_values) == 0


def should_keep_as_header_context(cells: list[str], numeric_values: list[dict[str, Any]]) -> bool:
    text = row_text_from_cells(cells)
    if not text:
        return False
    if len(numeric_values) <= 1:
        return True
    return bool(re.search(r"모집인원|지원자|지원율|평균|등급|백분위|환산|전형|구분", text))


def make_candidate_row(
    *,
    sheet: dict[str, Any],
    row_index: int,
    cells: list[str],
    filled_cells: list[str],
    row_text: str,
    filled_row_text: str,
    numeric_values: list[dict[str, Any]],
    row_role: str,
    row_type: str,
    header_context_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    candidate_payload = {
        "csvPath": sheet.get("csvPath"),
        "rowIndex": row_index,
        "filledRowText": filled_row_text,
        "rowRole": row_role,
    }
    candidate_sha = hashlib.sha256(
        json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_workbook_row_candidate",
        "year": sheet.get("year"),
        "unvCd": sheet.get("unvCd"),
        "universityName": sheet.get("universityName"),
        "campus": sheet.get("campus"),
        "sourceLinkRole": sheet.get("sourceLinkRole"),
        "attachmentRole": sheet.get("attachmentRole"),
        "sheetName": sheet.get("sheetName"),
        "detectedSheetRole": sheet.get("detectedSheetRole"),
        "rowCandidateRole": row_role,
        "evidenceTarget": TARGET_BY_ROW_ROLE.get(row_role, "ReviewQueue"),
        "rowType": row_type,
        "rowIndex": row_index,
        "nonEmptyCells": sum(1 for cell in cells if cell),
        "numericCellCount": len(numeric_values),
        "numericValues": numeric_values[:80],
        "cells": cells,
        "filledContextCells": filled_cells,
        "rowText": row_text[:4000],
        "filledRowText": filled_row_text[:4000],
        "headerContextRows": header_context_rows,
        "sourceCandidateUrl": sheet.get("sourceCandidateUrl"),
        "attachmentUrl": sheet.get("attachmentUrl"),
        "rawWorkbookPath": sheet.get("rawWorkbookPath"),
        "rawWorkbookSha256": sheet.get("rawWorkbookSha256"),
        "fileExtension": sheet.get("fileExtension"),
        "csvPath": sheet.get("csvPath"),
        "sheetSha256": sheet.get("sha256"),
        "candidateSha256": candidate_sha,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "status": "candidate",
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "sourceLinkRole",
        "sheetName",
        "detectedSheetRole",
        "rowCandidateRole",
        "evidenceTarget",
        "rowType",
        "rowIndex",
        "nonEmptyCells",
        "numericCellCount",
        "csvPath",
        "rawWorkbookPath",
        "attachmentUrl",
        "candidateSha256",
        "filledRowText",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def summarize(
    year: int,
    sheet_rows: list[dict[str, Any]],
    row_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "sourceSheets": len([row for row in sheet_rows if int(row.get("year") or 0) == year]),
        "rowCandidates": len(row_candidates),
        "uniqueCandidateSha256": len(
            {str(row.get("candidateSha256") or "") for row in row_candidates}
        ),
        "universitiesWithRowCandidates": len(
            {str(row.get("unvCd") or "") for row in row_candidates if row.get("unvCd")}
        ),
        "byDetectedSheetRole": count_by(row_candidates, "detectedSheetRole"),
        "byRowCandidateRole": count_by(row_candidates, "rowCandidateRole"),
        "byEvidenceTarget": count_by(row_candidates, "evidenceTarget"),
        "byRowType": count_by(row_candidates, "rowType"),
        "bySourceLinkRole": count_by(row_candidates, "sourceLinkRole"),
        "notes": [
            "Workbook row candidates preserve source CSV row cells and carry-forward context cells for blank merged-label style tables.",
            "Rows are numeric evidence candidates only; final AdmissionRule or HistoricalOutcome promotion requires source review.",
        ],
    }


if __name__ == "__main__":
    main()
