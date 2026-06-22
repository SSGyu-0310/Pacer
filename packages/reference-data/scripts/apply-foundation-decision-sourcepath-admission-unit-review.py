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


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_DECISION_LOG = "foundation_operational_review_decision_log.csv"
DEFAULT_ADMISSION_UNITS = "foundation_admission_units.csv"
OUTPUT_SUMMARY = "foundation_decision_sourcepath_admission_unit_review_summary.json"

REVIEWER = "codex-decision-sourcepath-admission-unit-row-audit-v1"
APPROVAL_NOTE = (
    "Strict decision sourcePath AdmissionUnit audit: decision bundle source CSV was opened "
    "directly, and one extracted row contained the admission unit, admission year, "
    "recruitment group where applicable, and a matching quota candidate."
)

GROUP_LABELS = {
    "ga": ("가", "가군"),
    "na": ("나", "나군"),
    "da": ("다", "다군"),
    "none": (),
}


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    decision_log_path = foundation_dir / args.decision_log_csv
    admission_units_path = foundation_dir / args.admission_units_csv

    decision_rows = list(read_csv(decision_log_path))
    admission_units = {
        normalize_text(row.get("unitCandidateId")): row
        for row in read_csv(admission_units_path)
        if normalize_text(row.get("unitCandidateId"))
    }
    source_row_cache: dict[str, list[dict[str, Any]]] = {}

    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    results = []
    changed = 0
    for row in decision_rows:
        if normalize_text(row.get("sourceArtifact")) != "foundation_admission_units":
            continue
        if normalize_text(row.get("reviewOutcome")) != "pending":
            continue
        if normalize_text(row.get("primaryEvidenceKind")) != "source_text":
            continue
        unit = admission_units.get(normalize_text(row.get("sourceRecordId")))
        if unit is None:
            results.append(result(row, "missing_admission_unit", "No foundation admission unit row found."))
            continue
        if not quota_candidates(unit.get("quotaCandidates")):
            results.append(result(row, "missing_quota_candidates", "AdmissionUnit has no quotaCandidates."))
            continue
        verify_result = verify_sourcepath_admission_unit(repo_root, row, unit, source_row_cache)
        results.append(verify_result)
        if verify_result["status"] != "matched":
            continue
        if args.dry_run:
            continue
        row["decisionStatus"] = "reviewed"
        row["reviewOutcome"] = "approved"
        row["reviewedVerifiedStatus"] = "verified"
        row["reviewer"] = REVIEWER
        row["reviewedAt"] = reviewed_at
        row["sourceMatchStatus"] = "matched"
        row["valueMatchStatus"] = "matched"
        row["reviewNotes"] = APPROVAL_NOTE
        row["followupAction"] = ""
        row["rejectionReason"] = ""
        changed += 1

    if not args.dry_run:
        write_csv(decision_log_path, decision_rows, decision_rows[0].keys() if decision_rows else [])
    summary = summarize(
        repo_root=repo_root,
        decision_log_path=decision_log_path,
        admission_units_path=admission_units_path,
        results=results,
        changed=changed,
        dry_run=args.dry_run,
    )
    if not args.dry_run:
        (foundation_dir / OUTPUT_SUMMARY).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        "foundation decision sourcePath AdmissionUnit review complete. "
        f"matched={summary['matchedRows']} changed={changed} dryRun={args.dry_run}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--decision-log-csv", default=DEFAULT_DECISION_LOG)
    parser.add_argument("--admission-units-csv", default=DEFAULT_ADMISSION_UNITS)
    parser.add_argument("--dry-run", action="store_true")
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


