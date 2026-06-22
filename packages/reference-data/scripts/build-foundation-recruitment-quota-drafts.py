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
from urllib.parse import unquote_plus


DEFAULT_RULE_CANDIDATES = (
    "packages/reference-data/data/public/foundation/"
    "foundation_admission_rule_review_candidates.csv"
)
DEFAULT_EVIDENCE_LINKS = (
    "packages/reference-data/data/public/foundation/"
    "foundation_admission_office_evidence_links.csv"
)
DEFAULT_ADMISSION_UNITS = (
    "packages/reference-data/data/public/foundation/"
    "foundation_admission_units.csv"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/foundation"

OUTPUT_JSONL = "foundation_recruitment_quota_drafts.jsonl"
OUTPUT_CSV = "foundation_recruitment_quota_drafts.csv"
OUTPUT_SUMMARY = "foundation_recruitment_quota_drafts_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027

QUOTA_TERMS = re.compile(r"모집\s*/?\s*인원|모집인원|선발\s*/?\s*인원|정원\s*내|정원\s*외|모집\s*단위")
STRUCTURED_QUOTA_TERMS = re.compile(r"모집\s*/?\s*인원|모집인원|선발\s*/?\s*인원|정원\s*(?:내|외)")
STRUCTURED_QUOTA_VALUES = re.compile(
    r"\d+\s*명|(?<![\d.])(?:[1-9]\d{0,3})(?![\d.%])|수시\s*미충원인원|미\s*지정"
)
NOISE_TERMS = re.compile(r"개인정보|고유식별정보|동의|환산점수|등급|반영교과|교과성적|성적반영|보유기간")
UNIT_NAME_PATTERN = re.compile(r"[가-힣A-Za-z0-9·ㆍ&()./\\ -]{2,40}(?:학과|학부|전공|계열|대학|학군|모집단위)")
SCREENING_PATTERN = re.compile(
    r"[가-힣A-Za-z0-9·ㆍ()\\/ -]{2,40}(?:전형|모집|편입학|정시|수시|학생부교과|학생부종합|논술|실기)"
)
ADMISSION_YEAR_CONTEXT_PATTERN = re.compile(r"(?<!\d)(20\d{2})\s*학\s*년\s*도")

QUOTA_ROLES = {
    "recruitment_quota_table",
    "recruitment_quota_row",
    "recruitment_notice_table",
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    input_path = resolve(repo_root, args.rule_candidates)
    evidence_links_path = resolve(repo_root, args.evidence_links)
    admission_units_path = resolve(repo_root, args.admission_units)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rule_candidate_rows = read_csv(input_path)
    evidence_link_rows = read_csv(evidence_links_path)
    admission_unit_rows = read_csv(admission_units_path)
    recruitment_quota_rows = [row for row in rule_candidate_rows if row.get("ruleCategory") == "recruitment_quota"]
    adiga_structured_quota_rows = [
        row
        for row in rule_candidate_rows
        if is_adiga_structured_quota_rule(row)
    ]
    evidence_quota_rows = [
        normalize_evidence_link_row(row)
        for row in evidence_link_rows
        if is_admission_rule_quota_evidence(row)
    ]
    admission_unit_quota_rows = [
        normalize_admission_unit_quota_row(row)
        for row in admission_unit_rows
        if admission_unit_has_quota(row)
    ]
    quota_source_rows = (
        recruitment_quota_rows
        + adiga_structured_quota_rows
        + evidence_quota_rows
        + admission_unit_quota_rows
    )
    quota_like_rows = [row for row in quota_source_rows if is_quota_like(row)]
    drafts = build_drafts(quota_like_rows)

    write_jsonl(output_dir / OUTPUT_JSONL, drafts)
    write_csv(output_dir / OUTPUT_CSV, drafts)
    summary = summarize(
        input_path,
        evidence_links_path,
        admission_units_path,
        repo_root,
        recruitment_quota_rows,
        adiga_structured_quota_rows,
        evidence_quota_rows,
        admission_unit_quota_rows,
        quota_like_rows,
        drafts,
    )
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation recruitment quota drafts complete. "
        f"ruleSourceRows={len(recruitment_quota_rows)} "
        f"adigaStructuredQuotaRows={len(adiga_structured_quota_rows)} "
        f"evidenceSourceRows={len(evidence_quota_rows)} "
        f"admissionUnitQuotaRows={len(admission_unit_quota_rows)} "
        f"quotaLikeRows={len(quota_like_rows)} "
        f"drafts={len(drafts)} recentDrafts={summary['draftRows']['recentAdmissionYears2021To2027']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule-candidates", default=DEFAULT_RULE_CANDIDATES)
    parser.add_argument("--evidence-links", default=DEFAULT_EVIDENCE_LINKS)
    parser.add_argument("--admission-units", default=DEFAULT_ADMISSION_UNITS)
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


def is_quota_like(row: dict[str, str]) -> bool:
    text = normalize_text(row.get("textPreview"))
    role = normalize_text(row.get("evidenceRole"))
    if role in QUOTA_ROLES:
        if normalize_text(row.get("artifactType")) == "foundation_admission_office_evidence_link":
            return bool(QUOTA_TERMS.search(text))
        return True
    return bool(QUOTA_TERMS.search(text))


def is_admission_rule_quota_evidence(row: dict[str, str]) -> bool:
    target = normalize_text(row.get("evidenceTarget"))
    role = normalize_text(row.get("evidenceRole"))
    return target == "AdmissionRule" and role in QUOTA_ROLES


def is_adiga_structured_quota_rule(row: dict[str, str]) -> bool:
    if normalize_text(row.get("ruleCategory")) == "recruitment_quota":
        return False
    if normalize_text(row.get("sourceProvider")) != "adiga":
        return False
    if normalize_text(row.get("evidenceType")) != "html_table":
        return False
    if normalize_text(row.get("evidenceRole")) not in {"csat_rule", "student_rule", "common"}:
        return False
    text = normalize_text(row.get("textPreview"))
    return bool(STRUCTURED_QUOTA_TERMS.search(text) and STRUCTURED_QUOTA_VALUES.search(text))


def normalize_evidence_link_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "ruleCandidateId": "",
        "sourceProvider": normalize_text(row.get("sourceProvider")),
        "artifactType": "foundation_admission_office_evidence_link",
        "sourceEvidenceId": normalize_text(row.get("evidenceCandidateSha256")),
        "unvCd": normalize_text(row.get("unvCd")),
        "universityName": normalize_text(row.get("universityName")),
        "campus": normalize_text(row.get("campus")),
        "admissionYears": "",
        "detectedAdmissionYears": normalize_text(row.get("detectedAdmissionYears")),
        "collectionYears": normalize_text(row.get("collectionYears")),
        "ruleCategory": "recruitment_quota",
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "evidenceType": normalize_text(row.get("evidenceTypes")),
        "sourceDocumentKind": normalize_text(row.get("sourceDocumentKinds")),
        "reviewPriorityScore": normalize_text(row.get("reviewPriorityScore")),
        "evidenceCount": normalize_text(row.get("evidenceCount")),
        "detectedSignals": "recruitment_quota",
        "percentageValues": "",
        "weightValues": "",
        "scoreMetricSignals": "",
        "subjectSignals": "",
        "formulaSignals": "",
        "textPreview": normalize_text(row.get("textPreview")),
        "sourceUrl": normalize_text(row.get("sourceCandidateUrl")),
        "attachmentUrl": normalize_text(row.get("attachmentUrl")),
        "rawPath": normalize_text(row.get("rawPath")),
        "sourcePath": normalize_text(row.get("sourcePath")),
        "sourceUrls": normalize_text(row.get("sourceCandidateUrls")),
        "attachmentUrls": normalize_text(row.get("attachmentUrls")),
        "rawPaths": normalize_text(row.get("rawPaths")),
        "sourcePaths": normalize_text(row.get("sourcePaths")),
        "sourceLabels": normalize_text(row.get("sourceLabels")),
        "sourceRowCount": normalize_text(row.get("sourceRowCount")),
        "duplicateSourceCount": normalize_text(row.get("duplicateSourceCount")),
        "tableSha256": "",
        "sectionLabel": "",
        "tableRole": normalize_text(row.get("evidenceRole")),
        "tableIndex": "",
        "rows": "",
        "cols": "",
        "reviewStatus": normalize_text(row.get("reviewStatus")),
    }


