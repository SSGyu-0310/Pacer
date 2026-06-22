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


DEFAULT_ADMISSION_UNITS = "packages/reference-data/data/public/foundation/foundation_admission_units.csv"
DEFAULT_HISTORICAL_OUTCOMES = "packages/reference-data/data/public/foundation/foundation_historical_outcomes.csv"
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/foundation"

OUTPUT_JSONL = "foundation_admission_unit_clusters.jsonl"
OUTPUT_CSV = "foundation_admission_unit_clusters.csv"
OUTPUT_SUMMARY = "foundation_admission_unit_clusters_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027
RECENT_YEARS = [str(year) for year in range(RECENT_YEAR_MIN, RECENT_YEAR_MAX + 1)]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    admission_units_path = resolve(repo_root, args.admission_units)
    historical_outcomes_path = resolve(repo_root, args.historical_outcomes)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    admission_units = read_csv(admission_units_path)
    historical_outcomes = read_csv(historical_outcomes_path)
    clusters = build_clusters(admission_units, historical_outcomes)

    write_jsonl(output_dir / OUTPUT_JSONL, clusters)
    write_csv(output_dir / OUTPUT_CSV, clusters)
    summary = summarize(admission_units_path, historical_outcomes_path, repo_root, admission_units, historical_outcomes, clusters)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation admission unit clusters complete. "
        f"sourceUnits={len(admission_units)} sourceOutcomes={len(historical_outcomes)} "
        f"clusters={len(clusters)} continuousRecent5Plus={summary['clusterRows']['continuousRecent5PlusYears']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission-units", default=DEFAULT_ADMISSION_UNITS)
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


def build_clusters(
    admission_units: list[dict[str, str]],
    historical_outcomes: list[dict[str, str]],
) -> list[dict[str, Any]]:
    outcomes_by_unit: dict[str, list[dict[str, str]]] = {}
    for row in historical_outcomes:
        unit_id = normalize_text(row.get("unitCandidateId"))
        if unit_id:
            outcomes_by_unit.setdefault(unit_id, []).append(row)

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in admission_units:
        unit_key = normalized_unit_key(row.get("admissionUnitCanonicalName") or row.get("admissionUnitName"))
        key = (
            normalize_text(row.get("unvCd")),
            normalize_text(row.get("universityName")),
            unit_key,
        )
        if key not in groups:
            groups[key] = new_group(key)
        add_unit_row(groups[key], row, outcomes_by_unit.get(normalize_text(row.get("unitCandidateId")), []))

    clusters = [finalize_group(group) for group in groups.values()]
    clusters.sort(
        key=lambda row: (
            -int(row.get("recentYears2021To2027Count") or 0),
            -int(row.get("outcomeRowsWithScores") or 0),
            str(row.get("universityName") or ""),
            str(row.get("representativeAdmissionUnitName") or ""),
        )
    )
    return clusters


def new_group(key: tuple[str, str, str]) -> dict[str, Any]:
    unv_cd, university_name, unit_key = key
    return {
        "unvCd": unv_cd,
        "universityName": university_name,
        "normalizedAdmissionUnitKey": unit_key,
        "unitCandidateIds": [],
        "sourceCandidateSha256Values": [],
        "admissionUnitNames": Counter(),
        "canonicalNames": Counter(),
        "years": Counter(),
        "recruitmentGroups": Counter(),
        "majorGroups": Counter(),
        "sourceProviders": Counter(),
        "scoreAvailability": Counter(),
        "confidence": Counter(),
        "sourceUrls": [],
        "rawPaths": [],
        "sampleOutcomes": [],
        "unitRows": 0,
        "outcomeRows": 0,
        "outcomeRowsWithScores": 0,
        "outcomeRowsWithQuotaCompetition": 0,
        "metricCount": 0,
        "subjectMetricCount": 0,
    }


def add_unit_row(group: dict[str, Any], row: dict[str, str], outcomes: list[dict[str, str]]) -> None:
    group["unitRows"] += 1
    add_limited(group["unitCandidateIds"], row.get("unitCandidateId"), 200)
    for value in split_joined(row.get("sourceCandidateSha256Values")):
        add_limited(group["sourceCandidateSha256Values"], value, 200)
    bump_counter(group["admissionUnitNames"], row.get("admissionUnitName"))
    bump_counter(group["canonicalNames"], row.get("admissionUnitCanonicalName"))
    bump_counter(group["years"], row.get("year"))
    bump_counter(group["recruitmentGroups"], row.get("recruitmentGroup"))
    bump_counter(group["majorGroups"], row.get("majorGroup"))
    for value in split_joined(row.get("sourceProviders")):
        group["sourceProviders"][value] += 1

    for outcome in outcomes:
        group["outcomeRows"] += 1
        if truthy(outcome.get("hasOutcomeScore")):
            group["outcomeRowsWithScores"] += 1
        if truthy(outcome.get("hasQuotaAndCompetition")):
            group["outcomeRowsWithQuotaCompetition"] += 1
        group["metricCount"] += int_or_none(outcome.get("metricCount")) or 0
        group["subjectMetricCount"] += int_or_none(outcome.get("subjectMetricCount")) or 0
        bump_counter(group["scoreAvailability"], outcome.get("scoreAvailability"))
        bump_counter(group["confidence"], outcome.get("confidence"))
        add_limited(group["sourceUrls"], outcome.get("sourceUrl"), 30)
        add_limited(group["rawPaths"], outcome.get("rawPath"), 30)
        add_sample(group, outcome)


