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
from urllib.parse import urlparse


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_GAP_COLLECTION_TARGETS = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_collection_targets.csv"
)
DEFAULT_UNIVERSITY_SITE_DIR = "packages/reference-data/data/public/university-admission-sites"

OUTPUT_JSONL = "foundation_gap_crawler_worklist.jsonl"
OUTPUT_CSV = "foundation_gap_crawler_worklist.csv"
OUTPUT_SUMMARY = "foundation_gap_crawler_worklist_summary.json"

DIRECT_FILE_EXTENSIONS = {"csv", "doc", "docx", "hwp", "hwpx", "pdf", "xls", "xlsx", "zip"}
BLOCKED_HELPER_SOURCE_PATTERN = re.compile(
    r"jinhak|jinhakapply|uway|uwayapply|telegr|01consulting|nesin|고속성장|진학사|유웨이",
    re.I,
)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    targets_path = resolve(repo_root, args.gap_collection_targets)
    university_site_dir = resolve(repo_root, args.university_site_dir)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    office_targets = [
        row
        for row in read_csv(targets_path)
        if normalize_text(row.get("sourceProvider")) == "university-admission-office"
        and not row_has_blocked_helper_source(row)
    ]
    crawler_inputs = load_crawler_inputs(university_site_dir)
    worklist = build_worklist(office_targets, crawler_inputs)
    worklist.sort(
        key=lambda row: (
            priority_sort(row.get("priorityTier")),
            -int_or_none(row.get("crawlerPriorityScore") or 0),
            str(row.get("crawlerPattern") or ""),
            str(row.get("sourceHostname") or ""),
            str(row.get("pathFamily") or ""),
            str(row.get("sourceRole") or ""),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, worklist)
    write_csv(foundation_dir / OUTPUT_CSV, worklist)
    summary = summarize(
        repo_root=repo_root,
        inputs=[targets_path, *crawler_inputs["inputPaths"]],
        office_targets=office_targets,
        worklist=worklist,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap crawler worklist complete. "
        f"officeTargets={len(office_targets)} worklistRows={len(worklist)} "
        f"patterns={len(summary['byCrawlerPattern'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--gap-collection-targets", default=DEFAULT_GAP_COLLECTION_TARGETS)
    parser.add_argument("--university-site-dir", default=DEFAULT_UNIVERSITY_SITE_DIR)
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


def load_crawler_inputs(site_dir: Path) -> dict[str, Any]:
    indexes = new_indexes()
    input_paths: list[Path] = []

    for path in sorted(site_dir.glob("university_admission_homepage_manifest_*.jsonl")):
        input_paths.append(path)
        for row in read_jsonl(path):
            if row_has_blocked_helper_source(row):
                continue
            add_group_index(indexes["homepageManifestByGroup"], row)
            add_url_index(indexes["homepageManifestByUrl"], row_key(row), row, "sourceHomepageUrl", "finalHomepageUrl")

    for path in sorted(site_dir.glob("university_admission_link_candidates_*.csv")):
        input_paths.append(path)
        for row in read_csv(path):
            if row_has_blocked_helper_source(row):
                continue
            add_group_index(indexes["linkCandidateByGroup"], row)
            add_url_index(
                indexes["linkCandidateByUrl"],
                row_key(row),
                row,
                "sourceHomepageUrl",
                "finalHomepageUrl",
                "resolvedUrl",
            )

    for path in sorted(site_dir.glob("university_admission_link_artifact_manifest_*.jsonl")):
        input_paths.append(path)
        for row in read_jsonl(path):
            if row_has_blocked_helper_source(row):
                continue
            add_group_index(indexes["linkArtifactByGroup"], row)
            add_url_index(indexes["linkArtifactByUrl"], row_key(row), row, "sourceCandidateUrl", "finalUrl")

    for path in sorted(site_dir.glob("university_admission_attachment_candidates_*.csv")):
        input_paths.append(path)
        for row in read_csv(path):
            if row_has_blocked_helper_source(row):
                continue
            add_group_index(indexes["attachmentCandidateByGroup"], row)
            add_url_index(indexes["attachmentCandidateByUrl"], row_key(row), row, "sourceCandidateUrl", "resolvedUrl")

    for path in sorted(site_dir.glob("university_admission_related_detail_attachment_candidates_*.csv")):
        input_paths.append(path)
        for row in read_csv(path):
            if row_has_blocked_helper_source(row):
                continue
            add_group_index(indexes["relatedDetailCandidateByGroup"], row)
            add_url_index(indexes["relatedDetailCandidateByUrl"], row_key(row), row, "sourceCandidateUrl", "resolvedUrl")

    for path in sorted(site_dir.glob("university_admission_attachment_artifact_manifest_*.jsonl")):
        input_paths.append(path)
        for row in read_jsonl(path):
            if row_has_blocked_helper_source(row):
                continue
            add_group_index(indexes["attachmentArtifactByGroup"], row)
            add_url_index(
                indexes["attachmentArtifactByUrl"],
                row_key(row),
                row,
                "sourceCandidateUrl",
                "attachmentUrl",
                "canonicalAttachmentUrl",
                "finalUrl",
            )

    indexes["inputPaths"] = input_paths
    return indexes


def new_indexes() -> dict[str, Any]:
    return {
        "inputPaths": [],
        "homepageManifestByGroup": defaultdict(list),
        "homepageManifestByUrl": defaultdict(list),
        "linkCandidateByGroup": defaultdict(list),
        "linkCandidateByUrl": defaultdict(list),
        "linkArtifactByGroup": defaultdict(list),
        "linkArtifactByUrl": defaultdict(list),
        "attachmentCandidateByGroup": defaultdict(list),
        "attachmentCandidateByUrl": defaultdict(list),
        "relatedDetailCandidateByGroup": defaultdict(list),
        "relatedDetailCandidateByUrl": defaultdict(list),
        "attachmentArtifactByGroup": defaultdict(list),
        "attachmentArtifactByUrl": defaultdict(list),
    }


def add_group_index(index: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]], row: dict[str, Any]) -> None:
    unv_cd = normalize_text(row.get("unvCd"))
    year = normalize_text(row.get("year"))
    if unv_cd and year:
        index[(unv_cd, year)].append((row_key(row), row))


