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
DEFAULT_GAP_SOURCE_CANDIDATES = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_source_candidates.csv"
)
DEFAULT_OFFICIAL_SITES = (
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_official_site_candidates.csv"
)
DEFAULT_ADIGA_PUBLIC_DIR = "packages/reference-data/data/public/adiga"
DEFAULT_UNIVERSITY_SITE_DIR = "packages/reference-data/data/public/university-admission-sites"

OUTPUT_JSONL = "foundation_gap_collection_targets.jsonl"
OUTPUT_CSV = "foundation_gap_collection_targets.csv"
OUTPUT_SUMMARY = "foundation_gap_collection_targets_summary.json"

ADIGA_BASE_URL = "https://www.adiga.kr/ucp/uvt/uni/univDetailSelection.do"
ADIGA_MENU_ID = "PCUVTINF2000"
RECENT_YEARS = [2021, 2022, 2023, 2024, 2025, 2026, 2027]
MAX_LINK_TARGETS_PER_GROUP = 5
ADIGA_COMPATIBLE_MISSING_FLAGS = {
    "missing_admission_units",
    "missing_historical_outcomes",
    "missing_outcome_scores",
    "missing_quota_competition",
    "missing_csat_rule_draft",
    "missing_recruitment_quota_draft",
    "missing_screening_method_draft",
    "missing_school_record_rule_draft",
    "missing_eligibility_rule_draft",
}
BLOCKED_HELPER_SOURCE_PATTERN = re.compile(
    r"jinhak|jinhakapply|uway|uwayapply|telegr|01consulting|nesin|고속성장|진학사|유웨이",
    re.I,
)
SOURCE_GUARD_FIELDS = (
    "normalizedUrl",
    "rawUrl",
    "finalUrl",
    "sourceHomepageUrl",
    "finalHomepageUrl",
    "resolvedUrl",
    "sourceUrl",
    "sourceHostname",
    "hostname",
    "rawPath",
)
OFFICIAL_SITE_OVERRIDES = (
    {
        "provider": "manual_official_site_override",
        "artifactType": "adiga_official_site_candidate",
        "year": "2027",
        "unvCd": "0000092",
        "universityName": "세한대학교",
        "campus": "본교",
        "linkType": "admission_homepage",
        "label": "입학안내",
        "rawUrl": "https://apply.sehan.ac.kr/apply/",
        "normalizedUrl": "https://apply.sehan.ac.kr/apply/",
        "hostname": "apply.sehan.ac.kr",
        "sourceUrl": "https://www.sehan.ac.kr/sehan/index.do",
        "rawPath": "",
        "confidence": "manual_verified_official_homepage_link_20260612",
        "status": "parsed_candidate",
        "extractedAt": "2026-06-12T13:08:59+00:00",
    },
)
OFFICIAL_SITE_OVERRIDE_KEYS = {("0000092", "2027")}

