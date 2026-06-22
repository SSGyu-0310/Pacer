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

OUTPUT_JSONL = "foundation_eligibility_rule_drafts.jsonl"
OUTPUT_CSV = "foundation_eligibility_rule_drafts.csv"
OUTPUT_SUMMARY = "foundation_eligibility_rule_drafts_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027

PERCENT_PATTERN = re.compile(r"(?<!\d)(?:100|[1-9]?\d)(?:\.\d+)?\s*%")
ADMISSION_TYPE_PATTERN = re.compile(
    r"[가-힣A-Za-z0-9·ㆍ&()./\\ _-]{2,56}(?:전형|대상자|지원자|출신자)"
)
REGION_PATTERN = re.compile(
    r"서울|경기|인천|강원|충북|충청북도|충남|충청남도|대전|세종|전북|전라북도|"
    r"전남|전라남도|광주|경북|경상북도|경남|경상남도|대구|울산|부산|제주"
)
NOISE_TERMS = re.compile(r"개인정보|고유식별정보|보유기간|동의|수집 및 이용|환불|원서접수")


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    input_path = resolve(repo_root, args.rule_candidates)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(input_path)
    eligibility_rows = [row for row in rows if is_eligibility_candidate(row)]
    drafts = build_drafts(eligibility_rows)

    write_jsonl(output_dir / OUTPUT_JSONL, drafts)
    write_csv(output_dir / OUTPUT_CSV, drafts)
    summary = summarize(input_path, repo_root, eligibility_rows, drafts)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation eligibility rule drafts complete. "
        f"sourceRows={len(eligibility_rows)} drafts={len(drafts)} "
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
        "eligibilitySignals": Counter(),
        "applicantTypeSignals": Counter(),
        "legalBasisSignals": Counter(),
        "regionSignals": Counter(),
        "recordContextSignals": Counter(),
        "scoreMetricSignals": Counter(),
        "subjectSignals": Counter(),
        "formulaSignals": Counter(),
        "noiseSignals": Counter(),
        "yearInferenceSignals": Counter(),
        "percentageValues": Counter(),
        "weightValues": Counter(),
        "admissionTypeCandidates": Counter(),
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
    for signal in eligibility_signals(row, text):
        group["eligibilitySignals"][signal] += 1
    for signal in applicant_type_signals(text):
        group["applicantTypeSignals"][signal] += 1
    for signal in legal_basis_signals(text):
        group["legalBasisSignals"][signal] += 1
    for signal in region_signals(text):
        group["regionSignals"][signal] += 1
    for signal in record_context_signals(row, text):
        group["recordContextSignals"][signal] += 1
    for signal in split_joined(row.get("scoreMetricSignals")):
        group["scoreMetricSignals"][signal] += 1
    for signal in split_joined(row.get("subjectSignals")):
        group["subjectSignals"][signal] += 1
    for signal in split_joined(row.get("formulaSignals")):
        group["formulaSignals"][signal] += 1
    for signal in noise_signals(row, text):
        group["noiseSignals"][signal] += 1
    for value in extract_percentages(row, text):
        group["percentageValues"][value] += 1
    for value in split_joined(row.get("weightValues")):
        group["weightValues"][value] += 1
    for value in admission_type_candidates(text):
        group["admissionTypeCandidates"][value] += 1

    priority = int_or_none(row.get("reviewPriorityScore")) or 0
    group["maxSourcePriority"] = max(group["maxSourcePriority"], priority)
    add_limited(group["sourceEvidenceIds"], row.get("sourceEvidenceId"), 120)
    add_limited(group["sourceUrls"], row.get("sourceUrl"), 30)
    add_limited(group["attachmentUrls"], row.get("attachmentUrl"), 30)
    add_limited(group["rawPaths"], row.get("rawPath"), 30)
    add_limited(group["sourcePaths"], row.get("sourcePath"), 30)
    add_sample(group, row, priority)


