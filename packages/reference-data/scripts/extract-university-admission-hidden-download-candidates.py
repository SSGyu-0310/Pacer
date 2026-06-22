#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import html as html_lib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites"
DEFAULT_DOWNLOAD_URL_TEMPLATE = "/common/download.do?file_no={id}"

HEADERS = [
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

DOWNLOAD_HREF_PATTERN = re.compile(
    r"""^\s*javascript:\s*(?:download|fileDown|file_download)\s*\(\s*['"]?(?P<id>\d+)['"]?""",
    re.IGNORECASE,
)
ASPNET_FILE_BLOCK_PATTERN = re.compile(
    r"""<a\b(?P<a_attrs>[^>]*?)>(?P<link_text>[\s\S]*?)</a>\s*
        (?P<inputs>(?:\s*<input\b[^>]*?(?:hdnFileNo|hdnFilePath|hdnFileName)[^>]*?/?>)+)""",
    re.IGNORECASE | re.VERBOSE,
)
INPUT_ATTR_PATTERN = re.compile(r"""(?P<name>[A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*["'](?P<value>[^"']*)["']""")

KEYWORD_PATTERNS = [
    ("입시결과", re.compile(r"입시결과|입학결과|전형결과|최종등록|등록자|충원|예비")),
    ("경쟁률", re.compile(r"경쟁률|지원현황|지원 현황|지원율")),
    ("모집요강", re.compile(r"모집요강|모집 요강|신입생 모집")),
    ("시행계획", re.compile(r"시행계획|시행 계획|전형계획|전형 계획")),
    ("정시", re.compile(r"정시|수능|대학수학능력시험")),
    ("수시", re.compile(r"수시|학생부|면접|실기")),
    ("선행학습", re.compile(r"선행학습|영향평가")),
]


class AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, str]] = []
        self.current_anchor: dict[str, str] | None = None
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr_map = {key.lower(): value or "" for key, value in attrs}
        self.current_anchor = {
            "href": attr_map.get("href", ""),
            "onclick": attr_map.get("onclick", ""),
        }
        self.text_parts = []

    def handle_data(self, data: str) -> None:
        if self.current_anchor is not None:
            self.text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self.current_anchor is None:
            return
        self.current_anchor["text"] = normalize_space("".join(self.text_parts))
        self.anchors.append(self.current_anchor)
        self.current_anchor = None
        self.text_parts = []


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_paths = resolve_manifest_paths(repo_root, args)
    rows: list[dict[str, str]] = []
    input_rows = 0
    missing_raw_paths = 0

    for manifest_path in manifest_paths:
        for source in load_jsonl(manifest_path):
            input_rows += 1
            if int(source.get("year") or 0) != args.year:
                continue
            if str(source.get("status") or "") != "fetched":
                continue
            raw_path = resolve(repo_root, str(source.get("rawPath") or ""))
            if not raw_path.exists():
                missing_raw_paths += 1
                continue
            html = raw_path.read_text(encoding="utf-8", errors="replace")
            rows.extend(extract_rows(source, html, args, repo_root))

    deduped_rows = dedupe_rows(rows)
    output_suffix = sanitize_output_suffix(args.output_suffix)
    output_suffix_segment = f"_{output_suffix}" if output_suffix else ""
    output_csv = output_dir / (
        f"university_admission_attachment_candidates_{args.year}{output_suffix_segment}.csv"
    )
    write_csv(output_csv, deduped_rows)

    summary = summarize(args, manifest_paths, input_rows, missing_raw_paths, rows, deduped_rows, repo_root)
    output_summary = output_dir / (
        f"university_admission_hidden_download_candidates_summary_{args.year}"
        f"{output_suffix_segment}.json"
    )
    output_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "university admission hidden download candidate extraction complete. "
        f"sources={input_rows} candidates={len(deduped_rows)} "
        f"universities={summary['universitiesRepresented']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--manifest", action="append", default=[])
    parser.add_argument("--manifest-glob", action="append", default=[])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-suffix", default="hidden_download")
    parser.add_argument("--download-url-template", default=DEFAULT_DOWNLOAD_URL_TEMPLATE)
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


