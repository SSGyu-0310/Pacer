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

OUTPUT_JSONL = "foundation_general_rule_drafts.jsonl"
OUTPUT_CSV = "foundation_general_rule_drafts.csv"
OUTPUT_SUMMARY = "foundation_general_rule_drafts_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027

PERCENT_PATTERN = re.compile(r"(?<!\d)(?:100|[1-9]?\d)(?:\.\d+)?\s*%")
YEAR_ONLY_PATTERN = re.compile(r"^\d{4}\s*학년도$")
NOISE_TERMS = re.compile(r"개인정보|고유식별정보|보유기간|동의|수집 및 이용|원서접수")
OCR_NOISE_PATTERN = re.compile(r"\b(?:wees|Pee|Peete|fee|foe|aes|xe|poe)\b", re.IGNORECASE)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    input_path = resolve(repo_root, args.rule_candidates)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(input_path)
    general_rows = [row for row in rows if row.get("ruleCategory") == "general_rule"]
    drafts = build_drafts(general_rows)

    write_jsonl(output_dir / OUTPUT_JSONL, drafts)
    write_csv(output_dir / OUTPUT_CSV, drafts)
    summary = summarize(input_path, repo_root, general_rows, drafts)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation general rule drafts complete. "
        f"sourceRows={len(general_rows)} drafts={len(drafts)} "
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
        years = split_joined(row.get("admissionYears"))
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
        "generalRuleSignals": Counter(),
        "conversionSignals": Counter(),
        "policyContextSignals": Counter(),
        "sourceQualitySignals": Counter(),
        "scoreMetricSignals": Counter(),
        "subjectSignals": Counter(),
        "formulaSignals": Counter(),
        "percentageValues": Counter(),
        "weightValues": Counter(),
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
    for signal in general_rule_signals(row, text):
        group["generalRuleSignals"][signal] += 1
    for signal in conversion_signals(row, text):
        group["conversionSignals"][signal] += 1
    for signal in policy_context_signals(row, text):
        group["policyContextSignals"][signal] += 1
    for signal in source_quality_signals(row, text):
        group["sourceQualitySignals"][signal] += 1
    for signal in split_joined(row.get("scoreMetricSignals")):
        group["scoreMetricSignals"][signal] += 1
    for signal in split_joined(row.get("subjectSignals")):
        group["subjectSignals"][signal] += 1
    for signal in split_joined(row.get("formulaSignals")):
        group["formulaSignals"][signal] += 1
    for value in extract_percentages(row, text):
        group["percentageValues"][value] += 1
    for value in split_joined(row.get("weightValues")):
        group["weightValues"][value] += 1

    priority = int_or_none(row.get("reviewPriorityScore")) or 0
    group["maxSourcePriority"] = max(group["maxSourcePriority"], priority)
    add_limited(group["sourceEvidenceIds"], row.get("sourceEvidenceId"), 120)
    add_limited(group["sourceUrls"], row.get("sourceUrl"), 30)
    add_limited(group["attachmentUrls"], row.get("attachmentUrl"), 30)
    add_limited(group["rawPaths"], row.get("rawPath"), 30)
    add_limited(group["sourcePaths"], row.get("sourcePath"), 30)
    add_sample(group, row, priority)


def general_rule_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    role = normalize_text(row.get("evidenceRole"))
    if role in {"common", "recruitment_rule_image", "recruitment_notice_table"}:
        signals.append("general_rule_evidence_role")
    if normalize_text(row.get("sourceProvider")) == "university-admission-office":
        signals.append("admission_office_general_rule")
    if re.search(r"공통|공개표준안|전형\s*평가기준|결과공개", text):
        signals.append("common_section_context")
    if conversion_signals(row, text):
        signals.append("conversion_or_scale_context")
    if policy_context_signals(row, text):
        signals.append("policy_context")
    return signals


def conversion_signals(row: dict[str, str], text: str) -> list[str]:
    metrics = set(split_joined(row.get("scoreMetricSignals")))
    detected = set(split_joined(row.get("detectedSignals")))
    signals = []
    if "grade" in metrics or re.search(r"석차\s*등급|등급\s*\d|등급\s*점수", text):
        signals.append("grade_scale_or_conversion")
    if "raw_score" in metrics or "raw_score" in detected or re.search(r"원점수|원\s*점수", text):
        signals.append("raw_score_conversion")
    if "converted_score" in metrics or re.search(r"환산\s*/?\s*점수|변환\s*점수|환산점수", text):
        signals.append("converted_score_context")
    if re.search(r"변환\s*등급|성취도|A\s+B\s+C|A\s+A\s+A", text):
        signals.append("achievement_or_conversion_grade")
    if "highest_score" in metrics or re.search(r"최고점|만점", text):
        signals.append("highest_score_context")
    return signals


