#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


DEFAULT_MANIFESTS = [
    "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027.jsonl",
    "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027_file_download_route.jsonl",
    "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027_related_detail.jsonl",
    "packages/reference-data/data/public/university-admission-sites/university_admission_attachment_artifact_manifest_2027_related_detail_file_routes.jsonl",
]
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"
OFFICE_DOCUMENT_EXTENSIONS = {"doc", "docx", "ppt", "pptx"}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    manifest_paths = [resolve(repo_root, value) for value in args.manifest]
    output_dir = resolve(repo_root, args.output_dir)
    text_root = output_dir / "office-document-text" / str(args.year)
    text_root.mkdir(parents=True, exist_ok=True)

    artifact_rows = load_manifest_rows(manifest_paths)
    office_rows = [
        row
        for row in artifact_rows
        if is_http_ok_office_document(row, repo_root) and int(row.get("year") or 0) == args.year
    ]
    if args.limit is not None:
        office_rows = office_rows[: args.limit]

    extraction_cache: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []

    for index, artifact in enumerate(office_rows, start=1):
        source_row = source_manifest_row(artifact, repo_root)
        sha256 = str(source_row.get("rawOfficeDocumentSha256") or "")
        raw_document_path = repo_root / str(source_row["rawOfficeDocumentPath"])

        if not raw_document_path.exists():
            source_row.update(
                {
                    "extractionStatus": "missing_raw_file",
                    "notes": "Raw Office document path does not exist in the local artifact store.",
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
        extraction_result = extract_office_document_text(raw_document_path, text_path, repo_root, source_row)
        extraction_cache[sha256] = extraction_result
        source_row.update(extraction_result)
        source_rows.append(source_row)

        print(
            "university admission office document text "
            f"index={index}/{len(office_rows)} "
            f"unvCd={source_row.get('unvCd')} "
            f"ext={source_row.get('fileExtension')} "
            f"status={source_row.get('extractionStatus')} "
            f"chars={source_row.get('textChars')}"
        )

    summary = summarize(args.year, source_rows)
    write_jsonl(
        output_dir / f"university_admission_office_document_sources_manifest_{args.year}.jsonl",
        source_rows,
    )
    write_attention_csv(
        output_dir / f"university_admission_office_document_attention_candidates_{args.year}.csv",
        attention_rows(source_rows),
    )
    (output_dir / f"university_admission_office_document_text_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "university admission office document text extraction complete. "
        f"sources={summary['sourceOfficeDocuments']} "
        f"unique={summary['uniqueRawOfficeDocumentSha256']} "
        f"extractedUnique={summary['extractedUniqueOfficeDocuments']} "
        f"textRoot={to_repo_relative(text_root, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--manifest", action="append", default=[])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int)
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
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").split("\n"):
            if line.strip():
                row = json.loads(line)
                row["_manifestPath"] = str(path)
                rows.append(row)
    return rows


def is_http_ok_office_document(row: dict[str, Any], repo_root: Path) -> bool:
    status = str(row.get("status") or "")
    kind = str(row.get("detectedKind") or "")
    extension = artifact_extension(row)
    http_status = row.get("httpStatus")
    return (
        status == "fetched"
        and extension in OFFICE_DOCUMENT_EXTENSIONS
        and isinstance(http_status, int)
        and 200 <= http_status < 300
        and (kind == "file" or has_any_file_signature(row, repo_root, [b"\xd0\xcf\x11\xe0", b"PK"]))
    )


def artifact_extension(row: dict[str, Any]) -> str:
    extension = str(row.get("fileExtension") or "").lower().lstrip(".")
    if extension:
        return extension
    raw_suffix = Path(str(row.get("rawPath") or "")).suffix.lower().lstrip(".")
    if raw_suffix:
        return raw_suffix
    return Path(str(row.get("suggestedFilename") or "")).suffix.lower().lstrip(".")


def has_any_file_signature(row: dict[str, Any], repo_root: Path, signatures: list[bytes]) -> bool:
    raw_path = str(row.get("rawPath") or "")
    if not raw_path:
        return False
    path = repo_root / raw_path
    if not path.exists():
        return False
    max_len = max(len(signature) for signature in signatures)
    try:
        with path.open("rb") as file:
            prefix = file.read(max_len)
    except OSError:
        return False
    return any(prefix.startswith(signature) for signature in signatures)


def source_manifest_row(artifact: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    raw_path = str(artifact.get("rawPath") or "")
    raw_document_path = repo_root / raw_path
    extension = artifact_extension(artifact)
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_office_document_text_source",
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
                    extension,
                ]
            )
        ),
        "sourceCandidateUrl": artifact.get("sourceCandidateUrl"),
        "attachmentUrl": artifact.get("attachmentUrl"),
        "finalUrl": artifact.get("finalUrl"),
        "rawOfficeDocumentPath": raw_path,
        "rawOfficeDocumentSha256": artifact.get("sha256"),
        "rawOfficeDocumentBytes": artifact.get("bytes"),
        "fileExtension": extension,
        "suggestedFilename": artifact.get("suggestedFilename"),
        "contentType": artifact.get("contentType"),
        "sourceManifestPath": to_repo_relative(Path(str(artifact.get("_manifestPath"))), repo_root),
        "rawFileExists": raw_document_path.exists(),
        "sourceZipRawPath": artifact.get("sourceZipRawPath"),
        "sourceZipSha256": artifact.get("sourceZipSha256"),
        "zipEntryDecodedName": artifact.get("zipEntryDecodedName"),
        "zipEntryIndex": artifact.get("zipEntryIndex"),
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }


