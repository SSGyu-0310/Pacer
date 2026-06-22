#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urlparse


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_PACKET_ROWS = "foundation_operational_review_packet_rows.csv"
DEFAULT_PACKET_BATCHES = "foundation_operational_review_packet_batches.csv"
DEFAULT_ADMISSION_UNITS = "foundation_admission_units.csv"
DEFAULT_EVIDENCE_LINKS = "foundation_admission_office_evidence_links.csv"
OUTPUT_CSV = "foundation_operational_review_decision_template.csv"
OUTPUT_SUMMARY = "foundation_operational_review_decision_summary.json"

FIELDNAMES = [
    "decisionId",
    "decisionStatus",
    "suggestedReviewDecision",
    "suggestedDecisionReason",
    "reviewer",
    "reviewedAt",
    "reviewNotes",
    "packetRank",
    "reviewBatchId",
    "reviewLane",
    "rowRankInBatch",
    "promotionQueueId",
    "targetEntity",
    "promotionAction",
    "ruleCategory",
    "priorityTier",
    "reviewPriorityScore",
    "confidence",
    "admissionYear",
    "academicYear",
    "examType",
    "unvCd",
    "universityName",
    "admissionUnitName",
    "recruitmentGroup",
    "subjectName",
    "provider",
    "sourceArtifact",
    "sourceRecordId",
    "localRawPathCount",
    "existingRawPathCount",
    "missingRawPathCount",
    "localSourcePathCount",
    "existingSourcePathCount",
    "missingSourcePathCount",
    "requestedYear",
    "localEvidenceYears",
    "urlEvidenceYears",
    "hasRequestedYearLocalEvidence",
    "hasRequestedYearUrlEvidence",
    "hasMixedYearLocalEvidence",
    "hasAdigaRequestedYearHtml",
    "sourceUrls",
    "attachmentUrls",
    "rawPaths",
    "sourcePaths",
    "evidenceSummary",
    "reviewInstruction",
]


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    packet_rows = list(read_csv(foundation_dir / args.packet_rows_csv))
    packet_batches = list(read_csv(foundation_dir / args.packet_batches_csv))
    lane_by_batch = {
        normalize_text(row.get("reviewBatchId")): normalize_text(row.get("reviewLane"))
        for row in packet_batches
    }
    admission_unit_evidence = load_admission_unit_evidence(
        repo_root,
        foundation_dir,
        args.admission_units_csv,
        args.evidence_links_csv,
    )

    decisions = [
        build_decision(
            repo_root,
            row,
            lane_by_batch.get(normalize_text(row.get("reviewBatchId")), ""),
            admission_unit_evidence,
        )
        for row in packet_rows
    ]
    write_csv(foundation_dir / OUTPUT_CSV, decisions)
    summary = summarize(repo_root, foundation_dir, packet_rows, decisions)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation operational review decisions complete. "
        f"decisionRows={len(decisions)} output={to_repo_relative(foundation_dir / OUTPUT_CSV, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--packet-rows-csv", default=DEFAULT_PACKET_ROWS)
    parser.add_argument("--packet-batches-csv", default=DEFAULT_PACKET_BATCHES)
    parser.add_argument("--admission-units-csv", default=DEFAULT_ADMISSION_UNITS)
    parser.add_argument("--evidence-links-csv", default=DEFAULT_EVIDENCE_LINKS)
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


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def load_admission_unit_evidence(
    repo_root: Path,
    foundation_dir: Path,
    admission_units_csv: str,
    evidence_links_csv: str,
) -> dict[str, dict[str, list[str]]]:
    evidence_by_sha: dict[str, list[dict[str, str]]] = {}
    for evidence in read_csv(foundation_dir / evidence_links_csv):
        sha = normalize_text(evidence.get("evidenceCandidateSha256"))
        if sha:
            evidence_by_sha.setdefault(sha, []).append(evidence)

    output: dict[str, dict[str, list[str]]] = {}
    for unit in read_csv(foundation_dir / admission_units_csv):
        unit_id = normalize_text(unit.get("unitCandidateId"))
        if not unit_id:
            continue
        evidence = {
            "sourceUrls": [],
            "attachmentUrls": [],
            "rawPaths": [],
            "sourcePaths": [],
        }
        year = normalize_text(unit.get("year"))
        unv_cd = normalize_text(unit.get("unvCd"))
        providers = set(split_joined(unit.get("sourceProviders")))
        if "adiga" in providers and year and unv_cd:
            add_unique(
                evidence["sourceUrls"],
                [
                    "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"
                    f"?menuId=PCUVTINF2000&searchSyr={year}&unvCd={unv_cd}"
                ],
            )
            raw_path = f".reference-data/raw/adiga/{year}/{unv_cd}/selection.html"
            add_unique(evidence["rawPaths"], [raw_path])

        for sha in split_joined(unit.get("sourceCandidateSha256Values")):
            for linked in evidence_by_sha.get(sha, []):
                add_unique(evidence["sourceUrls"], split_joined(linked.get("sourceCandidateUrls")))
                add_unique(evidence["sourceUrls"], split_joined(linked.get("sourceCandidateUrl")))
                add_unique(evidence["attachmentUrls"], split_joined(linked.get("attachmentUrls")))
                add_unique(evidence["attachmentUrls"], split_joined(linked.get("attachmentUrl")))
                add_unique(evidence["rawPaths"], split_joined(linked.get("rawPaths")))
                add_unique(evidence["rawPaths"], split_joined(linked.get("rawPath")))
                add_unique(evidence["sourcePaths"], split_joined(linked.get("sourcePaths")))
                add_unique(evidence["sourcePaths"], split_joined(linked.get("sourcePath")))

        existing_raw_paths = [
            path for path in evidence["rawPaths"] if not is_local_path(path) or resolve(repo_root, path).exists()
        ]
        if existing_raw_paths or evidence["sourceUrls"] or evidence["sourcePaths"]:
            output[unit_id] = evidence
    return output


