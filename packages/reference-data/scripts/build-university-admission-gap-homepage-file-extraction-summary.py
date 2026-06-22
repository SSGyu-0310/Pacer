#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-file-attachments"
)
DEFAULT_YEARS = "2021,2022,2023,2024,2025,2026,2027"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    years = [int(value) for value in args.years.split(",") if value.strip()]

    yearly: dict[str, dict[str, int]] = {}
    totals: Counter[str] = Counter()
    evidence_target = Counter()
    evidence_type = Counter()
    evidence_role = Counter()
    inputs: list[Path] = []

    for year in years:
        row = {
            "workbookSources": get_summary_value(
                output_dir, year, "workbook_sheets", "sourceWorkbooks"
            ),
            "workbookExtracted": get_summary_value(
                output_dir, year, "workbook_sheets", "extractedWorkbooks"
            ),
            "workbookSheets": get_summary_value(output_dir, year, "workbook_sheets", "sheets"),
            "workbookRowCandidates": get_summary_value(
                output_dir, year, "workbook_row_candidates", "rowCandidates"
            ),
            "pdfSources": get_summary_value(output_dir, year, "pdf_text", "sourcePdfs"),
            "uniquePdfs": get_summary_value(output_dir, year, "pdf_text", "uniqueRawPdfSha256"),
            "extractedUniquePdfs": get_summary_value(
                output_dir, year, "pdf_text", "extractedUniquePdfs"
            ),
            "lowTextSourcePdfs": get_summary_value(
                output_dir, year, "pdf_text", "lowTextSourcePdfs"
            ),
            "lowTextUniquePdfs": get_summary_value(
                output_dir, year, "low_text_pdf_images", "uniqueLowTextPdfs"
            ),
            "lowTextRenderedPageImages": get_summary_value(
                output_dir, year, "low_text_pdf_images", "renderedPageImages"
            ),
            "lowTextTotalImageBytes": get_summary_value(
                output_dir, year, "low_text_pdf_images", "totalImageBytes"
            ),
            "lowTextRenderFailures": get_summary_value(
                output_dir, year, "low_text_pdf_images", "failedDocumentRows"
            ),
            "lowTextPartialDocumentRows": get_summary_value(
                output_dir, year, "low_text_pdf_images", "partialDocumentRows"
            ),
            "lowTextOcrCandidates": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "ocrCandidates"
            ),
            "lowTextOcrRows": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "ocrRows"
            ),
            "lowTextOcrExtracted": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "ocrExtracted"
            ),
            "lowTextOcrFailed": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "ocrFailed"
            ),
            "lowTextOcrTimeout": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "ocrTimeout"
            ),
            "lowTextMissingPageImages": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "missingPageImages"
            ),
            "lowTextRowsWithText": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "rowsWithText"
            ),
            "lowTextRowsWithKeywords": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "rowsWithKeywords"
            ),
            "lowTextOcrEvidenceRows": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "evidenceRows"
            ),
            "lowTextOcrTextChars": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "totalTextChars"
            ),
            "lowTextOcrNonWhitespaceChars": get_summary_value(
                output_dir, year, "low_text_pdf_page_ocr", "totalNonWhitespaceChars"
            ),
            "pdfPages": get_summary_value(output_dir, year, "pdf_text", "totalPages"),
            "pdfTextChars": get_summary_value(output_dir, year, "pdf_text", "totalTextChars"),
            "pdfSnippets": get_summary_value(output_dir, year, "pdf_snippets", "snippets"),
            "hwpSources": get_summary_value(output_dir, year, "hwp_text", "sourceHwps"),
            "uniqueHwps": get_summary_value(output_dir, year, "hwp_text", "uniqueRawHwpSha256"),
            "extractedUniqueHwps": get_summary_value(
                output_dir, year, "hwp_text", "extractedUniqueHwps"
            ),
            "hwpTextChars": get_summary_value(output_dir, year, "hwp_text", "totalTextChars"),
            "hwpSnippets": get_summary_value(output_dir, year, "hwp_snippets", "snippets"),
            "officeDocumentSources": get_summary_value(
                output_dir, year, "office_document_text", "sourceOfficeDocuments"
            ),
            "officeDocumentExtracted": get_summary_value(
                output_dir, year, "office_document_text", "extractedUniqueOfficeDocuments"
            ),
            "officeDocumentTextChars": get_summary_value(
                output_dir, year, "office_document_text", "totalTextChars"
            ),
            "officeDocumentSnippets": get_summary_value(
                output_dir, year, "office_document_snippets", "snippets"
            ),
            "evidenceRows": get_summary_value(output_dir, year, "evidence_index", "evidenceRows"),
        }
        yearly[str(year)] = row
        totals.update(row)

        for stem in SUMMARY_STEMS:
            path = output_dir / f"university_admission_{stem}_{year}.json"
            if path.exists():
                inputs.append(path)

        evidence_summary_path = output_dir / f"university_admission_evidence_index_summary_{year}.json"
        if evidence_summary_path.exists():
            evidence_summary = json.loads(evidence_summary_path.read_text(encoding="utf-8"))
            evidence_target.update(counter_from_rows(evidence_summary.get("byEvidenceTarget")))
            evidence_type.update(counter_from_rows(evidence_summary.get("byEvidenceType")))
            evidence_role.update(counter_from_rows(evidence_summary.get("byEvidenceRole")))

    promotion_summary_path = output_dir / "university_admission_promotion_review_summary.json"
    promotion_summary = (
        json.loads(promotion_summary_path.read_text(encoding="utf-8"))
        if promotion_summary_path.exists()
        else {}
    )
    if promotion_summary_path.exists():
        inputs.append(promotion_summary_path)

    output = {
        "provider": "university-admission-office",
        "artifactType": "gap_homepage_file_attachment_extraction_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "years": years,
        "outputDir": to_repo_relative(output_dir, repo_root),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in inputs
        ],
        "yearly": yearly,
        "aggregate": dict(totals),
        "byEvidenceTarget": counter_rows(evidence_target, 20),
        "byEvidenceType": counter_rows(evidence_type, 20),
        "byEvidenceRole": counter_rows(evidence_role, 30),
        "promotionReview": {
            "sourceEvidenceRows": promotion_summary.get("sourceEvidenceRows", 0),
            "promotionReviewCandidates": promotion_summary.get("promotionReviewCandidates", 0),
            "dedupeRatio": promotion_summary.get("dedupeRatio", 0),
            "universitiesRepresented": promotion_summary.get("universitiesRepresented", 0),
            "candidatesWithDetectedAdmissionYear": promotion_summary.get(
                "candidatesWithDetectedAdmissionYear", 0
            ),
            "candidatesWithoutDetectedAdmissionYear": promotion_summary.get(
                "candidatesWithoutDetectedAdmissionYear", 0
            ),
            "byEvidenceTarget": promotion_summary.get("byEvidenceTarget", []),
            "byEvidenceRole": promotion_summary.get("byEvidenceRole", []),
            "byEvidenceType": promotion_summary.get("byEvidenceType", []),
            "byCollectionYear": promotion_summary.get("byCollectionYear", []),
            "sourceEvidenceRowsByCollectionYear": promotion_summary.get(
                "sourceEvidenceRowsByCollectionYear", []
            ),
        },
        "notes": [
            "This summary covers extraction outputs generated from gap-homepage direct_file and file_download_route attachment artifacts.",
            "Rows are source-preserving review candidates, not verified AdmissionRule, AdmissionSchedule, or HistoricalOutcome records.",
            "Low-text PDF page render and OCR evidence rows are included when the corresponding summaries are present.",
            "OCR rows remain source-preserving candidates and should be reviewed before promotion into verified reference tables.",
        ],
    }

    output_path = output_dir / "university_admission_gap_homepage_file_extraction_summary.json"
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "university admission gap homepage file extraction summary complete. "
        f"evidenceRows={totals['evidenceRows']} "
        f"promotionCandidates={output['promotionReview']['promotionReviewCandidates']}"
    )