def is_eligibility_candidate(row: dict[str, str]) -> bool:
    if row.get("ruleCategory") == "eligibility":
        return True
    text = normalize_text(row.get("textPreview"))
    return bool(eligibility_signals(row, text))


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


def eligibility_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    detected = set(split_joined(row.get("detectedSignals")))
    role = normalize_text(row.get("evidenceRole"))
    if role in {"student_rule", "common", "recruitment_rule_image"}:
        signals.append("eligibility_evidence_role")
    if "eligibility" in detected or re.search(r"지원\s*자격|전형별\s*주요사항|지원\s*대상", text):
        signals.append("eligibility")
    if re.search(r"고등학교\s*졸업|졸업\s*\(?예정\)?|졸업자와\s*동등", text):
        signals.append("high_school_graduation")
    if re.search(r"동등(?:의)?\s*학력|검정고시|학력\s*인정", text):
        signals.append("equivalent_education")
    if re.search(r"지역인재|지역균형|지역\s*소재|전\s*교육과정|입학부터\s*졸업", text):
        signals.append("regional_talent_or_local_school")
    if re.search(r"농어촌", text):
        signals.append("rural_student")
    if re.search(r"기초생활|수급권자|차상위|한부모", text):
        signals.append("low_income_or_welfare")
    if re.search(r"특성화고|마이스터고|전문계|직업", text):
        signals.append("vocational_high_school")
    if re.search(r"특수교육|장애|장애인", text):
        signals.append("special_education_or_disability")
    if re.search(r"국가보훈|보훈대상|독립유공|국가유공", text):
        signals.append("veterans_or_merit")
    if re.search(r"북한이탈|새터민", text):
        signals.append("north_korean_defector")
    if re.search(r"외국|재외국민|해외", text):
        signals.append("overseas_or_foreign")
    if "minimum_grade" in detected or re.search(r"최저\s*학력|수능\s*최저|등급\s*합", text):
        signals.append("csat_minimum_or_grade_sum")
    return signals


def applicant_type_signals(text: str) -> list[str]:
    signals = []
    if re.search(r"고등학교\s*졸업\s*\(?예정\)?|졸업\s*\(?예정\)?\s*자", text):
        signals.append("expected_graduate")
    if re.search(r"고등학교\s*졸업|졸업자와\s*동등|졸업한\s*자|졸업\s*\(?예정\)?\s*자", text):
        signals.append("graduate")
    if re.search(r"검정고시", text):
        signals.append("qualification_exam")
    if re.search(r"기회균형", text):
        signals.append("opportunity_balance")
    if re.search(r"지역인재", text):
        signals.append("regional_talent")
    if re.search(r"지역균형", text):
        signals.append("regional_balance")
    if re.search(r"농어촌", text):
        signals.append("rural")
    if re.search(r"기초생활|수급권자|차상위|한부모", text):
        signals.append("low_income")
    if re.search(r"재직자|특성화고.*재직", text):
        signals.append("employed_or_working_student")
    return signals


def legal_basis_signals(text: str) -> list[str]:
    signals = []
    if re.search(r"초\s*·?\s*중등교육법|초중등교육법", text):
        signals.append("elementary_secondary_education_act")
    if re.search(r"국민기초생활\s*보장법|국민기초생활보장법", text):
        signals.append("national_basic_living_security_act")
    if re.search(r"한부모가족지원법", text):
        signals.append("single_parent_family_support_act")
    if re.search(r"국가보훈|국가유공자|독립유공자", text):
        signals.append("patriots_veterans_law_context")
    if re.search(r"장애인복지법|특수교육", text):
        signals.append("disability_or_special_education_law_context")
    return signals


def region_signals(text: str) -> list[str]:
    return unique_preserve_order(REGION_PATTERN.findall(text))[:30]


