#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_INPUT_GLOB = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_attachment_candidates_*_gap_homepage_links.csv"
)
DEFAULT_MANIFEST_GLOB = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_*artifact_manifest_*.jsonl"
)
DEFAULT_OUTPUT_CSV = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_attachment_candidates_gap_homepage_related_detail_high_value_20260608.csv"
)
DEFAULT_OUTPUT_SUMMARY = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_attachment_candidates_gap_homepage_related_detail_high_value_20260608_summary.json"
)

RECENT_YEARS = set(range(2021, 2028))

FIELDNAMES = [
    "provider",
    "artifactType",
    "year",
    "unvCd",
    "universityName",
    "campus",
    "sourceLinkRole",
    "sourceLinkText",
    "sourceCandidateUrl",
    "detailRawPath",
    "attachmentRole",
    "linkText",
    "hrefRaw",
    "resolvedUrl",
    "hostname",
    "fileExtension",
    "keywordHits",
    "originalCollectionYear",
    "detectedAdmissionYears",
    "selectionScore",
    "selectionReasons",
]

STRONG_PATTERNS = {
    "admission_guide": re.compile(r"모집\s*요강|수시\s*모집|정시\s*모집|신입학.*요강"),
    "admission_result": re.compile(
        r"입시\s*결과|입학\s*결과|전년도|전년\s*도|경쟁률|충원|최종\s*등록|등록자|"
        r"성적|등급|백분위|환산|cut|컷",
        re.I,
    ),
    "admission_plan": re.compile(r"대학입학전형.*시행계획|입학전형.*시행계획|시행계획|전형계획|주요사항"),
    "admission_rule": re.compile(r"수능|학생부|지원자격|전형방법|전형요소|반영비율|산출"),
}
LOW_SIGNAL_PATTERN = re.compile(
    r"입학식|사진|도서관|채용|학위수여|개강|종강|축제|행사|캠프|장학|생활관|기숙사|"
    r"평생교육원|대학원|교직원"
)
ADMISSION_YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})\s*학\s*년\s*도")


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    input_paths = resolve_glob(repo_root, args.input_glob)
    manifest_paths = resolve_glob(repo_root, args.manifest_glob)
    output_csv = resolve(repo_root, args.output_csv)
    output_summary = resolve(repo_root, args.output_summary)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_summary.parent.mkdir(parents=True, exist_ok=True)

    source_rows = read_csv_many(input_paths)
    fetched_keys, manifest_stats = load_fetched_url_keys(manifest_paths)
    selected, stats = select_rows(
        source_rows,
        fetched_keys=fetched_keys,
        limit=args.limit,
        per_university_limit=args.per_university_limit,
        min_score=args.min_score,
    )

    write_csv(output_csv, selected, FIELDNAMES)
    write_json(
        output_summary,
        {
            "provider": "university-admission-office",
            "artifactType": "university_admission_gap_related_detail_high_value_candidate_summary",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "inputPaths": [to_repo_relative(path, repo_root) for path in input_paths],
            "manifestPathsScanned": len(manifest_paths),
            "outputCsv": to_repo_relative(output_csv, repo_root),
            "parameters": {
                "limit": args.limit,
                "perUniversityLimit": args.per_university_limit,
                "minScore": args.min_score,
            },
            "sourceRows": len(source_rows),
            "relatedDetailRows": stats["related_detail_rows"],
            "uniqueRelatedDetailUrls": stats["unique_related_detail_urls"],
            "alreadyFetchedUrls": stats["already_fetched_urls"],
            "eligibleRows": stats["eligible_rows"],
            "selectedRows": len(selected),
            "byOutputYear": counter_rows(selected, "year"),
            "byUniversity": counter_rows(selected, "universityName", limit=25),
            "byHostname": counter_rows(selected, "hostname", limit=25),
            "byReason": counter_values_from_pipe(selected, "selectionReasons"),
            "manifestStats": manifest_stats,
            "notes": [
                "Rows are selected from existing gap-homepage related_detail candidates only.",
                "Already fetched sourceCandidateUrl, attachmentUrl, canonicalAttachmentUrl, and finalUrl values are excluded.",
                "The output is still a crawl queue. It does not prove an AdmissionRule or HistoricalOutcome until files are fetched, extracted, and reviewed.",
            ],
        },
    )

    print(
        "gap related-detail high-value candidate build complete. "
        f"sourceRows={len(source_rows)} "
        f"relatedDetail={stats['related_detail_rows']} "
        f"eligible={stats['eligible_rows']} "
        f"selected={len(selected)} "
        f"output={to_repo_relative(output_csv, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--manifest-glob", default=DEFAULT_MANIFEST_GLOB)
    parser.add_argument("--output-csv", default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-summary", default=DEFAULT_OUTPUT_SUMMARY)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--per-university-limit", type=int, default=80)
    parser.add_argument("--min-score", type=int, default=115)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def select_rows(
    source_rows: list[dict[str, str]],
    *,
    fetched_keys: set[str],
    limit: int,
    per_university_limit: int,
    min_score: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    by_url: dict[str, dict[str, Any]] = {}
    stats = Counter()

    for row in source_rows:
        if normalize_text(row.get("attachmentRole")) != "related_detail":
            continue
        stats["related_detail_rows"] += 1

        url = normalize_text(row.get("resolvedUrl"))
        url_key = canonical_url(url)
        if not url_key:
            continue
        if url_key in fetched_keys:
            stats["already_fetched_urls"] += 1
            continue

        scored = score_row(row)
        if scored["score"] < min_score:
            continue

        stats["eligible_rows"] += 1
        output_row = make_output_row(row, scored)
        existing = by_url.get(url_key)
        if not existing or row_sort_key(output_row) < row_sort_key(existing):
            by_url[url_key] = output_row

    stats["unique_related_detail_urls"] = len(by_url)
    ranked = sorted(by_url.values(), key=row_sort_key)

    selected: list[dict[str, Any]] = []
    by_university: dict[str, int] = defaultdict(int)
    for row in ranked:
        unv_cd = normalize_text(row.get("unvCd"))
        if by_university[unv_cd] >= per_university_limit:
            continue
        selected.append(row)
        by_university[unv_cd] += 1
        if len(selected) >= limit:
            break

    return selected, dict(stats)


def score_row(row: dict[str, str]) -> dict[str, Any]:
    text = normalize_text(row.get("linkText"))
    url = decode_percent(normalize_text(row.get("resolvedUrl")))
    keyword_hits = normalize_text(row.get("keywordHits"))
    source_role = normalize_text(row.get("sourceLinkRole"))
    haystack = compact(f"{text} {url} {keyword_hits}")
    score = 0
    reasons: list[str] = []

    for reason, pattern in STRONG_PATTERNS.items():
        if pattern.search(haystack):
            score += {
                "admission_guide": 90,
                "admission_result": 100,
                "admission_plan": 75,
                "admission_rule": 35,
            }[reason]
            reasons.append(reason)

    if source_role in {"admission_result", "competition_rate"}:
        score += 65
        reasons.append(f"source_role:{source_role}")
    elif source_role in {"recruitment_notice", "regular_admission_guide"}:
        score += 40
        reasons.append(f"source_role:{source_role}")
    elif source_role == "admission_related":
        score += 10

    detected_years = detected_recent_years(haystack)
    if detected_years:
        score += 30
        reasons.append("recent_admission_year_signal")
        newest = max(detected_years)
        if newest == 2027:
            score += 25
        elif newest == 2026:
            score += 20
        elif newest >= 2024:
            score += 12

    if keyword_hits:
        score += min(30, 5 * len(keyword_hits.split("|")))

    if LOW_SIGNAL_PATTERN.search(haystack) and not has_strong_document_signal(haystack):
        score -= 120
        reasons.append("low_signal_penalty")

    return {
        "score": score,
        "reasons": sorted(set(reasons)),
        "detectedYears": detected_years,
    }


def make_output_row(row: dict[str, str], scored: dict[str, Any]) -> dict[str, Any]:
    output = {name: normalize_text(row.get(name)) for name in FIELDNAMES}
    original_year = normalize_text(row.get("year"))
    detected_years = scored["detectedYears"]
    output["originalCollectionYear"] = original_year
    output["detectedAdmissionYears"] = "|".join(str(year) for year in detected_years)
    output["selectionScore"] = scored["score"]
    output["selectionReasons"] = "|".join(scored["reasons"])
    if detected_years:
        output["year"] = str(max(detected_years))
    else:
        output["year"] = original_year
    return output


def row_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -int(row.get("selectionScore") or 0),
        -int(row.get("year") or 0),
        normalize_text(row.get("universityName")),
        normalize_text(row.get("resolvedUrl")),
    )


