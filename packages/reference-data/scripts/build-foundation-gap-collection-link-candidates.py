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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_OPERATIONS_DASHBOARD = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_operations_dashboard.csv"
)
DEFAULT_COLLECTION_TARGETS = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_collection_targets.csv"
)
DEFAULT_MANIFEST_GLOB = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_*artifact_manifest_*.jsonl"
)
DEFAULT_OUTPUT_CSV = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_gap_collection_link_candidates_20260613.csv"
)
DEFAULT_OUTPUT_SUMMARY = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_gap_collection_link_candidates_20260613_summary.json"
)

OUTPUT_FIELDS = [
    "provider",
    "artifactType",
    "year",
    "unvCd",
    "universityName",
    "campus",
    "sourceHomepageUrl",
    "finalHomepageUrl",
    "rawPath",
    "linkRole",
    "linkText",
    "hrefRaw",
    "resolvedUrl",
    "hostname",
    "fileExtension",
    "keywordHits",
    "collectionTargetId",
    "collectionRoute",
    "collectionAction",
    "gapActionIds",
    "missingFlags",
    "targetEntities",
    "selectionScore",
    "selectionReasons",
]

ROUTE_ROLE = {
    "admission_office_result_board_or_file": "admission_result",
    "admission_office_guide_or_notice": "regular_admission_guide",
    "admission_office_link_candidate": "admission_related",
    "admission_homepage": "admission_related",
    "admission_office_deep_link_discovery": "admission_related",
}

ROUTE_BASE_SCORE = {
    "admission_office_result_board_or_file": 95,
    "admission_office_guide_or_notice": 75,
    "admission_office_link_candidate": 45,
    "admission_homepage": 25,
    "admission_office_deep_link_discovery": 20,
}

