#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_DECISIONS = "foundation_operational_review_decision_template.csv"
DEFAULT_WORKBOOK_ROW_GLOB = "packages/reference-data/data/public/university-admission-sites/**/university_admission_workbook_row_candidates_*.csv"
DEFAULT_PDF_SOURCE_GLOB = "packages/reference-data/data/public/university-admission-sites/**/university_admission_pdf_sources_manifest_*.jsonl"
OUTPUT_CSV = "foundation_operational_source_review_bundle.csv"
OUTPUT_SUMMARY = "foundation_operational_source_review_bundle_summary.json"

SOURCE_RECORD_CONFIGS = {
    "foundation_admission_units": ("foundation_admission_units.csv", "unitCandidateId"),
    "foundation_csat_reflection_rule_drafts": (
        "foundation_csat_reflection_rule_drafts.csv",
        "csatRuleDraftId",
    ),
    "foundation_historical_outcomes": ("foundation_historical_outcomes.csv", "outcomeCandidateId"),
    "foundation_kice_grade_cuts": ("foundation_kice_grade_cuts.csv", "gradeCutCandidateId"),
    "foundation_kice_standard_score_distributions": (
        "foundation_kice_standard_score_distributions.csv",
        "distributionCandidateId",
    ),
    "foundation_recruitment_quota_drafts": (
        "foundation_recruitment_quota_drafts.csv",
        "quotaDraftId",
    ),
    "foundation_screening_method_drafts": (
        "foundation_screening_method_drafts.csv",
        "screeningMethodDraftId",
    ),
}

FIELDNAMES = [
    "bundleId",
    "bundleStatus",
    "suggestedNextAction",
    "reviewLane",
    "reviewBatchId",
    "packetRank",
    "rowRankInBatch",
    "promotionQueueId",
    "targetEntity",
    "promotionAction",
    "ruleCategory",
    "admissionYear",
    "academicYear",
    "examType",
    "unvCd",
    "universityName",
    "admissionUnitName",
    "recruitmentGroup",
    "subjectName",
    "provider",
    "sourceArtifact",
    "sourceRecordId",
    "reviewPriorityScore",
    "confidence",
    "primaryEvidencePath",
    "primaryEvidenceKind",
    "primaryEvidenceExists",
    "sourceRecordSummary",
    "candidateValueSummary",
    "sourceCoordinates",
    "reviewValueChecklist",
    "approvalScopeKey",
    "snippetMatchTerm",
    "evidenceSnippet",
    "sourceUrls",
    "attachmentUrls",
    "rawPaths",
    "sourcePaths",
    "localEvidenceYears",
    "urlEvidenceYears",
    "reviewInstruction",
]

RULE_KEYWORDS = {
    "csat_reflection": ["수능", "대학수학능력시험", "반영", "영역", "백분위", "표준점수"],
    "recruitment_quota": ["모집인원", "모집단위", "정원", "가군", "나군", "다군"],
    "screening_method": ["전형방법", "전형요소", "단계", "일괄합산", "반영비율"],
}


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    decision_rows = list(read_csv(foundation_dir / args.decisions_csv))
    workbook_rows = load_workbook_row_index(repo_root, args.workbook_row_glob)
    pdf_text_by_raw = load_pdf_text_index(repo_root, args.pdf_source_glob)
    source_records = load_source_record_index(foundation_dir)
    ready_rows = [
        row
        for row in decision_rows
        if normalize_text(row.get("suggestedReviewDecision")) == "ready_for_source_review"
    ]
    cache: dict[Path, str] = {}
    bundles = [
        build_bundle(repo_root, row, cache, workbook_rows, pdf_text_by_raw, source_records)
        for row in ready_rows
    ]
    write_csv(foundation_dir / OUTPUT_CSV, bundles)
    summary = summarize(repo_root, foundation_dir, decision_rows, ready_rows, bundles)
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation operational source review bundles complete. "
        f"bundleRows={len(bundles)} output={to_repo_relative(foundation_dir / OUTPUT_CSV, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--decisions-csv", default=DEFAULT_DECISIONS)
    parser.add_argument("--workbook-row-glob", default=DEFAULT_WORKBOOK_ROW_GLOB)
    parser.add_argument("--pdf-source-glob", default=DEFAULT_PDF_SOURCE_GLOB)
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


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def load_workbook_row_index(repo_root: Path, glob_pattern: str) -> dict[str, list[dict[str, str]]]:
    pattern_path = resolve(repo_root, glob_pattern)
    matches = [Path(path) for path in sorted(glob.glob(str(pattern_path), recursive=True))]
    output: dict[str, list[dict[str, str]]] = {}
    for csv_path in matches:
        try:
            rows = read_csv(csv_path)
        except OSError:
            continue
        for row in rows:
            raw_path = normalize_text(row.get("rawWorkbookPath"))
            text = normalize_text(row.get("filledRowText"))
            if raw_path and text:
                output.setdefault(raw_path, []).append(row)
    return output


