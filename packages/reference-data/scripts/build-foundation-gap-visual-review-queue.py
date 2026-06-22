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
DEFAULT_GAP_IMAGE_SOURCE_CANDIDATES = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_image_source_candidates.csv"
)

OUTPUT_JSONL = "foundation_gap_visual_review_queue.jsonl"
OUTPUT_CSV = "foundation_gap_visual_review_queue.csv"
OUTPUT_SUMMARY = "foundation_gap_visual_review_queue_summary.json"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    input_path = resolve(repo_root, args.gap_image_source_candidates)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    source_rows = read_csv(input_path)
    queue = build_queue(source_rows)
    queue.sort(
        key=lambda row: (
            priority_sort(row.get("priorityTier")),
            -int_or_none(row.get("visualReviewPriorityScore") or 0),
            str(row.get("reviewBucket") or ""),
            str(row.get("universityName") or ""),
            int_or_large(row.get("admissionYear")),
            str(row.get("sourceArtifactScope") or ""),
            int_or_large(first_value(row.get("pageNumbers"))),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, queue)
    write_csv(foundation_dir / OUTPUT_CSV, queue)
    summary = summarize(repo_root, input_path, source_rows, queue)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap visual review queue complete. "
        f"sourceRows={len(source_rows)} queueRows={len(queue)} "
        f"dedupeReduction={summary['dedupe']['reductionRows']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument(
        "--gap-image-source-candidates",
        default=DEFAULT_GAP_IMAGE_SOURCE_CANDIDATES,
    )
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