def admission_unit_has_quota(row: dict[str, str]) -> bool:
    return bool(split_joined(row.get("quotaCandidates")))


def normalize_admission_unit_quota_row(row: dict[str, str]) -> dict[str, str]:
    unit_name = normalize_text(row.get("admissionUnitName"))
    quota_values = split_joined(row.get("quotaCandidates"))
    quota_text = " ".join(f"{value}명" for value in quota_values[:12])
    text_preview = normalize_text(f"모집단위 {unit_name} 모집인원 {quota_text}")
    return {
        "ruleCandidateId": "",
        "sourceProvider": normalize_text(row.get("sourceProviders")),
        "artifactType": "foundation_admission_unit_quota_evidence",
        "sourceEvidenceId": normalize_text(row.get("unitCandidateId")),
        "unvCd": normalize_text(row.get("unvCd")),
        "universityName": normalize_text(row.get("universityName")),
        "campus": "",
        "admissionYears": normalize_text(row.get("year")),
        "detectedAdmissionYears": normalize_text(row.get("year")),
        "collectionYears": normalize_text(row.get("year")),
        "ruleCategory": "recruitment_quota",
        "evidenceRole": "recruitment_quota_table",
        "evidenceType": "admission_unit_quota",
        "sourceDocumentKind": "admission_unit_candidate",
        "reviewPriorityScore": "80",
        "evidenceCount": normalize_text(row.get("outcomeRows")) or "1",
        "detectedSignals": "recruitment_quota",
        "percentageValues": "",
        "weightValues": "|".join(quota_values),
        "scoreMetricSignals": "",
        "subjectSignals": "",
        "formulaSignals": "",
        "textPreview": text_preview,
        "sourceUrl": "",
        "attachmentUrl": "",
        "rawPath": "",
        "sourcePath": "",
        "sourceUrls": "",
        "attachmentUrls": "",
        "rawPaths": "",
        "sourcePaths": "",
        "sourceLabels": unit_name,
        "sourceRowCount": "1",
        "duplicateSourceCount": "",
        "tableSha256": "",
        "sectionLabel": "",
        "tableRole": "recruitment_quota_table",
        "tableIndex": "",
        "rows": "",
        "cols": "",
        "reviewStatus": normalize_text(row.get("reviewStatus")),
    }


