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


DEFAULT_RULE_CANDIDATES = (
    "packages/reference-data/data/public/foundation/"
    "foundation_admission_rule_review_candidates.csv"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/foundation"

OUTPUT_JSONL = "foundation_school_record_rule_drafts.jsonl"
OUTPUT_CSV = "foundation_school_record_rule_drafts.csv"
OUTPUT_SUMMARY = "foundation_school_record_rule_drafts_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027

PERCENT_PATTERN = re.compile(r"(?<!\d)(?:100|[1-9]?\d)(?:\.\d+)?\s*%")
NOISE_TERMS = re.compile(r"개인정보|고유식별정보|보유기간|동의|수집 및 이용|환불|원서접수")
SUBJECT_SCOPE_PATTERN = re.compile(
    r"(?:반영\s*교과|반영\s*과목|공통과목|일반선택과목|진로선택과목|"
    r"상위\s*\d+\s*개\s*과목)[가-힣A-Za-z0-9·ㆍ&(),./:%\s+-]{0,140}"
)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    input_path = resolve(repo_root, args.rule_candidates)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(input_path)
    school_record_rows = [row for row in rows if is_school_record_candidate(row)]
    drafts = build_drafts(school_record_rows)

    write_jsonl(output_dir / OUTPUT_JSONL, drafts)
    write_csv(output_dir / OUTPUT_CSV, drafts)
    summary = summarize(input_path, repo_root, school_record_rows, drafts)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation school record rule drafts complete. "
        f"sourceRows={len(school_record_rows)} drafts={len(drafts)} "
        f"recentDrafts={summary['draftRows']['recentAdmissionYears2021To2027']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule-candidates", default=DEFAULT_RULE_CANDIDATES)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
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


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_drafts(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        years, year_source = candidate_admission_years(row)
        if not years:
            years = ["unknown"]
            year_source = "unknown_year"
        for year in years:
            key = (
                normalize_text(row.get("unvCd")),
                normalize_text(row.get("universityName")),
                year,
            )
            if key not in groups:
                groups[key] = new_group(key)
            add_row(groups[key], row)
            groups[key]["yearInferenceSignals"][year_source] += 1

    drafts = [finalize_group(group) for group in groups.values()]
    drafts.sort(
        key=lambda row: (
            year_sort_bucket(row.get("admissionYear")),
            -int_or_none(row.get("admissionYear") or 0) if int_or_none(row.get("admissionYear")) else 0,
            str(row.get("universityName") or ""),
            -int(row.get("reviewPriorityScore") or 0),
        )
    )
    return drafts


def new_group(key: tuple[str, str, str]) -> dict[str, Any]:
    unv_cd, university_name, admission_year = key
    return {
        "unvCd": unv_cd,
        "universityName": university_name,
        "admissionYear": admission_year,
        "sourceProviders": Counter(),
        "evidenceRoles": Counter(),
        "evidenceTypes": Counter(),
        "sourceDocumentKinds": Counter(),
        "schoolRecordSignals": Counter(),
        "subjectSignals": Counter(),
        "scoreMetricSignals": Counter(),
        "formulaSignals": Counter(),
        "semesterYearSignals": Counter(),
        "noiseSignals": Counter(),
        "yearInferenceSignals": Counter(),
        "percentageValues": Counter(),
        "weightValues": Counter(),
        "gradeScaleCandidates": Counter(),
        "achievementGradeCandidates": Counter(),
        "subjectScopeCandidates": Counter(),
        "sourceEvidenceIds": [],
        "sourceUrls": [],
        "attachmentUrls": [],
        "rawPaths": [],
        "sourcePaths": [],
        "sampleEvidence": [],
        "maxSourcePriority": 0,
        "sourceRows": 0,
    }


def add_row(group: dict[str, Any], row: dict[str, str]) -> None:
    group["sourceRows"] += 1
    provider = normalize_text(row.get("sourceProvider"))
    if provider:
        group["sourceProviders"][provider] += 1
    bump_counter(group["evidenceRoles"], row.get("evidenceRole"))
    bump_counter(group["evidenceTypes"], row.get("evidenceType"))
    bump_counter(group["sourceDocumentKinds"], row.get("sourceDocumentKind"))

    text = normalize_text(row.get("textPreview"))
    for signal in school_record_signals(row, text):
        group["schoolRecordSignals"][signal] += 1
    for signal in split_joined(row.get("subjectSignals")):
        group["subjectSignals"][signal] += 1
    for signal in split_joined(row.get("scoreMetricSignals")):
        group["scoreMetricSignals"][signal] += 1
    for signal in split_joined(row.get("formulaSignals")):
        group["formulaSignals"][signal] += 1
    for signal in semester_year_signals(text):
        group["semesterYearSignals"][signal] += 1
    for signal in noise_signals(row, text):
        group["noiseSignals"][signal] += 1
    for value in extract_percentages(row, text):
        group["percentageValues"][value] += 1
    for value in split_joined(row.get("weightValues")):
        group["weightValues"][value] += 1
    for value in grade_scale_candidates(row, text):
        group["gradeScaleCandidates"][value] += 1
    for value in achievement_grade_candidates(text):
        group["achievementGradeCandidates"][value] += 1
    for value in subject_scope_candidates(text):
        group["subjectScopeCandidates"][value] += 1

    priority = int_or_none(row.get("reviewPriorityScore")) or 0
    group["maxSourcePriority"] = max(group["maxSourcePriority"], priority)
    add_limited(group["sourceEvidenceIds"], row.get("sourceEvidenceId"), 120)
    add_limited(group["sourceUrls"], row.get("sourceUrl"), 30)
    add_limited(group["attachmentUrls"], row.get("attachmentUrl"), 30)
    add_limited(group["rawPaths"], row.get("rawPath"), 30)
    add_limited(group["sourcePaths"], row.get("sourcePath"), 30)
    add_sample(group, row, priority)


def is_school_record_candidate(row: dict[str, str]) -> bool:
    if row.get("ruleCategory") == "school_record_reflection":
        return True
    text = normalize_text(row.get("textPreview"))
    return bool(school_record_signals(row, text))


def candidate_admission_years(row: dict[str, str]) -> tuple[list[str], str]:
    explicit_years = normalized_year_values(row.get("admissionYears"))
    if explicit_years:
        return explicit_years, "explicit_admission_year"

    collection_years = [
        year
        for year in normalized_year_values(row.get("collectionYears"))
        if RECENT_YEAR_MIN <= int(year) <= RECENT_YEAR_MAX
    ]
    if len(collection_years) == 1:
        return collection_years, "collection_year_fallback"

    return [], ""


def normalized_year_values(value: Any) -> list[str]:
    values = []
    for part in split_joined(value):
        year = int_or_none(part)
        if year is not None and 1900 <= year <= 2099:
            values.append(str(year))
    return unique_preserve_order(values)


def school_record_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    detected = set(split_joined(row.get("detectedSignals")))
    role = normalize_text(row.get("evidenceRole"))
    if role in {"student_rule", "recruitment_rule_image"}:
        signals.append("student_record_evidence_role")
    if "school_record" in detected or re.search(r"학생부|학교생활기록부|교과\s*성적", text):
        signals.append("school_record")
    if "reflection_ratio" in detected or re.search(r"반영\s*비율|반영\s*지표|반영\s*교과", text):
        signals.append("reflection_ratio")
    if "score_formula" in detected or re.search(r"산출\s*방법|산출식|점수|배점|환산", text):
        signals.append("score_formula")
    if re.search(r"석차\s*등급|등급\s*점수|과목별\s*석차", text):
        signals.append("grade_conversion_table")
    if re.search(r"성취도|성취평가|진로선택|A\s+B\s+C", text):
        signals.append("achievement_evaluation")
    if re.search(r"반영\s*교과|반영\s*과목|상위\s*\d+\s*개\s*과목", text):
        signals.append("subject_scope")
    if re.search(r"비교내신|검정고시", text):
        signals.append("comparative_record")
    if re.search(r"출결|봉사", text):
        signals.append("attendance_or_volunteer")
    return signals


def semester_year_signals(text: str) -> list[str]:
    signals = []
    if re.search(r"1\s*학년", text):
        signals.append("grade_year_1")
    if re.search(r"2\s*학년", text):
        signals.append("grade_year_2")
    if re.search(r"3\s*학년", text):
        signals.append("grade_year_3")
    if re.search(r"전\s*학년|전학년", text):
        signals.append("all_grade_years")
    if re.search(r"1\s*학기", text):
        signals.append("semester_1")
    if re.search(r"2\s*학기", text):
        signals.append("semester_2")
    if re.search(r"학년\s*,?\s*학기\s*반영\s*비율\s*동일|학년\s*학기\s*구분\s*없음", text):
        signals.append("same_year_semester_weight")
    if re.search(r"졸업예정|졸업자|재수|삼수", text):
        signals.append("graduation_status_context")
    return signals


def noise_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    detected = set(split_joined(row.get("detectedSignals")))
    if NOISE_TERMS.search(text):
        signals.append("has_noise_terms")
    if "csat" in detected and not re.search(r"학생부|학교생활기록부|교과", text):
        signals.append("csat_without_school_record_term")
    if "screening_method" in detected and not re.search(r"학생부|학교생활기록부|교과", text):
        signals.append("screening_method_without_school_record_term")
    if not school_record_signals(row, text) and not split_joined(row.get("scoreMetricSignals")):
        signals.append("low_structured_school_record_signal")
    return signals


def extract_percentages(row: dict[str, str], text: str) -> list[str]:
    values = split_joined(row.get("percentageValues"))
    for match in PERCENT_PATTERN.finditer(text):
        values.append(re.sub(r"\s+", "", match.group(0)))
    return unique_preserve_order(values)[:60]


def grade_scale_candidates(row: dict[str, str], text: str) -> list[str]:
    candidates = []
    metrics = set(split_joined(row.get("scoreMetricSignals")))
    if "grade" in metrics or re.search(r"석차\s*등급|등급\s*점수", text):
        if all(re.search(rf"{grade}\s*등급", text) for grade in range(1, 10)):
            candidates.append("1등급-9등급")
        elif re.search(r"석차\s*등급|등급\s*점수", text):
            candidates.append("grade_score_table")
    if "converted_score" in metrics:
        candidates.append("converted_score_table")
    if "raw_score" in metrics:
        candidates.append("raw_score_table")
    if "highest_score" in metrics or re.search(r"최고점|만점", text):
        candidates.append("highest_score_context")
    return unique_preserve_order(candidates)


def achievement_grade_candidates(text: str) -> list[str]:
    candidates = []
    if re.search(r"성취도|성취평가|진로선택", text):
        candidates.append("achievement_evaluation")
    if re.search(r"(?<![A-Za-z])A\s+B\s+C(?![A-Za-z])", text):
        candidates.append("A-B-C")
    if re.search(r"A\s*[:=]\s*\d|B\s*[:=]\s*\d|C\s*[:=]\s*\d", text):
        candidates.append("achievement_to_grade_or_score_mapping")
    return unique_preserve_order(candidates)


def subject_scope_candidates(text: str) -> list[str]:
    values = []
    for match in SUBJECT_SCOPE_PATTERN.finditer(text):
        value = clean_candidate_label(match.group(0))
        if is_useful_label(value):
            values.append(value)
    return unique_preserve_order(values)[:80]


def clean_candidate_label(value: str) -> str:
    value = re.sub(r"\s+", " ", value)
    return value.strip(" /,.:;·ㆍ-")[:180]


def is_useful_label(value: str) -> bool:
    if len(value) < 4:
        return False
    return not bool(NOISE_TERMS.search(value))


def add_sample(group: dict[str, Any], row: dict[str, str], priority: int) -> None:
    preview = normalize_text(row.get("textPreview"))
    if not preview:
        return
    sample = {
        "priority": priority,
        "sourceProvider": normalize_text(row.get("sourceProvider")),
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "sourceEvidenceId": normalize_text(row.get("sourceEvidenceId")),
        "schoolRecordSignals": school_record_signals(row, preview),
        "subjectSignals": split_joined(row.get("subjectSignals")),
        "scoreMetricSignals": split_joined(row.get("scoreMetricSignals")),
        "formulaSignals": split_joined(row.get("formulaSignals")),
        "semesterYearSignals": semester_year_signals(preview),
        "noiseSignals": noise_signals(row, preview),
        "percentageValues": extract_percentages(row, preview)[:30],
        "gradeScaleCandidates": grade_scale_candidates(row, preview),
        "achievementGradeCandidates": achievement_grade_candidates(preview),
        "subjectScopeCandidates": subject_scope_candidates(preview)[:10],
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "attachmentUrl": normalize_text(row.get("attachmentUrl")),
        "preview": preview[:700],
    }
    samples = group["sampleEvidence"]
    if sample["sourceEvidenceId"] in {item.get("sourceEvidenceId") for item in samples}:
        return
    samples.append(sample)
    samples.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            -len(item.get("schoolRecordSignals") or []),
            -len(item.get("scoreMetricSignals") or []),
            len(item.get("noiseSignals") or []),
        )
    )
    del samples[8:]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    year = normalize_text(group["admissionYear"])
    status = "unknown" if year == "unknown" else "detected"
    provider_counts = dict(sorted(group["sourceProviders"].items()))
    school_record = sorted(group["schoolRecordSignals"])
    subjects = sorted(group["subjectSignals"])
    metrics = sorted(group["scoreMetricSignals"])
    formulas = sorted(group["formulaSignals"])
    semester_year = sorted(group["semesterYearSignals"])
    noise = sorted(group["noiseSignals"])
    percentages = top_counter_values(group["percentageValues"], 60)
    weights = top_counter_values(group["weightValues"], 80)
    grade_scale = top_counter_values(group["gradeScaleCandidates"], 20)
    achievement = top_counter_values(group["achievementGradeCandidates"], 20)
    subject_scope = top_counter_values(group["subjectScopeCandidates"], 80)
    flags = draft_flags(group, school_record, subjects, metrics, formulas, semester_year, noise, percentages, weights)
    policy_json_draft = {
        "status": "review_candidate",
        "schoolRecordSignals": school_record,
        "subjectSignals": subjects,
        "scoreMetricSignals": metrics,
        "formulaSignals": formulas,
        "semesterYearSignals": semester_year,
        "noiseSignals": noise,
        "percentageValues": percentages[:40],
        "weightValues": weights[:50],
        "gradeScaleCandidates": grade_scale,
        "achievementGradeCandidates": achievement,
        "subjectScopeCandidates": subject_scope[:40],
        "sourceEvidenceIds": group["sourceEvidenceIds"][:30],
        "needsHumanVerification": True,
    }
    return {
        "schoolRecordRuleDraftId": deterministic_uuid(
            f"school-record-rule-draft:{group['unvCd']}:{group['universityName']}:{year}"
        ),
        "artifactType": "foundation_school_record_rule_draft",
        "unvCd": group["unvCd"],
        "universityName": group["universityName"],
        "admissionYear": "" if year == "unknown" else int_or_none(year),
        "admissionYearStatus": status,
        "sourceRows": group["sourceRows"],
        "sourceProviders": "|".join(provider_counts),
        "sourceProviderCounts": provider_counts,
        "evidenceRoles": counter_to_rows(group["evidenceRoles"], 20),
        "evidenceTypes": counter_to_rows(group["evidenceTypes"], 20),
        "sourceDocumentKinds": counter_to_rows(group["sourceDocumentKinds"], 20),
        "reviewPriorityScore": draft_priority(group, school_record, subjects, metrics, formulas, semester_year, noise, percentages, weights),
        "reviewStrength": review_strength(school_record, subjects, metrics, formulas, semester_year, noise, percentages, weights),
        "draftFlags": "|".join(flags),
        "schoolRecordSignals": "|".join(school_record),
        "subjectSignals": "|".join(subjects),
        "scoreMetricSignals": "|".join(metrics),
        "formulaSignals": "|".join(formulas),
        "semesterYearSignals": "|".join(semester_year),
        "noiseSignals": "|".join(noise),
        "percentageValues": "|".join(percentages),
        "weightValues": "|".join(weights),
        "gradeScaleCandidates": "|".join(grade_scale),
        "achievementGradeCandidates": "|".join(achievement),
        "subjectScopeCandidates": "|".join(subject_scope),
        "schoolRecordPolicyJsonDraft": policy_json_draft,
        "sampleEvidence": group["sampleEvidence"],
        "sourceEvidenceIds": "|".join(group["sourceEvidenceIds"]),
        "sourceUrls": "|".join(group["sourceUrls"]),
        "attachmentUrls": "|".join(group["attachmentUrls"]),
        "rawPaths": "|".join(group["rawPaths"]),
        "sourcePaths": "|".join(group["sourcePaths"]),
        "reviewStatus": "needs_human_verification",
    }


