#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_COVERAGE_AUDIT = (
    "packages/reference-data/data/public/foundation/"
    "foundation_university_year_coverage.csv"
)

OUTPUT_JSONL = "foundation_gap_action_queue.jsonl"
OUTPUT_CSV = "foundation_gap_action_queue.csv"
OUTPUT_SUMMARY = "foundation_gap_action_queue_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027


ACTION_CONFIG: dict[str, dict[str, str]] = {
    "university_not_listed_for_year": {
        "gapCategory": "university_scope",
        "targetEntity": "University",
        "recommendedAction": "verify_university_listing_or_exclusion",
        "sourceHint": "adiga_university_list",
    },
    "missing_admission_units": {
        "gapCategory": "admission_unit",
        "targetEntity": "AdmissionUnit",
        "recommendedAction": "collect_or_parse_admission_units",
        "sourceHint": "adiga_or_admission_office",
    },
    "missing_historical_outcomes": {
        "gapCategory": "historical_outcome",
        "targetEntity": "HistoricalOutcome",
        "recommendedAction": "collect_or_parse_historical_outcomes",
        "sourceHint": "adiga_or_admission_office",
    },
    "missing_outcome_scores": {
        "gapCategory": "historical_outcome_score",
        "targetEntity": "HistoricalOutcome",
        "recommendedAction": "collect_or_parse_outcome_score_metrics",
        "sourceHint": "adiga_outcome_table_or_admission_office_result",
    },
    "missing_quota_competition": {
        "gapCategory": "historical_outcome_quota_competition",
        "targetEntity": "HistoricalOutcome",
        "recommendedAction": "collect_or_parse_quota_competition",
        "sourceHint": "adiga_or_admission_office_result",
    },
    "missing_csat_rule_draft": {
        "gapCategory": "admission_rule",
        "targetEntity": "AdmissionRule",
        "recommendedAction": "collect_or_parse_csat_reflection_rule",
        "sourceHint": "adiga_rule_table_or_admission_office_recruitment_guide",
    },
    "missing_recruitment_quota_draft": {
        "gapCategory": "admission_rule",
        "targetEntity": "AdmissionRule",
        "recommendedAction": "collect_or_parse_recruitment_quota_rule",
        "sourceHint": "recruitment_guide_or_adiga_quota_table",
    },
    "missing_screening_method_draft": {
        "gapCategory": "admission_rule",
        "targetEntity": "AdmissionRule",
        "recommendedAction": "collect_or_parse_screening_method_rule",
        "sourceHint": "recruitment_guide_or_adiga_screening_table",
    },
    "missing_school_record_rule_draft": {
        "gapCategory": "admission_rule",
        "targetEntity": "AdmissionRule",
        "recommendedAction": "collect_or_parse_school_record_rule",
        "sourceHint": "adiga_student_record_table_or_recruitment_guide",
    },
    "missing_eligibility_rule_draft": {
        "gapCategory": "admission_rule",
        "targetEntity": "AdmissionRule",
        "recommendedAction": "collect_or_parse_eligibility_rule",
        "sourceHint": "recruitment_guide_eligibility_section",
    },
    "missing_admission_office_detected_year_evidence": {
        "gapCategory": "direct_evidence",
        "targetEntity": "AdmissionOfficeEvidence",
        "recommendedAction": "collect_or_map_direct_admission_office_evidence",
        "sourceHint": "university_admission_office_pdf_hwp_xlsx",
    },
    "missing_schedule_draft": {
        "gapCategory": "admission_schedule",
        "targetEntity": "AdmissionSchedule",
        "recommendedAction": "collect_or_parse_admission_schedule",
        "sourceHint": "admission_office_schedule_or_kcue_common_schedule",
    },
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    coverage_path = resolve(repo_root, args.coverage_audit)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    coverage_rows = read_csv(coverage_path)
    actions = build_actions(coverage_rows)
    actions.sort(
        key=lambda row: (
            priority_sort(row.get("priorityTier")),
            -int_or_none(row.get("actionPriorityScore") or 0) if int_or_none(row.get("actionPriorityScore")) else 0,
            -int_or_none(row.get("admissionYear") or 0) if int_or_none(row.get("admissionYear")) else 0,
            str(row.get("universityName") or ""),
            str(row.get("missingFlag") or ""),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, actions)
    write_csv(foundation_dir / OUTPUT_CSV, actions)
    summary = summarize(coverage_path, repo_root, actions)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap action queue complete. "
        f"actions={len(actions)} p0={summary['byPriorityTier'].get('p0', 0)} "
        f"p1={summary['byPriorityTier'].get('p1', 0)} p2={summary['byPriorityTier'].get('p2', 0)} "
        f"p3={summary['byPriorityTier'].get('p3', 0)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--coverage-audit", default=DEFAULT_COVERAGE_AUDIT)
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


def build_actions(coverage_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for row in coverage_rows:
        for missing_flag in split_joined(row.get("coverageMissingFlags")):
            config = ACTION_CONFIG.get(missing_flag)
            if not config:
                continue
            year = int_or_none(row.get("admissionYear"))
            priority_tier = infer_priority_tier(row, missing_flag, year)
            action_priority_score = action_priority(row, missing_flag, priority_tier, year)
            actions.append(
                {
                    "gapActionId": deterministic_uuid(
                        f"gap-action:{row.get('universityKey')}:{row.get('admissionYear')}:{missing_flag}"
                    ),
                    "artifactType": "foundation_gap_action_item",
                    "universityKey": normalize_text(row.get("universityKey")),
                    "unvCd": normalize_text(row.get("unvCd")),
                    "universityName": normalize_text(row.get("universityName")),
                    "admissionYear": year or "",
                    "coverageTier": normalize_text(row.get("coverageTier")),
                    "coverageScore": int_or_none(row.get("coverageScore")) or 0,
                    "missingFlag": missing_flag,
                    "gapCategory": config["gapCategory"],
                    "targetEntity": config["targetEntity"],
                    "recommendedAction": config["recommendedAction"],
                    "sourceHint": config["sourceHint"],
                    "priorityTier": priority_tier,
                    "actionPriorityScore": action_priority_score,
                    "expectedAvailability": expected_availability(missing_flag, year),
                    "existingEvidenceSummary": evidence_snapshot(row),
                    "blockingReason": blocking_reason(row, missing_flag, year),
                    "promotionQueueP0Rows": int_or_none(row.get("promotionQueueP0Rows")) or 0,
                    "admissionOfficeCollectionYearEvidence": int_or_none(
                        row.get("admissionOfficeCollectionYearEvidence")
                    )
                    or 0,
                    "reviewStatus": "needs_source_collection_or_parser_review",
                }
            )
    return actions


def infer_priority_tier(row: dict[str, str], missing_flag: str, year: int | None) -> str:
    coverage_tier = normalize_text(row.get("coverageTier"))
    score = int_or_none(row.get("coverageScore")) or 0
    critical = {
        "missing_admission_units",
        "missing_historical_outcomes",
        "missing_outcome_scores",
        "missing_quota_competition",
        "missing_csat_rule_draft",
    }
    current_cycle_rules = {
        "missing_admission_units",
        "missing_csat_rule_draft",
        "missing_recruitment_quota_draft",
        "missing_screening_method_draft",
        "missing_school_record_rule_draft",
        "missing_eligibility_rule_draft",
        "missing_schedule_draft",
        "missing_admission_office_detected_year_evidence",
    }

    if year is not None and year <= 2026 and missing_flag in critical:
        return "p0"
    if year == 2027 and missing_flag in current_cycle_rules:
        return "p0"
    if coverage_tier == "source_gap" and year is not None and year <= 2026:
        return "p0"
    if missing_flag in {"missing_historical_outcomes", "missing_outcome_scores", "missing_quota_competition"} and year == 2027:
        return "p1"
    if missing_flag in {"missing_schedule_draft", "missing_admission_office_detected_year_evidence"}:
        return "p1"
    if missing_flag in critical:
        return "p1"
    if missing_flag == "university_not_listed_for_year":
        return "p2"
    return "p2" if coverage_tier in {"partial_evidence", "review_ready_partial"} else "p3"


def action_priority(row: dict[str, str], missing_flag: str, priority_tier: str, year: int | None) -> int:
    tier_base = {"p0": 90, "p1": 70, "p2": 45, "p3": 20}.get(priority_tier, 30)
    score = int_or_none(row.get("coverageScore")) or 0
    action_weight = {
        "missing_historical_outcomes": 35,
        "missing_outcome_scores": 32,
        "missing_admission_units": 30,
        "missing_csat_rule_draft": 28,
        "missing_quota_competition": 24,
        "missing_admission_office_detected_year_evidence": 20,
        "missing_schedule_draft": 18,
        "missing_recruitment_quota_draft": 16,
        "missing_screening_method_draft": 14,
        "missing_school_record_rule_draft": 12,
        "missing_eligibility_rule_draft": 12,
        "university_not_listed_for_year": 8,
    }.get(missing_flag, 10)
    year_bonus = 0
    if year in {2025, 2026}:
        year_bonus = 12
    elif year == 2027:
        year_bonus = 10
    elif year in {2023, 2024}:
        year_bonus = 8
    elif year in {2021, 2022}:
        year_bonus = 6
    gap_bonus = max(0, 100 - score) // 5
    collection_bonus = 4 if int_or_none(row.get("admissionOfficeCollectionYearEvidence")) else 0
    return tier_base + action_weight + year_bonus + gap_bonus + collection_bonus


def expected_availability(missing_flag: str, year: int | None) -> str:
    if year is None:
        return "unknown_year_requires_manual_assignment"
    if missing_flag in {"missing_outcome_scores", "missing_quota_competition", "missing_historical_outcomes"}:
        if year >= 2027:
            return "likely_not_public_until_after_cycle"
        if year == 2026:
            return "check_public_now_or_pending_release"
        return "should_be_public_or_parse_gap"
    if missing_flag in {
        "missing_admission_units",
        "missing_csat_rule_draft",
        "missing_recruitment_quota_draft",
        "missing_screening_method_draft",
        "missing_school_record_rule_draft",
        "missing_eligibility_rule_draft",
        "missing_schedule_draft",
    }:
        if year == 2027:
            return "should_be_public_for_current_cycle"
        return "should_be_public_or_parse_gap"
    if missing_flag == "missing_admission_office_detected_year_evidence":
        return "should_be_public_or_parse_gap"
    if missing_flag == "university_not_listed_for_year":
        return "verify_scope_or_institution_status"
    return "needs_review"


def evidence_snapshot(row: dict[str, str]) -> str:
    keys = [
        "admissionUnitCandidates",
        "historicalOutcomeCandidates",
        "outcomeScoreCandidates",
        "quotaCompetitionCandidates",
        "csatRuleDrafts",
        "recruitmentQuotaDrafts",
        "screeningMethodDrafts",
        "schoolRecordRuleDrafts",
        "eligibilityRuleDrafts",
        "scheduleDrafts",
        "admissionOfficeDetectedYearEvidence",
        "promotionQueueP0Rows",
    ]
    return "; ".join(f"{key}={normalize_text(row.get(key)) or '0'}" for key in keys)


def blocking_reason(row: dict[str, str], missing_flag: str, year: int | None) -> str:
    availability = expected_availability(missing_flag, year)
    if availability == "likely_not_public_until_after_cycle":
        return "current_cycle_outcome_may_not_be_public_yet"
    if missing_flag == "university_not_listed_for_year":
        return "coverage_universe_or_institution_status_needs_verification"
    if int_or_none(row.get("promotionQueueP0Rows")):
        return "existing_p0_source_candidates_require_parser_or_human_review"
    if int_or_none(row.get("admissionOfficeCollectionYearEvidence")):
        return "collected_admission_office_sources_require_year_mapping_or_parser_review"
    return "no_structured_candidate_detected_for_required_entity"


def summarize(coverage_path: Path, repo_root: Path, actions: list[dict[str, Any]]) -> dict[str, Any]:
    by_priority = Counter(str(row["priorityTier"]) for row in actions)
    by_flag = Counter(str(row["missingFlag"]) for row in actions)
    by_category = Counter(str(row["gapCategory"]) for row in actions)
    by_year = Counter(str(row["admissionYear"]) for row in actions)
    by_availability = Counter(str(row["expectedAvailability"]) for row in actions)
    by_target = Counter(str(row["targetEntity"]) for row in actions)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_action_queue_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "input": {"path": to_repo_relative(coverage_path, repo_root), "sha256": sha256_file(coverage_path)},
        "actionRows": {
            "total": len(actions),
            "p0": by_priority.get("p0", 0),
            "p1": by_priority.get("p1", 0),
            "p2": by_priority.get("p2", 0),
            "p3": by_priority.get("p3", 0),
        },
        "byPriorityTier": dict(sorted(by_priority.items())),
        "byMissingFlag": counter_rows(by_flag, 40),
        "byGapCategory": counter_rows(by_category, 30),
        "byAdmissionYear": dict(sorted(by_year.items())),
        "byExpectedAvailability": counter_rows(by_availability, 30),
        "byTargetEntity": counter_rows(by_target, 30),
        "notes": [
            "This is an operational action queue derived from coverage missing flags, not evidence of verified absence.",
            "p0 actions are the highest-priority collection/parser/review gaps for making recent public data promotable.",
            "2027 outcome-score gaps are marked as likely not public until after the cycle; rule/schedule gaps remain actionable.",
        ],
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "gapActionId",
        "artifactType",
        "universityKey",
        "unvCd",
        "universityName",
        "admissionYear",
        "coverageTier",
        "coverageScore",
        "missingFlag",
        "gapCategory",
        "targetEntity",
        "recommendedAction",
        "sourceHint",
        "priorityTier",
        "actionPriorityScore",
        "expectedAvailability",
        "existingEvidenceSummary",
        "blockingReason",
        "promotionQueueP0Rows",
        "admissionOfficeCollectionYearEvidence",
        "reviewStatus",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def priority_sort(value: Any) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(normalize_text(value), 9)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