SUMMARY_STEMS = {
    "workbook_sheets_summary",
    "workbook_row_candidates_summary",
    "pdf_text_summary",
    "pdf_snippets_summary",
    "low_text_pdf_images_summary",
    "low_text_pdf_page_ocr_summary",
    "hwp_text_summary",
    "hwp_snippets_summary",
    "office_document_text_summary",
    "office_document_snippets_summary",
    "evidence_index_summary",
}

SUMMARY_FILES = {
    "workbook_sheets": "workbook_sheets_summary",
    "workbook_row_candidates": "workbook_row_candidates_summary",
    "pdf_text": "pdf_text_summary",
    "pdf_snippets": "pdf_snippets_summary",
    "low_text_pdf_images": "low_text_pdf_images_summary",
    "low_text_pdf_page_ocr": "low_text_pdf_page_ocr_summary",
    "hwp_text": "hwp_text_summary",
    "hwp_snippets": "hwp_snippets_summary",
    "office_document_text": "office_document_text_summary",
    "office_document_snippets": "office_document_snippets_summary",
    "evidence_index": "evidence_index_summary",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
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


def get_summary_value(output_dir: Path, year: int, summary_key: str, field: str) -> int:
    stem = SUMMARY_FILES[summary_key]
    path = output_dir / f"university_admission_{stem}_{year}.json"
    if not path.exists():
        return 0
    summary = json.loads(path.read_text(encoding="utf-8"))
    return int(summary.get(field) or 0)


def counter_from_rows(rows: Any) -> Counter[str]:
    counter: Counter[str] = Counter()
    if not isinstance(rows, list):
        return counter
    for row in rows:
        if isinstance(row, dict):
            counter[str(row.get("value") or "")] += int(row.get("count") or 0)
    return counter


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
