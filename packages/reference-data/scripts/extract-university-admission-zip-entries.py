#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote


DEFAULT_UNIVERSITY_SITE_DIR = "packages/reference-data/data/public/university-admission-sites"
DEFAULT_RAW_DIR = ".reference-data/raw/university-admission-sites"
DEFAULT_YEARS = "2027"
OUTPUT_JSONL_TEMPLATE = "university_admission_zip_entry_artifact_manifest_{year}.jsonl"
OUTPUT_CSV_TEMPLATE = "university_admission_zip_entry_artifact_index_{year}.csv"
OUTPUT_SUMMARY_TEMPLATE = "university_admission_zip_entry_summary_{year}.json"
OUTPUT_ALL_YEARS_SUMMARY = "university_admission_zip_entry_summary_all_years.json"
DEFAULT_ALLOWED_INFERRED_YEARS = "2021,2022,2023,2024,2025,2026,2027,2028"

DOCUMENT_EXTENSIONS = {
    "doc",
    "docx",
    "hwp",
    "hwpx",
    "pdf",
    "ppt",
    "pptx",
    "xls",
    "xlsx",
}

MIME_BY_EXTENSION = {
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "hwp": "application/x-hwp",
    "hwpx": "application/hwp+zip",
    "pdf": "application/pdf",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xls": "application/vnd.ms-excel",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    site_dir = resolve(repo_root, args.university_site_dir)
    output_dir = resolve(repo_root, args.output_dir) if args.output_dir else site_dir
    raw_dir = resolve(repo_root, args.raw_dir)
    years = [int(value) for value in args.years.split(",") if value.strip()]
    allowed_inferred_years = {
        int(value) for value in args.allowed_inferred_years.split(",") if value.strip()
    }

    yearly_summaries: dict[str, Any] = {}
    all_inputs: list[Path] = []
    for year in years:
        manifest_paths = select_manifest_paths(site_dir, year, args.manifest_glob)
        all_inputs.extend(manifest_paths)
        rows, source_zip_rows = extract_year_entries(
            repo_root=repo_root,
            raw_dir=raw_dir,
            year=year,
            manifest_paths=manifest_paths,
            include_unsupported=args.include_unsupported,
            infer_entry_year_from_name=args.infer_entry_year_from_name,
            require_inferred_year=args.require_inferred_year,
            allowed_inferred_years=allowed_inferred_years,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(output_dir / output_name(OUTPUT_JSONL_TEMPLATE, year, args.output_suffix), rows)
        write_csv(output_dir / output_name(OUTPUT_CSV_TEMPLATE, year, args.output_suffix), rows)
        summary = summarize_year(
            repo_root,
            year,
            manifest_paths,
            source_zip_rows,
            rows,
            infer_entry_year_from_name=args.infer_entry_year_from_name,
            require_inferred_year=args.require_inferred_year,
        )
        (output_dir / output_name(OUTPUT_SUMMARY_TEMPLATE, year, args.output_suffix)).write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        yearly_summaries[str(year)] = summary
        print(
            "university admission zip entries "
            f"year={year} sourceZips={summary['sourceZipRows']} "
            f"entries={summary['zipEntryRows']} documentEntries={summary['documentEntryRows']}"
        )

    all_years = summarize_all_years(repo_root, years, yearly_summaries)
    (output_dir / output_name(OUTPUT_ALL_YEARS_SUMMARY, None, args.output_suffix)).write_text(
        json.dumps(all_years, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "university admission zip entry extraction complete. "
        f"years={len(years)} entries={all_years['aggregate']['zipEntryRows']} "
        f"documents={all_years['aggregate']['documentEntryRows']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--university-site-dir", default=DEFAULT_UNIVERSITY_SITE_DIR)
    parser.add_argument("--output-dir")
    parser.add_argument("--raw-dir", default=DEFAULT_RAW_DIR)
    parser.add_argument("--years", default=DEFAULT_YEARS)
    parser.add_argument(
        "--manifest-glob",
        action="append",
        default=[],
        help=(
            "Optional glob(s), relative to --university-site-dir unless absolute, "
            "for the source attachment manifests. {year} is expanded."
        ),
    )
    parser.add_argument("--output-suffix", default="")
    parser.add_argument(
        "--infer-entry-year-from-name",
        action="store_true",
        help="Set each ZIP entry row.year from the decoded entry filename when a public admission-year signal is present.",
    )
    parser.add_argument(
        "--require-inferred-year",
        action="store_true",
        help="With --infer-entry-year-from-name, skip ZIP entries whose decoded filename has no allowed year signal.",
    )
    parser.add_argument("--allowed-inferred-years", default=DEFAULT_ALLOWED_INFERRED_YEARS)
    parser.add_argument(
        "--include-unsupported",
        action="store_true",
        help="Also emit non-document ZIP entries such as .ai or .bat files.",
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


def select_manifest_paths(site_dir: Path, year: int, manifest_globs: list[str]) -> list[Path]:
    if not manifest_globs:
        return sorted(site_dir.glob(f"university_admission_attachment_artifact_manifest_{year}*.jsonl"))

    paths: list[Path] = []
    seen: set[Path] = set()
    for pattern in manifest_globs:
        expanded = pattern.format(year=year)
        base = Path(expanded)
        matches = sorted(base.parent.glob(base.name)) if base.is_absolute() else sorted(site_dir.glob(expanded))
        for path in matches:
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(path)
    return paths


def output_name(template: str, year: int | None, suffix: str) -> str:
    name = template.format(year=year) if year is not None else template
    clean_suffix = re.sub(r"[^0-9A-Za-z_-]+", "_", suffix.strip()).strip("_")
    if not clean_suffix:
        return name
    stem = Path(name).stem
    suffix_part = "".join(Path(name).suffixes)
    if suffix_part:
        return f"{stem}_{clean_suffix}{suffix_part}"
    return f"{name}_{clean_suffix}"


def extract_year_entries(
    *,
    repo_root: Path,
    raw_dir: Path,
    year: int,
    manifest_paths: list[Path],
    include_unsupported: bool,
    infer_entry_year_from_name: bool,
    require_inferred_year: bool,
    allowed_inferred_years: set[int],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_zip_rows = source_zip_artifacts(manifest_paths, year)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for source in source_zip_rows:
        raw_zip_path = repo_root / normalize_text(source.get("rawPath"))
        if not raw_zip_path.exists() or not zipfile.is_zipfile(raw_zip_path):
            continue
        with zipfile.ZipFile(raw_zip_path) as archive:
            for index, info in enumerate(archive.infolist(), start=1):
                if info.is_dir():
                    continue
                raw_entry_name = info.filename
                decoded_entry_name = decoded_zip_name(raw_entry_name, info)
                extension = file_extension(decoded_entry_name or raw_entry_name)
                if not include_unsupported and extension not in DOCUMENT_EXTENSIONS:
                    continue
                inferred_year = infer_admission_year_from_entry_name(
                    decoded_entry_name or raw_entry_name,
                    allowed_inferred_years,
                )
                if infer_entry_year_from_name and require_inferred_year and inferred_year is None:
                    continue
                entry_year = inferred_year if infer_entry_year_from_name and inferred_year is not None else year
                try:
                    entry_bytes = archive.read(info)
                except RuntimeError:
                    continue
                entry_sha256 = sha256_bytes(entry_bytes)
                key = (
                    normalize_text(source.get("rawPath")),
                    raw_entry_name,
                    entry_sha256,
                    normalize_text(source.get("_manifestPath")),
                )
                if key in seen:
                    continue
                seen.add(key)
                entry_raw_path = write_entry_file(
                    repo_root=repo_root,
                    raw_dir=raw_dir,
                    year=entry_year,
                    source=source,
                    entry_index=index,
                    entry_sha256=entry_sha256,
                    extension=extension,
                    entry_bytes=entry_bytes,
                )
                rows.append(
                    zip_entry_manifest_row(
                    repo_root=repo_root,
                    year=entry_year,
                    source_year=year,
                    source=source,
                    info=info,
                    raw_entry_name=raw_entry_name,
                    decoded_entry_name=decoded_entry_name,
                    inferred_year=inferred_year,
                    entry_index=index,
                    entry_sha256=entry_sha256,
                    entry_raw_path=entry_raw_path,
                        extension=extension,
                        entry_bytes=entry_bytes,
                    )
                )
    rows.sort(
        key=lambda row: (
            int(row.get("year") or 0),
            str(row.get("unvCd") or ""),
            str(row.get("sourceZipSha256") or ""),
            int(row.get("zipEntryIndex") or 0),
            str(row.get("sha256") or ""),
        )
    )
    return rows, source_zip_rows


def source_zip_artifacts(manifest_paths: list[Path], year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for path in manifest_paths:
        for row in read_jsonl(path):
            if not is_http_ok_zip(row, year):
                continue
            key = (
                normalize_text(row.get("rawPath")),
                normalize_text(row.get("sha256")),
                to_repo_relative(path, find_repo_root(Path.cwd())),
            )
            if key in seen:
                continue
            seen.add(key)
            copied = dict(row)
            copied["_manifestPath"] = str(path)
            rows.append(copied)
    return rows


def is_http_ok_zip(row: dict[str, Any], year: int) -> bool:
    return (
        normalize_text(row.get("status")) == "fetched"
        and normalize_text(row.get("detectedKind")) == "file"
        and normalize_text(row.get("fileExtension")).lower() == "zip"
        and int_or_none(row.get("year")) == year
        and 200 <= (int_or_none(row.get("httpStatus")) or 0) < 300
    )


def write_entry_file(
    *,
    repo_root: Path,
    raw_dir: Path,
    year: int,
    source: dict[str, Any],
    entry_index: int,
    entry_sha256: str,
    extension: str,
    entry_bytes: bytes,
) -> str:
    unv_cd = normalize_text(source.get("unvCd")) or "unknown"
    source_sha = normalize_text(source.get("sha256"))[:16] or sha256_text(
        normalize_text(source.get("rawPath"))
    )[:16]
    suffix = f".{extension}" if extension else ".bin"
    entry_path = (
        raw_dir
        / str(year)
        / unv_cd
        / "zip-entries"
        / source_sha
        / f"{entry_index:03d}_{entry_sha256[:16]}{suffix}"
    )
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_bytes(entry_bytes)
    return to_repo_relative(entry_path, repo_root)


def zip_entry_manifest_row(
    *,
    repo_root: Path,
    year: int,
    source_year: int,
    source: dict[str, Any],
    info: zipfile.ZipInfo,
    raw_entry_name: str,
    decoded_entry_name: str,
    inferred_year: int | None,
    entry_index: int,
    entry_sha256: str,
    entry_raw_path: str,
    extension: str,
    entry_bytes: bytes,
) -> dict[str, Any]:
    source_manifest = Path(normalize_text(source.get("_manifestPath")))
    entry_fragment = quote(raw_entry_name)
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_zip_entry_artifact",
        "year": year,
        "sourceManifestYear": source_year,
        "inferredAdmissionYear": inferred_year,
        "unvCd": source.get("unvCd"),
        "universityName": source.get("universityName"),
        "campus": source.get("campus"),
        "sourceLinkRole": source.get("sourceLinkRole"),
        "attachmentRole": "zip_entry",
        "parentAttachmentRole": source.get("attachmentRole"),
        "linkText": decoded_entry_name or raw_entry_name,
        "sourceCandidateUrl": source.get("sourceCandidateUrl"),
        "attachmentUrl": f"{source.get('attachmentUrl') or source.get('finalUrl')}#zip-entry={entry_fragment}",
        "canonicalAttachmentUrl": f"{source.get('canonicalAttachmentUrl') or source.get('finalUrl')}#zip-entry={entry_fragment}",
        "finalUrl": f"{source.get('finalUrl') or source.get('attachmentUrl')}#zip-entry={entry_fragment}",
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "rawPath": entry_raw_path,
        "sha256": entry_sha256,
        "bytes": len(entry_bytes),
        "httpStatus": 200,
        "contentType": MIME_BY_EXTENSION.get(extension, ""),
        "contentDisposition": "",
        "suggestedFilename": decoded_entry_name or raw_entry_name,
        "fileExtension": extension,
        "detectedKind": "file",
        "status": "fetched",
        "sourceManifestPath": to_repo_relative(source_manifest, repo_root),
        "sourceZipRawPath": source.get("rawPath"),
        "sourceZipSha256": source.get("sha256"),
        "sourceZipBytes": source.get("bytes"),
        "zipEntryIndex": entry_index,
        "zipEntryRawName": raw_entry_name,
        "zipEntryDecodedName": decoded_entry_name,
        "zipEntryCompressedBytes": info.compress_size,
        "zipEntryUncompressedBytes": info.file_size,
        "zipEntryCompressionType": info.compress_type,
        "zipEntryEncrypted": bool(info.flag_bits & 0x1),
    }


def infer_admission_year_from_entry_name(name: str, allowed_years: set[int]) -> int | None:
    text = normalize_text(name)
    if not text:
        return None

    strong_patterns = [
        r"(20(?:2[1-8]))\s*학\s*년\s*도",
        r"(20(?:2[1-8]))\s*(?:대학입학|정시|수시|모집|편입|지원현황|입시|전형|성적|결과|충원|경쟁률)",
        r"(?:대학입학|정시|수시|모집|편입|지원현황|입시|전형|성적|결과|충원|경쟁률)\s*(20(?:2[1-8]))",
    ]
    for pattern in strong_patterns:
        for match in re.findall(pattern, text):
            year = int(match)
            if year in allowed_years:
                return year

    for match in re.findall(r"20(?:2[1-8])", text):
        year = int(match)
        if year in allowed_years:
            return year
    return None


def decoded_zip_name(name: str, info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return name
    try:
        repaired = name.encode("cp437").decode("cp949")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name
    return repaired if korean_or_less_garbled(repaired, name) else name


def korean_or_less_garbled(repaired: str, original: str) -> bool:
    repaired_korean = len(re.findall(r"[가-힣]", repaired))
    original_garbled = len(re.findall(r"[╟╜╡╢╧╛╫╬└┴┼├─│]", original))
    return repaired_korean > 0 or original_garbled > 0


def file_extension(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    return re.sub(r"[^0-9a-z]+", "", suffix)


def summarize_year(
    repo_root: Path,
    year: int,
    manifest_paths: list[Path],
    source_zip_rows: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    *,
    infer_entry_year_from_name: bool,
    require_inferred_year: bool,
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "artifactType": "university_admission_zip_entry_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in manifest_paths
            if path.exists()
        ],
        "sourceZipRows": len(source_zip_rows),
        "uniqueSourceZipSha256": len({normalize_text(row.get("sha256")) for row in source_zip_rows}),
        "zipEntryRows": len(rows),
        "documentEntryRows": sum(1 for row in rows if row.get("fileExtension") in DOCUMENT_EXTENSIONS),
        "uniqueZipEntrySha256": len({normalize_text(row.get("sha256")) for row in rows}),
        "inferEntryYearFromName": infer_entry_year_from_name,
        "requireInferredYear": require_inferred_year,
        "byEntryYear": counter_rows(Counter(str(row.get("year") or "") for row in rows), 20),
        "bySourceLinkRole": counter_rows(Counter(str(row.get("sourceLinkRole") or "") for row in rows), 20),
        "byParentAttachmentRole": counter_rows(
            Counter(str(row.get("parentAttachmentRole") or "") for row in rows), 20
        ),
        "byFileExtension": counter_rows(Counter(str(row.get("fileExtension") or "") for row in rows), 30),
        "byUniversity": counter_rows(Counter(str(row.get("universityName") or "") for row in rows), 30),
        "notes": [
            "ZIP entries are extracted from already fetched public university admission-office ZIP artifacts.",
            "The entry manifest is shaped like an attachment artifact manifest so existing PDF/HWP/workbook extraction scripts can consume it.",
            "Parent ZIP raw path and SHA-256 are preserved for source auditability.",
        ],
    }


def summarize_all_years(
    repo_root: Path,
    years: list[int],
    yearly_summaries: dict[str, Any],
) -> dict[str, Any]:
    totals = Counter()
    extension = Counter()
    universities = Counter()
    inputs = []
    for year in years:
        summary = yearly_summaries.get(str(year), {})
        totals["sourceZipRows"] += int(summary.get("sourceZipRows") or 0)
        totals["zipEntryRows"] += int(summary.get("zipEntryRows") or 0)
        totals["documentEntryRows"] += int(summary.get("documentEntryRows") or 0)
        totals["uniqueZipEntrySha256"] += int(summary.get("uniqueZipEntrySha256") or 0)
        extension.update(counter_from_rows(summary.get("byFileExtension")))
        universities.update(counter_from_rows(summary.get("byUniversity")))
        inputs.extend(summary.get("inputs") or [])
    return {
        "provider": "university-admission-office",
        "artifactType": "university_admission_zip_entry_all_years_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "years": years,
        "inputs": inputs,
        "yearly": {
            year: {
                "sourceZipRows": summary.get("sourceZipRows", 0),
                "uniqueSourceZipSha256": summary.get("uniqueSourceZipSha256", 0),
                "zipEntryRows": summary.get("zipEntryRows", 0),
                "documentEntryRows": summary.get("documentEntryRows", 0),
                "uniqueZipEntrySha256": summary.get("uniqueZipEntrySha256", 0),
            }
            for year, summary in yearly_summaries.items()
        },
        "aggregate": dict(totals),
        "byFileExtension": counter_rows(extension, 30),
        "byUniversity": counter_rows(universities, 30),
        "notes": [
            "This summary covers ZIP entry artifact manifests for the requested admission years.",
            "Duplicate ZIP contents may appear in multiple admission-year contexts and are preserved as source-context rows.",
        ],
    }


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "provider",
        "artifactType",
        "year",
        "unvCd",
        "universityName",
        "sourceLinkRole",
        "attachmentRole",
        "parentAttachmentRole",
        "linkText",
        "fileExtension",
        "bytes",
        "rawPath",
        "sha256",
        "sourceZipRawPath",
        "sourceZipSha256",
        "zipEntryIndex",
        "zipEntryRawName",
        "zipEntryDecodedName",
        "sourceManifestPath",
        "sourceCandidateUrl",
        "finalUrl",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": key, "count": value} for key, value in counter.most_common(limit)]


def counter_from_rows(rows: Any) -> Counter[str]:
    counter: Counter[str] = Counter()
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, dict):
                counter[str(row.get("value") or "")] += int(row.get("count") or 0)
    return counter


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def int_or_none(value: Any) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
