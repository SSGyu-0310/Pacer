#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
INPUT_CSV = "foundation_promotion_queue.csv"
OUTPUT_CSV = "foundation_operational_review_batches.csv"
OUTPUT_JSONL = "foundation_operational_review_batches.jsonl"
OUTPUT_SUMMARY = "foundation_operational_review_batches_summary.json"


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


LANE_ORDER = {
    "historical_outcome_core": 0,
    "admission_unit_core": 1,
    "kice_score_reference": 2,
    "rule_schedule_2027": 3,
    "university_master": 4,
    "continuity_review": 5,
    "other_p0_review": 9,
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    rows = list(read_csv(foundation_dir / args.input_csv))
    batches = build_batches(rows)
    batches.sort(
        key=lambda row: (
            LANE_ORDER.get(str(row["reviewLane"]), 99),
            str(row.get("admissionYear") or row.get("academicYear") or ""),
            str(row.get("universityName") or ""),
            str(row.get("targetEntity") or ""),
        )
    )

    write_csv(foundation_dir / OUTPUT_CSV, batches)
    write_jsonl(foundation_dir / OUTPUT_JSONL, batches)
    summary = summarize(repo_root, foundation_dir, rows, batches)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation operational review batches complete. "
        f"inputRows={len(rows)} p0Rows={summary['inputRows']['p0']} "
        f"batchRows={len(batches)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--input-csv", default=INPUT_CSV)
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


