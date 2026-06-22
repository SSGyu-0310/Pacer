#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ATTACHMENT_MANIFEST = (
    "packages/reference-data/data/public/kcue/"
    "kcue_admissions_press_attachment_manifest.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/kcue/extracted"
PDF_HELPER = "packages/reference-data/scripts/extract-university-admission-pdf-text.py"
HWP_HELPER = "packages/reference-data/scripts/extract-university-admission-hwp-text.py"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    attachment_manifest_path = resolve(repo_root, args.attachment_manifest)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_helper = load_helper(repo_root / PDF_HELPER, "pacer_university_pdf_text_helper")
    hwp_helper = load_helper(repo_root / HWP_HELPER, "pacer_university_hwp_text_helper")
    pdftotext = args.pdftotext or shutil.which("pdftotext")
    pdfinfo = args.pdfinfo or shutil.which("pdfinfo")
    if not pdftotext:
        raise RuntimeError("pdftotext is required for KCUE PDF text extraction.")

    attachment_rows = [
        row
        for row in load_jsonl(attachment_manifest_path)
        if str(row.get("status") or "") == "downloaded"
        and str(row.get("expectedExtension") or "").lower() in {"pdf", "hwp", "hwpx"}
    ]
    if args.limit is not None:
        attachment_rows = attachment_rows[: args.limit]

    extraction_cache: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []

    for index, attachment in enumerate(attachment_rows, start=1):
        source_row = source_manifest_row(attachment, repo_root)
        sha256 = str(source_row.get("rawAttachmentSha256") or "")
        raw_path = repo_root / str(source_row.get("rawAttachmentPath") or "")
        extension = str(source_row.get("expectedExtension") or "").lower()

        if not raw_path.exists():
            source_row.update(
                {
                    "extractionStatus": "missing_raw_file",
                    "notes": "Raw KCUE attachment path does not exist in the local artifact store.",
                }
            )
            source_rows.append(source_row)
            continue

        if sha256 in extraction_cache:
            source_row.update(extraction_cache[sha256])
            source_row["extractionStatus"] = "reused_duplicate_sha256"
            source_rows.append(source_row)
            continue

        text_path = text_path_for(output_dir, extension, sha256, index)
        text_path.parent.mkdir(parents=True, exist_ok=True)

        if extension == "pdf":
            result = pdf_helper.extract_pdf_text(
                pdf_path=raw_path,
                text_path=text_path,
                repo_root=repo_root,
                pdftotext=pdftotext,
                pdfinfo=pdfinfo,
                force=args.force,
            )
            result["extractionStatus"] = (
                "extracted" if result.get("extractReturnCode") == 0 else "extract_failed"
            )
            result["documentKind"] = "pdf"
        else:
            result = hwp_helper.extract_hwp_text(raw_path, text_path, repo_root)
            result["documentKind"] = extension

        extraction_cache[sha256] = result
        source_row.update(result)
        source_rows.append(source_row)

        print(
            "kcue admissions press text "
            f"index={index}/{len(attachment_rows)} "
            f"idx={source_row.get('idx')} "
            f"kind={extension} "
            f"status={source_row.get('extractionStatus')} "
            f"chars={source_row.get('textChars')}"
        )

    write_jsonl(output_dir / "kcue_admissions_press_text_sources.jsonl", source_rows)
    write_csv(
        output_dir / "kcue_admissions_press_low_text_or_attention.csv",
        attention_rows(source_rows),
    )
    summary = summarize(source_rows)
    (output_dir / "kcue_admissions_press_text_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "kcue admissions press text extraction complete. "
        f"sources={summary['sourceAttachments']} "
        f"unique={summary['uniqueRawAttachmentSha256']} "
        f"extracted={summary['extractedSources']} "
        f"textRoot={to_repo_relative(output_dir, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attachment-manifest", default=DEFAULT_ATTACHMENT_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pdftotext")
    parser.add_argument("--pdfinfo")
    parser.add_argument("--force", action="store_true")
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


def load_helper(path: Path, module_name: str) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load helper script: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def source_manifest_row(attachment: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    raw_path = str(attachment.get("rawPath") or "")
    return {
        "provider": "kcue",
        "artifactType": "kcue_admissions_press_text_source",
        "idx": attachment.get("idx"),
        "title": attachment.get("title"),
        "postRole": attachment.get("postRole"),
        "academicYear": attachment.get("academicYear"),
        "postedDate": attachment.get("postedDate"),
        "attachmentIndex": attachment.get("attachmentIndex"),
        "attachmentTitle": attachment.get("attachmentTitle"),
        "attachmentRole": attachment.get("attachmentRole"),
        "expectedExtension": str(attachment.get("expectedExtension") or "").lower(),
        "sourceUrl": attachment.get("sourceUrl"),
        "viewUrl": attachment.get("viewUrl"),
        "rawAttachmentPath": raw_path,
        "rawAttachmentSha256": attachment.get("sha256"),
        "rawAttachmentBytes": attachment.get("bytes"),
        "contentType": attachment.get("contentType"),
        "rawFileExists": (repo_root / raw_path).exists(),
        "sourceManifestPath": DEFAULT_ATTACHMENT_MANIFEST,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }


def text_path_for(output_dir: Path, extension: str, sha256: str, sequence: int) -> Path:
    folder = "pdf-text" if extension == "pdf" else "hwp-text"
    if sha256:
        return output_dir / folder / sha256[:2] / f"{sha256[:16]}.txt"
    return output_dir / folder / "unknown" / f"{sequence:04d}.txt"


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "idx",
        "title",
        "postRole",
        "academicYear",
        "postedDate",
        "attachmentRole",
        "expectedExtension",
        "extractionStatus",
        "documentKind",
        "pages",
        "charsPerPage",
        "textChars",
        "nonWhitespaceChars",
        "rawAttachmentPath",
        "textPath",
        "sourceUrl",
        "notes",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def attention_rows(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    statuses = {
        "extract_failed",
        "missing_raw_file",
        "low_text",
        "distribution_notice_only",
        "html_like_text",
    }
    return [
        row
        for row in source_rows
        if row.get("extractionStatus") in statuses or row.get("lowTextPdf")
    ]


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u001f\u007f-\u009f]+", " ", value).strip()
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


def summarize(source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    extracted_statuses = {"extracted", "reused_duplicate_sha256", "html_like_text"}
    return {
        "provider": "kcue",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceAttachments": len(source_rows),
        "uniqueRawAttachmentSha256": len(
            {str(row.get("rawAttachmentSha256") or "") for row in source_rows}
        ),
        "extractedSources": sum(
            1 for row in source_rows if row.get("extractionStatus") in extracted_statuses
        ),
        "failedSources": sum(1 for row in source_rows if row.get("extractionStatus") == "extract_failed"),
        "missingRawSources": sum(
            1 for row in source_rows if row.get("extractionStatus") == "missing_raw_file"
        ),
        "reusedDuplicateSources": sum(
            1 for row in source_rows if row.get("extractionStatus") == "reused_duplicate_sha256"
        ),
        "lowTextSources": sum(
            1 for row in source_rows if row.get("lowTextPdf") or row.get("extractionStatus") == "low_text"
        ),
        "distributionNoticeOnlySources": sum(
            1 for row in source_rows if row.get("extractionStatus") == "distribution_notice_only"
        ),
        "totalPages": sum(int(row.get("pages") or 0) for row in source_rows),
        "totalTextChars": sum(int(row.get("textChars") or 0) for row in source_rows),
        "totalNonWhitespaceChars": sum(
            int(row.get("nonWhitespaceChars") or 0) for row in source_rows
        ),
        "byExpectedExtension": count_by(source_rows, "expectedExtension"),
        "byPostRole": count_by(source_rows, "postRole"),
        "byAttachmentRole": count_by(source_rows, "attachmentRole"),
        "byExtractionStatus": count_by(source_rows, "extractionStatus"),
        "byDocumentKind": count_by(source_rows, "documentKind"),
        "notes": [
            "PDF attachments are extracted with pdftotext -layout.",
            "HWP/HWPX attachments reuse the HWP5/HWPX extraction routines used by university admission-office data.",
            "Rows are source-preserving candidates and require human verification before promotion to AdmissionSchedule or AdmissionRule.",
        ],
    }


def to_repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    main()
