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
DEFAULT_ADIGA_DIR = "packages/reference-data/data/public/adiga/extracted"
DEFAULT_DECISION_LOG = "foundation_operational_review_decision_log.csv"
DEFAULT_HISTORICAL_OUTCOMES = "foundation_historical_outcomes.csv"
DEFAULT_ADIGA_OUTCOMES = "adiga_csat_outcome_row_candidates.csv"
OUTPUT_SUMMARY = "foundation_adiga_csat_outcome_review_summary.json"

REVIEWER = "codex-adiga-csat-outcome-row-audit-v1"
APPROVAL_NOTE = (
    "Strict ADIGA CSAT outcome audit: foundation row matched ADIGA candidateSha256, "
    "candidate values matched foundation values, and extracted table grid row contained "
    "the admission unit, recruitment group, quota, competition, additional-pass, score, "
    "total-score, and percentile values."
)

GROUP_TEXT = {
    "ga": "가군",
    "na": "나군",
    "da": "다군",
    "none": "",
}


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    adiga_dir = resolve(repo_root, args.adiga_dir)
    decision_log_path = foundation_dir / args.decision_log_csv
    historical_outcomes_path = foundation_dir / args.historical_outcomes_csv
    adiga_outcomes_path = adiga_dir / args.adiga_outcomes_csv

    decision_rows = list(read_csv(decision_log_path))
    historical_outcomes = {
        normalize_text(row.get("outcomeCandidateId")): row
        for row in read_csv(historical_outcomes_path)
        if normalize_text(row.get("outcomeCandidateId"))
    }
    adiga_candidates = {
        normalize_text(row.get("candidateSha256")): row
        for row in read_csv(adiga_outcomes_path)
        if normalize_text(row.get("candidateSha256"))
    }
    table_cache: dict[str, dict[tuple[str, str, str, str], dict[str, Any]]] = {}

    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    results = []
    changed = 0
    for row in decision_rows:
        if normalize_text(row.get("sourceArtifact")) != "foundation_historical_outcomes":
            continue
        if normalize_text(row.get("provider")) != "adiga":
            continue
        result = verify_adiga_outcome_row(
            adiga_dir,
            row,
            historical_outcomes,
            adiga_candidates,
            table_cache,
        )
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
    summary = summarize(
        repo_root=repo_root,
        decision_log_path=decision_log_path,
        historical_outcomes_path=historical_outcomes_path,
        adiga_outcomes_path=adiga_outcomes_path,
        results=results,
        changed=changed,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation ADIGA CSAT outcome review complete. "
        f"matched={summary['matchedRows']} changed={changed} output={to_repo_relative(decision_log_path, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--adiga-dir", default=DEFAULT_ADIGA_DIR)
    parser.add_argument("--decision-log-csv", default=DEFAULT_DECISION_LOG)
    parser.add_argument("--historical-outcomes-csv", default=DEFAULT_HISTORICAL_OUTCOMES)
    parser.add_argument("--adiga-outcomes-csv", default=DEFAULT_ADIGA_OUTCOMES)
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


def verify_adiga_outcome_row(
    adiga_dir: Path,
    decision_row: dict[str, str],
    historical_outcomes: dict[str, dict[str, str]],
    adiga_candidates: dict[str, dict[str, str]],
    table_cache: dict[str, dict[tuple[str, str, str, str], dict[str, Any]]],
) -> dict[str, Any]:
    source_record_id = normalize_text(decision_row.get("sourceRecordId"))
    outcome = historical_outcomes.get(source_record_id)
    if outcome is None:
        return result(decision_row, "missing_historical_outcome", "No foundation historical outcome row found.")
    if normalize_text(outcome.get("sourceProvider")) != "adiga":
        return result(decision_row, "non_adiga_source", "Historical outcome sourceProvider is not ADIGA.")

    candidate_sha = normalize_text(outcome.get("sourceCandidateSha256"))
    candidate = adiga_candidates.get(candidate_sha)
    if candidate is None:
        return result(decision_row, "missing_adiga_candidate", "No ADIGA candidate row found for sourceCandidateSha256.")

    mismatch = candidate_mismatch(outcome, candidate)
    if mismatch:
        return result(decision_row, mismatch, "Foundation outcome values differ from the ADIGA candidate row.")

    table = table_for_outcome(adiga_dir, outcome, table_cache)
    if table is None:
        return result(decision_row, "missing_extracted_table", "No extracted ADIGA table found for source coordinates.")
    grid = table.get("grid") if isinstance(table.get("grid"), list) else []
    row_index = int_or_none(outcome.get("rowIndex"))
    if row_index is None or row_index < 1 or row_index > len(grid):
        return result(decision_row, "row_out_of_bounds", "rowIndex is outside extracted table grid.")
    raw_row = grid[row_index - 1]
    if not isinstance(raw_row, list):
        return result(decision_row, "invalid_grid_row", "Extracted table grid row is not a list.")
    cells = [clean_cell(cell) for cell in raw_row]
    row_text = " ".join(cells)
    if normalize_compact(outcome.get("admissionUnitName")) not in normalize_compact(row_text):
        return result(decision_row, "unit_not_in_row", "Admission unit name not found in extracted table row.")

    group = GROUP_TEXT.get(normalize_text(outcome.get("recruitmentGroup")), "")
    if group and group not in row_text:
        return result(
            decision_row,
            "group_not_in_row",
            "Recruitment group is not explicit in this row; likely carry-forward, so manual review is required.",
        )

    row_numbers = {normalize_number(cell) for cell in cells if normalize_number(cell)}
    for field in [
        "quota",
        "competitionRate",
        "additionalPass",
        "convertedScore70Cut",
        "totalScore",
        "percentile70Average",
    ]:
        value = normalize_number(outcome.get(field))
        if value and value not in row_numbers:
            return result(decision_row, f"raw_row_value_missing_{field}", f"value={value} row={row_text[:500]}")
    return result(decision_row, "matched", "Strict ADIGA candidate and extracted-table row checks passed.")


