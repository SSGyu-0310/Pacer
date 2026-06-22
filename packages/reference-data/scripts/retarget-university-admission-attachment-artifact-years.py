#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_INPUT_GLOB = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_attachment_artifact_manifest_*_gap_worklist_html_bridge_file_high_value_20260613.jsonl"
)
DEFAULT_PUBLIC_DIR = "packages/reference-data/data/public/university-admission-sites"
DEFAULT_OUTPUT_SUFFIX = "gap_worklist_html_bridge_file_high_value_20260613_retargeted"
YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d)")


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    input_paths = resolve_glob(repo_root, args.input_glob)
    public_dir = resolve(repo_root, args.public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)

    rows_by_year: dict[int, list[dict[str, Any]]] = {}
    seen: set[str] = set()
    stats = Counter()

    for path in input_paths:
        for row in read_jsonl(path):
            stats["source_rows"] += 1
            if not is_fetched_file_row(row):
                stats["non_file_or_failed_rows"] += 1
                continue
            target_year, detected_years, year_source = target_year_for(
                row,
                min_year=args.min_year,
                max_year=args.max_year,
            )
            if target_year is None:
                stats["outside_target_year_rows"] += 1
                continue

            output = dict(row)
            original_year = int(row.get("year") or target_year)
            output["year"] = target_year
            output["retargetedFromManifestYear"] = original_year
            output["retargetedAdmissionYears"] = detected_years
            output["retargetedYearSource"] = year_source

            key = f"{target_year}|{canonical_url(output.get('canonicalAttachmentUrl') or output.get('attachmentUrl') or output.get('finalUrl'))}"
            if key in seen:
                stats["duplicate_rows"] += 1
                continue
            seen.add(key)
            rows_by_year.setdefault(target_year, []).append(output)
            stats[f"year_source:{year_source}"] += 1

    output_paths: list[Path] = []
    for year, rows in sorted(rows_by_year.items()):
        output_path = public_dir / f"university_admission_attachment_artifact_manifest_{year}_{args.output_suffix}.jsonl"
        write_jsonl(output_path, rows)
        output_paths.append(output_path)

    summary_path = public_dir / f"university_admission_attachment_artifact_manifest_{args.output_suffix}_retarget_summary.json"
    write_json(
        summary_path,
        {
            "provider": "university-admission-office",
            "artifactType": "admission_attachment_artifact_retarget_summary",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "inputPaths": [to_repo_relative(path, repo_root) for path in input_paths],
            "outputSuffix": args.output_suffix,
            "outputPaths": [to_repo_relative(path, repo_root) for path in output_paths],
            "parameters": {"minYear": args.min_year, "maxYear": args.max_year},
            "sourceRows": stats["source_rows"],
            "emittedRows": sum(len(rows) for rows in rows_by_year.values()),
            "outsideTargetYearRows": stats["outside_target_year_rows"],
            "nonFileOrFailedRows": stats["non_file_or_failed_rows"],
            "duplicateRows": stats["duplicate_rows"],
            "byYear": [{"value": str(year), "count": len(rows)} for year, rows in sorted(rows_by_year.items())],
            "byYearSource": counter_prefix_rows(stats, "year_source:"),
            "notes": [
                "Retargets fetched attachment manifests after HTTP content-disposition reveals the real admission year.",
                "Rows outside the configured year range are dropped instead of promoted under the collection year.",
                "Raw files are not moved; rawPath remains the original source-preserving fetch location.",
            ],
        },
    )

    print(
        "attachment manifest year retarget complete. "
        f"sourceRows={stats['source_rows']} "
        f"emitted={sum(len(rows) for rows in rows_by_year.values())} "
        f"outputs={len(output_paths)} "
        f"summary={to_repo_relative(summary_path, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-glob", default=DEFAULT_INPUT_GLOB)
    parser.add_argument("--public-dir", default=DEFAULT_PUBLIC_DIR)
    parser.add_argument("--output-suffix", default=DEFAULT_OUTPUT_SUFFIX)
    parser.add_argument("--min-year", type=int, default=2021)
    parser.add_argument("--max-year", type=int, default=2027)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def is_fetched_file_row(row: dict[str, Any]) -> bool:
    if str(row.get("status") or "") != "fetched":
        return False
    try:
        if int(row.get("httpStatus") or 0) != 200:
            return False
    except (TypeError, ValueError):
        return False
    return str(row.get("detectedKind") or "") == "file"


def target_year_for(row: dict[str, Any], *, min_year: int, max_year: int) -> tuple[int | None, list[int], str]:
    detected_years = detected_years_for(row)
    target_years = [year for year in detected_years if min_year <= year <= max_year]
    if detected_years and not target_years:
        return None, detected_years, "detected_outside_target"
    if target_years:
        return max(target_years), detected_years, "detected_from_artifact_metadata"

    original_year = int(row.get("year") or 0)
    if min_year <= original_year <= max_year:
        return original_year, [], "manifest_year_fallback"
    return None, [], "manifest_year_outside_target"


def detected_years_for(row: dict[str, Any]) -> list[int]:
    values = [
        row.get("suggestedFilename"),
        row.get("contentDisposition"),
        row.get("linkText"),
        row.get("sourceLinkText"),
        row.get("attachmentUrl"),
        row.get("finalUrl"),
    ]
    text = decode_percent(" ".join(str(value or "") for value in values))
    return sorted({int(match.group(1)) for match in YEAR_PATTERN.finditer(text)})


def canonical_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return re.sub(r";jsessionid=[^/?#;]*", "", text.split("#", 1)[0], flags=re.I)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() != "jsessionid"
    ]
    path = re.sub(r";jsessionid=[^/?#;]*", "", parsed.path, flags=re.I)
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urlencode(query, doseq=True),
            "",
        )
    )


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def counter_prefix_rows(counter: Counter[str], prefix: str) -> list[dict[str, Any]]:
    rows = [
        {"value": key.removeprefix(prefix), "count": value}
        for key, value in counter.items()
        if key.startswith(prefix)
    ]
    return sorted(rows, key=lambda row: (-row["count"], row["value"]))


def decode_percent(value: str) -> str:
    try:
        from urllib.parse import unquote

        return unquote(value)
    except Exception:
        return value


def resolve_glob(repo_root: Path, pattern: str) -> list[Path]:
    path = Path(pattern)
    if path.is_absolute():
        return sorted(path.parent.glob(path.name))
    return sorted(repo_root.glob(pattern))


def resolve(repo_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def find_repo_root(start: Path) -> Path:
    current = start.resolve()
    while True:
        if (current / "pnpm-workspace.yaml").exists():
            return current
        if current.parent == current:
            return start.resolve()
        current = current.parent


def to_repo_relative(path: Path, repo_root: Path) -> str:
    return str(path.resolve().relative_to(repo_root.resolve()))


if __name__ == "__main__":
    main()
