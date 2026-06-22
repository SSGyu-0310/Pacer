#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = "packages/reference-data/data/public/foundation/foundation_reference.sqlite"
DEFAULT_SEED_AUDIT = "packages/reference-data/data/p0-foundation/foundation_p0_seed_audit_summary.json"
DEFAULT_OUTPUT = "packages/reference-data/data/public/foundation/foundation_operational_readiness_summary.json"


ZERO_QUEUE_TABLES = [
    "foundation_gap_source_candidates",
    "foundation_gap_collection_targets",
    "foundation_gap_crawler_worklist",
    "foundation_gap_visual_review_queue",
    "foundation_gap_adiga_parser_review_queue",
    "foundation_gap_image_source_candidates",
]

ALLOWED_RELEASE_MONITOR_FLAGS = {
    "missing_historical_outcomes",
    "missing_outcome_scores",
    "missing_quota_competition",
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    db_path = resolve(repo_root, args.db)
    seed_audit_path = resolve(repo_root, args.seed_audit)
    output_path = resolve(repo_root, args.output)

    errors: list[str] = []
    warnings: list[str] = []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    integrity = con.execute("pragma integrity_check").fetchone()[0]
    if integrity != "ok":
        errors.append(f"sqlite integrity_check={integrity}")

    zero_queues = {}
    for table in ZERO_QUEUE_TABLES:
        count = scalar_int(con, f"select count(*) from {table}")
        zero_queues[table] = count
        if count != 0:
            errors.append(f"{table} has {count} rows")

    gap_stage_counts = dict_rows(
        con,
        "select next_best_stage as key, count(*) as value from foundation_gap_operations_dashboard group by next_best_stage",
    )
    non_release_stages = {k: v for k, v in gap_stage_counts.items() if k != "wait_for_public_release"}
    if non_release_stages:
        errors.append(f"non-release gap stages remain: {non_release_stages}")

    action_count = scalar_int(con, "select count(*) from foundation_gap_action_queue")
    public_count = scalar_int(con, "select count(*) from foundation_gap_public_discovery_queue")
    release_target_count = scalar_int(con, "select count(*) from foundation_release_monitor_targets")
    release_checklist_count = scalar_int(con, "select count(*) from foundation_release_monitor_checklist")
    release_year_counts = dict_rows(
        con,
        "select admission_year as key, count(*) as value from foundation_release_monitor_targets group by admission_year",
    )
    if set(release_year_counts) - {"2027"}:
        errors.append(f"release monitor contains non-2027 years: {release_year_counts}")

    missing_flags = dict_rows(
        con,
        "select missing_flag as key, count(*) as value from foundation_gap_action_queue group by missing_flag",
    )
    unexpected_flags = set(missing_flags) - ALLOWED_RELEASE_MONITOR_FLAGS
    if unexpected_flags:
        errors.append(f"unexpected remaining missing flags: {sorted(unexpected_flags)}")

    public_modes = query_tuples(
        con,
        "select source_discovery_mode,next_best_stage,count(*) from foundation_gap_public_discovery_queue group by source_discovery_mode,next_best_stage",
    )
    bad_public_modes = [
        row
        for row in public_modes
        if row[0] != "release_monitor" or row[1] != "wait_for_public_release"
    ]
    if bad_public_modes:
        errors.append(f"public discovery queue has non-release rows: {bad_public_modes}")

    seed_audit = json.loads(seed_audit_path.read_text(encoding="utf-8"))
    if seed_audit.get("status") != "ok":
        errors.append(f"seed audit status={seed_audit.get('status')}")

    seed_rows = seed_audit.get("rows") or {}
    seed_invariants = seed_audit.get("invariants") or {}
    for key, value in seed_invariants.items():
        if int(value or 0) != 0:
            errors.append(f"seed invariant {key}={value}")

    seed_units_2027 = int((seed_audit.get("unitRowsByYear") or {}).get("2027") or 0)
    seed_rules = int(seed_rows.get("admissionRules") or 0)
    if seed_units_2027 != seed_rules:
        errors.append(f"2027 seed unit/rule mismatch: units={seed_units_2027} rules={seed_rules}")

    seed_outcome_years = seed_audit.get("outcomeRowsByYear") or {}
    if any(int(year) >= 2027 for year in seed_outcome_years if str(year).isdigit()):
        errors.append(f"seed outcomes include 2027+ years: {seed_outcome_years}")

    if release_target_count == 0 and action_count > 0:
        warnings.append("gap action queue remains but release monitor target table is empty")
    if release_checklist_count != release_target_count:
        errors.append(
            "release monitor checklist count mismatch: "
            f"targets={release_target_count} checklist={release_checklist_count}"
        )

    summary = {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_operational_readiness_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "inputs": {
            "sqlite": to_repo_relative(db_path, repo_root),
            "seedAudit": to_repo_relative(seed_audit_path, repo_root),
        },
        "sqlite": {
            "integrityCheck": integrity,
            "gapActionRows": action_count,
            "gapPublicDiscoveryRows": public_count,
            "releaseMonitorTargets": release_target_count,
            "releaseMonitorChecklistRows": release_checklist_count,
            "gapStages": gap_stage_counts,
            "remainingMissingFlags": missing_flags,
            "releaseMonitorYears": release_year_counts,
            "zeroQueueTables": zero_queues,
        },
        "seed": {
            "rows": seed_rows,
            "unitRowsByYear": seed_audit.get("unitRowsByYear"),
            "ruleRowsByYear": seed_audit.get("ruleRowsByYear"),
            "ruleRowsByVerifiedStatus": seed_audit.get("ruleRowsByVerifiedStatus"),
            "outcomeRowsByYear": seed_audit.get("outcomeRowsByYear"),
            "invariants": seed_invariants,
        },
        "interpretation": {
            "collectableNowStatus": "closed" if not errors else "needs_attention",
            "remainingCollectionStatus": "2027_outcome_public_release_wait",
            "releaseMonitorUnit": "foundation_release_monitor_targets",
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "foundation operational readiness audit complete. "
        f"status={summary['status']} gapActions={action_count} releaseTargets={release_target_count} "
        f"seedRules={seed_rules}"
    )
    if errors:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=DEFAULT_DB)
    parser.add_argument("--seed-audit", default=DEFAULT_SEED_AUDIT)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
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


def scalar_int(con: sqlite3.Connection, query: str) -> int:
    return int(con.execute(query).fetchone()[0])


def dict_rows(con: sqlite3.Connection, query: str) -> dict[str, int]:
    return {str(row["key"]): int(row["value"]) for row in con.execute(query)}


def query_tuples(con: sqlite3.Connection, query: str) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in con.execute(query)]


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
