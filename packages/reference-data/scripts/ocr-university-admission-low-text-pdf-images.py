#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import concurrent.futures as futures
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
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


DEFAULT_PAGE_IMAGE_MANIFEST = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_low_text_pdf_page_images_2027.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"

OCR_LANG = "kor+eng"
OCR_PSM = "6"

# --- GLM-OCR backend (z.ai) -------------------------------------------------
GLM_DEFAULT_MODEL = "glm-ocr"
_GLM_CLIENT: Any = None


def load_dotenv_keys(repo_root: Path, keys: tuple[str, ...] = ("ZAI_API_KEY",)) -> None:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key in keys and key not in os.environ:
            os.environ[key] = val


GLM_IMAGE_MAX_BYTES = 10 * 1024 * 1024
GLM_PDF_MAX_BYTES = 50 * 1024 * 1024


def glm_sniff_mime(raw: bytes) -> str:
    if raw.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"GIF87a") or raw.startswith(b"GIF89a"):
        return "image/gif"
    if raw.startswith(b"BM"):
        return "image/bmp"
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw.startswith(b"%PDF"):
        return "application/pdf"
    return ""


def glm_to_data_uri(path: Path) -> str:
    raw = path.read_bytes()
    mime = glm_sniff_mime(raw)
    if not mime:
        raise RuntimeError("지원 형식(JPG/PNG/PDF 등)이 아님")
    limit = GLM_PDF_MAX_BYTES if mime == "application/pdf" else GLM_IMAGE_MAX_BYTES
    if len(raw) > limit:
        raise RuntimeError(f"glm-ocr 크기 초과({len(raw)} bytes > {limit})")
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


def get_glm_client() -> Any:
    global _GLM_CLIENT
    if _GLM_CLIENT is None:
        api_key = os.environ.get("ZAI_API_KEY")
        if not api_key:
            raise RuntimeError("ZAI_API_KEY 가 없습니다(.env 또는 환경변수).")
        try:
            from zai import ZaiClient
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("zai-sdk 미설치. `pip install zai-sdk` 후 재시도.") from exc
        _GLM_CLIENT = ZaiClient(api_key=api_key)
    return _GLM_CLIENT