def draft_flags(
    group: dict[str, Any],
    school_record: list[str],
    subjects: list[str],
    metrics: list[str],
    formulas: list[str],
    semester_year: list[str],
    noise: list[str],
    percentages: list[str],
    weights: list[str],
) -> list[str]:
    flags = []
    if school_record:
        flags.append("has_school_record_signal")
    if subjects:
        flags.append("has_subject_signal")
    if metrics:
        flags.append("has_score_metric_signal")
    if "grade" in metrics:
        flags.append("has_grade_metric_signal")
    if "converted_score" in metrics:
        flags.append("has_converted_score_signal")
    if formulas:
        flags.append("has_formula_signal")
    if percentages:
        flags.append("has_percentage_values")
    if weights:
        flags.append("has_weight_candidates")
    if semester_year:
        flags.append("has_semester_year_signal")
    if "achievement_evaluation" in school_record:
        flags.append("has_achievement_evaluation_signal")
    if "subject_scope" in school_record:
        flags.append("has_subject_scope_signal")
    if group["sourceRows"] >= 2:
        flags.append("has_multiple_evidence")
    if group["yearInferenceSignals"].get("collection_year_fallback"):
        flags.append("uses_collection_year_fallback")
    if noise:
        flags.append("has_noise_signals")
    if "has_noise_terms" in noise:
        flags.append("contains_non_school_record_noise")
    if not school_record or not metrics and not percentages and not weights:
        flags.append("low_structured_school_record_signal")
    return flags


