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
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PDF_SOURCE_MANIFEST = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_pdf_sources_manifest_2027.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    source_manifest_path = resolve(repo_root, args.pdf_source_manifest)
    output_dir = resolve(repo_root, args.output_dir)
    image_root = output_dir / "pdf-page-images" / str(args.year)
    image_root.mkdir(parents=True, exist_ok=True)

    pdftoppm = args.pdftoppm or shutil.which("pdftoppm")
    if not pdftoppm:
        raise RuntimeError("pdftoppm is required for low-text PDF page image rendering.")

    source_rows = load_jsonl(source_manifest_path)
    low_text_rows = [
        row
        for row in source_rows
        if int(row.get("year") or 0) == args.year
        and row.get("lowTextPdf")
        and row.get("extractionStatus") in {"extracted", "reused_duplicate_sha256"}
    ]
    unique_docs = unique_low_text_documents(low_text_rows)
    if args.max_pdfs is not None:
        unique_docs = unique_docs[: args.max_pdfs]

    document_rows: list[dict[str, Any]] = []
    page_rows: list[dict[str, Any]] = []

    for index, doc in enumerate(unique_docs, start=1):
        raw_pdf_path = repo_root / str(doc.get("rawPdfPath") or "")
        doc_row = document_manifest_row(doc, repo_root, index)
        if not raw_pdf_path.exists():
            doc_row["renderStatus"] = "missing_raw_file"
            document_rows.append(doc_row)
            continue

        page_count = int(doc.get("pages") or 0)
        max_pages = page_count
        if args.max_pages_per_pdf is not None:
            max_pages = min(max_pages, args.max_pages_per_pdf)
        doc_image_dir = image_root / str(doc.get("rawPdfSha256") or "unknown")[:2] / str(
            doc.get("rawPdfSha256") or f"unknown-{index:04d}"
        )[:16]
        doc_image_dir.mkdir(parents=True, exist_ok=True)

        render_result = render_pdf_pages(
            pdftoppm=pdftoppm,
            raw_pdf_path=raw_pdf_path,
            doc_image_dir=doc_image_dir,
            max_pages=max_pages,
            dpi=args.dpi,
            force=args.force,
        )
        doc_row.update(render_result["document"])
        document_rows.append(doc_row)
        page_rows.extend(
            page_manifest_row(
                doc=doc,
                repo_root=repo_root,
                image_path=page_path,
                page_number=page_number,
                dpi=args.dpi,
                render_status=render_result["document"]["renderStatus"],
            )
            for page_number, page_path in render_result["pages"]
        )
        print(
            "university admission low-text pdf images "
            f"index={index}/{len(unique_docs)} "
            f"unvCd={doc.get('unvCd')} "
            f"status={doc_row.get('renderStatus')} "
            f"pages={len(render_result['pages'])}/{page_count}"
        )

    write_jsonl(
        output_dir / f"university_admission_low_text_pdf_image_sources_{args.year}.jsonl",
        document_rows,
    )
    write_jsonl(
        output_dir / f"university_admission_low_text_pdf_page_images_{args.year}.jsonl",
        page_rows,
    )
    write_csv_index(
        output_dir / f"university_admission_low_text_pdf_page_image_index_{args.year}.csv",
        page_rows,
    )
    summary = summarize(args.year, low_text_rows, document_rows, page_rows, args)
    (output_dir / f"university_admission_low_text_pdf_images_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "university admission low-text pdf image rendering complete. "
        f"uniquePdfs={summary['uniqueLowTextPdfs']} pages={summary['renderedPageImages']} "
        f"imageRoot={to_repo_relative(image_root, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--pdf-source-manifest", default=DEFAULT_PDF_SOURCE_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--pdftoppm")
    parser.add_argument("--dpi", type=int, default=120)
    parser.add_argument("--max-pdfs", type=int)
    parser.add_argument("--max-pages-per-pdf", type=int)
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


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def unique_low_text_documents(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_sha: dict[str, dict[str, Any]] = {}
    duplicate_counts: Counter[str] = Counter()
    for row in rows:
        key = str(row.get("rawPdfSha256") or row.get("rawPdfPath") or "")
        if not key:
            continue
        duplicate_counts[key] += 1
        current = by_sha.get(key)
        if current is None:
            by_sha[key] = row
            continue
        current_pages = int(current.get("pages") or 0)
        row_pages = int(row.get("pages") or 0)
        if row_pages > current_pages:
            by_sha[key] = row
    docs = []
    for key, row in by_sha.items():
        copied = dict(row)
        copied["duplicateLowTextSourceRows"] = duplicate_counts[key]
        docs.append(copied)
    return sorted(
        docs,
        key=lambda row: (
            -int(row.get("pages") or 0),
            str(row.get("universityName") or ""),
            str(row.get("rawPdfSha256") or ""),
        ),
    )


def document_manifest_row(doc: dict[str, Any], repo_root: Path, sequence: int) -> dict[str, Any]:
    raw_pdf_path = repo_root / str(doc.get("rawPdfPath") or "")
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_low_text_pdf_image_source",
        "year": doc.get("year"),
        "sequence": sequence,
        "unvCd": doc.get("unvCd"),
        "universityName": doc.get("universityName"),
        "campus": doc.get("campus"),
        "sourceLinkRole": doc.get("sourceLinkRole"),
        "attachmentRole": doc.get("attachmentRole"),
        "detectedDocumentRole": doc.get("detectedDocumentRole"),
        "pages": doc.get("pages"),
        "charsPerPage": doc.get("charsPerPage"),
        "textChars": doc.get("textChars"),
        "rawPdfPath": doc.get("rawPdfPath"),
        "rawPdfSha256": doc.get("rawPdfSha256"),
        "textPath": doc.get("textPath"),
        "attachmentUrl": doc.get("attachmentUrl"),
        "duplicateLowTextSourceRows": doc.get("duplicateLowTextSourceRows", 1),
        "rawFileExists": raw_pdf_path.exists(),
        "renderedAt": datetime.now(timezone.utc).isoformat(),
    }


def render_pdf_pages(
    *,
    pdftoppm: str,
    raw_pdf_path: Path,
    doc_image_dir: Path,
    max_pages: int,
    dpi: int,
    force: bool,
) -> dict[str, Any]:
    normalize_page_image_names(doc_image_dir, max_pages)
    expected_paths = [doc_image_dir / f"page-{page_number:04d}.png" for page_number in range(1, max_pages + 1)]
    if expected_paths and all(path.exists() and path.stat().st_size > 0 for path in expected_paths) and not force:
        return {
            "document": {
                "renderStatus": "reused_existing_images",
                "renderedPages": len(expected_paths),
                "renderReturnCode": 0,
                "renderStdout": "",
                "renderStderr": "",
            },
            "pages": [(page_number, path) for page_number, path in enumerate(expected_paths, start=1)],
        }

    prefix = doc_image_dir / "page"
    process = subprocess.run(
        [
            pdftoppm,
            "-png",
            "-r",
            str(dpi),
            "-f",
            "1",
            "-l",
            str(max_pages),
            str(raw_pdf_path),
            str(prefix),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    normalize_page_image_names(doc_image_dir, max_pages)
    generated_pages: list[tuple[int, Path]] = []
    for page_number in range(1, max_pages + 1):
        expected = doc_image_dir / f"page-{page_number:04d}.png"
        if expected.exists() and expected.stat().st_size > 0:
            generated_pages.append((page_number, expected))
    render_status = "rendered" if process.returncode == 0 else "render_failed"
    if process.returncode == 0 and len(generated_pages) < max_pages:
        render_status = "partial_render"
    return {
        "document": {
            "renderStatus": render_status,
            "renderedPages": len(generated_pages),
            "renderReturnCode": process.returncode,
            "renderStdout": process.stdout.strip(),
            "renderStderr": process.stderr.strip(),
        },
        "pages": generated_pages,
    }


def normalize_page_image_names(doc_image_dir: Path, max_pages: int) -> None:
    for page_number in range(1, max_pages + 1):
        expected = doc_image_dir / f"page-{page_number:04d}.png"
        variants = [
            doc_image_dir / f"page-{page_number}.png",
            doc_image_dir / f"page-{page_number:02d}.png",
            doc_image_dir / f"page-{page_number:03d}.png",
            expected,
        ]
        for variant in variants:
            if not variant.exists() or variant == expected:
                continue
            if expected.exists():
                variant.unlink()
            else:
                variant.rename(expected)
            break


def page_manifest_row(
    *,
    doc: dict[str, Any],
    repo_root: Path,
    image_path: Path,
    page_number: int,
    dpi: int,
    render_status: str,
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_low_text_pdf_page_image",
        "year": doc.get("year"),
        "unvCd": doc.get("unvCd"),
        "universityName": doc.get("universityName"),
        "campus": doc.get("campus"),
        "sourceLinkRole": doc.get("sourceLinkRole"),
        "attachmentRole": doc.get("attachmentRole"),
        "detectedDocumentRole": doc.get("detectedDocumentRole"),
        "pageNumber": page_number,
        "pageImagePath": to_repo_relative(image_path, repo_root),
        "pageImageSha256": sha256_file(image_path),
        "pageImageBytes": image_path.stat().st_size,
        "renderDpi": dpi,
        "renderStatus": render_status,
        "sourceCandidateUrl": doc.get("sourceCandidateUrl"),
        "attachmentUrl": doc.get("attachmentUrl"),
        "rawPdfPath": doc.get("rawPdfPath"),
        "rawPdfSha256": doc.get("rawPdfSha256"),
        "textPath": doc.get("textPath"),
        "status": "ocr_or_visual_review_candidate",
        "renderedAt": datetime.now(timezone.utc).isoformat(),
    }


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


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "sourceLinkRole",
        "detectedDocumentRole",
        "pageNumber",
        "pageImagePath",
        "pageImageBytes",
        "renderDpi",
        "rawPdfPath",
        "rawPdfSha256",
        "attachmentUrl",
        "status",
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


def summarize(
    year: int,
    low_text_source_rows: list[dict[str, Any]],
    document_rows: list[dict[str, Any]],
    page_rows: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "lowTextSourceRows": len(low_text_source_rows),
        "uniqueLowTextPdfs": len(document_rows),
        "renderedDocumentRows": sum(
            1 for row in document_rows if row.get("renderStatus") in {"rendered", "reused_existing_images"}
        ),
        "partialDocumentRows": sum(1 for row in document_rows if row.get("renderStatus") == "partial_render"),
        "failedDocumentRows": sum(
            1 for row in document_rows if row.get("renderStatus") in {"render_failed", "missing_raw_file"}
        ),
        "renderedPageImages": len(page_rows),
        "totalImageBytes": sum(int(row.get("pageImageBytes") or 0) for row in page_rows),
        "renderDpi": args.dpi,
        "maxPdfs": args.max_pdfs,
        "maxPagesPerPdf": args.max_pages_per_pdf,
        "bySourceLinkRole": count_by(document_rows, "sourceLinkRole"),
        "byDetectedDocumentRole": count_by(document_rows, "detectedDocumentRole"),
        "byRenderStatus": count_by(document_rows, "renderStatus"),
        "notes": [
            "Low-text PDF page images are source-preserving OCR/visual-review candidates.",
            "Rendered pages are not verified admission-rule data until OCR or human review confirms table values.",
            "Duplicate low-text source rows with the same PDF SHA-256 render once and retain duplicateLowTextSourceRows.",
        ],
    }


if __name__ == "__main__":
    main()
