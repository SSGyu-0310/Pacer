#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = "packages/reference-data/data/public/foundation/foundation_reference.sqlite"
DEFAULT_OUTPUT = "packages/reference-data/data/public/foundation/foundation_data_completeness_summary.json"
DEFAULT_EXCEPTIONS = "packages/reference-data/data/public/foundation/foundation_data_completeness_exceptions.csv"

ZERO_QUEUE_TABLES = [
    "foundation_gap_source_candidates",
    "foundation_gap_collection_targets",
    "foundation_gap_crawler_worklist",
    "foundation_gap_visual_review_queue",
    "foundation_gap_adiga_parser_review_queue",
    "foundation_gap_image_source_candidates",
]

EXCEPTION_FIELDNAMES = [
    "unvCd",
    "universityName",
    "admissionYear",
    "coverageTier",
    "coverageScore",
    "scopeOverrideStatuses",
    "scopeExcludedMissingFlags",
    "scopeOverrideNotes",
    "admissionUnitCandidates",
    "historicalOutcomeCandidates",
    "outcomeScoreCandidates",
    "quotaCompetitionCandidates",
    "admissionOfficeDetectedYearEvidence",
    "admissionOfficeCollectionYearEvidence",
    "admissionOfficeTargets",
    "promotionQueueP0Rows",
    "promotionQueueP1Rows",
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    db_path = resolve(repo_root, args.db)
    output_path = resolve(repo_root, args.output)
    exceptions_path = resolve(repo_root, args.exceptions)
    years = parse_years(args.years)

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    errors: list[str] = []
    warnings: list[str] = []
    integrity = con.execute("pragma integrity_check").fetchone()[0]
    if integrity != "ok":
        errors.append(f"sqlite integrity_check={integrity}")

    coverage_rows = query(
        con,
        """
        select *
        from foundation_university_year_coverage
        where admission_year in ({placeholders})
          and university_listed_in_year='true'
        order by admission_year, university_name, unv_cd
        """.format(placeholders=",".join("?" for _ in years)),
        years,
    )
    found_years = sorted({row["admission_year"] for row in coverage_rows})
    missing_years = [year for year in years if year not in found_years]
    if missing_years:
        errors.append(f"coverage missing requested years: {missing_years}")

    coverage_by_year_tier: dict[str, dict[str, int]] = defaultdict(dict)
    metrics_by_year: dict[str, dict[str, int]] = {}
    exception_rows: list[dict[str, str]] = []
    rows_without_scope_override = 0

    for year in years:
        year_rows = [row for row in coverage_rows if row["admission_year"] == year]
        tier_counts = Counter(row["coverage_tier"] for row in year_rows)
        coverage_by_year_tier[year] = dict(sorted(tier_counts.items()))
        metrics_by_year[year] = {
            "cells": len(year_rows),
            "sourceRichReviewReady": tier_counts.get("source_rich_review_ready", 0),
            "hasHistoricalOutcomes": sum(intish(row["historical_outcome_candidates"]) > 0 for row in year_rows),
            "hasOutcomeScores": sum(intish(row["outcome_score_candidates"]) > 0 for row in year_rows),
            "hasQuotaCompetition": sum(intish(row["quota_competition_candidates"]) > 0 for row in year_rows),
            "hasAdmissionOfficeEvidence": sum(
                intish(row["admission_office_detected_year_evidence"]) > 0
                or intish(row["admission_office_collection_year_evidence"]) > 0
                for row in year_rows
            ),
        }
        for row in year_rows:
            if row["coverage_tier"] == "source_rich_review_ready":
                continue
            if not (row["scope_override_statuses"] and row["scope_excluded_missing_flags"]):
                rows_without_scope_override += 1
            exception_rows.append(exception_row(row))

    if rows_without_scope_override:
        errors.append(f"non-source-rich rows without scope override={rows_without_scope_override}")

    non_requested_gap_actions = scalar_int(
        con,
        """
        select count(*)
        from foundation_gap_action_queue
        where admission_year not in ({placeholders})
        """.format(placeholders=",".join("?" for _ in ["2027"])),
        ["2027"],
    )
    # Any 2021-2026 row in the action queue is collectable-now work, not a release wait.
    requested_year_gap_actions = scalar_int(
        con,
        """
        select count(*)
        from foundation_gap_action_queue
        where admission_year in ({placeholders})
        """.format(placeholders=",".join("?" for _ in years)),
        years,
    )
    if requested_year_gap_actions:
        errors.append(f"requested-year gap actions remain={requested_year_gap_actions}")
    if non_requested_gap_actions:
        warnings.append(f"gap actions outside 2027 release wait={non_requested_gap_actions}")

    zero_queues: dict[str, int] = {}
    for table in ZERO_QUEUE_TABLES:
        count = scalar_int(con, f"select count(*) from {table}")
        zero_queues[table] = count
        if count:
            errors.append(f"{table} has {count} rows")

    evidence_type_counts = evidence_counts(con)
    image_or_ocr_evidence_rows = sum(
        count
        for key, count in evidence_type_counts.items()
        if "ocr" in key.lower() or "image" in key.lower() or "pdf_page_image" in key.lower()
    )
    if image_or_ocr_evidence_rows == 0:
        errors.append("no image/OCR evidence rows found")

    target_counts = dict_counts(
        con,
        """
        select target_entity as key, count(*) as value
        from foundation_promotion_queue
        group by target_entity
        """,
    )

    release_monitor_years = dict_counts(
        con,
        """
        select admission_year as key, count(*) as value
        from foundation_release_monitor_targets
        group by admission_year
        """,
    )

    write_exceptions(exceptions_path, exception_rows)

    summary = {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_data_completeness_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "inputs": {
            "sqlite": to_repo_relative(db_path, repo_root),
        },
        "outputs": {
            "exceptionsCsv": to_repo_relative(exceptions_path, repo_root),
        },
        "scope": {
            "requestedPublicYears": years,
            "foundPublicYears": found_years,
            "futureOutcomeWaitYears": ["2027"],
        },
        "sqlite": {
            "integrityCheck": integrity,
            "zeroQueueTables": zero_queues,
            "requestedYearGapActions": requested_year_gap_actions,
            "releaseMonitorTargetsByYear": release_monitor_years,
        },
        "coverage": {
            "coverageByYearTier": coverage_by_year_tier,
            "metricsByYear": metrics_by_year,
            "nonSourceRichExceptionRows": len(exception_rows),
            "nonSourceRichRowsWithoutScopeOverride": rows_without_scope_override,
        },
        "evidence": {
            "admissionOfficeEvidenceRows": scalar_int(con, "select count(*) from foundation_admission_office_evidence_links"),
            "imageOrOcrEvidenceRows": image_or_ocr_evidence_rows,
            "evidenceTypeCounts": dict(sorted(evidence_type_counts.items())),
        },
        "promotionQueue": {
            "rowsByTargetEntity": target_counts,
        },
        "interpretation": {
            "collectablePublicDataStatus": "closed" if not errors else "needs_attention",
            "remainingCollectionStatus": "2027_outcome_public_release_wait",
            "reviewPromotionStatus": "needs_human_verification",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "foundation data completeness audit complete. "
        f"status={summary['status']} years={','.join(years)} exceptions={len(exception_rows)} "
        f"imageOrOcrEvidenceRows={image_or_ocr_evidence_rows}"
    )
    if errors:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--exceptions", default=DEFAULT_EXCEPTIONS)
    parser.add_argument("--years", default="2021,2022,2023,2024,2025,2026")
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def parse_years(value: str) -> list[str]:
    years = [part.strip() for part in value.split(",") if part.strip()]
    if len(years) < 5:
        raise SystemExit("--years must include at least five public years")
    return years


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


def query(con: sqlite3.Connection, sql: str, params: list[str] | None = None) -> list[sqlite3.Row]:
    return list(con.execute(sql, params or []))


def scalar_int(con: sqlite3.Connection, sql: str, params: list[str] | None = None) -> int:
    return int(con.execute(sql, params or []).fetchone()[0])


def dict_counts(con: sqlite3.Connection, sql: str) -> dict[str, int]:
    return {str(row["key"]): int(row["value"]) for row in con.execute(sql)}


def evidence_counts(con: sqlite3.Connection) -> dict[str, int]:
    rows = query(
        con,
        """
        select evidence_types, count(*) as rows
        from foundation_admission_office_evidence_links
        group by evidence_types
        """,
    )
    return {str(row["evidence_types"]): int(row["rows"]) for row in rows}


def exception_row(row: sqlite3.Row) -> dict[str, str]:
    return {
        "unvCd": row["unv_cd"],
        "universityName": row["university_name"],
        "admissionYear": row["admission_year"],
        "coverageTier": row["coverage_tier"],
        "coverageScore": row["coverage_score"],
        "scopeOverrideStatuses": row["scope_override_statuses"],
        "scopeExcludedMissingFlags": row["scope_excluded_missing_flags"],
        "scopeOverrideNotes": row["scope_override_notes"],
        "admissionUnitCandidates": row["admission_unit_candidates"],
        "historicalOutcomeCandidates": row["historical_outcome_candidates"],
        "outcomeScoreCandidates": row["outcome_score_candidates"],
        "quotaCompetitionCandidates": row["quota_competition_candidates"],
        "admissionOfficeDetectedYearEvidence": row["admission_office_detected_year_evidence"],
        "admissionOfficeCollectionYearEvidence": row["admission_office_collection_year_evidence"],
        "admissionOfficeTargets": row["admission_office_targets"],
        "promotionQueueP0Rows": row["promotion_queue_p0_rows"],
        "promotionQueueP1Rows": row["promotion_queue_p1_rows"],
    }


def write_exceptions(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=EXCEPTION_FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in EXCEPTION_FIELDNAMES})


def intish(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
