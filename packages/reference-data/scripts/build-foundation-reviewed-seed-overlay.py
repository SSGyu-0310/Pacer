#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_P0_SEED_DIR = "packages/reference-data/data/p0-foundation"
DEFAULT_DECISION_LOG = "foundation_operational_review_decision_log.csv"
OUTPUT_CSV = "foundation_reviewed_seed_overlay.csv"
OUTPUT_SUMMARY = "foundation_reviewed_seed_overlay_summary.json"

FIELDNAMES = [
    "overlayId",
    "overlayStatus",
    "overlayAction",
    "reviewDecisionId",
    "reviewedVerifiedStatus",
    "approvedScope",
    "approvalScopeKey",
    "targetEntity",
    "sourceArtifact",
    "sourceRecordId",
    "seedEntityIds",
    "seedEntityCount",
    "unvCd",
    "universityName",
    "admissionYear",
    "academicYear",
    "examType",
    "admissionUnitName",
    "recruitmentGroup",
    "subjectName",
    "reviewer",
    "reviewedAt",
    "candidateValueSummary",
    "sourceCoordinates",
    "reviewNotes",
]


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    p0_seed_dir = resolve(repo_root, args.p0_seed_dir)
    decision_rows = list(read_csv(foundation_dir / args.decision_log_csv))
    indexes = load_indexes(foundation_dir, p0_seed_dir)

    approved_rows = [
        row
        for row in decision_rows
        if normalize_text(row.get("reviewOutcome")) == "approved"
        and normalize_text(row.get("decisionStatus")) == "reviewed"
    ]
    overlays = [build_overlay(row, indexes) for row in approved_rows]
    output_csv = foundation_dir / OUTPUT_CSV
    write_csv(output_csv, overlays)
    summary = summarize(repo_root, foundation_dir, p0_seed_dir, decision_rows, overlays)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation reviewed seed overlay complete. "
        f"approved={len(approved_rows)} overlayRows={len(overlays)} output={to_repo_relative(output_csv, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--p0-seed-dir", default=DEFAULT_P0_SEED_DIR)
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


def load_indexes(foundation_dir: Path, p0_seed_dir: Path) -> dict[str, Any]:
    p0_units = load_csv_by_id(p0_seed_dir / "admission_units.csv", "id")
    p0_outcomes = load_csv_by_id(p0_seed_dir / "historical_outcomes.csv", "id")
    p0_rules = list(read_csv(p0_seed_dir / "admission_rules.csv"))
    rule_ids_by_source_draft: dict[str, list[str]] = {}
    for row in p0_rules:
        formula = parse_json(row.get("formulaJson"))
        source_draft_id = normalize_text(formula.get("sourceRuleDraftId") if isinstance(formula, dict) else "")
        if source_draft_id:
            rule_ids_by_source_draft.setdefault(source_draft_id, []).append(normalize_text(row.get("id")))

    historical_outcomes = load_csv_by_id(
        foundation_dir / "foundation_historical_outcomes.csv",
        "outcomeCandidateId",
    )
    return {
        "p0Units": p0_units,
        "p0Outcomes": p0_outcomes,
        "ruleIdsBySourceDraft": rule_ids_by_source_draft,
        "historicalOutcomes": historical_outcomes,
    }


def load_csv_by_id(path: Path, id_field: str) -> dict[str, dict[str, str]]:
    output = {}
    if not path.exists():
        return output
    for row in read_csv(path):
        record_id = normalize_text(row.get(id_field))
        if record_id:
            output[record_id] = row
    return output


def build_overlay(row: dict[str, str], indexes: dict[str, Any]) -> dict[str, Any]:
    seed_ids = seed_entity_ids(row, indexes)
    status = "ready_to_apply" if seed_ids else "approved_source_review_only"
    return {
        "overlayId": deterministic_uuid("foundation-reviewed-seed-overlay:" + normalize_text(row.get("reviewDecisionId"))),
        "overlayStatus": status,
        "overlayAction": overlay_action(row, seed_ids),
        "reviewDecisionId": row.get("reviewDecisionId", ""),
        "reviewedVerifiedStatus": row.get("reviewedVerifiedStatus", ""),
        "approvedScope": row.get("approvedScope", ""),
        "approvalScopeKey": row.get("approvalScopeKey", ""),
        "targetEntity": row.get("targetEntity", ""),
        "sourceArtifact": row.get("sourceArtifact", ""),
        "sourceRecordId": row.get("sourceRecordId", ""),
        "seedEntityIds": "|".join(seed_ids),
        "seedEntityCount": len(seed_ids),
        "unvCd": row.get("unvCd", ""),
        "universityName": row.get("universityName", ""),
        "admissionYear": row.get("admissionYear", ""),
        "academicYear": row.get("academicYear", ""),
        "examType": row.get("examType", ""),
        "admissionUnitName": row.get("admissionUnitName", ""),
        "recruitmentGroup": row.get("recruitmentGroup", ""),
        "subjectName": row.get("subjectName", ""),
        "reviewer": row.get("reviewer", ""),
        "reviewedAt": row.get("reviewedAt", ""),
        "candidateValueSummary": row.get("candidateValueSummary", ""),
        "sourceCoordinates": row.get("sourceCoordinates", ""),
        "reviewNotes": row.get("reviewNotes", ""),
    }


