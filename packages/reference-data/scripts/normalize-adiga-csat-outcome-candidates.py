#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_INPUT_GLOB = (
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_csat_outcome_candidates_*.csv"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/adiga/extracted"

BASE_NUMERIC_FIELDS = [
    ("quota", "모집인원"),
    ("competitionRate", "경쟁률"),
    ("additionalPass", "충원합격"),
    ("convertedScore50Cut", "대학별환산_50컷"),
    ("convertedScore70Cut", "대학별환산_70컷"),
    ("totalScore", "대학별환산_총점"),
    ("percentile70Average", "백분위_70평균"),
]
JSON_METRIC_FIELDS = [
    ("percentile50BySubjectJson", "백분위_50컷"),
    ("percentile70BySubjectJson", "백분위_70컷"),
    ("mathSelectionRatioJson", "수학선택비율"),
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    input_paths = sorted(resolve_glob(repo_root, args.input_glob))
    row_candidates: list[dict[str, Any]] = []
    source_rows = []
    for input_path in input_paths:
        rows = read_csv_dicts(input_path)
        source_rows.append(
            {
                "path": to_repo_relative(input_path, repo_root),
                "rows": len(rows),
                "sha256": sha256_file(input_path),
            }
        )
        for row in rows:
            row_candidates.append(make_candidate(row))

    write_jsonl(output_dir / "adiga_csat_outcome_row_candidates.jsonl", row_candidates)
    write_csv_index(output_dir / "adiga_csat_outcome_row_candidates.csv", row_candidates)
    summary = summarize(source_rows, row_candidates)
    (output_dir / "adiga_csat_outcome_row_candidates_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "adiga csat outcome row candidate normalization complete. "
        f"sources={summary['sources']} rowCandidates={summary['rowCandidates']} "
        f"metricValues={summary['metricValues']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    raw_args = __import__("sys").argv[1:]
    return raw_args[1:] if raw_args[:1] == ["--"] else raw_args


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
        return [Path(match) for match in sorted(path.parent.glob(path.name))]
    return [Path(match) for match in sorted(repo_root.glob(pattern))]


def read_csv_dicts(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def make_candidate(row: dict[str, str]) -> dict[str, Any]:
    metric_values = metric_values_for_row(row)
    subjectMetricCount = sum(1 for metric in metric_values if metric.get("subject"))
    admission_unit_name = normalize_text(row.get("admissionUnitName"))
    university_name = normalize_text(row.get("universityName"))
    candidate_payload = {
        "year": int_value(row.get("year")),
        "unvCd": normalize_text(row.get("unvCd")),
        "sectionId": normalize_text(row.get("sectionId")),
        "tableIndex": int_value(row.get("tableIndex")),
        "rowIndex": int_value(row.get("rowIndex")),
        "admissionUnitName": admission_unit_name,
    }
    candidate_sha = hashlib.sha256(
        json.dumps(candidate_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    score_availability = score_availability_for(metric_values)

    return {
        "provider": "adiga",
        "artifactType": "adiga_csat_outcome_row_candidate",
        "evidenceTarget": "HistoricalOutcome",
        "pacerTargets": ["HistoricalOutcome", "AdmissionUnit", "ReferenceDataReview"],
        "year": int_value(row.get("year")),
        "unvCd": normalize_text(row.get("unvCd")),
        "universityName": university_name,
        "admissionUnitName": admission_unit_name,
        "admissionUnitCanonicalCandidate": canonical_unit_name(admission_unit_name),
        "recruitmentGroup": normalize_text(row.get("recruitmentGroup")) or None,
        "recruitmentGroupText": normalize_text(row.get("recruitmentGroupText")) or None,
        "quota": number_or_none(row.get("quota")),
        "competitionRate": number_or_none(row.get("competitionRate")),
        "additionalPass": number_or_none(row.get("additionalPass")),
        "convertedScore50Cut": number_or_none(row.get("convertedScore50Cut")),
        "convertedScore70Cut": number_or_none(row.get("convertedScore70Cut")),
        "totalScore": number_or_none(row.get("totalScore")),
        "percentile70Average": number_or_none(row.get("percentile70Average")),
        "metricCount": len(metric_values),
        "subjectMetricCount": subjectMetricCount,
        "metricValues": metric_values,
        "scoreAvailability": score_availability,
        "hasQuotaAndCompetition": bool(
            number_or_none(row.get("quota")) is not None
            and number_or_none(row.get("competitionRate")) is not None
        ),
        "hasOutcomeScore": score_availability != "no_score_metric",
        "sourceConfidence": normalize_text(row.get("sourceConfidence")) or "parsed_candidate",
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "rawPath": normalize_text(row.get("rawPath")),
        "sectionId": normalize_text(row.get("sectionId")) or None,
        "tableIndex": int_value(row.get("tableIndex")),
        "rowIndex": int_value(row.get("rowIndex")),
        "sourceCsvArtifactType": normalize_text(row.get("artifactType")),
        "candidateSha256": candidate_sha,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "status": "candidate",
        "reviewRequired": True,
    }


def metric_values_for_row(row: dict[str, str]) -> list[dict[str, Any]]:
    metrics: list[dict[str, Any]] = []
    for field, label in BASE_NUMERIC_FIELDS:
        value = number_or_none(row.get(field))
        if value is None:
            continue
        metrics.append({"field": field, "label": label, "raw": normalize_text(row.get(field)), "value": value})

    for field, group_label in JSON_METRIC_FIELDS:
        parsed = parse_json_object(row.get(field))
        for subject, raw_value in sorted(parsed.items()):
            value = number_or_none(raw_value)
            if value is None:
                continue
            metrics.append(
                {
                    "field": field,
                    "label": f"{group_label}_{subject}",
                    "subject": str(subject),
                    "raw": str(raw_value),
                    "value": value,
                }
            )
    return metrics


def parse_json_object(value: Any) -> dict[str, Any]:
    text = normalize_text(value)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def score_availability_for(metrics: list[dict[str, Any]]) -> str:
    fields = {metric["field"] for metric in metrics}
    if "convertedScore70Cut" in fields and "percentile70Average" in fields:
        return "converted_and_percentile"
    if "convertedScore70Cut" in fields or "convertedScore50Cut" in fields:
        return "converted_score_only"
    if any(str(field).startswith("percentile") for field in fields) or "percentile70Average" in fields:
        return "percentile_only"
    return "no_score_metric"


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_unit_name(value: str) -> str:
    return re.sub(r"\s+", "", value.replace("·", "").replace("/", ""))


def number_or_none(value: Any) -> float | None:
    text = normalize_text(value)
    if not text or text in {"-", "–", "—"}:
        return None
    if not re.fullmatch(r"[-+]?\d[\d,]*(?:\.\d+)?", text):
        return None
    return float(text.replace(",", ""))


def int_value(value: Any) -> int | None:
    number = number_or_none(value)
    if number is None:
        return None
    return int(number)


def summarize(source_rows: list[dict[str, Any]], row_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "provider": "adiga",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sources": len(source_rows),
        "sourceRows": source_rows,
        "rowCandidates": len(row_candidates),
        "uniqueCandidateSha256": len({row["candidateSha256"] for row in row_candidates}),
        "metricValues": sum(int(row.get("metricCount") or 0) for row in row_candidates),
        "subjectMetricValues": sum(int(row.get("subjectMetricCount") or 0) for row in row_candidates),
        "universities": len({row["unvCd"] for row in row_candidates if row.get("unvCd")}),
        "admissionUnitNameCandidates": len(
            {row["admissionUnitCanonicalCandidate"] for row in row_candidates if row.get("admissionUnitCanonicalCandidate")}
        ),
        "rowsWithQuotaAndCompetition": sum(1 for row in row_candidates if row.get("hasQuotaAndCompetition")),
        "rowsWithOutcomeScore": sum(1 for row in row_candidates if row.get("hasOutcomeScore")),
        "byYear": count_by(row_candidates, "year"),
        "byRecruitmentGroup": count_by(row_candidates, "recruitmentGroup"),
        "byScoreAvailability": count_by(row_candidates, "scoreAvailability"),
        "notes": [
            "Rows are HistoricalOutcome candidates parsed from official Adiga CSAT-track outcome tables.",
            "Metric labels preserve the original candidate fields; final promotion requires admin review and AdmissionUnit canonical mapping.",
            "Image-only tables are not normalized here and remain in the raw HTML/image URL layer.",
        ],
    }


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(str(row.get(key) if row.get(key) is not None else "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "recruitmentGroup",
        "admissionUnitName",
        "quota",
        "competitionRate",
        "additionalPass",
        "convertedScore50Cut",
        "convertedScore70Cut",
        "totalScore",
        "percentile70Average",
        "metricCount",
        "subjectMetricCount",
        "scoreAvailability",
        "sourceUrl",
        "rawPath",
        "sectionId",
        "tableIndex",
        "rowIndex",
        "candidateSha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in headers})


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


if __name__ == "__main__":
    main()
