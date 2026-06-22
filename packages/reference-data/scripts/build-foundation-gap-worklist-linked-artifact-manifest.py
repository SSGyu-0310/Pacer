#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


DEFAULT_WORKLIST = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_crawler_worklist.csv"
)
DEFAULT_SITE_DIR = "packages/reference-data/data/public/university-admission-sites"
DEFAULT_OUTPUT_SUFFIX = "gap_worklist_linked_unpromoted_20260613"

TARGET_YEARS = set(range(2021, 2028))
FILE_EXTENSIONS = {"pdf", "hwp", "hwpx", "xls", "xlsx", "doc", "docx", "ppt", "pptx", "zip"}
HTML_EXTENSIONS = {"html", "htm"}
ADMISSION_YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})\s*학\s*년\s*도")
GENERIC_ARTIFACT_YEAR_PATTERN = re.compile(r"(?<!\d)(20\d{2})(?!\d|\.\d)")
HIGH_SIGNAL_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전형\s*결과|전년도|모집\s*요강|입학\s*전형|전형\s*계획|"
    r"시행\s*계획|정시|수시|수능|학생부|모집\s*인원|경쟁률|충원|최종\s*등록|"
    r"등록자|합격자|성적|등급|백분위|환산|cut|컷|원서\s*접수|합격자\s*발표",
    re.I,
)
OUT_OF_SCOPE_PATTERN = re.compile(
    r"재외국민|순수\s*외국인|외국인\s*특별전형|외국인|전\s*교육과정\s*이수자|"
    r"북한이탈주민|편입학|편입|대학원|시간제|평생교육|계약학과|산업체|"
    r"선행학습|영향평가|고교연계|체험|설명회|상담|입학식|학위수여|졸업|학위청구|"
    r"생활관|기숙사|장학|등록금|교통|오시는\s*길|캠퍼스|교직원|채용|대학\s*요람|"
    r"교육\s*만족도|자체평가|기관평가|평가인증|등록포기|전형료\s*환불|"
    r"입학원서|제출서류\s*양식|홈페이지\s*준비중|Q\s*&?\s*A|FAQ|묻고\s*답하기|"
    r"Ç¨ÆäÀÌÁö|ÁØºñÁß|copyright|저작권|공공누리|kogl|합격자\s*조회|"
    r"yoram|edu[_-]?level|survey|transfer|foreigner|graduate|gradresult|dorm|tuition|campus|employment",
    re.I,
)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    site_dir = resolve(repo_root, args.site_dir)
    worklist_rows = read_csv(resolve(repo_root, args.worklist))
    raw_index = load_raw_index(site_dir)
    promoted_raw_paths = load_promoted_raw_paths(site_dir)

    rows, skipped = build_rows(
        repo_root=repo_root,
        worklist_rows=worklist_rows,
        raw_index=raw_index,
        promoted_raw_paths=promoted_raw_paths,
        include_promoted=args.include_promoted,
        include_html=args.include_html,
        include_files=args.include_files,
    )
    rows = dedupe_rows(rows)
    rows.sort(
        key=lambda row: (
            int(row.get("year") or 0),
            str(row.get("unvCd") or ""),
            str(row.get("fileExtension") or ""),
            str(row.get("rawPath") or ""),
        )
    )

    suffix = sanitize_suffix(args.output_suffix)
    output_path = site_dir / f"university_admission_attachment_artifact_manifest_{suffix}.jsonl"
    summary_path = site_dir / f"university_admission_gap_worklist_linked_artifact_manifest_summary_{suffix}.json"
    write_jsonl(output_path, rows)
    write_json(
        summary_path,
        {
            "provider": "university-admission-office",
            "artifactType": "university_admission_gap_worklist_linked_artifact_manifest_summary",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "inputWorklist": to_repo_relative(resolve(repo_root, args.worklist), repo_root),
            "output": {
                "path": to_repo_relative(output_path, repo_root),
                "rows": len(rows),
            },
            "parameters": {
                "includePromoted": args.include_promoted,
                "includeHtml": args.include_html,
                "includeFiles": args.include_files,
            },
            "skipped": dict(sorted(skipped.items())),
            "byYear": counter_rows(Counter(str(row.get("year")) for row in rows)),
            "byFileExtension": counter_rows(Counter(str(row.get("fileExtension")) for row in rows)),
            "byDetectedKind": counter_rows(Counter(str(row.get("detectedKind")) for row in rows)),
            "bySourceLinkRole": counter_rows(Counter(str(row.get("sourceLinkRole")) for row in rows)),
            "topUniversities": counter_rows(Counter(str(row.get("universityName")) for row in rows), 30),
            "notes": [
                "Rows are copied from existing fetched admission-office manifests referenced by the current gap crawler worklist.",
                "Already promoted raw paths are excluded by default to focus extraction on local artifacts that never reached the promotion review queue.",
                "Explicit out-of-scope admissions-adjacent documents are excluded before extraction.",
            ],
        },
    )
    print(
        "foundation gap worklist linked artifact manifest complete. "
        f"worklistRows={len(worklist_rows)} rows={len(rows)} "
        f"output={to_repo_relative(output_path, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worklist", default=DEFAULT_WORKLIST)
    parser.add_argument("--site-dir", default=DEFAULT_SITE_DIR)
    parser.add_argument("--output-suffix", default=DEFAULT_OUTPUT_SUFFIX)
    parser.add_argument("--include-promoted", action="store_true")
    parser.add_argument("--no-html", dest="include_html", action="store_false")
    parser.add_argument("--no-files", dest="include_files", action="store_false")
    parser.set_defaults(include_html=True, include_files=True)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def build_rows(
    *,
    repo_root: Path,
    worklist_rows: list[dict[str, str]],
    raw_index: dict[str, dict[str, Any]],
    promoted_raw_paths: set[str],
    include_promoted: bool,
    include_html: bool,
    include_files: bool,
) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for worklist in worklist_rows:
        worklist_years = target_years_for_worklist(worklist)
        for raw_path in split_pipe(worklist.get("sampleLinkedRawPaths")):
            source = raw_index.get(raw_path)
            if not source:
                skipped["missing_manifest_source"] += 1
                continue
            if not (repo_root / raw_path).exists():
                skipped["missing_raw_path"] += 1
                continue
            if not include_promoted and raw_path in promoted_raw_paths:
                skipped["already_promoted_raw_path"] += 1
                continue
            http_status = int_or_none(source.get("httpStatus"))
            if http_status is not None and http_status >= 400:
                skipped["http_error"] += 1
                continue

            extension = file_extension(source, raw_path)
            if extension in HTML_EXTENSIONS:
                if not include_html:
                    skipped["html_disabled"] += 1
                    continue
                detected_kind = "html"
            elif extension in FILE_EXTENSIONS:
                if not include_files:
                    skipped["files_disabled"] += 1
                    continue
                if not raw_file_matches_extension(repo_root / raw_path, extension):
                    skipped["file_payload_mismatch"] += 1
                    continue
                detected_kind = "file"
            else:
                skipped["unsupported_extension"] += 1
                continue

            metadata_text = metadata_haystack(source, worklist)
            if OUT_OF_SCOPE_PATTERN.search(metadata_text):
                skipped["out_of_scope_metadata"] += 1
                continue
            if not is_high_signal(source, worklist, raw_path):
                skipped["low_signal_metadata"] += 1
                continue

            detected_years = [
                year for year in detected_admission_years_from_text(metadata_text) if year in TARGET_YEARS
            ]
            output_years = detected_years or worklist_years
            if not output_years:
                skipped["no_target_year"] += 1
                continue
            if detected_years and worklist_years and not (set(detected_years) & set(worklist_years)):
                skipped["detected_year_worklist_year_mismatch"] += 1
                continue

            for year in output_years:
                rows.append(make_output_row(source, worklist, raw_path, extension, detected_kind, year))
    return rows, skipped