def policy_context_signals(row: dict[str, str], text: str) -> list[str]:
    detected = set(split_joined(row.get("detectedSignals")))
    subjects = set(split_joined(row.get("subjectSignals")))
    signals = []
    if "csat" in detected or re.search(r"수능|대학수학능력시험", text):
        signals.append("csat_context")
    if "english_conversion" in detected or "english" in subjects or re.search(r"영어", text):
        signals.append("english_context")
    if "exploration_subjects" in detected or "exploration" in subjects or re.search(r"탐구|사회|과학", text):
        signals.append("inquiry_or_subject_context")
    if "recruitment_group" in detected or re.search(r"모집\s*군|가군|나군|다군", text):
        signals.append("recruitment_group_context")
    if "screening_method" in detected or re.search(r"전형\s*방법|선발\s*방법", text):
        signals.append("screening_method_context")
    if "reflection_ratio" in detected or re.search(r"반영\s*비율|반영\s*영역", text):
        signals.append("reflection_ratio_context")
    if "minimum_grade" in detected or re.search(r"최저\s*학력|수능\s*최저|등급\s*합", text):
        signals.append("minimum_grade_context")
    return signals


def source_quality_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    if not text:
        signals.append("empty_text")
    if YEAR_ONLY_PATTERN.match(text):
        signals.append("year_only_text")
    if len(text) <= 24 and not conversion_signals(row, text) and not policy_context_signals(row, text):
        signals.append("short_low_context_text")
    if re.search(r"학년도\s*전형\s*평가기준|결과공개|공개표준안", text) and len(text) <= 80:
        signals.append("title_like_text")
    if normalize_text(row.get("evidenceType")) == "image_ocr":
        signals.append("image_ocr_source")
    if OCR_NOISE_PATTERN.search(text):
        signals.append("ocr_noise_text")
    if NOISE_TERMS.search(text):
        signals.append("has_noise_terms")
    if not conversion_signals(row, text) and not policy_context_signals(row, text):
        signals.append("low_structured_general_rule_signal")
    return signals


def extract_percentages(row: dict[str, str], text: str) -> list[str]:
    values = split_joined(row.get("percentageValues"))
    for match in PERCENT_PATTERN.finditer(text):
        values.append(re.sub(r"\s+", "", match.group(0)))
    return unique_preserve_order(values)[:60]


def add_sample(group: dict[str, Any], row: dict[str, str], priority: int) -> None:
    preview = normalize_text(row.get("textPreview"))
    if not preview:
        return
    sample = {
        "priority": priority,
        "sourceProvider": normalize_text(row.get("sourceProvider")),
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "sourceEvidenceId": normalize_text(row.get("sourceEvidenceId")),
        "generalRuleSignals": general_rule_signals(row, preview),
        "conversionSignals": conversion_signals(row, preview),
        "policyContextSignals": policy_context_signals(row, preview),
        "sourceQualitySignals": source_quality_signals(row, preview),
        "scoreMetricSignals": split_joined(row.get("scoreMetricSignals")),
        "subjectSignals": split_joined(row.get("subjectSignals")),
        "formulaSignals": split_joined(row.get("formulaSignals")),
        "percentageValues": extract_percentages(row, preview)[:30],
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
            -len(item.get("conversionSignals") or []),
            -len(item.get("policyContextSignals") or []),
            len(item.get("sourceQualitySignals") or []),
        )
    )
    del samples[8:]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    year = normalize_text(group["admissionYear"])
    status = "unknown" if year == "unknown" else "detected"
    provider_counts = dict(sorted(group["sourceProviders"].items()))
    general = sorted(group["generalRuleSignals"])
    conversion = sorted(group["conversionSignals"])
    policy = sorted(group["policyContextSignals"])
    quality = sorted(group["sourceQualitySignals"])
    metrics = sorted(group["scoreMetricSignals"])
    subjects = sorted(group["subjectSignals"])
    formulas = sorted(group["formulaSignals"])
    percentages = top_counter_values(group["percentageValues"], 60)
    weights = top_counter_values(group["weightValues"], 80)
    flags = draft_flags(group, general, conversion, policy, quality, metrics, formulas, percentages, weights)
    rule_json_draft = {
        "status": "review_candidate",
        "generalRuleSignals": general,
        "conversionSignals": conversion,
        "policyContextSignals": policy,
        "sourceQualitySignals": quality,
        "scoreMetricSignals": metrics,
        "subjectSignals": subjects,
        "formulaSignals": formulas,
        "percentageValues": percentages[:40],
        "weightValues": weights[:50],
        "sourceEvidenceIds": group["sourceEvidenceIds"][:30],
        "needsHumanVerification": True,
    }
    return {
        "generalRuleDraftId": deterministic_uuid(
            f"general-rule-draft:{group['unvCd']}:{group['universityName']}:{year}"
        ),
        "artifactType": "foundation_general_rule_draft",
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
        "reviewPriorityScore": draft_priority(group, conversion, policy, quality, metrics, formulas, percentages, weights),
        "reviewStrength": review_strength(conversion, policy, quality, metrics, formulas, percentages, weights),
        "draftFlags": "|".join(flags),
        "generalRuleSignals": "|".join(general),
        "conversionSignals": "|".join(conversion),
        "policyContextSignals": "|".join(policy),
        "sourceQualitySignals": "|".join(quality),
        "scoreMetricSignals": "|".join(metrics),
        "subjectSignals": "|".join(subjects),
        "formulaSignals": "|".join(formulas),
        "percentageValues": "|".join(percentages),
        "weightValues": "|".join(weights),
        "generalRuleJsonDraft": rule_json_draft,
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
    general: list[str],
    conversion: list[str],
    policy: list[str],
    quality: list[str],
    metrics: list[str],
    formulas: list[str],
    percentages: list[str],
    weights: list[str],
) -> list[str]:
    flags = []
    if general:
        flags.append("has_general_rule_signal")
    if conversion:
        flags.append("has_conversion_signal")
    if policy:
        flags.append("has_policy_context_signal")
    if metrics:
        flags.append("has_score_metric_signal")
    if formulas:
        flags.append("has_formula_signal")
    if percentages:
        flags.append("has_percentage_values")
    if weights:
        flags.append("has_weight_candidates")
    if group["sourceRows"] >= 2:
        flags.append("has_multiple_evidence")
    if any(signal in quality for signal in ["image_ocr_source", "ocr_noise_text"]):
        flags.append("has_ocr_review_signal")
    if any(signal in quality for signal in ["year_only_text", "title_like_text", "short_low_context_text"]):
        flags.append("has_low_context_text")
    if "low_structured_general_rule_signal" in quality:
        flags.append("low_structured_general_rule_signal")
    return flags


