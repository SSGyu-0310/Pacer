#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_OUTPUT_DB = "foundation_reference.sqlite"
DEFAULT_OUTPUT_SUMMARY = "foundation_reference_sqlite_summary.json"

EXCLUDED_CSV_FILES = {
    # The SQLite export is the operational query layer. The CSV sources remain
    # the canonical review artifacts; summaries stay as JSON files.
}

COMMON_INDEX_COLUMNS = {
    "unv_cd",
    "university_name",
    "year",
    "admission_year",
    "academic_year",
    "target_entity",
    "priority_tier",
    "source_provider",
    "rule_category",
    "coverage_tier",
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    output_db = resolve(foundation_dir, args.output_db)
    output_summary = resolve(foundation_dir, args.output_summary)
    csv_paths = [
        path
        for path in sorted(foundation_dir.glob("foundation_*.csv"))
        if path.name not in EXCLUDED_CSV_FILES
    ]
    if not csv_paths:
        raise SystemExit(f"No foundation CSV files found under {foundation_dir}")

    configure_csv_field_limit()
    temp_db = output_db.with_suffix(output_db.suffix + ".tmp")
    if temp_db.exists():
        temp_db.unlink()

    generated_at = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(temp_db)
    try:
        configure_sqlite(conn)
        create_metadata_tables(conn)
        table_summaries = []
        for path in csv_paths:
            summary = import_csv_table(
                conn=conn,
                repo_root=repo_root,
                foundation_dir=foundation_dir,
                path=path,
                generated_at=generated_at,
            )
            table_summaries.append(summary)
            print(
                "foundation sqlite import "
                f"table={summary['tableName']} rows={summary['rowCount']} "
                f"columns={summary['columnCount']}"
            )

        create_review_views(conn, table_summaries)
        conn.execute("PRAGMA optimize")
        conn.commit()
    finally:
        conn.close()

    os.replace(temp_db, output_db)
    summary = build_summary(
        repo_root=repo_root,
        output_db=output_db,
        table_summaries=table_summaries,
        generated_at=generated_at,
    )
    output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", "utf-8")

    print(
        "foundation sqlite database complete. "
        f"tables={summary['tables']['total']} rows={summary['rows']['total']} "
        f"db={to_repo_relative(output_db, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--output-db", default=DEFAULT_OUTPUT_DB)
    parser.add_argument("--output-summary", default=DEFAULT_OUTPUT_SUMMARY)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def configure_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while True:
        if (current / "pnpm-workspace.yaml").exists():
            return current
        if current.parent == current:
            return start.resolve()
        current = current.parent


def resolve(base: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else base / path


def configure_sqlite(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=OFF")


def create_metadata_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE foundation_import_manifest (
          table_name TEXT PRIMARY KEY,
          source_path TEXT NOT NULL,
          source_sha256 TEXT NOT NULL,
          source_bytes INTEGER NOT NULL,
          row_count INTEGER NOT NULL,
          column_count INTEGER NOT NULL,
          columns_json TEXT NOT NULL,
          original_columns_json TEXT NOT NULL,
          imported_at TEXT NOT NULL
        );

        CREATE TABLE foundation_database_metadata (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """
    )


def import_csv_table(
    conn: sqlite3.Connection,
    repo_root: Path,
    foundation_dir: Path,
    path: Path,
    generated_at: str,
) -> dict[str, Any]:
    table_name = table_name_for(path)
    source_path = to_repo_relative(path, repo_root)
    source_sha256 = sha256_file(path)
    source_bytes = path.stat().st_size

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        original_columns = reader.fieldnames or []
        if not original_columns:
            raise ValueError(f"CSV file has no header: {path}")
        columns = unique_column_names(to_snake_case(column) for column in original_columns)
        create_data_table(conn, table_name, columns)
        row_count = insert_rows(conn, table_name, columns, original_columns, reader)

    create_common_indexes(conn, table_name, columns)
    conn.execute(
        """
        INSERT INTO foundation_import_manifest (
          table_name,
          source_path,
          source_sha256,
          source_bytes,
          row_count,
          column_count,
          columns_json,
          original_columns_json,
          imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            table_name,
            source_path,
            source_sha256,
            source_bytes,
            row_count,
            len(columns),
            json.dumps(columns, ensure_ascii=False),
            json.dumps(original_columns, ensure_ascii=False),
            generated_at,
        ),
    )
    return {
        "tableName": table_name,
        "sourcePath": source_path,
        "sourceSha256": source_sha256,
        "sourceBytes": source_bytes,
        "rowCount": row_count,
        "columnCount": len(columns),
        "columns": columns,
        "originalColumns": original_columns,
        "indexedColumns": sorted(COMMON_INDEX_COLUMNS.intersection(columns)),
    }


def table_name_for(path: Path) -> str:
    return to_snake_case(path.stem)


def to_snake_case(value: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value.strip())
    text = re.sub(r"[^0-9A-Za-z가-힣_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_").lower()
    if not text:
        text = "column"
    if re.match(r"^\d", text):
        text = f"c_{text}"
    return text


def unique_column_names(columns: Iterable[str]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for column in columns:
        base = column or "column"
        index = seen.get(base, 0)
        seen[base] = index + 1
        result.append(base if index == 0 else f"{base}_{index + 1}")
    return result


def create_data_table(conn: sqlite3.Connection, table_name: str, columns: list[str]) -> None:
    quoted_columns = ",\n          ".join(f"{quote_identifier(column)} TEXT" for column in columns)
    conn.execute(
        f"""
        CREATE TABLE {quote_identifier(table_name)} (
          _source_row_number INTEGER PRIMARY KEY,
          {quoted_columns}
        )
        """
    )


def insert_rows(
    conn: sqlite3.Connection,
    table_name: str,
    columns: list[str],
    original_columns: list[str],
    reader: csv.DictReader,
) -> int:
    placeholders = ", ".join(["?"] * (len(columns) + 1))
    quoted_columns = ", ".join(["_source_row_number", *[quote_identifier(column) for column in columns]])
    sql = f"INSERT INTO {quote_identifier(table_name)} ({quoted_columns}) VALUES ({placeholders})"
    batch: list[tuple[Any, ...]] = []
    row_count = 0
    for row_number, row in enumerate(reader, start=1):
        values = [row_number]
        for original_column in original_columns:
            value = row.get(original_column)
            values.append("" if value is None else value)
        batch.append(tuple(values))
        if len(batch) >= 1000:
            conn.executemany(sql, batch)
            batch.clear()
        row_count = row_number
    if batch:
        conn.executemany(sql, batch)
    return row_count


def create_common_indexes(conn: sqlite3.Connection, table_name: str, columns: list[str]) -> None:
    available = COMMON_INDEX_COLUMNS.intersection(columns)
    for column in sorted(available):
        index_name = f"idx_{table_name}_{column}"
        conn.execute(
            f"CREATE INDEX {quote_identifier(index_name)} "
            f"ON {quote_identifier(table_name)} ({quote_identifier(column)})"
        )
    if {"unv_cd", "admission_year"}.issubset(columns):
        conn.execute(
            f"CREATE INDEX {quote_identifier(f'idx_{table_name}_unv_cd_admission_year')} "
            f"ON {quote_identifier(table_name)} (unv_cd, admission_year)"
        )
    if {"unv_cd", "year"}.issubset(columns):
        conn.execute(
            f"CREATE INDEX {quote_identifier(f'idx_{table_name}_unv_cd_year')} "
            f"ON {quote_identifier(table_name)} (unv_cd, year)"
        )


def create_review_views(conn: sqlite3.Connection, table_summaries: list[dict[str, Any]]) -> None:
    table_names = {row["tableName"] for row in table_summaries}
    if {
        "foundation_universities",
        "foundation_university_year_coverage",
        "foundation_gap_action_queue",
    }.issubset(table_names):
        conn.executescript(
            """
            CREATE VIEW review_university_year_gaps AS
            SELECT
              coverage.unv_cd,
              coverage.university_name,
              coverage.admission_year,
              coverage.coverage_tier,
              coverage.coverage_score,
              coverage.coverage_missing_flags,
              coverage.promotion_queue_p0_rows,
              actions.gap_action_id,
              actions.target_entity,
              actions.recommended_action,
              actions.priority_tier,
              actions.expected_availability
            FROM foundation_university_year_coverage AS coverage
            LEFT JOIN foundation_gap_action_queue AS actions
              ON actions.unv_cd = coverage.unv_cd
             AND actions.admission_year = coverage.admission_year;
            """
        )
    if {
        "foundation_admission_units",
        "foundation_historical_outcomes",
    }.issubset(table_names):
        conn.executescript(
            """
            CREATE VIEW review_admission_unit_outcomes AS
            SELECT
              units.unv_cd,
              units.university_name,
              units.year,
              units.recruitment_group,
              units.admission_unit_name,
              units.admission_unit_canonical_name,
              outcomes.quota,
              outcomes.competition_rate,
              outcomes.additional_pass,
              outcomes.converted_score50_cut,
              outcomes.converted_score70_cut,
              outcomes.total_score,
              outcomes.percentile70_average,
              outcomes.avg_score_candidate,
              outcomes.cut_score_candidate,
              outcomes.percentile_cut_candidate,
              outcomes.score_availability,
              outcomes.confidence
            FROM foundation_admission_units AS units
            LEFT JOIN foundation_historical_outcomes AS outcomes
              ON outcomes.unit_candidate_id = units.unit_candidate_id;
            """
        )
    conn.execute(
        """
        INSERT INTO foundation_database_metadata (key, value)
        VALUES (?, ?), (?, ?), (?, ?)
        """,
        (
            "database_kind",
            "source_preserving_foundation_review_sqlite",
            "verification_status",
            "needs_human_verification",
            "notes",
            (
                "All imported tables are foundation review candidates. "
                "They are not verified production AdmissionRule or HistoricalOutcome records."
            ),
        ),
    )


def build_summary(
    repo_root: Path,
    output_db: Path,
    table_summaries: list[dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    rows_total = sum(int(row["rowCount"]) for row in table_summaries)
    return {
        "artifactType": "foundation_reference_sqlite_summary",
        "generatedAt": generated_at,
        "database": {
            "path": to_repo_relative(output_db, repo_root),
            "sha256": sha256_file(output_db),
            "bytes": output_db.stat().st_size,
        },
        "tables": {
            "total": len(table_summaries),
            "names": [row["tableName"] for row in table_summaries],
        },
        "rows": {
            "total": rows_total,
            "byTable": {
                row["tableName"]: row["rowCount"]
                for row in sorted(table_summaries, key=lambda item: item["tableName"])
            },
        },
        "sourceFiles": [
            {
                "tableName": row["tableName"],
                "path": row["sourcePath"],
                "sha256": row["sourceSha256"],
                "bytes": row["sourceBytes"],
                "rows": row["rowCount"],
                "columns": row["columnCount"],
                "indexedColumns": row["indexedColumns"],
            }
            for row in table_summaries
        ],
        "views": [
            "review_university_year_gaps",
            "review_admission_unit_outcomes",
        ],
        "notes": [
            "SQLite export preserves foundation CSV values as TEXT for review queries and auditability.",
            "Source CSV/JSONL artifacts remain the canonical pre-verification data layer.",
            "Rows require human source verification before promotion to production database records.",
        ],
    }


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
