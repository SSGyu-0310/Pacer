#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_TARGETS = "packages/reference-data/data/public/foundation/foundation_release_monitor_targets.csv"

OUTPUT_CSV = "foundation_release_monitor_checklist.csv"
OUTPUT_SUMMARY = "foundation_release_monitor_checklist_summary.json"

FIELDNAMES = [
    "releaseMonitorChecklistId",
    "artifactType",
    "releaseMonitorTargetId",
    "claimStatus",
    "claimedBy",
    "lastCheckedAt",
    "releaseEvidenceStatus",
    "officialResultUrl",
    "officialAttachmentUrl",
    "collectorInputStatus",
    "collectorInputPath",
    "unvCd",
    "universityName",
    "admissionYear",
    "missingFlags",
    "gapOperationCount",
    "primarySearchQueries",
    "searchQueriesJson",
    "expectedAvailability",
    "blockingReasons",
    "operatorNextStep",
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    targets_path = resolve(repo_root, args.targets)
    targets = read_csv(targets_path)
    rows = build_checklist(targets)

    output_csv = foundation_dir / OUTPUT_CSV
    write_csv(output_csv, rows)
    summary = summarize(repo_root, targets_path, output_csv, rows)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation release monitor checklist complete. "
        f"targets={len(targets)} checklistRows={len(rows)} output={to_repo_relative(output_csv, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--targets", default=DEFAULT_TARGETS)
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
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_checklist(targets: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows = []
    for target in targets:
        target_id = target.get("releaseMonitorTargetId", "")
        rows.append(
            {
                "releaseMonitorChecklistId": f"release-monitor-check-{target_id}",
                "artifactType": "foundation_release_monitor_checklist_item",
                "releaseMonitorTargetId": target_id,
                "claimStatus": "unclaimed",
                "claimedBy": "",
                "lastCheckedAt": "",
                "releaseEvidenceStatus": "not_checked",
                "officialResultUrl": "",
                "officialAttachmentUrl": "",
                "collectorInputStatus": "not_ready",
                "collectorInputPath": "",
                "unvCd": target.get("unvCd", ""),
                "universityName": target.get("universityName", ""),
                "admissionYear": target.get("admissionYear", ""),
                "missingFlags": target.get("missingFlags", ""),
                "gapOperationCount": target.get("gapOperationCount", ""),
                "primarySearchQueries": target.get("primarySearchQueries", ""),
                "searchQueriesJson": target.get("searchQueriesJson", ""),
                "expectedAvailability": target.get("expectedAvailability", ""),
                "blockingReasons": target.get("blockingReasons", ""),
                "operatorNextStep": (
                    "Check only official admission office or ADIGA pages for 2027 result release. "
                    "If public, fill officialResultUrl/officialAttachmentUrl and create a narrow collector input CSV. "
                    "If not public, set releaseEvidenceStatus=not_public_yet with lastCheckedAt."
                ),
            }
        )
    rows.sort(
        key=lambda row: (
            -int_or_zero(row.get("gapOperationCount")),
            row.get("universityName", ""),
            row.get("unvCd", ""),
        )
    )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def summarize(
    repo_root: Path,
    targets_path: Path,
    output_csv: Path,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_status = Counter(str(row.get("releaseEvidenceStatus", "")) for row in rows)
    by_claim = Counter(str(row.get("claimStatus", "")) for row in rows)
    by_year = Counter(str(row.get("admissionYear", "")) for row in rows)
    by_gap_count = Counter(str(row.get("gapOperationCount", "")) for row in rows)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_release_monitor_checklist_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputTargets": to_repo_relative(targets_path, repo_root),
        "outputCsv": to_repo_relative(output_csv, repo_root),
        "checklistRows": len(rows),
        "byReleaseEvidenceStatus": dict(sorted(by_status.items())),
        "byClaimStatus": dict(sorted(by_claim.items())),
        "byAdmissionYear": dict(sorted(by_year.items())),
        "byGapOperationCount": dict(sorted(by_gap_count.items())),
        "notes": [
            "This checklist is for release monitoring only; it is not evidence that 2027 results are public.",
            "Do not run broad collectors from this file. Fill officialResultUrl or officialAttachmentUrl first, then create a narrow collector input.",
            "2027 HistoricalOutcome promotion remains blocked until official result data is public.",
        ],
    }


def int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