def draft_priority(
    group: dict[str, Any],
    conversion: list[str],
    policy: list[str],
    quality: list[str],
    metrics: list[str],
    formulas: list[str],
    percentages: list[str],
    weights: list[str],
) -> int:
    conversion_bonus = min(len(conversion) * 12, 60)
    policy_bonus = min(len(policy) * 10, 50)
    metric_bonus = min(len(metrics) * 6, 30)
    formula_bonus = min(len(formulas) * 5, 25)
    value_bonus = min((len(percentages) + len(weights)) * 2, 50)
    evidence_bonus = min(int(group["sourceRows"]), 30)
    quality_penalty = min(len(quality) * 10, 60)
    return max(
        0,
        int(group["maxSourcePriority"])
        + conversion_bonus
        + policy_bonus
        + metric_bonus
        + formula_bonus
        + value_bonus
        + evidence_bonus
        - quality_penalty,
    )


def review_strength(
    conversion: list[str],
    policy: list[str],
    quality: list[str],
    metrics: list[str],
    formulas: list[str],
    percentages: list[str],
    weights: list[str],
) -> str:
    has_low_context = any(
        signal in quality
        for signal in ["year_only_text", "title_like_text", "short_low_context_text", "ocr_noise_text"]
    )
    has_structured_rule = bool(conversion or policy) and bool(metrics or formulas or percentages or weights)
    if has_structured_rule and not has_low_context:
        return "medium"
    if conversion or policy:
        return "low"
    return "limited"


def summarize(
    input_path: Path,
    repo_root: Path,
    source_rows: list[dict[str, str]],
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_general_rule_drafts_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "input": {"path": to_repo_relative(input_path, repo_root), "sha256": sha256_file(input_path)},
        "sourceRows": {
            "generalRuleCandidates": len(source_rows),
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
        "byGeneralRuleSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("generalRuleSignals"))),
            limit=30,
        ),
        "byConversionSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("conversionSignals"))),
            limit=30,
        ),
        "byPolicyContextSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("policyContextSignals"))),
            limit=30,
        ),
        "bySourceQualitySignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("sourceQualitySignals"))),
            limit=30,
        ),
        "notes": [
            "Drafts group residual general_rule candidates by university and detected admission year.",
            "generalRuleJsonDraft is a review scaffold for mixed common rules, not verified admissions logic.",
            "Year-only labels, title-like rows, and OCR-noise rows keep quality flags before promotion.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "generalRuleDraftId",
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
        "generalRuleSignals",
        "conversionSignals",
        "policyContextSignals",
        "sourceQualitySignals",
        "scoreMetricSignals",
        "subjectSignals",
        "formulaSignals",
        "percentageValues",
        "weightValues",
        "generalRuleJsonDraft",
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
