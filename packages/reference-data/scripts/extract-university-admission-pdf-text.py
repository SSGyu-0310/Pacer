#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LOCAL_PYTHON_TOOLING = ".reference-data/tools/python"


def bootstrap_local_python_tooling() -> None:
    current = Path.cwd().resolve()
    for candidate_root in [current, *current.parents]:
        if (candidate_root / "pnpm-workspace.yaml").exists():
            tooling_path = candidate_root / LOCAL_PYTHON_TOOLING
            if tooling_path.exists():
                sys.path.insert(0, str(tooling_path))
            return


bootstrap_local_python_tooling()

from pypdf import PdfReader


DEFAULT_MANIFESTS = [
    "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027.jsonl",
    "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027_file_download_route.jsonl",
    "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027_related_detail.jsonl",
    "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027_related_detail_file_routes.jsonl",
]
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    manifest_paths = [resolve(repo_root, value) for value in args.manifest]
    output_dir = resolve(repo_root, args.output_dir)
    text_root = output_dir / "pdf-text" / str(args.year)
    text_root.mkdir(parents=True, exist_ok=True)

    pdftotext = args.pdftotext or shutil.which("pdftotext")
    pdfinfo = args.pdfinfo or shutil.which("pdfinfo")
    if not pdftotext:
        raise RuntimeError("pdftotext is required for source-preserving PDF text extraction.")

    artifact_rows = load_manifest_rows(manifest_paths)
    pdf_rows = [
        row
        for row in artifact_rows
        if is_http_ok_pdf(row, repo_root) and int(row.get("year") or 0) == args.year
    ]
    if args.limit is not None:
        pdf_rows = pdf_rows[: args.limit]

    extraction_cache: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []

    for index, artifact in enumerate(pdf_rows, start=1):
        source_row = source_manifest_row(artifact, repo_root)
        sha256 = str(source_row.get("rawPdfSha256") or "")
        raw_pdf_path = repo_root / str(source_row["rawPdfPath"])

        if not raw_pdf_path.exists():
            source_row.update(
                {
                    "extractionStatus": "missing_raw_file",
                    "notes": "Raw PDF path does not exist in the local artifact store.",
                }
            )
            source_rows.append(source_row)
            continue

        if sha256 in extraction_cache:
            source_row.update(extraction_cache[sha256])
            source_row["extractionStatus"] = "reused_duplicate_sha256"
            source_rows.append(source_row)
            continue

        text_path = text_path_for(text_root, sha256, index)
        text_path.parent.mkdir(parents=True, exist_ok=True)

        extraction_result = extract_pdf_text(
            pdf_path=raw_pdf_path,
            text_path=text_path,
            repo_root=repo_root,
            pdftotext=pdftotext,
            pdfinfo=pdfinfo,
            force=args.force,
        )
        extraction_cache[sha256] = extraction_result
        source_row.update(extraction_result)
        source_row["extractionStatus"] = (
            "extracted" if extraction_result.get("extractReturnCode") == 0 else "extract_failed"
        )
        source_rows.append(source_row)

        print(
            "university admission pdf text "
            f"index={index}/{len(pdf_rows)} "
            f"unvCd={source_row.get('unvCd')} "
            f"status={source_row.get('extractionStatus')} "
            f"pages={source_row.get('pages')} "
            f"chars={source_row.get('textChars')}"
        )

    summary = summarize(args.year, source_rows)
    write_jsonl(
        output_dir / f"university_admission_pdf_sources_manifest_{args.year}.jsonl",
        source_rows,
    )
    write_csv(
        output_dir / f"university_admission_pdf_low_text_candidates_{args.year}.csv",
        low_text_rows(source_rows),
    )
    write_csv(
        output_dir / f"university_admission_pdf_extract_failed_{args.year}.csv",
        failed_rows(source_rows),
    )
    (output_dir / f"university_admission_pdf_text_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "university admission pdf text extraction complete. "
        f"sources={summary['sourcePdfs']} "
        f"unique={summary['uniqueRawPdfSha256']} "
        f"extractedUnique={summary['extractedUniquePdfs']} "
        f"textRoot={to_repo_relative(text_root, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--manifest", action="append", default=[])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--pdftotext")
    parser.add_argument("--pdfinfo")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(cli_args())
    if not args.manifest:
        args.manifest = DEFAULT_MANIFESTS
    return args


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


