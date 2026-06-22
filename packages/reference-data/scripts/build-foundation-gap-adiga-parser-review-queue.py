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


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_ADIGA_DIR = "packages/reference-data/data/public/adiga"
DEFAULT_GAP_COLLECTION_TARGETS = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_collection_targets.csv"
)

OUTPUT_JSONL = "foundation_gap_adiga_parser_review_queue.jsonl"
OUTPUT_CSV = "foundation_gap_adiga_parser_review_queue.csv"
OUTPUT_SUMMARY = "foundation_gap_adiga_parser_review_queue_summary.json"

CSV_FIELDS = [
    "adigaParserReviewQueueId",
    "artifactType",
    "collectionTargetId",
    "priorityTier",
    "parserReviewPriorityScore",
    "parserReviewBucket",
    "parserReviewAction",
    "parserReviewStatus",
    "unvCd",
    "universityName",
    "admissionYear",
    "gapCount",
    "missingFlags",
    "targetEntities",
    "recommendedActions",
    "sourceUrl",
    "rawPath",
    "manifestStatus",
    "rawBytes",
    "hasCsatTrack",
    "finalRegistrantMentions",
    "percentileMentions",
    "convertedScoreMentions",
    "htmlTableRows",
    "csatOutcomeTables",
    "csatOutcomeNonApplicableTables",
    "csatRuleTables",
    "studentOutcomeTables",
    "studentRuleTables",
    "commonTables",
    "otherTables",
    "csatOutcomeCandidateRows",
    "csatOutcomeScoreCandidateRows",
    "csatOutcomeQuotaCompetitionRows",
    "adigaImageReferenceRows",
    "adigaImageOcrEvidenceRows",
    "topDiagnosticTableRole",
    "topDiagnosticSectionId",
    "topDiagnosticHeader",
    "topDiagnosticSnippet",
    "parserBlockerFlags",
    "operatorNextStep",
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    adiga_dir = resolve(repo_root, args.adiga_dir)
    targets_path = resolve(repo_root, args.gap_collection_targets)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    collection_targets = [
        row
        for row in read_csv(targets_path)
        if normalize_text(row.get("collectionRoute")) == "adiga_selection_detail"
    ]
    indexes = load_adiga_indexes(adiga_dir)
    review_rows = build_review_queue(collection_targets, indexes)
    review_rows.sort(
        key=lambda row: (
            priority_sort(row.get("priorityTier")),
            -int_or_none(row.get("parserReviewPriorityScore") or 0),
            bucket_sort(row.get("parserReviewBucket")),
            str(row.get("universityName") or ""),
            int_or_large(row.get("admissionYear")),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, review_rows)
    write_csv(foundation_dir / OUTPUT_CSV, review_rows)
    summary = summarize(
        repo_root=repo_root,
        inputs=[targets_path, *indexes["inputPaths"]],
        collection_targets=collection_targets,
        review_rows=review_rows,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap Adiga parser review queue complete. "
        f"collectionTargets={len(collection_targets)} rows={len(review_rows)} "
        f"parserRepair={summary['byParserReviewBucketCounts'].get('csat_outcome_table_parser_repair', 0)} "
        f"studentOnly={summary['byParserReviewBucketCounts'].get('student_outcome_only_needs_office_or_scope_review', 0)} "
        f"imageOnly={summary['byParserReviewBucketCounts'].get('image_only_detail_visual_ocr_review', 0)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--adiga-dir", default=DEFAULT_ADIGA_DIR)
    parser.add_argument("--gap-collection-targets", default=DEFAULT_GAP_COLLECTION_TARGETS)
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


def load_adiga_indexes(adiga_dir: Path) -> dict[str, Any]:
    indexes: dict[str, Any] = {
        "inputPaths": [],
        "manifestByYearUnv": {},
        "tablesByYearUnv": defaultdict(list),
        "outcomeCandidatesByYearUnv": defaultdict(int),
        "outcomeScoreCandidatesByYearUnv": defaultdict(int),
        "outcomeQuotaCompetitionCandidatesByYearUnv": defaultdict(int),
        "imageRefsByYearUnv": defaultdict(list),
        "ocrEvidenceByImageKey": defaultdict(list),
    }

    for path in sorted(adiga_dir.glob("adiga_selection_manifest_*.jsonl")):
        indexes["inputPaths"].append(path)
        for row in read_jsonl(path):
            key = (normalize_year(row.get("year")), normalize_text(row.get("unvCd")))
            indexes["manifestByYearUnv"][key] = row

    extracted_dir = adiga_dir / "extracted"
    for path in sorted(extracted_dir.glob("adiga_extracted_tables_*.jsonl")):
        indexes["inputPaths"].append(path)
        for row in read_jsonl(path):
            key = (normalize_year(row.get("year")), normalize_text(row.get("unvCd")))
            indexes["tablesByYearUnv"][key].append(row)

    for path in sorted(extracted_dir.glob("adiga_csat_outcome_candidates_*.csv")):
        indexes["inputPaths"].append(path)
        for row in read_csv(path):
            key = (normalize_year(row.get("year")), normalize_text(row.get("unvCd")))
            indexes["outcomeCandidatesByYearUnv"][key] += 1
            if outcome_candidate_has_score_metric(row):
                indexes["outcomeScoreCandidatesByYearUnv"][key] += 1
            if outcome_candidate_has_quota_competition(row):
                indexes["outcomeQuotaCompetitionCandidatesByYearUnv"][key] += 1

    source_refs_path = adiga_dir / "adiga_image_source_references.csv"
    if source_refs_path.exists():
        indexes["inputPaths"].append(source_refs_path)
        for row in read_csv(source_refs_path):
            if is_decorative_adiga_image_ref(row):
                continue
            key = (normalize_year(row.get("year")), normalize_text(row.get("unvCd")))
            indexes["imageRefsByYearUnv"][key].append(row)

    ocr_evidence_path = extracted_dir / "adiga_image_ocr_evidence_index.csv"
    if ocr_evidence_path.exists():
        indexes["inputPaths"].append(ocr_evidence_path)
        for row in read_csv(ocr_evidence_path):
            image_key = normalize_text(row.get("canonicalImageKey"))
            if image_key:
                indexes["ocrEvidenceByImageKey"][image_key].append(row)

    return indexes


def build_review_queue(
    collection_targets: list[dict[str, str]],
    indexes: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for target in collection_targets:
        key = (
            normalize_year(target.get("admissionYear")),
            normalize_text(target.get("unvCd")),
        )
        manifest = indexes["manifestByYearUnv"].get(key, {})
        tables = indexes["tablesByYearUnv"].get(key, [])
        outcome_count = indexes["outcomeCandidatesByYearUnv"].get(key, 0)
        outcome_score_count = indexes["outcomeScoreCandidatesByYearUnv"].get(key, 0)
        outcome_quota_competition_count = indexes[
            "outcomeQuotaCompetitionCandidatesByYearUnv"
        ].get(key, 0)
        image_refs = indexes["imageRefsByYearUnv"].get(key, [])
        ocr_rows = ocr_rows_for_image_refs(image_refs, indexes["ocrEvidenceByImageKey"])
        role_counts = Counter(normalize_text(table.get("tableRole")) for table in tables)
        has_non_applicable_csat_outcome = has_non_applicable_csat_outcome_table(tables)
        bucket = parser_review_bucket(
            target,
            manifest,
            role_counts,
            outcome_count,
            image_refs,
            ocr_rows,
            has_non_applicable_csat_outcome,
        )
        blocker_flags = parser_blocker_flags(
            target,
            manifest,
            role_counts,
            outcome_count,
            image_refs,
            ocr_rows,
            has_non_applicable_csat_outcome,
        )
        top_table = top_diagnostic_table(tables)
        priority = parser_review_priority(
            target,
            bucket,
            role_counts,
            outcome_count,
            image_refs,
            ocr_rows,
        )

        rows.append(
            {
                "adigaParserReviewQueueId": deterministic_uuid(
                    "adiga-parser-review:"
                    f"{normalize_text(target.get('collectionTargetId'))}:{bucket}"
                ),
                "artifactType": "foundation_gap_adiga_parser_review_queue_item",
                "collectionTargetId": normalize_text(target.get("collectionTargetId")),
                "priorityTier": normalize_text(target.get("priorityTier")),
                "parserReviewPriorityScore": priority,
                "parserReviewBucket": bucket,
                "parserReviewAction": parser_review_action(bucket),
                "parserReviewStatus": "needs_human_or_parser_review",
                "unvCd": normalize_text(target.get("unvCd")),
                "universityName": normalize_text(target.get("universityName")),
                "admissionYear": int_or_none(target.get("admissionYear"))
                or normalize_text(target.get("admissionYear")),
                "gapCount": int_or_none(target.get("gapCount")) or 0,
                "missingFlags": normalize_text(target.get("missingFlags")),
                "targetEntities": normalize_text(target.get("targetEntities")),
                "recommendedActions": normalize_text(target.get("recommendedActions")),
                "sourceUrl": normalize_text(target.get("sourceUrl")),
                "rawPath": normalize_text(target.get("rawPath") or manifest.get("rawPath")),
                "manifestStatus": normalize_text(manifest.get("status")),
                "rawBytes": int_or_none(manifest.get("bytes")) or 0,
                "hasCsatTrack": bool((manifest.get("indicators") or {}).get("hasCsatTrack")),
                "finalRegistrantMentions": int_or_none((manifest.get("indicators") or {}).get("finalRegistrantMentions")) or 0,
                "percentileMentions": int_or_none((manifest.get("indicators") or {}).get("percentileMentions")) or 0,
                "convertedScoreMentions": int_or_none((manifest.get("indicators") or {}).get("convertedScoreMentions")) or 0,
                "htmlTableRows": len(tables),
                "csatOutcomeTables": role_counts.get("csat_outcome", 0),
                "csatOutcomeNonApplicableTables": 1 if has_non_applicable_csat_outcome else 0,
                "csatRuleTables": role_counts.get("csat_rule", 0),
                "studentOutcomeTables": role_counts.get("student_outcome", 0),
                "studentRuleTables": role_counts.get("student_rule", 0),
                "commonTables": role_counts.get("common", 0),
                "otherTables": role_counts.get("other", 0),
                "csatOutcomeCandidateRows": outcome_count,
                "csatOutcomeScoreCandidateRows": outcome_score_count,
                "csatOutcomeQuotaCompetitionRows": outcome_quota_competition_count,
                "adigaImageReferenceRows": len(image_refs),
                "adigaImageOcrEvidenceRows": len(ocr_rows),
                "topDiagnosticTableRole": normalize_text(top_table.get("tableRole")),
                "topDiagnosticSectionId": normalize_text(top_table.get("sectionId")),
                "topDiagnosticHeader": normalize_text(top_table.get("headerText"))[:500],
                "topDiagnosticSnippet": normalize_text(top_table.get("textSnippet"))[:500],
                "parserBlockerFlags": "|".join(blocker_flags),
                "operatorNextStep": operator_next_step(bucket, target),
            }
        )
    return rows


def ocr_rows_for_image_refs(
    image_refs: list[dict[str, str]],
    ocr_by_key: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for ref in image_refs:
        key = normalize_text(ref.get("canonicalImageKey"))
        for row in ocr_by_key.get(key, []):
            evidence_key = normalize_text(row.get("evidenceSha256")) or key
            if evidence_key in seen:
                continue
            seen.add(evidence_key)
            rows.append(row)
    return rows


def is_decorative_adiga_image_ref(row: dict[str, str]) -> bool:
    image_url = normalize_text(row.get("imageUrl")).lower()
    canonical_key = normalize_text(row.get("canonicalImageKey"))
    width = int_or_none(row.get("width")) or 0
    height = int_or_none(row.get("height")) or 0
    image_bytes = int_or_none(row.get("imageBytes")) or 0
    if "defaulttype=03" in image_url:
        return True
    if width and height and width <= 120 and height <= 120:
        return True
    if width and height and width == height and width <= 360 and image_bytes <= 60000:
        return True
    if re.search(r"fileid_0{12}2\d+_filesn_1", canonical_key):
        return True
    return False


def outcome_candidate_has_score_metric(row: dict[str, str]) -> bool:
    availability = normalize_text(row.get("scoreAvailability"))
    if availability and availability != "no_score_metric":
        return True
    return any(
        normalize_text(row.get(field))
        for field in (
            "convertedScore50Cut",
            "convertedScore70Cut",
            "percentile70Average",
        )
    )


def outcome_candidate_has_quota_competition(row: dict[str, str]) -> bool:
    return bool(normalize_text(row.get("quota")) and normalize_text(row.get("competitionRate")))


def parser_review_bucket(
    target: dict[str, str],
    manifest: dict[str, Any],
    role_counts: Counter[str],
    outcome_count: int,
    image_refs: list[dict[str, str]],
    ocr_rows: list[dict[str, str]],
    has_non_applicable_csat_outcome: bool,
) -> str:
    if not manifest:
        return "missing_adiga_manifest_refetch"
    if normalize_text(manifest.get("status")) != "fetched":
        return "adiga_fetch_failed_refetch"
    if outcome_count > 0:
        return "csat_outcome_candidates_available_recheck_gap_mapping"
    if has_non_applicable_csat_outcome:
        return "csat_outcome_non_applicable"
    if role_counts.get("csat_outcome", 0) > 0:
        return "csat_outcome_table_parser_repair"
    if role_counts.get("csat_rule", 0) > 0 and "missing_csat_rule_draft" in normalize_text(target.get("missingFlags")):
        return "csat_rule_table_review"
    if role_counts.get("student_outcome", 0) > 0:
        return "student_outcome_only_needs_office_or_scope_review"
    if len(ocr_rows) > 0 and len(image_refs) > 0 and sum(role_counts.values()) == 0:
        return "image_only_detail_visual_ocr_review"
    if len(image_refs) > 0 and sum(role_counts.values()) == 0:
        return "image_only_detail_download_or_ocr_review"
    indicators = manifest.get("indicators") or {}
    if has_outcome_keyword_signal(indicators):
        return "keyword_signal_no_csat_table_parser_review"
    if indicators.get("hasCsatTrack"):
        return "csat_section_no_structured_outcome"
    return "adiga_detail_low_signal_manual_source_search"


def parser_blocker_flags(
    target: dict[str, str],
    manifest: dict[str, Any],
    role_counts: Counter[str],
    outcome_count: int,
    image_refs: list[dict[str, str]],
    ocr_rows: list[dict[str, str]],
    has_non_applicable_csat_outcome: bool,
) -> list[str]:
    flags: list[str] = []
    if not manifest:
        flags.append("missing_manifest")
    elif normalize_text(manifest.get("status")) != "fetched":
        flags.append("fetch_not_successful")
    if outcome_count == 0:
        flags.append("no_csat_outcome_candidate_rows")
    if role_counts.get("csat_outcome", 0) == 0:
        flags.append("no_csat_outcome_html_table")
    if has_non_applicable_csat_outcome:
        flags.append("csat_outcome_table_non_applicable")
    if role_counts.get("student_outcome", 0) > 0:
        flags.append("student_outcome_table_present")
    if role_counts.get("csat_rule", 0) > 0:
        flags.append("csat_rule_table_present")
    if sum(role_counts.values()) == 0:
        flags.append("no_html_tables_extracted")
    if len(image_refs) > 0:
        flags.append("adiga_image_references_present")
    if len(ocr_rows) > 0:
        flags.append("adiga_image_ocr_evidence_present")
    indicators = manifest.get("indicators") if manifest else {}
    if has_percentile_only_signal(indicators):
        flags.append("weak_percentile_only_keyword_signal")
    if "missing_historical_outcomes" in normalize_text(target.get("missingFlags")) and outcome_count == 0:
        flags.append("historical_outcome_gap_unresolved")
    return flags


def has_outcome_keyword_signal(indicators: Any) -> bool:
    if not isinstance(indicators, dict):
        return False
    return bool(
        int_or_none(indicators.get("finalRegistrantMentions"))
        or int_or_none(indicators.get("convertedScoreMentions"))
    )


def has_percentile_only_signal(indicators: Any) -> bool:
    if not isinstance(indicators, dict):
        return False
    return bool(
        int_or_none(indicators.get("percentileMentions"))
        and not int_or_none(indicators.get("finalRegistrantMentions"))
        and not int_or_none(indicators.get("convertedScoreMentions"))
    )


def top_diagnostic_table(tables: list[dict[str, Any]]) -> dict[str, Any]:
    if not tables:
        return {}
    preferred_roles = [
        "csat_outcome",
        "student_outcome",
        "csat_rule",
        "student_rule",
        "common",
        "other",
    ]
    for role in preferred_roles:
        role_tables = [table for table in tables if normalize_text(table.get("tableRole")) == role]
        if role_tables:
            return max(role_tables, key=lambda table: int_or_none(table.get("rows")) or 0)
    return tables[0]


def has_non_applicable_csat_outcome_table(tables: list[dict[str, Any]]) -> bool:
    for table in tables:
        if normalize_text(table.get("tableRole")) != "csat_outcome":
            continue
        text = normalize_text(
            " ".join(
                [
                    str(table.get("headerText") or ""),
                    str(table.get("textSnippet") or ""),
                    json.dumps(table.get("grid") or [], ensure_ascii=False),
                ]
            )
        )
        if re.search(r"해당\s*없음|해당\s*없슴|없음|해당\s*사항\s*없", text):
            return True
    return False


def parser_review_action(bucket: str) -> str:
    return {
        "missing_adiga_manifest_refetch": "Refetch Adiga detail and rebuild extracted tables.",
        "adiga_fetch_failed_refetch": "Retry Adiga detail fetch before parser review.",
        "csat_outcome_candidates_available_recheck_gap_mapping": "Inspect candidate linkage; gap may be coverage mapping rather than parser absence.",
        "csat_outcome_non_applicable": "Record that Adiga explicitly marks the CSAT outcome table as not applicable; use admission-office sources for other gaps.",
        "csat_outcome_table_parser_repair": "Repair csat_outcome table column inference and rebuild outcome candidates.",
        "csat_rule_table_review": "Review csat_rule tables and promote rule drafts or record blocker.",
        "student_outcome_only_needs_office_or_scope_review": "Do not promote as CSAT outcome; seek admission-office regular outcome source or mark scope blocker.",
        "image_only_detail_visual_ocr_review": "Review Adiga image/OCR evidence and extract structured table if relevant.",
        "image_only_detail_download_or_ocr_review": "Download/OCR Adiga image references or confirm they are decorative.",
        "keyword_signal_no_csat_table_parser_review": "Inspect raw HTML around outcome keywords and refine section/table classifier.",
        "csat_section_no_structured_outcome": "Confirm whether CSAT section lacks public outcome data; then use office-source discovery.",
        "adiga_detail_low_signal_manual_source_search": "Use public discovery queue to find official admission-office source.",
    }.get(bucket, "Review Adiga detail target.")


def parser_review_priority(
    target: dict[str, str],
    bucket: str,
    role_counts: Counter[str],
    outcome_count: int,
    image_refs: list[dict[str, str]],
    ocr_rows: list[dict[str, str]],
) -> int:
    score = int_or_none(target.get("collectionPriorityScore")) or 0
    score += {
        "csat_outcome_table_parser_repair": 50,
        "keyword_signal_no_csat_table_parser_review": 42,
        "csat_outcome_candidates_available_recheck_gap_mapping": 38,
        "image_only_detail_visual_ocr_review": 34,
        "csat_rule_table_review": 30,
        "student_outcome_only_needs_office_or_scope_review": 18,
        "image_only_detail_download_or_ocr_review": 16,
        "csat_section_no_structured_outcome": 12,
        "csat_outcome_non_applicable": 10,
        "missing_adiga_manifest_refetch": 8,
        "adiga_fetch_failed_refetch": 8,
        "adiga_detail_low_signal_manual_source_search": 5,
    }.get(bucket, 0)
    score += min(role_counts.get("csat_outcome", 0) * 4, 24)
    score += min(outcome_count, 20)
    score += min(len(ocr_rows), 10)
    score += min(len(image_refs), 8)
    return score


def operator_next_step(bucket: str, target: dict[str, str]) -> str:
    action = parser_review_action(bucket)
    return (
        f"{action} Target {normalize_text(target.get('universityName'))} "
        f"{normalize_text(target.get('admissionYear'))}; "
        f"raw={normalize_text(target.get('rawPath')) or 'missing'}."
    )


def summarize(
    repo_root: Path,
    inputs: list[Path],
    collection_targets: list[dict[str, str]],
    review_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    immediate_parser_rows = [
        row
        for row in review_rows
        if row.get("parserReviewBucket")
        in {
            "csat_outcome_table_parser_repair",
            "keyword_signal_no_csat_table_parser_review",
            "csat_outcome_candidates_available_recheck_gap_mapping",
            "csat_rule_table_review",
        }
    ]
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_adiga_parser_review_queue_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [input_summary(path, repo_root) for path in inputs],
        "collectionTargets": {
            "total": len(collection_targets),
        },
        "reviewRows": {
            "total": len(review_rows),
            "immediateParserRepairOrMapping": len(immediate_parser_rows),
            "withHtmlTables": sum(1 for row in review_rows if int_or_none(row.get("htmlTableRows"))),
            "withImageReferences": sum(1 for row in review_rows if int_or_none(row.get("adigaImageReferenceRows"))),
            "withImageOcrEvidence": sum(1 for row in review_rows if int_or_none(row.get("adigaImageOcrEvidenceRows"))),
        },
        "byParserReviewBucket": counter_items(
            Counter(str(row.get("parserReviewBucket") or "") for row in review_rows)
        ),
        "byParserReviewBucketCounts": dict(
            Counter(str(row.get("parserReviewBucket") or "") for row in review_rows)
        ),
        "byAdmissionYear": counter_items(
            Counter(str(row.get("admissionYear") or "") for row in review_rows)
        ),
        "topUniversities": counter_items(
            Counter(str(row.get("universityName") or "") for row in review_rows),
            limit=30,
        ),
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    configure_csv_field_limit()
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def configure_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        fieldnames = list(rows[0].keys()) if rows else CSV_FIELDS
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def input_summary(path: Path, repo_root: Path) -> dict[str, Any]:
    return {
        "path": to_repo_relative(path, repo_root),
        "sha256": sha256_file(path),
        "rows": input_row_count(path),
    }


def input_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as file:
            return sum(1 for line in file if line.strip())
    with path.open(newline="", encoding="utf-8-sig") as file:
        return max(sum(1 for _ in file) - 1, 0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def counter_items(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [
        {"value": key, "count": count}
        for key, count in counter.most_common(limit)
        if key
    ]


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def normalize_year(value: Any) -> str:
    text = normalize_text(value)
    match = re.search(r"\d{4}", text)
    return match.group(0) if match else text


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def int_or_none(value: Any) -> int | None:
    try:
        text = normalize_text(value).replace(",", "")
        return int(float(text)) if text else None
    except ValueError:
        return None


def int_or_large(value: Any) -> int:
    return int_or_none(value) or 999999


def priority_sort(value: Any) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(normalize_text(value), 9)


def bucket_sort(value: Any) -> int:
    return {
        "csat_outcome_table_parser_repair": 0,
        "keyword_signal_no_csat_table_parser_review": 1,
        "csat_outcome_candidates_available_recheck_gap_mapping": 2,
        "image_only_detail_visual_ocr_review": 3,
        "csat_rule_table_review": 4,
        "student_outcome_only_needs_office_or_scope_review": 5,
        "image_only_detail_download_or_ocr_review": 6,
        "csat_section_no_structured_outcome": 7,
        "missing_adiga_manifest_refetch": 8,
        "adiga_fetch_failed_refetch": 9,
        "adiga_detail_low_signal_manual_source_search": 10,
    }.get(normalize_text(value), 99)


if __name__ == "__main__":
    main()