def record_context_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    detected = set(split_joined(row.get("detectedSignals")))
    if "school_record" in detected or re.search(r"학생부|학교생활기록부|교과\s*성적", text):
        signals.append("school_record_context")
    if "reflection_ratio" in detected or re.search(r"반영\s*비율|반영\s*지표", text):
        signals.append("reflection_ratio_context")
    if re.search(r"1\s*학년|2\s*학년|3\s*학년|1\s*학기|2\s*학기", text):
        signals.append("year_semester_context")
    if re.search(r"졸업생의\s*경우|졸업자는|졸업자\s*:", text):
        signals.append("graduate_record_semester_context")
    if re.search(r"석차\s*등급|등급\s*점수|과목별\s*석차", text):
        signals.append("grade_table_context")
    if re.search(r"출결|봉사", text):
        signals.append("attendance_or_volunteer_context")
    return signals


def noise_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    detected = set(split_joined(row.get("detectedSignals")))
    if NOISE_TERMS.search(text):
        signals.append("has_noise_terms")
    if "school_record" in detected and not re.search(r"지원\s*자격|전형별\s*주요사항|지원\s*대상|고등학교\s*졸업", text):
        signals.append("school_record_context_without_explicit_eligibility_term")
    if "grade" in split_joined(row.get("scoreMetricSignals")) and not re.search(r"지원\s*자격|전형별\s*주요사항|지원\s*대상", text):
        signals.append("grade_table_without_explicit_eligibility_term")
    if "csat" in detected and not re.search(r"최저\s*학력|수능\s*최저|등급\s*합", text):
        signals.append("csat_context_without_minimum_term")
    if not eligibility_signals(row, text):
        signals.append("low_structured_eligibility_signal")
    return signals


def extract_percentages(row: dict[str, str], text: str) -> list[str]:
    values = split_joined(row.get("percentageValues"))
    for match in PERCENT_PATTERN.finditer(text):
        values.append(re.sub(r"\s+", "", match.group(0)))
    return unique_preserve_order(values)[:60]


def admission_type_candidates(text: str) -> list[str]:
    values = []
    for match in ADMISSION_TYPE_PATTERN.finditer(text):
        value = clean_candidate_label(match.group(0))
        if is_useful_label(value):
            values.append(value)
    return unique_preserve_order(values)[:80]


def clean_candidate_label(value: str) -> str:
    value = re.sub(r"\s+", " ", value)
    return value.strip(" /,.:;·ㆍ-_")[:120]


