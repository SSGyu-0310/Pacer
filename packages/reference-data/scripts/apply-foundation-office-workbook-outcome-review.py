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
DEFAULT_HISTORICAL_OUTCOMES = "foundation_historical_outcomes.csv"
DEFAULT_OFFICE_EVIDENCE = "foundation_admission_office_evidence_links.csv"
OUTPUT_SUMMARY = "foundation_office_workbook_outcome_review_summary.json"

REVIEWER = "codex-office-workbook-outcome-row-audit-v1"
APPROVAL_NOTE = (
    "Strict admission-office workbook outcome audit: foundation HistoricalOutcome matched "
    "admission office evidenceCandidateSha256/rawPath/sourceUrl, and an extracted workbook "
    "CSV row contained the admission unit, recruitment group where applicable, quota, "
    "competition rate, and score/pass values."
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
    decision_log_path = foundation_dir / args.decision_log_csv
    historical_outcomes_path = foundation_dir / args.historical_outcomes_csv
    office_evidence_path = foundation_dir / args.office_evidence_csv

    decision_rows = list(read_csv(decision_log_path))
    historical_outcomes = {
        normalize_text(row.get("outcomeCandidateId")): row
        for row in read_csv(historical_outcomes_path)
        if normalize_text(row.get("outcomeCandidateId"))
    }
    office_evidence = {
        normalize_text(row.get("evidenceCandidateSha256")): row
        for row in read_csv(office_evidence_path)
        if normalize_text(row.get("evidenceCandidateSha256"))
    }
    source_row_cache: dict[str, list[dict[str, Any]]] = {}

    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    results = []
    changed = 0
    for row in decision_rows:
        if normalize_text(row.get("sourceArtifact")) != "foundation_historical_outcomes":
            continue
        if normalize_text(row.get("reviewOutcome")) != "pending":
            continue
        if normalize_text(row.get("provider")) != "university-admission-office":
            continue
        result = verify_office_workbook_outcome_row(
            repo_root,
            row,
            historical_outcomes,
            office_evidence,
            source_row_cache,
        )
        results.append(result)
        if result["status"] != "matched":
            continue
        if args.dry_run:
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

    if not args.dry_run:
        write_csv(decision_log_path, decision_rows, decision_rows[0].keys() if decision_rows else [])
    summary = summarize(
        repo_root=repo_root,
        decision_log_path=decision_log_path,
        historical_outcomes_path=historical_outcomes_path,
        office_evidence_path=office_evidence_path,
        results=results,
        changed=changed,
        dry_run=args.dry_run,
    )
    if not args.dry_run:
        (foundation_dir / OUTPUT_SUMMARY).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        "foundation admission-office workbook outcome review complete. "
        f"matched={summary['matchedRows']} changed={changed} dryRun={args.dry_run}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--decision-log-csv", default=DEFAULT_DECISION_LOG)
    parser.add_argument("--historical-outcomes-csv", default=DEFAULT_HISTORICAL_OUTCOMES)
    parser.add_argument("--office-evidence-csv", default=DEFAULT_OFFICE_EVIDENCE)
    parser.add_argument("--dry-run", action="store_true")
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