def verify_sourcepath_admission_unit(
    repo_root: Path,
    decision_row: dict[str, str],
    unit: dict[str, str],
    source_row_cache: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    source_paths = candidate_source_paths(decision_row, unit.get("year"))
    if not source_paths:
        return result(decision_row, "missing_source_paths", "Decision row has no source CSV paths.")
    failures = Counter()
    for source_path in source_paths:
        rows = source_rows(repo_root, source_path, source_row_cache)
        if not rows:
            failures["source_path_missing_or_empty"] += 1
            continue
        status, detail = match_source_row(unit, rows)
        if status == "matched":
            output = result(decision_row, "matched", f"{detail} sourcePath={source_path}")
            output["matchedSourcePath"] = source_path
            return output
        failures[status] += 1
    output = result(
        decision_row,
        "no_strict_source_row",
        ", ".join(f"{key}={value}" for key, value in sorted(failures.items())),
    )
    output["sourceRowFailureStatuses"] = dict(sorted(failures.items()))
    return output


def candidate_source_paths(decision_row: dict[str, str], year: Any) -> list[str]:
    values: list[str] = []
    primary = normalize_text(decision_row.get("primaryEvidencePath"))
    if primary:
        values.append(primary)
    coordinates = normalize_text(decision_row.get("sourceCoordinates"))
    match = re.search(r"sourcePaths=([^;]+)", coordinates)
    if match:
        values.extend(part for part in match.group(1).split("|") if part)
    year_text = normalize_text(year)
    csv_paths = []
    for value in values:
        if value.endswith(".csv") and value not in csv_paths:
            csv_paths.append(value)
    preferred = [path for path in csv_paths if f"/{year_text}/" in path]
    return preferred or csv_paths


def source_rows(
    repo_root: Path,
    source_path: str,
    source_row_cache: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    normalized_path = normalize_text(source_path)
    if normalized_path in source_row_cache:
        return source_row_cache[normalized_path]
    path = resolve(repo_root, normalized_path)
    if not path.exists() or path.suffix.lower() != ".csv":
        source_row_cache[normalized_path] = []
        return []
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for index, cells in enumerate(csv.reader(handle)):
            cleaned = [normalize_text(cell) for cell in cells]
            row_text = " ".join(cell for cell in cleaned if cell)
            if not row_text:
                continue
            rows.append(
                {
                    "rowIndex": index,
                    "cells": cleaned,
                    "rowText": row_text,
                    "compactText": normalize_compact(row_text),
                    "numbers": numbers_in_text(row_text),
                }
            )
    source_row_cache[normalized_path] = rows
    return rows


def match_source_row(unit: dict[str, str], rows: list[dict[str, Any]]) -> tuple[str, str]:
    unit_names = {
        normalize_compact(unit.get("admissionUnitName")),
        normalize_compact(unit.get("admissionUnitCanonicalName")),
    }
    unit_names.discard("")
    if not unit_names:
        return "missing_unit_name", "AdmissionUnit has no unit name."
    year_value = number_or_none(unit.get("year"))
    if year_value is None:
        return "missing_year", "AdmissionUnit has no year."
    quota_values = quota_candidates(unit.get("quotaCandidates"))
    if not quota_values:
        return "missing_quota_candidates", "AdmissionUnit has no quotaCandidates."

    unit_rows = [
        row
        for row in rows
        if any(unit_name in row["compactText"] for unit_name in unit_names)
    ]
    if not unit_rows:
        return "unit_not_in_source_row", "No source row contains the admission unit name."
    year_rows = [row for row in unit_rows if number_present(year_value, row["numbers"], 0.001)]
    if not year_rows:
        return "year_not_in_source_row", "No unit row contains the admission year."
    unit_rows = year_rows

    group = normalize_text(unit.get("recruitmentGroup"))
    if group != "none":
        grouped_rows = [row for row in unit_rows if group_present(group, row["cells"], row["rowText"])]
        if not grouped_rows:
            return "group_not_in_source_row", "No unit row contains the explicit recruitment group."
        unit_rows = grouped_rows

    for row in unit_rows:
        if any(number_present(quota, row["numbers"], 0.001) for quota in quota_values):
            return "matched", f"Source rowIndex={row['rowIndex']} matched unit/year/group/quota."
    return "quota_not_in_source_row", "No unit row contains any quotaCandidates value."


def group_present(group: str, cells: list[str], row_text: str) -> bool:
    labels = GROUP_LABELS.get(group, ())
    if not labels:
        return True
    for cell in cells:
        normalized = normalize_text(cell)
        compact = normalize_compact(cell)
        for label in labels:
            if normalized == label or compact == label:
                return True
            if label.endswith("군") and label in normalized:
                return True
            if label in {"가", "나", "다"} and re.search(rf"\({label}\)\s*군", normalized):
                return True
    return any(label.endswith("군") and label in row_text for label in labels)


def quota_candidates(value: Any) -> list[float]:
    output = []
    for part in re.split(r"[|,;/\s]+", normalize_text(value)):
        if not part:
            continue
        number = number_or_none(part)
        if number is not None:
            output.append(number)
    return output


def number_present(target: float, candidates: list[float], tolerance: float) -> bool:
    return any(abs(candidate - target) <= tolerance for candidate in candidates)


def numbers_in_text(value: Any) -> list[float]:
    text = normalize_text(value).replace(",", "")
    output = []
    for match in re.finditer(r"-?\d+(?:\.\d+)?", text):
        number = number_or_none(match.group(0))
        if number is not None:
            output.append(number)
    return output


def number_or_none(value: Any) -> float | None:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match is None:
            return None
        return float(match.group(0))


def result(row: dict[str, str], status: str, detail: str) -> dict[str, Any]:
    return {
        "reviewDecisionId": row.get("reviewDecisionId", ""),
        "sourceRecordId": row.get("sourceRecordId", ""),
        "admissionYear": row.get("admissionYear", ""),
        "unvCd": row.get("unvCd", ""),
        "universityName": row.get("universityName", ""),
        "admissionUnitName": row.get("admissionUnitName", ""),
        "recruitmentGroup": row.get("recruitmentGroup", ""),
        "status": status,
        "detail": detail,
    }


def summarize(
    *,
    repo_root: Path,
    decision_log_path: Path,
    admission_units_path: Path,
    results: list[dict[str, Any]],
    changed: int,
    dry_run: bool,
) -> dict[str, Any]:
    by_status = Counter(str(row.get("status") or "") for row in results)
    row_failures = Counter()
    for row in results:
        statuses = row.get("sourceRowFailureStatuses")
        if isinstance(statuses, dict):
            row_failures.update({str(key): int(value) for key, value in statuses.items()})
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_decision_sourcepath_admission_unit_review_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "decisionLogCsv": to_repo_relative(decision_log_path, repo_root),
            "admissionUnitsCsv": to_repo_relative(admission_units_path, repo_root),
        },
        "reviewer": REVIEWER,
        "dryRun": dry_run,
        "candidateRows": len(results),
        "matchedRows": by_status.get("matched", 0),
        "changedRows": changed,
        "byStatus": dict(sorted(by_status.items())),
        "sourceRowFailureStatuses": dict(sorted(row_failures.items())),
        "notes": [
            "Only pending AdmissionUnit rows with source_text evidence and non-empty quotaCandidates are considered.",
            "The script opens decision-row source CSV paths directly instead of relying on sourceCandidateSha256 linkage.",
            "Approval requires one extracted row containing unit name, admission year, recruitment group where applicable, and a matching quota candidate.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    fields = list(fieldnames)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def normalize_compact(value: Any) -> str:
    return normalize_text(value).replace(" ", "")


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
