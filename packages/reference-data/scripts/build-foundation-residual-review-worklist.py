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
DEFAULT_HISTORICAL_OUTCOMES = "foundation_historical_outcomes.csv"
OUTPUT_CSV = "foundation_residual_review_worklist.csv"
OUTPUT_SUMMARY = "foundation_residual_review_worklist_summary.json"


FIELDNAMES = [
    "residualWorkId",
    "residualCategory",
    "residualPriority",
    "delegateTrack",
    "autoApprovalAllowed",
    "blockedBy",
    "recommendedProtocol",
    "verificationRequirement",
    "reviewDecisionId",
    "reviewLane",
    "targetEntity",
    "sourceArtifact",
    "sourceRecordId",
    "promotionAction",
    "admissionYear",
    "academicYear",
    "examType",
    "unvCd",
    "universityName",
    "admissionUnitName",
    "recruitmentGroup",
    "provider",
    "primaryEvidenceKind",
    "quotaCandidates",
    "outcomeRows",
    "sourceRecordSummary",
    "candidateValueSummary",
    "primaryEvidencePath",
    "sourcePaths",
    "sourceUrls",
    "attachmentUrls",
    "rawPaths",
    "evidenceSnippet",
]


CATEGORY_INFO = {
    "adiga_admission_unit_identity_only_missing_quota": {
        "priority": "P1",
        "track": "adiga_parser_or_manual_quota",
        "auto": "no",
        "blockedBy": "AdmissionUnit quotaCandidates is blank. The source proves unit identity, but exact_record approval would also certify the blank quota.",
        "protocol": "Reopen the ADIGA selection/outcome table for the same year and unvCd, reconstruct the quota column for the unit row, then update the unit candidate or create a manual supplement before exact-record review.",
        "verification": "The reviewed row must show admission unit, recruitment group where applicable, and quota in the same table row or in an auditable carry-forward table structure.",
    },
    "admission_unit_source_text_missing_quota": {
        "priority": "P1",
        "track": "office_parser_or_manual_quota",
        "auto": "no",
        "blockedBy": "AdmissionUnit quotaCandidates is blank in an office source-text row.",
        "protocol": "Open the linked office source or extracted table, find the quota column for the unit, and add a source-backed quota supplement before approving the exact record.",
        "verification": "The reviewed source row must contain the unit name, year, group where applicable, and quota.",
    },
    "admission_unit_source_text_missing_source_paths": {
        "priority": "P2",
        "track": "html_or_text_extraction",
        "auto": "no",
        "blockedBy": "The decision bundle does not expose a usable extracted CSV sourcePath for strict row matching.",
        "protocol": "Run or improve HTML/PDF/workbook extraction for this university-year so sourcePaths point to row-level CSV; then rerun the decision sourcePath AdmissionUnit audit.",
        "verification": "A row-level CSV sourcePath must be present and must contain unit, year, group where applicable, and one quota candidate.",
    },
    "admission_unit_source_text_strict_row_mismatch": {
        "priority": "P2",
        "track": "office_table_parser",
        "auto": "no",
        "blockedBy": "A row-level sourcePath exists, but strict unit/year/group/quota matching did not pass.",
        "protocol": "Inspect whether the source table is split across header/body rows, merged cells, or multi-line unit names; add a targeted parser or manually review the row.",
        "verification": "Do not approve until unit, year, group where applicable, and quota can be traced to the same source row or a documented table carry-forward rule.",
    },
    "office_pdf_outcome_column_reconstruction_required": {
        "priority": "P1",
        "track": "pdf_table_column_reconstruction",
        "auto": "no",
        "blockedBy": "PDF text snippets are page-level or line-level and can mix registration counts, rates, pass ranks, and scores.",
        "protocol": "Reconstruct the PDF/OCR table columns for the page before review. Match unit, group where applicable, quota, competition, additional-pass/rank, and score fields by column, not by loose line numbers.",
        "verification": "The exact PDF/OCR table row must identify each numeric field's column. Loose numeric containment is forbidden.",
    },
    "office_workbook_outcome_strict_mismatch": {
        "priority": "P1",
        "track": "workbook_table_parser_or_manual",
        "auto": "no",
        "blockedBy": "The office workbook/raw binary evidence did not pass strict row/value matching.",
        "protocol": "Open the workbook-derived CSV or raw workbook, check merged cells and hidden sheets, then add a targeted parser or manually verify the exact HistoricalOutcome row.",
        "verification": "The reviewed row must contain unit, group where applicable, quota, competition, and at least one outcome score/pass metric in the correct columns.",
    },
    "admission_rule_2027_formula_human_review_required": {
        "priority": "P2",
        "track": "rule_formula_review",
        "auto": "no",
        "blockedBy": "2027 rule/schedule draft needs formula interpretation from the official rule source.",
        "protocol": "Review the official 2027 모집요강 source text for the university-year, confirm the parsed formula/schedule fields, then approve the rule source only if the source text supports it.",
        "verification": "The reviewed source must support the parsed rule formula or schedule fields; do not treat this as 2027 outcome/result data.",
    },
    "unclassified_pending_review": {
        "priority": "P3",
        "track": "manual_triage",
        "auto": "no",
        "blockedBy": "Pending row does not match a known residual pattern.",
        "protocol": "Inspect the decision bundle and classify the row before source review.",
        "verification": "Record the concrete source and value match requirements before approval.",
    },
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
    historical_outcomes_path = foundation_dir / args.historical_outcomes_csv
    output_csv_path = foundation_dir / args.output_csv
    output_summary_path = foundation_dir / args.output_summary

    decision_rows = list(read_csv(decision_log_path))
    admission_units = {
        normalize_text(row.get("unitCandidateId")): row
        for row in read_csv(admission_units_path)
        if normalize_text(row.get("unitCandidateId"))
    }
    historical_outcomes = {
        normalize_text(row.get("outcomeCandidateId")): row
        for row in read_csv(historical_outcomes_path)
        if normalize_text(row.get("outcomeCandidateId"))
    }

    pending_rows = [
        row
        for row in decision_rows
        if normalize_text(row.get("reviewOutcome")) == "pending"
    ]
    worklist_rows = [
        build_worklist_row(index, row, admission_units, historical_outcomes)
        for index, row in enumerate(pending_rows, start=1)
    ]

    write_csv(output_csv_path, worklist_rows, FIELDNAMES)
    summary = summarize(
        repo_root=repo_root,
        output_csv_path=output_csv_path,
        decision_log_path=decision_log_path,
        rows=worklist_rows,
    )
    output_summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation residual review worklist complete. "
        f"rows={len(worklist_rows)} categories={len(summary['byResidualCategory'])} "
        f"output={to_repo_relative(output_csv_path, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--decision-log-csv", default=DEFAULT_DECISION_LOG)
    parser.add_argument("--admission-units-csv", default=DEFAULT_ADMISSION_UNITS)
    parser.add_argument("--historical-outcomes-csv", default=DEFAULT_HISTORICAL_OUTCOMES)
    parser.add_argument("--output-csv", default=OUTPUT_CSV)
    parser.add_argument("--output-summary", default=OUTPUT_SUMMARY)
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


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_worklist_row(
    index: int,
    decision_row: dict[str, str],
    admission_units: dict[str, dict[str, str]],
    historical_outcomes: dict[str, dict[str, str]],
) -> dict[str, str]:
    source_record_id = normalize_text(decision_row.get("sourceRecordId"))
    unit = admission_units.get(source_record_id, {})
    outcome = historical_outcomes.get(source_record_id, {})
    source_record = unit or outcome
    category = classify(decision_row, unit, outcome)
    info = CATEGORY_INFO[category]
    return {
        "residualWorkId": f"residual-review-{index:05d}",
        "residualCategory": category,
        "residualPriority": info["priority"],
        "delegateTrack": info["track"],
        "autoApprovalAllowed": info["auto"],
        "blockedBy": info["blockedBy"],
        "recommendedProtocol": info["protocol"],
        "verificationRequirement": info["verification"],
        "reviewDecisionId": normalize_text(decision_row.get("reviewDecisionId")),
        "reviewLane": normalize_text(decision_row.get("reviewLane")),
        "targetEntity": normalize_text(decision_row.get("targetEntity")),
        "sourceArtifact": normalize_text(decision_row.get("sourceArtifact")),
        "sourceRecordId": source_record_id,
        "promotionAction": normalize_text(decision_row.get("promotionAction")),
        "admissionYear": normalize_text(decision_row.get("admissionYear")),
        "academicYear": normalize_text(decision_row.get("academicYear")),
        "examType": normalize_text(decision_row.get("examType")),
        "unvCd": normalize_text(decision_row.get("unvCd")),
        "universityName": normalize_text(decision_row.get("universityName")),
        "admissionUnitName": normalize_text(decision_row.get("admissionUnitName")),
        "recruitmentGroup": normalize_text(decision_row.get("recruitmentGroup")),
        "provider": normalize_text(decision_row.get("provider")),
        "primaryEvidenceKind": normalize_text(decision_row.get("primaryEvidenceKind")),
        "quotaCandidates": normalize_text(source_record.get("quotaCandidates")),
        "outcomeRows": normalize_text(source_record.get("outcomeRows")),
        "sourceRecordSummary": normalize_text(decision_row.get("sourceRecordSummary")),
        "candidateValueSummary": normalize_text(decision_row.get("candidateValueSummary")),
        "primaryEvidencePath": normalize_text(decision_row.get("primaryEvidencePath")),
        "sourcePaths": normalize_text(decision_row.get("sourcePaths")),
        "sourceUrls": normalize_text(decision_row.get("sourceUrls")),
        "attachmentUrls": normalize_text(decision_row.get("attachmentUrls")),
        "rawPaths": normalize_text(decision_row.get("rawPaths")),
        "evidenceSnippet": normalize_text(decision_row.get("evidenceSnippet")),
    }


