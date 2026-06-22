#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT_GLOB = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_evidence_index_*.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"

OUTPUT_JSONL = "university_admission_promotion_review_candidates.jsonl"
OUTPUT_CSV = "university_admission_promotion_review_candidates.csv"
OUTPUT_SUMMARY = "university_admission_promotion_review_summary.json"

YEAR_PATTERN = re.compile(r"(?<!\d)(20[0-3]\d)(?!\d)")
VALID_ADMISSION_YEAR_MIN = 2010
VALID_ADMISSION_YEAR_MAX = 2035

TARGET_PRIORITY = {
    "HistoricalOutcome": 40,
    "AdmissionRule": 36,
    "AdmissionSchedule": 28,
    "OCRReviewQueue": 12,
    "ReviewQueue": 4,
}

TYPE_PRIORITY = {
    "workbook_row": 30,
    "html_table": 26,
    "html_text_snippet": 22,
    "pdf_snippet": 20,
    "hwp_snippet": 18,
    "image_ocr": 16,
    "pdf_page_ocr": 14,
    "workbook_sheet": 12,
    "pdf_page_image": 6,
}

SOURCE_LINK_PRIORITY = {
    "admission_result": 20,
    "competition_rate": 18,
    "recruitment_notice": 14,
    "regular_admission_guide": 12,
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_paths = sorted(resolve_glob(repo_root, args.input_glob))
    groups: dict[str, dict[str, Any]] = {}
    source_rows = 0
    skipped_rows: Counter[str] = Counter()
    source_rows_by_collection_year: Counter[str] = Counter()
    input_manifests = []

    for input_path in input_paths:
        manifest_rows = 0
        for row in read_jsonl(input_path):
            manifest_rows += 1
            if not target_allowed(row.get("evidenceTarget"), args.target):
                skipped_rows["target_filter"] += 1
                continue
            if evidence_role_excluded(row.get("evidenceRole"), args.exclude_evidence_role):
                skipped_rows["exclude_evidence_role"] += 1
                continue
            if text_excluded(row, args.exclude_text_pattern):
                skipped_rows["exclude_text_pattern"] += 1
                continue
            add_row(groups, row)
            source_rows += 1
            source_rows_by_collection_year[str(row.get("year") or "")] += 1
        input_manifests.append(
            {
                "path": to_repo_relative(input_path, repo_root),
                "rows": manifest_rows,
                "sha256": sha256_file(input_path),
            }
        )

    candidates = [finalize_group(group) for group in groups.values()]
    candidates.sort(
        key=lambda row: (
            str(row.get("evidenceTarget") or ""),
            str(row.get("unvCd") or ""),
            -int(row.get("reviewPriorityScore") or 0),
            str(row.get("candidateSha256") or ""),
        )
    )

    write_jsonl(output_dir / OUTPUT_JSONL, candidates)
    write_csv_index(output_dir / OUTPUT_CSV, candidates)
    summary = summarize(input_manifests, source_rows, source_rows_by_collection_year, skipped_rows, candidates)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "university admission promotion review queue complete. "
        f"sourceRows={source_rows} candidates={len(candidates)} "
        f"targets={len(summary['byEvidenceTarget'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--target",
        action="append",
        help="Optional evidenceTarget filter. May be repeated.",
    )
    parser.add_argument(
        "--exclude-evidence-role",
        action="append",
        default=[],
        help="Optional evidenceRole exclusion. May be repeated.",
    )
    parser.add_argument(
        "--exclude-text-pattern",
        action="append",
        default=[],
        help="Optional regex exclusion applied to candidate source text. May be repeated.",
    )
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def target_allowed(value: Any, allowed: list[str] | None) -> bool:
    return True if not allowed else str(value or "") in set(allowed)


def evidence_role_excluded(value: Any, excluded: list[str] | None) -> bool:
    return bool(excluded) and str(value or "") in set(excluded)