def build_decision(
    repo_root: Path,
    row: dict[str, str],
    review_lane: str,
    admission_unit_evidence: dict[str, dict[str, list[str]]],
) -> dict[str, Any]:
    enrichment = admission_unit_evidence.get(normalize_text(row.get("sourceRecordId")), {})
    raw_paths = merge_split_values(row.get("rawPaths"), enrichment.get("rawPaths", []))
    source_paths = merge_split_values(row.get("sourcePaths"), enrichment.get("sourcePaths", []))
    source_urls = merge_split_values(row.get("sourceUrls"), enrichment.get("sourceUrls", []))
    attachment_urls = merge_split_values(row.get("attachmentUrls"), enrichment.get("attachmentUrls", []))
    local_raw = [path for path in raw_paths if is_local_path(path)]
    local_source = [path for path in source_paths if is_local_path(path)]
    existing_raw = [path for path in local_raw if resolve(repo_root, path).exists()]
    existing_source = [path for path in local_source if resolve(repo_root, path).exists()]
    requested_year = normalize_text(row.get("admissionYear") or row.get("academicYear"))

    local_years = sorted(
        {
            year
            for path in [*local_raw, *local_source]
            for year in path_years(path)
        }
    )
    url_years = sorted(
        {
            year
            for url in [*source_urls, *attachment_urls]
            for year in url_years_from_url(url)
        }
    )
    has_requested_local = bool(requested_year and requested_year in local_years)
    has_requested_url = bool(requested_year and requested_year in url_years)
    has_mixed_year_local = bool(requested_year and any(year != requested_year for year in local_years))
    has_adiga_requested = any(
        requested_year
        and requested_year in path_years(path)
        and "/adiga/" in path.replace("\\", "/")
        for path in local_raw
    )

    suggested, reason = suggested_decision(
        row=row,
        review_lane=review_lane,
        requested_year=requested_year,
        local_raw_count=len(local_raw),
        existing_raw_count=len(existing_raw),
        missing_raw_count=len(local_raw) - len(existing_raw),
        local_source_count=len(local_source),
        existing_source_count=len(existing_source),
        missing_source_count=len(local_source) - len(existing_source),
        has_requested_local=has_requested_local,
        has_requested_url=has_requested_url,
        has_mixed_year_local=has_mixed_year_local,
        has_adiga_requested=has_adiga_requested,
    )

    decision_id = "review-decision-" + normalize_text(row.get("promotionQueueId"))
    return {
        "decisionId": decision_id,
        "decisionStatus": "unreviewed",
        "suggestedReviewDecision": suggested,
        "suggestedDecisionReason": reason,
        "reviewer": "",
        "reviewedAt": "",
        "reviewNotes": "",
        "packetRank": row.get("packetRank", ""),
        "reviewBatchId": row.get("reviewBatchId", ""),
        "reviewLane": review_lane,
        "rowRankInBatch": row.get("rowRankInBatch", ""),
        "promotionQueueId": row.get("promotionQueueId", ""),
        "targetEntity": row.get("targetEntity", ""),
        "promotionAction": row.get("promotionAction", ""),
        "ruleCategory": row.get("ruleCategory", ""),
        "priorityTier": row.get("priorityTier", ""),
        "reviewPriorityScore": row.get("reviewPriorityScore", ""),
        "confidence": row.get("confidence", ""),
        "admissionYear": row.get("admissionYear", ""),
        "academicYear": row.get("academicYear", ""),
        "examType": row.get("examType", ""),
        "unvCd": row.get("unvCd", ""),
        "universityName": row.get("universityName", ""),
        "admissionUnitName": row.get("admissionUnitName", ""),
        "recruitmentGroup": row.get("recruitmentGroup", ""),
        "subjectName": row.get("subjectName", ""),
        "provider": row.get("provider", ""),
        "sourceArtifact": row.get("sourceArtifact", ""),
        "sourceRecordId": row.get("sourceRecordId", ""),
        "localRawPathCount": len(local_raw),
        "existingRawPathCount": len(existing_raw),
        "missingRawPathCount": len(local_raw) - len(existing_raw),
        "localSourcePathCount": len(local_source),
        "existingSourcePathCount": len(existing_source),
        "missingSourcePathCount": len(local_source) - len(existing_source),
        "requestedYear": requested_year,
        "localEvidenceYears": "|".join(local_years),
        "urlEvidenceYears": "|".join(url_years),
        "hasRequestedYearLocalEvidence": str(has_requested_local).lower(),
        "hasRequestedYearUrlEvidence": str(has_requested_url).lower(),
        "hasMixedYearLocalEvidence": str(has_mixed_year_local).lower(),
        "hasAdigaRequestedYearHtml": str(has_adiga_requested).lower(),
        "sourceUrls": "|".join(source_urls),
        "attachmentUrls": "|".join(attachment_urls),
        "rawPaths": "|".join(raw_paths),
        "sourcePaths": "|".join(source_paths),
        "evidenceSummary": row.get("evidenceSummary", ""),
        "reviewInstruction": row.get("reviewInstruction", ""),
    }