def classify(
    decision_row: dict[str, str],
    unit: dict[str, str],
    outcome: dict[str, str],
) -> str:
    target = normalize_text(decision_row.get("targetEntity"))
    lane = normalize_text(decision_row.get("reviewLane"))
    provider = normalize_text(decision_row.get("provider"))
    evidence_kind = normalize_text(decision_row.get("primaryEvidenceKind"))

    if lane == "rule_schedule_2027" or target == "AdmissionRule":
        return "admission_rule_2027_formula_human_review_required"
    if target == "HistoricalOutcome" and evidence_kind == "pdf_text_manifest":
        return "office_pdf_outcome_column_reconstruction_required"
    if target == "HistoricalOutcome" and evidence_kind == "raw_binary":
        return "office_workbook_outcome_strict_mismatch"
    if target == "AdmissionUnit" and provider == "adiga" and evidence_kind == "raw_text":
        if not normalize_text(unit.get("quotaCandidates")):
            return "adiga_admission_unit_identity_only_missing_quota"
        return "admission_unit_source_text_strict_row_mismatch"
    if target == "AdmissionUnit" and evidence_kind == "source_text":
        if not normalize_text(unit.get("quotaCandidates")):
            return "admission_unit_source_text_missing_quota"
        if not extracted_csv_source_paths(decision_row):
            return "admission_unit_source_text_missing_source_paths"
        return "admission_unit_source_text_strict_row_mismatch"
    return "unclassified_pending_review"


