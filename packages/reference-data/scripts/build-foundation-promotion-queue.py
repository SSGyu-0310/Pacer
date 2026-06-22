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
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"

OUTPUT_JSONL = "foundation_promotion_queue.jsonl"
OUTPUT_CSV = "foundation_promotion_queue.csv"
OUTPUT_SUMMARY = "foundation_promotion_queue_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027

try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


ARTIFACTS: list[dict[str, Any]] = [
    {
        "file": "foundation_universities.csv",
        "record_id": "universityCandidateId",
        "target": "University",
        "action": "promote_university_candidate",
    },
    {
        "file": "foundation_admission_units.csv",
        "record_id": "unitCandidateId",
        "target": "AdmissionUnit",
        "action": "promote_yearly_admission_unit_candidate",
    },
    {
        "file": "foundation_admission_unit_clusters.csv",
        "record_id": "unitClusterId",
        "target": "AdmissionUnitClusterReview",
        "action": "review_admission_unit_continuity",
    },
    {
        "file": "foundation_historical_outcomes.csv",
        "record_id": "outcomeCandidateId",
        "target": "HistoricalOutcome",
        "action": "promote_historical_outcome_candidate",
    },
    {
        "file": "foundation_historical_outcome_series.csv",
        "record_id": "outcomeSeriesId",
        "target": "HistoricalOutcomeSeriesReview",
        "action": "review_historical_outcome_series",
    },
    {
        "file": "foundation_csat_reflection_rule_drafts.csv",
        "record_id": "csatRuleDraftId",
        "target": "AdmissionRule",
        "action": "review_csat_reflection_rule_draft",
        "rule_category": "csat_reflection",
    },
    {
        "file": "foundation_recruitment_quota_drafts.csv",
        "record_id": "quotaDraftId",
        "target": "AdmissionRule",
        "action": "review_recruitment_quota_draft",
        "rule_category": "recruitment_quota",
    },
    {
        "file": "foundation_screening_method_drafts.csv",
        "record_id": "screeningMethodDraftId",
        "target": "AdmissionRule",
        "action": "review_screening_method_draft",
        "rule_category": "screening_method",
    },
    {
        "file": "foundation_school_record_rule_drafts.csv",
        "record_id": "schoolRecordRuleDraftId",
        "target": "AdmissionRule",
        "action": "review_school_record_rule_draft",
        "rule_category": "school_record_reflection",
    },
    {
        "file": "foundation_eligibility_rule_drafts.csv",
        "record_id": "eligibilityRuleDraftId",
        "target": "AdmissionRule",
        "action": "review_eligibility_rule_draft",
        "rule_category": "eligibility",
    },
    {
        "file": "foundation_general_rule_drafts.csv",
        "record_id": "generalRuleDraftId",
        "target": "AdmissionRule",
        "action": "review_general_rule_draft",
        "rule_category": "general_rule",
    },
    {
        "file": "foundation_admission_schedule_drafts.csv",
        "record_id": "scheduleDraftId",
        "target": "AdmissionSchedule",
        "action": "review_admission_schedule_draft",
    },
    {
        "file": "foundation_kice_grade_cuts.csv",
        "record_id": "gradeCutCandidateId",
        "target": "GradeCutReference",
        "action": "promote_kice_grade_cut_candidate",
    },
    {
        "file": "foundation_kice_standard_score_distributions.csv",
        "record_id": "distributionCandidateId",
        "target": "StandardScoreDistributionReference",
        "action": "promote_kice_standard_score_distribution_candidate",
    },
    {
        "file": "foundation_kice_press_evidence_links.csv",
        "record_id": "evidenceCandidateSha256",
        "target": "ExamScoreReferenceEvidence",
        "action": "review_kice_press_evidence",
    },
    {
        "file": "foundation_kcue_policy_evidence_links.csv",
        "record_id": "evidenceCandidateSha256",
        "target": "PolicyEvidence",
        "action": "review_kcue_policy_evidence",
    },
    {
        "file": "foundation_academyinfo_university_metric_summaries.csv",
        "record_id": "summaryCandidateSha256",
        "target": "AuxiliaryUniversityMetric",
        "action": "review_academyinfo_metric_summary",
    },
    {
        "file": "foundation_admission_office_evidence_links.csv",
        "record_id": "evidenceCandidateSha256",
        "target": "AdmissionOfficeEvidence",
        "action": "review_admission_office_evidence_link",
    },
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    queue = build_queue(foundation_dir)
    queue.sort(
        key=lambda row: (
            priority_sort(row.get("priorityTier")),
            -int_or_none(row.get("reviewPriorityScore") or 0) if int_or_none(row.get("reviewPriorityScore")) else 0,
            str(row.get("targetEntity") or ""),
            str(row.get("universityName") or ""),
            int_or_large(row.get("admissionYear") or row.get("academicYear")),
            str(row.get("sourceArtifact") or ""),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, queue)
    write_csv(foundation_dir / OUTPUT_CSV, queue)
    summary = summarize(foundation_dir, repo_root, queue)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation promotion queue complete. "
        f"queueRows={len(queue)} p0={summary['byPriorityTier'].get('p0', 0)} "
        f"p1={summary['byPriorityTier'].get('p1', 0)} p2={summary['byPriorityTier'].get('p2', 0)} "
        f"p3={summary['byPriorityTier'].get('p3', 0)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
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


def build_queue(foundation_dir: Path) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for artifact in ARTIFACTS:
        path = foundation_dir / artifact["file"]
        for row in read_csv(path):
            item = make_queue_item(artifact, row)
            queue.append(item)
    return queue


def make_queue_item(artifact: dict[str, Any], row: dict[str, str]) -> dict[str, Any]:
    source_artifact = artifact["file"].replace(".csv", "")
    source_record_id = normalize_text(row.get(artifact["record_id"])) or fallback_record_id(source_artifact, row)
    target = infer_target_entity(artifact, row)
    admission_year = admission_year_value(row)
    academic_year = academic_year_value(row)
    priority_tier = infer_priority_tier(artifact, row, target, admission_year, academic_year)
    review_priority = review_priority_score(artifact, row, priority_tier)
    blocker_flags = blocker_flags_for(row)
    provider = provider_value(row)
    university_name = first_nonempty(row, "universityName", "matchedUniversityName", "universityNameCanonical")

    return {
        "promotionQueueId": deterministic_uuid(f"promotion-queue:{source_artifact}:{source_record_id}"),
        "artifactType": "foundation_promotion_queue_item",
        "sourceArtifact": source_artifact,
        "sourceRecordId": source_record_id,
        "targetEntity": target,
        "promotionAction": artifact["action"],
        "ruleCategory": artifact.get("rule_category", ""),
        "priorityTier": priority_tier,
        "reviewPriorityScore": review_priority,
        "reviewStrength": normalize_text(row.get("reviewStrength")),
        "confidence": first_nonempty(row, "confidence", "candidateConfidence", "sourceConfidence"),
        "reviewStatus": normalize_text(row.get("reviewStatus")) or "needs_human_verification",
        "admissionYear": admission_year or "",
        "academicYear": academic_year or "",
        "examType": normalize_text(row.get("examType")),
        "unvCd": first_nonempty(row, "unvCd", "matchedUnvCd"),
        "universityName": university_name,
        "admissionUnitName": first_nonempty(
            row,
            "admissionUnitName",
            "representativeAdmissionUnitName",
            "admissionUnitCanonicalName",
        ),
        "recruitmentGroup": normalize_text(row.get("recruitmentGroup")),
        "subjectName": first_nonempty(row, "subjectNameNormalized", "subjectName", "subjectGroup"),
        "provider": provider,
        "sourceRows": normalize_text(row.get("sourceRows") or row.get("sourceRowsCount") or row.get("evidenceCount")),
        "draftFlags": normalize_text(row.get("draftFlags") or row.get("coverageFlags") or row.get("seriesFlags")),
        "blockerFlags": "|".join(blocker_flags),
        "evidenceSummary": evidence_summary(row),
        "sourceUrls": first_nonempty(row, "sourceUrls", "sourceUrl", "viewUrl", "sourceCandidateUrl"),
        "attachmentUrls": first_nonempty(row, "attachmentUrls", "attachmentUrl"),
        "rawPaths": first_nonempty(row, "rawPaths", "rawPath", "rawAttachmentPath"),
        "sourcePaths": first_nonempty(row, "sourcePaths", "sourcePath", "csvPath", "textPath"),
    }


def infer_target_entity(artifact: dict[str, Any], row: dict[str, str]) -> str:
    if artifact["file"] == "foundation_kcue_policy_evidence_links.csv":
        return normalize_text(row.get("targetEntity")) or artifact["target"]
    if artifact["file"] == "foundation_kice_press_evidence_links.csv":
        return normalize_text(row.get("targetEntity")) or artifact["target"]
    if artifact["file"] == "foundation_admission_office_evidence_links.csv":
        return normalize_text(row.get("evidenceTarget")) or artifact["target"]
    return str(artifact["target"])


def infer_priority_tier(
    artifact: dict[str, Any],
    row: dict[str, str],
    target_entity: str,
    admission_year: int | None,
    academic_year: int | None,
) -> str:
    file_name = str(artifact["file"])
    recent = is_recent(admission_year or academic_year)
    strength = normalize_text(row.get("reviewStrength"))
    confidence = normalize_text(row.get("confidence") or row.get("candidateConfidence"))
    flags = set(split_joined(row.get("draftFlags") or row.get("coverageFlags") or row.get("seriesFlags")))
    blockers = set(blocker_flags_for(row))

    if file_name == "foundation_universities.csv":
        return "p0"
    if file_name == "foundation_admission_units.csv":
        return "p0" if recent else "p2"
    if file_name == "foundation_admission_unit_clusters.csv":
        if "full_recent_2021_2027_coverage" in flags or int_or_none(row.get("recentYears2021To2027Count")) and int(row["recentYears2021To2027Count"]) >= 5:
            return "p0"
        return "p1" if recent_range_present(row.get("recentYears2021To2027")) else "p2"
    if file_name == "foundation_historical_outcomes.csv":
        has_outcome_score = truthy(row.get("hasOutcomeScore"))
        has_quota_and_competition = truthy(row.get("hasQuotaAndCompetition"))
        if has_outcome_score and has_quota_and_competition and recent:
            return "p0"
        if has_outcome_score and recent:
            return "p1"
        return "p2"
    if file_name == "foundation_historical_outcome_series.csv":
        if "converted_score_scale_review_required" in flags:
            return "p1"
        if int_or_none(row.get("recentYears2021To2027Count")) and int(row["recentYears2021To2027Count"]) >= 5:
            return "p0"
        return "p1" if recent_range_present(row.get("recentYears2021To2027")) else "p2"
    if target_entity in {"GradeCutReference", "StandardScoreDistributionReference"}:
        return "p0" if recent else "p2"
    if target_entity in {"ExamScoreReference", "GradeCutReference", "StandardScoreDistributionReference", "ExamScoreReferenceEvidence"}:
        return "p1" if recent else "p2"
    if file_name.endswith("_drafts.csv"):
        if "unknown_admission_year" in blockers or "has_noise_signals" in flags or "has_low_context_text" in flags:
            return "p2" if recent else "p3"
        if strength in {"high", "medium"} and recent:
            return "p0"
        if strength in {"high", "medium"}:
            return "p1"
        if strength in {"low", "limited"} and recent:
            return "p2"
        return "p3"
    if file_name == "foundation_admission_schedule_drafts.csv":
        if "unknown_admission_year" in blockers:
            return "p2"
        return "p0" if recent else "p1"
    if file_name == "foundation_admission_office_evidence_links.csv":
        score = int_or_none(row.get("reviewPriorityScore")) or 0
        if score >= 100:
            return "p1"
        return "p2"
    if file_name == "foundation_kcue_policy_evidence_links.csv":
        return "p1" if target_entity in {"AdmissionRule", "AdmissionSchedule"} else "p2"
    if file_name == "foundation_academyinfo_university_metric_summaries.csv":
        if row.get("matchStatus") == "matched_by_unv_cd":
            return "p1"
        return "p2"
    if confidence in {"high", "medium"}:
        return "p1"
    return "p2"


def review_priority_score(artifact: dict[str, Any], row: dict[str, str], priority_tier: str) -> int:
    explicit = int_or_none(row.get("reviewPriorityScore"))
    if explicit is not None:
        return explicit

    tier_base = {"p0": 80, "p1": 60, "p2": 40, "p3": 20}.get(priority_tier, 30)
    bonus = 0
    if is_recent(admission_year_value(row) or academic_year_value(row)):
        bonus += 10
    if normalize_text(row.get("reviewStrength")) == "high":
        bonus += 20
    elif normalize_text(row.get("reviewStrength")) == "medium":
        bonus += 10
    if normalize_text(row.get("confidence")) == "medium":
        bonus += 8
    if normalize_text(row.get("confidence")) == "high":
        bonus += 16
    if truthy(row.get("hasOutcomeScore")):
        bonus += 10
    if truthy(row.get("hasQuotaAndCompetition")):
        bonus += 10
    return tier_base + bonus


def blocker_flags_for(row: dict[str, str]) -> list[str]:
    flags = []
    draft_flags = split_joined(row.get("draftFlags") or row.get("coverageFlags") or row.get("seriesFlags"))
    source_quality = split_joined(row.get("sourceQualitySignals"))
    if normalize_text(row.get("admissionYearStatus")) == "unknown":
        flags.append("unknown_admission_year")
    if normalize_text(row.get("sourceAreaReviewFlag")):
        flags.append(normalize_text(row.get("sourceAreaReviewFlag")))
    for flag in draft_flags:
        if re.search(r"noise|low_structured|low_context|review_required|unknown|missing", flag):
            flags.append(flag)
    for flag in source_quality:
        if re.search(r"noise|low|year_only|title_like|ocr|empty", flag):
            flags.append(flag)
    if normalize_text(row.get("matchStatus")) in {"unmatched_or_ambiguous", "ambiguous"}:
        flags.append("unmatched_or_ambiguous_university")
    if normalize_text(row.get("confidence")) in {"limited", "low"}:
        flags.append(f"{normalize_text(row.get('confidence'))}_confidence")
    if normalize_text(row.get("candidateConfidence")) in {"low", "limited"}:
        flags.append(f"{normalize_text(row.get('candidateConfidence'))}_candidate_confidence")
    return unique_preserve_order(flags)


def evidence_summary(row: dict[str, str]) -> str:
    parts = []
    for key in [
        "sourceProviders",
        "sourceProvider",
        "evidenceRoles",
        "evidenceRole",
        "evidenceTypes",
        "sourceDocumentKinds",
        "documentKinds",
        "scoreAvailability",
        "reviewStrength",
    ]:
        value = normalize_text(row.get(key))
        if value:
            parts.append(f"{key}={shorten(value, 160)}")
    return "; ".join(parts[:6])


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "promotionQueueId",
        "artifactType",
        "sourceArtifact",
        "sourceRecordId",
        "targetEntity",
        "promotionAction",
        "ruleCategory",
        "priorityTier",
        "reviewPriorityScore",
        "reviewStrength",
        "confidence",
        "reviewStatus",
        "admissionYear",
        "academicYear",
        "examType",
        "unvCd",
        "universityName",
        "admissionUnitName",
        "recruitmentGroup",
        "subjectName",
        "provider",
        "sourceRows",
        "draftFlags",
        "blockerFlags",
        "evidenceSummary",
        "sourceUrls",
        "attachmentUrls",
        "rawPaths",
        "sourcePaths",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def summarize(foundation_dir: Path, repo_root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_priority = Counter(str(row.get("priorityTier") or "") for row in rows)
    by_target = Counter(str(row.get("targetEntity") or "") for row in rows)
    by_artifact = Counter(str(row.get("sourceArtifact") or "") for row in rows)
    by_action = Counter(str(row.get("promotionAction") or "") for row in rows)
    by_provider = Counter(str(row.get("provider") or "") for row in rows)
    by_blocker = Counter(flag for row in rows for flag in split_joined(row.get("blockerFlags")))
    recent_rows = sum(
        1
        for row in rows
        if is_recent(int_or_none(row.get("admissionYear")) or int_or_none(row.get("academicYear")))
    )
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_promotion_queue_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {
                "path": to_repo_relative(foundation_dir / artifact["file"], repo_root),
                "sha256": sha256_file(foundation_dir / artifact["file"]),
            }
            for artifact in ARTIFACTS
            if (foundation_dir / artifact["file"]).exists()
        ],
        "queueRows": {
            "total": len(rows),
            "recentAdmissionOrAcademicYears2021To2027": recent_rows,
        },
        "byPriorityTier": dict(sorted(by_priority.items())),
        "byTargetEntity": counter_rows(by_target, 40),
        "bySourceArtifact": counter_rows(by_artifact, 40),
        "byPromotionAction": counter_rows(by_action, 40),
        "byProvider": counter_rows(by_provider, 40),
        "byBlockerFlag": counter_rows(by_blocker, 60),
        "notes": [
            "This queue is an operational verification index, not a verified database export.",
            "priorityTier is heuristic: p0 rows are first-pass promotion candidates, p1/p2 require more review, p3 is mostly old/low-context/noisy evidence.",
            "All rows preserve sourceArtifact/sourceRecordId so reviewers can return to the full foundation artifact before promotion.",
        ],
    }


def fallback_record_id(source_artifact: str, row: dict[str, str]) -> str:
    digest = hashlib.sha256()
    digest.update(source_artifact.encode("utf-8"))
    for key in sorted(row):
        digest.update(str(key).encode("utf-8"))
        digest.update(str(row.get(key) or "").encode("utf-8"))
    return digest.hexdigest()


def provider_value(row: dict[str, str]) -> str:
    return first_nonempty(row, "sourceProviders", "sourceProvider", "provider")


def admission_year_value(row: dict[str, str]) -> int | None:
    return int_or_none(first_nonempty(row, "admissionYear", "year", "firstYear"))


def academic_year_value(row: dict[str, str]) -> int | None:
    return int_or_none(first_nonempty(row, "academicYear", "surveyYear"))


def first_nonempty(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = normalize_text(row.get(key))
        if value:
            return value
    return ""


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def recent_range_present(value: Any) -> bool:
    return any(is_recent(int_or_none(part)) for part in split_joined(value))


def is_recent(value: Any) -> bool:
    year = int_or_none(value)
    return year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX


def priority_sort(value: Any) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(normalize_text(value), 9)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def truthy(value: Any) -> bool:
    return normalize_text(value).lower() in {"1", "true", "t", "yes", "y"}


def shorten(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def int_or_large(value: Any) -> int:
    parsed = int_or_none(value)
    return parsed if parsed is not None else 999999


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
