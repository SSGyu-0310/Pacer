#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"
VALID_ADMISSION_YEAR_MIN = 2010
VALID_ADMISSION_YEAR_MAX = 2035

ROLE_RULES = [
    {
        "role": "admission_result_table",
        "patterns": [
            r"전형결과|입시결과|입학결과|최종등록|등록자|합격자|충원|후보",
            r"경쟁률|교과등급|등급|평균|컷|성적|지원인원|모집인원",
        ],
        "table_bonus": 14,
    },
    {
        "role": "competition_rate_table",
        "patterns": [r"경쟁률|지원율|\d+\s*:\s*1", r"모집인원|지원인원|지원자"],
        "table_bonus": 10,
    },
    {
        "role": "recruitment_quota_table",
        "patterns": [r"모집단위|모집\s*단위|모집인원", r"전형|정원내|정원외|가군|나군|다군"],
        "table_bonus": 8,
    },
    {
        "role": "screening_method",
        "patterns": [r"전형방법|전형요소|반영비율|일괄합산|단계별", r"학생부|면접|서류|실기|수능"],
        "table_bonus": 6,
    },
    {
        "role": "school_record_rule",
        "patterns": [r"학생부|학교생활기록부|교과성적|내신|반영교과|반영과목", r"석차등급|진로선택|성취도|출결"],
        "table_bonus": 6,
    },
    {
        "role": "csat_reflection_rule",
        "patterns": [r"수능|대학수학능력시험|수능최저", r"반영영역|반영비율|국어|수학|영어|탐구|등급"],
        "table_bonus": 6,
    },
    {
        "role": "eligibility_rule",
        "patterns": [r"지원자격|지원\s*자격|졸업|검정고시", r"농어촌|지역인재|기회균형|특성화고|차상위"],
        "table_bonus": 4,
    },
    {
        "role": "schedule_and_registration",
        "patterns": [r"원서접수|합격자\s*발표|충원합격|등록기간|추가합격|미등록"],
        "table_bonus": 4,
    },
    {
        "role": "schedule_and_registration",
        "patterns": [
            r"학부|신입생|모집",
            r"\d{4}\.\d{1,2}\.\d{1,2}\s*[~\-]\s*(?:\d{4}\.)?\d{1,2}\.\d{1,2}",
            r"접수|입시요강",
        ],
        "table_bonus": 4,
    },
]


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.in_table = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "table":
            self.in_table = True
        elif self.in_table and tag == "tr":
            self.current_row = []
        elif self.in_table and tag in {"td", "th"}:
            self.current_cell = []
        elif self.in_table and tag == "br" and self.current_cell is not None:
            self.current_cell.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self.current_cell is not None:
            cell = normalize_space("".join(self.current_cell))
            if self.current_row is not None:
                self.current_row.append(cell)
            self.current_cell = None
        elif tag == "tr" and self.current_row is not None:
            if any(cell for cell in self.current_row):
                self.rows.append(self.current_row)
            self.current_row = None
        elif tag == "table":
            self.in_table = False

    def handle_data(self, data: str) -> None:
        if self.in_table and self.current_cell is not None:
            self.current_cell.append(data)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest_paths = input_manifest_paths(repo_root, args)
    snippets: list[dict[str, Any]] = []
    source_rows: list[dict[str, Any]] = []
    for manifest_path in manifest_paths:
        for source in read_jsonl(manifest_path):
            if not is_html_source(source):
                continue
            if int_or_none(source.get("year")) != args.year:
                continue
            raw_path = resolve(repo_root, str(source.get("rawPath") or ""))
            if not raw_path.exists():
                continue
            source_rows.append(source)
            html_text = raw_path.read_text(encoding="utf-8", errors="replace")
            snippets.extend(extract_source_snippets(source, html_text, repo_root, args))

    snippets.sort(
        key=lambda row: (
            str(row.get("unvCd") or ""),
            str(row.get("snippetRole") or ""),
            -int(row.get("score") or 0),
            str(row.get("snippetSha256") or ""),
        )
    )

    write_jsonl(output_dir / f"university_admission_html_snippets_{args.year}.jsonl", snippets)
    write_csv_index(output_dir / f"university_admission_html_snippet_index_{args.year}.csv", snippets)
    summary = summarize(args.year, manifest_paths, source_rows, snippets)
    (output_dir / f"university_admission_html_snippets_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "university admission html snippet extraction complete. "
        f"sources={len(source_rows)} snippets={len(snippets)} roles={len(summary['bySnippetRole'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--manifest", action="append", default=[])
    parser.add_argument("--manifest-glob", action="append", default=[])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-tables-per-document", type=int, default=24)
    parser.add_argument("--max-text-snippets-per-document", type=int, default=12)
    parser.add_argument("--min-score", type=int, default=4)
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


