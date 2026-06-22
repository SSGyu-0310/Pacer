#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PDF_SOURCE_MANIFEST = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_pdf_sources_manifest_2027.jsonl"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/university-admission-sites/extracted"
VALID_ADMISSION_YEAR_MIN = 2010
VALID_ADMISSION_YEAR_MAX = 2035
MIN_SNIPPETS_PER_ROLE_BEFORE_GLOBAL_CAP = 2
DOCUMENT_ADMISSION_YEAR_PATTERNS = [
    re.compile(r"(?<!\d)(20[0-3]\d)\s*학년도"),
    re.compile(r"모집요강\s*[․.\-·/ ]*\s*(20[0-3]\d)"),
    re.compile(r"(?<!\d)(20[0-3]\d)\s*(?:대학입학전형|입학전형)\s*(?:기본계획|시행계획)"),
]

SNIPPET_RULES = [
    {
        "role": "csat_reflection_rule",
        "patterns": [
            r"수능",
            r"대학수학능력시험",
            r"반영영역",
            r"반영비율",
            r"영역별",
            r"국어",
            r"수학",
            r"영어",
            r"탐구",
            r"표준점수",
            r"백분위",
            r"등급",
            r"가산점",
            r"환산점수",
        ],
        "requiredAny": [r"수능|대학수학능력시험", r"반영|환산|표준점수|백분위|등급"],
    },
    {
        "role": "screening_method",
        "patterns": [
            r"전형방법",
            r"전형요소",
            r"반영비율",
            r"실질반영비율",
            r"일괄합산",
            r"단계별",
            r"학생부",
            r"면접",
            r"실기",
            r"수능",
        ],
        "requiredAny": [r"전형방법|전형요소|반영비율|실질반영비율|일괄합산|단계별"],
    },
    {
        "role": "admission_result_table",
        "patterns": [
            r"입시결과",
            r"입학결과",
            r"전형결과",
            r"최종등록",
            r"등록자",
            r"합격자",
            r"충원",
            r"예비",
            r"평균",
            r"컷",
            r"백분위",
            r"환산",
            r"등급",
        ],
        "requiredAny": [
            r"입시결과|입학결과|전형결과|최종등록|등록자|최초합격|최종합격|합격자\s*(평균|성적|컷|최저|최고)|충원합격|충원\s*(순위|율)|예비\s*(순위|번호)",
            r"백분위|환산|등급|평균|컷|성적|경쟁률|순위|지원인원|등록인원",
        ],
        "excludeIfAny": [r"원서접수|서류제출|합격자 발표|등록기간"],
        "excludeUnlessAny": [
            r"입시결과|입학결과|전형결과|최종등록|백분위|환산|등급|평균|컷|지원인원|등록인원"
        ],
    },
    {
        "role": "competition_rate_table",
        "patterns": [
            r"경쟁률",
            r"지원율",
            r"모집인원",
            r"지원자",
            r"지원인원",
            r"\d+\s*:\s*1",
        ],
        "requiredAny": [r"경쟁률|지원율|\d+\s*:\s*1"],
    },
    {
        "role": "recruitment_quota_table",
        "patterns": [
            r"모집인원",
            r"모집단위",
            r"모집군",
            r"가군",
            r"나군",
            r"다군",
            r"일반전형",
            r"농어촌",
            r"특성화고",
            r"기회균형",
        ],
        "requiredAny": [r"모집인원|모집단위|모집군"],
    },
    {
        "role": "eligibility_rule",
        "patterns": [
            r"지원자격",
            r"지원\s*자격",
            r"졸업(?:자|예정자)?",
            r"고등학교",
            r"검정고시",
            r"동등\s*이상",
            r"농어촌",
            r"지역인재",
            r"기회균형",
            r"특성화고",
            r"기초생활수급자",
            r"차상위",
            r"한부모",
            r"국가보훈",
            r"재외국민",
        ],
        "requiredAny": [
            r"지원자격|지원\s*자격|졸업(?:자|예정자)?|검정고시|동등\s*이상|농어촌|지역인재|기회균형|특성화고|기초생활수급자|차상위|한부모|국가보훈|재외국민"
        ],
        "excludeIfAny": [r"개인정보\s*수집|동의서|유의사항"],
        "excludeUnlessAny": [
            r"지원자격|지원\s*자격|졸업(?:자|예정자)?|검정고시|동등\s*이상|농어촌|지역인재|기회균형|특성화고|기초생활수급자|차상위|한부모|국가보훈|재외국민"
        ],
    },
    {
        "role": "school_record_rule",
        "patterns": [
            r"학생부",
            r"학교생활기록부",
            r"교과",
            r"비교과",
            r"내신",
            r"석차등급",
            r"진로선택",
            r"성취도",
            r"반영교과",
            r"반영과목",
            r"교과성적",
            r"출결",
            r"봉사",
            r"학년별",
            r"학기별",
        ],
        "requiredAny": [
            r"학생부|학교생활기록부|교과성적|반영교과|반영과목|내신|석차등급|진로선택|성취도"
        ],
        "excludeIfAny": [r"학생부종합|면접|서류평가"],
        "excludeUnlessAny": [
            r"교과성적|반영교과|반영과목|석차등급|내신|진로선택|성취도|출결|봉사|학년별|학기별"
        ],
    },
    {
        "role": "schedule_and_registration",
        "patterns": [
            r"원서접수",
            r"합격자 발표",
            r"충원합격",
            r"등록기간",
            r"등록금",
            r"미등록",
            r"추가합격",
        ],
        "requiredAny": [r"원서접수|합격자 발표|충원합격|등록기간|미등록|추가합격"],
    },
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    source_manifest_path = resolve(repo_root, args.pdf_source_manifest)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    source_rows = load_jsonl(source_manifest_path)
    snippets: list[dict[str, Any]] = []

    for source in source_rows:
        if source.get("extractionStatus") not in {"extracted", "reused_duplicate_sha256"}:
            continue
        text_path_raw = str(source.get("textPath") or "")
        if not text_path_raw:
            continue
        text_path = repo_root / text_path_raw
        if not text_path.exists():
            continue
        text = text_path.read_text(encoding="utf-8", errors="replace")
        snippets.extend(extract_source_snippets(source, text, args))

    write_jsonl(
        output_dir / f"university_admission_pdf_snippets_{args.year}.jsonl",
        snippets,
    )
    write_csv_index(
        output_dir / f"university_admission_pdf_snippet_index_{args.year}.csv",
        snippets,
    )
    summary = summarize(args.year, source_rows, snippets)
    (output_dir / f"university_admission_pdf_snippets_summary_{args.year}.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "university admission pdf snippet extraction complete. "
        f"sources={summary['eligibleSources']} snippets={summary['snippets']} "
        f"roles={len(summary['bySnippetRole'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2027)
    parser.add_argument("--pdf-source-manifest", default=DEFAULT_PDF_SOURCE_MANIFEST)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--max-snippets-per-document", type=int, default=24)
    parser.add_argument("--max-snippets-per-role", type=int, default=6)
    parser.add_argument("--before-lines", type=int, default=4)
    parser.add_argument("--after-lines", type=int, default=10)
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
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").split("\n"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def extract_source_snippets(
    source: dict[str, Any],
    text: str,
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    page_texts = text.split("\f")
    document_detected_admission_years = detected_admission_years_from_document(text)
    candidates: list[dict[str, Any]] = []

    for page_index, page_text in enumerate(page_texts, start=1):
        lines = page_text.splitlines()
        if not any(normalize_space(line) for line in lines):
            continue
        for rule in SNIPPET_RULES:
            windows = candidate_windows_for_rule(lines, rule, args)
            for start_line, end_line, matched_keywords, score in windows:
                snippet_lines = lines[start_line : end_line + 1]
                snippet_text = "\n".join(rstrip_control(line) for line in snippet_lines).strip()
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
                        document_detected_admission_years=document_detected_admission_years,
                    )
                )

    if not candidates:
        candidates.extend(
            numeric_admission_result_fallback_snippets(
                source,
                page_texts,
                document_detected_admission_years,
            )
        )

    selected = select_top_snippets(
        candidates,
        max_per_document=args.max_snippets_per_document,
        max_per_role=args.max_snippets_per_role,
    )
    return selected


