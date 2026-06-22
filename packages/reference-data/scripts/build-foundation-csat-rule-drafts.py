#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RULE_CANDIDATES = (
    "packages/reference-data/data/public/foundation/"
    "foundation_admission_rule_review_candidates.csv"
)
DEFAULT_ADMISSION_OFFICE_EVIDENCE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_admission_office_evidence_links.csv"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/foundation"

OUTPUT_JSONL = "foundation_csat_reflection_rule_drafts.jsonl"
OUTPUT_CSV = "foundation_csat_reflection_rule_drafts.csv"
OUTPUT_SUMMARY = "foundation_csat_reflection_rule_drafts_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    input_path = resolve(repo_root, args.rule_candidates)
    admission_office_evidence_path = resolve(repo_root, args.admission_office_evidence)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(input_path)
    csat_rows = [row for row in rows if row.get("ruleCategory") == "csat_reflection"]
    csat_rows.extend(manual_admission_office_csat_rows(read_csv(admission_office_evidence_path)))
    drafts = build_drafts(csat_rows)

    write_jsonl(output_dir / OUTPUT_JSONL, drafts)
    write_csv(output_dir / OUTPUT_CSV, drafts)
    summary = summarize(input_path, repo_root, csat_rows, drafts)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation csat reflection rule drafts complete. "
        f"sourceRows={len(csat_rows)} drafts={len(drafts)} "
        f"detectedYearDrafts={summary['draftRows']['detectedAdmissionYear']} "
        f"unknownYearDrafts={summary['draftRows']['unknownAdmissionYear']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule-candidates", default=DEFAULT_RULE_CANDIDATES)
    parser.add_argument("--admission-office-evidence", default=DEFAULT_ADMISSION_OFFICE_EVIDENCE)
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


def manual_admission_office_csat_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    converted: list[dict[str, str]] = []
    for row in rows:
        if normalize_text(row.get("evidenceTarget")) != "AdmissionRule":
            continue
        if normalize_text(row.get("evidenceRole")) not in {"csat_reflection_rule", "csat_rule"}:
            continue
        if "manual_source" not in split_joined(row.get("evidenceTypes")):
            continue
        converted.append(convert_manual_admission_office_row(row))
    return converted


def convert_manual_admission_office_row(row: dict[str, str]) -> dict[str, str]:
    text = normalize_text(row.get("textPreview"))
    return {
        "ruleCategory": "csat_reflection",
        "unvCd": normalize_text(row.get("unvCd")),
        "universityName": normalize_text(row.get("universityName")),
        "admissionYears": normalize_text(row.get("detectedAdmissionYears")),
        "sourceProvider": normalize_text(row.get("sourceProvider")) or "university-admission-office",
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "evidenceType": "manual_source",
        "sourceDocumentKind": normalize_text(row.get("sourceDocumentKinds")),
        "detectedSignals": "|".join(manual_detected_signals(text)),
        "scoreMetricSignals": "|".join(manual_score_metric_signals(text)),
        "subjectSignals": "|".join(manual_subject_signals(text)),
        "formulaSignals": "|".join(manual_formula_signals(text)),
        "percentageValues": "|".join(re.findall(r"\d+(?:\.\d+)?\s*%", text)),
        "weightValues": "|".join(re.findall(r"\d+(?:\.\d+)?\s*%", text)),
        "reviewPriorityScore": normalize_text(row.get("reviewPriorityScore")) or "90",
        "sourceEvidenceId": evidence_id_for_manual_row(row),
        "sourceUrl": normalize_text(row.get("sourceCandidateUrl")),
        "attachmentUrl": normalize_text(row.get("attachmentUrl")),
        "rawPath": normalize_text(row.get("rawPath")),
        "sourcePath": normalize_text(row.get("sourcePath")),
        "textPreview": text,
    }


def manual_detected_signals(text: str) -> list[str]:
    signals: list[str] = []
    if re.search(r"수능|대학수학능력시험", text):
        signals.append("csat")
    if re.search(r"표준점수", text):
        signals.append("standard_score")
    if re.search(r"백분위", text):
        signals.append("percentile")
    if re.search(r"등급", text):
        signals.append("grade")
    return signals


def manual_score_metric_signals(text: str) -> list[str]:
    signals: list[str] = []
    if re.search(r"표준점수", text):
        signals.append("standard_score")
    if re.search(r"백분위", text):
        signals.append("percentile")
    if re.search(r"등급", text):
        signals.append("grade")
    return signals


def manual_subject_signals(text: str) -> list[str]:
    signals: list[str] = []
    for pattern, signal in [
        (r"국어", "korean"),
        (r"수학", "math"),
        (r"영어", "english"),
        (r"탐구|사회|과학|직업", "exploration"),
        (r"한국사", "korean_history"),
    ]:
        if re.search(pattern, text):
            signals.append(signal)
    return signals


