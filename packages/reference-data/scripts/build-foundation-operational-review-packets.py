#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_BATCHES = "foundation_operational_review_batches.csv"
DEFAULT_QUEUE = "foundation_promotion_queue.csv"
OUTPUT_BATCHES = "foundation_operational_review_packet_batches.csv"
OUTPUT_ROWS = "foundation_operational_review_packet_rows.csv"
OUTPUT_SUMMARY = "foundation_operational_review_packet_summary.json"

LANE_ORDER = {
    "historical_outcome_core": 0,
    "rule_schedule_2027": 1,
    "kice_score_reference": 2,
    "admission_unit_core": 3,
    "university_master": 4,
    "continuity_review": 5,
    "other_p0_review": 9,
}

PACKET_BATCH_FIELDNAMES = [
    "packetRank",
    "packetStatus",
    "reviewBatchId",
    "reviewLane",
    "targetEntity",
    "admissionYear",
    "academicYear",
    "examType",
    "subjectName",
    "unvCd",
    "universityName",
    "batchRowCount",
    "includedRowCount",
    "truncatedRowCount",
    "reviewPriorityScoreMax",
    "sourceArtifacts",
    "promotionActions",
    "blockerFlags",
    "sampleSourceUrls",
    "sampleRawPaths",
    "sampleSourcePaths",
    "operatorNextStep",
    "reviewInstruction",
]

PACKET_ROW_FIELDNAMES = [
    "packetRank",
    "reviewBatchId",
    "rowRankInBatch",
    "promotionQueueId",
    "sourceArtifact",
    "sourceRecordId",
    "targetEntity",
    "promotionAction",
    "ruleCategory",
    "priorityTier",
    "reviewPriorityScore",
    "reviewStrength",
    "confidence",
    "reviewStatus",
    "admissionYear",
    "academicYear",
    "examType",
    "unvCd",
    "universityName",
    "admissionUnitName",
    "recruitmentGroup",
    "subjectName",
    "provider",
    "sourceRows",
    "draftFlags",
    "blockerFlags",
    "evidenceSummary",
    "sourceUrls",
    "attachmentUrls",
    "rawPaths",
    "sourcePaths",
    "reviewInstruction",
]


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    batches = list(read_csv(foundation_dir / args.batches_csv))
    queue_rows = list(read_csv(foundation_dir / args.queue_csv))

    selected_batches = select_batches(
        batches,
        lanes=parse_csv_arg(args.lanes),
        per_lane=args.per_lane,
        limit=args.limit,
    )
    queue_by_batch = group_queue_rows(queue_rows)
    packet_batches, packet_rows = build_packets(selected_batches, queue_by_batch, args.max_rows_per_batch)

    write_csv(foundation_dir / OUTPUT_BATCHES, PACKET_BATCH_FIELDNAMES, packet_batches)
    write_csv(foundation_dir / OUTPUT_ROWS, PACKET_ROW_FIELDNAMES, packet_rows)
    summary = summarize(repo_root, foundation_dir, batches, queue_rows, packet_batches, packet_rows)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation operational review packets complete. "
        f"packetBatches={len(packet_batches)} packetRows={len(packet_rows)} "
        f"output={to_repo_relative(foundation_dir / OUTPUT_ROWS, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--batches-csv", default=DEFAULT_BATCHES)
    parser.add_argument("--queue-csv", default=DEFAULT_QUEUE)
    parser.add_argument(
        "--lanes",
        default="historical_outcome_core,rule_schedule_2027,kice_score_reference,admission_unit_core",
    )
    parser.add_argument("--per-lane", type=int, default=12)
    parser.add_argument("--limit", type=int, default=48)
    parser.add_argument("--max-rows-per-batch", type=int, default=200)
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


