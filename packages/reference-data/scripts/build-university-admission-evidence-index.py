#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"
DEFAULT_PDF_SNIPPETS = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_pdf_snippets_2027.jsonl"
)
DEFAULT_HWP_SNIPPETS = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_hwp_snippets_2027.jsonl"
)
DEFAULT_OFFICE_DOCUMENT_SNIPPETS = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_office_document_snippets_2027.jsonl"
)
DEFAULT_HTML_SNIPPETS = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_html_snippets_2027.jsonl"
)
DEFAULT_WORKBOOK_SHEETS = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_workbook_sheets_manifest_2027.jsonl"
)
DEFAULT_WORKBOOK_ROW_CANDIDATES = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_workbook_row_candidates_2027.jsonl"
)
DEFAULT_LOW_TEXT_PDF_PAGE_IMAGES = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_low_text_pdf_page_images_2027.jsonl"
)
DEFAULT_LOW_TEXT_PDF_PAGE_OCR_EVIDENCE = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_low_text_pdf_page_ocr_evidence_index_2027.jsonl"
)


TARGET_BY_ROLE = {
    "admission_result_table": "HistoricalOutcome",
    "admission_result_row": "HistoricalOutcome",
    "competition_rate_table": "HistoricalOutcome",
    "competition_rate_row": "HistoricalOutcome",
    "csat_reflection_rule": "AdmissionRule",
    "screening_method": "AdmissionRule",
    "screening_method_row": "AdmissionRule",
    "recruitment_quota_table": "AdmissionRule",
    "recruitment_quota_row": "AdmissionRule",
    "recruitment_notice_table": "AdmissionRule",
    "eligibility_rule": "AdmissionRule",
    "school_record_rule": "AdmissionRule",
    "schedule_and_registration": "AdmissionSchedule",
    "schedule_row": "AdmissionSchedule",
    "low_text_pdf_page_image": "OCRReviewQueue",
    "workbook_review_row": "ReviewQueue",
    "unknown": "ReviewQueue",
}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    evidence_rows: list[dict[str, Any]] = []
    evidence_rows.extend(
        pdf_snippet_evidence(load_jsonl(resolve(repo_root, args.pdf_snippets)), args.year)
    )
    evidence_rows.extend(
        hwp_snippet_evidence(load_jsonl(resolve(repo_root, args.hwp_snippets)), args.year)
    )
    evidence_rows.extend(
        office_document_snippet_evidence(
            load_jsonl(resolve(repo_root, args.office_document_snippets)), args.year
        )
    )
    evidence_rows.extend(
        html_snippet_evidence(load_jsonl(resolve(repo_root, args.html_snippets)), args.year)
    )
    evidence_rows.extend(
        workbook_sheet_evidence(load_jsonl(resolve(repo_root, args.workbook_sheets)), args.year)
    )
    evidence_rows.extend(
        workbook_row_evidence(
            load_jsonl(resolve(repo_root, args.workbook_row_candidates)), args.year
        )
    )
    evidence_rows.extend(
        low_text_pdf_image_evidence(
            load_jsonl(resolve(repo_root, args.low_text_pdf_page_images)), args.year
        )
    )
    evidence_rows.extend(
        low_text_pdf_page_ocr_evidence(
            load_jsonl(resolve(repo_root, args.low_text_pdf_page_ocr_evidence)), args.year
        )
    )

    evidence_rows.sort(
        key=lambda row: (
            str(row.get("unvCd") or ""),
            str(row.get("evidenceTarget") or ""),
            str(row.get("evidenceRole") or ""),
            -int(row.get("priorityScore") or 0),
            str(row.get("evidenceSha256") or ""),
        )
    )

    write_jsonl(
        output_dir / f"university_admission_evidence_index_{args.year}.jsonl",
        evidence_rows,
    )
    write_csv_index(
        output_dir / f"university_admission_evidence_index_{args.year}.csv",
        evidence_rows,
    )
    summary = summarize(args.year, evidence_rows)
    (output_dir / f"university_admission_evidence_index_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "university admission evidence index complete. "
        f"rows={summary['evidenceRows']} targets={len(summary['byEvidenceTarget'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--pdf-snippets", default=DEFAULT_PDF_SNIPPETS)
    parser.add_argument("--hwp-snippets", default=DEFAULT_HWP_SNIPPETS)
    parser.add_argument("--office-document-snippets", default=DEFAULT_OFFICE_DOCUMENT_SNIPPETS)
    parser.add_argument("--html-snippets", default=DEFAULT_HTML_SNIPPETS)
    parser.add_argument("--workbook-sheets", default=DEFAULT_WORKBOOK_SHEETS)
    parser.add_argument("--workbook-row-candidates", default=DEFAULT_WORKBOOK_ROW_CANDIDATES)
    parser.add_argument("--low-text-pdf-page-images", default=DEFAULT_LOW_TEXT_PDF_PAGE_IMAGES)
    parser.add_argument(
        "--low-text-pdf-page-ocr-evidence",
        default=DEFAULT_LOW_TEXT_PDF_PAGE_OCR_EVIDENCE,
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def pdf_snippet_evidence(snippets: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snippet in snippets:
        if int(snippet.get("year") or 0) != year:
            continue
        role = str(snippet.get("snippetRole") or "unknown")
        rows.append(
            base_evidence_row(
                source=snippet,
                evidence_type="pdf_snippet",
                evidence_role=role,
                source_document_kind="pdf",
                source_path=snippet.get("textPath"),
                raw_path=snippet.get("rawPdfPath"),
                source_sha256=snippet.get("rawPdfSha256"),
                text_preview=snippet.get("textPreview"),
                text=snippet.get("text"),
                source_specific={
                    "score": snippet.get("score"),
                    "pageNumber": snippet.get("pageNumber"),
                    "startLine": snippet.get("startLine"),
                    "endLine": snippet.get("endLine"),
                    "matchedKeywords": snippet.get("matchedKeywords"),
                    "snippetSha256": snippet.get("snippetSha256"),
                },
            )
        )
    return rows


def hwp_snippet_evidence(snippets: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snippet in snippets:
        if int(snippet.get("year") or 0) != year:
            continue
        role = str(snippet.get("snippetRole") or "unknown")
        rows.append(
            base_evidence_row(
                source=snippet,
                evidence_type="hwp_snippet",
                evidence_role=role,
                source_document_kind="hwp",
                source_path=snippet.get("textPath"),
                raw_path=snippet.get("rawHwpPath"),
                source_sha256=snippet.get("rawHwpSha256"),
                text_preview=snippet.get("textPreview"),
                text=snippet.get("text"),
                source_specific={
                    "score": snippet.get("score"),
                    "startLine": snippet.get("startLine"),
                    "endLine": snippet.get("endLine"),
                    "matchedKeywords": snippet.get("matchedKeywords"),
                    "snippetSha256": snippet.get("snippetSha256"),
                },
            )
        )
    return rows


def office_document_snippet_evidence(
    snippets: list[dict[str, Any]], year: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snippet in snippets:
        if int(snippet.get("year") or 0) != year:
            continue
        role = str(snippet.get("snippetRole") or "unknown")
        extension = str(snippet.get("fileExtension") or "office_document").lower()
        rows.append(
            base_evidence_row(
                source=snippet,
                evidence_type="office_document_snippet",
                evidence_role=role,
                source_document_kind=extension,
                source_path=snippet.get("textPath"),
                raw_path=snippet.get("rawOfficeDocumentPath"),
                source_sha256=snippet.get("rawOfficeDocumentSha256"),
                text_preview=snippet.get("textPreview"),
                text=snippet.get("text"),
                source_specific={
                    "score": snippet.get("score"),
                    "fileExtension": extension,
                    "startLine": snippet.get("startLine"),
                    "endLine": snippet.get("endLine"),
                    "matchedKeywords": snippet.get("matchedKeywords"),
                    "snippetSha256": snippet.get("snippetSha256"),
                },
            )
        )
    return rows


def html_snippet_evidence(snippets: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for snippet in snippets:
        if int(snippet.get("year") or 0) != year:
            continue
        role = str(snippet.get("snippetRole") or "unknown")
        snippet_type = str(snippet.get("snippetType") or "html_snippet")
        rows.append(
            base_evidence_row(
                source=snippet,
                evidence_type=snippet_type,
                evidence_role=role,
                source_document_kind="html",
                source_path=snippet.get("rawHtmlPath"),
                raw_path=snippet.get("rawHtmlPath"),
                source_sha256=snippet.get("rawHtmlSha256"),
                text_preview=snippet.get("textPreview"),
                text=snippet.get("text"),
                source_specific={
                    **(snippet.get("sourceSpecific") or {}),
                    "score": snippet.get("score"),
                    "matchedKeywords": snippet.get("matchedKeywords"),
                    "snippetSha256": snippet.get("snippetSha256"),
                    "title": snippet.get("title"),
                    "finalUrl": snippet.get("finalUrl"),
                },
            )
        )
    return rows


def workbook_sheet_evidence(sheets: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sheet in sheets:
        if int(sheet.get("year") or 0) != year:
            continue
        if str(sheet.get("status") or "") != "extracted":
            continue
        role = str(sheet.get("detectedSheetRole") or "unknown")
        preview = header_preview_text(sheet.get("headerPreview"))
        rows.append(
            base_evidence_row(
                source=sheet,
                evidence_type="workbook_sheet",
                evidence_role=role,
                source_document_kind=str(sheet.get("fileExtension") or "workbook").lower(),
                source_path=sheet.get("csvPath"),
                raw_path=sheet.get("rawWorkbookPath"),
                source_sha256=sheet.get("rawWorkbookSha256"),
                text_preview=preview,
                text=preview,
                source_specific={
                    "sheetName": sheet.get("sheetName"),
                    "rows": sheet.get("rows"),
                    "cols": sheet.get("cols"),
                    "nonEmptyCells": sheet.get("nonEmptyCells"),
                    "sheetSha256": sheet.get("sha256"),
                },
            )
        )
    return rows


def workbook_row_evidence(candidates: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        if int(candidate.get("year") or 0) != year:
            continue
        if str(candidate.get("status") or "") != "candidate":
            continue
        role = str(candidate.get("rowCandidateRole") or "workbook_review_row")
        text = str(candidate.get("filledRowText") or candidate.get("rowText") or "")
        rows.append(
            base_evidence_row(
                source=candidate,
                evidence_type="workbook_row",
                evidence_role=role,
                source_document_kind=str(candidate.get("fileExtension") or "workbook").lower(),
                source_path=candidate.get("csvPath"),
                raw_path=candidate.get("rawWorkbookPath"),
                source_sha256=candidate.get("rawWorkbookSha256"),
                text_preview=text,
                text=text,
                source_specific={
                    "sheetName": candidate.get("sheetName"),
                    "rowIndex": candidate.get("rowIndex"),
                    "rowType": candidate.get("rowType"),
                    "nonEmptyCells": candidate.get("nonEmptyCells"),
                    "numericCellCount": candidate.get("numericCellCount"),
                    "numericValues": candidate.get("numericValues"),
                    "headerContextRows": candidate.get("headerContextRows"),
                    "cells": candidate.get("cells"),
                    "filledContextCells": candidate.get("filledContextCells"),
                    "candidateSha256": candidate.get("candidateSha256"),
                    "sheetSha256": candidate.get("sheetSha256"),
                },
            )
        )
    return rows


def low_text_pdf_image_evidence(images: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for image in images:
        if int(image.get("year") or 0) != year:
            continue
        role = "low_text_pdf_page_image"
        preview = (
            f"Low-text PDF page image for OCR/visual review: "
            f"page {image.get('pageNumber')} / {image.get('universityName')}"
        )
        rows.append(
            base_evidence_row(
                source=image,
                evidence_type="pdf_page_image",
                evidence_role=role,
                source_document_kind="pdf_page_image",
                source_path=image.get("pageImagePath"),
                raw_path=image.get("rawPdfPath"),
                source_sha256=image.get("rawPdfSha256"),
                text_preview=preview,
                text=preview,
                source_specific={
                    "pageNumber": image.get("pageNumber"),
                    "pageImagePath": image.get("pageImagePath"),
                    "pageImageSha256": image.get("pageImageSha256"),
                    "pageImageBytes": image.get("pageImageBytes"),
                    "renderDpi": image.get("renderDpi"),
                },
            )
        )
    return rows


def low_text_pdf_page_ocr_evidence(rows: list[dict[str, Any]], year: int) -> list[dict[str, Any]]:
    return [sanitize_json_value(row) for row in rows if int(row.get("year") or 0) == year]


def base_evidence_row(
    *,
    source: dict[str, Any],
    evidence_type: str,
    evidence_role: str,
    source_document_kind: str,
    source_path: Any,
    raw_path: Any,
    source_sha256: Any,
    text_preview: Any,
    text: Any,
    source_specific: dict[str, Any],
) -> dict[str, Any]:
    evidence_target = TARGET_BY_ROLE.get(evidence_role, "ReviewQueue")
    evidence_payload = {
        "type": evidence_type,
        "role": evidence_role,
        "unvCd": source.get("unvCd"),
        "sourcePath": source_path,
        "rawPath": raw_path,
        "sourceSha256": source_sha256,
        "sourceSpecific": source_specific,
        "preview": normalize_space(str(text_preview or ""))[:500],
    }
    evidence_sha = hashlib.sha256(
        json.dumps(evidence_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    priority_score = score_evidence(
        evidence_type=evidence_type,
        evidence_role=evidence_role,
        source_link_role=str(source.get("sourceLinkRole") or ""),
        source_specific=source_specific,
    )
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_evidence_candidate",
        "year": source.get("year"),
        "unvCd": source.get("unvCd"),
        "universityName": source.get("universityName"),
        "campus": source.get("campus"),
        "evidenceType": evidence_type,
        "evidenceRole": evidence_role,
        "evidenceTarget": evidence_target,
        "reviewStatus": "needs_human_verification",
        "priorityScore": priority_score,
        "sourceDocumentKind": source_document_kind,
        "sourceLinkRole": source.get("sourceLinkRole"),
        "attachmentRole": source.get("attachmentRole"),
        "detectedDocumentRole": source.get("detectedDocumentRole") or source.get("detectedSheetRole"),
        "documentDetectedAdmissionYears": source.get("documentDetectedAdmissionYears") or [],
        "sourceCandidateUrl": source.get("sourceCandidateUrl"),
        "attachmentUrl": source.get("attachmentUrl"),
        "sourcePath": source_path,
        "rawPath": raw_path,
        "sourceSha256": source_sha256,
        "evidenceSha256": evidence_sha,
        "textPreview": normalize_space(str(text_preview or ""))[:500],
        "text": str(text or "")[:4000],
        "sourceSpecific": source_specific,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def header_preview_text(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    lines: list[str] = []
    for row in value[:8]:
        if not isinstance(row, list):
            continue
        cells = [normalize_space(str(cell)) for cell in row if normalize_space(str(cell))]
        if cells:
            lines.append(" | ".join(cells[:12]))
    return "\n".join(lines)


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def score_evidence(
    *,
    evidence_type: str,
    evidence_role: str,
    source_link_role: str,
    source_specific: dict[str, Any],
) -> int:
    score = 20
    if evidence_type == "workbook_row":
        score += 24
    elif evidence_type == "workbook_sheet":
        score += 18
    elif evidence_type == "pdf_page_image":
        score += 10
    elif evidence_type in {"pdf_snippet", "hwp_snippet", "office_document_snippet"}:
        score += 12 + min(20, int(source_specific.get("score") or 0))
    if evidence_role in {
        "admission_result_table",
        "admission_result_row",
        "competition_rate_table",
        "competition_rate_row",
    }:
        score += 20
    elif evidence_role in {
        "csat_reflection_rule",
        "screening_method",
        "screening_method_row",
        "recruitment_quota_table",
        "recruitment_quota_row",
        "eligibility_rule",
        "school_record_rule",
    }:
        score += 16
    elif evidence_role in {"schedule_and_registration", "schedule_row"}:
        score += 8
    elif evidence_role == "low_text_pdf_page_image":
        score += 6
    if source_link_role == "admission_result":
        score += 14
    elif source_link_role == "competition_rate":
        score += 12
    elif source_link_role == "recruitment_notice":
        score += 8
    return score


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "evidenceType",
        "evidenceRole",
        "evidenceTarget",
        "reviewStatus",
        "priorityScore",
        "sourceDocumentKind",
        "sourceLinkRole",
        "detectedDocumentRole",
        "sourcePath",
        "rawPath",
        "attachmentUrl",
        "evidenceSha256",
        "textPreview",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for row in rows:
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


def top_by(rows: list[dict[str, Any]], key: str, limit: int = 30) -> list[dict[str, Any]]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in counts.most_common(limit)
    ]


def summarize(year: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "evidenceRows": len(rows),
        "uniqueEvidenceSha256": len({str(row.get("evidenceSha256") or "") for row in rows}),
        "universitiesWithEvidence": len({str(row.get("unvCd") or "") for row in rows if row.get("unvCd")}),
        "byEvidenceType": count_by(rows, "evidenceType"),
        "byEvidenceRole": count_by(rows, "evidenceRole"),
        "byEvidenceTarget": count_by(rows, "evidenceTarget"),
        "bySourceLinkRole": count_by(rows, "sourceLinkRole"),
        "topUniversities": top_by(rows, "universityName"),
        "notes": [
            "Evidence rows are review candidates, not verified production AdmissionRule or HistoricalOutcome records.",
            "Workbook rows point to full sheet CSVs; snippet rows retain capped text and source text/raw paths.",
            "reviewStatus=needs_human_verification must be resolved before data promotion.",
        ],
    }


if __name__ == "__main__":
    main()