def add_url_index(
    index: dict[str, list[tuple[str, dict[str, Any]]]],
    key: str,
    row: dict[str, Any],
    *url_fields: str,
) -> None:
    for field in url_fields:
        url = canonical_url(row.get(field))
        if url:
            index[url].append((key, row))


def build_worklist(office_targets: list[dict[str, str]], indexes: dict[str, Any]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in office_targets:
        pattern = classify_crawler_pattern(row)
        action = recommended_action(pattern, row)
        path = path_family(row.get("sourceUrl"))
        host = source_hostname(row)
        key = (
            pattern,
            action,
            host,
            normalize_text(row.get("collectionRoute")),
            normalize_text(row.get("existingFetchStatus")),
            normalize_text(row.get("sourceRole")),
            normalize_text(row.get("sourceFileExtension")),
            path,
        )
        if key not in groups:
            groups[key] = new_worklist_group(row, pattern, action, path, host)
        add_target_to_group(groups[key], row, linked_sets_for_target(row, indexes))

    return [finalize_group(group) for group in groups.values()]


def new_worklist_group(
    row: dict[str, str],
    pattern: str,
    action: str,
    path: str,
    host: str,
) -> dict[str, Any]:
    return {
        "crawlerWorklistId": deterministic_uuid(
            "gap-crawler-worklist:"
            f"{pattern}:{action}:{host}:{row.get('collectionRoute')}:{row.get('existingFetchStatus')}:"
            f"{row.get('sourceRole')}:{row.get('sourceFileExtension')}:{path}"
        ),
        "artifactType": "foundation_gap_crawler_worklist",
        "priorityTier": normalize_text(row.get("priorityTier")) or "p0",
        "crawlerPattern": pattern,
        "recommendedCrawlerAction": action,
        "sourceHostname": host,
        "pathFamily": path,
        "collectionRoute": normalize_text(row.get("collectionRoute")),
        "existingFetchStatus": normalize_text(row.get("existingFetchStatus")),
        "sourceRole": normalize_text(row.get("sourceRole")),
        "sourceFileExtension": normalize_text(row.get("sourceFileExtension")),
        "targetCount": 0,
        "gapCountSum": 0,
        "maxCollectionPriorityScore": 0,
        "unvCds": set(),
        "universityNames": set(),
        "universityYearGroups": set(),
        "admissionYears": set(),
        "missingFlags": Counter(),
        "targetEntities": Counter(),
        "recommendedActions": Counter(),
        "expectedAvailabilityValues": Counter(),
        "collectionTargetIds": set(),
        "sourceUrls": set(),
        "linkedHomepageManifestRows": set(),
        "linkedLinkCandidateRows": set(),
        "linkedLinkArtifactRows": set(),
        "linkedAttachmentCandidateRows": set(),
        "linkedRelatedDetailCandidateRows": set(),
        "linkedAttachmentArtifactRows": set(),
        "linkedRawPaths": set(),
    }


def add_target_to_group(group: dict[str, Any], row: dict[str, str], linked: dict[str, set[str]]) -> None:
    group["targetCount"] += 1
    group["gapCountSum"] += int_or_none(row.get("gapCount")) or 0
    group["maxCollectionPriorityScore"] = max(
        int(group.get("maxCollectionPriorityScore") or 0),
        int_or_none(row.get("collectionPriorityScore")) or 0,
    )
    unv_cd = normalize_text(row.get("unvCd"))
    year = normalize_text(row.get("admissionYear"))
    if unv_cd:
        group["unvCds"].add(unv_cd)
    if normalize_text(row.get("universityName")):
        group["universityNames"].add(normalize_text(row.get("universityName")))
    if unv_cd and year:
        group["universityYearGroups"].add(f"{unv_cd}:{year}")
    if year:
        group["admissionYears"].add(year)
    for field in ["missingFlags", "targetEntities", "recommendedActions", "expectedAvailabilityValues"]:
        for value in split_joined(row.get(field)):
            group[field][value] += 1
    if normalize_text(row.get("collectionTargetId")):
        group["collectionTargetIds"].add(normalize_text(row.get("collectionTargetId")))
    if canonical_url(row.get("sourceUrl")):
        group["sourceUrls"].add(canonical_url(row.get("sourceUrl")))
    for field, keys in linked.items():
        group[field].update(keys)


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    linked_counts = {
        "linkedHomepageManifestRows": len(group["linkedHomepageManifestRows"]),
        "linkedLinkCandidateRows": len(group["linkedLinkCandidateRows"]),
        "linkedLinkArtifactRows": len(group["linkedLinkArtifactRows"]),
        "linkedAttachmentCandidateRows": len(group["linkedAttachmentCandidateRows"]),
        "linkedRelatedDetailCandidateRows": len(group["linkedRelatedDetailCandidateRows"]),
        "linkedAttachmentArtifactRows": len(group["linkedAttachmentArtifactRows"]),
    }
    pipeline_stage = pipeline_stage_from_counts(group, linked_counts)
    score = crawler_priority_score(group, linked_counts)
    return {
        "crawlerWorklistId": group["crawlerWorklistId"],
        "artifactType": group["artifactType"],
        "priorityTier": group["priorityTier"],
        "crawlerPriorityScore": score,
        "pipelineStage": pipeline_stage,
        "crawlerPattern": group["crawlerPattern"],
        "recommendedCrawlerAction": group["recommendedCrawlerAction"],
        "sourceHostname": group["sourceHostname"],
        "pathFamily": group["pathFamily"],
        "collectionRoute": group["collectionRoute"],
        "existingFetchStatus": group["existingFetchStatus"],
        "sourceRole": group["sourceRole"],
        "sourceFileExtension": group["sourceFileExtension"],
        "targetCount": group["targetCount"],
        "gapCountSum": group["gapCountSum"],
        "universityCount": len(group["unvCds"]),
        "universityYearGroupCount": len(group["universityYearGroups"]),
        "admissionYears": join_sorted(group["admissionYears"], numeric=True),
        "missingFlags": join_counter_keys(group["missingFlags"]),
        "targetEntities": join_counter_keys(group["targetEntities"]),
        "recommendedActions": join_counter_keys(group["recommendedActions"]),
        "expectedAvailabilityValues": join_counter_keys(group["expectedAvailabilityValues"]),
        "sampleSourceUrls": join_sample(group["sourceUrls"], limit=5),
        "sampleUnvCds": join_sample(group["unvCds"], limit=8),
        "sampleUniversityNames": join_sample(group["universityNames"], limit=8),
        "sampleCollectionTargetIds": join_sample(group["collectionTargetIds"], limit=8),
        **linked_counts,
        "sampleLinkedRawPaths": join_sample(group["linkedRawPaths"], limit=5),
        "operatorNextStep": operator_next_step(group["crawlerPattern"], pipeline_stage, group),
    }


def linked_sets_for_target(row: dict[str, str], indexes: dict[str, Any]) -> dict[str, set[str]]:
    linked = {
        "linkedHomepageManifestRows": set(),
        "linkedLinkCandidateRows": set(),
        "linkedLinkArtifactRows": set(),
        "linkedAttachmentCandidateRows": set(),
        "linkedRelatedDetailCandidateRows": set(),
        "linkedAttachmentArtifactRows": set(),
        "linkedRawPaths": set(),
    }
    group = (normalize_text(row.get("unvCd")), normalize_text(row.get("admissionYear")))
    source_url = canonical_url(row.get("sourceUrl"))
    route = normalize_text(row.get("collectionRoute"))

    if route == "admission_homepage":
        add_indexed_rows(linked, "linkedHomepageManifestRows", indexes["homepageManifestByGroup"].get(group, []))

    if route in {"admission_homepage", "admission_office_deep_link_discovery"}:
        # Homepage/deep-discovery gaps often point at a seed URL that redirects to a
        # sibling board, intro, or Uway host. Preserve same university-year crawler
        # progress even when the final candidate URL no longer exactly equals the seed.
        add_indexed_rows(linked, "linkedLinkCandidateRows", indexes["linkCandidateByGroup"].get(group, []))
        add_indexed_rows(linked, "linkedLinkArtifactRows", indexes["linkArtifactByGroup"].get(group, []))
        add_indexed_rows(
            linked,
            "linkedAttachmentCandidateRows",
            indexes["attachmentCandidateByGroup"].get(group, []),
        )
        add_indexed_rows(
            linked,
            "linkedRelatedDetailCandidateRows",
            indexes["relatedDetailCandidateByGroup"].get(group, []),
        )
        add_indexed_rows(
            linked,
            "linkedAttachmentArtifactRows",
            indexes["attachmentArtifactByGroup"].get(group, []),
        )

    if source_url:
        add_indexed_rows(linked, "linkedHomepageManifestRows", indexes["homepageManifestByUrl"].get(source_url, []))
        add_indexed_rows(linked, "linkedLinkCandidateRows", indexes["linkCandidateByUrl"].get(source_url, []))
        add_indexed_rows(linked, "linkedLinkArtifactRows", indexes["linkArtifactByUrl"].get(source_url, []))
        add_indexed_rows(linked, "linkedAttachmentCandidateRows", indexes["attachmentCandidateByUrl"].get(source_url, []))
        add_indexed_rows(linked, "linkedRelatedDetailCandidateRows", indexes["relatedDetailCandidateByUrl"].get(source_url, []))
        add_indexed_rows(linked, "linkedAttachmentArtifactRows", indexes["attachmentArtifactByUrl"].get(source_url, []))

    return linked


def add_indexed_rows(
    linked: dict[str, set[str]],
    field: str,
    rows: list[tuple[str, dict[str, Any]]],
) -> None:
    for key, row in rows:
        linked[field].add(key)
        raw_path = normalize_text(row.get("rawPath") or row.get("detailRawPath"))
        if raw_path:
            linked["linkedRawPaths"].add(raw_path)


def classify_crawler_pattern(row: dict[str, str]) -> str:
    url = normalize_text(row.get("sourceUrl"))
    host = source_hostname(row)
    route = normalize_text(row.get("collectionRoute"))
    status = normalize_text(row.get("existingFetchStatus"))
    file_ext = source_file_extension(row)
    parsed = urlparse(url)
    path = parsed.path.lower()

    if not url:
        if status == "fetch_required":
            return "homepage_initial_fetch"
        if status == "homepage_fetch_failed_retry_or_manual":
            return "homepage_fetch_retry_or_manual"
        return "missing_source_url_review"
    if file_ext in DIRECT_FILE_EXTENSIONS:
        return "direct_file_fetch"
    if "/bbs/list.do" in path:
        return "korean_bbs_list_parser"
    if "/bbs/read" in path:
        return "korean_bbs_detail_parser"
    if "/board/list" in path:
        return "board_list_parser"
    if "/board/read" in path:
        return "board_detail_parser"
    if "/prog/" in path and path.endswith("/list.do"):
        return "program_list_parser"
    if route == "admission_homepage" and status == "already_fetched_needs_link_parser_review":
        return "homepage_link_extractor_review"
    if route == "admission_office_deep_link_discovery":
        return "rendered_homepage_or_board_discovery"
    if status == "homepage_fetch_failed_retry_or_manual":
        return "homepage_fetch_retry_or_manual"
    if status == "fetch_required":
        return "homepage_initial_fetch"
    if route == "admission_office_result_board_or_file":
        return "result_board_or_file_discovery"
    if file_ext in {"asp", "aspx", "do", "php"}:
        return "dynamic_notice_page_fetch"
    return "admission_office_html_review"


def recommended_action(pattern: str, row: dict[str, str]) -> str:
    if pattern == "direct_file_fetch":
        return "fetch_file_then_text_table_ocr_extraction"
    if pattern in {"korean_bbs_list_parser", "board_list_parser", "program_list_parser"}:
        return "crawl_board_list_then_select_year_keyword_details"
    if pattern in {"korean_bbs_detail_parser", "board_detail_parser"}:
        return "fetch_detail_then_extract_file_download_routes"
    if pattern == "homepage_link_extractor_review":
        return "reparse_homepage_links_with_admission_keyword_rules"
    if pattern == "rendered_homepage_or_board_discovery":
        return "discover_rendered_or_script_generated_admission_links"
    if pattern == "homepage_fetch_retry_or_manual":
        return "retry_homepage_fetch_with_headers_or_manual_seed"
    if pattern == "homepage_initial_fetch":
        return "fetch_homepage_then_extract_admission_links"
    if pattern == "result_board_or_file_discovery":
        return "crawl_result_board_or_file_route_candidates"
    if pattern == "dynamic_notice_page_fetch":
        return "fetch_dynamic_notice_page_then_extract_attachments"
    return "fetch_html_then_extract_admission_links_and_attachments"


def pipeline_stage_from_counts(group: dict[str, Any], linked_counts: dict[str, int]) -> str:
    if linked_counts["linkedAttachmentArtifactRows"] > 0:
        return "attachment_fetched_needs_extraction_or_promotion_review"
    if linked_counts["linkedRelatedDetailCandidateRows"] > 0:
        return "related_detail_candidates_ready_for_attachment_fetch"
    if linked_counts["linkedAttachmentCandidateRows"] > 0:
        return "attachment_candidates_ready_for_fetch"
    if linked_counts["linkedLinkArtifactRows"] > 0:
        return "detail_html_fetched_needs_attachment_extraction"
    if linked_counts["linkedLinkCandidateRows"] > 0:
        return "link_candidates_ready_for_detail_fetch"
    if linked_counts["linkedHomepageManifestRows"] > 0:
        return "homepage_html_fetched_needs_link_extraction"
    if group["existingFetchStatus"] in {"fetch_required", "homepage_fetch_failed_retry_or_manual", "no_matching_link_candidate"}:
        return "source_discovery_or_refetch_required"
    return "crawler_or_parser_review_required"


def crawler_priority_score(group: dict[str, Any], linked_counts: dict[str, int]) -> int:
    status_bonus = {
        "link_candidate_discovered_needs_detail_or_attachment_crawl": 70,
        "already_fetched_needs_link_parser_review": 45,
        "no_matching_link_candidate": 35,
        "fetch_required": 25,
        "homepage_fetch_failed_retry_or_manual": 20,
    }.get(group["existingFetchStatus"], 10)
    route_bonus = {
        "admission_office_guide_or_notice": 45,
        "admission_office_result_board_or_file": 44,
        "admission_office_link_candidate": 38,
        "admission_office_deep_link_discovery": 30,
        "admission_homepage": 25,
    }.get(group["collectionRoute"], 10)
    pattern_bonus = {
        "direct_file_fetch": 80,
        "korean_bbs_list_parser": 60,
        "board_list_parser": 58,
        "program_list_parser": 56,
        "board_detail_parser": 54,
        "korean_bbs_detail_parser": 54,
        "dynamic_notice_page_fetch": 45,
        "homepage_link_extractor_review": 42,
        "result_board_or_file_discovery": 40,
        "rendered_homepage_or_board_discovery": 32,
        "homepage_initial_fetch": 20,
        "homepage_fetch_retry_or_manual": 16,
    }.get(group["crawlerPattern"], 8)
    evidence_bonus = min(80, linked_counts["linkedAttachmentArtifactRows"] * 3)
    evidence_bonus += min(60, linked_counts["linkedLinkArtifactRows"] * 2)
    return (
        int(group.get("maxCollectionPriorityScore") or 0)
        + min(500, int(group.get("gapCountSum") or 0) * 3)
        + min(160, int(group.get("targetCount") or 0) * 4)
        + status_bonus
        + route_bonus
        + pattern_bonus
        + evidence_bonus
    )


def operator_next_step(pattern: str, pipeline_stage: str, group: dict[str, Any]) -> str:
    if pipeline_stage == "attachment_fetched_needs_extraction_or_promotion_review":
        return "Run document extraction/promotion review for fetched attachments linked to these gap targets."
    if pipeline_stage == "related_detail_candidates_ready_for_attachment_fetch":
        return "Fetch related detail attachment candidates, then extract file download routes and document text."
    if pipeline_stage == "attachment_candidates_ready_for_fetch":
        return "Fetch attachment candidates for this host/pattern and feed resulting files into PDF/HWP/workbook extractors."
    if pipeline_stage == "detail_html_fetched_needs_attachment_extraction":
        return "Extract attachment candidates from fetched detail HTML before refetching the homepage."
    if pipeline_stage == "link_candidates_ready_for_detail_fetch":
        return "Fetch discovered detail/link candidates and collect attachment candidates for the same university-year gaps."
    if pattern == "homepage_link_extractor_review":
        return "Re-run or improve homepage link extraction with admission-year and 정시/수능/입시결과 keywords."
    if pattern == "direct_file_fetch":
        return "Fetch the direct public file URL and route it through PDF/HWP/workbook/OCR extraction."
    if pattern == "homepage_fetch_retry_or_manual":
        return "Retry homepage fetch with browser-like headers; if still blocked, add a manual seed URL from the admission office."
    if pattern == "rendered_homepage_or_board_discovery":
        return "Use rendered-page discovery or manual board seeds because static homepage extraction found no matching candidate."
    return f"Run {group['recommendedCrawlerAction']} for this host/path family, then refresh gap source candidates."


def summarize(
    repo_root: Path,
    inputs: list[Path],
    office_targets: list[dict[str, str]],
    worklist: list[dict[str, Any]],
) -> dict[str, Any]:
    unique_groups = {
        (normalize_text(row.get("unvCd")), normalize_text(row.get("admissionYear")))
        for row in office_targets
        if normalize_text(row.get("unvCd")) and normalize_text(row.get("admissionYear"))
    }
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_crawler_worklist_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in inputs
            if path.exists()
        ],
        "officeCollectionTargets": {
            "total": len(office_targets),
            "uniqueUniversityYearGroups": len(unique_groups),
            "uniqueUniversities": len({unv_cd for unv_cd, _ in unique_groups}),
        },
        "crawlerWorklist": {
            "total": len(worklist),
            "p0": sum(1 for row in worklist if row.get("priorityTier") == "p0"),
            "targetCountSum": sum(int_or_none(row.get("targetCount")) or 0 for row in worklist),
            "gapCountSum": sum(int_or_none(row.get("gapCountSum")) or 0 for row in worklist),
        },
        "linkedCrawlerData": {
            "homepageManifestRows": sum(int_or_none(row.get("linkedHomepageManifestRows")) or 0 for row in worklist),
            "linkCandidateRows": sum(int_or_none(row.get("linkedLinkCandidateRows")) or 0 for row in worklist),
            "linkArtifactRows": sum(int_or_none(row.get("linkedLinkArtifactRows")) or 0 for row in worklist),
            "attachmentCandidateRows": sum(int_or_none(row.get("linkedAttachmentCandidateRows")) or 0 for row in worklist),
            "relatedDetailCandidateRows": sum(int_or_none(row.get("linkedRelatedDetailCandidateRows")) or 0 for row in worklist),
            "attachmentArtifactRows": sum(int_or_none(row.get("linkedAttachmentArtifactRows")) or 0 for row in worklist),
        },
        "byCrawlerPattern": counter_rows(Counter(str(row.get("crawlerPattern")) for row in worklist), 40),
        "byRecommendedCrawlerAction": counter_rows(Counter(str(row.get("recommendedCrawlerAction")) for row in worklist), 40),
        "byPipelineStage": counter_rows(Counter(str(row.get("pipelineStage")) for row in worklist), 30),
        "byExistingFetchStatus": counter_rows(Counter(str(row.get("existingFetchStatus")) for row in worklist), 30),
        "byCollectionRoute": counter_rows(Counter(str(row.get("collectionRoute")) for row in worklist), 30),
        "topSourceHostnamesByTargetCount": top_by_sum(worklist, "sourceHostname", "targetCount", 30),
        "targetCountByAdmissionYear": dict(
            sorted(
                Counter(str(row.get("admissionYear") or "") for row in office_targets).items(),
                key=lambda item: int_or_none(item[0]) or 9999,
            )
        ),
        "notes": [
            "Worklist rows group p0 university-admission-office collection targets by host, route, parser pattern, and path family.",
            "Linked crawler data counts are deduplicated within each worklist row and are intended to expose the next pipeline bottleneck.",
            "Helper/application tool URLs are excluded from crawler worklist source fields.",
        ],
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "crawlerWorklistId",
        "artifactType",
        "priorityTier",
        "crawlerPriorityScore",
        "pipelineStage",
        "crawlerPattern",
        "recommendedCrawlerAction",
        "sourceHostname",
        "pathFamily",
        "collectionRoute",
        "existingFetchStatus",
        "sourceRole",
        "sourceFileExtension",
        "targetCount",
        "gapCountSum",
        "universityCount",
        "universityYearGroupCount",
        "admissionYears",
        "missingFlags",
        "targetEntities",
        "recommendedActions",
        "expectedAvailabilityValues",
        "sampleSourceUrls",
        "sampleUnvCds",
        "sampleUniversityNames",
        "sampleCollectionTargetIds",
        "linkedHomepageManifestRows",
        "linkedLinkCandidateRows",
        "linkedLinkArtifactRows",
        "linkedAttachmentCandidateRows",
        "linkedRelatedDetailCandidateRows",
        "linkedAttachmentArtifactRows",
        "sampleLinkedRawPaths",
        "operatorNextStep",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def split_joined(value: Any) -> list[str]:
    return [part for part in normalize_text(value).split("|") if part]


