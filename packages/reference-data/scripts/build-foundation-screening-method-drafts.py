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

OUTPUT_JSONL = "foundation_screening_method_drafts.jsonl"
OUTPUT_CSV = "foundation_screening_method_drafts.csv"
OUTPUT_SUMMARY = "foundation_screening_method_drafts_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027

SCREENING_TYPE_PATTERN = re.compile(
    r"[가-힣A-Za-z0-9·ㆍ&()./\\ -]{2,46}(?:전형|모집|편입학|정시|수시|논술|실기|학생부교과|학생부종합)"
)
PERCENT_PATTERN = re.compile(r"(?<!\d)(?:100|[1-9]?\d)\s*%")
NOISE_TERMS = re.compile(r"개인정보|고유식별정보|보유기간|동의|환산점수|변환점수|등급표|수집 및 이용")


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    input_path = resolve(repo_root, args.rule_candidates)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(input_path)
    screening_rows = [row for row in rows if is_screening_method_source_row(row)]
    drafts = build_drafts(screening_rows)

    write_jsonl(output_dir / OUTPUT_JSONL, drafts)
    write_csv(output_dir / OUTPUT_CSV, drafts)
    summary = summarize(input_path, repo_root, screening_rows, drafts)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation screening method drafts complete. "
        f"sourceRows={len(screening_rows)} drafts={len(drafts)} "
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


def is_screening_method_source_row(row: dict[str, str]) -> bool:
    if normalize_text(row.get("ruleCategory")) == "screening_method":
        return True

    # ADIGA selection-detail tables often combine quota, selection method,
    # and evaluation weights in one structured table. Keep those multi-purpose
    # tables available to the screening-method draft builder without changing
    # the global rule-category classifier.
    if normalize_text(row.get("sourceProvider")) != "adiga":
        return False
    if normalize_text(row.get("evidenceType")) != "html_table":
        return False
    role = normalize_text(f"{row.get('evidenceRole')} {row.get('tableRole')}")
    if not re.search(r"student_rule|csat_rule|common", role):
        return False

    text = normalize_text(row.get("textPreview"))
    has_selection_header = bool(
        re.search(
            r"전형\s*방법|선발\s*/?\s*방법|전형요소\s*및\s*반영\s*비율|"
            r"모집\s*/?\s*인원.{0,80}선발|선발.{0,80}전형요소",
            text,
        )
    )
    has_selection_structure = bool(
        re.search(r"일괄|단계|배수|면접|실기|서류|학생부|수능|(?<!\d)(?:100|[1-9]?\d)\s*%", text)
    )
    return has_selection_header and has_selection_structure


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
        "screeningSignals": Counter(),
        "evaluationElementSignals": Counter(),
        "stageSignals": Counter(),
        "noiseSignals": Counter(),
        "percentageValues": Counter(),
        "weightValues": Counter(),
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
    for signal in screening_signals(row, text):
        group["screeningSignals"][signal] += 1
    for signal in evaluation_element_signals(row, text):
        group["evaluationElementSignals"][signal] += 1
    for signal in stage_signals(text):
        group["stageSignals"][signal] += 1
    for signal in noise_signals(row, text):
        group["noiseSignals"][signal] += 1
    for value in extract_percentages(row, text):
        group["percentageValues"][value] += 1
    for value in split_joined(row.get("weightValues")):
        group["weightValues"][value] += 1
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


def screening_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    role = normalize_text(row.get("evidenceRole"))
    detected = set(split_joined(row.get("detectedSignals")))
    if role in {"screening_method", "screening_method_ocr_page"}:
        signals.append("screening_method_evidence_role")
    if "screening_method" in detected or re.search(r"전형\s*방법|선발\s*방법|사정\s*방법", text):
        signals.append("screening_method")
    if re.search(r"일괄\s*합산|일괄", text):
        signals.append("batch_selection")
    if re.search(r"단계\s*별|1\s*단계|2\s*단계|배수", text):
        signals.append("staged_selection")
    if re.search(r"반영\s*비율|전형요소|평가요소", text):
        signals.append("evaluation_weight")
    if re.search(r"최고점|최저점|총점|배점", text):
        signals.append("score_point_scale")
    if re.search(r"서류\s*평가|서류전형", text):
        signals.append("document_evaluation")
    if re.search(r"면접\s*평가|면접방법|면접", text):
        signals.append("interview_evaluation")
    if re.search(r"실기|논술", text):
        signals.append("practical_or_essay")
    return signals


