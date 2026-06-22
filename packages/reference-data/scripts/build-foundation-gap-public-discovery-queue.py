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
from urllib.parse import urlparse


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_OPERATIONS_DASHBOARD = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_operations_dashboard.csv"
)

OUTPUT_JSONL = "foundation_gap_public_discovery_queue.jsonl"
OUTPUT_CSV = "foundation_gap_public_discovery_queue.csv"
OUTPUT_SUMMARY = "foundation_gap_public_discovery_queue_summary.json"

DISCOVERY_STAGES = {
    "run_or_repair_collection",
    "manual_source_discovery",
    "verify_university_scope",
    "wait_for_public_release",
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    operations_path = resolve(repo_root, args.operations_dashboard)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    operation_rows = read_csv(operations_path)
    queue_rows = build_queue(operation_rows)
    queue_rows.sort(
        key=lambda row: (
            priority_sort(row.get("priorityTier")),
            -int_or_none(row.get("searchPriorityScore") or 0),
            stage_sort(row.get("sourceDiscoveryMode")),
            str(row.get("universityName") or ""),
            int_or_large(row.get("admissionYear")),
            str(row.get("targetEntity") or ""),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, queue_rows)
    write_csv(foundation_dir / OUTPUT_CSV, queue_rows)
    summary = summarize(
        repo_root=repo_root,
        inputs=[operations_path],
        operation_rows=operation_rows,
        queue_rows=queue_rows,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap public discovery queue complete. "
        f"operationRows={len(operation_rows)} queueRows={len(queue_rows)} "
        f"manual={summary['bySourceDiscoveryModeCounts'].get('public_web_search', 0)} "
        f"collection={summary['bySourceDiscoveryModeCounts'].get('collection_or_parser_repair', 0)} "
        f"releaseMonitor={summary['bySourceDiscoveryModeCounts'].get('release_monitor', 0)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--operations-dashboard", default=DEFAULT_OPERATIONS_DASHBOARD)
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


def build_queue(operation_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for row in operation_rows:
        next_stage = normalize_text(row.get("nextBestStage"))
        if next_stage not in DISCOVERY_STAGES:
            continue
        mode = source_discovery_mode(next_stage)
        queries = build_search_queries(row, mode)
        host = hostname(row.get("topCollectionUrl"))
        queue.append(
            {
                "publicDiscoveryQueueId": deterministic_uuid(
                    f"public-discovery:{normalize_text(row.get('gapOperationId'))}:{mode}"
                ),
                "artifactType": "foundation_gap_public_discovery_queue_item",
                "gapOperationId": normalize_text(row.get("gapOperationId")),
                "gapActionId": normalize_text(row.get("gapActionId")),
                "priorityTier": normalize_text(row.get("priorityTier")),
                "searchPriorityScore": search_priority(row, mode),
                "sourceDiscoveryMode": mode,
                "nextBestStage": next_stage,
                "unvCd": normalize_text(row.get("unvCd")),
                "universityName": normalize_text(row.get("universityName")),
                "admissionYear": int_or_none(row.get("admissionYear"))
                or normalize_text(row.get("admissionYear")),
                "targetEntity": normalize_text(row.get("targetEntity")),
                "missingFlag": normalize_text(row.get("missingFlag")),
                "recommendedAction": normalize_text(row.get("recommendedAction")),
                "expectedAvailability": normalize_text(row.get("expectedAvailability")),
                "blockingReason": normalize_text(row.get("blockingReason")),
                "collectionRoutes": normalize_text(row.get("collectionRoutes")),
                "collectionExistingFetchStatuses": normalize_text(
                    row.get("collectionExistingFetchStatuses")
                ),
                "topCollectionRoute": normalize_text(row.get("topCollectionRoute")),
                "topCollectionStatus": normalize_text(row.get("topCollectionStatus")),
                "topCollectionUrl": normalize_text(row.get("topCollectionUrl"))[:800],
                "topCollectionHostname": host,
                "searchQueriesJson": json.dumps(queries, ensure_ascii=False),
                "primarySearchQuery": queries[0] if queries else "",
                "queryCount": len(queries),
                "operatorNextStep": operator_next_step(row, mode, queries),
            }
        )
    return queue


def source_discovery_mode(next_stage: str) -> str:
    if next_stage == "run_or_repair_collection":
        return "collection_or_parser_repair"
    if next_stage == "verify_university_scope":
        return "scope_verification"
    if next_stage == "wait_for_public_release":
        return "release_monitor"
    return "public_web_search"


def build_search_queries(row: dict[str, str], mode: str) -> list[str]:
    university = normalize_text(row.get("universityName"))
    year = normalize_text(row.get("admissionYear"))
    target_entity = normalize_text(row.get("targetEntity"))
    missing_flag = normalize_text(row.get("missingFlag"))
    host = hostname(row.get("topCollectionUrl"))
    year_label = f"{year}학년도" if year else ""
    base = " ".join(part for part in [university, year_label] if part)
    phrases = target_phrases(target_entity, missing_flag)
    queries: list[str] = []

    if mode == "collection_or_parser_repair" and row.get("topCollectionUrl"):
        queries.append(normalize_space(normalize_text(row.get("topCollectionUrl"))))
    if mode == "release_monitor":
        phrases = ["정시 입시결과", "정시 경쟁률 충원합격", "최종등록자 백분위"]
    if mode == "scope_verification":
        phrases = ["입학처", "대학교 입학처", "정시 모집요강"]

    for phrase in phrases:
        query = normalize_space(f"{base} {phrase}")
        if query:
            queries.append(query)
        if host and mode != "collection_or_parser_repair":
            queries.append(normalize_space(f"site:{host} {base} {phrase}"))

    return dedupe_keep_order(queries)[:6]


def target_phrases(target_entity: str, missing_flag: str) -> list[str]:
    if target_entity == "HistoricalOutcome" or "historical" in missing_flag:
        return [
            "정시 입시결과",
            "정시 경쟁률 충원합격",
            "수능위주전형 최종등록자 백분위",
        ]
    if target_entity == "AdmissionRule":
        if "schedule" in missing_flag:
            return ["정시 모집요강 전형일정", "정시 원서접수 합격자 발표"]
        return [
            "정시 모집요강 수능 반영방법",
            "정시 수능 반영비율",
            "정시 전형방법 모집요강",
        ]
    if target_entity == "AdmissionSchedule":
        return [
            "정시 모집요강 전형일정",
            "정시 원서접수 합격자 발표",
            "입학처 정시 일정",
        ]
    if target_entity == "AdmissionUnit":
        return ["정시 모집요강 모집단위 모집인원", "정시 모집인원", "정시 모집요강"]
    if target_entity == "AdmissionOfficeEvidence":
        return ["입학처 정시 모집요강", "입학처 정시 입시결과", "입학처 공지"]
    if target_entity == "University":
        return ["입학처", "대학교 입학처", "정시 모집요강"]
    return ["정시 모집요강", "정시 입시결과", "입학처"]


def search_priority(row: dict[str, str], mode: str) -> int:
    score = int_or_none(row.get("operationPriorityScore")) or 0
    score += {
        "collection_or_parser_repair": 35,
        "public_web_search": 30,
        "scope_verification": 10,
        "release_monitor": -10,
    }.get(mode, 0)
    score += {
        "HistoricalOutcome": 30,
        "AdmissionRule": 25,
        "AdmissionSchedule": 20,
        "AdmissionUnit": 15,
        "AdmissionOfficeEvidence": 12,
        "University": 5,
    }.get(normalize_text(row.get("targetEntity")), 0)
    year = int_or_none(row.get("admissionYear")) or 0
    if 2021 <= year <= 2025:
        score += 10
    elif year == 2026:
        score += 8
    elif year >= 2027:
        score += 4
    return score


def operator_next_step(row: dict[str, str], mode: str, queries: list[str]) -> str:
    if mode == "collection_or_parser_repair":
        url = normalize_text(row.get("topCollectionUrl"))
        status = normalize_text(row.get("topCollectionStatus"))
        if url:
            return (
                f"Fetch or repair parser for {url}; current fetch status={status or 'unknown'}."
            )
        return "Repair collection/parser route using collectionRoutes and existing fetch status."
    if mode == "scope_verification":
        query = queries[0] if queries else normalize_text(row.get("universityName"))
        return f"Verify university scope/status from official source query: {query}."
    if mode == "release_monitor":
        query = queries[0] if queries else normalize_text(row.get("universityName"))
        return f"Monitor public release; do not mark missing as final until source appears: {query}."
    query = queries[0] if queries else normalize_text(row.get("universityName"))
    return f"Run public web/source discovery query, then add source candidate or blocker: {query}."


def summarize(
    repo_root: Path,
    inputs: list[Path],
    operation_rows: list[dict[str, str]],
    queue_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    p0_rows = [row for row in queue_rows if row.get("priorityTier") == "p0"]
    immediate_rows = [
        row
        for row in queue_rows
        if row.get("sourceDiscoveryMode")
        in {"collection_or_parser_repair", "public_web_search", "scope_verification"}
    ]
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_public_discovery_queue_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [input_summary(path, repo_root) for path in inputs],
        "operationRows": {
            "total": len(operation_rows),
        },
        "queueRows": {
            "total": len(queue_rows),
            "p0": len(p0_rows),
            "immediateNonRelease": len(immediate_rows),
        },
        "bySourceDiscoveryMode": counter_items(
            Counter(str(row.get("sourceDiscoveryMode") or "") for row in queue_rows)
        ),
        "bySourceDiscoveryModeCounts": dict(
            Counter(str(row.get("sourceDiscoveryMode") or "") for row in queue_rows)
        ),
        "byTargetEntity": counter_items(
            Counter(str(row.get("targetEntity") or "") for row in queue_rows)
        ),
        "byAdmissionYear": counter_items(
            Counter(str(row.get("admissionYear") or "") for row in queue_rows)
        ),
        "topUniversities": counter_items(
            Counter(str(row.get("universityName") or "") for row in queue_rows),
            limit=30,
        ),
        "topImmediateUniversities": counter_items(
            Counter(str(row.get("universityName") or "") for row in immediate_rows),
            limit=30,
        ),
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    configure_csv_field_limit()
    if not path.exists():
        raise SystemExit(f"Missing input CSV: {path}")
    with path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def configure_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit = int(limit / 10)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def input_summary(path: Path, repo_root: Path) -> dict[str, Any]:
    return {
        "path": to_repo_relative(path, repo_root),
        "sha256": sha256_file(path),
        "rows": csv_row_count(path),
    }


def csv_row_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as file:
        return max(sum(1 for _ in file) - 1, 0)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def counter_items(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    items = [
        {"value": key, "count": count}
        for key, count in counter.most_common(limit)
        if key
    ]
    return items


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, value))


def hostname(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    try:
        return urlparse(text).netloc.lower()
    except ValueError:
        return ""


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_space(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def int_or_none(value: Any) -> int | None:
    try:
        text = normalize_text(value).replace(",", "")
        return int(float(text)) if text else None
    except ValueError:
        return None


def int_or_large(value: Any) -> int:
    return int_or_none(value) or 999999


def priority_sort(value: Any) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(normalize_text(value), 9)


def stage_sort(value: Any) -> int:
    return {
        "collection_or_parser_repair": 0,
        "public_web_search": 1,
        "scope_verification": 2,
        "release_monitor": 3,
    }.get(normalize_text(value), 9)


if __name__ == "__main__":
    main()