def load_pdf_text_index(repo_root: Path, glob_pattern: str) -> dict[str, str]:
    pattern_path = resolve(repo_root, glob_pattern)
    matches = [Path(path) for path in sorted(glob.glob(str(pattern_path), recursive=True))]
    output: dict[str, str] = {}
    for jsonl_path in matches:
        try:
            lines = jsonl_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            raw_path = normalize_text(row.get("rawPdfPath"))
            text_path = normalize_text(row.get("textPath"))
            if raw_path and text_path and resolve(repo_root, text_path).exists():
                output.setdefault(raw_path, text_path)
    return output


def load_source_record_index(foundation_dir: Path) -> dict[str, dict[str, dict[str, str]]]:
    output: dict[str, dict[str, dict[str, str]]] = {}
    for artifact, (filename, id_field) in SOURCE_RECORD_CONFIGS.items():
        path = foundation_dir / filename
        if not path.exists():
            continue
        records: dict[str, dict[str, str]] = {}
        for row in read_csv(path):
            record_id = normalize_text(row.get(id_field))
            if record_id:
                records[record_id] = row
        output[artifact] = records
    return output


def build_bundle(
    repo_root: Path,
    row: dict[str, str],
    cache: dict[Path, str],
    workbook_rows: dict[str, list[dict[str, str]]],
    pdf_text_by_raw: dict[str, str],
    source_records: dict[str, dict[str, dict[str, str]]],
) -> dict[str, Any]:
    evidence_path, evidence_kind, exists = choose_evidence_path(repo_root, row, pdf_text_by_raw)
    text = read_evidence_text(evidence_path, evidence_kind, cache) if exists else ""
    terms = match_terms(row)
    match_term, snippet = find_snippet(text, terms)
    if not snippet:
        match_term, snippet = find_workbook_snippet(row, workbook_rows)
    source_record = source_records.get(normalize_text(row.get("sourceArtifact")), {}).get(
        normalize_text(row.get("sourceRecordId")),
        {},
    )
    return {
        "bundleId": "source-review-" + normalize_text(row.get("promotionQueueId")),
        "bundleStatus": "ready_for_source_comparison" if exists else "missing_local_evidence",
        "suggestedNextAction": suggested_next_action(row, exists, snippet),
        "reviewLane": row.get("reviewLane", ""),
        "reviewBatchId": row.get("reviewBatchId", ""),
        "packetRank": row.get("packetRank", ""),
        "rowRankInBatch": row.get("rowRankInBatch", ""),
        "promotionQueueId": row.get("promotionQueueId", ""),
        "targetEntity": row.get("targetEntity", ""),
        "promotionAction": row.get("promotionAction", ""),
        "ruleCategory": row.get("ruleCategory", ""),
        "admissionYear": row.get("admissionYear", ""),
        "academicYear": row.get("academicYear", ""),
        "examType": row.get("examType", ""),
        "unvCd": row.get("unvCd", ""),
        "universityName": row.get("universityName", ""),
        "admissionUnitName": row.get("admissionUnitName", ""),
        "recruitmentGroup": row.get("recruitmentGroup", ""),
        "subjectName": row.get("subjectName", ""),
        "provider": row.get("provider", ""),
        "sourceArtifact": row.get("sourceArtifact", ""),
        "sourceRecordId": row.get("sourceRecordId", ""),
        "reviewPriorityScore": row.get("reviewPriorityScore", ""),
        "confidence": row.get("confidence", ""),
        "primaryEvidencePath": to_repo_relative(evidence_path, repo_root) if evidence_path else "",
        "primaryEvidenceKind": evidence_kind,
        "primaryEvidenceExists": str(exists).lower(),
        "sourceRecordSummary": source_record_summary(row, source_record),
        "candidateValueSummary": candidate_value_summary(row, source_record),
        "sourceCoordinates": source_coordinates(row, source_record),
        "reviewValueChecklist": review_value_checklist(row, source_record),
        "approvalScopeKey": approval_scope_key(row, source_record),
        "snippetMatchTerm": match_term,
        "evidenceSnippet": snippet,
        "sourceUrls": row.get("sourceUrls", ""),
        "attachmentUrls": row.get("attachmentUrls", ""),
        "rawPaths": row.get("rawPaths", ""),
        "sourcePaths": row.get("sourcePaths", ""),
        "localEvidenceYears": row.get("localEvidenceYears", ""),
        "urlEvidenceYears": row.get("urlEvidenceYears", ""),
        "reviewInstruction": row.get("reviewInstruction", ""),
    }


