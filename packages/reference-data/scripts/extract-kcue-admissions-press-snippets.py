#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TEXT_SOURCE_MANIFEST = (
    "packages/reference-data/data/public/kcue/extracted/"
    "kcue_admissions_press_text_sources.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/kcue/extracted"

SNIPPET_RULES = [
    {
        "role": "admission_schedule",
        "target": "AdmissionSchedule",
        "patterns": [
            r"원서접수",
            r"전형기간",
            r"합격자\s*발표",
            r"합격자\s*등록",
            r"충원\s*합격",
            r"등록\s*마감",
            r"정시\s*모집",
            r"수시\s*모집",
            r"\d{4}\.\s*\d{1,2}\.\s*\d{1,2}",
        ],
        "requiredAny": [
            r"원서접수|합격자\s*발표|합격자\s*등록|충원|등록\s*마감|등록기간|전형기간\s*(?:가군|나군|다군|\d{4})"
        ],
    },
    {
        "role": "implementation_plan_overview",
        "target": "AdmissionRule",
        "patterns": [
            r"대학입학전형시행계획",
            r"전체\s*모집인원",
            r"수시\s*모집인원",
            r"정시\s*모집인원",
            r"수능위주",
            r"학생부위주",
            r"선발\s*기조",
            r"전형유형",
        ],
        "requiredAny": [r"대학입학전형시행계획|전체\s*모집인원|수능위주|학생부위주"],
    },
    {
        "role": "admission_policy_rule",
        "target": "AdmissionRule",
        "patterns": [
            r"대학입학전형기본사항",
            r"대입전형\s*기본사항",
            r"전형자료",
            r"공정성",
            r"사전예고",
            r"학교폭력",
            r"고등교육법",
            r"전형방법",
            r"대입전형\s*간소화",
        ],
        "requiredAny": [r"기본사항|고등교육법|공정성|사전예고|학교폭력|전형방법"],
    },
    {
        "role": "recruitment_quota_trend",
        "target": "AdmissionRule",
        "patterns": [
            r"모집인원",
            r"모집시기",
            r"모집단위",
            r"권역별",
            r"기회균형",
            r"지역균형",
            r"지역인재",
            r"논술위주",
            r"사회통합전형",
        ],
        "requiredAny": [r"모집인원|모집단위|기회균형|지역균형|지역인재|논술위주"],
    },
    {
        "role": "common_application_schedule",
        "target": "AdmissionSchedule",
        "patterns": [
            r"공통원서",
            r"표준\s*공통원서",
            r"통합회원",
            r"원서접수",
            r"진학어플라이",
            r"유웨이어플라이",
            r"전문대학",
            r"4년제\s*대학",
        ],
        "requiredAny": [r"공통원서|원서접수|통합회원"],
    },
    {
        "role": "admission_counseling_support",
        "target": "ReviewQueue",
        "patterns": [
            r"대입상담",
            r"상담교사단",
            r"집중상담",
            r"전화상담",
            r"온라인\s*상담",
            r"1600-1615",
            r"대입정보포털",
            r"챗봇",
        ],
        "requiredAny": [r"대입상담|상담교사단|집중상담|전화상담|온라인\s*상담"],
    },
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    text_source_path = resolve(repo_root, args.text_source_manifest)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_rows = load_jsonl(text_source_path)
    snippets: list[dict[str, Any]] = []

    for source in source_rows:
        if source.get("extractionStatus") not in {"extracted", "reused_duplicate_sha256", "html_like_text"}:
            continue
        text_path_raw = str(source.get("textPath") or "")
        if not text_path_raw:
            continue
        text_path = repo_root / text_path_raw
        if not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")
        snippets.extend(extract_source_snippets(source, text, args))

    write_jsonl(output_dir / "kcue_admissions_press_snippets.jsonl", snippets)
    write_csv_index(output_dir / "kcue_admissions_press_snippet_index.csv", snippets)
    summary = summarize(source_rows, snippets)
    (output_dir / "kcue_admissions_press_snippets_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "kcue admissions press snippet extraction complete. "
        f"eligibleSources={summary['eligibleSources']} "
        f"snippets={summary['snippets']} roles={len(summary['bySnippetRole'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-source-manifest", default=DEFAULT_TEXT_SOURCE_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-snippets-per-document", type=int, default=20)
    parser.add_argument("--max-snippets-per-role", type=int, default=5)
    parser.add_argument("--before-lines", type=int, default=3)
    parser.add_argument("--after-lines", type=int, default=8)
    parser.add_argument("--min-score", type=int, default=3)
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


def extract_source_snippets(
    source: dict[str, Any],
    text: str,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    page_texts = text.split("\f") if str(source.get("documentKind") or "") == "pdf" else [text]
    candidates: list[dict[str, Any]] = []

    for page_index, page_text in enumerate(page_texts, start=1):
        lines = logical_lines(page_text)
        if not lines:
            continue
        for rule in SNIPPET_RULES:
            for start_line, end_line, matched_keywords, score in candidate_windows(lines, rule, args):
                snippet_text = "\n".join(lines[start_line : end_line + 1]).strip()
                if not snippet_text:
                    continue
                candidates.append(
                    build_snippet(
                        source=source,
                        rule=rule,
                        page_number=page_index,
                        start_line=start_line + 1,
                        end_line=end_line + 1,
                        matched_keywords=matched_keywords,
                        score=score,
                        snippet_text=snippet_text,
                    )
                )

    return select_top_snippets(
        candidates,
        max_per_document=args.max_snippets_per_document,
        max_per_role=args.max_snippets_per_role,
    )


def logical_lines(text: str) -> list[str]:
    seeded = re.sub(
        r"(?=(?:□|❍|○|①|②|③|④|⑤|⑥|Ⅰ\.|Ⅱ\.|Ⅲ\.|IV\.|I\.|II\.|III\.|구분\s+내용|수시\s*모집|정시\s*모집|추가\s*모집))",
        "\n",
        text,
    )
    lines: list[str] = []
    for raw_line in seeded.splitlines():
        line = normalize_space(raw_line)
        if not line:
            continue
        if len(line) <= 260:
            lines.append(line)
            continue
        sentence_seed = re.sub(r"(다\.|함\.|임\.|됨\.|음\.|[.!?。])\s+", r"\1\n", line)
        pieces = sentence_seed.splitlines()
        buffer = ""
        for piece in pieces:
            piece = normalize_space(piece)
            if not piece:
                continue
            if len(buffer) + len(piece) <= 260:
                buffer = f"{buffer} {piece}".strip()
            else:
                if buffer:
                    lines.append(buffer)
                buffer = piece
        if buffer:
            lines.append(buffer)
    return lines


def candidate_windows(
    lines: list[str],
    rule: dict[str, Any],
    args: argparse.Namespace,
) -> list[tuple[int, int, list[str], int]]:
    patterns = [re.compile(pattern) for pattern in rule["patterns"]]
    required_patterns = [re.compile(pattern) for pattern in rule["requiredAny"]]
    windows: list[tuple[int, int, list[str], int]] = []

    for index, line in enumerate(lines):
        compact_line = normalize_space(line)
        if not compact_line:
            continue
        matched = [pattern.pattern for pattern in patterns if pattern.search(compact_line)]
        if not matched:
            continue
        start = max(0, index - args.before_lines)
        end = min(len(lines) - 1, index + args.after_lines)
        window_text = "\n".join(lines[start : end + 1])
        if not any(pattern.search(window_text) for pattern in required_patterns):
            continue
        score = len(matched) + sum(1 for pattern in patterns if pattern.search(window_text))
        if score < args.min_score:
            continue
        windows.append((start, end, sorted(set(matched)), score))

    return merge_overlapping_windows(windows)


def merge_overlapping_windows(
    windows: list[tuple[int, int, list[str], int]]
) -> list[tuple[int, int, list[str], int]]:
    if not windows:
        return []
    windows = sorted(windows, key=lambda item: (item[0], item[1]))
    merged: list[tuple[int, int, list[str], int]] = []
    for start, end, matched, score in windows:
        if not merged or start > merged[-1][1] + 1:
            merged.append((start, end, matched, score))
            continue
        prev_start, prev_end, prev_matched, prev_score = merged[-1]
        merged[-1] = (
            prev_start,
            max(prev_end, end),
            sorted(set(prev_matched + matched)),
            max(prev_score, score),
        )
    return merged


def build_snippet(
    *,
    source: dict[str, Any],
    rule: dict[str, Any],
    page_number: int,
    start_line: int,
    end_line: int,
    matched_keywords: list[str],
    score: int,
    snippet_text: str,
) -> dict[str, Any]:
    snippet_payload = {
        "idx": source.get("idx"),
        "attachmentIndex": source.get("attachmentIndex"),
        "role": rule["role"],
        "pageNumber": page_number,
        "startLine": start_line,
        "endLine": end_line,
        "text": snippet_text,
    }
    snippet_sha = hashlib.sha256(
        json.dumps(snippet_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "provider": "kcue",
        "artifactType": "kcue_admissions_press_snippet_candidate",
        "idx": source.get("idx"),
        "title": source.get("title"),
        "postRole": source.get("postRole"),
        "academicYear": source.get("academicYear"),
        "postedDate": source.get("postedDate"),
        "attachmentIndex": source.get("attachmentIndex"),
        "attachmentTitle": source.get("attachmentTitle"),
        "attachmentRole": source.get("attachmentRole"),
        "documentKind": source.get("documentKind"),
        "snippetRole": rule["role"],
        "evidenceTarget": rule["target"],
        "reviewStatus": "needs_human_verification",
        "pageNumber": page_number,
        "startLine": start_line,
        "endLine": end_line,
        "score": score,
        "matchedKeywords": matched_keywords,
        "textPreview": normalize_space(snippet_text)[:500],
        "text": snippet_text[:4000],
        "textPath": source.get("textPath"),
        "rawAttachmentPath": source.get("rawAttachmentPath"),
        "rawAttachmentSha256": source.get("rawAttachmentSha256"),
        "sourceUrl": source.get("sourceUrl"),
        "viewUrl": source.get("viewUrl"),
        "snippetSha256": snippet_sha,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }


def select_top_snippets(
    candidates: list[dict[str, Any]],
    *,
    max_per_document: int,
    max_per_role: int,
) -> list[dict[str, Any]]:
    by_role: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        by_role.setdefault(str(candidate.get("snippetRole")), []).append(candidate)

    selected: list[dict[str, Any]] = []
    for role, role_candidates in by_role.items():
        role_candidates.sort(
            key=lambda item: (
                -int(item.get("score") or 0),
                int(item.get("pageNumber") or 0),
                int(item.get("startLine") or 0),
                str(item.get("snippetSha256") or ""),
            )
        )
        selected.extend(role_candidates[:max_per_role])

    selected.sort(
        key=lambda item: (
            -int(item.get("score") or 0),
            str(item.get("snippetRole") or ""),
            int(item.get("pageNumber") or 0),
            int(item.get("startLine") or 0),
        )
    )
    return selected[:max_per_document]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv_index(path: Path, rows: list[dict[str, Any]]) -> None:
    headers = [
        "idx",
        "title",
        "postRole",
        "academicYear",
        "postedDate",
        "attachmentRole",
        "documentKind",
        "snippetRole",
        "evidenceTarget",
        "reviewStatus",
        "score",
        "pageNumber",
        "startLine",
        "endLine",
        "textPath",
        "rawAttachmentPath",
        "snippetSha256",
        "textPreview",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({header: row.get(header, "") for header in headers})


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u001f\u007f-\u009f]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


def summarize(source_rows: list[dict[str, Any]], snippets: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_statuses = {"extracted", "reused_duplicate_sha256", "html_like_text"}
    return {
        "provider": "kcue",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceAttachments": len(source_rows),
        "eligibleSources": sum(1 for row in source_rows if row.get("extractionStatus") in eligible_statuses),
        "sourcesWithSnippets": len({snippet.get("textPath") for snippet in snippets}),
        "snippets": len(snippets),
        "uniqueSnippetSha256": len({str(row.get("snippetSha256") or "") for row in snippets}),
        "bySnippetRole": count_by(snippets, "snippetRole"),
        "byEvidenceTarget": count_by(snippets, "evidenceTarget"),
        "byPostRole": count_by(snippets, "postRole"),
        "byAttachmentRole": count_by(snippets, "attachmentRole"),
        "byDocumentKind": count_by(snippets, "documentKind"),
        "notes": [
            "Snippets are review candidates extracted from KCUE press attachment text.",
            "AdmissionRule and AdmissionSchedule promotion requires human source verification.",
            "ReviewQueue snippets capture support/service information such as counseling and portal guidance.",
        ],
    }


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counts = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    main()
