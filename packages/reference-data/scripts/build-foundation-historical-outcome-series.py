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


DEFAULT_UNIT_CLUSTERS = "packages/reference-data/data/public/foundation/foundation_admission_unit_clusters.csv"
DEFAULT_HISTORICAL_OUTCOMES = "packages/reference-data/data/public/foundation/foundation_historical_outcomes.csv"
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/foundation"

OUTPUT_JSONL = "foundation_historical_outcome_series.jsonl"
OUTPUT_CSV = "foundation_historical_outcome_series.csv"
OUTPUT_SUMMARY = "foundation_historical_outcome_series_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027
RECENT_YEARS = [str(year) for year in range(RECENT_YEAR_MIN, RECENT_YEAR_MAX + 1)]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    unit_clusters_path = resolve(repo_root, args.unit_clusters)
    historical_outcomes_path = resolve(repo_root, args.historical_outcomes)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    unit_clusters = read_csv(unit_clusters_path)
    historical_outcomes = read_csv(historical_outcomes_path)
    series = build_series(unit_clusters, historical_outcomes)

    write_jsonl(output_dir / OUTPUT_JSONL, series)
    write_csv(output_dir / OUTPUT_CSV, series)
    summary = summarize(unit_clusters_path, historical_outcomes_path, repo_root, unit_clusters, historical_outcomes, series)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation historical outcome series complete. "
        f"sourceClusters={len(unit_clusters)} sourceOutcomes={len(historical_outcomes)} "
        f"series={len(series)} recent5Plus={summary['seriesRows']['recent5PlusYears']} "
        f"scoreBearing={summary['seriesRows']['withScoreOutcomes']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--unit-clusters", default=DEFAULT_UNIT_CLUSTERS)
    parser.add_argument("--historical-outcomes", default=DEFAULT_HISTORICAL_OUTCOMES)
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


def build_series(
    unit_clusters: list[dict[str, str]],
    historical_outcomes: list[dict[str, str]],
) -> list[dict[str, Any]]:
    cluster_by_unit_id: dict[str, dict[str, str]] = {}
    for cluster in unit_clusters:
        for unit_id in split_joined(cluster.get("unitCandidateIds")):
            cluster_by_unit_id[unit_id] = cluster

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for outcome in historical_outcomes:
        unit_id = normalize_text(outcome.get("unitCandidateId"))
        cluster = cluster_by_unit_id.get(unit_id)
        if cluster is None:
            continue
        recruitment_group = normalize_text(outcome.get("recruitmentGroup")) or "none"
        key = (normalize_text(cluster.get("unitClusterId")), recruitment_group)
        if key not in groups:
            groups[key] = new_group(cluster, recruitment_group)
        add_outcome(groups[key], outcome)

    series = [finalize_group(group) for group in groups.values()]
    series.sort(
        key=lambda row: (
            -int(row.get("recentYears2021To2027Count") or 0),
            -int(row.get("outcomeRowsWithScores") or 0),
            str(row.get("universityName") or ""),
            str(row.get("representativeAdmissionUnitName") or ""),
            str(row.get("recruitmentGroup") or ""),
        )
    )
    return series


def new_group(cluster: dict[str, str], recruitment_group: str) -> dict[str, Any]:
    return {
        "unitClusterId": normalize_text(cluster.get("unitClusterId")),
        "unvCd": normalize_text(cluster.get("unvCd")),
        "universityName": normalize_text(cluster.get("universityName")),
        "representativeAdmissionUnitName": normalize_text(cluster.get("representativeAdmissionUnitName")),
        "admissionUnitCanonicalName": normalize_text(cluster.get("admissionUnitCanonicalName")),
        "normalizedAdmissionUnitKey": normalize_text(cluster.get("normalizedAdmissionUnitKey")),
        "recruitmentGroup": recruitment_group,
        "years": Counter(),
        "admissionUnitNames": Counter(),
        "scoreAvailability": Counter(),
        "confidence": Counter(),
        "sourceProviders": Counter(),
        "sourceCandidateSha256Values": [],
        "sourceUrls": [],
        "rawPaths": [],
        "points": [],
        "outcomeRows": 0,
        "outcomeRowsWithScores": 0,
        "outcomeRowsWithQuotaCompetition": 0,
        "metricCount": 0,
        "subjectMetricCount": 0,
    }