def add_sample(group: dict[str, Any], outcome: dict[str, str]) -> None:
    sample = {
        "year": int_or_none(outcome.get("year")),
        "recruitmentGroup": normalize_text(outcome.get("recruitmentGroup")),
        "admissionUnitName": normalize_text(outcome.get("admissionUnitName")),
        "quota": number_or_text(outcome.get("quota")),
        "competitionRate": number_or_text(outcome.get("competitionRate")),
        "scoreAvailability": normalize_text(outcome.get("scoreAvailability")),
        "confidence": normalize_text(outcome.get("confidence")),
        "sourceCandidateSha256": normalize_text(outcome.get("sourceCandidateSha256")),
    }
    samples = group["sampleOutcomes"]
    if sample["sourceCandidateSha256"] in {item.get("sourceCandidateSha256") for item in samples}:
        return
    samples.append(sample)
    samples.sort(
        key=lambda item: (
            -(item.get("year") or 0),
            str(item.get("recruitmentGroup") or ""),
        )
    )
    del samples[10:]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    years = sorted(group["years"], key=lambda value: int_or_large(value))
    int_years = [year for year in (int_or_none(value) for value in years) if year is not None]
    recent_years = [str(year) for year in int_years if RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX]
    missing_recent_years = [year for year in RECENT_YEARS if year not in recent_years]
    canonical_name = most_common_value(group["canonicalNames"]) or most_common_value(group["admissionUnitNames"])
    representative_name = most_common_value(group["admissionUnitNames"]) or canonical_name
    continuity = continuity_strength(recent_years)
    coverage_flags = cluster_flags(group, recent_years, missing_recent_years)
    return {
        "unitClusterId": deterministic_uuid(
            f"admission-unit-cluster:{group['unvCd']}:{group['universityName']}:{group['normalizedAdmissionUnitKey']}"
        ),
        "artifactType": "foundation_admission_unit_cluster",
        "unvCd": group["unvCd"],
        "universityName": group["universityName"],
        "normalizedAdmissionUnitKey": group["normalizedAdmissionUnitKey"],
        "representativeAdmissionUnitName": representative_name,
        "admissionUnitCanonicalName": canonical_name,
        "sampleAdmissionUnitNames": counter_to_rows(group["admissionUnitNames"], 20),
        "firstYear": min(int_years) if int_years else "",
        "lastYear": max(int_years) if int_years else "",
        "years": "|".join(years),
        "yearCount": len(years),
        "recentYears2021To2027": "|".join(recent_years),
        "recentYears2021To2027Count": len(recent_years),
        "missingRecentYears2021To2027": "|".join(missing_recent_years),
        "continuityStrength": continuity,
        "coverageFlags": "|".join(coverage_flags),
        "unitRows": group["unitRows"],
        "outcomeRows": group["outcomeRows"],
        "outcomeRowsWithScores": group["outcomeRowsWithScores"],
        "outcomeRowsWithQuotaCompetition": group["outcomeRowsWithQuotaCompetition"],
        "metricCount": group["metricCount"],
        "subjectMetricCount": group["subjectMetricCount"],
        "recruitmentGroups": counter_to_rows(group["recruitmentGroups"], 10),
        "majorGroups": counter_to_rows(group["majorGroups"], 10),
        "sourceProviders": "|".join(sorted(group["sourceProviders"])),
        "scoreAvailability": counter_to_rows(group["scoreAvailability"], 10),
        "confidence": counter_to_rows(group["confidence"], 10),
        "reviewPriorityScore": review_priority(group, recent_years, continuity),
        "sampleOutcomes": group["sampleOutcomes"],
        "unitCandidateIds": "|".join(group["unitCandidateIds"]),
        "sourceCandidateSha256Values": "|".join(group["sourceCandidateSha256Values"]),
        "sourceUrls": "|".join(group["sourceUrls"]),
        "rawPaths": "|".join(group["rawPaths"]),
        "reviewStatus": "needs_human_verification",
    }


def normalized_unit_key(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"[()\[\]{}]", "", text)
    text = re.sub(r"\s+", "", text)
    return text or "unknown"


