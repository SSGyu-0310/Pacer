#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import concurrent.futures as futures
import csv
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST_GLOB = (
    "packages/reference-data/data/public/university-admission-sites/"
    "university_admission_attachment_artifact_manifest_*.jsonl"
)
DEFAULT_OUTPUT_DIR = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-image-attachment-ocr-20260608"
)
DEFAULT_YEARS = "2021,2022,2023,2024,2025,2026,2027"

OCR_LANG = "kor+eng"
OCR_PSM = "6"

# --- GLM-OCR backend (z.ai) -------------------------------------------------
GLM_DEFAULT_MODEL = "glm-ocr"
_GLM_CLIENT: Any = None


def load_dotenv_keys(repo_root: Path, keys: tuple[str, ...] = ("ZAI_API_KEY",)) -> None:
    """의존성 없이 .env에서 지정 키만 읽어 os.environ에 올린다(이미 있으면 보존)."""
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


GLM_IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 이미지 ≤ 10MB
GLM_PDF_MAX_BYTES = 50 * 1024 * 1024     # PDF ≤ 50MB


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
    """raw 저장소가 확장자 없는 .bin 이라, magic 바이트로 MIME을 정해 data URI로 보낸다."""
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
    """glm-ocr 응답에서 OCR 텍스트(마크다운)를 방어적으로 추출한다.
    응답 스키마가 제공사 버전마다 달라질 수 있어, 우선순위 키를 재귀 탐색하고
    페이지 배열이면 이어붙인다."""
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
        # 가장 긴 단일 문자열을 우선 채택(페이지 합본이면 그게 보통 본문)
        best.sort(key=len, reverse=True)
        return best[0]
    return ""
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "webp"}
IMAGE_EXTENSION_PATTERN = re.compile(r"\.(png|jpe?g|gif|bmp|webp)(?:$|[?#])", re.I)

