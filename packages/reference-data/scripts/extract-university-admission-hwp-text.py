#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import hashlib
import json
import re
import sys
import zipfile
import zlib
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
TEXT_RECORD_TAG = 67


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    maybe_add_local_python_tools(repo_root)
    manifest_paths = [resolve(repo_root, value) for value in args.manifest]
    output_dir = resolve(repo_root, args.output_dir)
    text_root = output_dir / "hwp-text" / str(args.year)
    text_root.mkdir(parents=True, exist_ok=True)

    artifact_rows = load_manifest_rows(manifest_paths)
    hwp_rows = [
        row
        for row in artifact_rows
        if is_http_ok_hwp(row, repo_root) and int(row.get("year") or 0) == args.year
    ]
    if args.limit is not None:
        hwp_rows = hwp_rows[: args.limit]

    extraction_cache: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []

    for index, artifact in enumerate(hwp_rows, start=1):
        source_row = source_manifest_row(artifact, repo_root)
        sha256 = str(source_row.get("rawHwpSha256") or "")
        raw_hwp_path = repo_root / str(source_row["rawHwpPath"])

        if not raw_hwp_path.exists():
            source_row.update(
                {
                    "extractionStatus": "missing_raw_file",
                    "notes": "Raw HWP path does not exist in the local artifact store.",
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
        extraction_result = extract_hwp_text(raw_hwp_path, text_path, repo_root)
        extraction_cache[sha256] = extraction_result
        source_row.update(extraction_result)
        source_rows.append(source_row)

        print(
            "university admission hwp text "
            f"index={index}/{len(hwp_rows)} "
            f"unvCd={source_row.get('unvCd')} "
            f"status={source_row.get('extractionStatus')} "
            f"chars={source_row.get('textChars')} "
            f"streams={source_row.get('streamCount')}"
        )

    summary = summarize(args.year, source_rows)
    write_jsonl(
        output_dir / f"university_admission_hwp_sources_manifest_{args.year}.jsonl",
        source_rows,
    )
    write_attention_csv(
        output_dir / f"university_admission_hwp_attention_candidates_{args.year}.csv",
        attention_rows(source_rows),
    )
    (output_dir / f"university_admission_hwp_text_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "university admission hwp text extraction complete. "
        f"sources={summary['sourceHwps']} unique={summary['uniqueRawHwpSha256']} "
        f"extractedUnique={summary['extractedUniqueHwps']} "
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


def maybe_add_local_python_tools(repo_root: Path) -> None:
    local_tools = repo_root / ".reference-data" / "tools" / "python"
    if local_tools.exists():
        sys.path.insert(0, str(local_tools))


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


def is_http_ok_hwp(row: dict[str, Any], repo_root: Path) -> bool:
    status = str(row.get("status") or "")
    kind = str(row.get("detectedKind") or "")
    extension = artifact_extension(row)
    http_status = row.get("httpStatus")
    return (
        status == "fetched"
        and extension in {"hwp", "hwpx"}
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
    raw_hwp_path = repo_root / raw_path
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_hwp_text_source",
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
        "rawHwpPath": raw_path,
        "rawHwpSha256": artifact.get("sha256"),
        "rawHwpBytes": artifact.get("bytes"),
        "fileExtension": artifact_extension(artifact),
        "suggestedFilename": artifact.get("suggestedFilename"),
        "contentType": artifact.get("contentType"),
        "sourceManifestPath": to_repo_relative(Path(str(artifact.get("_manifestPath"))), repo_root),
        "rawFileExists": raw_hwp_path.exists(),
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }


def extract_hwp_text(raw_path: Path, text_path: Path, repo_root: Path) -> dict[str, Any]:
    prefix = raw_path.read_bytes()[:16]
    if prefix.startswith(b"<") or prefix.lstrip().startswith(b"<"):
        return extract_html_like_text(raw_path, text_path, repo_root)
    if zipfile.is_zipfile(raw_path):
        return extract_hwpx_text(raw_path, text_path, repo_root)
    return extract_hwp5_ole_text(raw_path, text_path, repo_root)


def extract_hwp5_ole_text(raw_path: Path, text_path: Path, repo_root: Path) -> dict[str, Any]:
    try:
        import olefile  # type: ignore
    except ModuleNotFoundError as error:
        return failed_result(
            "dependency_missing",
            text_path,
            repo_root,
            f"olefile is required for HWP5 extraction: {error}",
        )

    if not olefile.isOleFile(str(raw_path)):
        return failed_result("not_ole_hwp", text_path, repo_root, "File is not an OLE HWP5 document.")

    try:
        ole = olefile.OleFileIO(str(raw_path))
        header = ole.openstream("FileHeader").read() if ole.exists("FileHeader") else b""
        flags = int.from_bytes(header[36:40], "little") if len(header) >= 40 else 0
        compressed = bool(flags & 0x01)
        encrypted = bool(flags & 0x02)
        distribution = bool(flags & 0x04)
        streams = [
            name
            for name in ole.listdir()
            if len(name) == 2
            and name[0] in {"BodyText", "ViewText"}
            and name[1].startswith("Section")
        ]
        stream_texts: list[str] = []
        failed_streams = 0
        for stream_name in sorted(streams, key=lambda item: (item[0], section_number(item[1]))):
            data = ole.openstream(stream_name).read()
            if compressed:
                try:
                    data = zlib.decompress(data, -15)
                except zlib.error:
                    failed_streams += 1
            stream_texts.extend(extract_text_records(data))

        text = normalize_extracted_text("\n".join(stream_texts))
        write_text(text_path, text)
        text_chars = len(text)
        non_whitespace_chars = len(re.sub(r"\s+", "", text))
        distribution_notice_only = "배포용 문서" in text and non_whitespace_chars < 800
        status = "extracted"
        if distribution_notice_only:
            status = "distribution_notice_only"
        elif non_whitespace_chars < 80:
            status = "low_text"

        return {
            "textPath": to_repo_relative(text_path, repo_root),
            "textSha256": sha256_file(text_path),
            "hwpContainerKind": "hwp5_ole",
            "hwpFlags": flags,
            "compressed": compressed,
            "encrypted": encrypted,
            "distribution": distribution,
            "streamCount": len(streams),
            "failedStreamCount": failed_streams,
            "textChars": text_chars,
            "nonWhitespaceChars": non_whitespace_chars,
            "textPreview": preview_text(text),
            "distributionNoticeOnly": distribution_notice_only,
            "extractionStatus": status,
            "notes": "" if failed_streams == 0 else "Some HWP streams could not be decompressed.",
        }
    except Exception as error:
        return failed_result("extract_failed", text_path, repo_root, f"{type(error).__name__}: {error}")


def extract_text_records(data: bytes) -> list[str]:
    texts: list[str] = []
    offset = 0
    while offset + 4 <= len(data):
        header = int.from_bytes(data[offset : offset + 4], "little")
        offset += 4
        tag = header & 0x3FF
        size = (header >> 20) & 0xFFF
        if size == 0xFFF:
            if offset + 4 > len(data):
                break
            size = int.from_bytes(data[offset : offset + 4], "little")
            offset += 4
        payload = data[offset : offset + size]
        offset += size
        if tag == TEXT_RECORD_TAG:
            texts.append(payload.decode("utf-16le", errors="ignore"))
    return texts


def extract_html_like_text(raw_path: Path, text_path: Path, repo_root: Path) -> dict[str, Any]:
    raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
    text = normalize_extracted_text(strip_html(raw_text))
    write_text(text_path, text)
    non_whitespace_chars = len(re.sub(r"\s+", "", text))
    return {
        "textPath": to_repo_relative(text_path, repo_root),
        "textSha256": sha256_file(text_path),
        "hwpContainerKind": "html_like",
        "hwpFlags": None,
        "compressed": False,
        "encrypted": False,
        "distribution": False,
        "streamCount": 0,
        "failedStreamCount": 0,
        "textChars": len(text),
        "nonWhitespaceChars": non_whitespace_chars,
        "textPreview": preview_text(text),
        "distributionNoticeOnly": False,
        "extractionStatus": "html_like_artifact" if non_whitespace_chars >= 80 else "low_text",
        "notes": "File extension is HWP, but the body is HTML-like text.",
    }


def extract_hwpx_text(raw_path: Path, text_path: Path, repo_root: Path) -> dict[str, Any]:
    texts: list[str] = []
    try:
        with zipfile.ZipFile(raw_path) as archive:
            names = [name for name in archive.namelist() if name.lower().endswith(".xml")]
            for name in names:
                try:
                    root = ElementTree.fromstring(archive.read(name))
                    xml_text = " ".join(text for text in root.itertext() if text)
                    if xml_text.strip():
                        texts.append(xml_text)
                except ElementTree.ParseError:
                    continue
        text = normalize_extracted_text("\n".join(texts))
        write_text(text_path, text)
        non_whitespace_chars = len(re.sub(r"\s+", "", text))
        return {
            "textPath": to_repo_relative(text_path, repo_root),
            "textSha256": sha256_file(text_path),
            "hwpContainerKind": "hwpx_zip",
            "hwpFlags": None,
            "compressed": False,
            "encrypted": False,
            "distribution": False,
            "streamCount": len(texts),
            "failedStreamCount": 0,
            "textChars": len(text),
            "nonWhitespaceChars": non_whitespace_chars,
            "textPreview": preview_text(text),
            "distributionNoticeOnly": False,
            "extractionStatus": "extracted" if non_whitespace_chars >= 80 else "low_text",
            "notes": "",
        }
    except Exception as error:
        return failed_result("extract_failed", text_path, repo_root, f"{type(error).__name__}: {error}")


def failed_result(status: str, text_path: Path, repo_root: Path, notes: str) -> dict[str, Any]:
    return {
        "textPath": to_repo_relative(text_path, repo_root),
        "textSha256": "",
        "hwpContainerKind": "unknown",
        "hwpFlags": None,
        "compressed": False,
        "encrypted": False,
        "distribution": False,
        "streamCount": 0,
        "failedStreamCount": 0,
        "textChars": 0,
        "nonWhitespaceChars": 0,
        "textPreview": [],
        "distributionNoticeOnly": False,
        "extractionStatus": status,
        "notes": notes,
    }


def section_number(value: str) -> int:
    match = re.search(r"(\d+)$", value)
    return int(match.group(1)) if match else 0


def strip_html(value: str) -> str:
    value = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", value)
    value = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</tr>", "\n", value)
    value = re.sub(r"(?is)<[^>]+>", " ", value)
    return html.unescape(value)


def normalize_extracted_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"[\u0000-\u001F\u007F-\u009F]+", " ", value)
    value = re.sub(r"[\u3400-\u4DBF\u4E00-\u9FFF]+", " ", value)
    value = re.sub(r"[\uE000-\uF8FF]+", " ", value)
    lines = []
    for line in value.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + ("\n" if text else ""), encoding="utf-8")


def preview_text(text: str) -> list[str]:
    return [line for line in text.splitlines() if line][:8]


def detect_document_role(text: str) -> str:
    normalized = text.lower()
    if re.search(r"경쟁률|competition|competition_rate", normalized):
        return "competition_rate_hwp"
    if re.search(
        r"입시결과|입학결과|전형결과|admission_result|합격|등록|충원|성적|환산|백분위|등급",
        normalized,
    ):
        return "admission_result_hwp"
    if re.search(
        r"모집요강|모집인원|전형계획|regular_admission_guide|recruitment_notice|정시|수능|전형방법|반영",
        normalized,
    ):
        return "recruitment_notice_hwp"
    return "unknown"


def text_path_for(text_root: Path, sha256: str, sequence: int) -> Path:
    if sha256:
        return text_root / sha256[:2] / f"{sha256[:16]}.txt"
    return text_root / "unknown" / f"{sequence:04d}.txt"


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
    import csv

    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "sourceLinkRole",
        "attachmentRole",
        "detectedDocumentRole",
        "extractionStatus",
        "distributionNoticeOnly",
        "textChars",
        "nonWhitespaceChars",
        "rawHwpPath",
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
        "distribution_notice_only",
        "html_like_artifact",
        "low_text",
        "extract_failed",
        "dependency_missing",
        "not_ole_hwp",
    }
    return [
        row
        for row in source_rows
        if row.get("extractionStatus") in statuses or row.get("distributionNoticeOnly")
    ]


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u001F\u007F-\u009F]+", " ", value).strip()
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
    unique_sha = {str(row.get("rawHwpSha256") or "") for row in source_rows}
    extracted_unique = {
        str(row.get("rawHwpSha256") or "")
        for row in source_rows
        if row.get("extractionStatus") in {"extracted", "html_like_artifact", "low_text"}
    }
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "sourceHwps": len(source_rows),
        "uniqueRawHwpSha256": len(unique_sha),
        "extractedUniqueHwps": len(extracted_unique),
        "reusedDuplicateSourceHwps": sum(
            1 for row in source_rows if row.get("extractionStatus") == "reused_duplicate_sha256"
        ),
        "distributionNoticeOnlySourceHwps": sum(
            1 for row in source_rows if row.get("distributionNoticeOnly")
        ),
        "lowTextSourceHwps": sum(1 for row in source_rows if row.get("extractionStatus") == "low_text"),
        "htmlLikeSourceHwps": sum(
            1 for row in source_rows if row.get("extractionStatus") == "html_like_artifact"
        ),
        "failedSourceHwps": sum(
            1 for row in source_rows if row.get("extractionStatus") in {"extract_failed", "dependency_missing", "not_ole_hwp"}
        ),
        "totalTextChars": sum(int(row.get("textChars") or 0) for row in source_rows),
        "totalNonWhitespaceChars": sum(
            int(row.get("nonWhitespaceChars") or 0) for row in source_rows
        ),
        "byExtractionStatus": count_by(source_rows, "extractionStatus"),
        "byContainerKind": count_by(source_rows, "hwpContainerKind"),
        "bySourceLinkRole": count_by(source_rows, "sourceLinkRole"),
        "byDetectedDocumentRole": count_by(source_rows, "detectedDocumentRole"),
        "notes": [
            "HWP5 text is extracted from BodyText/ViewText paragraph text records.",
            "CJK/private-use control noise from HWP binary controls is removed from the text candidate.",
            "distributionNoticeOnly=true usually means the source is a protected/distribution HWP requiring a dedicated viewer or OCR path.",
            "Extracted text is a source-preserving candidate and requires human verification before promotion to AdmissionRule or HistoricalOutcome.",
        ],
    }


if __name__ == "__main__":
    main()