SOURCE_GUARD_FIELDS = (
    "attachmentUrl",
    "canonicalAttachmentUrl",
    "finalHomepageUrl",
    "finalUrl",
    "rawPath",
    "resolvedUrl",
    "sourceCandidateUrl",
    "sourceHomepageUrl",
    "sourceUrl",
)


def row_has_blocked_helper_source(row: dict[str, Any]) -> bool:
    return any(
        BLOCKED_HELPER_SOURCE_PATTERN.search(normalize_text(row.get(field_name)))
        for field_name in SOURCE_GUARD_FIELDS
    )


def join_sorted(values: set[str], numeric: bool = False) -> str:
    if numeric:
        return "|".join(sorted(values, key=lambda value: int_or_none(value) or 9999))
    return "|".join(sorted(values))


def join_sample(values: set[str], limit: int) -> str:
    return "|".join(sorted(values)[:limit])


def join_counter_keys(counter: Counter[str]) -> str:
    return "|".join(value for value, _ in counter.most_common())


def canonical_url(value: Any) -> str:
    url = normalize_text(value)
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}{query}"


def source_hostname(row: dict[str, str]) -> str:
    host = normalize_text(row.get("sourceHostname"))
    if host:
        return host.lower()
    parsed = urlparse(normalize_text(row.get("sourceUrl")))
    return parsed.netloc.lower()


