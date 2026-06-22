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
DEFAULT_ADIGA_DIR = "packages/reference-data/data/public/adiga/extracted"
DEFAULT_DECISION_LOG = "foundation_operational_review_decision_log.csv"
DEFAULT_ADMISSION_UNITS = "foundation_admission_units.csv"
DEFAULT_ADIGA_OUTCOMES = "adiga_csat_outcome_row_candidates.csv"
OUTPUT_SUMMARY = "foundation_adiga_admission_unit_review_summary.json"

REVIEWER = "codex-adiga-admission-unit-row-audit-v1"
APPROVAL_NOTE = (
    "Strict ADIGA AdmissionUnit audit: foundation unit sourceCandidateSha256Values "
    "included an ADIGA CSAT outcome candidate, unit year/unvCd/name/group/quota matched "
    "that candidate, and the extracted table grid row contained the admission unit, "
    "explicit recruitment group, and quota."
)

GROUP_TEXT = {
    "ga": "가군",
    "na": "나군",
    "da": "다군",
    "none": "",
}


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    adiga_dir = resolve(repo_root, args.adiga_dir)
    decision_log_path = foundation_dir / args.decision_log_csv
    admission_units_path = foundation_dir / args.admission_units_csv
    adiga_outcomes_path = adiga_dir / args.adiga_outcomes_csv

    decision_rows = list(read_csv(decision_log_path))
    admission_units = {
        normalize_text(row.get("unitCandidateId")): row
        for row in read_csv(admission_units_path)
        if normalize_text(row.get("unitCandidateId"))
    }
    adiga_candidates = {
        normalize_text(row.get("candidateSha256")): row
        for row in read_csv(adiga_outcomes_path)
        if normalize_text(row.get("candidateSha256"))
    }
    table_cache: dict[str, dict[tuple[str, str, str, str], dict[str, Any]]] = {}

    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    results = []
    changed = 0
    for row in decision_rows:
        if normalize_text(row.get("sourceArtifact")) != "foundation_admission_units":
            continue
        if normalize_text(row.get("reviewOutcome")) != "pending":
            continue
        result = verify_adiga_admission_unit_row(
            adiga_dir,
            row,
            admission_units,
            adiga_candidates,
            table_cache,
        )
        results.append(result)
        if result["status"] != "matched":
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

    write_csv(decision_log_path, decision_rows, decision_rows[0].keys() if decision_rows else [])
    summary = summarize(
        repo_root=repo_root,
        decision_log_path=decision_log_path,
        admission_units_path=admission_units_path,
        adiga_outcomes_path=adiga_outcomes_path,
        results=results,
        changed=changed,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation ADIGA AdmissionUnit review complete. "
        f"matched={summary['matchedRows']} changed={changed} output={to_repo_relative(decision_log_path, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--adiga-dir", default=DEFAULT_ADIGA_DIR)
    parser.add_argument("--decision-log-csv", default=DEFAULT_DECISION_LOG)
    parser.add_argument("--admission-units-csv", default=DEFAULT_ADMISSION_UNITS)
    parser.add_argument("--adiga-outcomes-csv", default=DEFAULT_ADIGA_OUTCOMES)
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


def verify_adiga_admission_unit_row(
    adiga_dir: Path,
    decision_row: dict[str, str],
    admission_units: dict[str, dict[str, str]],
    adiga_candidates: dict[str, dict[str, str]],
    table_cache: dict[str, dict[tuple[str, str, str, str], dict[str, Any]]],
) -> dict[str, Any]:
    source_record_id = normalize_text(decision_row.get("sourceRecordId"))
    unit = admission_units.get(source_record_id)
    if unit is None:
        return result(decision_row, "missing_admission_unit", "No foundation admission unit row found.")

    candidate_shas = split_values(unit.get("sourceCandidateSha256Values"))
    candidates = [adiga_candidates[sha] for sha in candidate_shas if sha in adiga_candidates]
    if not candidates:
        return result(
            decision_row,
            "no_adiga_outcome_sha",
            "No ADIGA CSAT outcome candidateSha256 was found in sourceCandidateSha256Values.",
        )

    failures = Counter()
    failure_details = []
    for candidate in candidates:
        status, detail = verify_candidate(adiga_dir, decision_row, unit, candidate, table_cache)
        if status == "matched":
            output = result(decision_row, "matched", detail)
            output["matchedCandidateSha256"] = candidate.get("candidateSha256", "")
            return output
        failures[status] += 1
        failure_details.append(f"{status}: {detail}")

    output = result(
        decision_row,
        "no_strict_candidate",
        "; ".join(failure_details[:4]),
    )
    output["candidateFailureStatuses"] = dict(sorted(failures.items()))
    return output