def build_drafts(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        years = candidate_admission_years(row)
        if not years:
            years = ["unknown"]
        for year in years:
            key = (
                normalize_text(row.get("unvCd")),
                normalize_text(row.get("universityName")),
                year,
            )
            if key not in groups:
                groups[key] = new_group(key)
            add_row(groups[key], row)

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


def candidate_admission_years(row: dict[str, str]) -> list[str]:
    contextual_years = extract_contextual_admission_years(row)
    if contextual_years:
        return contextual_years

    explicit_years = normalized_year_values(row.get("admissionYears"))
    if explicit_years:
        return explicit_years

    detected_years = normalized_year_values(row.get("detectedAdmissionYears"))
    if len(detected_years) == 1:
        return detected_years
    return []


def extract_contextual_admission_years(row: dict[str, str]) -> list[str]:
    values = []
    for field in (
        "textPreview",
        "attachmentUrl",
        "sourceUrl",
        "sourceUrls",
        "attachmentUrls",
        "sourceLabels",
        "sourcePath",
        "sourcePaths",
        "rawPath",
        "rawPaths",
    ):
        text = decode_text(row.get(field))
        for match in ADMISSION_YEAR_CONTEXT_PATTERN.finditer(text):
            year = int_or_none(match.group(1))
            if year is not None:
                values.append(str(year))
    return unique_preserve_order(values)


def normalized_year_values(value: Any) -> list[str]:
    values = []
    for part in split_joined(value):
        year = int_or_none(part)
        if year is not None and 1900 <= year <= 2099:
            values.append(str(year))
    return unique_preserve_order(values)


def decode_text(value: Any) -> str:
    return normalize_text(unquote_plus(str(value or "")))


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
        "quotaSignals": Counter(),
        "noiseSignals": Counter(),
        "candidateQuotaValues": Counter(),
        "admissionUnitNameCandidates": Counter(),
        "screeningTypeCandidates": Counter(),
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
    for signal in quota_signals(row, text):
        group["quotaSignals"][signal] += 1
    for signal in noise_signals(row, text):
        group["noiseSignals"][signal] += 1
    for value in extract_quota_values(row, text):
        group["candidateQuotaValues"][value] += 1
    for value in extract_unit_name_candidates(text):
        group["admissionUnitNameCandidates"][value] += 1
    for value in extract_screening_type_candidates(text):
        group["screeningTypeCandidates"][value] += 1

    priority = int_or_none(row.get("reviewPriorityScore")) or 0
    group["maxSourcePriority"] = max(group["maxSourcePriority"], priority)
    add_limited(group["sourceEvidenceIds"], row.get("sourceEvidenceId"), 120)
    add_limited(group["sourceUrls"], row.get("sourceUrl"), 30)
    add_limited(group["attachmentUrls"], row.get("attachmentUrl"), 30)
    add_limited(group["rawPaths"], row.get("rawPath"), 30)
    add_limited(group["sourcePaths"], row.get("sourcePath"), 30)
    add_sample(group, row, priority)


def quota_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    role = normalize_text(row.get("evidenceRole"))
    if role in QUOTA_ROLES:
        signals.append("quota_evidence_role")
    if re.search(r"모집\s*/?\s*인원|모집인원", text):
        signals.append("has_recruitment_quota_term")
    if re.search(r"정원\s*내", text):
        signals.append("has_in_quota_signal")
    if re.search(r"정원\s*외", text):
        signals.append("has_out_of_quota_signal")
    if re.search(r"모집\s*단위|모집단위", text):
        signals.append("has_admission_unit_signal")
    if re.search(r"계\\s|합계|총계", text):
        signals.append("has_total_signal")
    if re.search(r"수시|정시|편입학", text):
        signals.append("has_recruitment_season_signal")
    return signals


def noise_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    if NOISE_TERMS.search(text):
        signals.append("has_noise_terms")
    if "grade" in split_joined(row.get("scoreMetricSignals")):
        signals.append("has_grade_metric_signal")
    if "school_record" in split_joined(row.get("detectedSignals")) and not QUOTA_TERMS.search(text):
        signals.append("school_record_without_quota_term")
    if len(extract_quota_values(row, text)) == 0:
        signals.append("no_numeric_quota_candidates")
    return signals


def extract_quota_values(row: dict[str, str], text: str) -> list[str]:
    values = []
    for value in split_joined(row.get("weightValues")):
        number = int_or_none(value)
        if number is not None and 0 < number <= 500:
            values.append(str(number))
    if not values and QUOTA_TERMS.search(text):
        for match in re.finditer(r"(?<![\d.])(?:[1-9]\d{0,2}|0)(?![\d.%])", text):
            number = int_or_none(match.group(0))
            if number is not None and 0 < number <= 500:
                values.append(str(number))
    return unique_preserve_order(values)[:80]


def extract_unit_name_candidates(text: str) -> list[str]:
    values = []
    for match in UNIT_NAME_PATTERN.finditer(text):
        value = clean_candidate_label(match.group(0))
        if is_useful_label(value):
            values.append(value)
    return unique_preserve_order(values)[:80]


def extract_screening_type_candidates(text: str) -> list[str]:
    values = []
    for match in SCREENING_PATTERN.finditer(text):
        value = clean_candidate_label(match.group(0))
        if is_useful_label(value):
            values.append(value)
    return unique_preserve_order(values)[:60]


def clean_candidate_label(value: str) -> str:
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" /,.:;·ㆍ-")
    return value[:80]