def source_file_extension(row: dict[str, str]) -> str:
    ext = normalize_text(row.get("sourceFileExtension")).lower().lstrip(".")
    if ext:
        return ext
    path = urlparse(normalize_text(row.get("sourceUrl"))).path
    if "." not in path:
        return ""
    return path.rsplit(".", 1)[-1].lower()


def path_family(value: Any) -> str:
    parsed = urlparse(normalize_text(value))
    path = parsed.path.strip("/")
    if not path:
        return "/"
    parts = [part for part in path.split("/") if part]
    if len(parts) == 1:
        return f"/{parts[0]}"
    if len(parts) == 2:
        return f"/{parts[0]}/{parts[1]}"
    return f"/{parts[0]}/{parts[1]}/{parts[2]}"


def row_key(row: dict[str, Any]) -> str:
    for field in ["sha256", "rawPath", "detailRawPath"]:
        value = normalize_text(row.get(field))
        if value:
            return value
    parts = [
        normalize_text(row.get("year")),
        normalize_text(row.get("unvCd")),
        normalize_text(row.get("sourceLinkRole")),
        normalize_text(row.get("sourceCandidateUrl")),
        normalize_text(row.get("resolvedUrl") or row.get("attachmentUrl") or row.get("finalUrl")),
        normalize_text(row.get("linkText") or row.get("sourceLinkText")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def priority_sort(value: Any) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(normalize_text(value), 9)


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def top_by_sum(rows: list[dict[str, Any]], key_field: str, value_field: str, limit: int) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        counter[str(row.get(key_field) or "")] += int_or_none(row.get(value_field)) or 0
    return counter_rows(counter, limit)


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