def resolve_manifest_paths(repo_root: Path, args: argparse.Namespace) -> list[Path]:
    paths = [resolve(repo_root, value) for value in args.manifest]
    for pattern in args.manifest_glob:
        pattern_path = Path(pattern)
        if pattern_path.is_absolute():
            paths.extend(Path(match) for match in glob.glob(str(pattern_path)))
        else:
            paths.extend(repo_root.glob(pattern))
    unique_paths = sorted({path.resolve() for path in paths})
    return [path for path in unique_paths if path.exists()]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def extract_rows(
    source: dict[str, Any],
    html: str,
    args: argparse.Namespace,
    repo_root: Path,
) -> list[dict[str, str]]:
    parser = AnchorParser()
    parser.feed(html)

    rows: list[dict[str, str]] = []
    base_url = str(source.get("finalUrl") or source.get("sourceCandidateUrl") or "")
    for anchor in parser.anchors:
        href_raw = anchor.get("href", "")
        onclick = anchor.get("onclick", "")
        download_id = download_id_for(href_raw) or download_id_for(onclick)
        if not download_id:
            continue
        resolved_url = urljoin(base_url, args.download_url_template.format(id=download_id))
        link_text = normalize_space(anchor.get("text") or "")
        source_text = normalize_space(str(source.get("sourceLinkText") or ""))
        row = {
            "provider": "university-admission-office",
            "artifactType": "admission_attachment_link_candidate",
            "year": str(args.year),
            "unvCd": str(source.get("unvCd") or ""),
            "universityName": str(source.get("universityName") or ""),
            "campus": str(source.get("campus") or ""),
            "sourceLinkRole": str(source.get("sourceLinkRole") or ""),
            "sourceLinkText": source_text,
            "sourceCandidateUrl": str(source.get("sourceCandidateUrl") or source.get("finalUrl") or ""),
            "detailRawPath": to_repo_relative(resolve(repo_root, str(source.get("rawPath") or "")), repo_root),
            "attachmentRole": "direct_file",
            "linkText": link_text,
            "hrefRaw": href_raw or onclick,
            "resolvedUrl": resolved_url,
            "hostname": hostname_for(resolved_url),
            "fileExtension": file_extension_for_filename(link_text),
            "keywordHits": "|".join(keyword_hits(f"{source_text} {link_text}")),
        }
        rows.append(row)
    rows.extend(extract_aspnet_hidden_file_rows(source, html, base_url, repo_root))
    return rows