def input_manifest_paths(repo_root: Path, args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = []
    for value in args.manifest:
        paths.append(resolve(repo_root, value))
    for pattern in args.manifest_glob:
        raw = Path(pattern)
        matches = sorted(glob.glob(str(raw if raw.is_absolute() else repo_root / raw)))
        paths.extend(Path(match) for match in matches)
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path.resolve())
        if key not in seen and path.exists():
            seen.add(key)
            deduped.append(path)
    return deduped


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def is_html_source(source: dict[str, Any]) -> bool:
    return (
        str(source.get("detectedKind") or "").lower() == "html"
        or "html" in str(source.get("contentType") or "").lower()
        or str(source.get("rawPath") or "").lower().endswith((".html", ".htm"))
    )


def int_or_none(value: Any) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def extract_source_snippets(
    source: dict[str, Any],
    html_text: str,
    repo_root: Path,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    title = extract_title(html_text)
    content_html = main_content_html(html_text)
    document_text = strip_html(content_html)
    years = detected_admission_years(document_text)
    snippets: list[dict[str, Any]] = []

    for table_index, table_html in enumerate(extract_table_html_blocks(content_html), start=1):
        rows = parse_table_rows(table_html)
        if not rows:
            continue
        table_text = table_rows_text(rows)
        role, score, matched = classify_role(f"{title}\n{table_text}", is_table=True)
        if score < args.min_score:
            continue
        snippets.append(
            build_snippet(
                source=source,
                repo_root=repo_root,
                snippet_type="html_table",
                role=role,
                score=score + min(20, len(rows) // 2),
                matched_keywords=matched,
                text=table_text,
                text_preview=table_text,
                title=title,
                years=years,
                source_specific={
                    "tableIndex": table_index,
                    "rows": len(rows),
                    "cols": max((len(row) for row in rows), default=0),
                },
            )
        )
        if len([row for row in snippets if row.get("snippetType") == "html_table"]) >= args.max_tables_per_document:
            break

    text_candidates = text_snippet_candidates(document_text)
    selected_text = 0
    for index, text in enumerate(text_candidates, start=1):
        role, score, matched = classify_role(f"{title}\n{text}", is_table=False)
        if score < args.min_score:
            continue
        snippets.append(
            build_snippet(
                source=source,
                repo_root=repo_root,
                snippet_type="html_text_snippet",
                role=role,
                score=score,
                matched_keywords=matched,
                text=text,
                text_preview=text,
                title=title,
                years=years,
                source_specific={"textSnippetIndex": index},
            )
        )
        selected_text += 1
        if selected_text >= args.max_text_snippets_per_document:
            break

    return snippets


def extract_table_html_blocks(html_text: str) -> list[str]:
    return [match.group(0) for match in re.finditer(r"<table\b[\s\S]*?</table>", html_text, re.I)]


def main_content_html(html_text: str) -> str:
    class_match = re.search(
        r"<div\b[^>]*class\s*=\s*(['\"])[^'\"]*(?:veiw_con|view_con)[^'\"]*\1[^>]*>",
        html_text,
        re.I,
    )
    if not class_match:
        return html_text

    start = class_match.start()
    depth = 0
    for match in re.finditer(r"</?div\b[^>]*>", html_text[start:], re.I):
        tag = match.group(0)
        if tag.startswith("</"):
            depth -= 1
            if depth <= 0:
                return html_text[start : start + match.end()]
        else:
            depth += 1
    return html_text[start:]


def parse_table_rows(table_html: str) -> list[list[str]]:
    parser = TableParser()
    parser.feed(table_html)
    return [[cell for cell in row] for row in parser.rows if any(normalize_space(cell) for cell in row)]


def table_rows_text(rows: list[list[str]]) -> str:
    lines = [" | ".join(normalize_space(cell) for cell in row if normalize_space(cell)) for row in rows]
    return "\n".join(line for line in lines if line)[:12000]


def text_snippet_candidates(document_text: str) -> list[str]:
    lines = [line for line in document_text.splitlines() if normalize_space(line)]
    candidates: list[str] = []
    for index, line in enumerate(lines):
        if re.search(
            r"\d{4}\.\d{1,2}\.\d{1,2}\s*[~\-]\s*(?:\d{4}\.)?\d{1,2}\.\d{1,2}",
            line,
        ):
            compact_window = "\n".join(lines[max(0, index - 1) : min(len(lines), index + 3)])
            if (
                re.search(r"학부|신입생|모집", compact_window)
                and re.search(r"접수|입시요강", compact_window)
            ):
                normalized = normalize_space(compact_window)
                if normalized and normalized not in candidates:
                    candidates.append(compact_window[:2000])
        window = "\n".join(lines[max(0, index - 3) : min(len(lines), index + 12)])
        if any(re.search(pattern, window) for rule in ROLE_RULES for pattern in rule["patterns"]):
            normalized = normalize_space(window)
            if normalized and normalized not in candidates:
                candidates.append(window[:5000])
    return candidates


def classify_role(text: str, *, is_table: bool) -> tuple[str, int, list[str]]:
    scored: list[tuple[int, str, list[str]]] = []
    for rule in ROLE_RULES:
        matched: list[str] = []
        score = 0
        for pattern in rule["patterns"]:
            if re.search(pattern, text, re.I):
                matched.append(pattern)
                score += 4
        if len(matched) < len(rule["patterns"]):
            continue
        score += min(12, len(re.findall(r"\d+(?:\.\d+)?", text)) // 8)
        if is_table:
            score += int(rule.get("table_bonus") or 0)
        if matched:
            scored.append((score, str(rule["role"]), matched))
    if not scored:
        return ("unknown", 0, [])
    score, role, matched = sorted(scored, key=lambda item: (-item[0], item[1]))[0]
    return role, score, sorted(set(matched))


def build_snippet(
    *,
    source: dict[str, Any],
    repo_root: Path,
    snippet_type: str,
    role: str,
    score: int,
    matched_keywords: list[str],
    text: str,
    text_preview: str,
    title: str,
    years: list[int],
    source_specific: dict[str, Any],
) -> dict[str, Any]:
    raw_path = str(source.get("rawPath") or "")
    raw_abs = resolve(repo_root, raw_path) if raw_path else Path()
    raw_sha = str(source.get("sha256") or "")
    if not raw_sha and raw_abs.exists():
        raw_sha = sha256_file(raw_abs)
    snippet_sha = hashlib.sha256(
        "|".join([raw_sha, snippet_type, role, text[:12000]]).encode("utf-8")
    ).hexdigest()
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_html_snippet",
        "year": source.get("year"),
        "unvCd": source.get("unvCd"),
        "universityName": source.get("universityName"),
        "campus": source.get("campus"),
        "sourceLinkRole": source.get("sourceLinkRole"),
        "attachmentRole": source.get("attachmentRole"),
        "detectedDocumentRole": role,
        "documentDetectedAdmissionYears": years,
        "snippetType": snippet_type,
        "snippetRole": role,
        "score": score,
        "matchedKeywords": matched_keywords,
        "sourceCandidateUrl": (
            source.get("sourceCandidateUrl")
            or source.get("sourceHomepageUrl")
            or source.get("finalHomepageUrl")
        ),
        "attachmentUrl": source.get("attachmentUrl") or source.get("finalUrl"),
        "finalUrl": source.get("finalUrl") or source.get("finalHomepageUrl"),
        "rawHtmlPath": raw_path,
        "rawHtmlSha256": raw_sha,
        "sourceRowKey": source_row_key(source),
        "snippetSha256": snippet_sha,
        "title": title,
        "textPreview": normalize_space(text_preview)[:300],
        "text": text[:8000],
        "sourceSpecific": source_specific,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "status": "candidate",
    }


def extract_title(html_text: str) -> str:
    for pattern in [r"<h1\b[^>]*>([\s\S]*?)</h1>", r"<h2\b[^>]*>([\s\S]*?)</h2>", r"<title\b[^>]*>([\s\S]*?)</title>"]:
        match = re.search(pattern, html_text, re.I)
        if match:
            return normalize_space(strip_html(match.group(1)))
    return ""


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script\b.*?</script>", " ", value)
    value = re.sub(r"(?is)<style\b.*?</style>", " ", value)
    value = re.sub(r"(?is)<!--.*?-->", " ", value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</(?:p|div|li|tr|table|h[1-6])>", "\n", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    return "\n".join(normalize_space(line) for line in value.splitlines() if normalize_space(line))


def detected_admission_years(value: str) -> list[int]:
    years: set[int] = set()
    for match in re.findall(r"(?<!\d)(20[0-3]\d)\s*학\s*년\s*도", value):
        year = int(match)
        if VALID_ADMISSION_YEAR_MIN <= year <= VALID_ADMISSION_YEAR_MAX:
            years.add(year)
    return sorted(years)


def source_row_key(source: dict[str, Any]) -> str:
    payload = {
        "unvCd": source.get("unvCd"),
        "rawPath": source.get("rawPath"),
        "sha256": source.get("sha256"),
        "attachmentUrl": source.get("attachmentUrl"),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + ("\n" if rows else ""),
        encoding="utf-8",
    )


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "snippetType",
        "snippetRole",
        "score",
        "documentDetectedAdmissionYears",
        "sourceLinkRole",
        "attachmentRole",
        "rawHtmlPath",
        "attachmentUrl",
        "snippetSha256",
        "textPreview",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **{header: row.get(header, "") for header in headers},
                    "documentDetectedAdmissionYears": "|".join(str(v) for v in row.get("documentDetectedAdmissionYears") or []),
                }
            )


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


def summarize(
    year: int,
    manifest_paths: list[Path],
    sources: list[dict[str, Any]],
    snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_html_snippet_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "inputManifests": [str(path) for path in manifest_paths],
        "htmlSources": len(sources),
        "snippets": len(snippets),
        "bySnippetType": counter_rows(Counter(str(row.get("snippetType") or "") for row in snippets)),
        "bySnippetRole": counter_rows(Counter(str(row.get("snippetRole") or "") for row in snippets)),
        "topUniversities": counter_rows(Counter(str(row.get("universityName") or "") for row in snippets)),
        "notes": [
            "HTML snippets preserve official admission-office detail pages whose result tables are embedded in the page body rather than downloadable files.",
            "Rows remain review candidates until manually verified or promoted by a downstream parser.",
        ],
    }


def counter_rows(counter: Counter[str], limit: int = 40) -> list[dict[str, Any]]:
    return [
        {"value": value, "count": count}
        for value, count in counter.most_common(limit)
    ]


if __name__ == "__main__":
    main()