def is_useful_label(value: str) -> bool:
    if len(value) < 2:
        return False
    if re.search(r"개인정보|보유기간|반영교과|환산점수|성적|등급|비고|총계", value):
        return False
    return True


def add_sample(group: dict[str, Any], row: dict[str, str], priority: int) -> None:
    preview = normalize_text(row.get("textPreview"))
    if not preview:
        return
    sample = {
        "priority": priority,
        "sourceProvider": normalize_text(row.get("sourceProvider")),
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "sourceEvidenceId": normalize_text(row.get("sourceEvidenceId")),
        "quotaSignals": quota_signals(row, preview),
        "noiseSignals": noise_signals(row, preview),
        "candidateQuotaValues": extract_quota_values(row, preview)[:30],
        "admissionUnitNameCandidates": extract_unit_name_candidates(preview)[:20],
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
            -len(item.get("quotaSignals") or []),
            len(item.get("noiseSignals") or []),
        )
    )
    del samples[8:]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    year = normalize_text(group["admissionYear"])
    status = "unknown" if year == "unknown" else "detected"
    provider_counts = dict(sorted(group["sourceProviders"].items()))
    quota_signals_list = sorted(group["quotaSignals"])
    noise_signals_list = sorted(group["noiseSignals"])
    quota_values = top_counter_values(group["candidateQuotaValues"], 80)
    unit_names = top_counter_values(group["admissionUnitNameCandidates"], 80)
    screening_types = top_counter_values(group["screeningTypeCandidates"], 60)
    flags = draft_flags(group, quota_signals_list, noise_signals_list, quota_values, unit_names)
    quota_json_draft = {
        "status": "review_candidate",
        "quotaSignals": quota_signals_list,
        "noiseSignals": noise_signals_list,
        "candidateQuotaValues": quota_values[:50],
        "admissionUnitNameCandidates": unit_names[:50],
        "screeningTypeCandidates": screening_types[:40],
        "sourceEvidenceIds": group["sourceEvidenceIds"][:30],
        "needsHumanVerification": True,
    }
    return {
        "quotaDraftId": deterministic_uuid(
            f"recruitment-quota-draft:{group['unvCd']}:{group['universityName']}:{year}"
        ),
        "artifactType": "foundation_recruitment_quota_draft",
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
        "reviewPriorityScore": draft_priority(group, quota_signals_list, noise_signals_list, quota_values, unit_names),
        "reviewStrength": review_strength(group, quota_signals_list, noise_signals_list, quota_values, unit_names),
        "draftFlags": "|".join(flags),
        "quotaSignals": "|".join(quota_signals_list),
        "noiseSignals": "|".join(noise_signals_list),
        "candidateQuotaValues": "|".join(quota_values),
        "admissionUnitNameCandidates": "|".join(unit_names),
        "screeningTypeCandidates": "|".join(screening_types),
        "quotaJsonDraft": quota_json_draft,
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
    quota_signals_list: list[str],
    noise_signals_list: list[str],
    quota_values: list[str],
    unit_names: list[str],
) -> list[str]:
    flags = []
    if quota_values:
        flags.append("has_quota_value_candidates")
    if unit_names:
        flags.append("has_admission_unit_name_candidates")
    if group["sourceRows"] >= 2:
        flags.append("has_multiple_evidence")
    if "has_in_quota_signal" in quota_signals_list:
        flags.append("has_in_quota_signal")
    if "has_out_of_quota_signal" in quota_signals_list:
        flags.append("has_out_of_quota_signal")
    if noise_signals_list:
        flags.append("has_noise_signals")
    if "has_noise_terms" in noise_signals_list:
        flags.append("contains_non_quota_table_noise")
    if not quota_values or not unit_names:
        flags.append("low_structured_quota_signal")
    return flags