ROLE_RULES = [
    (
        "schedule_image_ocr",
        "AdmissionSchedule",
        [
            r"원서\s*접수",
            r"합격자\s*발표",
            r"추가\s*합격",
            r"전형일",
            r"등록",
            r"일정",
        ],
    ),
    (
        "competition_rate_image_ocr",
        "HistoricalOutcome",
        [
            r"경쟁\s*[률율를]",
            r"지원\s*현황",
            r"지원\s*인원",
            r"지원자",
            r"모집\s*인원",
            r"\d+\s*[:：]\s*\d+",
        ],
    ),
    (
        "admission_result_image_ocr",
        "HistoricalOutcome",
        [
            r"입시\s*결과",
            r"전형\s*결과",
            r"합격자",
            r"등록자",
            r"최종\s*등록",
            r"충원",
            r"예비",
            r"환산",
            r"백분위",
            r"등급",
            r"컷",
        ],
    ),
    (
        "csat_rule_image_ocr",
        "AdmissionRule",
        [
            r"수능",
            r"대학수학능력",
            r"반영",
            r"표준점수",
            r"백분위",
            r"탐구",
            r"영어",
            r"한국사",
            r"영역",
        ],
    ),
    (
        "screening_method_image_ocr",
        "AdmissionRule",
        [
            r"전형\s*방법",
            r"선발",
            r"학생부",
            r"면접",
            r"실기",
            r"논술",
            r"서류",
            r"평가",
        ],
    ),
    (
        "recruitment_quota_image_ocr",
        "AdmissionRule",
        [
            r"모집\s*단위",
            r"모집\s*학과",
            r"모집\s*인원",
            r"정원\s*내",
            r"정원\s*외",
            r"전형별\s*모집",
        ],
    ),
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    text_root = output_dir / "image-attachment-ocr-text"
    text_root.mkdir(parents=True, exist_ok=True)

    backend = args.ocr_backend
    tesseract = args.tesseract or shutil.which("tesseract")
    if backend == "glm-ocr":
        load_dotenv_keys(repo_root)
        get_glm_client()  # 키/SDK 사전 점검 (없으면 즉시 명확히 실패)
    elif not tesseract:
        raise RuntimeError("tesseract is required for university admission image OCR.")

    years = parse_years(args.years, args.year)
    input_paths = resolve_globs(repo_root, args.manifest_glob)
    if not input_paths:
        raise RuntimeError(f"No attachment artifact manifests matched: {args.manifest_glob}")

    manifest_inputs: list[dict[str, Any]] = []
    rows_by_year: dict[int, list[dict[str, Any]]] = defaultdict(list)
    scanned_rows = 0
    for input_path in input_paths:
        manifest_rows = 0
        image_rows = 0
        for row in read_jsonl(input_path):
            manifest_rows += 1
            scanned_rows += 1
            row_year = int_or_none(row.get("year"))
            if row_year not in years:
                continue
            image_kind = detect_image_kind(row, repo_root)
            if not image_kind:
                continue
            if args.source_link_role and str(row.get("sourceLinkRole") or "") not in args.source_link_role:
                continue
            row = dict(row)
            row["detectedImageKind"] = image_kind
            row["manifestPath"] = to_repo_relative(input_path, repo_root)
            rows_by_year[row_year].append(row)
            image_rows += 1
        manifest_inputs.append(
            {
                "path": to_repo_relative(input_path, repo_root),
                "rows": manifest_rows,
                "imageCandidateRows": image_rows,
                "sha256": sha256_file(input_path),
            }
        )

    all_ocr_rows: list[dict[str, Any]] = []
    all_evidence_rows: list[dict[str, Any]] = []
    for year in sorted(years):
        image_rows = dedupe_rows(rows_by_year.get(year, []))
        if args.limit is not None:
            image_rows = image_rows[: args.limit]
        ocr_rows = run_ocr_jobs(
            image_rows=image_rows,
            repo_root=repo_root,
            text_root=text_root / str(year),
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
            if row.get("ocrStatus") in {"ocr_extracted", "reused_existing_ocr"}
        ]
        write_year_outputs(output_dir, year, image_rows, ocr_rows, evidence_rows)
        write_summary(
            output_dir=output_dir,
            year=year,
            scanned_rows=scanned_rows,
            manifest_inputs=manifest_inputs,
            image_rows=image_rows,
            ocr_rows=ocr_rows,
            evidence_rows=evidence_rows,
            tesseract=tesseract,
        )
        all_ocr_rows.extend(ocr_rows)
        all_evidence_rows.extend(evidence_rows)

    combined_summary = summarize(
        year=None,
        scanned_rows=scanned_rows,
        manifest_inputs=manifest_inputs,
        image_rows=[row for rows in rows_by_year.values() for row in dedupe_rows(rows)],
        ocr_rows=all_ocr_rows,
        evidence_rows=all_evidence_rows,
        tesseract=tesseract,
    )
    (output_dir / "university_admission_image_attachment_ocr_summary_all.json").write_text(
        json.dumps(combined_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "university admission image attachment ocr complete. "
        f"years={','.join(str(year) for year in sorted(years))} "
        f"imageRows={combined_summary['imageAttachmentRows']} "
        f"ocrRows={combined_summary['ocrRows']} "
        f"evidenceRows={combined_summary['evidenceRows']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", default=DEFAULT_YEARS)
    parser.add_argument("--year", action="append", type=int)
    parser.add_argument("--manifest-glob", action="append", default=[])
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-link-role", action="append")
    parser.add_argument("--tesseract")
    parser.add_argument("--ocr-backend", choices=["tesseract", "glm-ocr"], default="tesseract")
    parser.add_argument("--glm-model", default=GLM_DEFAULT_MODEL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(cli_args())
    if not args.manifest_glob:
        args.manifest_glob = [DEFAULT_MANIFEST_GLOB]
    return args


def cli_args() -> list[str]:
    args = sys.argv[1:]
    return args[1:] if args[:1] == ["--"] else args


def parse_years(years: str, repeated_years: list[int] | None) -> set[int]:
    parsed = {int(value) for value in re.split(r"[,\s]+", years.strip()) if value}
    if repeated_years:
        parsed.update(repeated_years)
    return parsed


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


def resolve_globs(repo_root: Path, patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for pattern in patterns:
        path = Path(pattern)
        matches = sorted(glob.glob(str(path if path.is_absolute() else repo_root / path)))
        for match in matches:
            resolved = str(Path(match).resolve())
            if resolved not in seen:
                seen.add(resolved)
                paths.append(Path(match))
    return paths


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def detect_image_kind(row: dict[str, Any], repo_root: Path) -> str:
    metadata_values = [
        row.get("contentType"),
        row.get("contentDisposition"),
        row.get("suggestedFilename"),
        row.get("attachmentUrl"),
        row.get("finalUrl"),
        row.get("rawPath"),
        row.get("linkText"),
        row.get("fileExtension"),
    ]
    metadata_text = " ".join(str(value or "") for value in metadata_values).lower()
    file_extension = str(row.get("fileExtension") or "").lower().lstrip(".")
    if str(row.get("contentType") or "").lower().startswith("image/"):
        return extension_from_content_type(str(row.get("contentType") or "")) or file_extension or "image"
    if file_extension in IMAGE_EXTENSIONS:
        return "jpg" if file_extension == "jpeg" else file_extension
    match = IMAGE_EXTENSION_PATTERN.search(metadata_text)
    if match:
        extension = match.group(1).lower()
        return "jpg" if extension == "jpeg" else extension

    raw_path = repo_root / str(row.get("rawPath") or "")
    if str(row.get("status") or "") == "fetched" and raw_path.exists() and int(row.get("bytes") or 0) <= 20_000_000:
        return image_kind_from_magic(raw_path)
    return ""


def extension_from_content_type(content_type: str) -> str:
    value = content_type.lower()
    if "png" in value:
        return "png"
    if "jpeg" in value or "jpg" in value:
        return "jpg"
    if "gif" in value:
        return "gif"
    if "bmp" in value:
        return "bmp"
    if "webp" in value:
        return "webp"
    return ""


def image_kind_from_magic(path: Path) -> str:
    try:
        header = path.read_bytes()[:16]
    except OSError:
        return ""
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8"):
        return "jpg"
    if header.startswith(b"GIF87a") or header.startswith(b"GIF89a"):
        return "gif"
    if header.startswith(b"BM"):
        return "bmp"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    return ""


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in sorted(
        rows,
        key=lambda value: (
            str(value.get("year") or ""),
            str(value.get("unvCd") or ""),
            str(value.get("sourceLinkRole") or ""),
            str(value.get("sha256") or value.get("rawPath") or ""),
            str(value.get("attachmentUrl") or ""),
        ),
    ):
        key = "|".join(
            [
                str(row.get("year") or ""),
                str(row.get("unvCd") or ""),
                str(row.get("sourceLinkRole") or ""),
                str(row.get("sha256") or row.get("rawPath") or ""),
                str(row.get("attachmentUrl") or ""),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def run_ocr_jobs(
    *,
    image_rows: list[dict[str, Any]],
    repo_root: Path,
    text_root: Path,
    tesseract: str,
    backend: str = "tesseract",
    glm_model: str = GLM_DEFAULT_MODEL,
    force: bool,
    timeout_seconds: int,
    jobs: int,
) -> list[dict[str, Any]]:
    def process(index_and_row: tuple[int, dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        index, image_row = index_and_row
        return (
            index,
            build_ocr_row(
                image_row=image_row,
                repo_root=repo_root,
                text_root=text_root,
                tesseract=tesseract,
                backend=backend,
                glm_model=glm_model,
                force=force,
                timeout_seconds=timeout_seconds,
            ),
        )

    indexed_rows = list(enumerate(image_rows, start=1))
    completed: dict[int, dict[str, Any]] = {}
    if jobs == 1:
        for item in indexed_rows:
            index, ocr_row = process(item)
            completed[index] = ocr_row
            print_ocr_progress(index, len(indexed_rows), ocr_row)
    else:
        with futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            future_map = {executor.submit(process, item): item[0] for item in indexed_rows}
            for future in futures.as_completed(future_map):
                index, ocr_row = future.result()
                completed[index] = ocr_row
                print_ocr_progress(index, len(indexed_rows), ocr_row)
    return [completed[index] for index in sorted(completed)]


def print_ocr_progress(index: int, total: int, ocr_row: dict[str, Any]) -> None:
    print(
        "university admission image attachment ocr "
        f"index={index}/{total} "
        f"status={ocr_row['ocrStatus']} "
        f"chars={ocr_row['textChars']} "
        f"role={ocr_row.get('detectedOcrRole')} "
        f"unvCd={ocr_row.get('unvCd')}"
    )


def build_ocr_row(
    *,
    image_row: dict[str, Any],
    repo_root: Path,
    text_root: Path,
    tesseract: str,
    backend: str = "tesseract",
    glm_model: str = GLM_DEFAULT_MODEL,
    force: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    raw_path = repo_root / str(image_row.get("rawPath") or "")
    raw_sha = str(image_row.get("sha256") or "")
    if raw_path.exists() and not raw_sha:
        raw_sha = sha256_file(raw_path)
    image_kind = str(image_row.get("detectedImageKind") or detect_image_kind(image_row, repo_root))
    text_path = text_path_for(
        text_root=text_root,
        raw_image_sha=raw_sha,
        unv_cd=str(image_row.get("unvCd") or "unknown"),
        image_kind=image_kind or "image",
    )
    text_path.parent.mkdir(parents=True, exist_ok=True)
    common = {
        "provider": "university-admission-office",
        "artifactType": "admission_image_attachment_ocr",
        "year": image_row.get("year"),
        "unvCd": image_row.get("unvCd"),
        "universityName": image_row.get("universityName"),
        "campus": image_row.get("campus"),
        "sourceLinkRole": image_row.get("sourceLinkRole"),
        "attachmentRole": image_row.get("attachmentRole"),
        "detectedDocumentRole": image_row.get("detectedDocumentRole"),
        "sourceCandidateUrl": image_row.get("sourceCandidateUrl"),
        "attachmentUrl": image_row.get("attachmentUrl"),
        "canonicalAttachmentUrl": image_row.get("canonicalAttachmentUrl"),
        "finalUrl": image_row.get("finalUrl"),
        "linkText": image_row.get("linkText"),
        "suggestedFilename": image_row.get("suggestedFilename"),
        "contentType": image_row.get("contentType"),
        "contentDisposition": image_row.get("contentDisposition"),
        "fileExtension": image_row.get("fileExtension"),
        "rawImagePath": image_row.get("rawPath"),
        "rawImageSha256": raw_sha,
        "rawImageBytes": image_row.get("bytes"),
        "detectedImageKind": image_kind,
        "manifestPath": image_row.get("manifestPath"),
        "ocrEngine": "glm-ocr" if backend == "glm-ocr" else "tesseract",
        "ocrModel": glm_model if backend == "glm-ocr" else None,
        "ocrLang": glm_model if backend == "glm-ocr" else OCR_LANG,
        "ocrPsm": None if backend == "glm-ocr" else OCR_PSM,
        "textPath": to_repo_relative(text_path, repo_root),
        "ocrAt": datetime.now(timezone.utc).isoformat(),
    }

    if not raw_path.exists():
        return row_with_text_analysis(
            {
                **common,
                "ocrStatus": "missing_raw_image",
                "textSha256": "",
                "tesseractReturnCode": None,
                "stderrPreview": "Raw image path does not exist.",
            },
            "",
        )
    if not image_kind:
        return row_with_text_analysis(
            {
                **common,
                "ocrStatus": "not_image_attachment",
                "textSha256": "",
                "tesseractReturnCode": None,
                "stderrPreview": "Attachment does not look like a supported image.",
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
            resp = client.layout_parsing.create(model=glm_model, file=glm_to_data_uri(raw_path))
            # 원천 보존: 응답 원본 JSON을 텍스트 옆에 sidecar로 남긴다.
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
        except Exception as error:  # API/네트워크/파싱 오류는 행 단위로 격리
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
            [tesseract, str(raw_path), "stdout", "-l", OCR_LANG, "--psm", OCR_PSM],
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
    role, target, matched = detect_ocr_role(row, clean_text)
    row.update(
        {
            "textChars": len(clean_text),
            "nonWhitespaceChars": len(non_ws),
            "lineCount": len([line for line in clean_text.splitlines() if line.strip()]),
            "ocrTextPreview": clean_text[:1000],
            "ocrText": clean_text,
            "detectedOcrRole": role,
            "targetEntity": target,
            "matchedKeywords": matched,
            "priorityScore": priority_score(row, role, matched, len(non_ws)),
            "needsHumanVerification": True,
        }
    )
    return sanitize_json_value(row)


def detect_ocr_role(row: dict[str, Any], text: str) -> tuple[str, str, list[str]]:
    source_link_role = str(row.get("sourceLinkRole") or "")
    metadata_text = normalize_space(
        " ".join(
            str(row.get(field) or "")
            for field in (
                "linkText",
                "suggestedFilename",
                "sourceCandidateUrl",
                "attachmentUrl",
                "contentDisposition",
            )
        )
    )
    searchable_text = "\n".join(value for value in [text, metadata_text] if value)

    if source_link_role == "competition_rate":
        matched = matched_patterns(searchable_text, ROLE_RULES[0][2])
        return ("competition_rate_image_ocr", "HistoricalOutcome", matched or ["source_link_role"])
    if source_link_role == "admission_result":
        matched = matched_patterns(searchable_text, ROLE_RULES[1][2])
        return ("admission_result_image_ocr", "HistoricalOutcome", matched or ["source_link_role"])

    matches_by_role: list[tuple[int, int, str, str, list[str]]] = []
    for order, (role, target, patterns) in enumerate(ROLE_RULES):
        matched = matched_patterns(searchable_text, patterns)
        if matched:
            matches_by_role.append((len(matched), order, role, target, matched))
    if not matches_by_role:
        return ("low_signal_image_ocr", "OCRReviewQueue", [])
    _, _, role, target, matched = sorted(
        matches_by_role, key=lambda item: (-item[0], item[1])
    )[0]
    return role, target, matched


def matched_patterns(text: str, patterns: list[str]) -> list[str]:
    return sorted({pattern for pattern in patterns if re.search(pattern, text)})


def priority_score(row: dict[str, Any], role: str, matched: list[str], non_ws_chars: int) -> int:
    score = 0
    score += min(42, len(matched) * 6)
    score += min(24, non_ws_chars // 50)
    score += 8 if int(row.get("rawImageBytes") or 0) >= 80_000 else 0
    source_link_role = str(row.get("sourceLinkRole") or "")
    if source_link_role == "admission_result":
        score += 20
    elif source_link_role == "competition_rate":
        score += 18
    elif source_link_role == "recruitment_notice":
        score += 10
    if role in {"admission_result_image_ocr", "competition_rate_image_ocr"}:
        score += 18
    elif role in {"csat_rule_image_ocr", "screening_method_image_ocr", "recruitment_quota_image_ocr"}:
        score += 16
    elif role == "schedule_image_ocr":
        score += 10
    elif role == "low_signal_image_ocr":
        score -= 8
    return max(0, min(100, score))


def build_evidence_row(ocr_row: dict[str, Any]) -> dict[str, Any]:
    text = str(ocr_row.get("ocrText") or "")
    evidence_key = "|".join(
        [
            str(ocr_row.get("rawImageSha256") or ""),
            str(ocr_row.get("detectedOcrRole") or ""),
            str(ocr_row.get("textSha256") or ""),
        ]
    )
    return sanitize_json_value(
        {
            "provider": "university-admission-office",
            "artifactType": "admission_image_attachment_ocr_evidence_candidate",
            "year": ocr_row.get("year"),
            "unvCd": ocr_row.get("unvCd"),
            "universityName": ocr_row.get("universityName"),
            "campus": ocr_row.get("campus"),
            "evidenceType": "image_ocr",
            "evidenceRole": ocr_row.get("detectedOcrRole"),
            "evidenceTarget": ocr_row.get("targetEntity"),
            "reviewStatus": "needs_human_verification",
            "priorityScore": ocr_row.get("priorityScore"),
            "sourceDocumentKind": "image_attachment_ocr",
            "sourceLinkRole": ocr_row.get("sourceLinkRole"),
            "attachmentRole": ocr_row.get("attachmentRole"),
            "detectedDocumentRole": ocr_row.get("detectedDocumentRole"),
            "sourceCandidateUrl": ocr_row.get("sourceCandidateUrl"),
            "attachmentUrl": ocr_row.get("attachmentUrl"),
            "sourcePath": ocr_row.get("textPath"),
            "rawPath": ocr_row.get("rawImagePath"),
            "sourceSha256": ocr_row.get("rawImageSha256"),
            "evidenceSha256": hashlib.sha256(evidence_key.encode("utf-8")).hexdigest(),
            "textPreview": normalize_space(text)[:300],
            "text": text,
            "matchedKeywords": ocr_row.get("matchedKeywords"),
            "sourceSpecific": {
                "rawImagePath": ocr_row.get("rawImagePath"),
                "rawImageSha256": ocr_row.get("rawImageSha256"),
                "rawImageBytes": ocr_row.get("rawImageBytes"),
                "detectedImageKind": ocr_row.get("detectedImageKind"),
                "contentType": ocr_row.get("contentType"),
                "contentDisposition": ocr_row.get("contentDisposition"),
                "suggestedFilename": ocr_row.get("suggestedFilename"),
                "linkText": ocr_row.get("linkText"),
                "manifestPath": ocr_row.get("manifestPath"),
                "textPath": ocr_row.get("textPath"),
                "textSha256": ocr_row.get("textSha256"),
                "ocrStatus": ocr_row.get("ocrStatus"),
                "ocrLang": ocr_row.get("ocrLang"),
                "ocrPsm": ocr_row.get("ocrPsm"),
                "textChars": ocr_row.get("textChars"),
                "nonWhitespaceChars": ocr_row.get("nonWhitespaceChars"),
            },
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
    )


def write_year_outputs(
    output_dir: Path,
    year: int,
    image_rows: list[dict[str, Any]],
    ocr_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
) -> None:
    write_jsonl(output_dir / f"university_admission_image_attachment_candidates_{year}.jsonl", image_rows)
    write_jsonl(output_dir / f"university_admission_image_attachment_ocr_manifest_{year}.jsonl", ocr_rows)
    write_csv_index(output_dir / f"university_admission_image_attachment_ocr_index_{year}.csv", ocr_rows)
    write_jsonl(
        output_dir / f"university_admission_image_attachment_ocr_evidence_index_{year}.jsonl",
        evidence_rows,
    )
    write_csv_evidence_index(
        output_dir / f"university_admission_image_attachment_ocr_evidence_index_{year}.csv",
        evidence_rows,
    )


def write_summary(
    *,
    output_dir: Path,
    year: int,
    scanned_rows: int,
    manifest_inputs: list[dict[str, Any]],
    image_rows: list[dict[str, Any]],
    ocr_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    tesseract: str,
) -> None:
    summary = summarize(year, scanned_rows, manifest_inputs, image_rows, ocr_rows, evidence_rows, tesseract)
    (output_dir / f"university_admission_image_attachment_ocr_summary_{year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def summarize(
    year: int | None,
    scanned_rows: int,
    manifest_inputs: list[dict[str, Any]],
    image_rows: list[dict[str, Any]],
    ocr_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    tesseract: str,
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "artifactType": "university_admission_image_attachment_ocr_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "tesseractPath": tesseract,
        "ocrLang": OCR_LANG,
        "ocrPsm": OCR_PSM,
        "manifestInputCount": len(manifest_inputs),
        "scannedAttachmentArtifactRows": scanned_rows,
        "imageAttachmentRows": len(image_rows),
        "ocrRows": len(ocr_rows),
        "ocrExtracted": sum(
            1 for row in ocr_rows if row.get("ocrStatus") in {"ocr_extracted", "reused_existing_ocr"}
        ),
        "ocrFailed": sum(1 for row in ocr_rows if row.get("ocrStatus") == "ocr_failed"),
        "ocrTimeout": sum(1 for row in ocr_rows if row.get("ocrStatus") == "ocr_timeout"),
        "missingRawImages": sum(1 for row in ocr_rows if row.get("ocrStatus") == "missing_raw_image"),
        "rowsWithText": sum(1 for row in ocr_rows if int(row.get("nonWhitespaceChars") or 0) > 0),
        "rowsWithKeywords": sum(1 for row in ocr_rows if row.get("detectedOcrRole") != "low_signal_image_ocr"),
        "evidenceRows": len(evidence_rows),
        "totalTextChars": sum(int(row.get("textChars") or 0) for row in ocr_rows),
        "totalNonWhitespaceChars": sum(int(row.get("nonWhitespaceChars") or 0) for row in ocr_rows),
        "byOcrStatus": count_by(ocr_rows, "ocrStatus"),
        "byDetectedOcrRole": count_by(ocr_rows, "detectedOcrRole"),
        "byTargetEntity": count_by(ocr_rows, "targetEntity"),
        "bySourceLinkRole": count_by(ocr_rows, "sourceLinkRole"),
        "byDetectedImageKind": count_by(ocr_rows, "detectedImageKind"),
        "byUniversity": count_by(image_rows, "universityName")[:30],
        "manifestInputs": manifest_inputs,
        "notes": [
            "OCR text is generated from official admissions image attachments using Tesseract kor+eng.",
            "Rows are evidence candidates only and require human verification before promotion.",
            "Keyword roles are heuristic labels for reviewer triage, not production classifications.",
        ],
    }


def text_path_for(text_root: Path, raw_image_sha: str, unv_cd: str, image_kind: str) -> Path:
    folder = raw_image_sha[:2] if raw_image_sha else "unknown"
    suffix = raw_image_sha[:16] if raw_image_sha else "unknown"
    safe_unv_cd = safe_filename(unv_cd)
    safe_kind = safe_filename(image_kind)
    return text_root / folder / f"{safe_unv_cd}_{suffix}_{safe_kind}.txt"


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


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "ocrStatus",
        "detectedOcrRole",
        "targetEntity",
        "priorityScore",
        "textChars",
        "nonWhitespaceChars",
        "sourceLinkRole",
        "detectedImageKind",
        "matchedKeywords",
        "ocrTextPreview",
        "textPath",
        "rawImagePath",
        "attachmentUrl",
        "sourceCandidateUrl",
        "suggestedFilename",
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
        "textPreview",
        "sourcePath",
        "rawPath",
        "attachmentUrl",
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
