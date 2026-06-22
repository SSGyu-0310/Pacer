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
DEFAULT_ADMISSION_UNITS = "foundation_admission_units.csv"
DEFAULT_HISTORICAL_OUTCOMES = "foundation_historical_outcomes.csv"
OUTPUT_SUMMARY = "foundation_approved_outcome_admission_unit_review_summary.json"

REVIEWER = "codex-approved-outcome-admission-unit-row-audit-v1"
APPROVAL_NOTE = (
    "Strict linked-outcome AdmissionUnit audit: the same unitCandidateId has an already "
    "approved exact-record HistoricalOutcome whose source review verified the admission "
    "unit, recruitment group where applicable, quota, and outcome values; the AdmissionUnit "
    "quotaCandidates include the approved HistoricalOutcome quota."
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
    admission_units_path = foundation_dir / args.admission_units_csv
    historical_outcomes_path = foundation_dir / args.historical_outcomes_csv

    decision_rows = list(read_csv(decision_log_path))
    admission_units = {
        normalize_text(row.get("unitCandidateId")): row
        for row in read_csv(admission_units_path)
        if normalize_text(row.get("unitCandidateId"))
    }
    historical_outcomes = {
        normalize_text(row.get("outcomeCandidateId")): row
        for row in read_csv(historical_outcomes_path)
        if normalize_text(row.get("outcomeCandidateId"))
    }
    approved_outcomes_by_unit = approved_historical_outcomes_by_unit(decision_rows, historical_outcomes)

    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    results = []
    changed = 0
    for row in decision_rows:
        if normalize_text(row.get("sourceArtifact")) != "foundation_admission_units":
            continue
        if normalize_text(row.get("reviewOutcome")) != "pending":
            continue
        result = verify_linked_approved_outcome(row, admission_units, approved_outcomes_by_unit)
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
        row["reviewNotes"] = APPROVAL_NOTE + " linkedOutcomeCandidateId=" + result["linkedOutcomeCandidateId"]
        row["followupAction"] = ""
        row["rejectionReason"] = ""
        changed += 1

    if not args.dry_run:
        write_csv(decision_log_path, decision_rows, decision_rows[0].keys() if decision_rows else [])
    summary = summarize(
        repo_root=repo_root,
        decision_log_path=decision_log_path,
        admission_units_path=admission_units_path,
        historical_outcomes_path=historical_outcomes_path,
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
        "foundation approved-outcome AdmissionUnit review complete. "
        f"matched={summary['matchedRows']} changed={changed} dryRun={args.dry_run}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--decision-log-csv", default=DEFAULT_DECISION_LOG)
    parser.add_argument("--admission-units-csv", default=DEFAULT_ADMISSION_UNITS)
    parser.add_argument("--historical-outcomes-csv", default=DEFAULT_HISTORICAL_OUTCOMES)
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


def approved_historical_outcomes_by_unit(
    decision_rows: list[dict[str, str]],
    historical_outcomes: dict[str, dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    output: dict[str, list[dict[str, str]]] = {}
    for decision in decision_rows:
        if normalize_text(decision.get("sourceArtifact")) != "foundation_historical_outcomes":
            continue
        if normalize_text(decision.get("reviewOutcome")) != "approved":
            continue
        if normalize_text(decision.get("decisionStatus")) != "reviewed":
            continue
        if normalize_text(decision.get("approvedScope")) != "exact_record":
            continue
        if normalize_text(decision.get("sourceMatchStatus")) != "matched":
            continue
        if normalize_text(decision.get("valueMatchStatus")) != "matched":
            continue
        outcome_id = normalize_text(decision.get("sourceRecordId"))
        outcome = dict(historical_outcomes.get(outcome_id, {}))
        if not outcome:
            continue
        unit_id = normalize_text(outcome.get("unitCandidateId"))
        if not unit_id:
            continue
        outcome["approvedOutcomeReviewDecisionId"] = normalize_text(decision.get("reviewDecisionId"))
        output.setdefault(unit_id, []).append(outcome)
    return output


def verify_linked_approved_outcome(
    decision_row: dict[str, str],
    admission_units: dict[str, dict[str, str]],
    approved_outcomes_by_unit: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    source_record_id = normalize_text(decision_row.get("sourceRecordId"))
    unit = admission_units.get(source_record_id)
    if unit is None:
        return result(decision_row, "missing_admission_unit", "No foundation admission unit row found.")
    quota_values = quota_candidates(unit.get("quotaCandidates"))
    if not quota_values:
        return result(decision_row, "missing_quota_candidates", "AdmissionUnit has no quotaCandidates.")

    approved_outcomes = approved_outcomes_by_unit.get(source_record_id, [])
    if not approved_outcomes:
        return result(decision_row, "no_approved_linked_outcome", "No approved exact-record HistoricalOutcome for unitCandidateId.")

    failures = Counter()
    for outcome in approved_outcomes:
        status, detail = match_unit_to_outcome(unit, outcome, quota_values)
        if status != "matched":
            failures[status] += 1
            continue
        output = result(decision_row, "matched", detail)
        output["linkedOutcomeCandidateId"] = normalize_text(outcome.get("outcomeCandidateId"))
        output["linkedOutcomeReviewDecisionId"] = normalize_text(outcome.get("approvedOutcomeReviewDecisionId"))
        output["linkedOutcomeQuota"] = normalize_text(outcome.get("quota"))
        return output

    output = result(
        decision_row,
        "linked_outcome_mismatch",
        ", ".join(f"{key}={value}" for key, value in sorted(failures.items())),
    )
    output["linkedOutcomeFailureStatuses"] = dict(sorted(failures.items()))
    return output


def match_unit_to_outcome(
    unit: dict[str, str],
    outcome: dict[str, str],
    quota_values: list[float],
) -> tuple[str, str]:
    for field in ("unvCd", "year", "recruitmentGroup"):
        if normalize_text(unit.get(field)) != normalize_text(outcome.get(field)):
            return "field_mismatch_" + field, f"Unit {field} differs from approved outcome."
    unit_name = normalize_compact(unit.get("admissionUnitName"))
    unit_canonical = normalize_compact(unit.get("admissionUnitCanonicalName"))
    outcome_name = normalize_compact(outcome.get("admissionUnitName"))
    outcome_canonical = normalize_compact(outcome.get("admissionUnitCanonicalName"))
    if unit_name not in {outcome_name, outcome_canonical} and unit_canonical not in {outcome_name, outcome_canonical}:
        return "field_mismatch_admissionUnitName", "Unit name differs from approved outcome."

    outcome_quota = number_or_none(outcome.get("quota"))
    if outcome_quota is None:
        return "missing_outcome_quota", "Approved outcome has no quota."
    if not any(abs(outcome_quota - quota) <= 0.001 for quota in quota_values):
        return "quota_not_in_candidates", "Approved outcome quota is not in AdmissionUnit quotaCandidates."
    return "matched", "Approved HistoricalOutcome matched unit/year/group/name and quotaCandidates."


def quota_candidates(value: Any) -> list[float]:
    output = []
    for part in re.split(r"[|,;/\s]+", normalize_text(value)):
        if not part:
            continue
        number = number_or_none(part)
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
    admission_units_path: Path,
    historical_outcomes_path: Path,
    results: list[dict[str, Any]],
    changed: int,
    dry_run: bool,
) -> dict[str, Any]:
    by_status = Counter(str(row.get("status") or "") for row in results)
    linked_failures = Counter()
    for row in results:
        statuses = row.get("linkedOutcomeFailureStatuses")
        if isinstance(statuses, dict):
            linked_failures.update({str(key): int(value) for key, value in statuses.items()})
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_approved_outcome_admission_unit_review_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "decisionLogCsv": to_repo_relative(decision_log_path, repo_root),
            "admissionUnitsCsv": to_repo_relative(admission_units_path, repo_root),
            "historicalOutcomesCsv": to_repo_relative(historical_outcomes_path, repo_root),
        },
        "reviewer": REVIEWER,
        "dryRun": dry_run,
        "candidateRows": len(results),
        "matchedRows": by_status.get("matched", 0),
        "changedRows": changed,
        "byStatus": dict(sorted(by_status.items())),
        "linkedOutcomeFailureStatuses": dict(sorted(linked_failures.items())),
        "matchedRowsDetail": [
            {
                "reviewDecisionId": row.get("reviewDecisionId", ""),
                "sourceRecordId": row.get("sourceRecordId", ""),
                "linkedOutcomeCandidateId": row.get("linkedOutcomeCandidateId", ""),
                "linkedOutcomeReviewDecisionId": row.get("linkedOutcomeReviewDecisionId", ""),
                "linkedOutcomeQuota": row.get("linkedOutcomeQuota", ""),
            }
            for row in results
            if row.get("status") == "matched"
        ],
        "notes": [
            "Only pending AdmissionUnit rows are considered.",
            "Rows are approved only when a linked HistoricalOutcome exact-record decision is already approved, source/value matched, and the approved outcome quota matches AdmissionUnit quotaCandidates.",
            "This script reuses the stronger already-reviewed outcome source instead of accepting loose sourcePath text matches.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    fields = list(fieldnames)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


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
