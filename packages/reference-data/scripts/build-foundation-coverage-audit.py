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
DEFAULT_SCOPE_OVERRIDES = "packages/reference-data/data/sources/admissions_scope_overrides.csv"

OUTPUT_JSONL = "foundation_university_year_coverage.jsonl"
OUTPUT_CSV = "foundation_university_year_coverage.csv"
OUTPUT_SUMMARY = "foundation_university_year_coverage_summary.json"

RECENT_YEARS = [2021, 2022, 2023, 2024, 2025, 2026, 2027]


RULE_DRAFT_FILES = [
    ("csatRuleDrafts", "foundation_csat_reflection_rule_drafts.csv"),
    ("recruitmentQuotaDrafts", "foundation_recruitment_quota_drafts.csv"),
    ("screeningMethodDrafts", "foundation_screening_method_drafts.csv"),
    ("schoolRecordRuleDrafts", "foundation_school_record_rule_drafts.csv"),
    ("eligibilityRuleDrafts", "foundation_eligibility_rule_drafts.csv"),
    ("generalRuleDrafts", "foundation_general_rule_drafts.csv"),
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    scope_overrides_path = resolve(repo_root, args.scope_overrides)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    rows = build_coverage_rows(foundation_dir, scope_overrides_path)
    rows.sort(key=lambda row: (str(row["universityName"]), int(row["admissionYear"])))

    write_jsonl(foundation_dir / OUTPUT_JSONL, rows)
    write_csv(foundation_dir / OUTPUT_CSV, rows)
    summary = summarize(foundation_dir, repo_root, rows)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation university-year coverage audit complete. "
        f"rows={len(rows)} sourceRich={summary['byCoverageTier'].get('source_rich_review_ready', 0)} "
        f"partial={summary['byCoverageTier'].get('partial_evidence', 0)} "
        f"gaps={summary['byCoverageTier'].get('source_gap', 0)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--scope-overrides", default=DEFAULT_SCOPE_OVERRIDES)
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


def build_coverage_rows(foundation_dir: Path, scope_overrides_path: Path) -> list[dict[str, Any]]:
    universities = read_universities(foundation_dir / "foundation_universities.csv")
    scope_overrides = read_scope_overrides(scope_overrides_path)
    rows: dict[tuple[str, int], dict[str, Any]] = {}
    for key, university in universities.items():
        listed_years = {int_or_none(part) for part in split_joined(university.get("years"))}
        listed_years = {year for year in listed_years if year is not None}
        for year in RECENT_YEARS:
            rows[(key, year)] = new_coverage_row(key, university, year, year in listed_years)

    apply_scope_overrides(rows, scope_overrides)
    add_admission_units(rows, universities, foundation_dir / "foundation_admission_units.csv")
    add_historical_outcomes(rows, universities, foundation_dir / "foundation_historical_outcomes.csv")
    add_admission_office_evidence(rows, universities, foundation_dir / "foundation_admission_office_evidence_links.csv")
    add_rule_drafts(rows, universities, foundation_dir)
    add_schedule_drafts(rows, universities, foundation_dir / "foundation_admission_schedule_drafts.csv")
    add_academyinfo(rows, universities, foundation_dir / "foundation_academyinfo_university_metric_summaries.csv")
    add_promotion_queue_counts(rows, universities, foundation_dir / "foundation_promotion_queue.csv")

    finalized = [finalize_row(row) for row in rows.values()]
    return finalized


def read_universities(path: Path) -> dict[str, dict[str, str]]:
    universities: dict[str, dict[str, str]] = {}
    for row in read_csv(path):
        key = university_key(row)
        if not key:
            continue
        universities[key] = row
    return universities


