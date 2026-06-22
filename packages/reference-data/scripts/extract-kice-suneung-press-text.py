#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = "packages/reference-data/data/public/kice/kice_suneung_press_manifest.jsonl"
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/kice/extracted"
HWP_HELPER = "packages/reference-data/scripts/extract-university-admission-hwp-text.py"


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    manifest_path = resolve(repo_root, args.manifest)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    hwp_helper = load_helper(repo_root / HWP_HELPER, "pacer_university_hwp_text_helper_for_kice")
    if hasattr(hwp_helper, "maybe_add_local_python_tools"):
        hwp_helper.maybe_add_local_python_tools(repo_root)

    attachments = [
        row
        for row in load_jsonl(manifest_path)
        if row.get("status") == "downloaded"
        and row.get("fileKind") == "press_hwp"
        and suffix(row.get("fileTitle")) in {"hwp", "hwpx"}
    ]
    if args.limit is not None:
        attachments = attachments[: args.limit]

    extraction_cache: dict[str, dict[str, Any]] = {}
    source_rows: list[dict[str, Any]] = []

    for index, attachment in enumerate(attachments, start=1):
        source_row = source_manifest_row(attachment, repo_root)
        sha256 = str(source_row.get("rawAttachmentSha256") or "")
        raw_path = repo_root / str(source_row.get("rawAttachmentPath") or "")

        if not raw_path.exists():
            source_row.update(
                {
                    "extractionStatus": "missing_raw_file",
                    "notes": "Raw KICE press attachment path does not exist in the local artifact store.",
                }
            )
            source_rows.append(source_row)
            continue

        if sha256 in extraction_cache:
            source_row.update(extraction_cache[sha256])
            source_row["extractionStatus"] = "reused_duplicate_sha256"
            source_rows.append(source_row)
            continue

        text_path = text_path_for(output_dir, source_row, sha256, index)
        text_path.parent.mkdir(parents=True, exist_ok=True)
        result = hwp_helper.extract_hwp_text(raw_path, text_path, repo_root)
        result["documentKind"] = suffix(source_row.get("fileTitle")) or "hwp"
        extraction_cache[sha256] = result
        source_row.update(result)
        source_rows.append(source_row)

        print(
            "kice suneung press hwp text "
            f"index={index}/{len(attachments)} "
            f"academicYear={source_row.get('academicYear')} "
            f"examType={source_row.get('examType')} "
            f"status={source_row.get('extractionStatus')} "
            f"chars={source_row.get('textChars')}"
        )

    write_jsonl(output_dir / "kice_suneung_press_text_sources.jsonl", source_rows)
    write_csv(
        output_dir / "kice_suneung_press_low_text_or_attention.csv",
        attention_rows(source_rows),
    )
    summary = summarize(source_rows)
    (output_dir / "kice_suneung_press_text_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "kice suneung press hwp text extraction complete. "
        f"sources={summary['sourcePressHwps']} "
        f"unique={summary['uniqueRawAttachmentSha256']} "
        f"extracted={summary['extractedSources']} "
        f"textRoot={to_repo_relative(output_dir / 'hwp-text', repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int)
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
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def source_manifest_row(attachment: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    raw_path = str(attachment.get("rawPath") or "")
    return {
        "provider": "kice-suneung",
        "artifactType": "kice_suneung_press_text_source",
        "boardID": attachment.get("boardID"),
        "boardSeq": attachment.get("boardSeq"),
        "title": attachment.get("title"),
        "academicYear": attachment.get("academicYear"),
        "examType": attachment.get("examType"),
        "postedDate": attachment.get("postedDate"),
        "fileSeq": attachment.get("fileSeq"),
        "fileTitle": attachment.get("fileTitle"),
        "fileKind": attachment.get("fileKind"),
        "sourceUrl": attachment.get("sourceUrl"),
        "viewUrl": attachment.get("viewUrl"),
        "rawAttachmentPath": raw_path,
        "rawAttachmentSha256": attachment.get("sha256"),
        "rawAttachmentBytes": attachment.get("bytes"),
        "contentType": attachment.get("contentType"),
        "rawFileExists": (repo_root / raw_path).exists(),
        "sourceManifestPath": DEFAULT_MANIFEST,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }


def text_path_for(output_dir: Path, source: dict[str, Any], sha256: str, sequence: int) -> Path:
    year = str(source.get("academicYear") or "unknown")
    exam_type = str(source.get("examType") or "unknown")
    if sha256:
        return output_dir / "hwp-text" / year / exam_type / sha256[:2] / f"{sha256[:16]}.txt"
    return output_dir / "hwp-text" / year / exam_type / "unknown" / f"{sequence:04d}.txt"


def suffix(value: Any) -> str:
    text = str(value or "")
    if "." not in text:
        return ""
    return text.rsplit(".", 1)[-1].lower()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "academicYear",
        "examType",
        "boardSeq",
        "title",
        "postedDate",
        "fileTitle",
        "extractionStatus",
        "documentKind",
        "hwpContainerKind",
        "distributionNoticeOnly",
        "streamCount",
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
        "distribution_notice_only",
        "html_like_artifact",
        "low_text",
        "extract_failed",
        "dependency_missing",
        "not_ole_hwp",
        "missing_raw_file",
    }
    return [
        row
        for row in source_rows
        if row.get("extractionStatus") in statuses or row.get("distributionNoticeOnly")
    ]


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    unique_sha = {str(row.get("rawAttachmentSha256") or "") for row in rows}
    extracted_statuses = {"extracted", "html_like_artifact", "low_text", "reused_duplicate_sha256"}
    return {
        "provider": "kice-suneung",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourcePressHwps": len(rows),
        "uniqueRawAttachmentSha256": len(unique_sha),
        "extractedSources": sum(1 for row in rows if row.get("extractionStatus") in extracted_statuses),
        "failedSources": sum(
            1
            for row in rows
            if row.get("extractionStatus")
            in {"extract_failed", "dependency_missing", "not_ole_hwp", "missing_raw_file"}
        ),
        "distributionNoticeOnlySources": sum(1 for row in rows if row.get("distributionNoticeOnly")),
        "lowTextSources": sum(1 for row in rows if row.get("extractionStatus") == "low_text"),
        "totalTextChars": sum(int(row.get("textChars") or 0) for row in rows),
        "totalNonWhitespaceChars": sum(int(row.get("nonWhitespaceChars") or 0) for row in rows),
        "byAcademicYear": count_by(rows, "academicYear"),
        "byExamType": count_by(rows, "examType"),
        "byExtractionStatus": count_by(rows, "extractionStatus"),
        "byContainerKind": count_by(rows, "hwpContainerKind"),
        "notes": [
            "KICE press HWP text is extracted from official Suneung press attachments.",
            "The extracted text is source-preserving evidence for official score-reference facts.",
            "Numeric grade-cut and distribution tables remain in workbook candidate CSVs; press text adds prose/table context for review.",
        ],
    }


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counter = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u001F\u007F-\u009F]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


def to_repo_relative(path: Path, repo_root: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(repo_root))
    except ValueError:
        return str(resolved)


if __name__ == "__main__":
    main()