def seed_entity_ids(row: dict[str, str], indexes: dict[str, Any]) -> list[str]:
    source_artifact = normalize_text(row.get("sourceArtifact"))
    source_record_id = normalize_text(row.get("sourceRecordId"))
    if source_artifact == "foundation_admission_units":
        return [source_record_id] if source_record_id in indexes["p0Units"] else []
    if source_artifact == "foundation_historical_outcomes":
        source_record = indexes["historicalOutcomes"].get(source_record_id, {})
        seed_id = historical_outcome_seed_id(source_record) if source_record else ""
        return [seed_id] if seed_id and seed_id in indexes["p0Outcomes"] else []
    if source_artifact == "foundation_csat_reflection_rule_drafts":
        return indexes["ruleIdsBySourceDraft"].get(source_record_id, [])
    if source_artifact in {
        "foundation_kice_grade_cuts",
        "foundation_kice_standard_score_distributions",
        "foundation_recruitment_quota_drafts",
        "foundation_screening_method_drafts",
    }:
        return []
    return []


def historical_outcome_seed_id(row: dict[str, str]) -> str:
    if not row:
        return ""
    seed = "foundation-historical-outcome-seed:" + "|".join(
        [
            first(row, "unitCandidateId"),
            first(row, "year"),
            first(row, "sourceCandidateSha256"),
            first(row, "sectionId"),
            first(row, "tableIndex"),
            first(row, "rowIndex"),
            first(row, "sourceUrl"),
            first(row, "quota"),
            first(row, "competitionRate"),
            first(row, "convertedScore70Cut"),
            first(row, "cutScoreCandidate"),
            first(row, "avgScoreCandidate"),
        ]
    )
    return deterministic_uuid(seed)


def overlay_action(row: dict[str, str], seed_ids: list[str]) -> str:
    source_artifact = normalize_text(row.get("sourceArtifact"))
    if not seed_ids:
        return "record_source_review_without_seed_mutation"
    if source_artifact == "foundation_csat_reflection_rule_drafts":
        return "mark_matching_admission_rules_reviewed"
    if source_artifact == "foundation_historical_outcomes":
        return "mark_historical_outcome_source_reviewed"
    if source_artifact == "foundation_admission_units":
        return "mark_admission_unit_source_reviewed"
    return "mark_seed_record_source_reviewed"


def summarize(
    repo_root: Path,
    foundation_dir: Path,
    p0_seed_dir: Path,
    decision_rows: list[dict[str, str]],
    overlays: list[dict[str, Any]],
) -> dict[str, Any]:
    approved = [
        row
        for row in decision_rows
        if normalize_text(row.get("reviewOutcome")) == "approved"
        and normalize_text(row.get("decisionStatus")) == "reviewed"
    ]
    by_status = Counter(str(row.get("overlayStatus") or "") for row in overlays)
    by_artifact = Counter(str(row.get("sourceArtifact") or "") for row in overlays)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_reviewed_seed_overlay_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "foundationDir": to_repo_relative(foundation_dir, repo_root),
            "p0SeedDir": to_repo_relative(p0_seed_dir, repo_root),
            "decisionRows": len(decision_rows),
            "approvedDecisionRows": len(approved),
        },
        "outputs": {
            "overlayCsv": to_repo_relative(foundation_dir / OUTPUT_CSV, repo_root),
        },
        "overlayRows": len(overlays),
        "byOverlayStatus": dict(sorted(by_status.items())),
        "bySourceArtifact": dict(sorted(by_artifact.items())),
        "affectedSeedEntityRows": sum(int(row.get("seedEntityCount") or 0) for row in overlays),
        "notes": [
            "This overlay records reviewed source approvals; it does not mutate the base p0 seed CSV files.",
            "Rows with overlayStatus=approved_source_review_only are useful verified evidence but do not map to the current p0 seed shape.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in FIELDNAMES})


def parse_json(value: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except json.JSONDecodeError:
        return None


def first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = normalize_text(row.get(key))
        if value:
            return value
    return ""


def deterministic_uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


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