def new_coverage_row(key: str, university: dict[str, str], year: int, listed: bool) -> dict[str, Any]:
    return {
        "coverageAuditId": deterministic_uuid(f"university-year-coverage:{key}:{year}"),
        "artifactType": "foundation_university_year_coverage",
        "universityKey": key,
        "unvCd": normalize_text(university.get("unvCd")),
        "universityName": normalize_text(university.get("universityName")),
        "universityNameCanonical": normalize_text(university.get("universityNameCanonical")),
        "admissionYear": year,
        "universityListedInYear": listed,
        "admissionUnitCandidates": 0,
        "recruitmentGroups": Counter(),
        "historicalOutcomeCandidates": 0,
        "outcomeScoreCandidates": 0,
        "quotaCompetitionCandidates": 0,
        "mediumConfidenceOutcomes": 0,
        "lowOrLimitedConfidenceOutcomes": 0,
        "admissionOfficeDetectedYearEvidence": 0,
        "admissionOfficeCollectionYearEvidence": 0,
        "admissionOfficeTargets": Counter(),
        "csatRuleDrafts": 0,
        "recruitmentQuotaDrafts": 0,
        "screeningMethodDrafts": 0,
        "schoolRecordRuleDrafts": 0,
        "eligibilityRuleDrafts": 0,
        "generalRuleDrafts": 0,
        "ruleDraftHighOrMedium": 0,
        "ruleDraftLowOrLimited": 0,
        "ruleDraftNoiseOrBlockerFlags": Counter(),
        "scheduleDrafts": 0,
        "nationalScheduleDrafts": 0,
        "academyinfoMetricSummaries": 0,
        "promotionQueueP0Rows": 0,
        "promotionQueueP1Rows": 0,
        "promotionQueueP2Rows": 0,
        "promotionQueueP3Rows": 0,
        "scopeExcludedMissingFlags": Counter(),
        "scopeOverrideStatuses": Counter(),
        "scopeOverrideSourceUrls": [],
        "scopeOverrideNotes": [],
    }


def read_scope_overrides(path: Path) -> dict[tuple[str, int], list[dict[str, str]]]:
    overrides: dict[tuple[str, int], list[dict[str, str]]] = {}
    for row in read_csv(path):
        key = university_key(row)
        start_year = int_or_none(row.get("startAdmissionYear"))
        end_year = int_or_none(row.get("endAdmissionYear")) or start_year
        if not key or start_year is None or end_year is None:
            continue
        for year in RECENT_YEARS:
            if start_year <= year <= end_year:
                overrides.setdefault((key, year), []).append(row)
    return overrides


def apply_scope_overrides(
    rows: dict[tuple[str, int], dict[str, Any]],
    scope_overrides: dict[tuple[str, int], list[dict[str, str]]],
) -> None:
    for key, overrides in scope_overrides.items():
        target = rows.get(key)
        if not target:
            continue
        for override in overrides:
            for flag in split_joined(override.get("excludedMissingFlags")):
                target["scopeExcludedMissingFlags"][flag] += 1
            status = normalize_text(override.get("scopeStatus"))
            if status:
                target["scopeOverrideStatuses"][status] += 1
            source_url = normalize_text(override.get("sourceUrl"))
            if source_url and source_url not in target["scopeOverrideSourceUrls"]:
                target["scopeOverrideSourceUrls"].append(source_url)
            note = normalize_text(override.get("note"))
            if note and note not in target["scopeOverrideNotes"]:
                target["scopeOverrideNotes"].append(note)


def add_admission_units(rows: dict[tuple[str, int], dict[str, Any]], universities: dict[str, dict[str, str]], path: Path) -> None:
    for row in read_csv(path):
        key = university_key(row)
        year = int_or_none(row.get("year"))
        if not key or year not in RECENT_YEARS or (key, year) not in rows:
            continue
        target = rows[(key, year)]
        target["admissionUnitCandidates"] += 1
        group = normalize_text(row.get("recruitmentGroup"))
        if group:
            target["recruitmentGroups"][group] += 1


