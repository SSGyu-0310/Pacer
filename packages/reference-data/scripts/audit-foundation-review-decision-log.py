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
OUTPUT_SUMMARY = "foundation_review_decision_log_audit_summary.json"

VALID_DECISION_STATUS = {"unreviewed", "reviewed", "needs_followup"}
VALID_REVIEW_OUTCOME = {"pending", "approved", "rejected", "needs_followup"}
VALID_VERIFIED_STATUS = {"verified", "live"}
VALID_MATCH_STATUS = {"matched", "mismatch", "not_applicable", "unclear"}
VALID_APPROVED_SCOPE = {"exact_record", "university_year_rule_source"}


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    decision_log_path = foundation_dir / args.decision_log_csv
    rows = list(read_csv(decision_log_path))
    errors, warnings = audit_rows(rows)
    summary = summarize(repo_root, decision_log_path, rows, errors, warnings)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation review decision log audit complete. "
        f"status={summary['status']} rows={len(rows)} approved={summary['counts']['approvedRows']}"
    )
    if errors:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--decision-log-csv", default=DEFAULT_DECISION_LOG)
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


def audit_rows(rows: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    for index, row in enumerate(rows, start=2):
        decision_id = normalize_text(row.get("reviewDecisionId"))
        if not decision_id:
            errors.append(f"row {index}: missing reviewDecisionId")
        elif decision_id in seen_ids:
            errors.append(f"row {index}: duplicate reviewDecisionId={decision_id}")
        seen_ids.add(decision_id)

        decision_status = normalize_text(row.get("decisionStatus"))
        review_outcome = normalize_text(row.get("reviewOutcome"))
        source_match = normalize_text(row.get("sourceMatchStatus"))
        value_match = normalize_text(row.get("valueMatchStatus"))
        approved_scope = normalize_text(row.get("approvedScope"))
        verified_status = normalize_text(row.get("reviewedVerifiedStatus"))

        if decision_status not in VALID_DECISION_STATUS:
            errors.append(f"{decision_id}: invalid decisionStatus={decision_status}")
        if review_outcome not in VALID_REVIEW_OUTCOME:
            errors.append(f"{decision_id}: invalid reviewOutcome={review_outcome}")
        if source_match and source_match not in VALID_MATCH_STATUS:
            errors.append(f"{decision_id}: invalid sourceMatchStatus={source_match}")
        if value_match and value_match not in VALID_MATCH_STATUS:
            errors.append(f"{decision_id}: invalid valueMatchStatus={value_match}")
        if approved_scope not in VALID_APPROVED_SCOPE:
            errors.append(f"{decision_id}: invalid approvedScope={approved_scope}")

        if review_outcome == "approved":
            require(row, decision_id, "reviewer", errors)
            require(row, decision_id, "reviewedAt", errors)
            require(row, decision_id, "candidateValueSummary", errors)
            require(row, decision_id, "sourceCoordinates", errors)
            require(row, decision_id, "approvalScopeKey", errors)
            if decision_status != "reviewed":
                errors.append(f"{decision_id}: approved row must have decisionStatus=reviewed")
            if source_match != "matched":
                errors.append(f"{decision_id}: approved row must have sourceMatchStatus=matched")
            if value_match != "matched":
                errors.append(f"{decision_id}: approved row must have valueMatchStatus=matched")
            if verified_status not in VALID_VERIFIED_STATUS:
                errors.append(
                    f"{decision_id}: approved row must have reviewedVerifiedStatus in {sorted(VALID_VERIFIED_STATUS)}"
                )
        elif decision_status == "reviewed" and review_outcome == "pending":
            warnings.append(f"{decision_id}: reviewed status with pending outcome")
        elif review_outcome == "rejected":
            require(row, decision_id, "reviewer", errors)
            require(row, decision_id, "reviewedAt", errors)
            require(row, decision_id, "rejectionReason", errors)
        elif review_outcome == "needs_followup":
            require(row, decision_id, "followupAction", errors)
    return errors, warnings


def require(row: dict[str, str], decision_id: str, field: str, errors: list[str]) -> None:
    if not normalize_text(row.get(field)):
        errors.append(f"{decision_id}: missing required field {field}")


def summarize(
    repo_root: Path,
    decision_log_path: Path,
    rows: list[dict[str, str]],
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    by_status = Counter(normalize_text(row.get("decisionStatus")) for row in rows)
    by_outcome = Counter(normalize_text(row.get("reviewOutcome")) for row in rows)
    by_lane = Counter(normalize_text(row.get("reviewLane")) for row in rows)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_review_decision_log_audit_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "error" if errors else "ok",
        "errors": errors,
        "warnings": warnings,
        "inputs": {
            "decisionLogCsv": to_repo_relative(decision_log_path, repo_root),
        },
        "counts": {
            "rows": len(rows),
            "approvedRows": by_outcome.get("approved", 0),
            "rejectedRows": by_outcome.get("rejected", 0),
            "followupRows": by_outcome.get("needs_followup", 0),
            "pendingRows": by_outcome.get("pending", 0),
        },
        "byDecisionStatus": dict(sorted(by_status.items())),
        "byReviewOutcome": dict(sorted(by_outcome.items())),
        "byReviewLane": dict(sorted(by_lane.items())),
    }


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