def parse_csv_arg(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def select_batches(
    batches: list[dict[str, str]],
    lanes: list[str],
    per_lane: int,
    limit: int,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    lane_set = set(lanes)
    for lane in lanes:
        lane_batches = [
            batch
            for batch in batches
            if normalize_text(batch.get("reviewLane")) == lane
            and normalize_text(batch.get("reviewStatus")) == "needs_human_verification"
        ]
        lane_batches.sort(key=batch_sort_key)
        selected.extend(lane_batches[:per_lane])
    selected = [batch for batch in selected if normalize_text(batch.get("reviewLane")) in lane_set]
    selected.sort(key=batch_sort_key)
    return selected[:limit]


def batch_sort_key(batch: dict[str, str]) -> tuple[int, int, int, str, str, str]:
    lane = normalize_text(batch.get("reviewLane"))
    return (
        LANE_ORDER.get(lane, 99),
        -(int_or_zero(batch.get("reviewPriorityScoreMax"))),
        -(int_or_zero(batch.get("batchRowCount"))),
        normalize_text(batch.get("universityName")),
        normalize_text(batch.get("admissionYear") or batch.get("academicYear")),
        normalize_text(batch.get("targetEntity")),
    )


def group_queue_rows(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if normalize_text(row.get("priorityTier")) != "p0":
            continue
        if normalize_text(row.get("reviewStatus")) not in {"needs_human_verification", "manual_verified"}:
            continue
        grouped[review_batch_id_for_queue_row(row)].append(row)
    for bucket in grouped.values():
        bucket.sort(key=queue_row_sort_key)
    return grouped


def review_batch_id_for_queue_row(row: dict[str, str]) -> str:
    lane = review_lane(row)
    target = normalize_text(row.get("targetEntity"))
    admission_year = normalize_text(row.get("admissionYear"))
    academic_year = normalize_text(row.get("academicYear"))
    unv_cd = normalize_text(row.get("unvCd"))
    university_name = normalize_text(row.get("universityName"))
    exam_type = normalize_text(row.get("examType"))
    subject_name = normalize_text(row.get("subjectName"))
    batch_seed = "|".join([lane, target, admission_year, academic_year, unv_cd, university_name, exam_type, subject_name])
    return deterministic_uuid(f"foundation-operational-review-batch:{batch_seed}")


def review_lane(row: dict[str, str]) -> str:
    target = normalize_text(row.get("targetEntity"))
    source_artifact = normalize_text(row.get("sourceArtifact"))
    admission_year = normalize_text(row.get("admissionYear"))
    if target == "HistoricalOutcome" and source_artifact == "foundation_historical_outcomes":
        return "historical_outcome_core"
    if target == "AdmissionUnit":
        return "admission_unit_core"
    if target in {"GradeCutReference", "StandardScoreDistributionReference"}:
        return "kice_score_reference"
    if target in {"AdmissionRule", "AdmissionSchedule"} and admission_year == "2027":
        return "rule_schedule_2027"
    if target == "University":
        return "university_master"
    if target in {"AdmissionUnitClusterReview", "HistoricalOutcomeSeriesReview"}:
        return "continuity_review"
    return "other_p0_review"


def queue_row_sort_key(row: dict[str, str]) -> tuple[int, str, str]:
    return (
        -(int_or_zero(row.get("reviewPriorityScore"))),
        normalize_text(row.get("admissionUnitName") or row.get("subjectName")),
        normalize_text(row.get("promotionQueueId")),
    )


def build_packets(
    selected_batches: list[dict[str, str]],
    queue_by_batch: dict[str, list[dict[str, str]]],
    max_rows_per_batch: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    packet_batches: list[dict[str, Any]] = []
    packet_rows: list[dict[str, Any]] = []
    for packet_rank, batch in enumerate(selected_batches, start=1):
        batch_id = normalize_text(batch.get("reviewBatchId"))
        rows = queue_by_batch.get(batch_id, [])
        included_rows = rows[:max_rows_per_batch]
        truncated = max(0, len(rows) - len(included_rows))
        instruction = review_instruction(batch)
        packet_batches.append(
            {
                "packetRank": packet_rank,
                "packetStatus": "ready_for_human_review",
                "reviewBatchId": batch_id,
                "reviewLane": batch.get("reviewLane", ""),
                "targetEntity": batch.get("targetEntity", ""),
                "admissionYear": batch.get("admissionYear", ""),
                "academicYear": batch.get("academicYear", ""),
                "examType": batch.get("examType", ""),
                "subjectName": batch.get("subjectName", ""),
                "unvCd": batch.get("unvCd", ""),
                "universityName": batch.get("universityName", ""),
                "batchRowCount": batch.get("batchRowCount", ""),
                "includedRowCount": len(included_rows),
                "truncatedRowCount": truncated,
                "reviewPriorityScoreMax": batch.get("reviewPriorityScoreMax", ""),
                "sourceArtifacts": batch.get("sourceArtifacts", ""),
                "promotionActions": batch.get("promotionActions", ""),
                "blockerFlags": batch.get("blockerFlags", ""),
                "sampleSourceUrls": batch.get("sampleSourceUrls", ""),
                "sampleRawPaths": batch.get("sampleRawPaths", ""),
                "sampleSourcePaths": batch.get("sampleSourcePaths", ""),
                "operatorNextStep": batch.get("operatorNextStep", ""),
                "reviewInstruction": instruction,
            }
        )
        for row_rank, row in enumerate(included_rows, start=1):
            packet_rows.append(
                {
                    "packetRank": packet_rank,
                    "reviewBatchId": batch_id,
                    "rowRankInBatch": row_rank,
                    "reviewInstruction": instruction,
                    **{field: row.get(field, "") for field in PACKET_ROW_FIELDNAMES if field in row},
                }
            )
    return packet_batches, packet_rows


def review_instruction(batch: dict[str, str]) -> str:
    lane = normalize_text(batch.get("reviewLane"))
    if lane == "historical_outcome_core":
        return "Open raw/source path, compare row numbers and numeric columns, then mark only source-matched outcome rows for verified promotion."
    if lane == "rule_schedule_2027":
        return "Compare 2027 rule/schedule draft against official guide; keep parsed status until formula fields and applicability are confirmed."
    if lane == "kice_score_reference":
        return "Spot-check KICE official workbook/table coordinates, then approve score reference rows used by the calculation engine."
    if lane == "admission_unit_core":
        return "Verify admission unit name, recruitment group, year, and quota candidates before using the unit in live analysis."
    return "Compare source artifact with extracted row before any verified promotion."


def summarize(
    repo_root: Path,
    foundation_dir: Path,
    batches: list[dict[str, str]],
    queue_rows: list[dict[str, str]],
    packet_batches: list[dict[str, Any]],
    packet_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    by_lane = Counter(str(row.get("reviewLane") or "") for row in packet_batches)
    row_by_lane = Counter()
    missing_detail_batches = 0
    for batch in packet_batches:
        lane = str(batch.get("reviewLane") or "")
        row_by_lane[lane] += int_or_zero(batch.get("includedRowCount"))
        if int_or_zero(batch.get("includedRowCount")) == 0:
            missing_detail_batches += 1
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_operational_review_packet_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "batchesCsv": to_repo_relative(foundation_dir / DEFAULT_BATCHES, repo_root),
            "promotionQueueCsv": to_repo_relative(foundation_dir / DEFAULT_QUEUE, repo_root),
            "batchRows": len(batches),
            "promotionQueueRows": len(queue_rows),
        },
        "outputs": {
            "packetBatchesCsv": to_repo_relative(foundation_dir / OUTPUT_BATCHES, repo_root),
            "packetRowsCsv": to_repo_relative(foundation_dir / OUTPUT_ROWS, repo_root),
        },
        "packet": {
            "batchRows": len(packet_batches),
            "detailRows": len(packet_rows),
            "missingDetailBatches": missing_detail_batches,
            "batchesByReviewLane": dict(sorted(by_lane.items())),
            "detailRowsByReviewLane": dict(sorted(row_by_lane.items())),
        },
        "notes": [
            "This is a review work packet, not a verified production seed.",
            "Rows remain needs_human_verification until original source comparison is completed.",
            "Use the rawPaths/sourcePaths/sourceUrls columns to open the source evidence for each row.",
        ],
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def deterministic_uuid(seed: str) -> str:
    import hashlib
    import uuid

    return str(uuid.UUID(hashlib.md5(seed.encode("utf-8")).hexdigest()))


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