def has_strong_document_signal(value: str) -> bool:
    return any(pattern.search(value) for pattern in STRONG_PATTERNS.values())


def detected_recent_years(value: str) -> list[int]:
    years = {
        int(match.group(1))
        for match in ADMISSION_YEAR_PATTERN.finditer(value)
        if int(match.group(1)) in RECENT_YEARS
    }
    return sorted(years)


def load_fetched_url_keys(paths: list[Path]) -> tuple[set[str], dict[str, Any]]:
    keys: set[str] = set()
    by_manifest_type = Counter()
    rows = 0
    for path in paths:
        for row in read_jsonl(path):
            rows += 1
            by_manifest_type[normalize_text(row.get("artifactType"))] += 1
            for field_name in (
                "sourceCandidateUrl",
                "attachmentUrl",
                "canonicalAttachmentUrl",
                "finalUrl",
            ):
                key = canonical_url(row.get(field_name))
                if key:
                    keys.add(key)
    return keys, {
        "rows": rows,
        "fetchedUrlKeys": len(keys),
        "byArtifactType": counter_to_rows(by_manifest_type),
    }


def canonical_url(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text.split("#", 1)[0].replace(";jsessionid=", ";JSESSIONID=")
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "jsessionid"
    ]
    path = re.sub(r";jsessionid=[^/?#;]*", "", parsed.path, flags=re.I)
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urlencode(query, doseq=True),
            "",
        )
    )