STRONG_RESULT_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전년도|경쟁률|충원|최종\s*등록|등록자|"
    r"성적|등급|백분위|환산|cut|컷",
    re.I,
)
STRONG_GUIDE_PATTERN = re.compile(
    r"정시|수시|모집\s*요강|입학\s*전형|전형\s*계획|시행\s*계획|주요\s*사항|"
    r"전형\s*방법|수능\s*반영|학생부\s*반영|모집\s*인원",
    re.I,
)
OUT_OF_SCOPE_PATTERN = re.compile(
    r"재외국민|외국인|편입|대학원|시간제|평생교육|계약학과|산업체|"
    r"선행학습|영향평가|고교연계|체험|설명회|상담|입학식|학위수여|"
    r"기숙사|생활관|장학|등록금|교통|오시는\s*길|캠퍼스|"
    r"교직원|채용|공지사항$",
    re.I,
)
EXTERNAL_HELPER_HOST_PATTERN = re.compile(
    r"jinhak|jinhakapply|uway|uwayapply|telegr|01consulting|nesin|go3\.co\.kr",
    re.I,
)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    operations_path = resolve(repo_root, args.operations_dashboard)
    targets_path = resolve(repo_root, args.collection_targets)
    manifest_paths = resolve_globs(repo_root, args.manifest_glob)
    output_csv = resolve(repo_root, args.output_csv)
    output_summary = resolve(repo_root, args.output_summary)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_summary.parent.mkdir(parents=True, exist_ok=True)

    operations = read_csv(operations_path)
    targets = read_csv(targets_path)
    fetched_keys, manifest_stats = load_fetched_url_keys(manifest_paths)
    selected, stats = build_candidates(
        operations=operations,
        targets=targets,
        fetched_keys=fetched_keys,
        limit=args.limit,
        per_university_limit=args.per_university_limit,
        min_score=args.min_score,
        include_homepage=args.include_homepage,
    )

    write_csv(output_csv, selected, OUTPUT_FIELDS)
    write_json(
        output_summary,
        {
            "provider": "pacer-reference-data",
            "artifactType": "foundation_gap_collection_link_candidates_summary",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "inputs": {
                "operationsDashboard": to_repo_relative(operations_path, repo_root),
                "collectionTargets": to_repo_relative(targets_path, repo_root),
                "manifestGlob": args.manifest_glob,
                "manifestPathsScanned": len(manifest_paths),
            },
            "parameters": {
                "limit": args.limit,
                "perUniversityLimit": args.per_university_limit,
                "minScore": args.min_score,
                "includeHomepage": args.include_homepage,
            },
            "outputCsv": to_repo_relative(output_csv, repo_root),
            "operationRows": len(operations),
            "collectionTargetRows": len(targets),
            "runOrRepairOperationRows": stats["run_or_repair_operation_rows"],
            "eligibleTargetRows": stats["eligible_target_rows"],
            "alreadyFetchedUrls": stats["already_fetched_urls"],
            "outOfScopeRows": stats["out_of_scope_rows"],
            "conflictingYearRows": stats["conflicting_year_rows"],
            "belowMinScoreRows": stats["below_min_score_rows"],
            "selectedRows": len(selected),
            "byYear": counter_rows(Counter(str(row["year"]) for row in selected)),
            "byRoute": counter_rows(Counter(str(row["collectionRoute"]) for row in selected)),
            "byLinkRole": counter_rows(Counter(str(row["linkRole"]) for row in selected)),
            "byUniversity": counter_rows(Counter(str(row["universityName"]) for row in selected), 30),
            "byReason": counter_values_from_pipe(selected, "selectionReasons"),
            "manifestStats": manifest_stats,
            "notes": [
                "This is a crawl input derived from current foundation gap operations, not verified production data.",
                "ADIGA selection-detail targets are excluded because they require parser review, not network crawling.",
                "Out-of-scope helper/foreign/transfer/graduate/life-campus links are filtered before collection.",
            ],
        },
    )
    print(
        "foundation gap collection link candidates complete. "
        f"operations={len(operations)} targets={len(targets)} "
        f"eligible={stats['eligible_target_rows']} selected={len(selected)} "
        f"alreadyFetched={stats['already_fetched_urls']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--operations-dashboard", default=DEFAULT_OPERATIONS_DASHBOARD)
    parser.add_argument("--collection-targets", default=DEFAULT_COLLECTION_TARGETS)
    parser.add_argument("--manifest-glob", default=DEFAULT_MANIFEST_GLOB)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-summary", default=DEFAULT_OUTPUT_SUMMARY)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--per-university-limit", type=int, default=12)
    parser.add_argument("--min-score", type=int, default=150)
    parser.add_argument("--include-homepage", action="store_true")
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def build_candidates(
    *,
    operations: list[dict[str, str]],
    targets: list[dict[str, str]],
    fetched_keys: set[str],
    limit: int,
    per_university_limit: int,
    min_score: int,
    include_homepage: bool,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    stats: Counter[str] = Counter()
    run_gap_ids = {
        normalize_text(row.get("gapActionId"))
        for row in operations
        if normalize_text(row.get("nextBestStage")) == "run_or_repair_collection"
    }
    stats["run_or_repair_operation_rows"] = len(run_gap_ids)

    by_url: dict[str, dict[str, Any]] = {}
    for target in targets:
        route = normalize_text(target.get("collectionRoute"))
        if route == "adiga_selection_detail":
            continue
        if route == "admission_homepage" and not include_homepage:
            continue
        target_gap_ids = split_joined(target.get("gapActionIds"))
        if not run_gap_ids.intersection(target_gap_ids):
            continue
        url = normalize_text(target.get("sourceUrl"))
        url_key = canonical_url(url)
        if not url_key:
            continue
        if is_external_helper_url(url) or is_out_of_scope_target(target):
            stats["out_of_scope_rows"] += 1
            continue
        if has_conflicting_admission_year(target):
            stats["conflicting_year_rows"] += 1
            continue
        if url_key in fetched_keys:
            stats["already_fetched_urls"] += 1
            continue

        output_row = make_output_row(target)
        if (int_or_none(output_row.get("selectionScore")) or 0) < min_score:
            stats["below_min_score_rows"] += 1
            continue
        stats["eligible_target_rows"] += 1
        existing = by_url.get(url_key)
        if not existing or row_sort_key(output_row) < row_sort_key(existing):
            by_url[url_key] = output_row

    ranked = sorted(by_url.values(), key=row_sort_key)
    selected: list[dict[str, Any]] = []
    by_university: Counter[str] = Counter()
    for row in ranked:
        unv_cd = normalize_text(row.get("unvCd"))
        if by_university[unv_cd] >= per_university_limit:
            continue
        selected.append(row)
        by_university[unv_cd] += 1
        if len(selected) >= limit:
            break
    return selected, stats


def make_output_row(target: dict[str, str]) -> dict[str, Any]:
    url = normalize_text(target.get("sourceUrl"))
    route = normalize_text(target.get("collectionRoute"))
    label = normalize_text(target.get("sourceLabel"))
    role = link_role_for(target)
    scored = score_target(target, role)
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_link_candidate",
        "year": int_or_none(target.get("admissionYear")) or normalize_text(target.get("admissionYear")),
        "unvCd": normalize_text(target.get("unvCd")),
        "universityName": normalize_text(target.get("universityName")),
        "campus": "",
        "sourceHomepageUrl": homepage_url_for(target),
        "finalHomepageUrl": "",
        "rawPath": normalize_text(target.get("rawPath")),
        "linkRole": role,
        "linkText": label or route,
        "hrefRaw": url,
        "resolvedUrl": url,
        "hostname": hostname(url),
        "fileExtension": file_extension(url),
        "keywordHits": keyword_hits(target),
        "collectionTargetId": normalize_text(target.get("collectionTargetId")),
        "collectionRoute": route,
        "collectionAction": normalize_text(target.get("collectionAction")),
        "gapActionIds": normalize_text(target.get("gapActionIds")),
        "missingFlags": normalize_text(target.get("missingFlags")),
        "targetEntities": normalize_text(target.get("targetEntities")),
        "selectionScore": scored["score"],
        "selectionReasons": "|".join(scored["reasons"]),
    }


