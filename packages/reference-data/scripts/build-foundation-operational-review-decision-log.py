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
DEFAULT_SOURCE_BUNDLE = "foundation_operational_source_review_bundle.csv"
OUTPUT_CSV = "foundation_operational_review_decision_log.csv"
OUTPUT_SUMMARY = "foundation_operational_review_decision_log_summary.json"

EDITABLE_FIELDS = [
    "decisionStatus",
    "reviewOutcome",
    "reviewedVerifiedStatus",
    "reviewer",
    "reviewedAt",
    "sourceMatchStatus",
    "valueMatchStatus",
    "approvedScope",
    "reviewNotes",
    "followupAction",
    "rejectionReason",
]

FIELDNAMES = [
    "reviewDecisionId",
    *EDITABLE_FIELDS,
    "bundleId",
    "approvalScopeKey",
    "promotionQueueId",
    "reviewLane",
    "targetEntity",
    "promotionAction",
    "ruleCategory",
    "sourceArtifact",
    "sourceRecordId",
    "admissionYear",
    "academicYear",
    "examType",
    "unvCd",
    "universityName",
    "admissionUnitName",
    "recruitmentGroup",
    "subjectName",
    "provider",
    "reviewPriorityScore",
    "confidence",
    "sourceRecordSummary",
    "candidateValueSummary",
    "sourceCoordinates",
    "reviewValueChecklist",
    "primaryEvidencePath",
    "primaryEvidenceKind",
    "primaryEvidenceExists",
    "snippetMatchTerm",
    "evidenceSnippet",
    "sourceUrls",
    "attachmentUrls",
    "rawPaths",
    "sourcePaths",
    "localEvidenceYears",
    "urlEvidenceYears",
    "reviewInstruction",
]


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    source_bundle_path = foundation_dir / args.source_bundle_csv
    output_path = foundation_dir / args.output_csv
    source_rows = list(read_csv(source_bundle_path))
    existing_rows = load_existing_decisions(output_path)

    rows = [build_decision_log_row(row, existing_rows) for row in source_rows]
    write_csv(output_path, rows)
    summary = summarize(repo_root, source_bundle_path, output_path, source_rows, rows)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation operational review decision log complete. "
        f"rows={len(rows)} output={to_repo_relative(output_path, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--source-bundle-csv", default=DEFAULT_SOURCE_BUNDLE)
    parser.add_argument("--output-csv", default=OUTPUT_CSV)
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


def load_existing_decisions(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    output = {}
    for row in read_csv(path):
        key = normalize_text(row.get("reviewDecisionId"))
        if key:
            output[key] = row
    return output


def build_decision_log_row(
    bundle_row: dict[str, str],
    existing_rows: dict[str, dict[str, str]],
) -> dict[str, Any]:
    decision_id = "review-log-" + normalize_text(bundle_row.get("promotionQueueId"))
    existing = existing_rows.get(decision_id, {})
    row = {
        "reviewDecisionId": decision_id,
        "decisionStatus": "unreviewed",
        "reviewOutcome": "pending",
        "reviewedVerifiedStatus": "",
        "reviewer": "",
        "reviewedAt": "",
        "sourceMatchStatus": "",
        "valueMatchStatus": "",
        "approvedScope": default_approved_scope(bundle_row),
        "reviewNotes": "",
        "followupAction": "",
        "rejectionReason": "",
    }
    for field in EDITABLE_FIELDS:
        if normalize_text(existing.get(field)):
            row[field] = existing[field]
    for field in FIELDNAMES:
        if field in row:
            continue
        row[field] = bundle_row.get(field, "")
    return row


def default_approved_scope(bundle_row: dict[str, str]) -> str:
    artifact = normalize_text(bundle_row.get("sourceArtifact"))
    if artifact in {
        "foundation_csat_reflection_rule_drafts",
        "foundation_recruitment_quota_drafts",
        "foundation_screening_method_drafts",
    }:
        return "university_year_rule_source"
    return "exact_record"


def summarize(
    repo_root: Path,
    source_bundle_path: Path,
    output_path: Path,
    source_rows: list[dict[str, str]],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_status = Counter(str(row.get("decisionStatus") or "") for row in rows)
    by_outcome = Counter(str(row.get("reviewOutcome") or "") for row in rows)
    by_lane = Counter(str(row.get("reviewLane") or "") for row in rows)
    by_scope = Counter(str(row.get("approvedScope") or "") for row in rows)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_operational_review_decision_log_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "sourceReviewBundleCsv": to_repo_relative(source_bundle_path, repo_root),
            "sourceReviewBundleRows": len(source_rows),
        },
        "outputs": {
            "decisionLogCsv": to_repo_relative(output_path, repo_root),
        },
        "rows": len(rows),
        "byDecisionStatus": dict(sorted(by_status.items())),
        "byReviewOutcome": dict(sorted(by_outcome.items())),
        "byReviewLane": dict(sorted(by_lane.items())),
        "byApprovedScope": dict(sorted(by_scope.items())),
        "notes": [
            "Editable fields are preserved when this script is rerun.",
            "Approved rows are not applied to seed data until audit passes and the reviewed seed overlay is generated.",
            "Use reviewOutcome=approved only after sourceMatchStatus=matched and valueMatchStatus=matched.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in FIELDNAMES})


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