def read_csv_many(paths: list[Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows.extend(csv.DictReader(handle))
    return rows


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def counter_rows(rows: list[dict[str, Any]], field_name: str, limit: int | None = None) -> list[dict[str, Any]]:
    counter = Counter(normalize_text(row.get(field_name)) for row in rows)
    return counter_to_rows(counter, limit=limit)


def counter_values_from_pipe(
    rows: list[dict[str, Any]], field_name: str, limit: int | None = None
) -> list[dict[str, Any]]:
    counter = Counter()
    for row in rows:
        for value in normalize_text(row.get(field_name)).split("|"):
            if value:
                counter[value] += 1
    return counter_to_rows(counter, limit=limit)


def counter_to_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    items = counter.most_common(limit)
    return [{"value": value, "count": count} for value, count in items if value]


def resolve_glob(repo_root: Path, pattern: str) -> list[Path]:
    path = Path(pattern)
    if path.is_absolute():
        return sorted(path.parent.glob(path.name))
    return sorted(repo_root.glob(pattern))


def resolve(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while True:
        if (current / "pnpm-workspace.yaml").exists():
            return current
        if current.parent == current:
            return start.resolve()
        current = current.parent


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", decode_percent(value)).lower()


def decode_percent(value: str) -> str:
    try:
        from urllib.parse import unquote

        return unquote(value)
    except Exception:
        return value


def to_repo_relative(path: Path, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


if __name__ == "__main__":
    main()