def extracted_csv_source_paths(decision_row: dict[str, str]) -> list[str]:
    values: list[str] = []
    for field in ("primaryEvidencePath", "sourcePaths"):
        values.extend(split_values(decision_row.get(field)))
    coordinates = normalize_text(decision_row.get("sourceCoordinates"))
    match = re.search(r"sourcePaths=([^;]+)", coordinates)
    if match:
        values.extend(split_values(match.group(1)))
    output = []
    for value in values:
        cleaned = normalize_text(value)
        if cleaned.endswith(".csv") and cleaned not in output:
            output.append(cleaned)
    return output


def split_values(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"[|,]", text) if part.strip()]


def summarize(
    repo_root: Path,
    output_csv_path: Path,
    decision_log_path: Path,
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    by_category = Counter(row["residualCategory"] for row in rows)
    by_priority = Counter(row["residualPriority"] for row in rows)
    by_track = Counter(row["delegateTrack"] for row in rows)
    by_target = Counter(row["targetEntity"] for row in rows)
    by_lane = Counter(row["reviewLane"] for row in rows)
    by_year = Counter(row["admissionYear"] or row["academicYear"] for row in rows)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_residual_review_worklist_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "decisionLogCsv": to_repo_relative(decision_log_path, repo_root),
        },
        "outputs": {
            "worklistCsv": to_repo_relative(output_csv_path, repo_root),
        },
        "counts": {
            "rows": len(rows),
            "autoApprovalAllowedRows": sum(1 for row in rows if row["autoApprovalAllowed"] == "yes"),
            "autoApprovalForbiddenRows": sum(1 for row in rows if row["autoApprovalAllowed"] == "no"),
        },
        "byResidualCategory": dict(sorted(by_category.items())),
        "byResidualPriority": dict(sorted(by_priority.items())),
        "byDelegateTrack": dict(sorted(by_track.items())),
        "byTargetEntity": dict(sorted(by_target.items())),
        "byReviewLane": dict(sorted(by_lane.items())),
        "byAdmissionYear": dict(sorted(by_year.items())),
    }


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