def numeric_admission_result_fallback_snippets(
    source: dict[str, Any],
    page_texts: list[str],
    document_detected_admission_years: list[int],
) -> list[dict[str, Any]]:
    if normalize_space(source.get("sourceLinkRole")) != "admission_result":
        return []

    snippets: list[dict[str, Any]] = []
    fallback_rule = {"role": "admission_result_table"}
    for page_index, page_text in enumerate(page_texts, start=1):
        lines = page_text.splitlines()
        table_line_indexes = [
            index
            for index, line in enumerate(lines)
            if is_numeric_table_like_line(line)
        ]
        numeric_token_count = len(re.findall(r"\d+(?:\.\d+)?", page_text))
        if len(table_line_indexes) < 5 or numeric_token_count < 40:
            continue

        start_line = max(0, table_line_indexes[0] - 2)
        end_line = min(len(lines) - 1, table_line_indexes[-1] + 2)
        snippet_text = "\n".join(rstrip_control(line) for line in lines[start_line : end_line + 1]).strip()
        if not snippet_text:
            continue
        score = 40 + min(30, numeric_token_count // 20) + min(20, len(table_line_indexes))
        snippets.append(
            build_snippet(
                source=source,
                rule=fallback_rule,
                page_number=page_index,
                start_line=start_line + 1,
                end_line=end_line + 1,
                matched_keywords=["numeric_admission_result_table_fallback"],
                score=score,
                snippet_text=snippet_text,
                document_detected_admission_years=document_detected_admission_years,
            )
        )
    return snippets


def is_numeric_table_like_line(line: str) -> bool:
    normalized = normalize_space(line)
    if not normalized:
        return False
    numeric_tokens = re.findall(r"\d+(?:\.\d+)?", normalized)
    if len(numeric_tokens) < 4:
        return False
    has_table_spacing = len(re.split(r"\s{2,}", line.strip())) >= 4
    numeric_chars = sum(len(token) for token in numeric_tokens)
    return has_table_spacing or numeric_chars >= 12


def candidate_windows_for_rule(
    lines: list[str],
    rule: dict[str, Any],
    args: argparse.Namespace,
) -> list[tuple[int, int, list[str], int]]:
    raw_windows: list[tuple[int, int, list[str], int]] = []
    compiled_patterns = [re.compile(pattern) for pattern in rule["patterns"]]
    required_patterns = [re.compile(pattern) for pattern in rule["requiredAny"]]

    for line_index, line in enumerate(lines):
        line_text = normalize_space(line)
        if not line_text:
            continue
        window_start = max(0, line_index - args.before_lines)
        window_end = min(len(lines) - 1, line_index + args.after_lines)
        window_text = "\n".join(lines[window_start : window_end + 1])
        if not all(pattern.search(window_text) for pattern in required_patterns):
            continue
        exclude_patterns = [re.compile(pattern) for pattern in rule.get("excludeIfAny", [])]
        exclude_unless_patterns = [
            re.compile(pattern) for pattern in rule.get("excludeUnlessAny", [])
        ]
        if any(pattern.search(window_text) for pattern in exclude_patterns) and not any(
            pattern.search(window_text) for pattern in exclude_unless_patterns
        ):
            continue

        matched_keywords = matched_rule_keywords(window_text, compiled_patterns)
        score = score_window(window_text, matched_keywords)
        if score < args.min_score:
            continue
        raw_windows.append((window_start, window_end, matched_keywords, score))

    page_level_window = page_level_numeric_table_window(lines, rule, compiled_patterns)
    if page_level_window is not None:
        raw_windows.append(page_level_window)

    return merge_windows(raw_windows)


def page_level_numeric_table_window(
    lines: list[str],
    rule: dict[str, Any],
    compiled_patterns: list[re.Pattern[str]],
) -> tuple[int, int, list[str], int] | None:
    role = str(rule.get("role") or "")
    if role not in {"admission_result_table", "competition_rate_table"}:
        return None

    page_text = "\n".join(lines)
    normalized_page_text = normalize_space(page_text)
    if not normalized_page_text:
        return None
    if not re.search(r"모집\s*단위", normalized_page_text):
        return None
    if role == "admission_result_table" and not re.search(
        r"입시결과|입학결과|전형결과|최종등록|등록자", normalized_page_text
    ):
        return None
    if not re.search(r"경쟁률|지원\s*인원|지원인원|모집\s*인원|모집인원", normalized_page_text):
        return None

    table_like_lines = [line for line in lines if is_numeric_table_like_line(line)]
    numeric_tokens = re.findall(r"\d+(?:\.\d+)?", normalized_page_text)
    if len(table_like_lines) < 3 or len(numeric_tokens) < 24:
        return None

    non_empty_indexes = [
        index for index, line in enumerate(lines) if normalize_space(line)
    ]
    if not non_empty_indexes:
        return None

    matched_keywords = matched_rule_keywords(page_text, compiled_patterns)
    matched_keywords.append("page_level_numeric_table")
    score = 40 + min(20, len(table_like_lines)) + min(20, len(numeric_tokens) // 12)
    return (
        non_empty_indexes[0],
        non_empty_indexes[-1],
        sorted(set(matched_keywords)),
        score,
    )


def matched_rule_keywords(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    matches: list[str] = []
    for pattern in patterns:
        found = pattern.findall(text)
        if found:
            matches.append(pattern.pattern)
    return sorted(set(matches))


def score_window(text: str, matched_keywords: list[str]) -> int:
    normalized = normalize_space(text)
    numeric_density = len(re.findall(r"\d", normalized))
    table_like_lines = sum(
        1 for line in text.splitlines() if len(re.split(r"\s{2,}", line.strip())) >= 3
    )
    return len(matched_keywords) * 2 + min(8, numeric_density // 12) + min(6, table_like_lines)


def merge_windows(
    windows: list[tuple[int, int, list[str], int]]
) -> list[tuple[int, int, list[str], int]]:
    if not windows:
        return []
    windows = sorted(windows, key=lambda item: (item[0], item[1]))
    merged: list[tuple[int, int, list[str], int]] = []
    current_start, current_end, current_keywords, current_score = windows[0]

    for start, end, keywords, score in windows[1:]:
        if start <= current_end + 2:
            current_end = max(current_end, end)
            current_keywords = sorted(set(current_keywords + keywords))
            current_score = max(current_score, score) + 1
            continue
        merged.append((current_start, current_end, current_keywords, current_score))
        current_start, current_end, current_keywords, current_score = start, end, keywords, score

    merged.append((current_start, current_end, current_keywords, current_score))
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
    document_detected_admission_years: list[int],
) -> dict[str, Any]:
    snippet_sha = hashlib.sha256(
        "|".join(
            [
                str(source.get("rawPdfSha256") or ""),
                rule["role"],
                str(page_number),
                str(start_line),
                str(end_line),
                snippet_text,
            ]
        ).encode("utf-8")
    ).hexdigest()
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_pdf_text_snippet",
        "year": source.get("year"),
        "unvCd": source.get("unvCd"),
        "universityName": source.get("universityName"),
        "campus": source.get("campus"),
        "sourceLinkRole": source.get("sourceLinkRole"),
        "attachmentRole": source.get("attachmentRole"),
        "detectedDocumentRole": source.get("detectedDocumentRole"),
        "documentDetectedAdmissionYears": document_detected_admission_years,
        "snippetRole": rule["role"],
        "score": score,
        "pageNumber": page_number,
        "startLine": start_line,
        "endLine": end_line,
        "matchedKeywords": matched_keywords,
        "sourceCandidateUrl": source.get("sourceCandidateUrl"),
        "attachmentUrl": source.get("attachmentUrl"),
        "rawPdfPath": source.get("rawPdfPath"),
        "rawPdfSha256": source.get("rawPdfSha256"),
        "textPath": source.get("textPath"),
        "sourceRowKey": source_row_key(source),
        "snippetSha256": snippet_sha,
        "textPreview": normalize_space(snippet_text)[:300],
        "text": snippet_text[:4000],
        "extractedAt": datetime.now(timezone.utc).isoformat(),
        "status": "candidate",
    }


def select_top_snippets(
    candidates: list[dict[str, Any]],
    *,
    max_per_document: int,
    max_per_role: int,
) -> list[dict[str, Any]]:
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_role[str(candidate["snippetRole"])].append(candidate)

    role_selected: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []
    min_per_role = min(max_per_role, MIN_SNIPPETS_PER_ROLE_BEFORE_GLOBAL_CAP)
    for role, role_candidates in by_role.items():
        role_candidates.sort(
            key=lambda row: (
                -int(row["score"]),
                int(row["pageNumber"]),
                int(row["startLine"]),
                str(row["snippetSha256"]),
            )
        )
        role_selected.extend(role_candidates[:min_per_role])
        remaining.extend(role_candidates[min_per_role:max_per_role])

    remaining.sort(
        key=lambda row: (
            -int(row["score"]),
            str(row["snippetRole"]),
            int(row["pageNumber"]),
            int(row["startLine"]),
        )
    )
    selected = role_selected[:max_per_document]
    selected.extend(remaining[: max(0, max_per_document - len(selected))])
    selected.sort(key=lambda row: (int(row["pageNumber"]), int(row["startLine"]), str(row["snippetRole"])))
    return selected


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def detected_admission_years_from_document(text: str) -> list[int]:
    heading = normalize_space("\n".join(text.splitlines()[:80]))
    years: list[int] = []
    for pattern in DOCUMENT_ADMISSION_YEAR_PATTERNS:
        for raw_year in pattern.findall(heading):
            year = int(raw_year)
            if (
                VALID_ADMISSION_YEAR_MIN <= year <= VALID_ADMISSION_YEAR_MAX
                and year not in years
            ):
                years.append(year)
    return years


def rstrip_control(value: str) -> str:
    return re.sub(r"[\u0000-\u0008\u000b-\u001f\u007f-\u009f]+", " ", value).rstrip()


def source_row_key(source: dict[str, Any]) -> str:
    return hashlib.sha256(
        "|".join(
            [
                str(source.get("rawPdfSha256") or ""),
                str(source.get("unvCd") or ""),
                str(source.get("attachmentUrl") or ""),
                str(source.get("sourceCandidateUrl") or ""),
            ]
        ).encode("utf-8")
    ).hexdigest()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(sanitize_json_value(row), ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_csv_index(path: Path, snippets: list[dict[str, Any]]) -> None:
    headers = [
        "year",
        "unvCd",
        "universityName",
        "campus",
        "sourceLinkRole",
        "detectedDocumentRole",
        "snippetRole",
        "score",
        "pageNumber",
        "startLine",
        "endLine",
        "rawPdfPath",
        "textPath",
        "attachmentUrl",
        "textPreview",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        for row in snippets:
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
    source_rows: list[dict[str, Any]],
    snippets: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible_sources = [
        row for row in source_rows if row.get("extractionStatus") in {"extracted", "reused_duplicate_sha256"}
    ]
    source_rows_with_snippets = {str(row.get("sourceRowKey") or "") for row in snippets}
    unique_pdf_with_snippets = {str(row.get("rawPdfSha256") or "") for row in snippets}
    return {
        "provider": "university-admission-office",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "sourcePdfs": len(source_rows),
        "eligibleSources": len(eligible_sources),
        "sourceRowsWithSnippets": len(source_rows_with_snippets),
        "uniquePdfsWithSnippets": len(unique_pdf_with_snippets),
        "snippets": len(snippets),
        "uniqueSnippetSha256": len({str(row.get("snippetSha256") or "") for row in snippets}),
        "bySnippetRole": count_by(snippets, "snippetRole"),
        "bySourceLinkRole": count_by(snippets, "sourceLinkRole"),
        "byDetectedDocumentRole": count_by(snippets, "detectedDocumentRole"),
        "notes": [
            "Snippets are keyword-scored candidates extracted from pdftotext -layout output.",
            "Snippet text is capped for manifest size; textPath/rawPdfPath retain the source for full review.",
            "Candidates require human verification before promotion to AdmissionRule or HistoricalOutcome.",
        ],
    }


if __name__ == "__main__":
    main()