def verify_candidate(
    adiga_dir: Path,
    decision_row: dict[str, str],
    unit: dict[str, str],
    candidate: dict[str, str],
    table_cache: dict[str, dict[tuple[str, str, str, str], dict[str, Any]]],
) -> tuple[str, str]:
    if normalize_text(unit.get("year")) != normalize_text(candidate.get("year")):
        return "candidate_field_mismatch_year", "Unit year differs from ADIGA candidate year."
    if normalize_text(decision_row.get("admissionYear")) != normalize_text(candidate.get("year")):
        return "candidate_field_mismatch_admissionYear", "Decision admissionYear differs from ADIGA candidate year."
    if normalize_text(unit.get("unvCd")) != normalize_text(candidate.get("unvCd")):
        return "candidate_field_mismatch_unvCd", "Unit unvCd differs from ADIGA candidate unvCd."

    candidate_unit_name = normalize_compact(candidate.get("admissionUnitName"))
    unit_names = {
        normalize_compact(unit.get("admissionUnitName")),
        normalize_compact(unit.get("admissionUnitCanonicalName")),
        normalize_compact(decision_row.get("admissionUnitName")),
    }
    unit_names.discard("")
    if candidate_unit_name not in unit_names:
        return "candidate_field_mismatch_admissionUnitName", "Unit name differs from ADIGA candidate admissionUnitName."

    if normalize_text(unit.get("recruitmentGroup")) != normalize_text(candidate.get("recruitmentGroup")):
        return "candidate_field_mismatch_recruitmentGroup", "Unit recruitmentGroup differs from ADIGA candidate."
    if normalize_text(decision_row.get("recruitmentGroup")) != normalize_text(candidate.get("recruitmentGroup")):
        return "candidate_field_mismatch_decisionRecruitmentGroup", "Decision recruitmentGroup differs from ADIGA candidate."

    expected_quota = first_quota(unit.get("quotaCandidates"))
    candidate_quota = normalize_number(candidate.get("quota"))
    if expected_quota and expected_quota != candidate_quota:
        return "candidate_value_mismatch_quota", "First unit quota candidate differs from ADIGA candidate quota."

    table = table_for_candidate(adiga_dir, candidate, table_cache)
    if table is None:
        return "missing_extracted_table", "No extracted ADIGA table found for source coordinates."
    grid = table.get("grid") if isinstance(table.get("grid"), list) else []
    row_index = int_or_none(candidate.get("rowIndex"))
    if row_index is None or row_index < 1 or row_index > len(grid):
        return "row_out_of_bounds", "rowIndex is outside extracted table grid."
    raw_row = grid[row_index - 1]
    if not isinstance(raw_row, list):
        return "invalid_grid_row", "Extracted table grid row is not a list."

    cells = [clean_cell(cell) for cell in raw_row]
    row_text = " ".join(cells)
    if candidate_unit_name not in normalize_compact(row_text):
        return "unit_not_in_row", "Admission unit name not found in extracted table row."

    group = GROUP_TEXT.get(normalize_text(candidate.get("recruitmentGroup")), "")
    if group and group not in row_text:
        return "group_not_in_row", "Recruitment group is not explicit in this row; manual review is required."

    if expected_quota:
        row_numbers = {normalize_number(cell) for cell in cells if normalize_number(cell)}
        if expected_quota not in row_numbers:
            return "raw_row_value_missing_quota", f"value={expected_quota} row={row_text[:500]}"

    return "matched", "Strict ADIGA candidate and extracted-table row checks passed."


def table_for_candidate(
    adiga_dir: Path,
    candidate: dict[str, str],
    table_cache: dict[str, dict[tuple[str, str, str, str], dict[str, Any]]],
) -> dict[str, Any] | None:
    year = normalize_text(candidate.get("year"))
    if year not in table_cache:
        table_cache[year] = load_tables(adiga_dir / f"adiga_extracted_tables_{year}.jsonl")
    key = (
        normalize_text(candidate.get("unvCd")),
        normalize_text(candidate.get("sectionId")),
        normalize_text(candidate.get("tableIndex")),
        normalize_text(candidate.get("rawPath")),
    )
    return table_cache[year].get(key)


def load_tables(path: Path) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    output: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    if not path.exists():
        return output
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                table = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (
                normalize_text(table.get("unvCd")),
                normalize_text(table.get("sectionId")),
                normalize_text(table.get("tableIndex")),
                normalize_text(table.get("rawPath")),
            )
            output[key] = table
    return output


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
    adiga_outcomes_path: Path,
    results: list[dict[str, Any]],
    changed: int,
) -> dict[str, Any]:
    by_status = Counter(str(row.get("status") or "") for row in results)
    failure_statuses = Counter()
    for row in results:
        statuses = row.get("candidateFailureStatuses")
        if isinstance(statuses, dict):
            failure_statuses.update({str(key): int(value) for key, value in statuses.items()})
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_adiga_admission_unit_review_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "decisionLogCsv": to_repo_relative(decision_log_path, repo_root),
            "admissionUnitsCsv": to_repo_relative(admission_units_path, repo_root),
            "adigaOutcomesCsv": to_repo_relative(adiga_outcomes_path, repo_root),
        },
        "reviewer": REVIEWER,
        "candidateRows": len(results),
        "matchedRows": by_status.get("matched", 0),
        "changedRows": changed,
        "byStatus": dict(sorted(by_status.items())),
        "candidateFailureStatuses": dict(sorted(failure_statuses.items())),
        "notes": [
            "Only pending AdmissionUnit decision-log rows are modified.",
            "Rows are approved only when a unit sourceCandidateSha256Values entry maps to an ADIGA CSAT outcome candidate and the unit year/unvCd/name/group/quota match that candidate.",
            "The extracted ADIGA table row must contain the unit name and explicit recruitment group; carry-forward recruitment group rows remain pending.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: Iterable[str]) -> None:
    fields = list(fieldnames)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def clean_cell(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"\s*/\s*$", "", text)
    return text.strip()


def split_values(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [part for part in re.split(r"[|,;/\s]+", text) if part]


def first_quota(value: Any) -> str:
    for part in split_values(value):
        quota = normalize_number(part)
        if quota:
            return quota
    return ""


def normalize_number(value: Any) -> str:
    text = normalize_text(value).replace(",", "")
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if match is None:
            return ""
        number = float(match.group(0))
    if number.is_integer():
        return str(int(number))
    return f"{number:.10f}".rstrip("0").rstrip(".")


def int_or_none(value: Any) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


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