def add_outcome(group: dict[str, Any], outcome: dict[str, str]) -> None:
    group["outcomeRows"] += 1
    bump_counter(group["years"], outcome.get("year"))
    bump_counter(group["admissionUnitNames"], outcome.get("admissionUnitName"))
    bump_counter(group["scoreAvailability"], outcome.get("scoreAvailability"))
    bump_counter(group["confidence"], outcome.get("confidence"))
    bump_counter(group["sourceProviders"], outcome.get("sourceProvider"))
    if truthy(outcome.get("hasOutcomeScore")):
        group["outcomeRowsWithScores"] += 1
    if truthy(outcome.get("hasQuotaAndCompetition")):
        group["outcomeRowsWithQuotaCompetition"] += 1
    group["metricCount"] += int_or_none(outcome.get("metricCount")) or 0
    group["subjectMetricCount"] += int_or_none(outcome.get("subjectMetricCount")) or 0
    add_limited(group["sourceCandidateSha256Values"], outcome.get("sourceCandidateSha256"), 160)
    add_limited(group["sourceUrls"], outcome.get("sourceUrl"), 30)
    add_limited(group["rawPaths"], outcome.get("rawPath"), 30)
    group["points"].append(outcome_point(outcome))


def outcome_point(outcome: dict[str, str]) -> dict[str, Any]:
    return {
        "year": int_or_none(outcome.get("year")),
        "admissionUnitName": normalize_text(outcome.get("admissionUnitName")),
        "recruitmentGroup": normalize_text(outcome.get("recruitmentGroup")),
        "quota": float_or_none(outcome.get("quota")),
        "competitionRate": float_or_none(outcome.get("competitionRate")),
        "additionalPass": number_or_text(outcome.get("additionalPass")),
        "convertedScore50Cut": float_or_none(outcome.get("convertedScore50Cut")),
        "convertedScore70Cut": float_or_none(outcome.get("convertedScore70Cut")),
        "totalScore": float_or_none(outcome.get("totalScore")),
        "percentile70Average": float_or_none(outcome.get("percentile70Average")),
        "avgScoreCandidate": float_or_none(outcome.get("avgScoreCandidate")),
        "cutScoreCandidate": float_or_none(outcome.get("cutScoreCandidate")),
        "percentileCutCandidate": float_or_none(outcome.get("percentileCutCandidate")),
        "scoreAvailability": normalize_text(outcome.get("scoreAvailability")),
        "confidence": normalize_text(outcome.get("confidence")),
        "metricCount": int_or_none(outcome.get("metricCount")) or 0,
        "subjectMetricCount": int_or_none(outcome.get("subjectMetricCount")) or 0,
        "sourceCandidateSha256": normalize_text(outcome.get("sourceCandidateSha256")),
    }


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    points = sorted(
        group["points"],
        key=lambda point: (
            int_or_large(point.get("year")),
            str(point.get("admissionUnitName") or ""),
        ),
    )
    years = sorted((str(year) for year in group["years"] if year), key=int_or_large)
    int_years = [year for year in (int_or_none(value) for value in years) if year is not None]
    recent_years = [str(year) for year in int_years if RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX]
    missing_recent_years = [year for year in RECENT_YEARS if year not in recent_years]
    flags = series_flags(group, recent_years, missing_recent_years, points)
    numeric_summary = summarize_numeric_points(points)
    return {
        "outcomeSeriesId": deterministic_uuid(
            f"historical-outcome-series:{group['unitClusterId']}:{group['recruitmentGroup']}"
        ),
        "artifactType": "foundation_historical_outcome_series",
        "unitClusterId": group["unitClusterId"],
        "unvCd": group["unvCd"],
        "universityName": group["universityName"],
        "representativeAdmissionUnitName": group["representativeAdmissionUnitName"],
        "admissionUnitCanonicalName": group["admissionUnitCanonicalName"],
        "normalizedAdmissionUnitKey": group["normalizedAdmissionUnitKey"],
        "recruitmentGroup": group["recruitmentGroup"],
        "firstYear": min(int_years) if int_years else "",
        "lastYear": max(int_years) if int_years else "",
        "years": "|".join(years),
        "yearCount": len(years),
        "recentYears2021To2027": "|".join(recent_years),
        "recentYears2021To2027Count": len(recent_years),
        "missingRecentYears2021To2027": "|".join(missing_recent_years),
        "outcomeRows": group["outcomeRows"],
        "outcomeRowsWithScores": group["outcomeRowsWithScores"],
        "outcomeRowsWithQuotaCompetition": group["outcomeRowsWithQuotaCompetition"],
        "metricCount": group["metricCount"],
        "subjectMetricCount": group["subjectMetricCount"],
        "scoreAvailability": counter_to_rows(group["scoreAvailability"], 10),
        "confidence": counter_to_rows(group["confidence"], 10),
        "sourceProviders": "|".join(sorted(group["sourceProviders"])),
        "sampleAdmissionUnitNames": counter_to_rows(group["admissionUnitNames"], 20),
        "seriesFlags": "|".join(flags),
        "reviewPriorityScore": review_priority(group, recent_years, flags),
        "numericSummary": numeric_summary,
        "outcomePoints": points,
        "sourceCandidateSha256Values": "|".join(group["sourceCandidateSha256Values"]),
        "sourceUrls": "|".join(group["sourceUrls"]),
        "rawPaths": "|".join(group["rawPaths"]),
        "reviewStatus": "needs_human_verification",
    }