def extract_office_document_text(
    raw_path: Path,
    text_path: Path,
    repo_root: Path,
    source_row: dict[str, Any],
) -> dict[str, Any]:
    extension = str(source_row.get("fileExtension") or "").lower()
    if extension == "docx":
        return extract_docx_text(raw_path, text_path, repo_root)
    if extension == "pptx":
        return extract_pptx_text(raw_path, text_path, repo_root)
    if extension in {"doc", "ppt"}:
        return extract_legacy_office_text(raw_path, text_path, repo_root, extension)
    return failed_result("unsupported_extension", text_path, repo_root, extension)


def extract_docx_text(raw_path: Path, text_path: Path, repo_root: Path) -> dict[str, Any]:
    if not zipfile.is_zipfile(raw_path):
        return failed_result("not_zip_ooxml", text_path, repo_root, "DOCX file is not a ZIP package.")
    try:
        blocks: list[str] = []
        with zipfile.ZipFile(raw_path) as archive:
            xml_names = [
                name
                for name in archive.namelist()
                if name.startswith(
                    (
                        "word/document.xml",
                        "word/header",
                        "word/footer",
                        "word/footnotes",
                        "word/endnotes",
                    )
                )
                and name.lower().endswith(".xml")
            ]
            for name in sorted(xml_names):
                blocks.extend(paragraph_text_blocks(archive.read(name)))
        return extracted_result(
            text_path=text_path,
            repo_root=repo_root,
            text=normalize_extracted_text("\n".join(blocks)),
            container_kind="docx_ooxml",
            block_count=len(blocks),
            notes="",
        )
    except Exception as error:
        return failed_result("extract_failed", text_path, repo_root, f"{type(error).__name__}: {error}")