def draft_priority(
    group: dict[str, Any],
    quota_signals_list: list[str],
    noise_signals_list: list[str],
    quota_values: list[str],
    unit_names: list[str],
) -> int:
    signal_bonus = min(len(quota_signals_list) * 10, 60)
    quota_bonus = min(len(quota_values) * 2, 60)
    unit_bonus = min(len(unit_names) * 2, 60)
    evidence_bonus = min(int(group["sourceRows"]), 30)
    noise_penalty = min(len(noise_signals_list) * 12, 48)
    return max(0, int(group["maxSourcePriority"]) + signal_bonus + quota_bonus + unit_bonus + evidence_bonus - noise_penalty)


def review_strength(
    group: dict[str, Any],
    quota_signals_list: list[str],
    noise_signals_list: list[str],
    quota_values: list[str],
    unit_names: list[str],
) -> str:
    if quota_values and unit_names and len(quota_signals_list) >= 3 and "has_noise_terms" not in noise_signals_list:
        return "high"
    if quota_values and (unit_names or len(quota_signals_list) >= 2):
        return "medium"
    return "low"


def summarize(
    input_path: Path,
    evidence_links_path: Path,
    admission_units_path: Path,
    repo_root: Path,
    rule_source_rows: list[dict[str, str]],
    adiga_structured_quota_rows: list[dict[str, str]],
    evidence_source_rows: list[dict[str, str]],
    admission_unit_quota_rows: list[dict[str, str]],
    quota_like_rows: list[dict[str, str]],
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_recruitment_quota_drafts_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "input": {
            "ruleCandidates": {"path": to_repo_relative(input_path, repo_root), "sha256": sha256_file(input_path)},
            "evidenceLinks": {
                "path": to_repo_relative(evidence_links_path, repo_root),
                "sha256": sha256_file(evidence_links_path) if evidence_links_path.exists() else "",
            },
            "admissionUnits": {
                "path": to_repo_relative(admission_units_path, repo_root),
                "sha256": sha256_file(admission_units_path) if admission_units_path.exists() else "",
            },
        },
        "sourceRows": {
            "recruitmentQuotaRuleCandidates": len(rule_source_rows),
            "adigaStructuredQuotaRuleCandidates": len(adiga_structured_quota_rows),
            "admissionOfficeEvidenceQuotaCandidates": len(evidence_source_rows),
            "admissionUnitQuotaCandidates": len(admission_unit_quota_rows),
            "combinedQuotaSourceRows": len(rule_source_rows)
            + len(adiga_structured_quota_rows)
            + len(evidence_source_rows)
            + len(admission_unit_quota_rows),
            "quotaLikeRowsUsed": len(quota_like_rows),
            "nonQuotaLikeRowsExcluded": len(rule_source_rows)
            + len(adiga_structured_quota_rows)
            + len(evidence_source_rows)
            + len(admission_unit_quota_rows)
            - len(quota_like_rows),
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
        "byQuotaSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("quotaSignals"))),
            limit=30,
        ),
        "byNoiseSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("noiseSignals"))),
            limit=30,
        ),
        "notes": [
            "Drafts group quota-like recruitment_quota candidates and explicit admission-office quota evidence by university and detected admission year.",
            "When admissionYears is empty, the builder prefers contextual 학년도 years from preview/title/URL before single detectedAdmissionYears fallback.",
            "candidateQuotaValues and admissionUnitNameCandidates are raw review candidates, not verified quota rows.",
            "Rows with privacy forms, score conversion tables, or grade tables keep noise flags and require human source review.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "quotaDraftId",
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
        "quotaSignals",
        "noiseSignals",
        "candidateQuotaValues",
        "admissionUnitNameCandidates",
        "screeningTypeCandidates",
        "quotaJsonDraft",
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