def add_historical_outcomes(
    rows: dict[tuple[str, int], dict[str, Any]],
    universities: dict[str, dict[str, str]],
    path: Path,
) -> None:
    for row in read_csv(path):
        key = university_key(row)
        year = int_or_none(row.get("year"))
        if not key or year not in RECENT_YEARS or (key, year) not in rows:
            continue
        target = rows[(key, year)]
        target["historicalOutcomeCandidates"] += 1
        if bool_value(row.get("hasOutcomeScore")):
            target["outcomeScoreCandidates"] += 1
        if bool_value(row.get("hasQuotaAndCompetition")):
            target["quotaCompetitionCandidates"] += 1
        confidence = normalize_text(row.get("confidence"))
        if confidence == "medium":
            target["mediumConfidenceOutcomes"] += 1
        if confidence in {"low", "limited"}:
            target["lowOrLimitedConfidenceOutcomes"] += 1


def add_admission_office_evidence(
    rows: dict[tuple[str, int], dict[str, Any]],
    universities: dict[str, dict[str, str]],
    path: Path,
) -> None:
    for row in read_csv(path):
        key = university_key(row)
        if not key:
            continue
        target_name = normalize_text(row.get("evidenceTarget"))
        for year in split_years(row.get("detectedAdmissionYears")):
            if (key, year) in rows:
                rows[(key, year)]["admissionOfficeDetectedYearEvidence"] += 1
                if target_name:
                    rows[(key, year)]["admissionOfficeTargets"][target_name] += 1
        for year in split_years(row.get("collectionYears")):
            if (key, year) in rows:
                rows[(key, year)]["admissionOfficeCollectionYearEvidence"] += 1


def add_rule_drafts(rows: dict[tuple[str, int], dict[str, Any]], universities: dict[str, dict[str, str]], foundation_dir: Path) -> None:
    for column, file_name in RULE_DRAFT_FILES:
        for row in read_csv(foundation_dir / file_name):
            key = university_key(row)
            year = int_or_none(row.get("admissionYear"))
            if not key or year not in RECENT_YEARS or (key, year) not in rows:
                continue
            target = rows[(key, year)]
            target[column] += 1
            strength = normalize_text(row.get("reviewStrength"))
            if strength in {"high", "medium"}:
                target["ruleDraftHighOrMedium"] += 1
            elif strength in {"low", "limited"}:
                target["ruleDraftLowOrLimited"] += 1
            for flag in split_joined(row.get("draftFlags")):
                if re.search(r"noise|low_structured|low_context|unknown|review_required", flag):
                    target["ruleDraftNoiseOrBlockerFlags"][flag] += 1


def add_schedule_drafts(rows: dict[tuple[str, int], dict[str, Any]], universities: dict[str, dict[str, str]], path: Path) -> None:
    schedule_rows = read_csv(path)
    national_schedule_years: set[int] = set()
    for row in schedule_rows:
        scope = normalize_text(row.get("scheduleScope"))
        year = int_or_none(row.get("admissionYear"))
        if year not in RECENT_YEARS:
            continue
        if scope == "national":
            if national_schedule_can_satisfy_gap(row):
                national_schedule_years.add(year)
            continue
        if scope != "university":
            continue
        key = university_key(row)
        if not key or (key, year) not in rows:
            continue
        rows[(key, year)]["scheduleDrafts"] += 1

    for (_key, year), target in rows.items():
        if year in national_schedule_years and target["scheduleDrafts"] == 0:
            target["scheduleDrafts"] += 1
            target["nationalScheduleDrafts"] += 1


def national_schedule_can_satisfy_gap(row: dict[str, str]) -> bool:
    strength = normalize_text(row.get("reviewStrength"))
    if strength == "high":
        return True
    if strength != "medium":
        return False
    signals = set(split_joined(row.get("scheduleSignals")))
    return bool(split_joined(row.get("dateCandidateValues"))) and "application_period" in signals


def add_academyinfo(rows: dict[tuple[str, int], dict[str, Any]], universities: dict[str, dict[str, str]], path: Path) -> None:
    for row in read_csv(path):
        key = university_key({"unvCd": row.get("matchedUnvCd"), "universityName": row.get("matchedUniversityName")})
        year = int_or_none(row.get("surveyYear"))
        if not key or year not in RECENT_YEARS or (key, year) not in rows:
            continue
        rows[(key, year)]["academyinfoMetricSummaries"] += 1