def draft_priority(
    group: dict[str, Any],
    school_record: list[str],
    subjects: list[str],
    metrics: list[str],
    formulas: list[str],
    semester_year: list[str],
    noise: list[str],
    percentages: list[str],
    weights: list[str],
) -> int:
    signal_bonus = min(len(school_record) * 10, 70)
    subject_bonus = min(len(subjects) * 8, 48)
    metric_bonus = min(len(metrics) * 10, 40)
    formula_bonus = min(len(formulas) * 6, 36)
    semester_bonus = min(len(semester_year) * 5, 30)
    value_bonus = min((len(percentages) + len(weights)) * 2, 60)
    evidence_bonus = min(int(group["sourceRows"]), 30)
    noise_penalty = min(len(noise) * 10, 40)
    return max(
        0,
        int(group["maxSourcePriority"])
        + signal_bonus
        + subject_bonus
        + metric_bonus
        + formula_bonus
        + semester_bonus
        + value_bonus
        + evidence_bonus
        - noise_penalty,
    )


def review_strength(
    school_record: list[str],
    subjects: list[str],
    metrics: list[str],
    formulas: list[str],
    semester_year: list[str],
    noise: list[str],
    percentages: list[str],
    weights: list[str],
) -> str:
    has_structure = bool(metrics or formulas or percentages or weights)
    has_detail = bool(subjects or semester_year or "subject_scope" in school_record)
    if school_record and has_structure and has_detail and "has_noise_terms" not in noise:
        return "high"
    if school_record and has_structure:
        return "medium"
    return "low"


