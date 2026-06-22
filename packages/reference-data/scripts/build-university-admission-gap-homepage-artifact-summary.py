#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_UNIVERSITY_SITE_DIR = "packages/reference-data/data/public/university-admission-sites"
DEFAULT_SUFFIX = "gap_homepage_links"
DEFAULT_YEARS = "2021,2022,2023,2024,2025,2026,2027"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    site_dir = resolve(repo_root, args.university_site_dir)
    suffix = args.suffix
    years = [int(value) for value in args.years.split(",") if value.strip()]

    yearly: dict[str, dict[str, Any]] = {}
    inputs: list[Path] = []
    totals = Counter()
    manifest_status = Counter()
    manifest_http_status = Counter()
    manifest_artifact_type = Counter()
    manifest_file_extension = Counter()
    attachment_role = Counter()
    attachment_file_extension = Counter()

    for year in years:
        summary_path = site_dir / f"university_admission_artifacts_summary_{year}_{suffix}.json"
        manifest_path = site_dir / f"university_admission_link_artifact_manifest_{year}_{suffix}.jsonl"
        attachment_path = site_dir / f"university_admission_attachment_candidates_{year}_{suffix}.csv"
        inputs.extend([summary_path, manifest_path, attachment_path])
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        yearly[str(year)] = {
            "attempted": int(summary.get("attempted") or 0),
            "fetched": int(summary.get("fetched") or 0),
            "failed": int(summary.get("failed") or 0),
            "detailHtmlArtifacts": int(summary.get("detailHtmlArtifacts") or 0),
            "directFileArtifacts": int(summary.get("directFileArtifacts") or 0),
            "attachmentCandidates": int(summary.get("attachmentCandidates") or 0),
        }
        totals.update(yearly[str(year)])

        for row in read_jsonl(manifest_path):
            manifest_status[str(row.get("status") or "")] += 1
            manifest_http_status[str(row.get("httpStatus") or "")] += 1
            manifest_artifact_type[str(row.get("artifactType") or "")] += 1
            manifest_file_extension[str(row.get("fileExtension") or "")] += 1

        for row in read_csv(attachment_path):
            attachment_role[str(row.get("attachmentRole") or "")] += 1
            attachment_file_extension[str(row.get("fileExtension") or "")] += 1

    output = {
        "provider": "university-admission-office",
        "artifactType": "university_admission_gap_homepage_artifacts_all_years_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "suffix": suffix,
        "years": years,
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in inputs
            if path.exists()
        ],
        "yearly": yearly,
        "aggregate": dict(totals),
        "byManifestStatus": counter_rows(manifest_status, 20),
        "byHttpStatus": counter_rows(manifest_http_status, 20),
        "byArtifactType": counter_rows(manifest_artifact_type, 10),
        "byArtifactFileExtension": counter_rows(manifest_file_extension, 30),
        "byAttachmentRole": counter_rows(attachment_role, 10),
        "byAttachmentFileExtension": counter_rows(attachment_file_extension, 30),
        "notes": [
            "This aggregate summarizes gap-homepage link artifact collection across yearly suffix manifests.",
            "Rows are source-preserving crawl artifacts and attachment crawl targets, not verified AdmissionRule or HistoricalOutcome records.",
            "The unsuffixed/latest per-suffix summary may reflect the last executed year; use this all-years summary for 2021-2027 totals.",
        ],
    }

    output_path = site_dir / f"university_admission_artifacts_summary_{suffix}_all_years.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "university admission gap homepage artifact all-years summary complete. "
        f"attempted={totals['attempted']} fetched={totals['fetched']} "
        f"attachments={totals['attachmentCandidates']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--university-site-dir", default=DEFAULT_UNIVERSITY_SITE_DIR)
    parser.add_argument("--suffix", default=DEFAULT_SUFFIX)
    parser.add_argument("--years", default=DEFAULT_YEARS)
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


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


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
