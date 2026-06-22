#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
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


DEFAULT_IMAGE_MANIFEST = "packages/reference-data/data/public/adiga/adiga_unique_image_manifest.jsonl"
DEFAULT_SOURCE_REFERENCES = "packages/reference-data/data/public/adiga/adiga_image_source_references.jsonl"
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/adiga/extracted"

OCR_LANG = "kor+eng"
OCR_PSM = "6"
OCR_IMAGE_STATUSES = {"downloaded", "reused_existing_file"}
OCR_IMAGE_KINDS = {"png", "jpeg", "bmp", "gif"}

# --- GLM-OCR backend (z.ai) -------------------------------------------------
GLM_DEFAULT_MODEL = "glm-ocr"
GLM_IMAGE_MAX_BYTES = 10 * 1024 * 1024
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
        raise RuntimeError("지원 형식(JPG/PNG 등)이 아님")
    if len(raw) > GLM_IMAGE_MAX_BYTES:
        raise RuntimeError(f"glm-ocr 크기 초과({len(raw)} bytes)")
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


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
    if isinstance(data, dict):
        for key in ("md_results", "md_result", "markdown_results", "markdown"):
            val = data.get(key)
            if isinstance(val, str) and val.strip():
                return val
    preferred = ("md_results", "markdown", "md", "text", "content", "ocr_text", "result", "ocr")
    best: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key in preferred:
                v = node.get(key)
                if isinstance(v, str) and v.strip():
                    best.append(v)
            for v in node.values():
                walk(v)
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
        "admission_result_image",
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
        "score_distribution_image",
        "HistoricalOutcome",
        [r"성적", r"등급", r"백분위", r"표준점수", r"환산", r"평균", r"최고", r"최저"],
    ),
    (
        "recruitment_rule_image",
        "AdmissionRule",
        [r"전형", r"모집", r"수능", r"반영", r"학생부", r"면접", r"실기", r"논술", r"선발"],
    ),
    (
        "applicant_profile_image",
        "ReviewQueue",
        [r"지원자", r"합격자", r"지역", r"고교", r"소재지", r"성별", r"비율", r"분석"],
    ),
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    image_manifest_path = resolve(repo_root, args.image_manifest)
    source_references_path = resolve(repo_root, args.source_references)
    output_dir = resolve(repo_root, args.output_dir)
    text_root = output_dir / "image-ocr-text"
    text_root.mkdir(parents=True, exist_ok=True)

    backend = args.ocr_backend
    tesseract = args.tesseract or shutil.which("tesseract")
    if backend == "glm-ocr":
        load_dotenv_keys(repo_root)
        get_glm_client()
    elif not tesseract:
        raise RuntimeError("tesseract is required for Adiga image OCR.")

    image_rows = load_jsonl(image_manifest_path)
    reference_rows = load_jsonl(source_references_path)
    reference_stats = reference_stats_by_image_sha(reference_rows)
    ocr_candidates = [row for row in image_rows if is_ocr_candidate(row)]
    if args.limit is not None:
        ocr_candidates = ocr_candidates[: args.limit]

    ocr_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for index, image in enumerate(ocr_candidates, start=1):
        raw_path = repo_root / str(image.get("rawImagePath") or "")
        ocr_row = build_ocr_row(
            image=image,
            raw_path=raw_path,
            text_root=text_root,
            repo_root=repo_root,
            tesseract=tesseract,
            backend=backend,
            glm_model=args.glm_model,
            force=args.force,
            timeout_seconds=args.timeout_seconds,
            reference_stats=reference_stats,
        )
        ocr_rows.append(ocr_row)
        if ocr_row["ocrStatus"] in {"ocr_extracted", "reused_existing_ocr"}:
            evidence_rows.append(build_evidence_row(ocr_row))

        print(
            "adiga image ocr "
            f"index={index}/{len(ocr_candidates)} "
            f"status={ocr_row['ocrStatus']} "
            f"chars={ocr_row['textChars']} "
            f"role={ocr_row['detectedOcrRole']} "
            f"key={ocr_row['canonicalImageKey']}"
        )

    write_jsonl(output_dir / "adiga_image_ocr_manifest.jsonl", ocr_rows)
    write_csv_index(output_dir / "adiga_image_ocr_index.csv", ocr_rows)
    write_jsonl(output_dir / "adiga_image_ocr_evidence_index.jsonl", evidence_rows)
    write_csv_evidence_index(output_dir / "adiga_image_ocr_evidence_index.csv", evidence_rows)
    summary = summarize(image_rows, ocr_rows, evidence_rows, tesseract)
    (output_dir / "adiga_image_ocr_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "adiga image ocr complete. "
        f"candidates={summary['ocrCandidates']} "
        f"ocrRows={summary['ocrRows']} "
        f"extracted={summary['ocrExtracted']} "
        f"evidenceRows={summary['evidenceRows']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-manifest", default=DEFAULT_IMAGE_MANIFEST)
    parser.add_argument("--source-references", default=DEFAULT_SOURCE_REFERENCES)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--tesseract")
    parser.add_argument("--ocr-backend", choices=["tesseract", "glm-ocr"], default="tesseract")
    parser.add_argument("--glm-model", default=GLM_DEFAULT_MODEL)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--timeout-seconds", type=int, default=45)
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
        str(row.get("status") or "") in OCR_IMAGE_STATUSES
        and str(row.get("detectedImageKind") or "") in OCR_IMAGE_KINDS
        and bool(row.get("rawImagePath"))
    )