def continuity_strength(recent_years: list[str]) -> str:
    if len(recent_years) >= 5:
        return "high"
    if len(recent_years) >= 3:
        return "medium"
    return "low"


def cluster_flags(group: dict[str, Any], recent_years: list[str], missing_recent_years: list[str]) -> list[str]:
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
    if len(group["recruitmentGroups"]) > 1:
        flags.append("has_multiple_recruitment_groups")
    if len(group["admissionUnitNames"]) > 1:
        flags.append("has_name_variants")
    return flags


def review_priority(group: dict[str, Any], recent_years: list[str], continuity: str) -> int:
    continuity_bonus = {"high": 80, "medium": 45, "low": 10}[continuity]
    score_bonus = min(int(group["outcomeRowsWithScores"]) * 3, 60)
    metric_bonus = min(int(group["metricCount"]), 40)
    group_bonus = min(len(group["recruitmentGroups"]) * 5, 20)
    recent_bonus = len(recent_years) * 8
    return continuity_bonus + score_bonus + metric_bonus + group_bonus + recent_bonus


def summarize(
    admission_units_path: Path,
    historical_outcomes_path: Path,
    repo_root: Path,
    admission_units: list[dict[str, str]],
    historical_outcomes: list[dict[str, str]],
    clusters: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_admission_unit_clusters_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(admission_units_path, repo_root), "sha256": sha256_file(admission_units_path)},
            {"path": to_repo_relative(historical_outcomes_path, repo_root), "sha256": sha256_file(historical_outcomes_path)},
        ],
        "sourceRows": {
            "admissionUnits": len(admission_units),
            "historicalOutcomes": len(historical_outcomes),
        },
        "clusterRows": {
            "total": len(clusters),
            "continuousRecent5PlusYears": sum(1 for row in clusters if row["continuityStrength"] == "high"),
            "mediumContinuity": sum(1 for row in clusters if row["continuityStrength"] == "medium"),
            "lowContinuity": sum(1 for row in clusters if row["continuityStrength"] == "low"),
            "full2021To2027Coverage": sum(
                1 for row in clusters if "has_full_2021_2027_coverage" in split_joined(row.get("coverageFlags"))
            ),
            "withScoreOutcomes": sum(1 for row in clusters if row["outcomeRowsWithScores"] > 0),
            "withMultipleRecruitmentGroups": sum(
                1 for row in clusters if "has_multiple_recruitment_groups" in split_joined(row.get("coverageFlags"))
            ),
            "withNameVariants": sum(1 for row in clusters if "has_name_variants" in split_joined(row.get("coverageFlags"))),
        },
        "byUniversityTop30": counter_rows(Counter(str(row.get("universityName") or "") for row in clusters), limit=30),
        "byRecentYearCount": counter_rows(Counter(str(row.get("recentYears2021To2027Count") or 0) for row in clusters)),
        "byContinuityStrength": counter_rows(Counter(str(row.get("continuityStrength") or "") for row in clusters)),
        "byCoverageFlag": counter_rows(
            Counter(flag for row in clusters for flag in split_joined(row.get("coverageFlags"))),
            limit=30,
        ),
        "byRecruitmentGroupSignal": counter_rows(
            Counter(
                item["value"]
                for row in clusters
                for item in row.get("recruitmentGroups", [])
                if item.get("value")
            ),
            limit=20,
        ),
        "notes": [
            "Clusters group yearly AdmissionUnit candidates by university and normalized canonical admission-unit name.",
            "They are review scaffolds for longitudinal unit mapping, not verified AdmissionUnit rows.",
            "Recruitment groups and name variants are preserved because they may indicate true changes or parser noise.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "unitClusterId",
        "artifactType",
        "unvCd",
        "universityName",
        "normalizedAdmissionUnitKey",
        "representativeAdmissionUnitName",
        "admissionUnitCanonicalName",
        "sampleAdmissionUnitNames",
        "firstYear",
        "lastYear",
        "years",
        "yearCount",
        "recentYears2021To2027",
        "recentYears2021To2027Count",
        "missingRecentYears2021To2027",
        "continuityStrength",
        "coverageFlags",
        "unitRows",
        "outcomeRows",
        "outcomeRowsWithScores",
        "outcomeRowsWithQuotaCompetition",
        "metricCount",
        "subjectMetricCount",
        "recruitmentGroups",
        "majorGroups",
        "sourceProviders",
        "scoreAvailability",
        "confidence",
        "reviewPriorityScore",
        "sampleOutcomes",
        "unitCandidateIds",
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


def number_or_text(value: Any) -> Any:
    text = normalize_text(value)
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return int(number) if number.is_integer() else number


def most_common_value(counter: Counter[str]) -> str:
    return counter.most_common(1)[0][0] if counter else ""


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