def link_role_for(target: dict[str, str]) -> str:
    route = normalize_text(target.get("collectionRoute"))
    label = compact(f"{target.get('sourceLabel')} {target.get('sourceUrl')}")
    if STRONG_RESULT_PATTERN.search(label):
        return "admission_result"
    if "정시" in label and re.search(r"모집\s*요강|요강", label):
        return "regular_admission_guide"
    if "수시" in label and re.search(r"모집\s*요강|요강", label):
        return "recruitment_notice"
    return ROUTE_ROLE.get(route, "admission_related")


def score_target(target: dict[str, str], role: str) -> dict[str, Any]:
    route = normalize_text(target.get("collectionRoute"))
    label = normalize_text(target.get("sourceLabel"))
    url = decode_percent(normalize_text(target.get("sourceUrl")))
    missing_flags = normalize_text(target.get("missingFlags"))
    haystack = compact(f"{label} {url} {missing_flags}")
    score = int_or_none(target.get("collectionPriorityScore")) or 0
    score += ROUTE_BASE_SCORE.get(route, 0)
    reasons = [f"route:{route}"] if route else []
    if role == "admission_result":
        score += 70
        reasons.append("role:admission_result")
    elif role == "regular_admission_guide":
        score += 45
        reasons.append("role:regular_admission_guide")
    elif role == "recruitment_notice":
        score += 25
        reasons.append("role:recruitment_notice")
    if STRONG_RESULT_PATTERN.search(haystack):
        score += 60
        reasons.append("strong_result_signal")
    if STRONG_GUIDE_PATTERN.search(haystack):
        score += 30
        reasons.append("strong_guide_signal")
    if "missing_historical_outcomes" in missing_flags or "missing_outcome_scores" in missing_flags:
        score += 25
        reasons.append("historical_outcome_gap")
    if "missing_admission_units" in missing_flags or "missing_recruitment_quota_draft" in missing_flags:
        score += 15
        reasons.append("unit_or_quota_gap")
    detected_years = detected_admission_years(haystack)
    if detected_years:
        score += 10
        reasons.append("admission_year_signal")
    return {"score": score, "reasons": sorted(set(reasons))}


def is_out_of_scope_target(target: dict[str, str]) -> bool:
    route = normalize_text(target.get("collectionRoute"))
    if route == "admission_homepage":
        return False
    text = compact(f"{target.get('sourceLabel')} {decode_percent(target.get('sourceUrl'))}")
    if OUT_OF_SCOPE_PATTERN.search(text):
        return True
    return False


