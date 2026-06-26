#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_HWP_SOURCE_MANIFEST = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_hwp_sources_manifest_2027.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    source_manifest_path = resolve(repo_root, args.hwp_source_manifest)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_snippet_module = load_pdf_snippet_module()
    source_rows = load_jsonl(source_manifest_path)
    snippets: list[dict[str, Any]] = []

    for source in source_rows:
        if source.get("extractionStatus") not in {"extracted", "reused_duplicate_sha256"}:
            continue
        text_path_raw = str(source.get("textPath") or "")
        if not text_path_raw:
            continue
        text_path = repo_root / text_path_raw
        if not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")
        snippets.extend(extract_source_snippets(source, text, args, pdf_snippet_module))

    write_jsonl(
        output_dir / f"university_admission_hwp_snippets_{args.year}.jsonl",
        snippets,
    )
    write_csv_index(
        output_dir / f"university_admission_hwp_snippet_index_{args.year}.csv",
        snippets,
    )
    summary = summarize(args.year, source_rows, snippets)
    (output_dir / f"university_admission_hwp_snippets_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "university admission hwp snippet extraction complete. "
        f"sources={summary['eligibleSources']} snippets={summary['snippets']} "
        f"roles={len(summary['bySnippetRole'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--hwp-source-manifest", default=DEFAULT_HWP_SOURCE_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-snippets-per-document", type=int, default=24)
    parser.add_argument("--max-snippets-per-role", type=int, default=6)
    parser.add_argument("--before-lines", type=int, default=4)
    parser.add_argument("--after-lines", type=int, default=10)
    parser.add_argument("--min-score", type=int, default=3)
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


def load_pdf_snippet_module() -> Any:
    module_path = Path(__file__).with_name("extract-university-admission-pdf-snippets.py")
    spec = importlib.util.spec_from_file_location("university_admission_pdf_snippets", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load PDF snippet helper module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def extract_source_snippets(
    source: dict[str, Any],
    text: str,
    args: argparse.Namespace,
    pdf_snippet_module: Any,
) -> list[dict[str, Any]]:
    lines = hwp_review_lines(text)
    if not any(normalize_space(line) for line in lines):
        return []

    document_detected_admission_years = (
        pdf_snippet_module.detected_admission_years_from_document(text)
    )
    candidates: list[dict[str, Any]] = []
    for rule in pdf_snippet_module.SNIPPET_RULES:
        windows = pdf_snippet_module.candidate_windows_for_rule(lines, rule, args)
        for start_line, end_line, matched_keywords, score in windows:
            snippet_lines = lines[start_line : end_line + 1]
            snippet_text = "\n".join(rstrip_control(line) for line in snippet_lines).strip()
            if not snippet_text:
                continue
            candidates.append(
                build_snippet(
                    source=source,
                    rule=rule,
                    start_line=start_line + 1,
                    end_line=end_line + 1,
                    matched_keywords=matched_keywords,
                    score=score,
                    snippet_text=snippet_text,
                    document_detected_admission_years=document_detected_admission_years,
                )
            )

    return pdf_snippet_module.select_top_snippets(
        candidates,
        max_per_document=args.max_snippets_per_document,
        max_per_role=args.max_snippets_per_role,
    )


def build_snippet(
    *,
    source: dict[str, Any],
    rule: dict[str, Any],
    start_line: int,
    end_line: int,
    matched_keywords: list[str],
    score: int,
    snippet_text: str,
    document_detected_admission_years: list[int],
) -> dict[str, Any]:
    snippet_sha = hashlib.sha256(
        "|".join(
            [
                str(source.get("rawHwpSha256") or ""),
                rule["role"],
                str(start_line),
                str(end_line),
                snippet_text,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_hwp_text_snippet",
        "year": source.get("year"),
        "unvCd": source.get("unvCd"),
        "universityName": source.get("universityName"),
        "campus": source.get("campus"),
        "sourceLinkRole": source.get("sourceLinkRole"),
        "attachmentRole": source.get("attachmentRole"),
        "detectedDocumentRole": source.get("detectedDocumentRole"),
        "documentDetectedAdmissionYears": document_detected_admission_years,
        "documentTitleAdmissionYears": source.get("documentTitleAdmissionYears") or [],
        "documentPrimaryAdmissionYear": source.get("documentPrimaryAdmissionYear"),
        "documentYearStatus": source.get("documentYearStatus"),
        "promotionSafeSourceYear": source.get("promotionSafeSourceYear"),
        "snippetRole": rule["role"],
        "score": score,
        "pageNumber": 1,
        "startLine": start_line,
        "endLine": end_line,
        "matchedKeywords": matched_keywords,
        "sourceCandidateUrl": source.get("sourceCandidateUrl"),
        "attachmentUrl": source.get("attachmentUrl"),
        "rawHwpPath": source.get("rawHwpPath"),
        "rawHwpSha256": source.get("rawHwpSha256"),
        "textPath": source.get("textPath"),
        "sourceRowKey": source_row_key(source),
        "snippetSha256": snippet_sha,
        "textPreview": normalize_space(snippet_text)[:300],
        "text": snippet_text[:4000],
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "status": "candidate" if source.get("promotionSafeSourceYear") is not False else "source_year_mismatch",
    }


def source_row_key(source: dict[str, Any]) -> str:
    return hashlib.sha256(
        "|".join(
            [
                str(source.get("rawHwpSha256") or ""),
                str(source.get("unvCd") or ""),
                str(source.get("attachmentUrl") or ""),
                str(source.get("sourceCandidateUrl") or ""),
            ]
        ).encode("utf-8")
    ).hexdigest()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def hwp_review_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        normalized = normalize_space(raw_line)
        if not normalized:
            continue
        if len(normalized) <= 260:
            lines.append(normalized)
            continue
        lines.extend(split_long_line(normalized))
    return lines


def split_long_line(value: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    tokens = value.split(" ")
    for token in tokens:
        token_len = len(token) + (1 if current else 0)
        if current and current_len + token_len > 220:
            chunks.append(" ".join(current))
            current = [token]
            current_len = len(token)
            continue
        current.append(token)
        current_len += token_len
    if current:
        chunks.append(" ".join(current))
    return chunks


def rstrip_control(value: str) -> str:
    return re.sub(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f]+", " ", value).rstrip()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv_index(path: Path, snippets: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "sourceLinkRole",
        "detectedDocumentRole",
        "documentYearStatus",
        "documentPrimaryAdmissionYear",
        "promotionSafeSourceYear",
        "status",
        "snippetRole",
        "score",
        "pageNumber",
        "startLine",
        "endLine",
        "rawHwpPath",
        "textPath",
        "attachmentUrl",
        "textPreview",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for row in snippets:
            writer.writerow({header: row.get(header, "") for header in headers})


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def summarize(
    year: int,
    source_rows: list[dict[str, Any]],
    snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible_sources = [
        row for row in source_rows if row.get("extractionStatus") in {"extracted", "reused_duplicate_sha256"}
    ]
    source_rows_with_snippets = {str(row.get("sourceRowKey") or "") for row in snippets}
    unique_hwps_with_snippets = {str(row.get("rawHwpSha256") or "") for row in snippets}
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "sourceHwps": len(source_rows),
        "eligibleSources": len(eligible_sources),
        "sourceRowsWithSnippets": len(source_rows_with_snippets),
        "uniqueHwpsWithSnippets": len(unique_hwps_with_snippets),
        "snippets": len(snippets),
        "uniqueSnippetSha256": len({str(row.get("snippetSha256") or "") for row in snippets}),
        "bySnippetRole": count_by(snippets, "snippetRole"),
        "bySnippetStatus": count_by(snippets, "status"),
        "bySourceLinkRole": count_by(snippets, "sourceLinkRole"),
        "byDetectedDocumentRole": count_by(snippets, "detectedDocumentRole"),
        "byDocumentYearStatus": count_by(snippets, "documentYearStatus"),
        "promotionUnsafeSourceYearSnippets": sum(
            1 for row in snippets if row.get("promotionSafeSourceYear") is False
        ),
        "notes": [
            "Snippets are keyword-scored candidates extracted from HWP/HWPX text output.",
            "Snippet text is capped for manifest size; textPath/rawHwpPath retain the source for full review.",
            "status=source_year_mismatch snippets are retained for audit but must not be used as promotion evidence.",
            "Candidates require human verification before promotion to AdmissionRule or HistoricalOutcome.",
        ],
    }


if __name__ == "__main__":
    main()