def add_promotion_queue_counts(
    rows: dict[tuple[str, int], dict[str, Any]],
    universities: dict[str, dict[str, str]],
    path: Path,
) -> None:
    for row in read_csv(path):
        key = university_key(row)
        year = int_or_none(row.get("admissionYear")) or int_or_none(row.get("academicYear"))
        if not key or year not in RECENT_YEARS or (key, year) not in rows:
            continue
        tier = normalize_text(row.get("priorityTier")).upper()
        field = f"promotionQueue{tier}Rows"
        if field in rows[(key, year)]:
            rows[(key, year)][field] += 1


def finalize_row(row: dict[str, Any]) -> dict[str, Any]:
    score = coverage_score(row)
    missing_flags = missing_flags_for(row)
    row["coverageScore"] = score
    row["coverageTier"] = coverage_tier(score, missing_flags)
    row["coverageMissingFlags"] = "|".join(missing_flags)
    row["recruitmentGroups"] = "|".join(value for value, _ in row["recruitmentGroups"].most_common())
    row["admissionOfficeTargets"] = "|".join(value for value, _ in row["admissionOfficeTargets"].most_common())
    row["ruleDraftNoiseOrBlockerFlags"] = "|".join(
        value for value, _ in row["ruleDraftNoiseOrBlockerFlags"].most_common()
    )
    row["scopeExcludedMissingFlags"] = "|".join(
        value for value, _ in row["scopeExcludedMissingFlags"].most_common()
    )
    row["scopeOverrideStatuses"] = "|".join(value for value, _ in row["scopeOverrideStatuses"].most_common())
    row["scopeOverrideSourceUrls"] = "|".join(row["scopeOverrideSourceUrls"])
    row["scopeOverrideNotes"] = "|".join(row["scopeOverrideNotes"])
    return row


def coverage_score(row: dict[str, Any]) -> int:
    score = 0
    if row["universityListedInYear"]:
        score += 10
    if row["admissionUnitCandidates"] > 0:
        score += 10
    if row["historicalOutcomeCandidates"] > 0:
        score += 10
    if row["outcomeScoreCandidates"] > 0:
        score += 20
    if row["quotaCompetitionCandidates"] > 0:
        score += 10
    if row["csatRuleDrafts"] > 0:
        score += 10
    if row["recruitmentQuotaDrafts"] > 0:
        score += 5
    if row["screeningMethodDrafts"] > 0:
        score += 5
    if row["schoolRecordRuleDrafts"] > 0:
        score += 5
    if row["eligibilityRuleDrafts"] > 0:
        score += 5
    if row["admissionOfficeDetectedYearEvidence"] > 0:
        score += 5
    if row["scheduleDrafts"] > 0:
        score += 3
    if row["promotionQueueP0Rows"] > 0:
        score += 2
    return min(score, 100)


def missing_flags_for(row: dict[str, Any]) -> list[str]:
    flags = []
    if not row["universityListedInYear"]:
        flags.append("university_not_listed_for_year")
        return flags
    if row["admissionUnitCandidates"] == 0:
        flags.append("missing_admission_units")
    if row["historicalOutcomeCandidates"] == 0:
        flags.append("missing_historical_outcomes")
    if row["outcomeScoreCandidates"] == 0:
        flags.append("missing_outcome_scores")
    if row["quotaCompetitionCandidates"] == 0:
        flags.append("missing_quota_competition")
    if row["csatRuleDrafts"] == 0:
        flags.append("missing_csat_rule_draft")
    if row["recruitmentQuotaDrafts"] == 0 and not historical_rule_gap_is_non_operating(row):
        flags.append("missing_recruitment_quota_draft")
    if row["screeningMethodDrafts"] == 0 and not historical_rule_gap_is_non_operating(row):
        flags.append("missing_screening_method_draft")
    if row["schoolRecordRuleDrafts"] == 0 and not historical_rule_gap_is_non_operating(row):
        flags.append("missing_school_record_rule_draft")
    if row["eligibilityRuleDrafts"] == 0 and not historical_rule_gap_is_non_operating(row):
        flags.append("missing_eligibility_rule_draft")
    if row["admissionOfficeDetectedYearEvidence"] == 0 and not has_operating_core_coverage(row):
        flags.append("missing_admission_office_detected_year_evidence")
    if row["scheduleDrafts"] == 0 and not historical_schedule_gap_is_non_operating(row):
        flags.append("missing_schedule_draft")
    excluded = set(scope_excluded_missing_flags(row))
    return [flag for flag in flags if flag not in excluded]