def suggested_decision(
    *,
    row: dict[str, str],
    review_lane: str,
    requested_year: str,
    local_raw_count: int,
    existing_raw_count: int,
    missing_raw_count: int,
    local_source_count: int,
    existing_source_count: int,
    missing_source_count: int,
    has_requested_local: bool,
    has_requested_url: bool,
    has_mixed_year_local: bool,
    has_adiga_requested: bool,
) -> tuple[str, str]:
    if local_raw_count + local_source_count == 0 and not row.get("sourceUrls") and not row.get("attachmentUrls"):
        return "hold_missing_evidence", "No local path or URL evidence is attached to the packet row."
    if missing_raw_count or missing_source_count:
        return "needs_missing_path_check", "One or more local raw/source paths do not exist in the workspace."
    if review_lane == "rule_schedule_2027" and has_mixed_year_local:
        if has_requested_local:
            return (
                "needs_manual_source_year_review",
                "2027 rule packet includes both requested-year and older local evidence; verify the older artifact is only duplicate/context before promotion.",
            )
        if has_adiga_requested or has_requested_url:
            return (
                "needs_manual_source_year_review",
                "2027 rule packet has requested-year URL/ADIGA evidence but local PDF/text paths are from a different collection year.",
            )
        return (
            "hold_source_year_mismatch",
            "2027 rule packet only exposes older local evidence years; do not promote without finding requested-year source evidence.",
        )
    if requested_year and not (has_requested_local or has_requested_url):
        return "needs_manual_source_year_review", "No requested-year signal was found in local paths or URLs."
    return "ready_for_source_review", "Local/URL evidence is attached; reviewer must compare original source values before verified promotion."


def summarize(
    repo_root: Path,
    foundation_dir: Path,
    packet_rows: list[dict[str, str]],
    decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    by_decision = Counter(str(row.get("suggestedReviewDecision") or "") for row in decisions)
    by_lane_decision = Counter(
        f"{row.get('reviewLane')}::{row.get('suggestedReviewDecision')}" for row in decisions
    )
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_operational_review_decision_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "packetRowsCsv": to_repo_relative(foundation_dir / DEFAULT_PACKET_ROWS, repo_root),
            "packetRows": len(packet_rows),
        },
        "outputs": {
            "decisionTemplateCsv": to_repo_relative(foundation_dir / OUTPUT_CSV, repo_root),
        },
        "decisionRows": len(decisions),
        "bySuggestedReviewDecision": dict(sorted(by_decision.items())),
        "byReviewLaneAndSuggestedDecision": dict(sorted(by_lane_decision.items())),
        "notes": [
            "This file is a decision template for review workflow; it does not mark source data verified.",
            "Rows with source-year mismatch should remain parsed/needs_human_verification until a reviewer opens the original source.",
            "The suggested decision is based on path/URL evidence only, not semantic validation of extracted numbers.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in FIELDNAMES})


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def merge_split_values(original: Any, extra: list[str]) -> list[str]:
    values: list[str] = []
    add_unique(values, split_joined(original))
    add_unique(values, extra)
    return values


def add_unique(target: list[str], values: Iterable[str]) -> None:
    seen = set(target)
    for value in values:
        text = normalize_text(value)
        if text and text not in seen:
            target.append(text)
            seen.add(text)


def is_local_path(value: str) -> bool:
    return not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", value)


def path_years(value: str) -> list[str]:
    years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", value.replace("\\", "/"))
    return [year for year in years if 2021 <= int(year) <= 2028]


def url_years_from_url(value: str) -> list[str]:
    years = set(path_years(value))
    parsed = urlparse(value)
    query = parse_qs(parsed.query)
    for key in ("searchSyr", "year", "m_year"):
        for item in query.get(key, []):
            years.update(path_years(item))
    return sorted(years)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