def series_flags(
    group: dict[str, Any],
    recent_years: list[str],
    missing_recent_years: list[str],
    points: list[dict[str, Any]],
) -> list[str]:
    flags = []
    if len(recent_years) >= 5:
        flags.append("has_recent_5plus_years")
    if len(recent_years) == len(RECENT_YEARS):
        flags.append("has_full_2021_2027_coverage")
    if missing_recent_years:
        flags.append("has_recent_year_gaps")
    if group["outcomeRowsWithScores"]:
        flags.append("has_score_outcomes")
    if group["outcomeRowsWithQuotaCompetition"]:
        flags.append("has_quota_competition")
    if len(group["scoreAvailability"]) > 1:
        flags.append("mixed_score_availability")
    if "no_score_metric" in group["scoreAvailability"]:
        flags.append("has_no_score_metric_rows")
    if any(point.get("totalScore") for point in points):
        flags.append("converted_score_scale_review_required")
    if len(points) != len({point.get("year") for point in points}):
        flags.append("multiple_rows_same_year")
    if group["recruitmentGroup"] == "none":
        flags.append("recruitment_group_missing_or_irregular")
    return flags


def summarize_numeric_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "quota": numeric_range(points, "quota"),
        "competitionRate": numeric_range(points, "competitionRate"),
        "additionalPass": numeric_range(points, "additionalPass"),
        "convertedScore70Cut": numeric_range(points, "convertedScore70Cut"),
        "percentile70Average": numeric_range(points, "percentile70Average"),
        "percentileCutCandidate": numeric_range(points, "percentileCutCandidate"),
    }


def numeric_range(points: list[dict[str, Any]], key: str) -> dict[str, Any]:
    values = [float(value) for point in points for value in [point.get(key)] if isinstance(value, (int, float))]
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "latest": latest_numeric(points, key),
    }


def latest_numeric(points: list[dict[str, Any]], key: str) -> float | int | None:
    for point in sorted(points, key=lambda item: int_or_large(item.get("year")), reverse=True):
        value = point.get(key)
        if isinstance(value, (int, float)):
            return value
    return None