def extract_pptx_text(raw_path: Path, text_path: Path, repo_root: Path) -> dict[str, Any]:
    if not zipfile.is_zipfile(raw_path):
        return failed_result("not_zip_ooxml", text_path, repo_root, "PPTX file is not a ZIP package.")
    try:
        blocks: list[str] = []
        with zipfile.ZipFile(raw_path) as archive:
            slide_names = sorted(
                [
                    name
                    for name in archive.namelist()
                    if re.match(r"ppt/slides/slide\d+\.xml$", name)
                ],
                key=slide_sort_key,
            )
            note_names = sorted(
                [
                    name
                    for name in archive.namelist()
                    if re.match(r"ppt/notesSlides/notesSlide\d+\.xml$", name)
                ],
                key=slide_sort_key,
            )
            for name in slide_names + note_names:
                slide_blocks = paragraph_text_blocks(archive.read(name))
                if slide_blocks:
                    blocks.append(f"[{name}]")
                    blocks.extend(slide_blocks)
        return extracted_result(
            text_path=text_path,
            repo_root=repo_root,
            text=normalize_extracted_text("\n".join(blocks)),
            container_kind="pptx_ooxml",
            block_count=len(blocks),
            notes="",
        )
    except Exception as error:
        return failed_result("extract_failed", text_path, repo_root, f"{type(error).__name__}: {error}")