def is_useful_label(value: str) -> bool:
    if len(value) < 3:
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
        "eligibilitySignals": eligibility_signals(row, preview),
        "applicantTypeSignals": applicant_type_signals(preview),
        "legalBasisSignals": legal_basis_signals(preview),
        "regionSignals": region_signals(preview),
        "recordContextSignals": record_context_signals(row, preview),
        "scoreMetricSignals": split_joined(row.get("scoreMetricSignals")),
        "subjectSignals": split_joined(row.get("subjectSignals")),
        "formulaSignals": split_joined(row.get("formulaSignals")),
        "noiseSignals": noise_signals(row, preview),
        "percentageValues": extract_percentages(row, preview)[:30],
        "admissionTypeCandidates": admission_type_candidates(preview)[:20],
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "attachmentUrl": normalize_text(row.get("attachmentUrl")),
        "preview": preview[:800],
    }
    samples = group["sampleEvidence"]
    if sample["sourceEvidenceId"] in {item.get("sourceEvidenceId") for item in samples}:
        return
    samples.append(sample)
    samples.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            -len(item.get("eligibilitySignals") or []),
            -len(item.get("applicantTypeSignals") or []),
            len(item.get("noiseSignals") or []),
        )
    )
    del samples[8:]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    year = normalize_text(group["admissionYear"])
    status = "unknown" if year == "unknown" else "detected"
    provider_counts = dict(sorted(group["sourceProviders"].items()))
    eligibility = sorted(group["eligibilitySignals"])
    applicant_types = sorted(group["applicantTypeSignals"])
    legal_bases = sorted(group["legalBasisSignals"])
    regions = top_counter_values(group["regionSignals"], 30)
    record_context = sorted(group["recordContextSignals"])
    metrics = sorted(group["scoreMetricSignals"])
    subjects = sorted(group["subjectSignals"])
    formulas = sorted(group["formulaSignals"])
    noise = sorted(group["noiseSignals"])
    percentages = top_counter_values(group["percentageValues"], 60)
    weights = top_counter_values(group["weightValues"], 80)
    admission_types = top_counter_values(group["admissionTypeCandidates"], 80)
    flags = draft_flags(
        group,
        eligibility,
        applicant_types,
        legal_bases,
        regions,
        record_context,
        metrics,
        formulas,
        noise,
    )
    policy_json_draft = {
        "status": "review_candidate",
        "eligibilitySignals": eligibility,
        "applicantTypeSignals": applicant_types,
        "legalBasisSignals": legal_bases,
        "regionSignals": regions,
        "recordContextSignals": record_context,
        "scoreMetricSignals": metrics,
        "subjectSignals": subjects,
        "formulaSignals": formulas,
        "noiseSignals": noise,
        "percentageValues": percentages[:40],
        "weightValues": weights[:50],
        "admissionTypeCandidates": admission_types[:40],
        "sourceEvidenceIds": group["sourceEvidenceIds"][:30],
        "needsHumanVerification": True,
    }
    return {
        "eligibilityRuleDraftId": deterministic_uuid(
            f"eligibility-rule-draft:{group['unvCd']}:{group['universityName']}:{year}"
        ),
        "artifactType": "foundation_eligibility_rule_draft",
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
        "reviewPriorityScore": draft_priority(
            group,
            eligibility,
            applicant_types,
            legal_bases,
            regions,
            record_context,
            metrics,
            formulas,
            noise,
            percentages,
            weights,
        ),
        "reviewStrength": review_strength(eligibility, applicant_types, legal_bases, regions, record_context, noise),
        "draftFlags": "|".join(flags),
        "eligibilitySignals": "|".join(eligibility),
        "applicantTypeSignals": "|".join(applicant_types),
        "legalBasisSignals": "|".join(legal_bases),
        "regionSignals": "|".join(regions),
        "recordContextSignals": "|".join(record_context),
        "scoreMetricSignals": "|".join(metrics),
        "subjectSignals": "|".join(subjects),
        "formulaSignals": "|".join(formulas),
        "noiseSignals": "|".join(noise),
        "percentageValues": "|".join(percentages),
        "weightValues": "|".join(weights),
        "admissionTypeCandidates": "|".join(admission_types),
        "eligibilityPolicyJsonDraft": policy_json_draft,
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
    eligibility: list[str],
    applicant_types: list[str],
    legal_bases: list[str],
    regions: list[str],
    record_context: list[str],
    metrics: list[str],
    formulas: list[str],
    noise: list[str],
) -> list[str]:
    flags = []
    if eligibility:
        flags.append("has_eligibility_signal")
    if applicant_types:
        flags.append("has_applicant_type_signal")
    if legal_bases:
        flags.append("has_legal_basis_signal")
    if regions:
        flags.append("has_region_signal")
    if "csat_minimum_or_grade_sum" in eligibility:
        flags.append("has_csat_minimum_signal")
    if record_context:
        flags.append("has_school_record_context")
    if "school_record_context_without_explicit_eligibility_term" in noise:
        flags.append("has_record_context_noise")
    if metrics:
        flags.append("has_score_metric_signal")
    if formulas:
        flags.append("has_formula_signal")
    if group["sourceRows"] >= 2:
        flags.append("has_multiple_evidence")
    if group["yearInferenceSignals"].get("collection_year_fallback"):
        flags.append("uses_collection_year_fallback")
    if noise:
        flags.append("has_noise_signals")
    if "has_noise_terms" in noise:
        flags.append("contains_non_eligibility_noise")
    if (
        not eligibility
        or ("eligibility" not in eligibility and not applicant_types)
        or (record_context and not applicant_types and not legal_bases and not regions)
    ):
        flags.append("low_structured_eligibility_signal")
    return flags


