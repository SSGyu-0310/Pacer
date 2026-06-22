#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_TEXT_SOURCE_MANIFEST = (
    "packages/reference-data/data/public/kice/extracted/kice_suneung_press_text_sources.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/kice/extracted"

SNIPPET_RULES = [
    {
        "role": "scoring_result_summary",
        "target": "ExamScoreReference",
        "patterns": [
            r"채점\s*결과",
            r"성적\s*통지",
            r"응시자",
            r"지원자",
            r"결시자",
            r"재학생",
            r"졸업생",
            r"검정고시",
        ],
        "requiredAny": [r"채점\s*결과|응시자|지원자|성적\s*통지"],
    },
    {
        "role": "test_taker_count_table",
        "target": "ExamScoreReference",
        "patterns": [
            r"응시자",
            r"지원자",
            r"결시자",
            r"재학생",
            r"졸업생",
            r"검정고시",
            r"영역",
            r"선택",
            r"인원",
        ],
        "requiredAny": [r"응시자|지원자|결시자"],
    },
    {
        "role": "grade_cut_context",
        "target": "GradeCutReference",
        "patterns": [
            r"등급\s*구분",
            r"등급",
            r"구분\s*점수",
            r"표준점수",
            r"절대평가",
            r"원점수",
            r"영어\s*영역",
            r"한국사\s*영역",
        ],
        "requiredAny": [r"등급"],
    },
    {
        "role": "standard_score_distribution_context",
        "target": "StandardScoreDistributionReference",
        "patterns": [
            r"표준점수",
            r"도수분포",
            r"누적",
            r"백분위",
            r"남자",
            r"여자",
            r"계",
            r"영역별",
            r"과목별",
        ],
        "requiredAny": [r"표준점수|도수분포|백분위"],
    },
    {
        "role": "subject_choice_statistics",
        "target": "ExamScoreReference",
        "patterns": [
            r"선택과목",
            r"국어\s*영역",
            r"수학\s*영역",
            r"탐구\s*영역",
            r"사회탐구",
            r"과학탐구",
            r"직업탐구",
            r"제2외국어",
            r"한문",
        ],
        "requiredAny": [r"선택과목|탐구\s*영역|제2외국어|한문"],
    },
    {
        "role": "score_reporting_method",
        "target": "ExamScoreReference",
        "patterns": [
            r"성적표",
            r"표준점수",
            r"백분위",
            r"등급",
            r"산출",
            r"원점수",
            r"성적\s*자료",
        ],
        "requiredAny": [r"성적표|표준점수|백분위|등급"],
    },
    {
        "role": "top_score_or_distribution_note",
        "target": "ExamScoreReference",
        "patterns": [
            r"만점자",
            r"최고점",
            r"평균",
            r"표준편차",
            r"분포",
            r"상위",
            r"동점자",
        ],
        "requiredAny": [r"만점자|최고점|평균|표준편차|분포"],
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
        if source.get("extractionStatus") not in {
            "extracted",
            "reused_duplicate_sha256",
            "html_like_artifact",
            "low_text",
        }:
            continue
        text_path_raw = str(source.get("textPath") or "")
        if not text_path_raw:
            continue
        text_path = repo_root / text_path_raw
        if not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")
        snippets.extend(extract_source_snippets(source, text, args))

    write_jsonl(output_dir / "kice_suneung_press_snippets.jsonl", snippets)
    write_csv_index(output_dir / "kice_suneung_press_snippet_index.csv", snippets)
    summary = summarize(source_rows, snippets)
    (output_dir / "kice_suneung_press_snippets_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "kice suneung press snippet extraction complete. "
        f"eligibleSources={summary['eligibleSources']} "
        f"snippets={summary['snippets']} roles={len(summary['bySnippetRole'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text-source-manifest", default=DEFAULT_TEXT_SOURCE_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-snippets-per-document", type=int, default=24)
    parser.add_argument("--max-snippets-per-role", type=int, default=5)
    parser.add_argument("--before-lines", type=int, default=3)
    parser.add_argument("--after-lines", type=int, default=8)
    parser.add_argument("--min-score", type=int, default=3)
    return parser.parse_args(cli_args())


def cli_args() -> list[str]:
    args = __import__("sys").argv[1:]
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


def extract_source_snippets(source: dict[str, Any], text: str, args: argparse.Namespace) -> list[dict[str, Any]]:
    lines = logical_lines(text)
    candidates: list[dict[str, Any]] = []
    for rule in SNIPPET_RULES:
        for start_line, end_line, matched_keywords, score in candidate_windows(lines, rule, args):
            snippet_text = "\n".join(lines[start_line : end_line + 1]).strip()
            if not snippet_text:
                continue
            candidates.append(
                build_snippet(
                    source=source,
                    rule=rule,
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
        r"(?=(?:□|■|○|ㅇ|※|<표|표\s*\d|붙임|참고|자료|Ⅰ\.|Ⅱ\.|Ⅲ\.|Ⅳ\.|I\.|II\.|III\.|IV\.|채점\s*결과|응시자|지원자|표준점수|등급\s*구분|도수분포|선택과목|성적\s*통지))",
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
        pieces = re.sub(r"(다\.|함\.|임\.|됨\.|음\.|[.!?。])\s+", r"\1\n", line).splitlines()
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
        matched = [pattern.pattern for pattern in patterns if pattern.search(line)]
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
    start_line: int,
    end_line: int,
    matched_keywords: list[str],
    score: int,
    snippet_text: str,
) -> dict[str, Any]:
    snippet_sha = hashlib.sha256(
        "|".join(
            [
                str(source.get("rawAttachmentSha256") or ""),
                str(rule["role"]),
                str(start_line),
                str(end_line),
                snippet_text,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return {
        "provider": "kice-suneung",
        "artifactType": "kice_suneung_press_snippet",
        "targetEntity": rule["target"],
        "snippetRole": rule["role"],
        "academicYear": source.get("academicYear"),
        "examType": source.get("examType"),
        "postedDate": source.get("postedDate"),
        "title": source.get("title"),
        "boardSeq": source.get("boardSeq"),
        "fileSeq": source.get("fileSeq"),
        "fileTitle": source.get("fileTitle"),
        "sourceUrl": source.get("sourceUrl"),
        "viewUrl": source.get("viewUrl"),
        "rawAttachmentPath": source.get("rawAttachmentPath"),
        "rawAttachmentSha256": source.get("rawAttachmentSha256"),
        "textPath": source.get("textPath"),
        "startLine": start_line,
        "endLine": end_line,
        "matchedKeywords": matched_keywords,
        "score": score,
        "snippetText": snippet_text,
        "snippetSha256": snippet_sha,
        "extractedAt": datetime.now(timezone.utc).isoformat(),
    }


def select_top_snippets(
    candidates: list[dict[str, Any]],
    *,
    max_per_document: int,
    max_per_role: int,
) -> list[dict[str, Any]]:
    ordered = sorted(candidates, key=lambda item: (-int(item["score"]), item["startLine"]))
    selected: list[dict[str, Any]] = []
    selected_ranges_by_role: dict[str, list[tuple[int, int]]] = {}
    role_counts: Counter[str] = Counter()
    seen_sha: set[str] = set()

    for candidate in ordered:
        role = str(candidate["snippetRole"])
        if role_counts[role] >= max_per_role:
            continue
        if candidate["snippetSha256"] in seen_sha:
            continue
        current_range = (int(candidate["startLine"]), int(candidate["endLine"]))
        if any(ranges_overlap(current_range, existing) for existing in selected_ranges_by_role.get(role, [])):
            continue
        selected.append(candidate)
        selected_ranges_by_role.setdefault(role, []).append(current_range)
        role_counts[role] += 1
        seen_sha.add(str(candidate["snippetSha256"]))
        if len(selected) >= max_per_document:
            break

    return sorted(selected, key=lambda item: (str(item["snippetRole"]), int(item["startLine"])))


def ranges_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] <= right[1] and right[0] <= left[1]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv_index(path: Path, snippets: list[dict[str, Any]]) -> None:
    headers = [
        "academicYear",
        "examType",
        "snippetRole",
        "targetEntity",
        "score",
        "title",
        "fileTitle",
        "startLine",
        "endLine",
        "matchedKeywords",
        "snippetPreview",
        "textPath",
        "rawAttachmentPath",
        "sourceUrl",
        "snippetSha256",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for snippet in snippets:
            writer.writerow(
                {
                    "academicYear": snippet.get("academicYear"),
                    "examType": snippet.get("examType"),
                    "snippetRole": snippet.get("snippetRole"),
                    "targetEntity": snippet.get("targetEntity"),
                    "score": snippet.get("score"),
                    "title": snippet.get("title"),
                    "fileTitle": snippet.get("fileTitle"),
                    "startLine": snippet.get("startLine"),
                    "endLine": snippet.get("endLine"),
                    "matchedKeywords": ";".join(snippet.get("matchedKeywords") or []),
                    "snippetPreview": normalize_space(str(snippet.get("snippetText") or ""))[:240],
                    "textPath": snippet.get("textPath"),
                    "rawAttachmentPath": snippet.get("rawAttachmentPath"),
                    "sourceUrl": snippet.get("sourceUrl"),
                    "snippetSha256": snippet.get("snippetSha256"),
                }
            )


def summarize(source_rows: list[dict[str, Any]], snippets: list[dict[str, Any]]) -> dict[str, Any]:
    eligible_statuses = {"extracted", "reused_duplicate_sha256", "html_like_artifact", "low_text"}
    eligible_sources = [row for row in source_rows if row.get("extractionStatus") in eligible_statuses]
    return {
        "provider": "kice-suneung",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourcePressHwps": len(source_rows),
        "eligibleSources": len(eligible_sources),
        "sourcesWithSnippets": len({str(row.get("rawAttachmentSha256") or "") for row in snippets}),
        "snippets": len(snippets),
        "uniqueSnippetSha256": len({str(row.get("snippetSha256") or "") for row in snippets}),
        "byAcademicYear": count_by(snippets, "academicYear"),
        "byExamType": count_by(snippets, "examType"),
        "bySnippetRole": count_by(snippets, "snippetRole"),
        "byTargetEntity": count_by(snippets, "targetEntity"),
        "notes": [
            "Snippets are evidence candidates only; official numeric tables remain in the normalized workbook candidates.",
            "KICE press snippets provide audit context for score reference data such as test-taker counts, grade cuts, distributions, and score reporting methods.",
        ],
    }


def count_by(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    counter = Counter(str(row.get(key) or "") for row in rows)
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def sanitize_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"[\u0000-\u001F\u007F-\u009F]+", " ", value).strip()
    if isinstance(value, list):
        return [sanitize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: sanitize_json_value(item) for key, item in value.items()}
    return value


if __name__ == "__main__":
    main()