def build_batches(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if normalize_text(row.get("priorityTier")) != "p0":
            continue
        if normalize_text(row.get("reviewStatus")) not in {"needs_human_verification", "manual_verified"}:
            continue
        lane = review_lane(row)
        grouped[group_key(lane, row)].append(row)

    return [make_batch(key, bucket) for key, bucket in grouped.items()]


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


def group_key(lane: str, row: dict[str, str]) -> tuple[str, ...]:
    target = normalize_text(row.get("targetEntity"))
    admission_year = normalize_text(row.get("admissionYear"))
    academic_year = normalize_text(row.get("academicYear"))
    unv_cd = normalize_text(row.get("unvCd"))
    university_name = normalize_text(row.get("universityName"))
    exam_type = normalize_text(row.get("examType"))
    subject_name = normalize_text(row.get("subjectName"))

    if lane in {"historical_outcome_core", "admission_unit_core", "rule_schedule_2027", "continuity_review"}:
        return (lane, target, admission_year, unv_cd, university_name)
    if lane == "kice_score_reference":
        return (lane, target, academic_year, exam_type, subject_name)
    if lane == "university_master":
        return (lane, target, "", unv_cd, university_name)
    return (lane, target, admission_year or academic_year, unv_cd, university_name)


def make_batch(key: tuple[str, ...], rows: list[dict[str, str]]) -> dict[str, Any]:
    lane = key[0]
    target = key[1]
    admission_year = ""
    academic_year = ""
    unv_cd = ""
    university_name = ""
    exam_type = ""
    subject_name = ""
    if lane == "kice_score_reference":
        academic_year = key[2]
        exam_type = key[3]
        subject_name = key[4]
    else:
        admission_year = key[2]
        unv_cd = key[3] if len(key) > 3 else ""
        university_name = key[4] if len(key) > 4 else ""

    source_artifacts = Counter(normalize_text(row.get("sourceArtifact")) for row in rows)
    actions = Counter(normalize_text(row.get("promotionAction")) for row in rows)
    blockers = Counter(
        flag
        for row in rows
        for flag in split_joined(row.get("blockerFlags"))
        if flag
    )
    ids = [normalize_text(row.get("promotionQueueId")) for row in rows if normalize_text(row.get("promotionQueueId"))]
    max_score = max((int_or_none(row.get("reviewPriorityScore")) or 0 for row in rows), default=0)
    source_paths = unique_nonempty(row.get("sourcePaths") for row in rows)
    raw_paths = unique_nonempty(row.get("rawPaths") for row in rows)
    source_urls = unique_nonempty(row.get("sourceUrls") for row in rows)

    batch_seed = "|".join([lane, target, admission_year, academic_year, unv_cd, university_name, exam_type, subject_name])
    return {
        "reviewBatchId": deterministic_uuid(f"foundation-operational-review-batch:{batch_seed}"),
        "artifactType": "foundation_operational_review_batch",
        "reviewLane": lane,
        "targetEntity": target,
        "admissionYear": admission_year,
        "academicYear": academic_year,
        "examType": exam_type,
        "subjectName": subject_name,
        "unvCd": unv_cd,
        "universityName": university_name,
        "batchRowCount": len(rows),
        "reviewPriorityScoreMax": max_score,
        "sourceArtifacts": "|".join(source_artifacts),
        "promotionActions": "|".join(actions),
        "blockerFlags": "|".join(blockers),
        "samplePromotionQueueIds": "|".join(ids[:20]),
        "sampleSourceUrls": "|".join(source_urls[:5]),
        "sampleRawPaths": "|".join(raw_paths[:5]),
        "sampleSourcePaths": "|".join(source_paths[:5]),
        "operatorNextStep": operator_next_step(lane),
        "reviewStatus": "needs_human_verification",
    }


def operator_next_step(lane: str) -> str:
    if lane == "historical_outcome_core":
        return "Compare source rows against original official/ADIGA coordinates, then promote score+quota HistoricalOutcome rows by university-year."
    if lane == "admission_unit_core":
        return "Verify yearly admission unit names, recruitment groups, and quota candidates before promoting AdmissionUnit seeds."
    if lane == "kice_score_reference":
        return "Spot-check official KICE workbook coordinates and promote score reference rows used by the calculation engine."
    if lane == "rule_schedule_2027":
        return "Review 2027 rule/schedule drafts against official documents before enabling 2027 strategy calculations."
    if lane == "university_master":
        return "Verify university identity fields and promote the master University seed rows."
    if lane == "continuity_review":
        return "Review cross-year continuity clusters or outcome series before using them for trend explanations."
    return "Review the linked promotion queue rows and original artifacts before promotion."


def summarize(
    repo_root: Path,
    foundation_dir: Path,
    input_rows: list[dict[str, str]],
    batches: list[dict[str, Any]],
) -> dict[str, Any]:
    p0_rows = [row for row in input_rows if normalize_text(row.get("priorityTier")) == "p0"]
    by_lane_rows = Counter()
    for row in p0_rows:
        by_lane_rows[review_lane(row)] += 1
    by_lane_batches = Counter(str(row.get("reviewLane") or "") for row in batches)
    by_target_batches = Counter(str(row.get("targetEntity") or "") for row in batches)
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_operational_review_batches_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "input": {
            "path": to_repo_relative(foundation_dir / INPUT_CSV, repo_root),
            "sha256": sha256_file(foundation_dir / INPUT_CSV),
        },
        "outputs": [
            to_repo_relative(foundation_dir / OUTPUT_CSV, repo_root),
            to_repo_relative(foundation_dir / OUTPUT_JSONL, repo_root),
        ],
        "inputRows": {
            "total": len(input_rows),
            "p0": len(p0_rows),
        },
        "batchRows": {
            "total": len(batches),
        },
        "p0RowsByReviewLane": dict(sorted(by_lane_rows.items())),
        "batchRowsByReviewLane": dict(sorted(by_lane_batches.items())),
        "batchRowsByTargetEntity": dict(sorted(by_target_batches.items())),
        "notes": [
            "This artifact is an assignment index for human verification, not a production seed export.",
            "Rows are grouped from p0 promotion queue candidates so reviewers can claim university-year or source-reference batches.",
            "Promotion remains blocked on human source comparison; this script does not mark rows verified.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "reviewBatchId",
        "artifactType",
        "reviewLane",
        "targetEntity",
        "admissionYear",
        "academicYear",
        "examType",
        "subjectName",
        "unvCd",
        "universityName",
        "batchRowCount",
        "reviewPriorityScoreMax",
        "sourceArtifacts",
        "promotionActions",
        "blockerFlags",
        "samplePromotionQueueIds",
        "sampleSourceUrls",
        "sampleRawPaths",
        "sampleSourcePaths",
        "operatorNextStep",
        "reviewStatus",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else value


def unique_nonempty(values: Iterable[Any]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        for part in split_joined(value):
            if part and part not in seen:
                seen.add(part)
                output.append(part)
    return output


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def int_or_none(value: Any) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def deterministic_uuid(seed: str) -> str:
    return str(uuid.UUID(hashlib.md5(seed.encode("utf-8")).hexdigest()))


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