def draft_priority(
    group: dict[str, Any],
    eligibility: list[str],
    applicant_types: list[str],
    legal_bases: list[str],
    regions: list[str],
    record_context: list[str],
    metrics: list[str],
    formulas: list[str],
    noise: list[str],
    percentages: list[str],
    weights: list[str],
) -> int:
    eligibility_bonus = min(len(eligibility) * 10, 80)
    applicant_bonus = min(len(applicant_types) * 10, 50)
    legal_bonus = min(len(legal_bases) * 12, 48)
    region_bonus = min(len(regions) * 4, 28)
    context_bonus = min(len(record_context) * 4, 28)
    metric_bonus = min(len(metrics) * 4, 20)
    formula_bonus = min(len(formulas) * 3, 18)
    value_bonus = min((len(percentages) + len(weights)) * 2, 50)
    evidence_bonus = min(int(group["sourceRows"]), 30)
    noise_penalty = min(len(noise) * 12, 48)
    return max(
        0,
        int(group["maxSourcePriority"])
        + eligibility_bonus
        + applicant_bonus
        + legal_bonus
        + region_bonus
        + context_bonus
        + metric_bonus
        + formula_bonus
        + value_bonus
        + evidence_bonus
        - noise_penalty,
    )


def review_strength(
    eligibility: list[str],
    applicant_types: list[str],
    legal_bases: list[str],
    regions: list[str],
    record_context: list[str],
    noise: list[str],
) -> str:
    has_specific = bool(applicant_types or legal_bases or regions)
    has_record_noise = "school_record_context_without_explicit_eligibility_term" in noise
    has_strong_eligibility = bool(legal_bases or regions or "high_school_graduation" in eligibility)
    has_only_record_context = bool(record_context) and not has_specific
    if eligibility and has_specific and has_strong_eligibility and "has_noise_terms" not in noise and not has_record_noise:
        return "high"
    if eligibility and (has_specific or not has_only_record_context):
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
        "artifactType": "foundation_eligibility_rule_drafts_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "input": {"path": to_repo_relative(input_path, repo_root), "sha256": sha256_file(input_path)},
        "sourceRows": {
            "eligibilityRuleCandidates": len(source_rows),
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
        "byEligibilitySignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("eligibilitySignals"))),
            limit=40,
        ),
        "byApplicantTypeSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("applicantTypeSignals"))),
            limit=40,
        ),
        "byLegalBasisSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("legalBasisSignals"))),
            limit=30,
        ),
        "byRegionSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("regionSignals"))),
            limit=30,
        ),
        "byRecordContextSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("recordContextSignals"))),
            limit=30,
        ),
        "byNoiseSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("noiseSignals"))),
            limit=30,
        ),
        "notes": [
            "Drafts group eligibility candidates by university and detected admission year.",
            "When admissionYears is empty, a single recent collectionYears value is used as a review-only admission year fallback and flagged.",
            "eligibilityPolicyJsonDraft preserves raw review signals for 지원자격, not verified eligibility logic.",
            "School-record semester exceptions and grade tables remain flagged as record context before promotion.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "eligibilityRuleDraftId",
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
        "eligibilitySignals",
        "applicantTypeSignals",
        "legalBasisSignals",
        "regionSignals",
        "recordContextSignals",
        "scoreMetricSignals",
        "subjectSignals",
        "formulaSignals",
        "noiseSignals",
        "percentageValues",
        "weightValues",
        "admissionTypeCandidates",
        "eligibilityPolicyJsonDraft",
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