def build_queue(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        key = (
            normalize_text(row.get("imageSourceKind")),
            normalize_text(row.get("sourceArtifactScope")),
            normalize_text(row.get("unvCd")),
            normalize_text(row.get("admissionYear")),
            source_evidence_key(row),
        )
        groups[key].append(row)
    return [make_queue_item(key, group) for key, group in groups.items()]


def source_evidence_key(row: dict[str, str]) -> str:
    return first_nonempty(
        row,
        "canonicalImageKey",
        "pageImageSha256",
        "rawImagePath",
        "pageImagePath",
        "ocrSourcePath",
    )


def make_queue_item(
    key: tuple[str, str, str, str, str],
    group: list[dict[str, str]],
) -> dict[str, Any]:
    image_source_kind, source_scope, unv_cd, admission_year, evidence_key = key
    group = sorted(
        group,
        key=lambda row: (
            -int_or_none(row.get("imageReviewPriorityScore") or 0),
            str(row.get("imageEvidenceTarget") or ""),
            str(row.get("imageEvidenceRole") or ""),
            str(row.get("collectionTargetId") or ""),
        ),
    )
    top = group[0]
    targets = sorted(set(joined_values(group, "imageEvidenceTarget")))
    roles = sorted(set(joined_values(group, "imageEvidenceRole")))
    missing_flags = sorted(set(flag for row in group for flag in split_joined(row.get("missingFlags"))))
    bucket = review_bucket(targets, roles, image_source_kind)
    priority = visual_priority_score(group, bucket)

    return {
        "visualReviewQueueId": deterministic_uuid(
            f"gap-visual-review:{image_source_kind}:{source_scope}:{unv_cd}:{admission_year}:{evidence_key}"
        ),
        "artifactType": "foundation_gap_visual_review_queue_item",
        "priorityTier": normalize_text(top.get("priorityTier")) or "p0",
        "visualReviewPriorityScore": priority,
        "reviewBucket": bucket,
        "reviewAction": review_action(bucket),
        "reviewStatus": "needs_human_verification",
        "imageSourceKind": image_source_kind,
        "sourceProvider": normalize_text(top.get("sourceProvider")),
        "sourceArtifactScope": source_scope,
        "unvCd": unv_cd,
        "universityName": normalize_text(top.get("universityName")),
        "admissionYear": int_or_none(admission_year) or admission_year,
        "sourceEvidenceKey": evidence_key,
        "candidateRows": len(group),
        "matchedCollectionTargetCount": len({normalize_text(row.get("collectionTargetId")) for row in group}),
        "imageEvidenceTargets": "|".join(targets),
        "imageEvidenceRoles": "|".join(roles),
        "missingFlags": "|".join(missing_flags),
        "targetEntities": "|".join(sorted(set(value for row in group for value in split_joined(row.get("targetEntities"))))),
        "recommendedActions": "|".join(
            sorted(set(value for row in group for value in split_joined(row.get("recommendedActions"))))
        ),
        "sourceLinkRoles": "|".join(sorted(set(joined_values(group, "sourceLinkRole")))),
        "attachmentRoles": "|".join(sorted(set(joined_values(group, "attachmentRole")))),
        "detectedDocumentRoles": "|".join(sorted(set(joined_values(group, "detectedDocumentRole")))),
        "pageNumbers": "|".join(sorted(set(joined_values(group, "pageNumber")), key=int_or_large)),
        "imageBytesMax": max(int_or_none(row.get("imageBytes")) or 0 for row in group),
        "widthMax": max(int_or_none(row.get("width")) or 0 for row in group),
        "heightMax": max(int_or_none(row.get("height")) or 0 for row in group),
        "pageImagePath": first_nonempty(top, "pageImagePath", "rawImagePath"),
        "rawImagePath": first_nonempty(top, "rawImagePath"),
        "rawPdfPath": first_nonempty(top, "rawPdfPath", "detailRawPath"),
        "detailRawPath": first_nonempty(top, "detailRawPath"),
        "ocrSourcePath": first_nonempty(top, "ocrSourcePath"),
        "pageImageSha256": first_nonempty(top, "pageImageSha256"),
        "rawPdfSha256": first_nonempty(top, "rawPdfSha256"),
        "ocrEvidenceSha256": "|".join(sorted(set(joined_values(group, "ocrEvidenceSha256")))[:12]),
        "sourceCandidateUrl": first_nonempty(top, "sourceCandidateUrl"),
        "attachmentUrl": first_nonempty(top, "attachmentUrl"),
        "imageUrl": first_nonempty(top, "imageUrl"),
        "ocrTextPreview": normalize_text(top.get("ocrTextPreview"))[:700],
        "matchedKeywords": "|".join(sorted(set(value for row in group for value in split_joined(row.get("matchedKeywords"))))),
        "topCandidateReason": normalize_text(top.get("candidateReason")),
        "operatorNextStep": operator_next_step(bucket, targets, roles),
    }


def review_bucket(targets: list[str], roles: list[str], image_source_kind: str) -> str:
    role_set = set(roles)
    target_set = set(targets)
    if "HistoricalOutcome" in target_set:
        return "historical_outcome_visual_table"
    if "ReviewQueue" in target_set:
        return "auxiliary_visual_review"
    if "AdmissionRule" in target_set:
        if "csat_rule_ocr_page" in role_set or "csat_reflection_rule" in role_set:
            return "csat_rule_visual_table"
        if "screening_method_ocr_page" in role_set or "screening_method" in role_set:
            return "screening_method_visual_table"
        if "recruitment_rule_image" in role_set:
            return "admission_rule_visual_table"
        return "admission_rule_visual_review"
    if image_source_kind == "adiga_detail_image":
        return "adiga_low_signal_image_triage"
    return "low_signal_pdf_page_triage"


def review_action(bucket: str) -> str:
    return {
        "historical_outcome_visual_table": "visually_extract_historical_outcome_or_admission_unit_table",
        "csat_rule_visual_table": "visually_extract_csat_reflection_rule_draft",
        "screening_method_visual_table": "visually_extract_screening_method_or_evaluation_table",
        "admission_rule_visual_table": "visually_extract_admission_rule_table",
        "admission_rule_visual_review": "review_visual_page_for_admission_rule_signal",
        "auxiliary_visual_review": "review_auxiliary_visual_context_or_discard",
        "adiga_low_signal_image_triage": "triage_adiga_low_signal_image_before_promotion",
        "low_signal_pdf_page_triage": "triage_low_signal_pdf_page_before_promotion",
    }.get(bucket, "review_visual_or_ocr_source_before_promotion")


def operator_next_step(bucket: str, targets: list[str], roles: list[str]) -> str:
    if bucket == "historical_outcome_visual_table":
        return "Open the page/image and extract 모집단위, 모집인원, 경쟁률, 충원, 환산점수/백분위 only after source verification."
    if bucket == "csat_rule_visual_table":
        return "Open the page/image and extract 수능 반영영역, 반영비율, 영어/한국사/탐구 정책 candidates before formula verification."
    if bucket == "screening_method_visual_table":
        return "Open the page/image and extract 단계/일괄, 면접/서류/실기/논술, 평가요소 and percentage candidates."
    if bucket.startswith("admission_rule"):
        return "Open the page/image, classify the rule type, and create or discard a structured AdmissionRule draft candidate."
    if "OCRReviewQueue" in set(targets):
        return "Inspect the visual page and OCR text; discard promotional/noise pages or reclassify them to a structured target."
    return f"Inspect visual/OCR source roles={','.join(roles)} before any DB promotion."


def visual_priority_score(group: list[dict[str, str]], bucket: str) -> int:
    score = max(int_or_none(row.get("imageReviewPriorityScore")) or 0 for row in group)
    score += min(40, max(0, len(group) - 1) * 3)
    if bucket == "historical_outcome_visual_table":
        score += 35
    elif bucket in {"csat_rule_visual_table", "screening_method_visual_table"}:
        score += 30
    elif bucket.startswith("admission_rule"):
        score += 20
    elif bucket == "low_signal_pdf_page_triage":
        score -= 15
    if any(normalize_text(row.get("sourceArtifactScope")) == "gap_homepage_file_attachment" for row in group):
        score += 8
    return max(0, score)


def summarize(
    repo_root: Path,
    input_path: Path,
    source_rows: list[dict[str, str]],
    queue: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_visual_review_queue_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {
                "path": to_repo_relative(input_path, repo_root),
                "sha256": sha256_file(input_path),
                "rows": len(source_rows),
            }
        ],
        "sourceRows": {
            "total": len(source_rows),
            "byImageSourceKind": counter_rows(Counter(str(row.get("imageSourceKind") or "") for row in source_rows)),
            "bySourceArtifactScope": counter_rows(
                Counter(str(row.get("sourceArtifactScope") or "") for row in source_rows)
            ),
            "byImageEvidenceTarget": counter_rows(
                Counter(str(row.get("imageEvidenceTarget") or "") for row in source_rows)
            ),
        },
        "queueRows": {
            "total": len(queue),
            "recentAdmissionYears2021To2027": sum(
                1 for row in queue if 2021 <= (int_or_none(row.get("admissionYear")) or 0) <= 2027
            ),
        },
        "dedupe": {
            "sourceRows": len(source_rows),
            "queueRows": len(queue),
            "reductionRows": len(source_rows) - len(queue),
            "reductionRatio": round((len(source_rows) - len(queue)) / len(source_rows), 4) if source_rows else 0,
        },
        "byReviewBucket": counter_rows(Counter(str(row.get("reviewBucket") or "") for row in queue), 20),
        "byImageSourceKind": counter_rows(Counter(str(row.get("imageSourceKind") or "") for row in queue), 20),
        "bySourceArtifactScope": counter_rows(Counter(str(row.get("sourceArtifactScope") or "") for row in queue), 20),
        "byImageEvidenceTargets": counter_rows(Counter(str(row.get("imageEvidenceTargets") or "") for row in queue), 30),
        "byAdmissionYear": dict(sorted(Counter(str(row.get("admissionYear") or "") for row in queue).items())),
        "notes": [
            "This queue deduplicates gap image source candidates into one row per source image/PDF page and university year.",
            "Rows are visual/OCR review tasks only; they are not verified AdmissionRule or HistoricalOutcome records.",
            "The queue is designed to help reviewers avoid inspecting the same page repeatedly across multiple gap targets.",
        ],
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "visualReviewQueueId",
        "artifactType",
        "priorityTier",
        "visualReviewPriorityScore",
        "reviewBucket",
        "reviewAction",
        "reviewStatus",
        "imageSourceKind",
        "sourceProvider",
        "sourceArtifactScope",
        "unvCd",
        "universityName",
        "admissionYear",
        "sourceEvidenceKey",
        "candidateRows",
        "matchedCollectionTargetCount",
        "imageEvidenceTargets",
        "imageEvidenceRoles",
        "missingFlags",
        "targetEntities",
        "recommendedActions",
        "sourceLinkRoles",
        "attachmentRoles",
        "detectedDocumentRoles",
        "pageNumbers",
        "imageBytesMax",
        "widthMax",
        "heightMax",
        "pageImagePath",
        "rawImagePath",
        "rawPdfPath",
        "detailRawPath",
        "ocrSourcePath",
        "pageImageSha256",
        "rawPdfSha256",
        "ocrEvidenceSha256",
        "sourceCandidateUrl",
        "attachmentUrl",
        "imageUrl",
        "ocrTextPreview",
        "matchedKeywords",
        "topCandidateReason",
        "operatorNextStep",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def joined_values(rows: list[dict[str, str]], field: str) -> list[str]:
    return [normalize_text(row.get(field)) for row in rows if normalize_text(row.get(field))]


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [part for part in re.split(r"[|,;]", text) if part]


def first_value(value: Any) -> str:
    return split_joined(value)[0] if split_joined(value) else ""


def first_nonempty(row: dict[str, Any], *fields: str) -> str:
    for field in fields:
        text = normalize_text(row.get(field))
        if text:
            return text
    return ""


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def int_or_large(value: Any) -> int:
    parsed = int_or_none(value)
    return parsed if parsed is not None else 999999


def priority_sort(value: Any) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(normalize_text(value), 9)


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