def text_excluded(row: dict[str, Any], patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    text = normalize_space(
        " ".join(
            str(row.get(key) or "")
            for key in (
                "text",
                "textPreview",
                "evidenceRole",
                "detectedDocumentRole",
                "sourceCandidateUrl",
                "attachmentUrl",
            )
        )
    )
    return any(re.search(pattern, text, re.I) for pattern in patterns)


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


def resolve_glob(repo_root: Path, pattern: str) -> list[Path]:
    path = Path(pattern)
    if path.is_absolute():
        return [Path(match) for match in sorted(glob.glob(str(path)))]
    return [Path(match) for match in sorted(repo_root.glob(pattern))]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def add_row(groups: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    key = group_key(row)
    if key not in groups:
        groups[key] = new_group(key, row)

    group = groups[key]
    group["evidenceCount"] += 1
    collection_year = int_or_none(row.get("year"))
    if collection_year is not None:
        group["evidenceCountByCollectionYear"][str(collection_year)] += 1
    group["maxPriorityScore"] = max(
        int(group.get("maxPriorityScore") or 0),
        int(row.get("priorityScore") or 0),
    )
    group["collectionYears"].add(collection_year)
    group["detectedAdmissionYears"].update(detected_years(row))
    group["evidenceTypes"].add(str(row.get("evidenceType") or ""))
    group["sourceDocumentKinds"].add(str(row.get("sourceDocumentKind") or ""))
    group["sourceLinkRoles"].add(str(row.get("sourceLinkRole") or ""))
    group["attachmentRoles"].add(str(row.get("attachmentRole") or ""))
    group["detectedDocumentRoles"].add(str(row.get("detectedDocumentRole") or ""))
    group["sourceSha256Values"].add(str(row.get("sourceSha256") or ""))
    add_limited(group["sourcePaths"], row.get("sourcePath"), 20)
    add_limited(group["rawPaths"], row.get("rawPath"), 20)
    add_limited(group["sourceCandidateUrls"], row.get("sourceCandidateUrl"), 20)
    add_limited(group["attachmentUrls"], row.get("attachmentUrl"), 20)
    add_limited(group["evidenceSha256Values"], row.get("evidenceSha256"), 50)

    text = normalize_space(str(row.get("text") or row.get("textPreview") or ""))
    if len(text) > len(str(group.get("sampleText") or "")):
        group["sampleText"] = text[:2000]
        group["textPreview"] = normalize_space(str(row.get("textPreview") or text))[:500]

    sample = row.get("sourceSpecific")
    if sample and len(group["sourceSpecificSamples"]) < 5:
        group["sourceSpecificSamples"].append(sample)


def group_key(row: dict[str, Any]) -> str:
    text = normalize_space(str(row.get("text") or row.get("textPreview") or ""))
    text_hash = sha256_text(text)
    source_identity = str(row.get("sourceSha256") or row.get("rawPath") or row.get("sourcePath") or "")
    payload = {
        "target": row.get("evidenceTarget"),
        "role": row.get("evidenceRole"),
        "unvCd": row.get("unvCd"),
        "sourceIdentity": source_identity,
        "textHash": text_hash,
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def new_group(key: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidateSha256": key,
        "provider": "university-admission-office",
        "artifactType": "admission_promotion_review_candidate",
        "evidenceTarget": str(row.get("evidenceTarget") or ""),
        "reviewStatus": "needs_human_verification",
        "promotionStatus": "candidate",
        "unvCd": str(row.get("unvCd") or ""),
        "universityName": str(row.get("universityName") or ""),
        "campus": str(row.get("campus") or ""),
        "evidenceRole": str(row.get("evidenceRole") or ""),
        "evidenceCount": 0,
        "evidenceCountByCollectionYear": defaultdict(int),
        "maxPriorityScore": 0,
        "collectionYears": set(),
        "detectedAdmissionYears": set(),
        "evidenceTypes": set(),
        "sourceDocumentKinds": set(),
        "sourceLinkRoles": set(),
        "attachmentRoles": set(),
        "detectedDocumentRoles": set(),
        "sourceSha256Values": set(),
        "sourcePaths": [],
        "rawPaths": [],
        "sourceCandidateUrls": [],
        "attachmentUrls": [],
        "evidenceSha256Values": [],
        "textPreview": normalize_space(str(row.get("textPreview") or ""))[:500],
        "sampleText": normalize_space(str(row.get("text") or row.get("textPreview") or ""))[:2000],
        "sourceSpecificSamples": [],
    }


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    collection_years = sorted(v for v in group["collectionYears"] if v is not None)
    detected_admission_years = sorted(group["detectedAdmissionYears"])
    evidence_types = sorted(v for v in group["evidenceTypes"] if v)
    source_link_roles = sorted(v for v in group["sourceLinkRoles"] if v)
    source_document_kinds = sorted(v for v in group["sourceDocumentKinds"] if v)
    attachment_roles = sorted(v for v in group["attachmentRoles"] if v)
    detected_document_roles = sorted(v for v in group["detectedDocumentRoles"] if v)
    source_sha_values = sorted(v for v in group["sourceSha256Values"] if v)

    candidate = {
        "provider": group["provider"],
        "artifactType": group["artifactType"],
        "candidateSha256": group["candidateSha256"],
        "evidenceTarget": group["evidenceTarget"],
        "reviewStatus": group["reviewStatus"],
        "promotionStatus": group["promotionStatus"],
        "unvCd": group["unvCd"],
        "universityName": group["universityName"],
        "campus": group["campus"],
        "evidenceRole": group["evidenceRole"],
        "evidenceTypes": evidence_types,
        "sourceDocumentKinds": source_document_kinds,
        "sourceLinkRoles": source_link_roles,
        "attachmentRoles": attachment_roles,
        "detectedDocumentRoles": detected_document_roles,
        "collectionYears": collection_years,
        "detectedAdmissionYears": detected_admission_years,
        "evidenceCount": group["evidenceCount"],
        "evidenceCountByCollectionYear": dict(
            sorted(group["evidenceCountByCollectionYear"].items())
        ),
        "sourceDocumentCount": len(source_sha_values),
        "rawPathCount": len(group["rawPaths"]),
        "sourceSha256Values": source_sha_values[:20],
        "sourcePaths": group["sourcePaths"],
        "rawPaths": group["rawPaths"],
        "sourceCandidateUrls": group["sourceCandidateUrls"],
        "attachmentUrls": group["attachmentUrls"],
        "evidenceSha256Values": group["evidenceSha256Values"],
        "maxPriorityScore": group["maxPriorityScore"],
        "reviewPriorityScore": review_priority_score(
            target=group["evidenceTarget"],
            evidence_role=group["evidenceRole"],
            evidence_types=evidence_types,
            source_link_roles=source_link_roles,
            detected_admission_years=detected_admission_years,
            evidence_count=int(group["evidenceCount"] or 0),
            max_priority=int(group["maxPriorityScore"] or 0),
        ),
        "textPreview": group["textPreview"],
        "sampleText": group["sampleText"],
        "sourceSpecificSamples": group["sourceSpecificSamples"],
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }
    return candidate


def review_priority_score(
    *,
    target: str,
    evidence_role: str,
    evidence_types: list[str],
    source_link_roles: list[str],
    detected_admission_years: list[int],
    evidence_count: int,
    max_priority: int,
) -> int:
    score = TARGET_PRIORITY.get(target, 0)
    score += max(TYPE_PRIORITY.get(value, 0) for value in evidence_types or [""])
    score += max(SOURCE_LINK_PRIORITY.get(value, 0) for value in source_link_roles or [""])
    score += min(20, max_priority // 4)
    score += min(15, evidence_count)
    if detected_admission_years:
        score += 12
    if evidence_role in {"admission_result_row", "competition_rate_row"}:
        score += 12
    elif evidence_role in {"admission_result_image_ocr", "competition_rate_image_ocr"}:
        score += 12
    elif evidence_role in {
        "csat_reflection_rule",
        "screening_method",
        "recruitment_quota_table",
        "eligibility_rule",
        "school_record_rule",
    }:
        score += 10
    elif evidence_role in {
        "csat_rule_image_ocr",
        "screening_method_image_ocr",
        "recruitment_quota_image_ocr",
    }:
        score += 10
    elif evidence_role == "schedule_and_registration":
        score += 8
    elif evidence_role == "schedule_image_ocr":
        score += 8
    return score


def detected_years(row: dict[str, Any]) -> set[int]:
    years: set[int] = set()
    for value in row.get("documentDetectedAdmissionYears") or []:
        year = int_or_none(value)
        if year is not None and VALID_ADMISSION_YEAR_MIN <= year <= VALID_ADMISSION_YEAR_MAX:
            years.add(year)
    values = [
        row.get("text"),
        row.get("textPreview"),
        json.dumps(row.get("sourceSpecific") or {}, ensure_ascii=False),
    ]
    for value in values:
        text = str(value or "")
        for match in YEAR_PATTERN.findall(text):
            year = int(match)
            if VALID_ADMISSION_YEAR_MIN <= year <= VALID_ADMISSION_YEAR_MAX:
                years.add(year)
    return years


def add_limited(values: list[str], value: Any, limit: int) -> None:
    text = str(value or "")
    if text and text not in values and len(values) < limit:
        values.append(text)


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "candidateSha256",
        "evidenceTarget",
        "unvCd",
        "universityName",
        "campus",
        "evidenceRole",
        "evidenceTypes",
        "sourceDocumentKinds",
        "sourceLinkRoles",
        "collectionYears",
        "detectedAdmissionYears",
        "evidenceCount",
        "reviewPriorityScore",
        "maxPriorityScore",
        "textPreview",
        "sourceCandidateUrl",
        "attachmentUrl",
        "rawPath",
        "sourcePath",
        "reviewStatus",
        "promotionStatus",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "candidateSha256": row.get("candidateSha256"),
                    "evidenceTarget": row.get("evidenceTarget"),
                    "unvCd": row.get("unvCd"),
                    "universityName": row.get("universityName"),
                    "campus": row.get("campus"),
                    "evidenceRole": row.get("evidenceRole"),
                    "evidenceTypes": "|".join(row.get("evidenceTypes") or []),
                    "sourceDocumentKinds": "|".join(row.get("sourceDocumentKinds") or []),
                    "sourceLinkRoles": "|".join(row.get("sourceLinkRoles") or []),
                    "collectionYears": "|".join(str(v) for v in row.get("collectionYears") or []),
                    "detectedAdmissionYears": "|".join(
                        str(v) for v in row.get("detectedAdmissionYears") or []
                    ),
                    "evidenceCount": row.get("evidenceCount"),
                    "reviewPriorityScore": row.get("reviewPriorityScore"),
                    "maxPriorityScore": row.get("maxPriorityScore"),
                    "textPreview": row.get("textPreview"),
                    "sourceCandidateUrl": first(row.get("sourceCandidateUrls")),
                    "attachmentUrl": first(row.get("attachmentUrls")),
                    "rawPath": first(row.get("rawPaths")),
                    "sourcePath": first(row.get("sourcePaths")),
                    "reviewStatus": row.get("reviewStatus"),
                    "promotionStatus": row.get("promotionStatus"),
                }
            )


def first(values: Any) -> str:
    return str(values[0]) if isinstance(values, list) and values else ""


def summarize(
    input_manifests: list[dict[str, Any]],
    source_rows: int,
    source_rows_by_collection_year: Counter[str],
    skipped_rows: Counter[str],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    by_target = Counter(str(row.get("evidenceTarget") or "") for row in candidates)
    by_role = Counter(str(row.get("evidenceRole") or "") for row in candidates)
    by_type: Counter[str] = Counter()
    by_collection_year: Counter[str] = Counter()
    by_detected_admission_year: Counter[str] = Counter()
    rows_by_target: Counter[str] = Counter()
    universities = set()
    with_detected_year = 0

    for row in candidates:
        target = str(row.get("evidenceTarget") or "")
        rows_by_target[target] += int(row.get("evidenceCount") or 0)
        if row.get("unvCd"):
            universities.add(str(row.get("unvCd")))
        for evidence_type in row.get("evidenceTypes") or []:
            by_type[str(evidence_type)] += 1
        for year in row.get("collectionYears") or []:
            by_collection_year[str(year)] += 1
        if row.get("detectedAdmissionYears"):
            with_detected_year += 1
            for year in row.get("detectedAdmissionYears") or []:
                by_detected_admission_year[str(year)] += 1

    return {
        "provider": "university-admission-office",
        "artifactType": "admission_promotion_review_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputManifests": input_manifests,
        "sourceEvidenceRows": source_rows,
        "skippedEvidenceRows": counter_rows(skipped_rows),
        "promotionReviewCandidates": len(candidates),
        "dedupeRatio": round(len(candidates) / source_rows, 6) if source_rows else 0,
        "universitiesRepresented": len(universities),
        "candidatesWithDetectedAdmissionYear": with_detected_year,
        "candidatesWithoutDetectedAdmissionYear": len(candidates) - with_detected_year,
        "byEvidenceTarget": counter_rows(by_target),
        "sourceEvidenceRowsByTarget": counter_rows(rows_by_target),
        "byEvidenceRole": counter_rows(by_role, limit=40),
        "byEvidenceType": counter_rows(by_type),
        "byCollectionYear": counter_rows(by_collection_year),
        "sourceEvidenceRowsByCollectionYear": counter_rows(source_rows_by_collection_year),
        "byDetectedAdmissionYear": counter_rows(by_detected_admission_year, limit=40),
        "topPriorityCandidates": [
            {
                "candidateSha256": row.get("candidateSha256"),
                "evidenceTarget": row.get("evidenceTarget"),
                "unvCd": row.get("unvCd"),
                "universityName": row.get("universityName"),
                "evidenceRole": row.get("evidenceRole"),
                "reviewPriorityScore": row.get("reviewPriorityScore"),
                "collectionYears": row.get("collectionYears"),
                "detectedAdmissionYears": row.get("detectedAdmissionYears"),
                "textPreview": row.get("textPreview"),
            }
            for row in sorted(
                candidates,
                key=lambda item: (-int(item.get("reviewPriorityScore") or 0), str(item.get("candidateSha256") or "")),
            )[:25]
        ],
        "notes": [
            "Candidates are deduplicated review groups, not verified production records.",
            "collectionYears are crawl/admission-homepage cohorts; detectedAdmissionYears are text-derived hints.",
            "Promotion to AdmissionRule, AdmissionSchedule, or HistoricalOutcome requires human source comparison.",
        ],
    }


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    rows = [{"value": key, "count": value} for key, value in counter.most_common(limit)]
    return rows


if __name__ == "__main__":
    main()