LINK_ROLES_BY_MISSING_FLAG = {
    "missing_historical_outcomes": {"admission_result", "competition_rate"},
    "missing_outcome_scores": {"admission_result", "competition_rate"},
    "missing_quota_competition": {"admission_result", "competition_rate"},
    "missing_admission_units": {"regular_admission_guide", "recruitment_notice", "admission_related"},
    "missing_csat_rule_draft": {"regular_admission_guide", "recruitment_notice"},
    "missing_recruitment_quota_draft": {"regular_admission_guide", "recruitment_notice"},
    "missing_screening_method_draft": {"regular_admission_guide", "recruitment_notice"},
    "missing_school_record_rule_draft": {"regular_admission_guide", "recruitment_notice"},
    "missing_eligibility_rule_draft": {"regular_admission_guide", "recruitment_notice"},
    "missing_schedule_draft": {"regular_admission_guide", "recruitment_notice", "admission_related"},
    "missing_admission_office_detected_year_evidence": {
        "regular_admission_guide",
        "admission_result",
        "competition_rate",
        "recruitment_notice",
        "admission_related",
    },
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    gap_source_path = resolve(repo_root, args.gap_source_candidates)
    official_sites_path = resolve(repo_root, args.official_sites)
    adiga_public_dir = resolve(repo_root, args.adiga_public_dir)
    university_site_dir = resolve(repo_root, args.university_site_dir)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    no_source_rows = [
        row
        for row in read_csv(gap_source_path)
        if normalize_text(row.get("candidateStatus")) == "source_collection_required"
    ]
    official_site_rows = [
        row
        for row in read_csv(official_sites_path)
        if not row_has_blocked_helper_source(row)
    ]
    adiga_manifests = load_adiga_manifests(adiga_public_dir)
    link_candidates = load_link_candidates(university_site_dir)
    homepage_manifests = load_homepage_manifests(university_site_dir)

    targets = build_targets(
        no_source_rows=no_source_rows,
        official_site_rows=official_site_rows,
        adiga_manifests=adiga_manifests,
        link_candidates=link_candidates,
        homepage_manifests=homepage_manifests,
    )
    targets.sort(
        key=lambda row: (
            priority_sort(row.get("priorityTier")),
            -int_or_none(row.get("collectionPriorityScore") or 0),
            str(row.get("universityName") or ""),
            int_or_none(row.get("admissionYear")) or 9999,
            str(row.get("collectionRoute") or ""),
            str(row.get("sourceRole") or ""),
            str(row.get("sourceUrl") or ""),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, targets)
    write_csv(foundation_dir / OUTPUT_CSV, targets)
    summary = summarize(
        repo_root=repo_root,
        inputs=[
            gap_source_path,
            official_sites_path,
            *manifest_paths(adiga_public_dir, "adiga_selection_manifest_*.jsonl"),
            *manifest_paths(university_site_dir, "university_admission_link_candidates_*.csv"),
            *manifest_paths(university_site_dir, "university_admission_homepage_manifest_*.jsonl"),
        ],
        no_source_rows=no_source_rows,
        targets=targets,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap collection targets complete. "
        f"noSourceGapActions={len(no_source_rows)} "
        f"universityYearGroups={summary['noSourceGapActions']['uniqueUniversityYearGroups']} "
        f"targets={len(targets)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--gap-source-candidates", default=DEFAULT_GAP_SOURCE_CANDIDATES)
    parser.add_argument("--official-sites", default=DEFAULT_OFFICIAL_SITES)
    parser.add_argument("--adiga-public-dir", default=DEFAULT_ADIGA_PUBLIC_DIR)
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


def build_targets(
    no_source_rows: list[dict[str, str]],
    official_site_rows: list[dict[str, str]],
    adiga_manifests: dict[tuple[str, str], dict[str, Any]],
    link_candidates: dict[tuple[str, str], list[dict[str, str]]],
    homepage_manifests: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    official_by_unv_year = index_official_sites(official_site_rows)
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in no_source_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        year = normalize_text(row.get("admissionYear"))
        if unv_cd and year:
            groups[(unv_cd, year)].append(row)

    targets: list[dict[str, Any]] = []
    for (unv_cd, year), gap_rows in groups.items():
        if has_adiga_compatible_gap(gap_rows):
            targets.append(make_adiga_target(unv_cd, year, gap_rows, adiga_manifests.get((unv_cd, year))))
        homepage = best_official_site(official_by_unv_year, unv_cd, year)
        homepage_manifest = homepage_manifests.get((unv_cd, year))
        targets.append(make_homepage_target(unv_cd, year, gap_rows, homepage, homepage_manifest))

        link_rows = best_link_candidates(link_candidates, unv_cd, year, gap_rows)
        for rank, link_row in enumerate(link_rows, start=1):
            targets.append(make_link_target(unv_cd, year, gap_rows, link_row, rank))

        if not link_rows:
            targets.append(make_link_discovery_target(unv_cd, year, gap_rows, homepage))

    return [target for target in targets if not row_has_blocked_helper_source(target)]


def has_adiga_compatible_gap(gap_rows: list[dict[str, str]]) -> bool:
    return any(
        normalize_text(row.get("missingFlag")) in ADIGA_COMPATIBLE_MISSING_FLAGS
        for row in gap_rows
    )


def make_adiga_target(
    unv_cd: str,
    year: str,
    gap_rows: list[dict[str, str]],
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    source_url = adiga_selection_url(year, unv_cd)
    raw_path = normalize_text((manifest or {}).get("rawPath")) or f".reference-data/raw/adiga/{year}/{unv_cd}/selection.html"
    fetched_status = normalize_text((manifest or {}).get("status")) or "not_in_manifest"
    existing_fetch_status = "already_fetched_needs_parser_review" if fetched_status == "fetched" else "fetch_required"
    return base_target(
        unv_cd=unv_cd,
        year=year,
        gap_rows=gap_rows,
        collection_route="adiga_selection_detail",
        collection_action="reparse_or_refetch_adiga_selection_detail",
        source_provider="adiga",
        source_role="adiga_selection_detail",
        source_url=source_url,
        source_label="Adiga 대학별 평가기준 및 입시결과",
        source_year=year,
        raw_path=raw_path,
        existing_fetch_status=existing_fetch_status,
        source_hint="Adiga 상세 HTML은 이미 fetch된 경우 parser/section extraction 보강 우선",
        operator_next_step=(
            "Inspect Adiga selection.html and extracted tables/images; if raw exists, improve parser before refetch."
        ),
    )


def make_homepage_target(
    unv_cd: str,
    year: str,
    gap_rows: list[dict[str, str]],
    homepage: dict[str, str] | None,
    manifest: dict[str, Any] | None,
) -> dict[str, Any]:
    source_url = normalize_text((homepage or {}).get("normalizedUrl") or (manifest or {}).get("sourceHomepageUrl"))
    existing_fetch_status = "fetch_required"
    raw_path = ""
    if manifest:
        raw_path = normalize_text(manifest.get("rawPath"))
        existing_fetch_status = (
            "already_fetched_needs_link_parser_review"
            if normalize_text(manifest.get("status")) == "fetched"
            else "homepage_fetch_failed_retry_or_manual"
        )
    return base_target(
        unv_cd=unv_cd,
        year=year,
        gap_rows=gap_rows,
        collection_route="admission_homepage",
        collection_action="crawl_or_reparse_admission_homepage",
        source_provider="university-admission-office",
        source_role="admission_homepage",
        source_url=source_url,
        source_label=normalize_text((homepage or {}).get("label")) or "입시홈페이지",
        source_year=normalize_text((homepage or {}).get("year")) or year,
        raw_path=raw_path,
        existing_fetch_status=existing_fetch_status if source_url else "homepage_url_missing",
        source_hint="Adiga 공식 입시홈페이지 후보 기반 root/link discovery",
        operator_next_step=(
            "Fetch or reparse admission homepage links; then run attachment/detail crawlers for matched roles."
        ),
        extra={"sourceHostname": normalize_text((homepage or {}).get("hostname"))},
    )


def make_link_target(
    unv_cd: str,
    year: str,
    gap_rows: list[dict[str, str]],
    link_row: dict[str, str],
    rank: int,
) -> dict[str, Any]:
    route = "admission_office_link_candidate"
    role = normalize_text(link_row.get("linkRole"))
    if role in {"admission_result", "competition_rate"}:
        route = "admission_office_result_board_or_file"
    elif role in {"regular_admission_guide", "recruitment_notice"}:
        route = "admission_office_guide_or_notice"
    return base_target(
        unv_cd=unv_cd,
        year=year,
        gap_rows=gap_rows,
        collection_route=route,
        collection_action="crawl_link_candidate_and_extract_attachments",
        source_provider="university-admission-office",
        source_role=role,
        source_url=normalize_text(link_row.get("resolvedUrl")),
        source_label=normalize_text(link_row.get("linkText")),
        source_year=normalize_text(link_row.get("year")),
        raw_path=normalize_text(link_row.get("rawPath")),
        existing_fetch_status="link_candidate_discovered_needs_detail_or_attachment_crawl",
        source_hint=normalize_text(link_row.get("keywordHits")),
        operator_next_step=(
            "Fetch link/detail page and nested file routes; extract PDF/HWP/XLSX text, snippets, OCR where needed."
        ),
        extra={
            "sourceRank": rank,
            "sourceHostname": normalize_text(link_row.get("hostname")),
            "sourceFileExtension": normalize_text(link_row.get("fileExtension")),
        },
    )


def make_link_discovery_target(
    unv_cd: str,
    year: str,
    gap_rows: list[dict[str, str]],
    homepage: dict[str, str] | None,
) -> dict[str, Any]:
    return base_target(
        unv_cd=unv_cd,
        year=year,
        gap_rows=gap_rows,
        collection_route="admission_office_deep_link_discovery",
        collection_action="discover_board_links_with_rendered_or_manual_crawl",
        source_provider="university-admission-office",
        source_role="deep_link_discovery",
        source_url=normalize_text((homepage or {}).get("normalizedUrl")),
        source_label="입학처 심층 링크 탐색",
        source_year=year,
        raw_path="",
        existing_fetch_status="no_matching_link_candidate",
        source_hint="homepage fetched but relevant board/file link was not identified",
        operator_next_step=(
            "Use rendered crawl or board-specific parser to discover 모집요강/입시결과/일정 links."
        ),
        extra={"sourceHostname": normalize_text((homepage or {}).get("hostname"))},
    )


def base_target(
    *,
    unv_cd: str,
    year: str,
    gap_rows: list[dict[str, str]],
    collection_route: str,
    collection_action: str,
    source_provider: str,
    source_role: str,
    source_url: str,
    source_label: str,
    source_year: str,
    raw_path: str,
    existing_fetch_status: str,
    source_hint: str,
    operator_next_step: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gap_action_ids = sorted({normalize_text(row.get("gapActionId")) for row in gap_rows if row.get("gapActionId")})
    missing_flags = sorted({normalize_text(row.get("missingFlag")) for row in gap_rows if row.get("missingFlag")})
    recommended_actions = sorted(
        {normalize_text(row.get("recommendedAction")) for row in gap_rows if row.get("recommendedAction")}
    )
    target_entities = sorted({normalize_text(row.get("targetEntity")) for row in gap_rows if row.get("targetEntity")})
    priority_tier = collection_priority_tier(gap_rows)
    priority_score = collection_priority(collection_route, missing_flags, gap_rows, existing_fetch_status)
    row = {
        "collectionTargetId": deterministic_uuid(
            f"gap-collection:{unv_cd}:{year}:{collection_route}:{source_role}:{source_url}:{raw_path}"
        ),
        "artifactType": "foundation_gap_collection_target",
        "priorityTier": priority_tier,
        "collectionPriorityScore": priority_score,
        "collectionStatus": "needs_collection_or_parser_review",
        "unvCd": unv_cd,
        "universityName": normalize_text(gap_rows[0].get("universityName")) if gap_rows else "",
        "admissionYear": int_or_none(year) or year,
        "gapCount": len(gap_rows),
        "gapActionIds": join_values(gap_action_ids),
        "missingFlags": join_values(missing_flags),
        "targetEntities": join_values(target_entities),
        "recommendedActions": join_values(recommended_actions),
        "expectedAvailabilityValues": join_values(
            sorted({normalize_text(row.get("expectedAvailability")) for row in gap_rows if row.get("expectedAvailability")})
        ),
        "collectionRoute": collection_route,
        "collectionAction": collection_action,
        "sourceProvider": source_provider,
        "sourceRole": source_role,
        "sourceYear": source_year,
        "sourceUrl": source_url,
        "sourceLabel": source_label,
        "sourceHostname": "",
        "sourceFileExtension": "",
        "sourceRank": "",
        "rawPath": raw_path,
        "existingFetchStatus": existing_fetch_status,
        "sourceHint": source_hint,
        "operatorNextStep": operator_next_step,
    }
    if extra:
        row.update(extra)
    return row


def collection_priority_tier(gap_rows: list[dict[str, str]]) -> str:
    tiers = [normalize_text(row.get("gapPriorityTier") or row.get("priorityTier")) for row in gap_rows]
    tiers = [tier for tier in tiers if tier]
    return min(tiers, key=priority_sort) if tiers else "p0"


def collection_priority(
    collection_route: str,
    missing_flags: list[str],
    gap_rows: list[dict[str, str]],
    existing_fetch_status: str,
) -> int:
    score = 90 + min(70, len(gap_rows) * 8)
    if any(flag in {"missing_historical_outcomes", "missing_outcome_scores", "missing_quota_competition"} for flag in missing_flags):
        score += 35
    if "missing_admission_units" in missing_flags:
        score += 25
    if any(flag.endswith("_rule_draft") for flag in missing_flags):
        score += 20
    if "missing_schedule_draft" in missing_flags:
        score += 14
    if collection_route == "adiga_selection_detail":
        score += 30
    elif collection_route in {"admission_office_result_board_or_file", "admission_office_guide_or_notice"}:
        score += 24
    elif collection_route == "admission_homepage":
        score += 10
    if existing_fetch_status.startswith("already_fetched"):
        score += 12
    if existing_fetch_status in {"no_matching_link_candidate", "homepage_url_missing"}:
        score -= 18
    return score


def best_link_candidates(
    link_candidates: dict[tuple[str, str], list[dict[str, str]]],
    unv_cd: str,
    year: str,
    gap_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    desired_roles = desired_link_roles(gap_rows)
    candidates = [
        row
        for row in link_candidates.get((unv_cd, year), [])
        if not row_has_blocked_helper_source(row)
    ]
    if not candidates and year != "2027":
        candidates = [
            row
            for row in link_candidates.get((unv_cd, "2027"), [])
            if not row_has_blocked_helper_source(row)
        ]
    scored = [
        (score_link_candidate(row, desired_roles), row)
        for row in candidates
        if normalize_text(row.get("resolvedUrl"))
    ]
    scored = [(score, row) for score, row in scored if score > 0]
    scored.sort(key=lambda item: (-item[0], normalize_text(item[1].get("linkText")), normalize_text(item[1].get("resolvedUrl"))))
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for _, row in scored:
        key = normalize_text(row.get("resolvedUrl"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
        if len(deduped) >= MAX_LINK_TARGETS_PER_GROUP:
            break
    return deduped


def desired_link_roles(gap_rows: list[dict[str, str]]) -> set[str]:
    roles: set[str] = set()
    for row in gap_rows:
        roles.update(LINK_ROLES_BY_MISSING_FLAG.get(normalize_text(row.get("missingFlag")), set()))
    return roles


def score_link_candidate(row: dict[str, str], desired_roles: set[str]) -> int:
    role = normalize_text(row.get("linkRole"))
    text = normalize_text(f"{row.get('linkText')} {row.get('keywordHits')} {row.get('resolvedUrl')}")
    score = 0
    if role in desired_roles:
        score += 100
    if role == "admission_result" and re.search(r"입시결과|전형결과|경쟁률|충원|성적", text):
        score += 45
    if role == "regular_admission_guide" and re.search(r"모집요강|정시|수시|전형", text):
        score += 40
    if role == "competition_rate" and re.search(r"경쟁률|지원현황", text):
        score += 35
    if role == "recruitment_notice" and re.search(r"모집|공지|요강", text):
        score += 25
    if normalize_text(row.get("fileExtension")).lower() in {"pdf", "hwp", "hwpx", "xlsx", "xls"}:
        score += 25
    if not desired_roles and role:
        score += 20
    return score


def index_official_sites(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    indexed: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in [*rows, *OFFICIAL_SITE_OVERRIDES]:
        if normalize_text(row.get("linkType")) != "admission_homepage":
            continue
        if normalize_text(row.get("status")) != "parsed_candidate":
            continue
        unv_cd = normalize_text(row.get("unvCd"))
        year = normalize_text(row.get("year"))
        if (unv_cd, year) in OFFICIAL_SITE_OVERRIDE_KEYS and row not in OFFICIAL_SITE_OVERRIDES:
            continue
        if unv_cd and year:
            indexed[(unv_cd, year)].append(row)
    return indexed


def best_official_site(
    indexed: dict[tuple[str, str], list[dict[str, str]]],
    unv_cd: str,
    year: str,
) -> dict[str, str] | None:
    candidates = indexed.get((unv_cd, year)) or indexed.get((unv_cd, "2027")) or []
    if not candidates:
        for recent_year in reversed(RECENT_YEARS):
            candidates = indexed.get((unv_cd, str(recent_year))) or []
            if candidates:
                break
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: (normalize_text(row.get("normalizedUrl")), normalize_text(row.get("rawUrl"))))[0]


def adiga_selection_url(year: str, unv_cd: str) -> str:
    return f"{ADIGA_BASE_URL}?menuId={ADIGA_MENU_ID}&searchSyr={year}&unvCd={unv_cd}"


def load_adiga_manifests(public_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in public_dir.glob("adiga_selection_manifest_*.jsonl"):
        for row in read_jsonl(path):
            unv_cd = normalize_text(row.get("unvCd"))
            year = normalize_text(row.get("year"))
            if unv_cd and year:
                rows[(unv_cd, year)] = row
    return rows


def load_link_candidates(site_dir: Path) -> dict[tuple[str, str], list[dict[str, str]]]:
    rows: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for path in site_dir.glob("university_admission_link_candidates_*.csv"):
        for row in read_csv(path):
            unv_cd = normalize_text(row.get("unvCd"))
            year = normalize_text(row.get("year"))
            if unv_cd and year:
                rows[(unv_cd, year)].append(row)
    return rows


def load_homepage_manifests(site_dir: Path) -> dict[tuple[str, str], dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for path in site_dir.glob("university_admission_homepage_manifest_*.jsonl"):
        for row in read_jsonl(path):
            unv_cd = normalize_text(row.get("unvCd"))
            year = normalize_text(row.get("year"))
            if unv_cd and year:
                rows[(unv_cd, year)] = row
    return rows


def summarize(
    repo_root: Path,
    inputs: list[Path],
    no_source_rows: list[dict[str, str]],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    unique_groups = {(normalize_text(row.get("unvCd")), normalize_text(row.get("admissionYear"))) for row in no_source_rows}
    unique_groups = {(unv_cd, year) for unv_cd, year in unique_groups if unv_cd and year}
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_collection_targets_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in inputs
            if path.exists()
        ],
        "noSourceGapActions": {
            "total": len(no_source_rows),
            "uniqueUniversityYearGroups": len(unique_groups),
            "uniqueUniversities": len({unv_cd for unv_cd, _ in unique_groups}),
        },
        "collectionTargets": {
            "total": len(targets),
            "p0": sum(1 for row in targets if row.get("priorityTier") == "p0"),
        },
        "byCollectionRoute": counter_rows(Counter(str(row.get("collectionRoute")) for row in targets), 30),
        "byExistingFetchStatus": counter_rows(Counter(str(row.get("existingFetchStatus")) for row in targets), 30),
        "byMissingFlags": counter_rows(Counter(str(row.get("missingFlags")) for row in targets), 40),
        "byAdmissionYear": dict(sorted(Counter(str(row.get("admissionYear")) for row in targets).items())),
        "bySourceProvider": counter_rows(Counter(str(row.get("sourceProvider")) for row in targets), 20),
        "notes": [
            "Collection targets are crawler/parser operating targets for p0 gaps that had no existing source candidate.",
            "Adiga detail targets often point to already-fetched raw HTML; those should be parser-review first, not blind refetch.",
            "Admission-office link targets are keyword route candidates and remain unverified until fetched/extracted/reviewed.",
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
        "collectionTargetId",
        "artifactType",
        "priorityTier",
        "collectionPriorityScore",
        "collectionStatus",
        "unvCd",
        "universityName",
        "admissionYear",
        "gapCount",
        "gapActionIds",
        "missingFlags",
        "targetEntities",
        "recommendedActions",
        "expectedAvailabilityValues",
        "collectionRoute",
        "collectionAction",
        "sourceProvider",
        "sourceRole",
        "sourceYear",
        "sourceUrl",
        "sourceLabel",
        "sourceHostname",
        "sourceFileExtension",
        "sourceRank",
        "rawPath",
        "existingFetchStatus",
        "sourceHint",
        "operatorNextStep",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def manifest_paths(base_dir: Path, pattern: str) -> list[Path]:
    return sorted(base_dir.glob(pattern))


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def row_has_blocked_helper_source(row: dict[str, Any]) -> bool:
    return any(
        BLOCKED_HELPER_SOURCE_PATTERN.search(normalize_text(row.get(field)))
        for field in SOURCE_GUARD_FIELDS
    )


def join_values(values: Any) -> str:
    if isinstance(values, str):
        return values
    return "|".join(normalize_text(value) for value in values if normalize_text(value))


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
