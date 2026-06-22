#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


DEFAULT_CHECKLIST = (
    "packages/reference-data/data/public/foundation/"
    "foundation_release_monitor_checklist.csv"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites"
DEFAULT_SUFFIX = "release_monitor_ready"

READY_STATUSES = {
    "public",
    "official_public",
    "ready_for_collection",
}

LINK_FIELDNAMES = [
    "provider",
    "artifactType",
    "year",
    "unvCd",
    "universityName",
    "campus",
    "sourceHomepageUrl",
    "finalHomepageUrl",
    "rawPath",
    "linkRole",
    "linkText",
    "hrefRaw",
    "resolvedUrl",
    "hostname",
    "fileExtension",
    "keywordHits",
]

ATTACHMENT_FIELDNAMES = [
    "provider",
    "artifactType",
    "year",
    "unvCd",
    "universityName",
    "campus",
    "sourceLinkRole",
    "sourceLinkText",
    "sourceCandidateUrl",
    "detailRawPath",
    "attachmentRole",
    "linkText",
    "hrefRaw",
    "resolvedUrl",
    "hostname",
    "fileExtension",
    "keywordHits",
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    checklist_path = resolve(repo_root, args.checklist)
    output_dir = resolve(repo_root, args.output_dir)

    checklist_rows = read_csv(checklist_path)
    link_rows, attachment_rows, summary_counts = build_rows(checklist_rows)

    year = args.year
    link_path = output_dir / f"university_admission_link_candidates_{year}_{args.suffix}.csv"
    attachment_path = output_dir / f"university_admission_attachment_candidates_{year}_{args.suffix}.csv"
    summary_path = output_dir / f"university_admission_release_monitor_collector_inputs_{year}_{args.suffix}_summary.json"

    write_csv(link_path, LINK_FIELDNAMES, link_rows)
    write_csv(attachment_path, ATTACHMENT_FIELDNAMES, attachment_rows)

    summary = {
        "provider": "pacer-reference-data",
        "artifactType": "university_admission_release_monitor_collector_inputs_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputChecklist": to_repo_relative(checklist_path, repo_root),
        "outputLinkCandidates": to_repo_relative(link_path, repo_root),
        "outputAttachmentCandidates": to_repo_relative(attachment_path, repo_root),
        "checklistRows": len(checklist_rows),
        "readyLinkRows": len(link_rows),
        "readyAttachmentRows": len(attachment_rows),
        "byReleaseEvidenceStatus": dict(sorted(summary_counts["by_status"].items())),
        "skippedUrlsByNonReadyStatus": dict(sorted(summary_counts["skipped_url_by_status"].items())),
        "notes": [
            "Rows are emitted only when releaseEvidenceStatus is public/official_public/ready_for_collection.",
            "Fill officialResultUrl for HTML/detail pages and officialAttachmentUrl for direct files.",
            "Run the existing artifact/attachment collectors against these narrow CSVs after official 2027 results are public.",
        ],
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "foundation release monitor collector inputs complete. "
        f"checklistRows={len(checklist_rows)} linkRows={len(link_rows)} "
        f"attachmentRows={len(attachment_rows)} output={to_repo_relative(output_dir, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checklist", default=DEFAULT_CHECKLIST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--suffix", default=DEFAULT_SUFFIX)
    parser.add_argument("--year", default="2027")
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


def build_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Counter[str]]]:
    link_rows: list[dict[str, str]] = []
    attachment_rows: list[dict[str, str]] = []
    by_status: Counter[str] = Counter()
    skipped_url_by_status: Counter[str] = Counter()

    for row in rows:
        year = row.get("admissionYear", "")
        if year != "2027":
            continue
        status = normalize(row.get("releaseEvidenceStatus"))
        by_status[status] += 1
        result_url = row.get("officialResultUrl", "").strip()
        attachment_url = row.get("officialAttachmentUrl", "").strip()
        has_url = bool(result_url or attachment_url)
        if status not in READY_STATUSES:
            if has_url:
                skipped_url_by_status[status] += 1
            continue

        if result_url:
            link_rows.append(build_link_row(row, result_url))
        if attachment_url:
            attachment_rows.append(build_attachment_row(row, result_url, attachment_url))

    link_rows.sort(key=sort_key)
    attachment_rows.sort(key=sort_key)
    return link_rows, attachment_rows, {
        "by_status": by_status,
        "skipped_url_by_status": skipped_url_by_status,
    }


def build_link_row(row: dict[str, str], url: str) -> dict[str, str]:
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_site_link_candidate",
        "year": row.get("admissionYear", ""),
        "unvCd": row.get("unvCd", ""),
        "universityName": row.get("universityName", ""),
        "campus": "",
        "sourceHomepageUrl": url,
        "finalHomepageUrl": url,
        "rawPath": "",
        "linkRole": "admission_result",
        "linkText": release_label(row, "official result page"),
        "hrefRaw": url,
        "resolvedUrl": url,
        "hostname": hostname(url),
        "fileExtension": file_extension(url),
        "keywordHits": keyword_hits(row),
    }


def build_attachment_row(row: dict[str, str], result_url: str, attachment_url: str) -> dict[str, str]:
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_attachment_link_candidate",
        "year": row.get("admissionYear", ""),
        "unvCd": row.get("unvCd", ""),
        "universityName": row.get("universityName", ""),
        "campus": "",
        "sourceLinkRole": "admission_result",
        "sourceLinkText": release_label(row, "official result source"),
        "sourceCandidateUrl": result_url or attachment_url,
        "detailRawPath": "",
        "attachmentRole": "admission_result",
        "linkText": release_label(row, "official result attachment"),
        "hrefRaw": attachment_url,
        "resolvedUrl": attachment_url,
        "hostname": hostname(attachment_url),
        "fileExtension": file_extension(attachment_url),
        "keywordHits": keyword_hits(row),
    }


def release_label(row: dict[str, str], suffix: str) -> str:
    university = row.get("universityName", "")
    year = row.get("admissionYear", "")
    return f"{university} {year} {suffix}".strip()


def keyword_hits(row: dict[str, str]) -> str:
    flags = row.get("missingFlags", "")
    parts = ["release_monitor", "입시결과", "최종등록자", "경쟁률"]
    if "missing_quota_competition" in flags:
        parts.append("모집인원")
    return "|".join(dict.fromkeys(parts))


def hostname(url: str) -> str:
    return urlparse(url).hostname or ""


def file_extension(url: str) -> str:
    path = urlparse(url).path
    if "." not in path.rsplit("/", 1)[-1]:
        return ""
    return path.rsplit(".", 1)[-1].lower()


def normalize(value: Any) -> str:
    return str(value or "").strip().lower()


def sort_key(row: dict[str, str]) -> tuple[str, str, str]:
    return (row.get("universityName", ""), row.get("unvCd", ""), row.get("resolvedUrl", ""))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