def summarize(
    input_path: Path,
    repo_root: Path,
    source_rows: list[dict[str, str]],
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_school_record_rule_drafts_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "input": {"path": to_repo_relative(input_path, repo_root), "sha256": sha256_file(input_path)},
        "sourceRows": {
            "schoolRecordRuleCandidates": len(source_rows),
        },
        "draftRows": {
            "total": len(drafts),
            "detectedAdmissionYear": sum(1 for row in drafts if row["admissionYearStatus"] == "detected"),
            "unknownAdmissionYear": sum(1 for row in drafts if row["admissionYearStatus"] == "unknown"),
            "recentAdmissionYears2021To2027": sum(
                1
                for row in drafts
                if isinstance(row.get("admissionYear"), int)
                and RECENT_YEAR_MIN <= int(row["admissionYear"]) <= RECENT_YEAR_MAX
            ),
        },
        "byAdmissionYear": counter_rows(Counter(str(row.get("admissionYear") or "unknown") for row in drafts)),
        "byReviewStrength": counter_rows(Counter(str(row.get("reviewStrength") or "") for row in drafts)),
        "bySourceProviders": counter_rows(Counter(str(row.get("sourceProviders") or "") for row in drafts)),
        "byDraftFlag": counter_rows(
            Counter(flag for row in drafts for flag in split_joined(row.get("draftFlags"))),
            limit=30,
        ),
        "bySchoolRecordSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("schoolRecordSignals"))),
            limit=30,
        ),
        "bySubjectSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("subjectSignals"))),
            limit=30,
        ),
        "byScoreMetricSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("scoreMetricSignals"))),
            limit=30,
        ),
        "byFormulaSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("formulaSignals"))),
            limit=30,
        ),
        "bySemesterYearSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("semesterYearSignals"))),
            limit=30,
        ),
        "byNoiseSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("noiseSignals"))),
            limit=30,
        ),
        "notes": [
            "Drafts group school_record_reflection candidates by university and detected admission year.",
            "When admissionYears is empty, a single recent collectionYears value is used as a review-only admission year fallback and flagged.",
            "schoolRecordPolicyJsonDraft preserves raw review signals for 학생부 반영, not executable verified formulas.",
            "Grade point tables, achievement evaluation mappings, subject scope, and year/semester signals require source review before promotion.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "schoolRecordRuleDraftId",
        "artifactType",
        "unvCd",
        "universityName",
        "admissionYear",
        "admissionYearStatus",
        "sourceRows",
        "sourceProviders",
        "sourceProviderCounts",
        "evidenceRoles",
        "evidenceTypes",
        "sourceDocumentKinds",
        "reviewPriorityScore",
        "reviewStrength",
        "draftFlags",
        "schoolRecordSignals",
        "subjectSignals",
        "scoreMetricSignals",
        "formulaSignals",
        "semesterYearSignals",
        "noiseSignals",
        "percentageValues",
        "weightValues",
        "gradeScaleCandidates",
        "achievementGradeCandidates",
        "subjectScopeCandidates",
        "schoolRecordPolicyJsonDraft",
        "sampleEvidence",
        "sourceEvidenceIds",
        "sourceUrls",
        "attachmentUrls",
        "rawPaths",
        "sourcePaths",
        "reviewStatus",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def bump_counter(counter: Counter[str], value: Any) -> None:
    text = normalize_text(value)
    if text:
        counter[text] += 1


def add_limited(values: list[str], value: Any, limit: int) -> None:
    text = normalize_text(value)
    if text and text not in values and len(values) < limit:
        values.append(text)


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def top_counter_values(counter: Counter[str], limit: int) -> list[str]:
    return [value for value, _ in counter.most_common(limit)]


def counter_to_rows(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


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


def year_sort_bucket(value: Any) -> int:
    year = int_or_none(value)
    if year is None:
        return 3
    if RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX:
        return 0
    if year > RECENT_YEAR_MAX:
        return 1
    return 2


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