def choose_evidence_path(
    repo_root: Path,
    row: dict[str, str],
    pdf_text_by_raw: dict[str, str],
) -> tuple[Path | None, str, bool]:
    for value in split_joined(row.get("sourcePaths")):
        path = resolve(repo_root, value)
        if path.exists():
            return path, "source_text", True
    for value in split_joined(row.get("rawPaths")):
        if Path(value).suffix.lower() != ".pdf":
            continue
        text_path = pdf_text_by_raw.get(value)
        if text_path:
            path = resolve(repo_root, text_path)
            if path.exists():
                return path, "pdf_text_manifest", True
    for value in split_joined(row.get("rawPaths")):
        path = resolve(repo_root, value)
        if path.exists() and is_text_like(path):
            return path, "raw_text", True
    for value in split_joined(row.get("rawPaths")):
        path = resolve(repo_root, value)
        if path.exists():
            return path, "raw_binary", True
    return None, "", False


def read_evidence_text(path: Path | None, evidence_kind: str, cache: dict[Path, str]) -> str:
    if path is None or evidence_kind == "raw_binary":
        return ""
    if path in cache:
        return cache[path]
    try:
        raw = path.read_bytes()
    except OSError:
        cache[path] = ""
        return ""
    text = raw.decode("utf-8", errors="ignore")
    if path.suffix.lower() in {".html", ".htm"}:
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = normalize_whitespace(text)
    cache[path] = text[:2_000_000]
    return cache[path]


def match_terms(row: dict[str, str]) -> list[str]:
    terms = []
    for key in ("admissionUnitName", "subjectName", "universityName", "admissionYear", "academicYear"):
        value = normalize_text(row.get(key))
        if value:
            terms.append(value)
    terms.extend(RULE_KEYWORDS.get(normalize_text(row.get("ruleCategory")), []))
    terms.extend(["모집단위", "입시결과", "경쟁률", "수능", "표준점수"])
    return unique_terms(terms)


def find_snippet(text: str, terms: list[str]) -> tuple[str, str]:
    if not text:
        return "", ""
    lowered = text.lower()
    for term in terms:
        term_text = normalize_text(term)
        if not term_text:
            continue
        index = lowered.find(term_text.lower())
        if index >= 0:
            return term_text, text[max(0, index - 180) : min(len(text), index + 520)]
    return "", text[:700]