def evaluation_element_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    detected = set(split_joined(row.get("detectedSignals")))
    if "school_record" in detected or re.search(r"학생부|교과|학교생활기록부", text):
        signals.append("school_record")
    if "csat" in detected or re.search(r"수능|대학수학능력시험", text):
        signals.append("csat")
    if "interview_or_practical" in detected or re.search(r"면접", text):
        signals.append("interview")
    if re.search(r"서류", text):
        signals.append("documents")
    if re.search(r"실기", text):
        signals.append("practical")
    if re.search(r"논술", text):
        signals.append("essay")
    if re.search(r"출결|봉사", text):
        signals.append("attendance_or_volunteer")
    if re.search(r"인성|발전가능성|전공적합성|학업역량|진로역량|공동체역량", text):
        signals.append("competency_rubric")
    return signals


def stage_signals(text: str) -> list[str]:
    signals = []
    if re.search(r"일괄\s*합산|일괄", text):
        signals.append("one_step_batch")
    if re.search(r"1\s*단계", text):
        signals.append("stage_1")
    if re.search(r"2\s*단계", text):
        signals.append("stage_2")
    if re.search(r"\d+\s*배수", text):
        signals.append("multiple_cut")
    return signals


def noise_signals(row: dict[str, str], text: str) -> list[str]:
    signals = []
    if NOISE_TERMS.search(text):
        signals.append("has_noise_terms")
    if "grade" in split_joined(row.get("scoreMetricSignals")) and not re.search(r"전형\s*방법|선발\s*방법|평가\s*방법", text):
        signals.append("grade_table_without_screening_method_term")
    if "eligibility" in split_joined(row.get("detectedSignals")) and not re.search(r"전형\s*방법|선발\s*방법|평가\s*방법", text):
        signals.append("eligibility_without_screening_method_term")
    if not extract_percentages(row, text) and not re.search(r"일괄|단계|면접|서류|실기|논술", text):
        signals.append("low_structured_screening_signal")
    return signals


def extract_percentages(row: dict[str, str], text: str) -> list[str]:
    values = split_joined(row.get("percentageValues"))
    for match in PERCENT_PATTERN.finditer(text):
        values.append(re.sub(r"\s+", "", match.group(0)))
    return unique_preserve_order(values)[:60]


def extract_screening_type_candidates(text: str) -> list[str]:
    values = []
    for match in SCREENING_TYPE_PATTERN.finditer(text):
        value = clean_candidate_label(match.group(0))
        if is_useful_label(value):
            values.append(value)
    return unique_preserve_order(values)[:80]


def clean_candidate_label(value: str) -> str:
    value = re.sub(r"\s+", " ", value)
    return value.strip(" /,.:;·ㆍ-")[:90]


def is_useful_label(value: str) -> bool:
    if len(value) < 2:
        return False
    return not bool(re.search(r"개인정보|보유기간|환산점수|등급표|동의", value))