def extract_legacy_office_text(
    raw_path: Path,
    text_path: Path,
    repo_root: Path,
    extension: str,
) -> dict[str, Any]:
    textutil_path = shutil.which("textutil")
    if not textutil_path:
        return failed_result(
            "dependency_missing",
            text_path,
            repo_root,
            f"textutil is required to extract legacy .{extension} documents.",
        )
    try:
        completed = subprocess.run(
            [textutil_path, "-convert", "txt", "-stdout", str(raw_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return failed_result("extract_timeout", text_path, repo_root, "textutil timed out.")
    except Exception as error:
        return failed_result("extract_failed", text_path, repo_root, f"{type(error).__name__}: {error}")

    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace").strip()
        return failed_result("extract_failed", text_path, repo_root, stderr or "textutil failed.")

    text = completed.stdout.decode("utf-8", errors="replace")
    return extracted_result(
        text_path=text_path,
        repo_root=repo_root,
        text=normalize_extracted_text(text),
        container_kind=f"{extension}_textutil",
        block_count=0,
        notes="Extracted with macOS textutil.",
    )


def paragraph_text_blocks(xml_bytes: bytes) -> list[str]:
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError:
        return []

    blocks: list[str] = []
    paragraph_elements = [element for element in root.iter() if local_name(element.tag) == "p"]
    if not paragraph_elements:
        text = inline_text(root)
        return [text] if text else []

    for paragraph in paragraph_elements:
        text = inline_text(paragraph)
        if text:
            blocks.append(text)
    return blocks


def inline_text(element: ElementTree.Element) -> str:
    parts: list[str] = []
    for child in element.iter():
        name = local_name(child.tag)
        if name in {"t", "delText"} and child.text:
            parts.append(child.text)
        elif name == "tab":
            parts.append("\t")
        elif name in {"br", "cr"}:
            parts.append("\n")
    return normalize_inline_text("".join(parts))


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def slide_sort_key(name: str) -> tuple[str, int]:
    match = re.search(r"(\d+)\.xml$", name)
    return (name.rsplit("/", 1)[0], int(match.group(1)) if match else 0)


def extracted_result(
    *,
    text_path: Path,
    repo_root: Path,
    text: str,
    container_kind: str,
    block_count: int,
    notes: str,
) -> dict[str, Any]:
    write_text(text_path, text)
    non_whitespace_chars = len(re.sub(r"\s+", "", text))
    return {
        "textPath": to_repo_relative(text_path, repo_root),
        "textSha256": sha256_file(text_path),
        "officeDocumentContainerKind": container_kind,
        "blockCount": block_count,
        "textChars": len(text),
        "nonWhitespaceChars": non_whitespace_chars,
        "textPreview": preview_text(text),
        "extractionStatus": "extracted" if non_whitespace_chars >= 80 else "low_text",
        "notes": notes,
    }


def failed_result(status: str, text_path: Path, repo_root: Path, notes: str) -> dict[str, Any]:
    return {
        "textPath": to_repo_relative(text_path, repo_root),
        "textSha256": "",
        "officeDocumentContainerKind": "unknown",
        "blockCount": 0,
        "textChars": 0,
        "nonWhitespaceChars": 0,
        "textPreview": [],
        "extractionStatus": status,
        "notes": notes,
    }


def normalize_inline_text(value: str) -> str:
    value = value.replace("\u00a0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    return value.strip()


def normalize_extracted_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"[\u0000-\u001F\u007F-\u009F]+", " ", value)
    value = re.sub(r"[\uE000-\uF8FF]+", " ", value)
    lines = []
    for line in value.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def detect_document_role(text: str) -> str:
    normalized = text.lower()
    if re.search(r"경쟁률|competition|competition_rate", normalized):
        return "competition_rate_office_document"
    if re.search(
        r"입시결과|입학결과|전형결과|admission_result|합격|등록|충원|성적|환산|백분위|등급",
        normalized,
    ):
        return "admission_result_office_document"
    if re.search(
        r"모집요강|모집인원|전형계획|regular_admission_guide|recruitment_notice|정시|수능|전형방법|반영",
        normalized,
    ):
        return "recruitment_notice_office_document"
    if re.search(r"지원자격|확인서|추천서|서식|form|application", normalized):
        return "application_form_office_document"
    return "unknown"


def text_path_for(text_root: Path, sha256: str, sequence: int) -> Path:
    if sha256:
        return text_root / sha256[:2] / f"{sha256[:16]}.txt"
    return text_root / "unknown" / f"{sequence:04d}.txt"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def preview_text(text: str) -> list[str]:
    return [line for line in text.splitlines() if line][:8]


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


def write_attention_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "sourceLinkRole",
        "attachmentRole",
        "detectedDocumentRole",
        "fileExtension",
        "extractionStatus",
        "textChars",
        "nonWhitespaceChars",
        "rawOfficeDocumentPath",
        "textPath",
        "attachmentUrl",
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
        "low_text",
        "extract_failed",
        "extract_timeout",
        "dependency_missing",
        "missing_raw_file",
        "not_zip_ooxml",
        "unsupported_extension",
    }
    return [row for row in source_rows if row.get("extractionStatus") in statuses]


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u001F\u007F-\u009F]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counter = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def summarize(year: int, source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    unique_sha = {str(row.get("rawOfficeDocumentSha256") or "") for row in source_rows}
    extracted_unique = {
        str(row.get("rawOfficeDocumentSha256") or "")
        for row in source_rows
        if row.get("extractionStatus") in {"extracted", "low_text"}
    }
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "sourceOfficeDocuments": len(source_rows),
        "uniqueRawOfficeDocumentSha256": len(unique_sha),
        "extractedUniqueOfficeDocuments": len(extracted_unique),
        "reusedDuplicateSourceOfficeDocuments": sum(
            1 for row in source_rows if row.get("extractionStatus") == "reused_duplicate_sha256"
        ),
        "lowTextSourceOfficeDocuments": sum(
            1 for row in source_rows if row.get("extractionStatus") == "low_text"
        ),
        "failedSourceOfficeDocuments": sum(
            1
            for row in source_rows
            if row.get("extractionStatus")
            in {
                "extract_failed",
                "extract_timeout",
                "dependency_missing",
                "missing_raw_file",
                "not_zip_ooxml",
                "unsupported_extension",
            }
        ),
        "totalTextChars": sum(int(row.get("textChars") or 0) for row in source_rows),
        "totalNonWhitespaceChars": sum(
            int(row.get("nonWhitespaceChars") or 0) for row in source_rows
        ),
        "byFileExtension": count_by(source_rows, "fileExtension"),
        "byExtractionStatus": count_by(source_rows, "extractionStatus"),
        "byContainerKind": count_by(source_rows, "officeDocumentContainerKind"),
        "bySourceLinkRole": count_by(source_rows, "sourceLinkRole"),
        "byDetectedDocumentRole": count_by(source_rows, "detectedDocumentRole"),
        "notes": [
            "DOCX/PPTX text is extracted directly from OOXML packages.",
            "Legacy DOC/PPT extraction uses textutil when available; failures stay in the attention CSV.",
            "Extracted text is source-preserving and requires human verification before promotion.",
        ],
    }


if __name__ == "__main__":
    main()