def verify_office_workbook_outcome_row(
    repo_root: Path,
    decision_row: dict[str, str],
    historical_outcomes: dict[str, dict[str, str]],
    office_evidence: dict[str, dict[str, str]],
    source_row_cache: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    source_record_id = normalize_text(decision_row.get("sourceRecordId"))
    outcome = historical_outcomes.get(source_record_id)
    if outcome is None:
        return result(decision_row, "missing_historical_outcome", "No foundation historical outcome row found.")
    if normalize_text(outcome.get("sourceProvider")) != "university-admission-office":
        return result(decision_row, "non_office_source", "Historical outcome sourceProvider is not admission office.")

    evidence = office_evidence.get(normalize_text(outcome.get("sourceCandidateSha256")))
    if evidence is None:
        return result(decision_row, "missing_office_evidence", "No admission office evidence row found.")
    if normalize_text(evidence.get("evidenceTarget")) != "HistoricalOutcome":
        return result(decision_row, "non_historical_evidence", "Evidence target is not HistoricalOutcome.")
    if "workbook_row" not in split_values(evidence.get("evidenceTypes")):
        return result(decision_row, "non_workbook_evidence", "Evidence is not a workbook row.")

    mismatch = evidence_mismatch(outcome, evidence)
    if mismatch:
        return result(decision_row, mismatch, "Foundation outcome source fields differ from evidence link.")

    source_paths = source_paths_for_year(evidence, outcome.get("year"))
    if not source_paths:
        return result(decision_row, "missing_source_paths", "Evidence link has no sourcePaths.")

    row_failures = Counter()
    for source_path in source_paths:
        rows = source_rows(repo_root, source_path, source_row_cache)
        if not rows:
            row_failures["source_path_missing_or_empty"] += 1
            continue
        status, detail = match_source_row(outcome, rows)
        if status == "matched":
            output = result(decision_row, "matched", detail)
            output["matchedSourcePath"] = source_path
            return output
        row_failures[status] += 1

    output = result(
        decision_row,
        "no_strict_source_row",
        ", ".join(f"{key}={value}" for key, value in sorted(row_failures.items())),
    )
    output["sourceRowFailureStatuses"] = dict(sorted(row_failures.items()))
    return output


def evidence_mismatch(outcome: dict[str, str], evidence: dict[str, str]) -> str:
    if normalize_text(outcome.get("unvCd")) != normalize_text(evidence.get("unvCd")):
        return "evidence_field_mismatch_unvCd"
    source_url = normalize_text(outcome.get("sourceUrl"))
    if source_url and source_url not in split_values(evidence.get("sourceCandidateUrls")):
        return "evidence_field_mismatch_sourceUrl"
    raw_path = normalize_text(outcome.get("rawPath"))
    if raw_path and raw_path not in split_values(evidence.get("rawPaths")):
        return "evidence_field_mismatch_rawPath"
    return ""


def source_paths_for_year(evidence: dict[str, str], year: Any) -> list[str]:
    paths = split_values(evidence.get("sourcePaths"))
    year_text = normalize_text(year)
    preferred = [path for path in paths if f"/{year_text}/" in path]
    return preferred or paths


def source_rows(
    repo_root: Path,
    source_path: str,
    source_row_cache: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    normalized_path = normalize_text(source_path)
    if normalized_path in source_row_cache:
        return source_row_cache[normalized_path]
    path = resolve(repo_root, normalized_path)
    if not path.exists() or path.suffix.lower() != ".csv":
        source_row_cache[normalized_path] = []
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for index, cells in enumerate(csv.reader(handle)):
            cleaned = [normalize_text(cell) for cell in cells]
            row_text = " ".join(cell for cell in cleaned if cell)
            if not row_text:
                continue
            rows.append(
                {
                    "rowIndex": index,
                    "cells": cleaned,
                    "rowText": row_text,
                    "compactText": normalize_compact(row_text),
                    "numbers": numbers_in_text(row_text),
                }
            )
    source_row_cache[normalized_path] = rows
    return rows


def match_source_row(outcome: dict[str, str], rows: list[dict[str, Any]]) -> tuple[str, str]:
    unit_name = normalize_compact(outcome.get("admissionUnitName"))
    if not unit_name:
        return "missing_unit_name", "Outcome has no admissionUnitName."
    group = GROUP_TEXT.get(normalize_text(outcome.get("recruitmentGroup")), "")
    unit_rows = [row for row in rows if unit_name in row["compactText"]]
    if not unit_rows:
        return "unit_not_in_source_row", "No workbook row contains the admission unit name."
    if group:
        grouped_rows = [row for row in unit_rows if group in row["rowText"]]
        if not grouped_rows:
            return "group_not_in_source_row", "No unit row contains the explicit recruitment group."
        unit_rows = grouped_rows

    required_numbers = required_outcome_numbers(outcome)
    if not required_numbers:
        return "missing_required_values", "Outcome has no required numeric values."
    failures = Counter()
    for row in unit_rows:
        missing = [
            field
            for field, value, tolerance in required_numbers
            if not number_present(value, row["numbers"], tolerance)
        ]
        if not missing:
            return "matched", f"Workbook rowIndex={row['rowIndex']} matched all required values."
        failures["missing:" + "|".join(missing)] += 1
    return "source_row_values_missing", ", ".join(f"{key}={value}" for key, value in failures.items())


def required_outcome_numbers(outcome: dict[str, str]) -> list[tuple[str, float, float]]:
    required: list[tuple[str, float, float]] = []
    add_required(required, "quota", outcome.get("quota"), 0.001)
    add_required(required, "competitionRate", outcome.get("competitionRate"), 0.03)
    if normalize_text(outcome.get("additionalPass")):
        add_required(required, "additionalPass", outcome.get("additionalPass"), 0.001)

    score_fields = [
        "avgScoreCandidate",
        "cutScoreCandidate",
        "percentileCutCandidate",
    ]
    score_values = [
        (field, number_or_none(outcome.get(field)))
        for field in score_fields
        if normalize_text(outcome.get(field))
    ]
    if score_values:
        for field, value in score_values:
            if value is not None:
                required.append((field, value, score_tolerance(value)))
    return required


def add_required(output: list[tuple[str, float, float]], field: str, value: Any, tolerance: float) -> None:
    number = number_or_none(value)
    if number is not None:
        output.append((field, number, tolerance))


def score_tolerance(value: float) -> float:
    if value >= 100:
        return 0.05
    return 0.01


def number_present(target: float, candidates: list[float], tolerance: float) -> bool:
    return any(abs(candidate - target) <= tolerance for candidate in candidates)


def numbers_in_text(value: Any) -> list[float]:
    text = normalize_text(value).replace(",", "")
    output = []
    for match in re.finditer(r"-?\d+(?:\.\d+)?", text):
        number = number_or_none(match.group(0))
        if number is not None:
            output.append(number)
    return output


def number_or_none(value: Any) -> float | None:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match is None:
            return None
        return float(match.group(0))


def result(row: dict[str, str], status: str, detail: str) -> dict[str, Any]:
    return {
        "reviewDecisionId": row.get("reviewDecisionId", ""),
        "sourceRecordId": row.get("sourceRecordId", ""),
        "admissionYear": row.get("admissionYear", ""),
        "unvCd": row.get("unvCd", ""),
        "universityName": row.get("universityName", ""),
        "admissionUnitName": row.get("admissionUnitName", ""),
        "recruitmentGroup": row.get("recruitmentGroup", ""),
        "status": status,
        "detail": detail,
    }


def summarize(
    *,
    repo_root: Path,
    decision_log_path: Path,
    historical_outcomes_path: Path,
    office_evidence_path: Path,
    results: list[dict[str, Any]],
    changed: int,
    dry_run: bool,
) -> dict[str, Any]:
    by_status = Counter(str(row.get("status") or "") for row in results)
    row_failures = Counter()
    for row in results:
        statuses = row.get("sourceRowFailureStatuses")
        if isinstance(statuses, dict):
            row_failures.update({str(key): int(value) for key, value in statuses.items()})
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_office_workbook_outcome_review_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "decisionLogCsv": to_repo_relative(decision_log_path, repo_root),
            "historicalOutcomesCsv": to_repo_relative(historical_outcomes_path, repo_root),
            "officeEvidenceCsv": to_repo_relative(office_evidence_path, repo_root),
        },
        "reviewer": REVIEWER,
        "dryRun": dry_run,
        "candidateRows": len(results),
        "matchedRows": by_status.get("matched", 0),
        "changedRows": changed,
        "byStatus": dict(sorted(by_status.items())),
        "sourceRowFailureStatuses": dict(sorted(row_failures.items())),
        "notes": [
            "Only pending university-admission-office HistoricalOutcome rows are considered.",
            "Rows are approved only for workbook_row evidence; PDF snippets are left pending because page snippets may contain multiple units without a strict row boundary.",
            "Approval requires a real extracted workbook CSV row containing the unit, explicit recruitment group when applicable, quota, competition rate, and score/pass values.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    fields = list(fieldnames)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def split_values(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [part for part in re.split(r"[|]+", text) if part]


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