def candidate_mismatch(outcome: dict[str, str], candidate: dict[str, str]) -> str:
    text_fields = [
        "year",
        "unvCd",
        "universityName",
        "recruitmentGroup",
        "admissionUnitName",
        "scoreAvailability",
        "sourceUrl",
        "rawPath",
        "sectionId",
        "tableIndex",
        "rowIndex",
    ]
    number_fields = [
        "quota",
        "competitionRate",
        "additionalPass",
        "convertedScore70Cut",
        "totalScore",
        "percentile70Average",
    ]
    for field in text_fields:
        if normalize_compact(outcome.get(field)) != normalize_compact(candidate.get(field)):
            return f"candidate_field_mismatch_{field}"
    for field in number_fields:
        if normalize_number(outcome.get(field)) != normalize_number(candidate.get(field)):
            return f"candidate_value_mismatch_{field}"
    return ""


def table_for_outcome(
    adiga_dir: Path,
    outcome: dict[str, str],
    table_cache: dict[str, dict[tuple[str, str, str, str], dict[str, Any]]],
) -> dict[str, Any] | None:
    year = normalize_text(outcome.get("year"))
    if year not in table_cache:
        table_cache[year] = load_tables(adiga_dir / f"adiga_extracted_tables_{year}.jsonl")
    key = (
        normalize_text(outcome.get("unvCd")),
        normalize_text(outcome.get("sectionId")),
        normalize_text(outcome.get("tableIndex")),
        normalize_text(outcome.get("rawPath")),
    )
    return table_cache[year].get(key)


def load_tables(path: Path) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    output: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    if not path.exists():
        return output
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                table = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (
                normalize_text(table.get("unvCd")),
                normalize_text(table.get("sectionId")),
                normalize_text(table.get("tableIndex")),
                normalize_text(table.get("rawPath")),
            )
            output[key] = table
    return output


def result(row: dict[str, str], status: str, detail: str) -> dict[str, Any]:
    return {
        "reviewDecisionId": row.get("reviewDecisionId", ""),
        "sourceRecordId": row.get("sourceRecordId", ""),
        "admissionYear": row.get("admissionYear", ""),
        "unvCd": row.get("unvCd", ""),
        "universityName": row.get("universityName", ""),
        "admissionUnitName": row.get("admissionUnitName", ""),
        "status": status,
        "detail": detail,
    }


def summarize(
    *,
    repo_root: Path,
    decision_log_path: Path,
    historical_outcomes_path: Path,
    adiga_outcomes_path: Path,
    results: list[dict[str, Any]],
    changed: int,
) -> dict[str, Any]:
    by_status = Counter(str(row.get("status") or "") for row in results)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_adiga_csat_outcome_review_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "decisionLogCsv": to_repo_relative(decision_log_path, repo_root),
            "historicalOutcomesCsv": to_repo_relative(historical_outcomes_path, repo_root),
            "adigaOutcomesCsv": to_repo_relative(adiga_outcomes_path, repo_root),
        },
        "reviewer": REVIEWER,
        "candidateRows": len(results),
        "matchedRows": by_status.get("matched", 0),
        "changedRows": changed,
        "byStatus": dict(sorted(by_status.items())),
        "notes": [
            "Only pending ADIGA HistoricalOutcome decision-log rows are modified.",
            "Rows are approved only when foundation values match the ADIGA candidate row and the extracted table grid row contains the unit, explicit recruitment group, and all core numeric values.",
            "Rows whose recruitment group is carried forward from a previous table row remain pending for manual review.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    fields = list(fieldnames)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def clean_cell(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"\s*/\s*$", "", text)
    return text.strip()


def normalize_number(value: Any) -> str:
    text = normalize_text(value).replace(",", "")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match is None:
            return ""
        number = float(match.group(0))
    if number.is_integer():
        return str(int(number))
    return f"{number:.10f}".rstrip("0").rstrip(".")


def int_or_none(value: Any) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def normalize_compact(value: Any) -> str:
    return normalize_text(value).replace(" ", "")


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
