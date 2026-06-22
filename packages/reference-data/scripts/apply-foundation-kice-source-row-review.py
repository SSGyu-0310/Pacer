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
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_DECISION_LOG = "foundation_operational_review_decision_log.csv"
DEFAULT_KICE_DISTRIBUTIONS = "foundation_kice_standard_score_distributions.csv"
OUTPUT_SUMMARY = "foundation_kice_source_row_review_summary.json"

REVIEWER = "codex-kice-source-row-audit-v1"
APPROVAL_NOTE = (
    "Strict KICE source CSV audit: sourceRowNumber/sourceColumnNumber matched "
    "standardScore,maleCount,femaleCount,totalCount,cumulativeTotalCount, with "
    "subject and 표준점수 headers found above the source row."
)


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    decision_log_path = foundation_dir / args.decision_log_csv
    kice_path = foundation_dir / args.kice_distributions_csv
    decision_rows = list(read_csv(decision_log_path))
    kice_records = {
        normalize_text(row.get("distributionCandidateId")): row
        for row in read_csv(kice_path)
        if normalize_text(row.get("distributionCandidateId"))
    }

    csv_cache: dict[Path, list[list[str]]] = {}
    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    results = []
    changed = 0
    for row in decision_rows:
        if normalize_text(row.get("sourceArtifact")) != "foundation_kice_standard_score_distributions":
            continue
        result = verify_kice_distribution_row(repo_root, row, kice_records, csv_cache)
        results.append(result)
        if result["status"] != "matched":
            continue
        if normalize_text(row.get("reviewOutcome")) != "pending":
            continue
        row["decisionStatus"] = "reviewed"
        row["reviewOutcome"] = "approved"
        row["reviewedVerifiedStatus"] = "verified"
        row["reviewer"] = REVIEWER
        row["reviewedAt"] = reviewed_at
        row["sourceMatchStatus"] = "matched"
        row["valueMatchStatus"] = "matched"
        row["reviewNotes"] = APPROVAL_NOTE
        row["followupAction"] = ""
        row["rejectionReason"] = ""
        changed += 1

    write_csv(decision_log_path, decision_rows, decision_rows[0].keys() if decision_rows else [])
    summary = summarize(repo_root, decision_log_path, kice_path, results, changed)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation KICE source row review complete. "
        f"matched={summary['matchedRows']} changed={changed} output={to_repo_relative(decision_log_path, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--decision-log-csv", default=DEFAULT_DECISION_LOG)
    parser.add_argument("--kice-distributions-csv", default=DEFAULT_KICE_DISTRIBUTIONS)
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


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def verify_kice_distribution_row(
    repo_root: Path,
    decision_row: dict[str, str],
    kice_records: dict[str, dict[str, str]],
    csv_cache: dict[Path, list[list[str]]],
) -> dict[str, Any]:
    source_record_id = normalize_text(decision_row.get("sourceRecordId"))
    record = kice_records.get(source_record_id)
    if record is None:
        return result(decision_row, "missing_source_record", "No KICE distribution source record found.")

    csv_path = resolve(repo_root, normalize_text(record.get("csvPath")))
    if not csv_path.exists():
        return result(decision_row, "missing_csv", f"CSV path does not exist: {csv_path}")
    try:
        source_row_number = int(normalize_text(record.get("sourceRowNumber")))
        source_column_number = int(normalize_text(record.get("sourceColumnNumber")))
    except ValueError:
        return result(decision_row, "bad_coordinates", "sourceRowNumber/sourceColumnNumber are not integers.")

    csv_rows = load_csv_rows(csv_path, csv_cache)
    if source_row_number < 1 or source_row_number > len(csv_rows):
        return result(decision_row, "row_out_of_bounds", "sourceRowNumber is outside the CSV row range.")
    source_row = csv_rows[source_row_number - 1]
    start = source_column_number - 1
    if start < 0 or start + 4 >= len(source_row):
        return result(decision_row, "column_out_of_bounds", "sourceColumnNumber does not expose five value cells.")

    expected = [
        record.get("standardScore", ""),
        record.get("maleCount", ""),
        record.get("femaleCount", ""),
        record.get("totalCount", ""),
        record.get("cumulativeTotalCount", ""),
    ]
    actual = source_row[start : start + 5]
    if [normalize_number(value) for value in actual] != [normalize_number(value) for value in expected]:
        return result(
            decision_row,
            "value_mismatch",
            f"expected={expected} actual={actual} row={source_row_number} column={source_column_number}",
        )

    subject = normalize_text(record.get("subjectNameNormalized"))
    header_ok, subject_ok = header_checks(csv_rows, source_row_number, start, subject)
    if not header_ok:
        return result(decision_row, "header_missing", "No 표준점수 header found above the source row.")
    if not subject_ok:
        return result(decision_row, "subject_header_missing", "No subject header found above the source row.")
    return result(decision_row, "matched", "Strict source row, value, subject, and header checks passed.")


def load_csv_rows(path: Path, cache: dict[Path, list[list[str]]]) -> list[list[str]]:
    if path not in cache:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            cache[path] = list(csv.reader(handle))
    return cache[path]


def header_checks(
    csv_rows: list[list[str]],
    source_row_number: int,
    start: int,
    subject: str,
) -> tuple[bool, bool]:
    header_ok = False
    subject_ok = False
    for index in range(0, source_row_number - 1):
        row = csv_rows[index]
        window = row[max(0, start) : min(len(row), start + 6)]
        if any("표준점수" in cell for cell in window):
            header_ok = True
        if subject and any(subject == cell.strip() or subject in cell.strip() for cell in window):
            subject_ok = True
    return header_ok, subject_ok


def result(row: dict[str, str], status: str, detail: str) -> dict[str, Any]:
    return {
        "reviewDecisionId": row.get("reviewDecisionId", ""),
        "sourceRecordId": row.get("sourceRecordId", ""),
        "academicYear": row.get("academicYear", ""),
        "examType": row.get("examType", ""),
        "subjectName": row.get("subjectName", ""),
        "status": status,
        "detail": detail,
    }


def summarize(
    repo_root: Path,
    decision_log_path: Path,
    kice_path: Path,
    results: list[dict[str, Any]],
    changed: int,
) -> dict[str, Any]:
    by_status = Counter(str(row.get("status") or "") for row in results)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_kice_source_row_review_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "decisionLogCsv": to_repo_relative(decision_log_path, repo_root),
            "kiceDistributionsCsv": to_repo_relative(kice_path, repo_root),
        },
        "reviewer": REVIEWER,
        "candidateRows": len(results),
        "matchedRows": by_status.get("matched", 0),
        "changedRows": changed,
        "byStatus": dict(sorted(by_status.items())),
        "notes": [
            "Only pending KICE standard-score distribution decision-log rows are modified.",
            "Rows are approved only when source CSV coordinates, five numeric values, subject header, and 표준점수 header all match.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    fields = list(fieldnames)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def normalize_number(value: Any) -> str:
    return normalize_text(value).replace(",", "")


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