def find_workbook_snippet(row: dict[str, str], workbook_rows: dict[str, list[dict[str, str]]]) -> tuple[str, str]:
    terms = [term for term in match_terms(row) if term]
    for raw_path in split_joined(row.get("rawPaths")):
        for candidate in workbook_rows.get(raw_path, []):
            text = normalize_text(candidate.get("filledRowText"))
            if not text:
                continue
            for term in terms:
                if term.lower() in text.lower():
                    prefix = (
                        f"sheet={candidate.get('sheetName','')} row={candidate.get('rowIndex','')} "
                        f"role={candidate.get('rowCandidateRole','')}: "
                    )
                    return term, prefix + text[:650]
    return "", ""


def suggested_next_action(row: dict[str, str], evidence_exists: bool, snippet: str) -> str:
    if not evidence_exists:
        return "Find or restore the local source evidence path before review."
    if not snippet:
        return "Open primaryEvidencePath manually; the file exists but no text snippet was extracted."
    if normalize_text(row.get("reviewLane")) == "kice_score_reference":
        return "Compare the source CSV row range against KICE official workbook values before promotion."
    return "Compare evidenceSnippet against the original source row/table and then record a reviewed decision."


def source_record_summary(row: dict[str, str], source_record: dict[str, str]) -> str:
    if not source_record:
        return ""
    artifact = normalize_text(row.get("sourceArtifact"))
    if artifact == "foundation_historical_outcomes":
        return summary_from_fields(
            source_record,
            [
                "outcomeCandidateId",
                "universityName",
                "year",
                "admissionUnitName",
                "recruitmentGroup",
                "scoreAvailability",
                "confidence",
            ],
        )
    if artifact == "foundation_admission_units":
        return summary_from_fields(
            source_record,
            [
                "unitCandidateId",
                "universityName",
                "year",
                "admissionUnitCanonicalName",
                "recruitmentGroup",
                "majorGroup",
                "sourceProviders",
            ],
        )
    if artifact == "foundation_kice_standard_score_distributions":
        return summary_from_fields(
            source_record,
            [
                "distributionCandidateId",
                "academicYear",
                "examType",
                "subjectNameNormalized",
                "standardScore",
                "totalCount",
                "cumulativeTotalCount",
                "candidateConfidence",
            ],
        )
    if artifact == "foundation_kice_grade_cuts":
        return summary_from_fields(
            source_record,
            [
                "gradeCutCandidateId",
                "academicYear",
                "examType",
                "subjectNameNormalized",
                "grade",
                "cutScoreNumeric",
                "testTakerCount",
                "ratioPercent",
                "candidateConfidence",
            ],
        )
    if artifact == "foundation_csat_reflection_rule_drafts":
        return summary_from_fields(
            source_record,
            [
                "csatRuleDraftId",
                "universityName",
                "admissionYear",
                "reviewStrength",
                "scoreTypeCandidates",
                "detectedSignals",
            ],
        )
    if artifact == "foundation_recruitment_quota_drafts":
        return summary_from_fields(
            source_record,
            [
                "quotaDraftId",
                "universityName",
                "admissionYear",
                "reviewStrength",
                "quotaSignals",
                "noiseSignals",
            ],
        )
    if artifact == "foundation_screening_method_drafts":
        return summary_from_fields(
            source_record,
            [
                "screeningMethodDraftId",
                "universityName",
                "admissionYear",
                "reviewStrength",
                "screeningSignals",
                "evaluationElementSignals",
            ],
        )
    return summary_from_fields(source_record, list(source_record)[:10])