def scope_excluded_missing_flags(row: dict[str, Any]) -> list[str]:
    value = row.get("scopeExcludedMissingFlags")
    if isinstance(value, Counter):
        return list(value.keys())
    return split_joined(value)


def has_operating_core_coverage(row: dict[str, Any]) -> bool:
    return all(
        row[field] > 0
        for field in [
            "admissionUnitCandidates",
            "historicalOutcomeCandidates",
            "outcomeScoreCandidates",
            "quotaCompetitionCandidates",
            "csatRuleDrafts",
            "recruitmentQuotaDrafts",
            "screeningMethodDrafts",
            "schoolRecordRuleDrafts",
            "eligibilityRuleDrafts",
        ]
    )


def historical_schedule_gap_is_non_operating(row: dict[str, Any]) -> bool:
    year = int_or_none(row.get("admissionYear"))
    return bool(year and year <= 2021 and has_historical_outcome_core(row, require_direct_evidence=False))


def historical_rule_gap_is_non_operating(row: dict[str, Any]) -> bool:
    year = int_or_none(row.get("admissionYear"))
    if not year or year > 2025:
        return False
    return has_historical_outcome_core(row) and has_csat_rule_or_scope_exclusion(row)


def has_historical_outcome_core(row: dict[str, Any], *, require_direct_evidence: bool = True) -> bool:
    fields = [
        "admissionUnitCandidates",
        "historicalOutcomeCandidates",
        "outcomeScoreCandidates",
    ]
    if require_direct_evidence:
        fields.append("admissionOfficeDetectedYearEvidence")
    return all(row[field] > 0 for field in fields)


def has_csat_rule_or_scope_exclusion(row: dict[str, Any]) -> bool:
    return row["csatRuleDrafts"] > 0 or "missing_csat_rule_draft" in set(scope_excluded_missing_flags(row))


def coverage_tier(score: int, missing_flags: list[str]) -> str:
    missing = set(missing_flags)
    if score >= 80 and "missing_outcome_scores" not in missing and "missing_csat_rule_draft" not in missing:
        return "source_rich_review_ready"
    if score >= 60:
        return "review_ready_partial"
    if score >= 35:
        return "partial_evidence"
    return "source_gap"


