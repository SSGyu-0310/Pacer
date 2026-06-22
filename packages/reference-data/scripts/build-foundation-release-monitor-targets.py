#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_PUBLIC_DISCOVERY_QUEUE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_public_discovery_queue.csv"
)

OUTPUT_CSV = "foundation_release_monitor_targets.csv"
OUTPUT_JSON = "foundation_release_monitor_targets_summary.json"

FIELDNAMES = [
    "releaseMonitorTargetId",
    "artifactType",
    "priorityTier",
    "monitorStatus",
    "unvCd",
    "universityName",
    "admissionYear",
    "targetEntity",
    "missingFlags",
    "recommendedActions",
    "gapOperationCount",
    "searchPriorityScoreMax",
    "expectedAvailability",
    "blockingReasons",
    "primarySearchQueries",
    "searchQueriesJson",
    "operatorNextStep",
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    queue_path = resolve(repo_root, args.public_discovery_queue)
    rows = read_csv(queue_path)

    targets = build_targets(rows)
    write_csv(foundation_dir / OUTPUT_CSV, targets)
    summary = summarize(queue_path, repo_root, rows, targets)
    (foundation_dir / OUTPUT_JSON).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation release monitor targets complete. "
        f"queueRows={len(rows)} targets={len(targets)} "
        f"releaseMonitorRows={summary['releaseMonitorRows']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--public-discovery-queue", default=DEFAULT_PUBLIC_DISCOVERY_QUEUE)
    return parser.parse_args()


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
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def build_targets(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        if row.get("sourceDiscoveryMode") != "release_monitor":
            continue
        key = (row.get("unvCd", ""), row.get("universityName", ""), row.get("admissionYear", ""))
        if key not in grouped:
            grouped[key] = {
                "releaseMonitorTargetId": f"release-monitor-{key[0]}-{key[2]}",
                "artifactType": "foundation_release_monitor_target",
                "priorityTier": row.get("priorityTier", ""),
                "monitorStatus": "waiting_public_release",
                "unvCd": key[0],
                "universityName": key[1],
                "admissionYear": key[2],
                "targetEntity": row.get("targetEntity", ""),
                "missingFlags": [],
                "recommendedActions": [],
                "gapOperationCount": 0,
                "searchPriorityScoreMax": 0,
                "expectedAvailability": [],
                "blockingReasons": [],
                "primarySearchQueries": [],
                "searchQueries": [],
            }
        target = grouped[key]
        append_unique(target["missingFlags"], row.get("missingFlag", ""))
        append_unique(target["recommendedActions"], row.get("recommendedAction", ""))
        append_unique(target["expectedAvailability"], row.get("expectedAvailability", ""))
        append_unique(target["blockingReasons"], row.get("blockingReason", ""))
        append_unique(target["primarySearchQueries"], row.get("primarySearchQuery", ""))
        for query in parse_queries(row.get("searchQueriesJson", "")):
            append_unique(target["searchQueries"], query)
        target["gapOperationCount"] += 1
        target["searchPriorityScoreMax"] = max(
            int_or_zero(target["searchPriorityScoreMax"]),
            int_or_zero(row.get("searchPriorityScore")),
        )

    output = []
    for target in grouped.values():
        target["missingFlags"] = "|".join(target["missingFlags"])
        target["recommendedActions"] = "|".join(target["recommendedActions"])
        target["expectedAvailability"] = "|".join(target["expectedAvailability"])
        target["blockingReasons"] = "|".join(target["blockingReasons"])
        target["primarySearchQueries"] = "|".join(target["primarySearchQueries"])
        target["searchQueriesJson"] = json.dumps(target.pop("searchQueries"), ensure_ascii=False)
        target["operatorNextStep"] = (
            "Wait until the 2027 outcome/result data is officially public; then use "
            "primarySearchQueries or official admission-result pages to collect "
            "HistoricalOutcome score/quota/competition evidence."
        )
        output.append(target)
    output.sort(
        key=lambda row: (
            -int_or_zero(row.get("searchPriorityScoreMax")),
            row.get("universityName", ""),
            row.get("unvCd", ""),
        )
    )
    return output


def append_unique(values: list[str], value: str) -> None:
    value = (value or "").strip()
    if value and value not in values:
        values.append(value)


def parse_queries(value: str) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return [value]
    return [str(item) for item in parsed if str(item).strip()] if isinstance(parsed, list) else [str(parsed)]


def int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def summarize(
    queue_path: Path,
    repo_root: Path,
    rows: list[dict[str, str]],
    targets: list[dict[str, Any]],
) -> dict[str, Any]:
    release_rows = [row for row in rows if row.get("sourceDiscoveryMode") == "release_monitor"]
    by_missing = Counter(row.get("missingFlag", "") for row in release_rows)
    by_year = Counter(row.get("admissionYear", "") for row in release_rows)
    by_status = Counter(target.get("monitorStatus", "") for target in targets)
    target_sizes = Counter(str(target.get("gapOperationCount", "")) for target in targets)
    return {
        "artifactType": "foundation_release_monitor_targets_summary",
        "sourceQueue": rel_path(repo_root, queue_path),
        "outputCsv": f"{DEFAULT_FOUNDATION_DIR}/{OUTPUT_CSV}",
        "queueRows": len(rows),
        "releaseMonitorRows": len(release_rows),
        "targetRows": len(targets),
        "byMissingFlag": dict(by_missing.most_common()),
        "byAdmissionYear": dict(by_year.most_common()),
        "byMonitorStatus": dict(by_status.most_common()),
        "targetRowsByGapOperationCount": dict(target_sizes.most_common()),
    }


def rel_path(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