def review_priority(group: dict[str, Any], recent_years: list[str], flags: list[str]) -> int:
    recent_bonus = len(recent_years) * 12
    score_bonus = min(int(group["outcomeRowsWithScores"]) * 5, 80)
    metric_bonus = min(int(group["metricCount"]), 50)
    continuity_bonus = 50 if "has_recent_5plus_years" in flags else 0
    full_bonus = 30 if "has_full_2021_2027_coverage" in flags else 0
    review_penalty = 10 if "mixed_score_availability" in flags else 0
    return max(0, recent_bonus + score_bonus + metric_bonus + continuity_bonus + full_bonus - review_penalty)


def summarize(
    unit_clusters_path: Path,
    historical_outcomes_path: Path,
    repo_root: Path,
    unit_clusters: list[dict[str, str]],
    historical_outcomes: list[dict[str, str]],
    series: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_historical_outcome_series_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(unit_clusters_path, repo_root), "sha256": sha256_file(unit_clusters_path)},
            {"path": to_repo_relative(historical_outcomes_path, repo_root), "sha256": sha256_file(historical_outcomes_path)},
        ],
        "sourceRows": {
            "unitClusters": len(unit_clusters),
            "historicalOutcomes": len(historical_outcomes),
        },
        "seriesRows": {
            "total": len(series),
            "recent5PlusYears": sum(1 for row in series if "has_recent_5plus_years" in split_joined(row["seriesFlags"])),
            "full2021To2027Coverage": sum(
                1 for row in series if "has_full_2021_2027_coverage" in split_joined(row["seriesFlags"])
            ),
            "withScoreOutcomes": sum(1 for row in series if row["outcomeRowsWithScores"] > 0),
            "withMixedScoreAvailability": sum(
                1 for row in series if "mixed_score_availability" in split_joined(row["seriesFlags"])
            ),
            "withNoScoreMetricRows": sum(
                1 for row in series if "has_no_score_metric_rows" in split_joined(row["seriesFlags"])
            ),
            "multipleRowsSameYear": sum(1 for row in series if "multiple_rows_same_year" in split_joined(row["seriesFlags"])),
        },
        "byRecruitmentGroup": counter_rows(Counter(str(row.get("recruitmentGroup") or "") for row in series)),
        "byRecentYearCount": counter_rows(Counter(str(row.get("recentYears2021To2027Count") or 0) for row in series)),
        "bySeriesFlag": counter_rows(
            Counter(flag for row in series for flag in split_joined(row.get("seriesFlags"))),
            limit=30,
        ),
        "byUniversityTop30": counter_rows(Counter(str(row.get("universityName") or "") for row in series), limit=30),
        "notes": [
            "Series are grouped by AdmissionUnit cluster and recruitment group.",
            "Numeric summaries are raw extracted candidate ranges, not admissions predictions.",
            "Converted-score scales vary by university and year; rows with converted scores keep a review flag before engine use.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "outcomeSeriesId",
        "artifactType",
        "unitClusterId",
        "unvCd",
        "universityName",
        "representativeAdmissionUnitName",
        "admissionUnitCanonicalName",
        "normalizedAdmissionUnitKey",
        "recruitmentGroup",
        "firstYear",
        "lastYear",
        "years",
        "yearCount",
        "recentYears2021To2027",
        "recentYears2021To2027Count",
        "missingRecentYears2021To2027",
        "outcomeRows",
        "outcomeRowsWithScores",
        "outcomeRowsWithQuotaCompetition",
        "metricCount",
        "subjectMetricCount",
        "scoreAvailability",
        "confidence",
        "sourceProviders",
        "sampleAdmissionUnitNames",
        "seriesFlags",
        "reviewPriorityScore",
        "numericSummary",
        "outcomePoints",
        "sourceCandidateSha256Values",
        "sourceUrls",
        "rawPaths",
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


def truthy(value: Any) -> bool:
    return normalize_text(value).lower() in {"true", "1", "yes", "y"}


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


def float_or_none(value: Any) -> float | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def number_or_text(value: Any) -> Any:
    text = normalize_text(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def counter_to_rows(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


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