def add_sample(group: dict[str, Any], row: dict[str, str], priority: int) -> None:
    preview = normalize_text(row.get("textPreview"))
    if not preview:
        return
    sample = {
        "priority": priority,
        "sourceProvider": normalize_text(row.get("sourceProvider")),
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "sourceEvidenceId": normalize_text(row.get("sourceEvidenceId")),
        "screeningSignals": screening_signals(row, preview),
        "evaluationElementSignals": evaluation_element_signals(row, preview),
        "stageSignals": stage_signals(preview),
        "noiseSignals": noise_signals(row, preview),
        "percentageValues": extract_percentages(row, preview)[:30],
        "screeningTypeCandidates": extract_screening_type_candidates(preview)[:20],
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
            -len(item.get("screeningSignals") or []),
            len(item.get("noiseSignals") or []),
        )
    )
    del samples[8:]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    year = normalize_text(group["admissionYear"])
    status = "unknown" if year == "unknown" else "detected"
    provider_counts = dict(sorted(group["sourceProviders"].items()))
    screening = sorted(group["screeningSignals"])
    elements = sorted(group["evaluationElementSignals"])
    stages = sorted(group["stageSignals"])
    noise = sorted(group["noiseSignals"])
    percentages = top_counter_values(group["percentageValues"], 60)
    weights = top_counter_values(group["weightValues"], 60)
    screening_types = top_counter_values(group["screeningTypeCandidates"], 80)
    flags = draft_flags(group, screening, elements, stages, noise, percentages)
    method_json_draft = {
        "status": "review_candidate",
        "screeningSignals": screening,
        "evaluationElementSignals": elements,
        "stageSignals": stages,
        "noiseSignals": noise,
        "percentageValues": percentages[:40],
        "weightValues": weights[:40],
        "screeningTypeCandidates": screening_types[:50],
        "sourceEvidenceIds": group["sourceEvidenceIds"][:30],
        "needsHumanVerification": True,
    }
    return {
        "screeningMethodDraftId": deterministic_uuid(
            f"screening-method-draft:{group['unvCd']}:{group['universityName']}:{year}"
        ),
        "artifactType": "foundation_screening_method_draft",
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
        "reviewPriorityScore": draft_priority(group, screening, elements, stages, noise, percentages),
        "reviewStrength": review_strength(group, screening, elements, stages, noise, percentages),
        "draftFlags": "|".join(flags),
        "screeningSignals": "|".join(screening),
        "evaluationElementSignals": "|".join(elements),
        "stageSignals": "|".join(stages),
        "noiseSignals": "|".join(noise),
        "percentageValues": "|".join(percentages),
        "weightValues": "|".join(weights),
        "screeningTypeCandidates": "|".join(screening_types),
        "screeningMethodJsonDraft": method_json_draft,
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
    screening: list[str],
    elements: list[str],
    stages: list[str],
    noise: list[str],
    percentages: list[str],
) -> list[str]:
    flags = []
    if screening:
        flags.append("has_screening_method_signal")
    if elements:
        flags.append("has_evaluation_element_signal")
    if stages:
        flags.append("has_stage_signal")
    if percentages:
        flags.append("has_percentage_values")
    if group["sourceRows"] >= 2:
        flags.append("has_multiple_evidence")
    if noise:
        flags.append("has_noise_signals")
    if "has_noise_terms" in noise:
        flags.append("contains_non_screening_noise")
    if not screening or not elements:
        flags.append("low_structured_screening_signal")
    return flags


def draft_priority(
    group: dict[str, Any],
    screening: list[str],
    elements: list[str],
    stages: list[str],
    noise: list[str],
    percentages: list[str],
) -> int:
    signal_bonus = min(len(screening) * 10, 70)
    element_bonus = min(len(elements) * 8, 56)
    stage_bonus = min(len(stages) * 12, 48)
    percentage_bonus = min(len(percentages) * 4, 60)
    evidence_bonus = min(int(group["sourceRows"]), 30)
    noise_penalty = min(len(noise) * 10, 40)
    return max(0, int(group["maxSourcePriority"]) + signal_bonus + element_bonus + stage_bonus + percentage_bonus + evidence_bonus - noise_penalty)


def review_strength(
    group: dict[str, Any],
    screening: list[str],
    elements: list[str],
    stages: list[str],
    noise: list[str],
    percentages: list[str],
) -> str:
    if screening and elements and (stages or percentages) and "has_noise_terms" not in noise:
        return "high"
    if screening and (elements or stages or percentages):
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
        "artifactType": "foundation_screening_method_drafts_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "input": {"path": to_repo_relative(input_path, repo_root), "sha256": sha256_file(input_path)},
        "sourceRows": {
            "screeningMethodRuleCandidates": len(source_rows),
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
        "byScreeningSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("screeningSignals"))),
            limit=30,
        ),
        "byEvaluationElementSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("evaluationElementSignals"))),
            limit=30,
        ),
        "byStageSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("stageSignals"))),
            limit=30,
        ),
        "byNoiseSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("noiseSignals"))),
            limit=30,
        ),
        "notes": [
            "Drafts group screening_method candidates by university and detected admission year.",
            "screeningMethodJsonDraft is a review scaffold, not verified admissions logic.",
            "Rows with grade tables, score conversion tables, privacy text, or eligibility-only text keep noise flags before promotion.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "screeningMethodDraftId",
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
        "screeningSignals",
        "evaluationElementSignals",
        "stageSignals",
        "noiseSignals",
        "percentageValues",
        "weightValues",
        "screeningTypeCandidates",
        "screeningMethodJsonDraft",
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