def candidate_value_summary(row: dict[str, str], source_record: dict[str, str]) -> str:
    if not source_record:
        return ""
    artifact = normalize_text(row.get("sourceArtifact"))
    if artifact == "foundation_historical_outcomes":
        return summary_from_fields(
            source_record,
            [
                "admissionUnitName",
                "recruitmentGroup",
                "quota",
                "competitionRate",
                "additionalPass",
                "convertedScore50Cut",
                "convertedScore70Cut",
                "totalScore",
                "percentile70Average",
                "avgScoreCandidate",
                "cutScoreCandidate",
                "percentileCutCandidate",
            ],
        )
    if artifact == "foundation_admission_units":
        return summary_from_fields(
            source_record,
            [
                "admissionUnitName",
                "admissionUnitCanonicalName",
                "recruitmentGroup",
                "majorGroup",
                "quotaCandidates",
                "outcomeRows",
            ],
        )
    if artifact == "foundation_kice_standard_score_distributions":
        return summary_from_fields(
            source_record,
            [
                "subjectNameNormalized",
                "standardScore",
                "maleCount",
                "femaleCount",
                "totalCount",
                "cumulativeTotalCount",
            ],
        )
    if artifact == "foundation_kice_grade_cuts":
        return summary_from_fields(
            source_record,
            [
                "subjectNameNormalized",
                "scoreMetric",
                "grade",
                "cutScoreRaw",
                "cutScoreNumeric",
                "cutScoreOperator",
                "testTakerCount",
                "ratioPercent",
            ],
        )
    if artifact == "foundation_csat_reflection_rule_drafts":
        return summary_from_fields(
            source_record,
            [
                "scoreTypeCandidates",
                "percentageValues",
                "weightValues",
                "formulaSignals",
                "scoreMetricSignals",
                "subjectSignals",
            ],
        )
    if artifact == "foundation_recruitment_quota_drafts":
        return summary_from_fields(
            source_record,
            [
                "candidateQuotaValues",
                "admissionUnitNameCandidates",
                "screeningTypeCandidates",
            ],
        )
    if artifact == "foundation_screening_method_drafts":
        return summary_from_fields(
            source_record,
            [
                "percentageValues",
                "weightValues",
                "screeningTypeCandidates",
                "stageSignals",
            ],
        )
    return ""


def source_coordinates(row: dict[str, str], source_record: dict[str, str]) -> str:
    fields = [
        "sourceUrl",
        "viewUrl",
        "rawPath",
        "csvPath",
        "sheetName",
        "sourceRowNumber",
        "sourceColumnNumber",
        "sectionId",
        "tableIndex",
        "rowIndex",
        "sourceCandidateSha256",
        "sourceEvidenceIds",
    ]
    parts = []
    record_coordinates = summary_from_fields(source_record, fields, max_value_length=420)
    if record_coordinates:
        parts.append(record_coordinates)
    row_coordinates = summary_from_fields(
        row,
        ["sourceUrls", "attachmentUrls", "rawPaths", "sourcePaths"],
        max_value_length=420,
    )
    if row_coordinates:
        parts.append(row_coordinates)
    return "; ".join(parts)


def review_value_checklist(row: dict[str, str], source_record: dict[str, str]) -> str:
    artifact = normalize_text(row.get("sourceArtifact"))
    if artifact == "foundation_historical_outcomes":
        return (
            "Verify unit/recruitmentGroup, quota, competitionRate, additionalPass, "
            "cutScore or percentile values, source year, and row/table coordinates."
        )
    if artifact == "foundation_admission_units":
        return "Verify year, university, admission unit name, recruitment group, major group, and quota."
    if artifact == "foundation_kice_standard_score_distributions":
        return "Verify academicYear, examType, subject, standardScore, male/female/total counts, cumulative count, and workbook row."
    if artifact == "foundation_kice_grade_cuts":
        return "Verify academicYear, examType, subject, grade, cut score/operator, test-taker count, ratio, and workbook row."
    if artifact == "foundation_csat_reflection_rule_drafts":
        return "Verify 2027 source, score type, subject/metric signals, percentages, weights, English/history/inquiry policies, and formula draft."
    if artifact == "foundation_recruitment_quota_drafts":
        return "Verify 2027 source, 모집단위 names, quota values, screening type context, and noise flags before applying as a rule/quota source."
    if artifact == "foundation_screening_method_drafts":
        return "Verify 2027 source, 전형방법, 단계/일괄합산 signals, percentage weights, and evaluation elements."
    return "Verify candidate values against the original source before promotion."