def manual_formula_signals(text: str) -> list[str]:
    signals: list[str] = []
    if re.search(r"\d+(?:\.\d+)?\s*%", text):
        signals.append("ratio_weighting")
    if re.search(r"환산", text):
        signals.append("conversion")
    return signals


def evidence_id_for_manual_row(row: dict[str, str]) -> str:
    identity = "|".join(
        [
            normalize_text(row.get("unvCd")),
            normalize_text(row.get("detectedAdmissionYears")),
            normalize_text(row.get("evidenceRole")),
            normalize_text(row.get("sourceCandidateUrl")),
            normalize_text(row.get("sourcePath")),
            normalize_text(row.get("textPreview"))[:200],
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


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
        "detectedSignals": Counter(),
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
    for name in split_joined(row.get("detectedSignals")):
        group["detectedSignals"][name] += 1
    for name in split_joined(row.get("scoreMetricSignals")):
        group["scoreMetricSignals"][name] += 1
    for name in split_joined(row.get("subjectSignals")):
        group["subjectSignals"][name] += 1
    for name in split_joined(row.get("formulaSignals")):
        group["formulaSignals"][name] += 1
    for value in split_joined(row.get("percentageValues")):
        group["percentageValues"][value] += 1
    for value in split_joined(row.get("weightValues")):
        group["weightValues"][value] += 1

    priority = int_or_none(row.get("reviewPriorityScore")) or 0
    group["maxSourcePriority"] = max(group["maxSourcePriority"], priority)
    add_limited(group["sourceEvidenceIds"], row.get("sourceEvidenceId"), 80)
    add_limited(group["sourceUrls"], row.get("sourceUrl"), 20)
    add_limited(group["attachmentUrls"], row.get("attachmentUrl"), 20)
    add_limited(group["rawPaths"], row.get("rawPath"), 20)
    add_limited(group["sourcePaths"], row.get("sourcePath"), 20)
    add_sample(group, row, priority)


def add_sample(group: dict[str, Any], row: dict[str, str], priority: int) -> None:
    preview = normalize_text(row.get("textPreview"))
    if not preview:
        return
    sample = {
        "priority": priority,
        "sourceProvider": normalize_text(row.get("sourceProvider")),
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "sourceEvidenceId": normalize_text(row.get("sourceEvidenceId")),
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "attachmentUrl": normalize_text(row.get("attachmentUrl")),
        "preview": preview[:500],
    }
    samples = group["sampleEvidence"]
    if sample["sourceEvidenceId"] in {item.get("sourceEvidenceId") for item in samples}:
        return
    samples.append(sample)
    samples.sort(key=lambda item: -int(item.get("priority") or 0))
    del samples[6:]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    year = normalize_text(group["admissionYear"])
    status = "unknown" if year == "unknown" else "detected"
    provider_counts = dict(sorted(group["sourceProviders"].items()))
    signal_names = sorted(group["detectedSignals"])
    metric_names = sorted(group["scoreMetricSignals"])
    subject_names = sorted(group["subjectSignals"])
    formula_names = sorted(group["formulaSignals"])
    percentage_values = top_counter_values(group["percentageValues"], 30)
    weight_values = top_counter_values(group["weightValues"], 40)
    flags = draft_flags(signal_names, metric_names, subject_names, formula_names, percentage_values, weight_values)
    score_type_candidates = infer_score_type_candidates(metric_names)
    formula_json_draft = {
        "status": "review_candidate",
        "scoreTypeCandidates": score_type_candidates,
        "detectedSignals": signal_names,
        "scoreMetricSignals": metric_names,
        "subjectSignals": subject_names,
        "formulaSignals": formula_names,
        "percentageValues": percentage_values,
        "weightValues": weight_values,
        "sourceEvidenceIds": group["sourceEvidenceIds"][:20],
    }
    english_policy_draft = policy_draft("english", "english_conversion" in signal_names or "english" in subject_names)
    history_policy_draft = policy_draft(
        "korean_history",
        "korean_history" in signal_names or "korean_history" in subject_names,
    )
    inquiry_policy_draft = policy_draft(
        "inquiry",
        "exploration_subjects" in signal_names or "exploration" in subject_names,
    )
    return {
        "csatRuleDraftId": deterministic_uuid(
            f"csat-rule-draft:{group['unvCd']}:{group['universityName']}:{year}"
        ),
        "artifactType": "foundation_csat_reflection_rule_draft",
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
        "reviewPriorityScore": draft_priority(group, flags),
        "reviewStrength": review_strength(group, flags),
        "draftFlags": "|".join(flags),
        "scoreTypeCandidates": "|".join(score_type_candidates),
        "detectedSignals": "|".join(signal_names),
        "scoreMetricSignals": "|".join(metric_names),
        "subjectSignals": "|".join(subject_names),
        "formulaSignals": "|".join(formula_names),
        "percentageValues": "|".join(percentage_values),
        "weightValues": "|".join(weight_values),
        "formulaJsonDraft": formula_json_draft,
        "englishPolicyJsonDraft": english_policy_draft,
        "historyPolicyJsonDraft": history_policy_draft,
        "inquiryPolicyJsonDraft": inquiry_policy_draft,
        "sampleEvidence": group["sampleEvidence"],
        "sourceEvidenceIds": "|".join(group["sourceEvidenceIds"][:80]),
        "sourceUrls": "|".join(group["sourceUrls"]),
        "attachmentUrls": "|".join(group["attachmentUrls"]),
        "rawPaths": "|".join(group["rawPaths"]),
        "sourcePaths": "|".join(group["sourcePaths"]),
        "reviewStatus": "needs_human_verification",
    }


def draft_flags(
    signals: list[str],
    metrics: list[str],
    subjects: list[str],
    formulas: list[str],
    percentages: list[str],
    weights: list[str],
) -> list[str]:
    flags = []
    if percentages:
        flags.append("has_explicit_percentages")
    if weights:
        flags.append("has_weight_candidates")
    if formulas:
        flags.append("has_formula_signal")
    if metrics:
        flags.append("has_score_metric_signal")
    if subjects:
        flags.append("has_subject_signal")
    if "english_conversion" in signals or "english" in subjects:
        flags.append("has_english_policy_signal")
    if "korean_history" in signals or "korean_history" in subjects:
        flags.append("has_history_policy_signal")
    if "exploration_subjects" in signals or "exploration" in subjects:
        flags.append("has_inquiry_policy_signal")
    if "bonus" in signals:
        flags.append("has_bonus_signal")
    if "minimum_grade" in signals:
        flags.append("has_minimum_grade_signal")
    return flags


def infer_score_type_candidates(metrics: list[str]) -> list[str]:
    has_standard = "standard_score" in metrics
    has_percentile = "percentile" in metrics
    has_grade_or_conversion = any(value in metrics for value in ["grade", "converted_score", "raw_score"])
    if has_standard and has_percentile:
        return ["mixed"]
    if has_standard:
        return ["standard"]
    if has_percentile:
        return ["percentile"]
    if has_grade_or_conversion:
        return ["custom"]
    return ["custom"]


def policy_draft(policy_type: str, detected: bool) -> dict[str, Any]:
    return {"status": "review_candidate", "policyType": policy_type, "signalDetected": detected}


def draft_priority(group: dict[str, Any], flags: list[str]) -> int:
    provider_bonus = 24 if len(group["sourceProviders"]) > 1 else 10
    evidence_bonus = min(int(group["sourceRows"]), 20)
    flag_bonus = min(len(flags) * 5, 40)
    return int(group["maxSourcePriority"]) + provider_bonus + evidence_bonus + flag_bonus


def review_strength(group: dict[str, Any], flags: list[str]) -> str:
    has_multiple_sources = len(group["sourceProviders"]) > 1
    has_formula = "has_formula_signal" in flags or "has_explicit_percentages" in flags
    has_subjects = "has_subject_signal" in flags
    if has_multiple_sources and has_formula and has_subjects:
        return "high"
    if has_formula and (has_subjects or group["sourceRows"] >= 3):
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
        "artifactType": "foundation_csat_reflection_rule_drafts_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "input": {"path": to_repo_relative(input_path, repo_root), "sha256": sha256_file(input_path)},
        "sourceRows": {
            "csatReflectionRuleCandidates": len(source_rows),
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
        "byScoreTypeCandidates": counter_rows(Counter(str(row.get("scoreTypeCandidates") or "") for row in drafts)),
        "byDraftFlag": counter_rows(
            Counter(flag for row in drafts for flag in split_joined(row.get("draftFlags"))),
            limit=30,
        ),
        "notes": [
            "Drafts are grouped by university and detected admission year.",
            "Unknown admission-year drafts preserve high-value evidence but require manual year assignment before promotion.",
            "formulaJsonDraft and policy drafts are review scaffolds, not executable verified formulas.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "csatRuleDraftId",
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
        "scoreTypeCandidates",
        "detectedSignals",
        "scoreMetricSignals",
        "subjectSignals",
        "formulaSignals",
        "percentageValues",
        "weightValues",
        "formulaJsonDraft",
        "englishPolicyJsonDraft",
        "historyPolicyJsonDraft",
        "inquiryPolicyJsonDraft",
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


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def int_or_large(value: Any) -> int:
    parsed = int_or_none(value)
    return parsed if parsed is not None else 999999


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
