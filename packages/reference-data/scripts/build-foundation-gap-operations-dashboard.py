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
DEFAULT_GAP_ACTION_QUEUE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_action_queue.csv"
)
DEFAULT_GAP_SOURCE_CANDIDATES = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_source_candidates.csv"
)
DEFAULT_GAP_COLLECTION_TARGETS = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_collection_targets.csv"
)
DEFAULT_GAP_VISUAL_REVIEW_QUEUE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_visual_review_queue.csv"
)
DEFAULT_GAP_ADIGA_PARSER_REVIEW_QUEUE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_adiga_parser_review_queue.csv"
)
DEFAULT_HOMEPAGE_LINK_CANDIDATE_SUMMARY = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_gap_homepage_link_candidates_summary.json"
)
DEFAULT_COLLECTION_LINK_CANDIDATE_SUMMARY = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_gap_collection_link_candidates_20260613_summary.json"
)
DEFAULT_HOMEPAGE_LINK_CANDIDATES = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_gap_homepage_link_candidates.csv"
)
DEFAULT_COLLECTION_LINK_CANDIDATES = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_gap_collection_link_candidates_20260613.csv"
)

OUTPUT_JSONL = "foundation_gap_operations_dashboard.jsonl"
OUTPUT_CSV = "foundation_gap_operations_dashboard.csv"
OUTPUT_SUMMARY = "foundation_gap_operations_dashboard_summary.json"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    gap_path = resolve(repo_root, args.gap_action_queue)
    source_path = resolve(repo_root, args.gap_source_candidates)
    targets_path = resolve(repo_root, args.gap_collection_targets)
    visual_path = resolve(repo_root, args.gap_visual_review_queue)
    adiga_parser_review_path = resolve(repo_root, args.gap_adiga_parser_review_queue)
    homepage_link_summary_path = resolve(repo_root, args.homepage_link_candidate_summary)
    collection_link_summary_path = resolve(repo_root, args.collection_link_candidate_summary)
    homepage_link_candidates_path = resolve(repo_root, args.homepage_link_candidates)
    collection_link_candidates_path = resolve(repo_root, args.collection_link_candidates)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    gap_rows = read_csv(gap_path)
    source_rows = read_csv(source_path)
    target_rows = read_csv(targets_path)
    visual_rows = read_csv(visual_path)
    adiga_parser_review_rows = read_csv(adiga_parser_review_path)
    collection_state = {
        "homepage_link_candidates_remaining": summary_count(
            read_json(homepage_link_summary_path), "candidateRows", "total"
        ),
        "collection_link_candidates_remaining": int_or_none(
            read_json(collection_link_summary_path).get("selectedRows")
        )
        or 0,
        "homepage_link_candidate_groups": candidate_groups(
            read_csv(homepage_link_candidates_path)
        ),
        "collection_link_candidate_target_ids": candidate_target_ids(
            read_csv(collection_link_candidates_path)
        ),
    }

    dashboard_rows = build_dashboard(
        gap_rows,
        source_rows,
        target_rows,
        visual_rows,
        adiga_parser_review_rows,
        collection_state,
    )
    dashboard_rows.sort(
        key=lambda row: (
            priority_sort(row.get("priorityTier")),
            -int_or_none(row.get("operationPriorityScore") or 0),
            stage_sort(row.get("nextBestStage")),
            str(row.get("universityName") or ""),
            int_or_large(row.get("admissionYear")),
            str(row.get("missingFlag") or ""),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, dashboard_rows)
    write_csv(foundation_dir / OUTPUT_CSV, dashboard_rows)
    summary = summarize(
        repo_root=repo_root,
        inputs=[
            gap_path,
            source_path,
            targets_path,
            visual_path,
            adiga_parser_review_path,
            homepage_link_summary_path,
            collection_link_summary_path,
            homepage_link_candidates_path,
            collection_link_candidates_path,
        ],
        gap_rows=gap_rows,
        source_rows=source_rows,
        target_rows=target_rows,
        visual_rows=visual_rows,
        adiga_parser_review_rows=adiga_parser_review_rows,
        collection_state=collection_state,
        dashboard_rows=dashboard_rows,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap operations dashboard complete. "
        f"gapActions={len(gap_rows)} rows={len(dashboard_rows)} "
        f"sourceReview={summary['byNextBestStageCounts'].get('review_existing_source_candidate', 0)} "
        f"visualReview={summary['byNextBestStageCounts'].get('review_visual_or_ocr_source', 0)} "
        f"collection={summary['byNextBestStageCounts'].get('run_or_repair_collection', 0)} "
        f"waitRelease={summary['byNextBestStageCounts'].get('wait_for_public_release', 0)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--gap-action-queue", default=DEFAULT_GAP_ACTION_QUEUE)
    parser.add_argument("--gap-source-candidates", default=DEFAULT_GAP_SOURCE_CANDIDATES)
    parser.add_argument("--gap-collection-targets", default=DEFAULT_GAP_COLLECTION_TARGETS)
    parser.add_argument("--gap-visual-review-queue", default=DEFAULT_GAP_VISUAL_REVIEW_QUEUE)
    parser.add_argument("--gap-adiga-parser-review-queue", default=DEFAULT_GAP_ADIGA_PARSER_REVIEW_QUEUE)
    parser.add_argument("--homepage-link-candidate-summary", default=DEFAULT_HOMEPAGE_LINK_CANDIDATE_SUMMARY)
    parser.add_argument("--collection-link-candidate-summary", default=DEFAULT_COLLECTION_LINK_CANDIDATE_SUMMARY)
    parser.add_argument("--homepage-link-candidates", default=DEFAULT_HOMEPAGE_LINK_CANDIDATES)
    parser.add_argument("--collection-link-candidates", default=DEFAULT_COLLECTION_LINK_CANDIDATES)
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


def build_dashboard(
    gap_rows: list[dict[str, str]],
    source_rows: list[dict[str, str]],
    target_rows: list[dict[str, str]],
    visual_rows: list[dict[str, str]],
    adiga_parser_review_rows: list[dict[str, str]],
    collection_state: dict[str, Any],
) -> list[dict[str, Any]]:
    adiga_review_by_target = {
        normalize_text(row.get("collectionTargetId")): row
        for row in adiga_parser_review_rows
        if normalize_text(row.get("collectionTargetId"))
    }
    sources_by_gap: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        sources_by_gap[normalize_text(row.get("gapActionId"))].append(row)

    gap_by_id = {
        normalize_text(row.get("gapActionId")): row
        for row in gap_rows
        if normalize_text(row.get("gapActionId"))
    }
    targets_by_gap: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in target_rows:
        for gap_id in split_joined(row.get("gapActionIds")):
            gap = gap_by_id.get(gap_id, {})
            if not is_actionable_collection_target(row, gap, adiga_review_by_target, collection_state):
                continue
            targets_by_gap[gap_id].append(row)

    visual_by_unv_year: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in visual_rows:
        visual_by_unv_year[(normalize_text(row.get("unvCd")), normalize_text(row.get("admissionYear")))].append(row)

    dashboard: list[dict[str, Any]] = []
    for gap in gap_rows:
        gap_id = normalize_text(gap.get("gapActionId"))
        sources = sources_by_gap.get(gap_id, [])
        targets = targets_by_gap.get(gap_id, [])
        visuals = relevant_visual_rows(
            gap,
            visual_by_unv_year.get((normalize_text(gap.get("unvCd")), normalize_text(gap.get("admissionYear"))), []),
        )
        dashboard.append(make_dashboard_row(gap, sources, targets, visuals))
    return dashboard


def candidate_groups(rows: list[dict[str, str]]) -> set[tuple[str, str]]:
    groups: set[tuple[str, str]] = set()
    for row in rows:
        unv_cd = normalize_text(row.get("unvCd"))
        year = normalize_text(row.get("year") or row.get("admissionYear"))
        if unv_cd and year:
            groups.add((unv_cd, year))
    return groups


def candidate_target_ids(rows: list[dict[str, str]]) -> set[str]:
    return {
        normalize_text(row.get("collectionTargetId"))
        for row in rows
        if normalize_text(row.get("collectionTargetId"))
    }


ACTIONABLE_ADIGA_PARSER_BUCKETS = {
    "csat_outcome_table_parser_repair",
    "keyword_signal_no_csat_table_parser_review",
    "csat_rule_table_review",
    "csat_outcome_candidates_available_recheck_gap_mapping",
    "missing_adiga_manifest_refetch",
    "adiga_fetch_failed_refetch",
}


def is_actionable_collection_target(
    target: dict[str, str],
    gap: dict[str, str],
    adiga_review_by_target: dict[str, dict[str, str]],
    collection_state: dict[str, Any],
) -> bool:
    route = normalize_text(target.get("collectionRoute"))
    status = normalize_text(target.get("existingFetchStatus"))
    unv_year = (normalize_text(target.get("unvCd")), normalize_text(target.get("admissionYear")))
    if route == "admission_homepage" and status == "already_fetched_needs_link_parser_review":
        # The fetched homepage is only the seed page. Detail/attachment candidates
        # are emitted by the homepage-link candidate builder; count this route only
        # when that builder produced a current candidate for the same university-year.
        return unv_year in collection_state.get("homepage_link_candidate_groups", set())
    if route == "admission_office_deep_link_discovery" and status == "no_matching_link_candidate":
        return unv_year in collection_state.get("homepage_link_candidate_groups", set())
    if (
        status == "link_candidate_discovered_needs_detail_or_attachment_crawl"
        and route
        in {
            "admission_office_guide_or_notice",
            "admission_office_link_candidate",
            "admission_office_result_board_or_file",
        }
    ):
        return normalize_text(target.get("collectionTargetId")) in collection_state.get(
            "collection_link_candidate_target_ids",
            set(),
        )
    if route != "adiga_selection_detail":
        return True
    review = adiga_review_by_target.get(normalize_text(target.get("collectionTargetId")))
    if not review:
        return True
    bucket = normalize_text(review.get("parserReviewBucket"))
    if bucket not in ACTIONABLE_ADIGA_PARSER_BUCKETS:
        return False
    return adiga_parser_bucket_can_resolve_gap(bucket, gap, review)


def adiga_parser_bucket_can_resolve_gap(
    bucket: str,
    gap: dict[str, str],
    review: dict[str, str],
) -> bool:
    if bucket in {"missing_adiga_manifest_refetch", "adiga_fetch_failed_refetch"}:
        return True

    target_entity = normalize_text(gap.get("targetEntity"))
    missing_flag = normalize_text(gap.get("missingFlag"))
    if bucket == "csat_outcome_candidates_available_recheck_gap_mapping":
        if target_entity != "HistoricalOutcome" and missing_flag not in {
            "missing_historical_outcomes",
            "missing_outcome_scores",
            "missing_quota_competition",
        }:
            return False
        if missing_flag == "missing_outcome_scores":
            return (int_or_none(review.get("csatOutcomeScoreCandidateRows")) or 0) > 0
        if missing_flag == "missing_quota_competition":
            return (int_or_none(review.get("csatOutcomeQuotaCompetitionRows")) or 0) > 0
        return (int_or_none(review.get("csatOutcomeCandidateRows")) or 0) > 0
    if bucket == "keyword_signal_no_csat_table_parser_review":
        if (int_or_none(review.get("csatOutcomeTables")) or 0) == 0 and (
            int_or_none(review.get("csatOutcomeCandidateRows")) or 0
        ) == 0:
            return False
        if target_entity != "HistoricalOutcome" and missing_flag not in {
            "missing_historical_outcomes",
            "missing_outcome_scores",
            "missing_quota_competition",
        }:
            return False
        if missing_flag == "missing_outcome_scores":
            return (int_or_none(review.get("csatOutcomeScoreCandidateRows")) or 0) > 0
        if missing_flag == "missing_quota_competition":
            return (int_or_none(review.get("csatOutcomeQuotaCompetitionRows")) or 0) > 0
        return (int_or_none(review.get("csatOutcomeCandidateRows")) or 0) > 0
    if bucket == "csat_outcome_table_parser_repair":
        return target_entity == "HistoricalOutcome" or missing_flag in {
            "missing_historical_outcomes",
            "missing_outcome_scores",
            "missing_quota_competition",
        }
    if bucket == "csat_rule_table_review":
        return target_entity == "AdmissionRule" and missing_flag == "missing_csat_rule_draft"
    return True


def relevant_visual_rows(gap: dict[str, str], visual_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    missing_flag = normalize_text(gap.get("missingFlag"))
    target_entity = normalize_text(gap.get("targetEntity"))
    result: list[dict[str, str]] = []
    for row in visual_rows:
        missing_flags = set(split_joined(row.get("missingFlags")))
        targets = set(split_joined(row.get("targetEntities"))) | set(split_joined(row.get("imageEvidenceTargets")))
        if missing_flag in missing_flags or target_entity in targets:
            result.append(row)
    return result


def make_dashboard_row(
    gap: dict[str, str],
    sources: list[dict[str, str]],
    targets: list[dict[str, str]],
    visuals: list[dict[str, str]],
) -> dict[str, Any]:
    available_sources = [row for row in sources if row.get("candidateStatus") == "source_candidate_available"]
    collection_required = [row for row in sources if row.get("candidateStatus") == "source_collection_required"]
    source_count = len(available_sources)
    target_count = len(targets)
    visual_count = len(visuals)
    next_stage = next_best_stage(gap, source_count, target_count, visual_count)
    priority = operation_priority(gap, source_count, target_count, visual_count, next_stage)
    top_source = top_source_candidate(available_sources)
    top_visual = top_visual_candidate(visuals)
    top_target = top_collection_target(targets)
    target_statuses = Counter(normalize_text(row.get("existingFetchStatus")) for row in targets)
    collection_routes = Counter(normalize_text(row.get("collectionRoute")) for row in targets)

    return {
        "gapOperationId": deterministic_uuid(
            f"gap-operation:{normalize_text(gap.get('gapActionId'))}:{next_stage}"
        ),
        "artifactType": "foundation_gap_operation_dashboard_item",
        "gapActionId": normalize_text(gap.get("gapActionId")),
        "priorityTier": normalize_text(gap.get("priorityTier")),
        "operationPriorityScore": priority,
        "nextBestStage": next_stage,
        "nextBestAction": next_best_action(next_stage, gap, source_count, target_count, visual_count),
        "unvCd": normalize_text(gap.get("unvCd")),
        "universityName": normalize_text(gap.get("universityName")),
        "admissionYear": int_or_none(gap.get("admissionYear")) or normalize_text(gap.get("admissionYear")),
        "coverageTier": normalize_text(gap.get("coverageTier")),
        "coverageScore": int_or_none(gap.get("coverageScore")) or 0,
        "missingFlag": normalize_text(gap.get("missingFlag")),
        "gapCategory": normalize_text(gap.get("gapCategory")),
        "targetEntity": normalize_text(gap.get("targetEntity")),
        "recommendedAction": normalize_text(gap.get("recommendedAction")),
        "expectedAvailability": normalize_text(gap.get("expectedAvailability")),
        "blockingReason": normalize_text(gap.get("blockingReason")),
        "sourceCandidateRows": source_count,
        "sourceCollectionRequiredRows": len(collection_required),
        "collectionTargetRows": target_count,
        "visualReviewRows": visual_count,
        "topSourceArtifact": normalize_text(top_source.get("sourceArtifact")),
        "topSourceProvider": normalize_text(top_source.get("sourceProvider")),
        "topSourceMatchType": normalize_text(top_source.get("candidateMatchType")),
        "topSourceReviewPriorityScore": int_or_none(top_source.get("sourceReviewPriorityScore")) or 0,
        "topSourceUrls": normalize_text(top_source.get("sourceUrls"))[:800],
        "topSourcePaths": normalize_text(top_source.get("sourcePaths") or top_source.get("rawPaths"))[:800],
        "topVisualReviewBucket": normalize_text(top_visual.get("reviewBucket")),
        "topVisualReviewPriorityScore": int_or_none(top_visual.get("visualReviewPriorityScore")) or 0,
        "topVisualPageImagePath": normalize_text(top_visual.get("pageImagePath")),
        "topVisualOcrSourcePath": normalize_text(top_visual.get("ocrSourcePath")),
        "topVisualPreview": normalize_text(top_visual.get("ocrTextPreview"))[:500],
        "collectionRoutes": counter_text(collection_routes),
        "collectionExistingFetchStatuses": counter_text(target_statuses),
        "topCollectionRoute": normalize_text(top_target.get("collectionRoute")),
        "topCollectionStatus": normalize_text(top_target.get("existingFetchStatus")),
        "topCollectionUrl": normalize_text(top_target.get("sourceUrl"))[:800],
        "operatorNextStep": operator_next_step(next_stage, gap, top_source, top_visual, top_target),
    }


def next_best_stage(
    gap: dict[str, str],
    source_count: int,
    target_count: int,
    visual_count: int,
) -> str:
    if source_count > 0:
        return "review_existing_source_candidate"
    if visual_count > 0:
        return "review_visual_or_ocr_source"
    if target_count > 0:
        return "run_or_repair_collection"
    if normalize_text(gap.get("expectedAvailability")) == "likely_not_public_until_after_cycle":
        return "wait_for_public_release"
    if normalize_text(gap.get("targetEntity")) == "University":
        return "verify_university_scope"
    return "manual_source_discovery"


def next_best_action(
    next_stage: str,
    gap: dict[str, str],
    source_count: int,
    target_count: int,
    visual_count: int,
) -> str:
    if next_stage == "review_existing_source_candidate":
        return f"Review {source_count} existing source candidate(s) and promote or mark blocker."
    if next_stage == "review_visual_or_ocr_source":
        return f"Review {visual_count} visual/OCR source task(s), then extract or discard structured candidates."
    if next_stage == "run_or_repair_collection":
        return f"Run or repair {target_count} collection/parser target(s) before source review."
    if next_stage == "wait_for_public_release":
        return "Monitor release timing; collect after the public outcome data is expected to appear."
    if next_stage == "verify_university_scope":
        return "Verify whether the institution belongs in the Pacer university universe for this admission year."
    return "Perform manual public-source discovery or add a crawler/parser route."


def operation_priority(
    gap: dict[str, str],
    source_count: int,
    target_count: int,
    visual_count: int,
    next_stage: str,
) -> int:
    score = int_or_none(gap.get("actionPriorityScore")) or 0
    score += {
        "review_existing_source_candidate": 45,
        "review_visual_or_ocr_source": 38,
        "run_or_repair_collection": 25,
        "wait_for_public_release": 12,
        "verify_university_scope": 10,
        "manual_source_discovery": 5,
    }.get(next_stage, 0)
    score += min(30, source_count * 4)
    score += min(25, visual_count * 3)
    score += min(20, target_count * 2)
    if normalize_text(gap.get("targetEntity")) in {"AdmissionRule", "HistoricalOutcome"}:
        score += 12
    if normalize_text(gap.get("expectedAvailability")) == "should_be_public_or_parse_gap":
        score += 10
    return score


def top_source_candidate(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        return {}
    return sorted(
        rows,
        key=lambda row: (
            -int_or_none(row.get("candidateMatchScore") or 0),
            -int_or_none(row.get("sourceReviewPriorityScore") or 0),
            int_or_none(row.get("candidateRank")) or 999,
        ),
    )[0]


def top_visual_candidate(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        return {}
    return sorted(
        rows,
        key=lambda row: (
            -int_or_none(row.get("visualReviewPriorityScore") or 0),
            str(row.get("reviewBucket") or ""),
        ),
    )[0]


def top_collection_target(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        return {}
    return sorted(
        rows,
        key=lambda row: (
            fetch_status_sort(row.get("existingFetchStatus")),
            -int_or_none(row.get("collectionPriorityScore") or 0),
            str(row.get("collectionRoute") or ""),
        ),
    )[0]


def fetch_status_sort(value: Any) -> int:
    text = normalize_text(value)
    return {
        "already_fetched_needs_parser_review": 0,
        "already_fetched_needs_link_parser_review": 1,
        "link_candidate_discovered_needs_detail_or_attachment_crawl": 2,
        "fetch_required": 3,
        "homepage_fetch_failed_retry_or_manual": 4,
        "no_matching_link_candidate": 5,
    }.get(text, 9)


def operator_next_step(
    next_stage: str,
    gap: dict[str, str],
    top_source: dict[str, str],
    top_visual: dict[str, str],
    top_target: dict[str, str],
) -> str:
    recommended = normalize_text(gap.get("recommendedAction"))
    if next_stage == "review_existing_source_candidate":
        artifact = normalize_text(top_source.get("sourceArtifact"))
        return f"{recommended}: inspect {artifact or 'source candidate'} and promote verified structured data or record blocker."
    if next_stage == "review_visual_or_ocr_source":
        bucket = normalize_text(top_visual.get("reviewBucket"))
        return f"{recommended}: inspect visual bucket {bucket or 'visual_review'} and extract table values only after source verification."
    if next_stage == "run_or_repair_collection":
        route = normalize_text(top_target.get("collectionRoute"))
        status = normalize_text(top_target.get("existingFetchStatus"))
        return f"{recommended}: run/repair collection route={route or 'unknown'} status={status or 'unknown'}."
    if next_stage == "wait_for_public_release":
        return f"{recommended}: mark as release-monitor item; collect after this admission year's public results are released."
    if next_stage == "verify_university_scope":
        return "Verify university scope/institution status before adding or removing this university-year from coverage."
    return f"{recommended}: add public source hint, crawler route, or manual source record."


def summarize(
    repo_root: Path,
    inputs: list[Path],
    gap_rows: list[dict[str, str]],
    source_rows: list[dict[str, str]],
    target_rows: list[dict[str, str]],
    visual_rows: list[dict[str, str]],
    adiga_parser_review_rows: list[dict[str, str]],
    collection_state: dict[str, Any],
    dashboard_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    stage_counter = Counter(str(row.get("nextBestStage") or "") for row in dashboard_rows)
    actionable_adiga_targets = sum(
        1
        for row in adiga_parser_review_rows
        if normalize_text(row.get("parserReviewBucket")) in ACTIONABLE_ADIGA_PARSER_BUCKETS
    )
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_operations_dashboard_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in inputs
            if path.exists()
        ],
        "inputRows": {
            "gapActions": len(gap_rows),
            "gapSourceCandidates": len(source_rows),
            "gapCollectionTargets": len(target_rows),
            "gapVisualReviewQueue": len(visual_rows),
            "gapAdigaParserReviewQueue": len(adiga_parser_review_rows),
            "actionableAdigaParserTargets": actionable_adiga_targets,
            "homepageLinkCandidatesRemaining": collection_state.get("homepage_link_candidates_remaining", 0),
            "collectionLinkCandidatesRemaining": collection_state.get("collection_link_candidates_remaining", 0),
        },
        "operationRows": {
            "total": len(dashboard_rows),
            "p0": sum(1 for row in dashboard_rows if row.get("priorityTier") == "p0"),
        },
        "byNextBestStageCounts": dict(stage_counter),
        "byNextBestStage": counter_rows(stage_counter, 20),
        "byTargetEntity": counter_rows(Counter(str(row.get("targetEntity") or "") for row in dashboard_rows), 20),
        "byMissingFlag": counter_rows(Counter(str(row.get("missingFlag") or "") for row in dashboard_rows), 30),
        "byAdmissionYear": dict(sorted(Counter(str(row.get("admissionYear") or "") for row in dashboard_rows).items())),
        "byCoverageTier": counter_rows(Counter(str(row.get("coverageTier") or "") for row in dashboard_rows), 20),
        "notes": [
            "This dashboard merges gap actions with source candidates, visual review tasks, and collection targets.",
            "Rows are operational next-step guidance only; they do not prove the gap has been resolved.",
            "Source review is prioritized ahead of visual review, then collection repair, then manual discovery.",
            "Collection targets whose generated crawl candidate queues are exhausted are routed to manual discovery instead of run_or_repair_collection.",
        ],
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def summary_count(summary: dict[str, Any], section: str, key: str) -> int:
    value = summary.get(section)
    if not isinstance(value, dict):
        return 0
    return int_or_none(value.get(key)) or 0


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "gapOperationId",
        "artifactType",
        "gapActionId",
        "priorityTier",
        "operationPriorityScore",
        "nextBestStage",
        "nextBestAction",
        "unvCd",
        "universityName",
        "admissionYear",
        "coverageTier",
        "coverageScore",
        "missingFlag",
        "gapCategory",
        "targetEntity",
        "recommendedAction",
        "expectedAvailability",
        "blockingReason",
        "sourceCandidateRows",
        "sourceCollectionRequiredRows",
        "collectionTargetRows",
        "visualReviewRows",
        "topSourceArtifact",
        "topSourceProvider",
        "topSourceMatchType",
        "topSourceReviewPriorityScore",
        "topSourceUrls",
        "topSourcePaths",
        "topVisualReviewBucket",
        "topVisualReviewPriorityScore",
        "topVisualPageImagePath",
        "topVisualOcrSourcePath",
        "topVisualPreview",
        "collectionRoutes",
        "collectionExistingFetchStatuses",
        "topCollectionRoute",
        "topCollectionStatus",
        "topCollectionUrl",
        "operatorNextStep",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [part for part in re.split(r"[|,;]", text) if part]


def counter_text(counter: Counter[str]) -> str:
    return "|".join(f"{key}:{count}" for key, count in counter.most_common() if key)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def int_or_large(value: Any) -> int:
    parsed = int_or_none(value)
    return parsed if parsed is not None else 999999


def priority_sort(value: Any) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(normalize_text(value), 9)


def stage_sort(value: Any) -> int:
    return {
        "review_existing_source_candidate": 0,
        "review_visual_or_ocr_source": 1,
        "run_or_repair_collection": 2,
        "verify_university_scope": 3,
        "manual_source_discovery": 4,
        "wait_for_public_release": 5,
    }.get(normalize_text(value), 9)


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


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