def reference_stats_by_image_sha(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in rows:
        image_sha = str(row.get("imageSha256") or "")
        if not image_sha:
            continue
        current = stats.setdefault(
            image_sha,
            {
                "sourceReferenceCount": 0,
                "years": set(),
                "universities": set(),
                "sampleReferences": [],
            },
        )
        current["sourceReferenceCount"] += 1
        current["years"].add(row.get("year"))
        current["universities"].add(f"{row.get('year')}:{row.get('unvCd')}")
        if len(current["sampleReferences"]) < 5:
            current["sampleReferences"].append(
                {
                    "year": row.get("year"),
                    "unvCd": row.get("unvCd"),
                    "universityName": row.get("universityName"),
                    "detailRawPath": row.get("detailRawPath"),
                    "detailSourceUrl": row.get("detailSourceUrl"),
                }
            )
    for current in stats.values():
        current["years"] = sorted(value for value in current["years"] if value)
        current["universityCount"] = len(current.pop("universities"))
    return stats


def build_ocr_row(
    *,
    image: dict[str, Any],
    raw_path: Path,
    text_root: Path,
    repo_root: Path,
    tesseract: str,
    backend: str = "tesseract",
    glm_model: str = GLM_DEFAULT_MODEL,
    force: bool,
    timeout_seconds: int,
    reference_stats: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    image_sha = str(image.get("sha256") or "")
    text_path = text_path_for(text_root, image_sha, str(image.get("canonicalImageKey") or "image"))
    text_path.parent.mkdir(parents=True, exist_ok=True)
    common = {
        "provider": "adiga",
        "artifactType": "adiga_image_ocr",
        "canonicalImageKey": image.get("canonicalImageKey"),
        "imageUrl": image.get("imageUrl"),
        "imageUrlSha256": image.get("imageUrlSha256"),
        "rawImagePath": image.get("rawImagePath"),
        "rawImageSha256": image_sha,
        "imageBytes": image.get("bytes"),
        "detectedImageKind": image.get("detectedImageKind"),
        "width": image.get("width"),
        "height": image.get("height"),
        "sourceReferenceCount": reference_stats.get(image_sha, {}).get(
            "sourceReferenceCount", image.get("sourceReferenceCount")
        ),
        "years": reference_stats.get(image_sha, {}).get("years", image.get("years") or []),
        "universityCount": reference_stats.get(image_sha, {}).get(
            "universityCount", image.get("universityCount")
        ),
        "sampleReferences": reference_stats.get(image_sha, {}).get("sampleReferences", []),
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
    role, target, matched = detect_ocr_role(clean_text)
    row.update(
        {
            "textChars": len(clean_text),
            "nonWhitespaceChars": len(non_ws),
            "lineCount": len([line for line in clean_text.splitlines() if line.strip()]),
            "ocrTextPreview": clean_text[:500],
            "detectedOcrRole": role,
            "targetEntity": target,
            "matchedKeywords": matched,
            "priorityScore": priority_score(row, clean_text, role, matched),
            "needsHumanVerification": True,
        }
    )
    return sanitize_json_value(row)


def detect_ocr_role(text: str) -> tuple[str, str, list[str]]:
    matches_by_role: list[tuple[int, str, str, list[str]]] = []
    for role, target, patterns in ROLE_RULES:
        matched = sorted({pattern for pattern in patterns if re.search(pattern, text)})
        if matched:
            matches_by_role.append((len(matched), role, target, matched))
    if not matches_by_role:
        return ("low_signal_image", "OCRReviewQueue", [])
    _, role, target, matched = sorted(matches_by_role, key=lambda item: (-item[0], item[1]))[0]
    return role, target, matched


def priority_score(row: dict[str, Any], text: str, role: str, matched: list[str]) -> int:
    score = 0
    score += min(40, len(matched) * 6)
    score += min(25, int(row.get("nonWhitespaceChars") or len(re.sub(r"\s+", "", text))) // 20)
    score += 10 if int(row.get("sourceReferenceCount") or 0) <= 2 else 3
    score += 8 if int(row.get("imageBytes") or 0) >= 50_000 else 0
    if role in {"admission_result_image", "score_distribution_image", "recruitment_rule_image"}:
        score += 12
    if role == "low_signal_image":
        score -= 12
    return max(0, min(100, score))


def build_evidence_row(ocr_row: dict[str, Any]) -> dict[str, Any]:
    text = str(ocr_row.get("ocrTextPreview") or "")
    evidence_key = "|".join(
        [
            str(ocr_row.get("rawImageSha256") or ""),
            str(ocr_row.get("detectedOcrRole") or ""),
            str(ocr_row.get("textSha256") or ""),
        ]
    )
    return sanitize_json_value(
        {
            "provider": "adiga",
            "artifactType": "adiga_image_ocr_evidence_candidate",
            "evidenceType": "image_ocr",
            "evidenceRole": ocr_row.get("detectedOcrRole"),
            "evidenceTarget": ocr_row.get("targetEntity"),
            "reviewStatus": "needs_human_verification",
            "priorityScore": ocr_row.get("priorityScore"),
            "sourceDocumentKind": "adiga_image",
            "canonicalImageKey": ocr_row.get("canonicalImageKey"),
            "rawImagePath": ocr_row.get("rawImagePath"),
            "rawImageSha256": ocr_row.get("rawImageSha256"),
            "sourceReferenceCount": ocr_row.get("sourceReferenceCount"),
            "years": ocr_row.get("years"),
            "universityCount": ocr_row.get("universityCount"),
            "sampleReferences": ocr_row.get("sampleReferences"),
            "sourcePath": ocr_row.get("textPath"),
            "sourceSha256": ocr_row.get("textSha256"),
            "evidenceSha256": hashlib.sha256(evidence_key.encode("utf-8")).hexdigest(),
            "textPreview": normalize_space(text)[:240],
            "text": text,
            "matchedKeywords": ocr_row.get("matchedKeywords"),
            "sourceSpecific": {
                "imageUrl": ocr_row.get("imageUrl"),
                "imageUrlSha256": ocr_row.get("imageUrlSha256"),
                "detectedImageKind": ocr_row.get("detectedImageKind"),
                "width": ocr_row.get("width"),
                "height": ocr_row.get("height"),
                "imageBytes": ocr_row.get("imageBytes"),
                "ocrLang": ocr_row.get("ocrLang"),
                "ocrPsm": ocr_row.get("ocrPsm"),
                "textPath": ocr_row.get("textPath"),
                "textChars": ocr_row.get("textChars"),
                "nonWhitespaceChars": ocr_row.get("nonWhitespaceChars"),
            },
            "generatedAt": datetime.now(timezone.utc).isoformat(),
        }
    )


def text_path_for(text_root: Path, image_sha: str, key: str) -> Path:
    folder = image_sha[:2] if image_sha else "unknown"
    name = safe_filename(key)[:120]
    suffix = image_sha[:16] if image_sha else hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return text_root / folder / f"{name}_{suffix}.txt"


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
        "canonicalImageKey",
        "ocrStatus",
        "detectedOcrRole",
        "targetEntity",
        "priorityScore",
        "textChars",
        "nonWhitespaceChars",
        "sourceReferenceCount",
        "years",
        "universityCount",
        "detectedImageKind",
        "width",
        "height",
        "imageBytes",
        "matchedKeywords",
        "ocrTextPreview",
        "textPath",
        "rawImagePath",
        "imageUrl",
    ]
    write_dict_csv(path, headers, rows)


def write_csv_evidence_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "evidenceRole",
        "evidenceTarget",
        "priorityScore",
        "reviewStatus",
        "canonicalImageKey",
        "sourceReferenceCount",
        "years",
        "universityCount",
        "textPreview",
        "sourcePath",
        "rawImagePath",
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
    image_rows: list[dict[str, Any]],
    ocr_rows: list[dict[str, Any]],
    evidence_rows: list[dict[str, Any]],
    tesseract: str,
) -> dict[str, Any]:
    return {
        "provider": "adiga",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "tesseractPath": tesseract,
        "ocrLang": OCR_LANG,
        "ocrPsm": OCR_PSM,
        "uniqueImageManifestRows": len(image_rows),
        "ocrCandidates": sum(1 for row in image_rows if is_ocr_candidate(row)),
        "ocrRows": len(ocr_rows),
        "ocrExtracted": sum(
            1 for row in ocr_rows if row.get("ocrStatus") in {"ocr_extracted", "reused_existing_ocr"}
        ),
        "ocrFailed": sum(1 for row in ocr_rows if row.get("ocrStatus") == "ocr_failed"),
        "ocrTimeout": sum(1 for row in ocr_rows if row.get("ocrStatus") == "ocr_timeout"),
        "missingRawImages": sum(1 for row in ocr_rows if row.get("ocrStatus") == "missing_raw_image"),
        "rowsWithText": sum(1 for row in ocr_rows if int(row.get("nonWhitespaceChars") or 0) > 0),
        "rowsWithKeywords": sum(1 for row in ocr_rows if row.get("detectedOcrRole") != "low_signal_image"),
        "evidenceRows": len(evidence_rows),
        "totalTextChars": sum(int(row.get("textChars") or 0) for row in ocr_rows),
        "totalNonWhitespaceChars": sum(int(row.get("nonWhitespaceChars") or 0) for row in ocr_rows),
        "byOcrStatus": count_by(ocr_rows, "ocrStatus"),
        "byDetectedOcrRole": count_by(ocr_rows, "detectedOcrRole"),
        "byTargetEntity": count_by(ocr_rows, "targetEntity"),
        "byDetectedImageKind": count_by(ocr_rows, "detectedImageKind"),
        "notes": [
            "OCR text is generated from downloaded Adiga image artifacts using Tesseract kor+eng.",
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
    return cleaned.strip("_") or "image"


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