def has_conflicting_admission_year(target: dict[str, str]) -> bool:
    text = compact(f"{target.get('sourceLabel')} {decode_percent(target.get('sourceUrl'))}")
    years = set(detected_admission_years(text))
    if not years:
        return False
    target_year = int_or_none(target.get("admissionYear"))
    return bool(target_year and target_year not in years)


def is_external_helper_url(url: str) -> bool:
    return bool(EXTERNAL_HELPER_HOST_PATTERN.search(hostname(url)))


def homepage_url_for(target: dict[str, str]) -> str:
    if normalize_text(target.get("collectionRoute")) == "admission_homepage":
        return normalize_text(target.get("sourceUrl"))
    return ""


def keyword_hits(target: dict[str, str]) -> str:
    text = compact(f"{target.get('sourceLabel')} {decode_percent(target.get('sourceUrl'))}")
    hits: list[str] = []
    for label, pattern in [
        ("입시결과", STRONG_RESULT_PATTERN),
        ("모집요강", re.compile(r"모집\s*요강|요강")),
        ("정시", re.compile(r"정시")),
        ("수시", re.compile(r"수시")),
        ("시행계획", re.compile(r"시행\s*계획|전형\s*계획|주요\s*사항")),
    ]:
        if pattern.search(text):
            hits.append(label)
    return "|".join(hits)


def row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int_or_none(row.get("selectionScore") or 0),
        int_or_none(row.get("year")) or 9999,
        str(row.get("universityName") or ""),
        str(row.get("resolvedUrl") or ""),
    )


def load_fetched_url_keys(paths: list[Path]) -> tuple[set[str], dict[str, Any]]:
    fetched: set[str] = set()
    stats = {
        "manifestFiles": len(paths),
        "manifestRows": 0,
        "fetchedRows": 0,
        "uniqueFetchedUrls": 0,
    }
    for path in paths:
        for row in read_jsonl(path):
            stats["manifestRows"] += 1
            if normalize_text(row.get("status")) and normalize_text(row.get("status")) != "fetched":
                continue
            stats["fetchedRows"] += 1
            for field in [
                "sourceCandidateUrl",
                "attachmentUrl",
                "canonicalAttachmentUrl",
                "finalUrl",
            ]:
                key = canonical_url(normalize_text(row.get(field)))
                if key:
                    fetched.add(key)
    stats["uniqueFetchedUrls"] = len(fetched)
    return fetched, stats


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def resolve_globs(repo_root: Path, pattern: str) -> list[Path]:
    path = Path(pattern)
    return [Path(match) for match in sorted(glob.glob(str(path if path.is_absolute() else repo_root / path)))]


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while True:
        if (current / "pnpm-workspace.yaml").exists():
            return current
        if current.parent == current:
            return start.resolve()
        current = current.parent


def canonical_url(value: str) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text
    query = urlencode(sorted(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            query,
            "",
        )
    )


def hostname(value: str) -> str:
    try:
        return urlsplit(normalize_text(value)).hostname or ""
    except ValueError:
        return ""


def file_extension(value: str) -> str:
    path = urlsplit(normalize_text(value)).path.lower()
    match = re.search(r"\.([a-z0-9]{1,8})$", path)
    return match.group(1) if match else ""


def split_joined(value: Any) -> set[str]:
    text = normalize_text(value)
    if not text:
        return set()
    return {part for part in re.split(r"[|,;]", text) if part}


def detected_admission_years(value: str) -> list[int]:
    return sorted({int(year) for year in re.findall(r"(?<!\d)(20\d{2})\s*학\s*년\s*도", value)})


def compact(value: Any) -> str:
    return re.sub(r"\s+", "", decode_percent(normalize_text(value)))


def decode_percent(value: Any) -> str:
    text = normalize_text(value)
    try:
        from urllib.parse import unquote

        return unquote(text)
    except Exception:
        return text


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def counter_values_from_pipe(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for value in split_joined(row.get(field)):
            counter[value] += 1
    return counter_rows(counter, 30)


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