def make_output_row(
    source: dict[str, Any],
    worklist: dict[str, str],
    raw_path: str,
    extension: str,
    detected_kind: str,
    year: int,
) -> dict[str, Any]:
    output = dict(source)
    output.update(
        {
            "provider": "university-admission-office",
            "artifactType": "admission_attachment_artifact",
            "year": year,
            "rawPath": raw_path,
            "fileExtension": extension,
            "detectedKind": detected_kind,
            "status": "fetched",
            "httpStatus": int_or_none(source.get("httpStatus")) or 200,
            "sourceLinkRole": normalize_text(source.get("sourceLinkRole"))
            or normalize_text(worklist.get("sourceRole"))
            or "admission_related",
            "attachmentRole": normalize_text(source.get("attachmentRole")) or "worklist_linked_artifact",
            "sourceCandidateUrl": first_nonempty(
                source.get("sourceCandidateUrl"),
                source.get("sourceHomepageUrl"),
                source.get("finalHomepageUrl"),
                source.get("finalUrl"),
                first_pipe(worklist.get("sampleSourceUrls")),
            ),
            "attachmentUrl": first_nonempty(source.get("attachmentUrl"), source.get("finalUrl")),
            "finalUrl": first_nonempty(source.get("finalUrl"), source.get("attachmentUrl")),
            "gapWorklistId": normalize_text(worklist.get("crawlerWorklistId")),
            "pipelineStage": normalize_text(worklist.get("pipelineStage")),
            "crawlerPattern": normalize_text(worklist.get("crawlerPattern")),
            "targetEntities": normalize_text(worklist.get("targetEntities")),
            "missingFlags": normalize_text(worklist.get("missingFlags")),
            "worklistAdmissionYears": normalize_text(worklist.get("admissionYears")),
            "linkedArtifactManifestSource": normalize_text(source.get("_manifestPath")),
        }
    )
    return output