def _response_to_dict(resp: Any) -> Any:
    for attr in ("model_dump", "dict", "to_dict"):
        fn = getattr(resp, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    if hasattr(resp, "__dict__"):
        return {k: v for k, v in vars(resp).items()}
    return resp


def extract_glm_text(resp: Any) -> str:
    data = _response_to_dict(resp)
    # glm-ocr 본문은 top-level 'md_results'(HTML 표 포함 마크다운)에 담긴다.
    if isinstance(data, dict):
        for key in ("md_results", "md_result", "markdown_results", "markdown"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
    preferred = ("md_results", "markdown", "md", "text", "content", "ocr_text", "result", "ocr")
    best: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            return
        if isinstance(node, dict):
            for key in preferred:
                val = node.get(key)
                if isinstance(val, str) and val.strip():
                    best.append(val)
            for val in node.values():
                walk(val)
        elif isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(data)
    if best:
        best.sort(key=len, reverse=True)
        return best[0]
    return ""
# ---------------------------------------------------------------------------

ROLE_RULES = [
    (
        "admission_result_ocr_page",
        "HistoricalOutcome",
        [
            r"합격자",
            r"등록자",
            r"최종\s*등록",
            r"입시\s*결과",
            r"경쟁률",
            r"충원",
            r"환산",
            r"백분위",
            r"등급",
        ],
    ),
    (
        "competition_rate_ocr_page",
        "HistoricalOutcome",
        [r"경쟁률", r"모집\s*인원", r"지원\s*인원", r"지원자", r"실질\s*경쟁률"],
    ),
    (
        "csat_rule_ocr_page",
        "AdmissionRule",
        [r"수능", r"대학수학능력", r"반영", r"표준점수", r"백분위", r"탐구", r"영어", r"한국사", r"영역"],
    ),
    (
        "screening_method_ocr_page",
        "AdmissionRule",
        [r"전형\s*방법", r"선발", r"학생부", r"면접", r"실기", r"논술", r"서류", r"평가"],
    ),
    (
        "schedule_ocr_page",
        "AdmissionSchedule",
        [r"원서\s*접수", r"합격자\s*발표", r"등록", r"추가\s*합격", r"전형일", r"일정"],
    ),
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    page_manifest_path = resolve(repo_root, args.page_image_manifest)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    text_root = output_dir / "low-text-pdf-page-ocr-text" / str(args.year)
    text_root.mkdir(parents=True, exist_ok=True)

    backend = args.ocr_backend
    tesseract = args.tesseract or shutil.which("tesseract")
    if backend == "glm-ocr":
        load_dotenv_keys(repo_root)
        get_glm_client()
    elif not tesseract:
        raise RuntimeError("tesseract is required for low-text PDF page OCR.")

    page_rows = [
        row
        for row in load_jsonl(page_manifest_path)
        if int(row.get("year") or 0) == args.year and is_ocr_candidate(row)
    ]
    if args.limit is not None:
        page_rows = page_rows[: args.limit]

    ocr_rows = run_ocr_jobs(
        page_rows=page_rows,
        repo_root=repo_root,
        text_root=text_root,
        tesseract=tesseract,
        backend=backend,
        glm_model=args.glm_model,
        force=args.force,
        timeout_seconds=args.timeout_seconds,
        jobs=max(1, args.jobs),
    )
    evidence_rows = [
        build_evidence_row(row)
        for row in ocr_rows
        if row["ocrStatus"] in {"ocr_extracted", "reused_existing_ocr"}
    ]

    suffix = f"_{args.year}"
    write_jsonl(output_dir / f"university_admission_low_text_pdf_page_ocr_manifest{suffix}.jsonl", ocr_rows)
    write_csv_index(output_dir / f"university_admission_low_text_pdf_page_ocr_index{suffix}.csv", ocr_rows)
    write_jsonl(
        output_dir / f"university_admission_low_text_pdf_page_ocr_evidence_index{suffix}.jsonl",
        evidence_rows,
    )
    write_csv_evidence_index(
        output_dir / f"university_admission_low_text_pdf_page_ocr_evidence_index{suffix}.csv",
        evidence_rows,
    )
    summary = summarize(args.year, page_rows, ocr_rows, evidence_rows, tesseract)
    (output_dir / f"university_admission_low_text_pdf_page_ocr_summary{suffix}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "university admission low-text pdf page ocr complete. "
        f"candidates={summary['ocrCandidates']} "
        f"ocrRows={summary['ocrRows']} "
        f"extracted={summary['ocrExtracted']} "
        f"evidenceRows={summary['evidenceRows']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--page-image-manifest", default=DEFAULT_PAGE_IMAGE_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tesseract")
    parser.add_argument("--ocr-backend", choices=["tesseract", "glm-ocr"], default="tesseract")
    parser.add_argument("--glm-model", default=GLM_DEFAULT_MODEL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--jobs", type=int, default=1)
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
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def is_ocr_candidate(row: dict[str, Any]) -> bool:
    return (
        str(row.get("status") or "") == "ocr_or_visual_review_candidate"
        and str(row.get("pageImagePath") or "")
        and str(row.get("pageImageSha256") or "")
    )


def run_ocr_jobs(
    *,
    page_rows: list[dict[str, Any]],
    repo_root: Path,
    text_root: Path,
    tesseract: str,
    backend: str = "tesseract",
    glm_model: str = GLM_DEFAULT_MODEL,
    force: bool,
    timeout_seconds: int,
    jobs: int,
) -> list[dict[str, Any]]:
    def process(index_and_page: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        index, page = index_and_page
        return (
            index,
            build_ocr_row(
                page=page,
                repo_root=repo_root,
                text_root=text_root,
                tesseract=tesseract,
                backend=backend,
                glm_model=glm_model,
                force=force,
                timeout_seconds=timeout_seconds,
            ),
        )

    indexed_pages = list(enumerate(page_rows, start=1))
    completed: dict[int, dict[str, Any]] = {}
    if jobs == 1:
        for item in indexed_pages:
            index, ocr_row = process(item)
            completed[index] = ocr_row
            print_ocr_progress(index, len(page_rows), ocr_row)
    else:
        with futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            future_map = {executor.submit(process, item): item[0] for item in indexed_pages}
            for future in futures.as_completed(future_map):
                index, ocr_row = future.result()
                completed[index] = ocr_row
                print_ocr_progress(index, len(page_rows), ocr_row)
    return [completed[index] for index in sorted(completed)]


def print_ocr_progress(index: int, total: int, ocr_row: dict[str, Any]) -> None:
    print(
        "university admission low-text pdf page ocr "
        f"index={index}/{total} "
        f"status={ocr_row['ocrStatus']} "
        f"chars={ocr_row['textChars']} "
        f"role={ocr_row['detectedOcrRole']} "
        f"unvCd={ocr_row.get('unvCd')} "
        f"page={ocr_row.get('pageNumber')}"
    )


def build_ocr_row(
    *,
    page: dict[str, Any],
    repo_root: Path,
    text_root: Path,
    tesseract: str,
    backend: str = "tesseract",
    glm_model: str = GLM_DEFAULT_MODEL,
    force: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    page_image_path = repo_root / str(page.get("pageImagePath") or "")
    page_image_sha = str(page.get("pageImageSha256") or "")
    text_path = text_path_for(
        text_root=text_root,
        page_image_sha=page_image_sha,
        unv_cd=str(page.get("unvCd") or "unknown"),
        page_number=int(page.get("pageNumber") or 0),
    )
    text_path.parent.mkdir(parents=True, exist_ok=True)
    common = {
        "provider": "university-admission-office",
        "artifactType": "admission_low_text_pdf_page_ocr",
        "year": page.get("year"),
        "unvCd": page.get("unvCd"),
        "universityName": page.get("universityName"),
        "campus": page.get("campus"),
        "sourceLinkRole": page.get("sourceLinkRole"),
        "attachmentRole": page.get("attachmentRole"),
        "detectedDocumentRole": page.get("detectedDocumentRole"),
        "pageNumber": page.get("pageNumber"),
        "pageImagePath": page.get("pageImagePath"),
        "pageImageSha256": page_image_sha,
        "pageImageBytes": page.get("pageImageBytes"),
        "renderDpi": page.get("renderDpi"),
        "sourceCandidateUrl": page.get("sourceCandidateUrl"),
        "attachmentUrl": page.get("attachmentUrl"),
        "rawPdfPath": page.get("rawPdfPath"),
        "rawPdfSha256": page.get("rawPdfSha256"),
        "pdfTextPath": page.get("textPath"),
        "ocrEngine": "glm-ocr" if backend == "glm-ocr" else "tesseract",
        "ocrModel": glm_model if backend == "glm-ocr" else None,
        "ocrLang": glm_model if backend == "glm-ocr" else OCR_LANG,
        "ocrPsm": None if backend == "glm-ocr" else OCR_PSM,
        "textPath": to_repo_relative(text_path, repo_root),
        "ocrAt": datetime.now(timezone.utc).isoformat(),
    }

    if not page_image_path.exists():
        return row_with_text_analysis(
            {
                **common,
                "ocrStatus": "missing_page_image",
                "textSha256": "",
                "tesseractReturnCode": None,
                "stderrPreview": "Page image path does not exist.",
            },
            "",
        )

    if text_path.exists() and not force:
        text = text_path.read_text(encoding="utf-8", errors="replace")
        return row_with_text_analysis(
            {
                **common,
                "ocrStatus": "reused_existing_ocr",
                "textSha256": sha256_file(text_path),
                "tesseractReturnCode": 0,
                "stderrPreview": "",
            },
            text,
        )

    if backend == "glm-ocr":
        try:
            client = get_glm_client()
            resp = client.layout_parsing.create(model=glm_model, file=glm_to_data_uri(page_image_path))
            try:
                (text_path.with_suffix(text_path.suffix + ".glm.json")).write_text(
                    json.dumps(_response_to_dict(resp), ensure_ascii=False, indent=2, default=str)
                    + "\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            text = normalize_ocr_text(extract_glm_text(resp))
            text_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
            return row_with_text_analysis(
                {
                    **common,
                    "ocrStatus": "ocr_extracted" if text else "ocr_failed",
                    "textSha256": sha256_file(text_path),
                    "tesseractReturnCode": 0 if text else None,
                    "stderrPreview": "" if text else "glm-ocr returned no text",
                },
                text,
            )
        except Exception as error:
            return row_with_text_analysis(
                {
                    **common,
                    "ocrStatus": "ocr_failed",
                    "textSha256": "",
                    "tesseractReturnCode": None,
                    "stderrPreview": f"glm-ocr error: {error}"[:400],
                },
                "",
            )

    try:
        result = subprocess.run(
            [tesseract, str(page_image_path), "stdout", "-l", OCR_LANG, "--psm", OCR_PSM],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
        text = normalize_ocr_text(result.stdout)
        text_path.write_text(text + ("\n" if text else ""), encoding="utf-8")
        return row_with_text_analysis(
            {
                **common,
                "ocrStatus": "ocr_extracted" if result.returncode == 0 else "ocr_failed",
                "textSha256": sha256_file(text_path),
                "tesseractReturnCode": result.returncode,
                "stderrPreview": normalize_space(result.stderr)[:400],
            },
            text,
        )
    except subprocess.TimeoutExpired as error:
        return row_with_text_analysis(
            {
                **common,
                "ocrStatus": "ocr_timeout",
                "textSha256": "",
                "tesseractReturnCode": None,
                "stderrPreview": str(error)[:400],
            },
            "",
        )


def row_with_text_analysis(row: dict[str, Any], text: str) -> dict[str, Any]:
    clean_text = normalize_ocr_text(text)
    non_ws = re.sub(r"\s+", "", clean_text)
    role, target, matched = detect_ocr_role(
        clean_text,
        str(row.get("sourceLinkRole") or ""),
        str(row.get("detectedDocumentRole") or ""),
    )
    row.update(
        {
            "textChars": len(clean_text),
            "nonWhitespaceChars": len(non_ws),
            "lineCount": len([line for line in clean_text.splitlines() if line.strip()]),
            "ocrTextPreview": clean_text[:1000],
            "detectedOcrRole": role,
            "targetEntity": target,
            "matchedKeywords": matched,
            "priorityScore": priority_score(row, role, matched, len(non_ws)),
            "needsHumanVerification": True,
        }
    )
    return sanitize_json_value(row)


def detect_ocr_role(text: str, source_link_role: str, document_role: str) -> tuple[str, str, list[str]]:
    matches_by_role: list[tuple[int, str, str, list[str]]] = []
    for role, target, patterns in ROLE_RULES:
        matched = sorted({pattern for pattern in patterns if re.search(pattern, text)})
        if matched:
            matches_by_role.append((len(matched), role, target, matched))
    if not matches_by_role:
        if source_link_role == "admission_result" or document_role == "admission_result_pdf":
            return ("admission_result_ocr_page", "HistoricalOutcome", ["source_link_role"])
        if source_link_role == "competition_rate" or document_role == "competition_rate_pdf":
            return ("competition_rate_ocr_page", "HistoricalOutcome", ["source_link_role"])
        if document_role == "recruitment_notice_pdf":
            return ("low_signal_ocr_page", "OCRReviewQueue", [])
        return ("low_signal_ocr_page", "OCRReviewQueue", [])
    _, role, target, matched = sorted(matches_by_role, key=lambda item: (-item[0], item[1]))[0]
    return role, target, matched


def priority_score(row: dict[str, Any], role: str, matched: list[str], non_ws_chars: int) -> int:
    score = 0
    score += min(42, len(matched) * 6)
    score += min(26, non_ws_chars // 60)
    score += 8 if int(row.get("pageImageBytes") or 0) >= 120_000 else 0
    if str(row.get("sourceLinkRole") or "") == "admission_result":
        score += 18
    elif str(row.get("sourceLinkRole") or "") == "competition_rate":
        score += 16
    elif str(row.get("sourceLinkRole") or "") == "recruitment_notice":
        score += 8
    if role in {"admission_result_ocr_page", "competition_rate_ocr_page"}:
        score += 18
    elif role in {"csat_rule_ocr_page", "screening_method_ocr_page"}:
        score += 16
    elif role == "schedule_ocr_page":
        score += 10
    elif role == "low_signal_ocr_page":
        score -= 8
    return max(0, min(100, score))


def build_evidence_row(ocr_row: dict[str, Any]) -> dict[str, Any]:
    text = str(ocr_row.get("ocrTextPreview") or "")
    evidence_key = "|".join(
        [
            str(ocr_row.get("pageImageSha256") or ""),
            str(ocr_row.get("detectedOcrRole") or ""),
            str(ocr_row.get("textSha256") or ""),
        ]
    )
    return sanitize_json_value(
        {
            "provider": "university-admission-office",
            "artifactType": "admission_low_text_pdf_page_ocr_evidence_candidate",
            "year": ocr_row.get("year"),
            "unvCd": ocr_row.get("unvCd"),
            "universityName": ocr_row.get("universityName"),
            "campus": ocr_row.get("campus"),
            "evidenceType": "pdf_page_ocr",
            "evidenceRole": ocr_row.get("detectedOcrRole"),
            "evidenceTarget": ocr_row.get("targetEntity"),
            "reviewStatus": "needs_human_verification",
            "priorityScore": ocr_row.get("priorityScore"),
            "sourceDocumentKind": "pdf_page_image_ocr",
            "sourceLinkRole": ocr_row.get("sourceLinkRole"),
            "attachmentRole": ocr_row.get("attachmentRole"),
            "detectedDocumentRole": ocr_row.get("detectedDocumentRole"),
            "sourceCandidateUrl": ocr_row.get("sourceCandidateUrl"),
            "attachmentUrl": ocr_row.get("attachmentUrl"),
            "sourcePath": ocr_row.get("textPath"),
            "rawPath": ocr_row.get("rawPdfPath"),
            "sourceSha256": ocr_row.get("textSha256"),
            "evidenceSha256": hashlib.sha256(evidence_key.encode("utf-8")).hexdigest(),
            "textPreview": normalize_space(text)[:300],
            "text": text,
            "matchedKeywords": ocr_row.get("matchedKeywords"),
            "sourceSpecific": {
                "pageNumber": ocr_row.get("pageNumber"),
                "pageImagePath": ocr_row.get("pageImagePath"),
                "pageImageSha256": ocr_row.get("pageImageSha256"),
                "pageImageBytes": ocr_row.get("pageImageBytes"),
                "renderDpi": ocr_row.get("renderDpi"),
                "rawPdfSha256": ocr_row.get("rawPdfSha256"),
                "ocrLang": ocr_row.get("ocrLang"),
                "ocrPsm": ocr_row.get("ocrPsm"),
                "textChars": ocr_row.get("textChars"),
                "nonWhitespaceChars": ocr_row.get("nonWhitespaceChars"),
            },
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
    )


def text_path_for(text_root: Path, page_image_sha: str, unv_cd: str, page_number: int) -> Path:
    folder = page_image_sha[:2] if page_image_sha else "unknown"
    suffix = page_image_sha[:16] if page_image_sha else "unknown"
    safe_unv_cd = safe_filename(unv_cd)
    return text_root / folder / f"{safe_unv_cd}_page-{page_number:04d}_{suffix}.txt"


def normalize_ocr_text(value: str) -> str:
    value = re.sub(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f]+", " ", value)
    lines = []
    for line in value.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines).strip()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "pageNumber",
        "ocrStatus",
        "detectedOcrRole",
        "targetEntity",
        "priorityScore",
        "textChars",
        "nonWhitespaceChars",
        "sourceLinkRole",
        "detectedDocumentRole",
        "matchedKeywords",
        "ocrTextPreview",
        "textPath",
        "pageImagePath",
        "rawPdfPath",
        "attachmentUrl",
    ]
    write_dict_csv(path, headers, rows)


def write_csv_evidence_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "evidenceRole",
        "evidenceTarget",
        "priorityScore",
        "reviewStatus",
        "sourceLinkRole",
        "detectedDocumentRole",
        "textPreview",
        "sourcePath",
        "rawPath",
        "evidenceSha256",
    ]
    write_dict_csv(path, headers, rows)


def write_dict_csv(path: Path, headers: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({header: csv_value(row.get(header)) for header in headers})


def csv_value(value: Any) -> Any:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return "" if value is None else value


def summarize(
    year: int,
    page_rows: list[dict[str, Any]],
    ocr_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    tesseract: str,
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "tesseractPath": tesseract,
        "ocrLang": OCR_LANG,
        "ocrPsm": OCR_PSM,
        "ocrCandidates": len(page_rows),
        "ocrRows": len(ocr_rows),
        "ocrExtracted": sum(
            1 for row in ocr_rows if row.get("ocrStatus") in {"ocr_extracted", "reused_existing_ocr"}
        ),
        "ocrFailed": sum(1 for row in ocr_rows if row.get("ocrStatus") == "ocr_failed"),
        "ocrTimeout": sum(1 for row in ocr_rows if row.get("ocrStatus") == "ocr_timeout"),
        "missingPageImages": sum(1 for row in ocr_rows if row.get("ocrStatus") == "missing_page_image"),
        "rowsWithText": sum(1 for row in ocr_rows if int(row.get("nonWhitespaceChars") or 0) > 0),
        "rowsWithKeywords": sum(1 for row in ocr_rows if row.get("detectedOcrRole") != "low_signal_ocr_page"),
        "evidenceRows": len(evidence_rows),
        "totalTextChars": sum(int(row.get("textChars") or 0) for row in ocr_rows),
        "totalNonWhitespaceChars": sum(int(row.get("nonWhitespaceChars") or 0) for row in ocr_rows),
        "byOcrStatus": count_by(ocr_rows, "ocrStatus"),
        "byDetectedOcrRole": count_by(ocr_rows, "detectedOcrRole"),
        "byTargetEntity": count_by(ocr_rows, "targetEntity"),
        "bySourceLinkRole": count_by(ocr_rows, "sourceLinkRole"),
        "byDetectedDocumentRole": count_by(ocr_rows, "detectedDocumentRole"),
        "notes": [
            "OCR text is generated from rendered low-text PDF page images using Tesseract kor+eng.",
            "Rows are evidence candidates only and require human verification before promotion.",
            "Keyword roles are heuristic labels for reviewer triage, not production classifications.",
        ],
    }


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counter = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w.()\-가-힣]+", "_", value)
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned.strip("_") or "unknown"


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


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    main()