def summarize(foundation_dir: Path, repo_root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_year = Counter(str(row["admissionYear"]) for row in rows)
    by_tier = Counter(str(row["coverageTier"]) for row in rows)
    by_missing = Counter(flag for row in rows for flag in split_joined(row["coverageMissingFlags"]))
    by_scope_status = Counter(status for row in rows for status in split_joined(row["scopeOverrideStatuses"]))
    by_scope_excluded = Counter(flag for row in rows for flag in split_joined(row["scopeExcludedMissingFlags"]))
    rich_by_year = Counter(str(row["admissionYear"]) for row in rows if row["coverageTier"] == "source_rich_review_ready")
    p0_by_year = Counter(str(row["admissionYear"]) for row in rows if int(row["promotionQueueP0Rows"]) > 0)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_university_year_coverage_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in input_paths(foundation_dir)
            if path.exists()
        ],
        "coverageRows": {
            "total": len(rows),
            "universities": len({row["universityKey"] for row in rows}),
            "years": RECENT_YEARS,
        },
        "byAdmissionYear": dict(sorted(by_year.items())),
        "byCoverageTier": dict(sorted(by_tier.items())),
        "sourceRichReviewReadyByYear": dict(sorted(rich_by_year.items())),
        "hasPromotionQueueP0ByYear": dict(sorted(p0_by_year.items())),
        "byMissingFlag": counter_rows(by_missing, 40),
        "byScopeOverrideStatus": counter_rows(by_scope_status, 20),
        "byScopeExcludedMissingFlag": counter_rows(by_scope_excluded, 20),
        "notes": [
            "This audit is a coverage diagnostic, not a verified completeness claim.",
            "Rows are one university per admission year for 2021~2027.",
            "coverageScore is heuristic and rewards source-preserving candidates across AdmissionUnit, HistoricalOutcome, AdmissionRule, Schedule, admission-office evidence, and p0 promotion queue rows.",
            "Missing flags identify where more source review, parsing, or collection is needed before DB promotion.",
            "Scope overrides remove missing flags only when an official source makes that requirement not applicable for the university-year.",
        ],
    }


def input_paths(foundation_dir: Path) -> list[Path]:
    return [
        foundation_dir / "foundation_universities.csv",
        foundation_dir / "foundation_admission_units.csv",
        foundation_dir / "foundation_historical_outcomes.csv",
        foundation_dir / "foundation_admission_office_evidence_links.csv",
        foundation_dir / "foundation_admission_schedule_drafts.csv",
        foundation_dir / "foundation_academyinfo_university_metric_summaries.csv",
        foundation_dir / "foundation_promotion_queue.csv",
        *[foundation_dir / file_name for _, file_name in RULE_DRAFT_FILES],
    ]


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
        "coverageAuditId",
        "artifactType",
        "universityKey",
        "unvCd",
        "universityName",
        "universityNameCanonical",
        "admissionYear",
        "universityListedInYear",
        "coverageScore",
        "coverageTier",
        "coverageMissingFlags",
        "scopeExcludedMissingFlags",
        "scopeOverrideStatuses",
        "scopeOverrideSourceUrls",
        "scopeOverrideNotes",
        "admissionUnitCandidates",
        "recruitmentGroups",
        "historicalOutcomeCandidates",
        "outcomeScoreCandidates",
        "quotaCompetitionCandidates",
        "mediumConfidenceOutcomes",
        "lowOrLimitedConfidenceOutcomes",
        "admissionOfficeDetectedYearEvidence",
        "admissionOfficeCollectionYearEvidence",
        "admissionOfficeTargets",
        "csatRuleDrafts",
        "recruitmentQuotaDrafts",
        "screeningMethodDrafts",
        "schoolRecordRuleDrafts",
        "eligibilityRuleDrafts",
        "generalRuleDrafts",
        "ruleDraftHighOrMedium",
        "ruleDraftLowOrLimited",
        "ruleDraftNoiseOrBlockerFlags",
        "scheduleDrafts",
        "nationalScheduleDrafts",
        "academyinfoMetricSummaries",
        "promotionQueueP0Rows",
        "promotionQueueP1Rows",
        "promotionQueueP2Rows",
        "promotionQueueP3Rows",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def university_key(row: dict[str, Any]) -> str:
    unv_cd = normalize_text(row.get("unvCd") or row.get("matchedUnvCd"))
    if unv_cd:
        return f"unvCd:{unv_cd}"
    name = normalize_text(row.get("universityName") or row.get("matchedUniversityName") or row.get("universityNameCanonical"))
    return f"name:{name}" if name else ""


def split_years(value: Any) -> list[int]:
    years = []
    for part in split_joined(value):
        year = int_or_none(part)
        if year in RECENT_YEARS:
            years.append(year)
    return years


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def bool_value(value: Any) -> bool:
    return normalize_text(value).lower() in {"true", "1", "yes", "y"}


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
    if isinstance(value, bool):
        return "true" if value else "false"
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