def load_manifest_rows(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                row = json.loads(line)
                row["_manifestPath"] = str(path)
                rows.append(row)
    return rows


def is_http_ok_pdf(row: dict[str, Any], repo_root: Path) -> bool:
    status = str(row.get("status") or "")
    kind = str(row.get("detectedKind") or "")
    extension = artifact_extension(row)
    http_status = row.get("httpStatus")
    return (
        status == "fetched"
        and extension == "pdf"
        and isinstance(http_status, int)
        and 200 <= http_status < 300
        and (kind == "file" or has_file_signature(row, repo_root, b"%PDF"))
    )


def artifact_extension(row: dict[str, Any]) -> str:
    extension = str(row.get("fileExtension") or "").lower().lstrip(".")
    if extension:
        return extension
    raw_suffix = Path(str(row.get("rawPath") or "")).suffix.lower().lstrip(".")
    if raw_suffix:
        return raw_suffix
    return Path(str(row.get("suggestedFilename") or "")).suffix.lower().lstrip(".")


def has_file_signature(row: dict[str, Any], repo_root: Path, signature: bytes) -> bool:
    raw_path = str(row.get("rawPath") or "")
    if not raw_path:
        return False
    path = repo_root / raw_path
    if not path.exists():
        return False
    try:
        with path.open("rb") as file:
            return file.read(len(signature)) == signature
    except OSError:
        return False


def source_manifest_row(artifact: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    raw_path = str(artifact.get("rawPath") or "")
    raw_pdf_path = repo_root / raw_path
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_pdf_text_source",
        "year": artifact.get("year"),
        "unvCd": artifact.get("unvCd"),
        "universityName": artifact.get("universityName"),
        "campus": artifact.get("campus"),
        "sourceLinkRole": artifact.get("sourceLinkRole"),
        "attachmentRole": artifact.get("attachmentRole"),
        "linkText": artifact.get("linkText"),
        "detectedDocumentRole": detect_document_role(
            " ".join(
                [
                    str(artifact.get("sourceLinkRole") or ""),
                    str(artifact.get("linkText") or ""),
                    str(artifact.get("suggestedFilename") or ""),
                ]
            )
        ),
        "sourceCandidateUrl": artifact.get("sourceCandidateUrl"),
        "attachmentUrl": artifact.get("attachmentUrl"),
        "finalUrl": artifact.get("finalUrl"),
        "rawPdfPath": raw_path,
        "rawPdfSha256": artifact.get("sha256"),
        "rawPdfBytes": artifact.get("bytes"),
        "suggestedFilename": artifact.get("suggestedFilename"),
        "contentType": artifact.get("contentType"),
        "sourceManifestPath": to_repo_relative(Path(str(artifact.get("_manifestPath"))), repo_root),
        "rawFileExists": raw_pdf_path.exists(),
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }


def extract_pdf_text(
    *,
    pdf_path: Path,
    text_path: Path,
    repo_root: Path,
    pdftotext: str,
    pdfinfo: str | None,
    force: bool,
) -> dict[str, Any]:
    reused_existing_text = text_path.exists() and text_path.stat().st_size > 0 and not force
    if reused_existing_text:
        process_return_code = 0
        process_stdout = ""
        process_stderr = ""
    else:
        process = subprocess.run(
            [pdftotext, "-layout", "-enc", "UTF-8", str(pdf_path), str(text_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        process_return_code = process.returncode
        process_stdout = process.stdout.strip()
        process_stderr = process.stderr.strip()

    text = text_path.read_text(encoding="utf-8", errors="replace") if text_path.exists() else ""
    text_chars = len(text)
    non_whitespace_chars = len(re.sub(r"\s+", "", text))
    pages = page_count_with_pdfinfo(pdf_path, pdfinfo)
    if pages is None:
        pages = page_count_with_pypdf(pdf_path)
    if pages is None:
        pages = 0

    low_text_pdf = pages > 0 and non_whitespace_chars / pages < 80
    text_preview = preview_text(text)

    return {
        "textPath": to_repo_relative(text_path, repo_root) if text_path.exists() else "",
        "textSha256": sha256_file(text_path) if text_path.exists() else "",
        "pages": pages,
        "textChars": text_chars,
        "nonWhitespaceChars": non_whitespace_chars,
        "charsPerPage": round(non_whitespace_chars / pages, 2) if pages else 0,
        "lowTextPdf": low_text_pdf,
        "textPreview": text_preview,
        "extractTool": "pdftotext -layout",
        "extractReturnCode": process_return_code,
        "extractReusedExistingText": reused_existing_text,
        "extractStdout": process_stdout,
        "extractStderr": process_stderr,
        "notes": "" if process_return_code == 0 else "pdftotext returned a non-zero exit code.",
    }


def page_count_with_pdfinfo(pdf_path: Path, pdfinfo: str | None) -> int | None:
    if not pdfinfo:
        return None
    process = subprocess.run(
        [pdfinfo, str(pdf_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        return None
    for line in process.stdout.splitlines():
        match = re.match(r"Pages:\s+(\d+)", line)
        if match:
            return int(match.group(1))
    return None


def page_count_with_pypdf(pdf_path: Path) -> int | None:
    try:
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        return None


def text_path_for(text_root: Path, sha256: str, sequence: int) -> Path:
    if sha256:
        return text_root / sha256[:2] / f"{sha256[:16]}.txt"
    return text_root / "unknown" / f"{sequence:04d}.txt"


def preview_text(text: str) -> list[str]:
    lines = [normalize_space(line) for line in text.splitlines()]
    return [line for line in lines if line][:8]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def detect_document_role(text: str) -> str:
    normalized = text.lower()
    if re.search(r"경쟁률|competition|competition_rate", normalized):
        return "competition_rate_pdf"
    if re.search(r"입시결과|입학결과|전형결과|admission_result|합격|등록|충원|성적|환산|백분위|등급", normalized):
        return "admission_result_pdf"
    if re.search(r"모집요강|모집인원|전형계획|regular_admission_guide|recruitment_notice|정시|수능|전형방법|반영", normalized):
        return "recruitment_notice_pdf"
    return "unknown"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root))
    except ValueError:
        return str(resolved)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "sourceLinkRole",
        "attachmentRole",
        "detectedDocumentRole",
        "pages",
        "charsPerPage",
        "textChars",
        "rawPdfPath",
        "textPath",
        "attachmentUrl",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def low_text_rows(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [row for row in source_rows if row.get("lowTextPdf")],
        key=lambda row: (
            float(row.get("charsPerPage") or 0),
            str(row.get("universityName") or ""),
            str(row.get("rawPdfPath") or ""),
        ),
    )


def failed_rows(source_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in source_rows if row.get("extractionStatus") == "extract_failed"]


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u001f\u007f-\u009f]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "")
        counts[value] = counts.get(value, 0) + 1
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def summarize(year: int, source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    unique_sha = {str(row.get("rawPdfSha256") or "") for row in source_rows}
    extracted_unique = {
        str(row.get("rawPdfSha256") or "")
        for row in source_rows
        if row.get("extractionStatus") == "extracted"
    }
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "sourcePdfs": len(source_rows),
        "uniqueRawPdfSha256": len(unique_sha),
        "extractedUniquePdfs": len(extracted_unique),
        "reusedDuplicateSourcePdfs": sum(
            1 for row in source_rows if row.get("extractionStatus") == "reused_duplicate_sha256"
        ),
        "failedSourcePdfs": sum(
            1 for row in source_rows if row.get("extractionStatus") == "extract_failed"
        ),
        "missingRawSourcePdfs": sum(
            1 for row in source_rows if row.get("extractionStatus") == "missing_raw_file"
        ),
        "lowTextSourcePdfs": sum(1 for row in source_rows if row.get("lowTextPdf")),
        "totalPages": sum(int(row.get("pages") or 0) for row in source_rows),
        "totalTextChars": sum(int(row.get("textChars") or 0) for row in source_rows),
        "totalNonWhitespaceChars": sum(
            int(row.get("nonWhitespaceChars") or 0) for row in source_rows
        ),
        "byExtractionStatus": count_by(source_rows, "extractionStatus"),
        "bySourceLinkRole": count_by(source_rows, "sourceLinkRole"),
        "byAttachmentRole": count_by(source_rows, "attachmentRole"),
        "byDetectedDocumentRole": count_by(source_rows, "detectedDocumentRole"),
        "notes": [
            "PDF text is extracted with pdftotext -layout to preserve table-like spacing where possible.",
            "Duplicate source rows with the same PDF SHA-256 reuse the first extracted text artifact.",
            "lowTextPdf=true indicates likely scanned/image-heavy PDFs that need image/OCR handling before data promotion.",
            "Extracted text is a source-preserving candidate and requires human verification before promotion to AdmissionRule or HistoricalOutcome.",
        ],
    }


if __name__ == "__main__":
    main()