def extract_aspnet_hidden_file_rows(
    source: dict[str, Any],
    html: str,
    base_url: str,
    repo_root: Path,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    source_text = normalize_space(str(source.get("sourceLinkText") or ""))
    for match in ASPNET_FILE_BLOCK_PATTERN.finditer(html):
        input_attrs = hidden_input_values(match.group("inputs"))
        file_path = input_attrs.get("hdnfilepath", "")
        if not file_path:
            continue
        link_text = normalize_space(strip_tags(html_lib.unescape(match.group("link_text"))))
        file_name = input_attrs.get("hdnfilename", "") or link_text
        resolved_url = urljoin(base_url, file_path)
        href_raw = anchor_href(match.group("a_attrs")) or file_path
        rows.append(
            {
                "provider": "university-admission-office",
                "artifactType": "admission_attachment_link_candidate",
                "year": str(source.get("year") or ""),
                "unvCd": str(source.get("unvCd") or ""),
                "universityName": str(source.get("universityName") or ""),
                "campus": str(source.get("campus") or ""),
                "sourceLinkRole": str(source.get("sourceLinkRole") or ""),
                "sourceLinkText": source_text,
                "sourceCandidateUrl": str(source.get("sourceCandidateUrl") or source.get("finalUrl") or ""),
                "detailRawPath": to_repo_relative(
                    resolve(repo_root, str(source.get("rawPath") or "")),
                    repo_root,
                ),
                "attachmentRole": "direct_file",
                "linkText": link_text or file_name,
                "hrefRaw": href_raw,
                "resolvedUrl": resolved_url,
                "hostname": hostname_for(resolved_url),
                "fileExtension": file_extension_for_filename(file_name or resolved_url),
                "keywordHits": "|".join(keyword_hits(f"{source_text} {link_text} {file_name}")),
            }
        )
    return rows


def hidden_input_values(inputs_html: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for input_match in re.finditer(r"<input\b[^>]*>", inputs_html, re.IGNORECASE):
        attrs = {
            name.lower(): html_lib.unescape(value)
            for name, value in INPUT_ATTR_PATTERN.findall(input_match.group(0))
        }
        input_name = attrs.get("name", "").lower()
        input_id = attrs.get("id", "").lower()
        for key in ["hdnfileno", "hdnfilepath", "hdnfilename"]:
            if key in input_name or key in input_id:
                values[key] = attrs.get("value", "")
    return values


def anchor_href(attrs_html: str) -> str:
    attrs = {
        name.lower(): html_lib.unescape(value)
        for name, value in INPUT_ATTR_PATTERN.findall(attrs_html)
    }
    return attrs.get("href", "")


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", value)


def download_id_for(value: str) -> str:
    match = DOWNLOAD_HREF_PATTERN.search(value or "")
    return match.group("id") if match else ""


def dedupe_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (
            row["year"],
            row["unvCd"],
            row["sourceCandidateUrl"],
            row["resolvedUrl"],
            row["linkText"],
        )
        by_key.setdefault(key, row)
    return sorted(
        by_key.values(),
        key=lambda row: (
            row["year"],
            row["unvCd"],
            row["sourceLinkRole"],
            row["sourceCandidateUrl"],
            row["resolvedUrl"],
        ),
    )


def keyword_hits(text: str) -> list[str]:
    return [label for label, pattern in KEYWORD_PATTERNS if pattern.search(text)]


def file_extension_for_filename(filename: str) -> str:
    match = re.search(r"\.([A-Za-z0-9]+)(?:$|[?#])", filename)
    return match.group(1).lower() if match else ""


def hostname_for(url: str) -> str:
    return urlparse(url).hostname or ""


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def sanitize_output_suffix(value: str) -> str:
    return re.sub(r"[^a-z0-9_-]+", "_", value.strip().lower()).strip("_")


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize(
    args: argparse.Namespace,
    manifest_paths: list[Path],
    input_rows: int,
    missing_raw_paths: int,
    raw_rows: list[dict[str, str]],
    deduped_rows: list[dict[str, str]],
    repo_root: Path,
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_hidden_download_candidate_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": args.year,
        "downloadUrlTemplate": args.download_url_template,
        "inputManifests": [to_repo_relative(path, repo_root) for path in manifest_paths],
        "sourceManifestRows": input_rows,
        "missingRawPaths": missing_raw_paths,
        "rawCandidates": len(raw_rows),
        "dedupedCandidates": len(deduped_rows),
        "universitiesRepresented": len({row["unvCd"] for row in deduped_rows if row["unvCd"]}),
        "bySourceLinkRole": counter_rows(Counter(row["sourceLinkRole"] for row in deduped_rows)),
        "byFileExtension": counter_rows(Counter(row["fileExtension"] for row in deduped_rows)),
        "topUniversities": counter_rows(Counter(row["universityName"] for row in deduped_rows), 30),
        "notes": [
            "Rows convert numeric JavaScript download handlers into source-preserving direct_file attachment candidates.",
            "resolvedUrl points to the board download endpoint; detailRawPath keeps the source HTML that exposed the file id and filename.",
            "Fetched files still require document extraction and human verification before production promotion.",
        ],
    }


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": key, "count": value} for key, value in counter.most_common(limit)]


if __name__ == "__main__":
    main()