def approval_scope_key(row: dict[str, str], source_record: dict[str, str]) -> str:
    artifact = normalize_text(row.get("sourceArtifact"))
    source_record_id = normalize_text(row.get("sourceRecordId"))
    if artifact in {
        "foundation_historical_outcomes",
        "foundation_admission_units",
        "foundation_kice_grade_cuts",
        "foundation_kice_standard_score_distributions",
    }:
        return f"{artifact}:{source_record_id}"
    if artifact in {
        "foundation_csat_reflection_rule_drafts",
        "foundation_recruitment_quota_drafts",
        "foundation_screening_method_drafts",
    }:
        return ":".join(
            [
                artifact,
                source_record_id,
                normalize_text(source_record.get("unvCd") or row.get("unvCd")),
                normalize_text(source_record.get("admissionYear") or row.get("admissionYear")),
            ]
        )
    return f"{artifact}:{source_record_id}"


def summary_from_fields(
    row: dict[str, str],
    fields: list[str],
    *,
    max_value_length: int = 240,
) -> str:
    parts = []
    for field in fields:
        value = normalize_text(row.get(field))
        if not value:
            continue
        if len(value) > max_value_length:
            value = value[: max_value_length - 1] + "…"
        parts.append(f"{field}={value}")
    return "; ".join(parts)


def summarize(
    repo_root: Path,
    foundation_dir: Path,
    decision_rows: list[dict[str, str]],
    ready_rows: list[dict[str, str]],
    bundles: list[dict[str, Any]],
) -> dict[str, Any]:
    by_lane = Counter(str(row.get("reviewLane") or "") for row in bundles)
    by_status = Counter(str(row.get("bundleStatus") or "") for row in bundles)
    with_snippet = sum(1 for row in bundles if row.get("evidenceSnippet"))
    by_kind = Counter(str(row.get("primaryEvidenceKind") or "") for row in bundles)
    by_artifact = Counter(str(row.get("sourceArtifact") or "") for row in bundles)
    with_source_record = sum(1 for row in bundles if row.get("sourceRecordSummary"))
    with_candidate_summary = sum(1 for row in bundles if row.get("candidateValueSummary"))
    with_source_coordinates = sum(1 for row in bundles if row.get("sourceCoordinates"))
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_operational_source_review_bundle_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "decisionTemplateCsv": to_repo_relative(foundation_dir / DEFAULT_DECISIONS, repo_root),
            "decisionRows": len(decision_rows),
            "readyForSourceReviewRows": len(ready_rows),
        },
        "outputs": {
            "sourceReviewBundleCsv": to_repo_relative(foundation_dir / OUTPUT_CSV, repo_root),
        },
        "bundleRows": len(bundles),
        "bundleRowsWithSnippet": with_snippet,
        "bundleRowsWithSourceRecord": with_source_record,
        "bundleRowsWithCandidateValueSummary": with_candidate_summary,
        "bundleRowsWithSourceCoordinates": with_source_coordinates,
        "byReviewLane": dict(sorted(by_lane.items())),
        "byBundleStatus": dict(sorted(by_status.items())),
        "byPrimaryEvidenceKind": dict(sorted(by_kind.items())),
        "bySourceArtifact": dict(sorted(by_artifact.items())),
        "notes": [
            "This bundle accelerates source comparison; it does not mark any row verified.",
            "Evidence snippets are heuristic context windows; reviewers must compare candidateValueSummary against the original source path before promotion.",
            "approvalScopeKey indicates the unit of approval that can be applied after source comparison, not an approval by itself.",
        ],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in FIELDNAMES})


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def is_text_like(path: Path) -> bool:
    return path.suffix.lower() in {".txt", ".csv", ".tsv", ".json", ".jsonl", ".html", ".htm", ".md"}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def unique_terms(values: Iterable[str]) -> list[str]:
    seen = set()
    output = []
    for value in values:
        text = normalize_text(value)
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