def load_raw_index(site_dir: Path) -> dict[str, dict[str, Any]]:
    raw_index: dict[str, dict[str, Any]] = {}
    for pattern in [
        "university_admission_homepage_manifest_*.jsonl",
        "university_admission_link_artifact_manifest_*.jsonl",
        "university_admission_attachment_artifact_manifest_*.jsonl",
    ]:
        for path in sorted(site_dir.glob(pattern)):
            for row in read_jsonl(path):
                raw_path = normalize_text(row.get("rawPath"))
                if raw_path and raw_path not in raw_index:
                    enriched = dict(row)
                    enriched["_manifestPath"] = str(path)
                    raw_index[raw_path] = enriched
    return raw_index


def load_promoted_raw_paths(site_dir: Path) -> set[str]:
    paths: set[str] = set()
    for path in site_dir.glob("**/university_admission_promotion_review_candidates.jsonl"):
        for row in read_jsonl(path):
            for raw_path in row.get("rawPaths") or []:
                if raw_path:
                    paths.add(str(raw_path))
    return paths


def is_high_signal(source: dict[str, Any], worklist: dict[str, str], raw_path: str) -> bool:
    extension = file_extension(source, raw_path)
    text = source_haystack(source)
    if extension in FILE_EXTENSIONS and detected_admission_years_from_text(text):
        return True
    return bool(HIGH_SIGNAL_PATTERN.search(text))


def metadata_haystack(source: dict[str, Any], worklist: dict[str, str]) -> str:
    return decode_percent(
        " ".join(
            [
                source_haystack(source),
                normalize_text(worklist.get("sourceRole")),
                normalize_text(worklist.get("sampleSourceUrls")),
            ]
        )
    )


def source_haystack(source: dict[str, Any]) -> str:
    values = [
        source.get("sourceLinkRole"),
        source.get("linkText"),
        source.get("sourceCandidateUrl"),
        source.get("attachmentUrl"),
        source.get("finalUrl"),
        source.get("suggestedFilename"),
        source.get("contentDisposition"),
    ]
    return decode_percent(" ".join(normalize_text(value) for value in values))


def detected_admission_years_from_text(text: str) -> list[int]:
    years = {int(match.group(1)) for match in ADMISSION_YEAR_PATTERN.finditer(text)}
    years.update(int(match.group(1)) for match in GENERIC_ARTIFACT_YEAR_PATTERN.finditer(text))
    return sorted(year for year in years if year in TARGET_YEARS)


def target_years_for_worklist(worklist: dict[str, str]) -> list[int]:
    years = []
    for value in split_pipe(worklist.get("admissionYears")):
        try:
            year = int(value)
        except ValueError:
            continue
        if year in TARGET_YEARS:
            years.append(year)
    return sorted(set(years))


def file_extension(source: dict[str, Any], raw_path: str) -> str:
    value = normalize_text(source.get("fileExtension")).lower().lstrip(".")
    if value:
        return value
    return Path(raw_path.split("?", 1)[0]).suffix.lower().lstrip(".")


def raw_file_matches_extension(path: Path, extension: str) -> bool:
    try:
        sample = path.read_bytes()[:1024]
    except OSError:
        return False
    stripped = sample.lstrip().lower()
    if stripped.startswith((b"<!doctype html", b"<html", b"<?xml")) or b"<body" in stripped[:256]:
        return False
    if extension == "pdf":
        return sample.startswith(b"%PDF")
    return True


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("year"),
            row.get("unvCd"),
            canonical_url(row.get("attachmentUrl") or row.get("finalUrl") or row.get("rawPath")),
            row.get("rawPath"),
        )
        deduped.setdefault(key, row)
    return list(deduped.values())


def canonical_url(value: Any) -> str:
    text = normalize_text(value)
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
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(query, doseq=True), ""))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


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
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False, sort_keys=True) for row in rows)
        + ("\n" if rows else ""),
        encoding="utf-8",
    )


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit) if value]


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u001f\u007f-\u009f]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


def split_pipe(value: Any) -> list[str]:
    return [part.strip() for part in str(value or "").split("|") if part.strip()]


def first_pipe(value: Any) -> str:
    parts = split_pipe(value)
    return parts[0] if parts else ""


def first_nonempty(*values: Any) -> str:
    for value in values:
        text = normalize_text(value)
        if text:
            return text
    return ""


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def decode_percent(value: str) -> str:
    try:
        return unquote(value)
    except Exception:
        return value


def int_or_none(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


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
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def sanitize_suffix(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip()).strip("_") or DEFAULT_OUTPUT_SUFFIX


if __name__ == "__main__":
    main()
