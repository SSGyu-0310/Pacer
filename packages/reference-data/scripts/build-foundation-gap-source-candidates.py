#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_GAP_ACTION_QUEUE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_action_queue.csv"
)
DEFAULT_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_promotion_queue.csv"
)
DEFAULT_ADMISSION_OFFICE_EVIDENCE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_admission_office_evidence_links.csv"
)
DEFAULT_HISTORICAL_OUTCOMES = (
    "packages/reference-data/data/public/foundation/"
    "foundation_historical_outcomes.csv"
)

OUTPUT_JSONL = "foundation_gap_source_candidates.jsonl"
OUTPUT_CSV = "foundation_gap_source_candidates.csv"
OUTPUT_SUMMARY = "foundation_gap_source_candidates_summary.json"

DEFAULT_PRIORITY_TIERS = "p0"
DEFAULT_MAX_CANDIDATES_PER_GAP = 5
BLOCKED_HELPER_SOURCE_PATTERN = re.compile(
    r"jinhak|jinhakapply|uway|uwayapply|telegr|01consulting|nesin|고속성장|진학사|유웨이",
    re.I,
)
NON_ADMISSION_OFFICE_SOURCE_PATTERN = re.compile(
    r"대중교통\s*안내|좌석버스|시내버스|전세버스|노선번호|배차간격|첫차|막차|"
    r"교통안내|찾아오시는\s*길|캠퍼스\s*안내|학교\s*정문|경유\s*대중교통|"
    r"장학금\s*종류\s*및\s*선발기준|신입생\s*및\s*재학생\s*장학제도|"
    r"직전학기\s*평점평균|취득학점\s*\d+\s*이상|국가장학금|"
    r"졸업\s*시\s*취득자격증|졸업\s*후\s*취업\s*분야|졸업후\s*취업분야|"
    r"졸업\s*후\s*취업처|졸업후\s*취업처|학과\s*동아리|학과동아리|"
    r"학과\s*특장점|학과특장점|주요\s*전공\s*과목|주요전공과목|"
    r"학과\s*전공\s*안내|학과전공안내|"
    r"전공과목|전문\s*인력\s*양성|인재\s*양성|"
    r"전공지식과\s*조리실무|외식산업\s*전반",
    re.I,
)
GUIDE_FILENAME_YEAR_PATTERN = re.compile(
    r"(20\d{2})[_\-/ ]*(?:susi|수시|jeongsi|jungsi|regular|정시|guide|mojip)",
    re.I,
)
OUT_OF_SCOPE_ADMISSION_SOURCE_PATTERN = re.compile(
    r"재외국민|순수\s*외국인|외국인\s*특별전형|전\s*교육과정\s*이수자|"
    r"북한이탈주민|편입학|대학원\s*모집|대학원\s*입학|대학원\s*신입학|"
    r"대학원\s*신입생|후기\s*대학원|박사\s*학위\s*과정|박사학위\s*과정|"
    r"석사\s*학위\s*과정|석사학위\s*과정|daehakwon\.pdf|"
    r"recruitment[-_/]*(foreign|transfer)|transfer\.do|foreign\.do",
    re.I,
)
HISTORICAL_OUTCOME_TITLE_YEAR_PATTERN = re.compile(
    r"(20\d{2})\s*학년도.{0,40}?"
    r"(입시\s*결과|입학\s*결과|전형\s*결과|최종\s*결과|모집\s*결과|"
    r"정\s*/?\s*시\s*/?\s*모\s*/?\s*집\s*결과|최종\s*등록자|최종등록자|"
    r"합격자\s*성적|입시\s*경쟁률|경쟁률)",
    re.I,
)
GUIDE_TITLE_YEAR_PATTERN = re.compile(
    r"(20\d{2})\s*학년도.{0,40}?(모집\s*요강|입학\s*전형|전형\s*계획)",
    re.I,
)
OUTCOME_SCORE_SIGNAL_PATTERN = re.compile(
    r"최종\s*등록자|최종등록자|등록자\s*(?:평균|최저)|합격자\s*성적|"
    r"성적|등급|평균|최저|환산\s*점수|백분위|표준\s*점수|"
    r"70\s*%\s*(?:cut|컷)|80\s*%\s*(?:cut|컷)|100\s*%\s*(?:cut|컷)|"
    r"\bcut\b|컷",
    re.I,
)
STRONG_OUTCOME_SCORE_SIGNAL_PATTERN = re.compile(
    r"최종\s*등록자|최종등록자|등록자\s*(?:평균|최저)|합격자\s*성적|"
    r"평균\s*등급|최저\s*등급|환산\s*점수|백분위|표준\s*점수|"
    r"70\s*%\s*(?:cut|컷)|80\s*%\s*(?:cut|컷)|100\s*%\s*(?:cut|컷)|"
    r"\bcut\b|컷",
    re.I,
)
OUTCOME_QUOTA_COMPETITION_SIGNAL_PATTERN = re.compile(
    r"모집\s*인원|모집인원|지원\s*인원|지원인원|지원\s*자|지원자|경쟁률|지원율|지원률",
    re.I,
)
RECRUITMENT_NOTICE_CONTEXT_PATTERN = re.compile(
    r"추가\s*모집\s*(?:안내|모집\s*요강|제출\s*서류)|신입생\s*모집\s*요강|"
    r"모집\s*요강|입학\s*전형|전형\s*계획|원서\s*접수|합격자\s*발표|"
    r"제출\s*서류|지원\s*자격|전형\s*요소|전형\s*방법",
    re.I,
)
STRONG_HISTORICAL_OUTCOME_SIGNAL_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전형\s*결과|최종\s*결과|모집\s*결과|"
    r"경쟁률\s*현황|입시\s*경쟁률|합격자\s*성적|성적\s*통계|"
    r"최종\s*등록자|최종등록자|등록자\s*(?:평균|최저)|"
    r"70\s*%\s*(?:cut|컷)|80\s*%\s*(?:cut|컷)|100\s*%\s*(?:cut|컷)",
    re.I,
)

RULE_CATEGORY_BY_MISSING_FLAG = {
    "missing_csat_rule_draft": "csat_reflection",
    "missing_recruitment_quota_draft": "recruitment_quota",
    "missing_screening_method_draft": "screening_method",
    "missing_school_record_rule_draft": "school_record_reflection",
    "missing_eligibility_rule_draft": "eligibility",
}
OFFICE_SOURCE_TEXT_CACHE: dict[str, str] = {}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    gap_path = resolve(repo_root, args.gap_action_queue)
    promotion_path = resolve(repo_root, args.promotion_queue)
    evidence_path = resolve(repo_root, args.admission_office_evidence)
    historical_outcomes_path = resolve(repo_root, args.historical_outcomes)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    included_priority_tiers = set(split_csv_arg(args.priority_tiers))
    included_missing_flags = set(split_csv_arg(args.missing_flags))
    gap_rows = [
        row
        for row in read_csv(gap_path)
        if normalize_text(row.get("priorityTier")) in included_priority_tiers
        and (
            not included_missing_flags
            or normalize_text(row.get("missingFlag")) in included_missing_flags
        )
    ]
    promotion_rows = [
        row for row in read_csv(promotion_path) if not row_has_blocked_helper_source(row)
    ]
    office_rows = [row for row in read_csv(evidence_path) if not row_has_blocked_helper_source(row)]
    historical_outcome_rows = read_csv(historical_outcomes_path)

    indexes = build_indexes(promotion_rows, office_rows, historical_outcome_rows)
    source_rows = build_gap_source_rows(
        gap_rows,
        indexes,
        max_candidates_per_gap=max(1, args.max_candidates_per_gap),
    )
    source_rows.sort(
        key=lambda row: (
            priority_sort(row.get("gapPriorityTier")),
            -int_or_none(row.get("gapActionPriorityScore") or 0),
            int(row.get("candidateRank") or 999),
            -int_or_none(row.get("candidateMatchScore") or 0),
            str(row.get("universityName") or ""),
            str(row.get("missingFlag") or ""),
            str(row.get("sourceArtifact") or ""),
            str(row.get("sourceRecordId") or ""),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, source_rows)
    write_csv(foundation_dir / OUTPUT_CSV, source_rows)
    summary = summarize(
        repo_root=repo_root,
        inputs=[gap_path, promotion_path, evidence_path, historical_outcomes_path],
        source_rows=source_rows,
        gap_rows=gap_rows,
        included_priority_tiers=sorted(included_priority_tiers, key=priority_sort),
        max_candidates_per_gap=args.max_candidates_per_gap,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap source candidates complete. "
        f"gapActions={len(gap_rows)} rows={len(source_rows)} "
        f"withSources={summary['gapActions']['withSourceCandidates']} "
        f"withoutSources={summary['gapActions']['withoutSourceCandidates']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--gap-action-queue", default=DEFAULT_GAP_ACTION_QUEUE)
    parser.add_argument("--promotion-queue", default=DEFAULT_PROMOTION_QUEUE)
    parser.add_argument("--admission-office-evidence", default=DEFAULT_ADMISSION_OFFICE_EVIDENCE)
    parser.add_argument("--historical-outcomes", default=DEFAULT_HISTORICAL_OUTCOMES)
    parser.add_argument("--priority-tiers", default=DEFAULT_PRIORITY_TIERS)
    parser.add_argument("--missing-flags", default="")
    parser.add_argument("--max-candidates-per-gap", type=int, default=DEFAULT_MAX_CANDIDATES_PER_GAP)
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


def build_indexes(
    promotion_rows: list[dict[str, str]],
    office_rows: list[dict[str, str]],
    historical_outcome_rows: list[dict[str, str]],
) -> dict[str, Any]:
    promotion_by_unv_year: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    promotion_by_unv: dict[str, list[dict[str, str]]] = defaultdict(list)
    office_by_unv_detected_year: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    office_by_unv_collection_year: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    office_by_unv: dict[str, list[dict[str, str]]] = defaultdict(list)
    historical_outcome_by_id: dict[str, dict[str, str]] = {}

    for row in promotion_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        if not unv_cd:
            continue
        promotion_by_unv[unv_cd].append(row)
        for year in source_years(row):
            promotion_by_unv_year[(unv_cd, year)].append(row)

    for row in office_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        if not unv_cd:
            continue
        office_by_unv[unv_cd].append(row)
        for year in split_joined(row.get("detectedAdmissionYears")):
            office_by_unv_detected_year[(unv_cd, year)].append(row)
        for year in split_joined(row.get("collectionYears")):
            office_by_unv_collection_year[(unv_cd, year)].append(row)

    for row in historical_outcome_rows:
        outcome_id = normalize_text(row.get("outcomeCandidateId"))
        if outcome_id:
            historical_outcome_by_id[outcome_id] = row

    return {
        "promotionByUnvYear": promotion_by_unv_year,
        "promotionByUnv": promotion_by_unv,
        "officeByUnvDetectedYear": office_by_unv_detected_year,
        "officeByUnvCollectionYear": office_by_unv_collection_year,
        "officeByUnv": office_by_unv,
        "historicalOutcomeById": historical_outcome_by_id,
    }


def build_gap_source_rows(
    gap_rows: list[dict[str, str]],
    indexes: dict[str, Any],
    max_candidates_per_gap: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gap in gap_rows:
        candidates = candidate_rows_for_gap(gap, indexes)
        candidates.sort(
            key=lambda item: (
                -item["matchScore"],
                priority_sort(item["source"].get("priorityTier")),
                -int_or_none(item["source"].get("reviewPriorityScore") or item["source"].get("reviewPriority")),
                str(item["source"].get("sourceArtifact") or ""),
                str(item["source"].get("sourceRecordId") or item["source"].get("evidenceCandidateSha256") or ""),
            )
        )
        candidates = dedupe_candidates(candidates)[:max_candidates_per_gap]
        if not candidates:
            rows.append(make_no_source_row(gap))
            continue
        for rank, candidate in enumerate(candidates, start=1):
            rows.append(make_source_row(gap, candidate, rank))
    return rows


def candidate_rows_for_gap(gap: dict[str, str], indexes: dict[str, Any]) -> list[dict[str, Any]]:
    unv_cd = normalize_text(gap.get("unvCd"))
    year = normalize_text(gap.get("admissionYear"))
    if not unv_cd or not year:
        return []

    candidates: list[dict[str, Any]] = []
    promotion_pool = list(indexes["promotionByUnvYear"].get((unv_cd, year), []))
    if normalize_text(gap.get("targetEntity")) == "University":
        promotion_pool.extend(indexes["promotionByUnv"].get(unv_cd, []))

    for row in promotion_pool:
        scored = score_promotion_candidate(gap, row, indexes)
        if scored is not None:
            candidates.append(scored)

    for row in indexes["officeByUnvDetectedYear"].get((unv_cd, year), []):
        scored = score_office_candidate(gap, row, "admission_office_detected_year")
        if scored is not None:
            candidates.append(scored)

    for row in indexes["officeByUnvCollectionYear"].get((unv_cd, year), []):
        scored = score_office_candidate(gap, row, "admission_office_collection_year")
        if scored is not None:
            candidates.append(scored)

    if len(candidates) < DEFAULT_MAX_CANDIDATES_PER_GAP:
        for row in indexes["officeByUnv"].get(unv_cd, []):
            scored = score_office_candidate(gap, row, "admission_office_same_university_any_year")
            if scored is not None and scored["matchScore"] >= 70:
                candidates.append(scored)

    return candidates


def score_promotion_candidate(
    gap: dict[str, str],
    row: dict[str, str],
    indexes: dict[str, Any],
) -> dict[str, Any] | None:
    if not promotion_candidate_can_resolve_gap(gap, row, indexes):
        return None
    target_score = target_match_score(gap, normalize_text(row.get("targetEntity")))
    if target_score <= 0:
        return None

    match_parts = ["promotion_queue"]
    score = 40 + target_score
    gap_year = normalize_text(gap.get("admissionYear"))
    if gap_year in source_years(row):
        score += 90
        match_parts.append("same_year")

    required_rule_category = RULE_CATEGORY_BY_MISSING_FLAG.get(normalize_text(gap.get("missingFlag")))
    source_rule_category = normalize_text(row.get("ruleCategory"))
    if required_rule_category:
        if source_rule_category == required_rule_category:
            score += 55
            match_parts.append("rule_category_match")
        elif normalize_text(row.get("targetEntity")) == "AdmissionRule":
            return None

    source_artifact = normalize_text(row.get("sourceArtifact"))
    if source_artifact == "foundation_admission_office_evidence_links":
        score += 25
        match_parts.append("direct_admission_office_evidence")
    elif source_artifact in {
        "foundation_historical_outcomes",
        "foundation_admission_units",
        "foundation_admission_schedule_drafts",
    }:
        score += 15
        match_parts.append("foundation_structured_candidate")

    priority = normalize_text(row.get("priorityTier"))
    score += {"p0": 20, "p1": 12, "p2": 5}.get(priority, 0)
    score += min(30, (int_or_none(row.get("reviewPriorityScore")) or 0) // 12)

    if score < 110:
        return None
    return {
        "sourceKind": "promotion_queue",
        "matchType": "|".join(match_parts),
        "matchScore": score,
        "source": row,
    }


def promotion_candidate_can_resolve_gap(
    gap: dict[str, str],
    row: dict[str, str],
    indexes: dict[str, Any],
) -> bool:
    if is_direct_admission_office_evidence_gap(gap):
        return normalize_text(row.get("sourceArtifact")) == "foundation_admission_office_evidence_links"

    source_artifact = normalize_text(row.get("sourceArtifact"))
    if source_artifact != "foundation_historical_outcomes":
        return True

    missing_flag = normalize_text(gap.get("missingFlag"))
    if missing_flag not in {"missing_outcome_scores", "missing_quota_competition"}:
        return True

    source_record_id = normalize_text(row.get("sourceRecordId"))
    outcome_row = indexes["historicalOutcomeById"].get(source_record_id)
    if not outcome_row:
        return False
    if missing_flag == "missing_outcome_scores":
        return bool_value(outcome_row.get("hasOutcomeScore"))
    return bool_value(outcome_row.get("hasQuotaAndCompetition"))


def score_office_candidate(
    gap: dict[str, str],
    row: dict[str, str],
    match_scope: str,
) -> dict[str, Any] | None:
    if is_ignored_office_source(row):
        return None
    if is_direct_admission_office_evidence_gap(gap) and is_admission_rule_context_false_positive(row):
        return None
    if is_admission_schedule_context_false_positive(row):
        return None
    if is_historical_outcome_rule_context_false_positive(row):
        return None
    relevant_years = office_relevant_years_for_gap(gap, row)
    gap_year = normalize_text(gap.get("admissionYear"))
    if relevant_years:
        if gap_year not in relevant_years:
            return None
    elif office_text_year_mismatches_gap(gap, row, match_scope):
        return None
    elif office_collection_year_fallback_disallowed(gap, row, match_scope):
        return None
    elif is_year_sensitive_gap(gap) and match_scope == "admission_office_same_university_any_year":
        return None

    target_score = target_match_score(gap, normalize_text(row.get("evidenceTarget")))
    if target_score <= 0:
        return None
    if not office_candidate_matches_missing_metric(gap, row):
        return None

    score = 30 + target_score
    match_parts = [match_scope]
    if match_scope == "admission_office_detected_year":
        score += 100
    elif match_scope == "admission_office_collection_year":
        score += 65
    else:
        score += 20

    required_rule_category = RULE_CATEGORY_BY_MISSING_FLAG.get(normalize_text(gap.get("missingFlag")))
    role = normalize_text(row.get("evidenceRole"))
    if required_rule_category:
        if role_matches_rule_category(role, required_rule_category):
            score += 40
            match_parts.append("role_match")
        elif normalize_text(row.get("evidenceTarget")) == "AdmissionRule":
            return None

    if normalize_text(gap.get("targetEntity")) == "AdmissionOfficeEvidence":
        score += 55
        match_parts.append("direct_evidence_gap")
    if any(kind in normalize_text(row.get("evidenceTypes")) for kind in ["workbook", "image"]):
        score += 10
        match_parts.append("table_or_image_evidence")
    score += min(25, (int_or_none(row.get("reviewPriorityScore")) or 0) // 10)

    if score < 95:
        return None
    return {
        "sourceKind": "admission_office_evidence",
        "matchType": "|".join(match_parts),
        "matchScore": score,
        "source": row,
    }


def target_match_score(gap: dict[str, str], source_target: str) -> int:
    gap_target = normalize_text(gap.get("targetEntity"))
    missing_flag = normalize_text(gap.get("missingFlag"))
    if gap_target == source_target:
        return 80
    if gap_target == "AdmissionOfficeEvidence":
        return 65 if source_target in {"HistoricalOutcome", "AdmissionRule", "AdmissionSchedule"} else 0
    if missing_flag in {"missing_outcome_scores", "missing_quota_competition"} and source_target == "HistoricalOutcome":
        return 80
    return 0


def is_direct_admission_office_evidence_gap(gap: dict[str, str]) -> bool:
    return normalize_text(gap.get("targetEntity")) == "AdmissionOfficeEvidence" or (
        normalize_text(gap.get("missingFlag")) == "missing_admission_office_detected_year_evidence"
    )


def office_candidate_matches_missing_metric(
    gap: dict[str, str],
    row: dict[str, str],
) -> bool:
    missing_flag = normalize_text(gap.get("missingFlag"))
    text = office_candidate_guard_text(row)
    if normalize_text(row.get("evidenceTarget")) == "AdmissionRule":
        return admission_rule_candidate_matches_missing_metric(missing_flag, text)
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return True
    if missing_flag == "missing_historical_outcomes":
        return has_historical_outcome_context(text) or has_outcome_table_data_signal(text)
    if missing_flag == "missing_outcome_scores":
        return bool(STRONG_OUTCOME_SCORE_SIGNAL_PATTERN.search(text))
    if missing_flag == "missing_quota_competition":
        if is_prior_year_competition_only_without_quota_pair(text):
            return False
        return bool(OUTCOME_QUOTA_COMPETITION_SIGNAL_PATTERN.search(text))
    return True


def admission_rule_candidate_matches_missing_metric(missing_flag: str, text: str) -> bool:
    if missing_flag == "missing_csat_rule_draft":
        return bool(re.search(r"수능|대학\s*수학\s*능력\s*시험|수학\s*능력\s*시험|최저\s*학력", text))
    if missing_flag == "missing_screening_method_draft":
        if is_documents_or_schedule_without_screening_method(text):
            return False
        return bool(
            re.search(
                r"전형\s*방법|선발\s*방법|전형\s*요소|반영\s*비율|전형\s*총점|"
                r"일괄\s*합산|단계\s*별|서류\s*평가|면접\s*평가|실기\s*고사|"
                r"학생부.{0,20}\d+\s*%",
                text,
            )
        )
    return True


def is_documents_or_schedule_without_screening_method(text: str) -> bool:
    if re.search(r"전형\s*요소|반영\s*비율|전형\s*총점|일괄\s*합산|단계\s*별|서류\s*평가|면접\s*평가", text):
        return False
    return bool(
        re.search(r"제출\s*서류|학교생활기록부\s*사본|사진\s*1\s*매|원서\s*접수|합격\s*자\s*발표|등록", text)
    )


def is_prior_year_competition_only_without_quota_pair(text: str) -> bool:
    if not (re.search(r"전\s*년도", text) and re.search(r"경쟁률", text)):
        return False
    return not re.search(
        r"모집\s*인원|모집인원|지원\s*인원|지원인원|지원\s*자|지원자",
        text,
    )


def is_ignored_office_source(row: dict[str, str]) -> bool:
    text = office_candidate_guard_text(row)
    if NON_ADMISSION_OFFICE_SOURCE_PATTERN.search(text):
        return True
    return bool(OUT_OF_SCOPE_ADMISSION_SOURCE_PATTERN.search(text))


def is_historical_outcome_rule_context_false_positive(row: dict[str, str]) -> bool:
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    text = office_candidate_guard_text(row)
    if is_admission_site_navigation_only_result_text(text):
        return True
    if is_recruitment_notice_without_historical_outcome_result(row, text):
        return True
    if is_recruitment_quota_notice_without_historical_result(text):
        return True
    if is_scholarship_selection_without_historical_result(text):
        return True
    if is_foreign_admission_guide_navigation_without_historical_result(text):
        return True
    if is_admission_site_menu_or_form_without_historical_result(text):
        return True
    if is_department_intro_without_historical_result(text):
        return True
    if is_selection_method_without_historical_result(text):
        return True
    if is_practical_exam_scoring_without_historical_result(text):
        return True
    if is_school_record_reflection_without_historical_result(text):
        return True
    if has_historical_outcome_context(text):
        return False
    if re.search(r"반영\s*영역수|활용\s*지표|영어\s*영역\s*반영방법|수능\s*영역", text) and re.search(
        r"국어|수학|영어|탐구|한국사", text
    ):
        return True
    if re.search(
        r"모집\s*요강|신입생\s*모집요강|입학\s*전형\s*계획|전형\s*계획|추가\s*모집|"
        r"모집\s*단위\s*및\s*모집\s*인원|지원\s*자격|전형\s*요소|반영\s*비율|"
        r"전형\s*방법|전형료|제출\s*서류|원서\s*접수|전형\s*일정|등록\s*포기|"
        r"환불\s*신청|입학\s*정원|정원\s*내|정원\s*외|수능\s*최저|반영\s*교과|"
        r"성적\s*반영방법|대학수학능력시험\s*성적\s*반영방법",
        text,
    ):
        return True
    if re.search(
        r"충원\s*합격자\s*선발|합격자\s*등록\s*안내|등록\s*기간|면접\s*고사\s*반영방법|"
        r"수시\s*모집에\s*합격한\s*자.{0,80}정시\s*모집에\s*지원",
        text,
    ):
        return True
    return bool(
        re.search(
            r"학과\s*소개|전공\s*및\s*진로|졸업\s*후\s*진학|주요\s*과목|진로\s*과목|"
            r"교육\s*과정|커리큘럼|비교과|멘토링|사제동행|취업\s*진로|"
            r"학과\s*선택이\s*진로|크리에이터|학번|장학금|취득\s*자격증|"
            r"졸업\s*시\s*취득\s*자격|졸업\s*시|보안\s*관련|전문\s*공학도|"
            r"문화\s*예술|Fine\s*art|배재학당",
            text,
        )
    )


def is_foreign_admission_guide_navigation_without_historical_result(text: str) -> bool:
    has_foreign_guide_context = bool(
        re.search(r"외국인\s*모집|외국인모집", text)
        and re.search(r"모집\s*요강|pdfViewer/CAT081|입시\s*결과.{0,12}다운로드", text)
    )
    has_pcu_foreign_guide_route = bool(
        re.search(r"pcu\.ac\.kr/enter/23/pdfViewer/CAT081", text)
        and re.search(r"입시\s*결과.{0,12}다운로드", text)
    )
    if not (has_foreign_guide_context or has_pcu_foreign_guide_route):
        return False
    if re.search(r"최종\s*등록자|지원\s*인원|지원인원|합격자\s*성적|경쟁률\s*현황|모집\s*결과", text):
        return False
    return True


def is_recruitment_notice_without_historical_outcome_result(
    row: dict[str, str],
    text: str,
) -> bool:
    source_link_roles = normalize_text(row.get("sourceLinkRoles"))
    if "recruitment_notice" not in source_link_roles and not re.search(
        r"모집\s*공고|추가\s*모집\s*안내",
        text,
    ):
        return False
    if STRONG_HISTORICAL_OUTCOME_SIGNAL_PATTERN.search(text):
        return False
    return bool(RECRUITMENT_NOTICE_CONTEXT_PATTERN.search(text))


def is_recruitment_quota_notice_without_historical_result(text: str) -> bool:
    return bool(
        re.search(
            r"모집\s*인원\s*\[\s*미정\s*\]|수시\s*모집\s*결과에\s*따라|"
            r"수시\s*미충원\s*인원\s*이월\s*모집|지원\s*전.{0,30}홈페이지",
            text,
        )
    )


def is_scholarship_selection_without_historical_result(text: str) -> bool:
    if has_historical_outcome_context(text):
        return False
    return bool(
        re.search(
            r"장학|부가\s*혜택|생활관\s*신청\s*시\s*우선\s*선발|"
            r"수능\s*성적\s*우수자|장학\s*선발\s*기준",
            text,
        )
        and re.search(r"백분위\s*합|최초\s*합격자\s*전원|입학생\s*전원", text)
    )


def is_admission_site_menu_or_form_without_historical_result(text: str) -> bool:
    if re.search(
        r"개인\s*정보.{0,30}수집|개인정보의\s*종류|대입\s*원서\s*접수|"
        r"환불\s*계좌\s*번호|주민\s*\(?외국인\)?\s*등록\s*번호",
        text,
    ):
        return True
    if re.search(
        r"성적\s*산출\s*방법|교과\s*성적\s*산출\s*방법|환산\s*점수\s*산출\s*방법|"
        r"석차\s*등급\s*산출\s*방법",
        text,
    ) and not re.search(r"입시\s*결과|전형\s*결과|입학자\s*현황|경쟁률", text):
        return True
    if has_outcome_table_data_signal(text):
        return False
    if re.search(
        r"신청자\s*정보.{0,80}희망\s*모집\s*단위.{0,80}나의\s*성적|"
        r"희망\s*모집\s*단위.{0,80}희망\s*전형\s*선택.{0,80}희망\s*학과\s*선택|"
        r"성적\s*산출\s*프로그램|입시\s*자료\s*신청|입학\s*설명회\s*신청|"
        r"설명회\s*및\s*박람회|자주\s*하는\s*질문",
        text,
    ):
        return True
    return bool(
        re.search(r"공지사항|입학\s*상담|모집\s*요강|전년도\s*입시\s*결과", text)
        and re.search(r"성적\s*산출|입시\s*자료\s*신청|입학\s*도우미|외국인\s*모집", text)
        and len(re.findall(r"\d+(?:\.\d+)?", text)) < 3
    )


def is_admission_rule_context_false_positive(row: dict[str, str]) -> bool:
    if normalize_text(row.get("evidenceTarget")) != "AdmissionRule":
        return False
    text = office_candidate_guard_text(row)
    if is_admission_rule_form_without_rule_content(text):
        return True
    if is_non_undergraduate_admission_selection_text(text):
        return True
    if is_admission_qa_or_department_intro_without_rule_table(text):
        return True
    if has_admission_rule_data_signal(text):
        return False
    return bool(
        re.search(
            r"학과\s*소개|전공\s*필수|전공\s*기초|교육\s*과정|커리큘럼|"
            r"졸업\s*후\s*진로|졸업\s*후|관련\s*자격|취업|진로|"
            r"복수\s*전공|신입생이\s*궁금|Q\s*.{0,40}A|Q\s+[^\\n]{0,80}|"
            r"국제\s*교류|정규\s*교환\s*학생|장바구니|수강\s*신청|"
            r"재학생|복학생|교양|비교과|동아리|등록금.{0,40}장학",
            text,
            re.I,
        )
    )


def is_admission_schedule_context_false_positive(row: dict[str, str]) -> bool:
    if normalize_text(row.get("evidenceTarget")) != "AdmissionSchedule":
        return False
    text = office_candidate_guard_text(row)
    if has_admission_schedule_date_signal(text):
        return False
    return bool(
        re.search(
            r"개인\s*정보|개인정보|제\s*3\s*자\s*제공|처리\s*목적|이용자의\s*사전\s*동의",
            text,
        )
        or re.search(
            r"지원자\s*유의사항|복수\s*지원|등록\s*포기|전형료|목\s*차|"
            r"원서\s*작성|추가\s*서류|제출\s*서류|연락\s*두절|충원\s*합격자\s*전화\s*통보",
            text,
        )
    )


def has_admission_schedule_date_signal(text: str) -> bool:
    return bool(
        re.search(r"원서\s*접수|전형\s*일정|모집\s*일정|합격\s*자\s*발표|등록\s*기간|면접\s*고사|실기\s*고사", text)
        and re.search(r"20\d{2}\s*[.\-년]\s*\d{1,2}|(?:^|[^\\d])\d{1,2}\s*\.\s*\d{1,2}|(?:^|[^\\d])\d{1,2}\s*:\s*\d{2}", text)
    )


def is_non_undergraduate_admission_selection_text(text: str) -> bool:
    if re.search(r"학군단|ROTC|체력\s*인증|신원\s*조사|입단\s*전|예비\s*서열", text, re.I):
        return True
    return bool(
        re.search(
            r"대학\s*자체\s*선발\s*기준|이수\s*학점|평점\s*평균|장학생|장학\s*생|"
            r"정규\s*교환\s*학생|교환\s*학생|자매\s*대학|수강\s*신청|장바구니",
            text,
        )
        and not re.search(r"모집\s*단위|모집단위|모집\s*인원|모집인원|전형\s*방법|전형방법", text)
    )


def is_admission_qa_or_department_intro_without_rule_table(text: str) -> bool:
    if has_admission_rule_data_signal(text) and not re.search(r"\bQ\b|Q\s|신입생이\s*궁금|본\s*학과", text, re.I):
        return False
    return bool(
        re.search(
            r"\bQ\b|Q\s|신입생이\s*궁금|본\s*학과|학과만의\s*강점|"
            r"졸업\s*후|취업|진로|자격증|복수\s*전공|전공\s*역량|"
            r"중급\s*회계|유통\s*관리|영어\s*문장\s*연습|R\s*프로그래밍",
            text,
            re.I,
        )
        and not re.search(r"모집\s*단위|모집단위|모집\s*인원|모집인원|전형\s*방법|전형방법|지원\s*자격", text)
    )


def is_admission_rule_form_without_rule_content(text: str) -> bool:
    if not re.search(
        r"신청자\s*정보|희망\s*모집\s*단위|희망\s*전형\s*선택|희망\s*학과\s*선택|"
        r"나의\s*성적|고교명\s*검색|성적\s*산출\s*프로그램",
        text,
    ):
        return False
    return not re.search(
        r"모집\s*인원|모집인원|전형\s*방법|전형\s*요소|반영\s*비율|"
        r"지원\s*자격|수능\s*최저|학생부\s*반영|교과\s*반영|실기\s*고사",
        text,
    )


def has_admission_rule_data_signal(text: str) -> bool:
    return bool(
        re.search(
            r"모집\s*단위|모집단위|모집\s*인원|모집인원|전형\s*방법|전형방법|"
            r"전형\s*요소|전형요소|전형\s*별|전형별|선발\s*방법|선발방법|"
            r"학생부\s*(?:교과\s*성적|교과|반영)|교과\s*성적|수능\s*(?:최저|반영|점수)|"
            r"정원\s*(?:내|외)|원서\s*접수|합격자\s*발표|고등학교\s*졸업|"
            r"면접\s*(?:평가|고사)|실기\s*(?:평가|고사)|서류\s*평가",
            text,
            re.I,
        )
    )


def is_department_intro_without_historical_result(text: str) -> bool:
    if has_outcome_table_data_signal(text):
        return False
    return bool(
        re.search(
            r"major[_-]?introduce|educational[_-]?manual|학과\s*소개|학과\s*특성화|학과\s*전공\s*안내|"
            r"본\s*학과|학과만의\s*강점|신입생이\s*궁금|"
            r"전공\s*필수|전공\s*기초|"
            r"주요\s*전공\s*과목|교육\s*과정|졸업\s*후|취업|진로|"
            r"관련\s*자격|자격증|전공\s*역량|복수\s*전공|"
            r"전공\s*및\s*종목|실무형\s*인재|인재\s*양성|디자이너\s*양성|"
            r"전기\s*안전\s*점검|안전\s*공사|개인\s*대형자|"
            r"지진|화상|자동\s*제세동기|응급\s*처치|재난\s*공제회|안전\s*관리",
            text,
            re.I,
        )
    )


def is_practical_exam_scoring_without_historical_result(text: str) -> bool:
    if has_outcome_table_data_signal(text):
        return False
    return bool(
        re.search(
            r"올코트\s*드리블|중거리\s*슛|3\s*점\s*슛|하프\s*코트|"
            r"실기\s*시험|실기\s*고사|횟수\s*점수|스피드\s*슛",
            text,
        )
    )


def is_selection_method_without_historical_result(text: str) -> bool:
    if has_historical_outcome_context(text):
        return False
    return bool(
        re.search(
            r"선발\s*방법|합격자\s*사정|예비\s*합격자|예비합격자|"
            r"입학\s*전형\s*성적순|입학전형\s*성적순|전형\s*성적순",
            text,
        )
        and not re.search(
            r"경쟁률|지원\s*인원|지원인원|최종\s*등록자|최종등록자|"
            r"입시\s*결과|전형\s*결과|평균\s*등급|최저\s*등급|"
            r"70\s*%\s*(?:cut|컷)|80\s*%\s*(?:cut|컷)",
            text,
            re.I,
        )
    )


def is_school_record_reflection_without_historical_result(text: str) -> bool:
    if has_outcome_table_data_signal(text):
        return False
    return bool(
        re.search(
            r"학교\s*생활\s*기록부.{0,40}반영\s*방법|생활\s*기록부.{0,40}반영|"
            r"성분부\s*고과\s*성적|고과\s*성적|나이스\s*제공|"
            r"반영\s*교과목|교과\s*성적\s*석차\s*등급",
            text,
        )
    )


def has_outcome_table_data_signal(text: str) -> bool:
    return bool(
        re.search(
            r"모집\s*인원|모집인원|지원\s*인원|지원인원|지원\s*자|지원자|"
            r"경쟁률|최종\s*등록자|최종등록자|입학자\s*현황|합격자\s*성적|"
            r"평균\s*등급|최저\s*등급|70\s*%\s*(?:cut|컷)|80\s*%\s*(?:cut|컷)|"
            r"수능\s*환산\s*점수",
            text,
            re.I,
        )
    )


def is_admission_site_navigation_only_result_text(text: str) -> bool:
    preview = re.split(r"https?://|\.reference-data|packages/", text, maxsplit=1)[0]
    preview = normalize_text(preview)
    if len(preview) > 700:
        return False
    if not re.search(r"공지사항\s+모집\s*요강\s+자료실\s+경쟁률\s+입시\s*결과", preview):
        return False
    if re.search(r"최종\s*등록자|지원\s*인원|지원인원|합격자\s*성적|모집\s*결과", preview):
        return False
    data_numbers = [
        value
        for value in re.findall(r"\d+(?:\.\d+)?", preview)
        if value not in {"1", "1.1"}
    ]
    return len(data_numbers) == 0


def has_historical_outcome_context(text: str) -> bool:
    if HISTORICAL_OUTCOME_TITLE_YEAR_PATTERN.search(text):
        return True
    return bool(
        re.search(
            r"입시\s*결과|입학\s*결과|전형\s*결과|최종\s*결과|모집\s*결과|"
            r"최종\s*등록자|최종등록자|합격자\s*성적|입시\s*경쟁률|경쟁률\s*현황|"
            r"지원\s*인원|지원인원|등록자\s*평균|등록자\s*최저",
            text,
        )
    )


def office_candidate_guard_text(row: dict[str, str]) -> str:
    return " ".join(
        normalize_text(row.get(key))
        for key in [
            "textPreview",
            "evidenceSummary",
            "draftFlags",
            "blockerFlags",
            "promotionAction",
            "evidenceRole",
            "sourceLabels",
            "sourceLinkRoles",
            "sourceDocumentKinds",
            "sourceCandidateUrl",
            "sourceCandidateUrls",
            "attachmentUrl",
            "attachmentUrls",
            "rawPath",
            "rawPaths",
            "sourcePath",
            "sourcePaths",
        ]
        if normalize_text(row.get(key))
    )


def is_year_sensitive_gap(gap: dict[str, str]) -> bool:
    target = normalize_text(gap.get("targetEntity"))
    missing_flag = normalize_text(gap.get("missingFlag"))
    return target in {"HistoricalOutcome", "AdmissionRule", "AdmissionUnit", "AdmissionSchedule"} or missing_flag in {
        "missing_historical_outcomes",
        "missing_outcome_scores",
        "missing_quota_competition",
        "missing_admission_office_detected_year_evidence",
        "missing_csat_rule_draft",
        "missing_recruitment_quota_draft",
        "missing_screening_method_draft",
        "missing_school_record_rule_draft",
        "missing_eligibility_rule_draft",
        "missing_admission_units",
        "missing_schedule_draft",
    }


def office_collection_year_fallback_disallowed(
    gap: dict[str, str],
    row: dict[str, str],
    match_scope: str,
) -> bool:
    if match_scope != "admission_office_collection_year":
        return False
    if not is_year_sensitive_gap(gap):
        return False
    if normalize_text(row.get("detectedAdmissionYears")):
        return False
    evidence_types = normalize_text(row.get("evidenceTypes"))
    if normalize_text(row.get("evidenceTarget")) not in {
        "HistoricalOutcome",
        "AdmissionRule",
        "AdmissionUnit",
        "AdmissionSchedule",
    }:
        return False
    if "workbook_row" in evidence_types:
        return True
    collection_years = split_joined(row.get("collectionYears"))
    return "pdf_snippet" in evidence_types and len(collection_years) > 1


def office_relevant_years_for_gap(gap: dict[str, str], row: dict[str, str]) -> list[str]:
    target = normalize_text(gap.get("targetEntity"))
    missing_flag = normalize_text(gap.get("missingFlag"))
    source_target = normalize_text(row.get("evidenceTarget"))
    if target == "AdmissionOfficeEvidence" or missing_flag == "missing_admission_office_detected_year_evidence":
        if source_target == "HistoricalOutcome":
            return office_historical_outcome_years(row)
        if source_target in {"AdmissionRule", "AdmissionUnit", "AdmissionSchedule"}:
            return office_admission_rule_years(row)
        return []
    if target == "HistoricalOutcome" or missing_flag in {
        "missing_historical_outcomes",
        "missing_outcome_scores",
        "missing_quota_competition",
    }:
        return office_historical_outcome_years(row)
    if target == "AdmissionRule" or missing_flag in RULE_CATEGORY_BY_MISSING_FLAG:
        return office_admission_rule_years(row)
    if target in {"AdmissionUnit", "AdmissionSchedule"}:
        if source_target == "HistoricalOutcome":
            return office_historical_outcome_years(row)
        return office_admission_rule_years(row)
    return []


def office_historical_outcome_years(row: dict[str, str]) -> list[str]:
    hanil_application_status_years = hanil_application_status_collection_years(row)
    if hanil_application_status_years:
        return hanil_application_status_years
    text = " ".join([office_candidate_guard_text(row), office_candidate_source_text_sample(row)])
    simulation_result_years = sorted(
        set(
            re.findall(
                r"(20\d{2})\s*학년도.{0,80}최종\s*합격자.{0,80}실제\s*등급.{0,80}시뮬레이션",
                text,
            )
        )
    )
    if simulation_result_years:
        return simulation_result_years
    recent_two_years = recent_two_year_outcome_years(text)
    if recent_two_years:
        return recent_two_years
    years = {match[0] for match in HISTORICAL_OUTCOME_TITLE_YEAR_PATTERN.findall(text)}
    years.update(re.findall(r"(20\d{2})\s*년도\s*입시\s*지원\s*현황", text))
    years.update(
        re.findall(
            r"(20\d{2})\s*학년도.{0,40}?(?:최종\s*합격자|실제\s*등급|평균\s*등급|80\s*%\s*등급)",
            text,
        )
    )
    compact_text = re.sub(r"\s+", "", text)
    years.update(re.findall(r"(20\d{2})년도입시지원현황", compact_text))
    years.update(match[0] for match in HISTORICAL_OUTCOME_TITLE_YEAR_PATTERN.findall(compact_text))
    guide_years = {int(year) for year, _ in GUIDE_TITLE_YEAR_PATTERN.findall(text)}
    filename_years = {int(year) for year in GUIDE_FILENAME_YEAR_PATTERN.findall(text)}
    if "전년도" in text and guide_years:
        years.update(str(year - 1) for year in guide_years if 2000 <= year - 1 <= 2099)
    if "전년도" in text:
        years.update(str(year - 1) for year in filename_years if 2000 <= year - 1 <= 2099)
    if years:
        return sorted(years)
    if (
        normalize_text(row.get("evidenceTarget")) == "HistoricalOutcome"
        and "admission_result" in normalize_text(row.get("evidenceRole"))
        and filename_years
    ):
        return [str(max(filename_years) - 1)]
    detected_years = split_joined(row.get("detectedAdmissionYears"))
    if "regular_admission_guide" in text and "전년도" in text:
        guide_year_candidates = [
            int(year)
            for year in detected_years
            if int_or_none(year) is not None and 2021 <= int(year) <= 2027
        ]
        if guide_year_candidates:
            return [str(max(guide_year_candidates) - 1)]
    return detected_years


def office_text_year_mismatches_gap(
    gap: dict[str, str],
    row: dict[str, str],
    match_scope: str,
) -> bool:
    if match_scope != "admission_office_collection_year":
        return False
    if not is_direct_admission_office_evidence_gap(gap):
        return False
    gap_year = int_or_none(gap.get("admissionYear"))
    if gap_year is None:
        return False
    text_years = office_candidate_context_years(row)
    if not text_years or gap_year in text_years:
        return False
    return max(text_years) <= gap_year - 1


def office_candidate_context_years(row: dict[str, str]) -> list[int]:
    text = " ".join(
        normalize_text(row.get(key))
        for key in [
            "textPreview",
            "evidenceSummary",
            "draftFlags",
            "blockerFlags",
            "promotionAction",
            "evidenceRole",
            "sourceLinkRoles",
            "sourceDocumentKinds",
        ]
        if normalize_text(row.get(key))
    )
    text = " ".join([text, office_candidate_source_text_sample(row)])
    years: list[int] = []
    for value in re.findall(r"20\d{2}", text):
        year = int_or_none(value)
        if year is not None and 2021 <= year <= 2028 and year not in years:
            years.append(year)
    return years


def office_candidate_source_text_sample(row: dict[str, str], limit: int = 20000) -> str:
    for source_path in split_joined(row.get("sourcePaths") or row.get("sourcePath")):
        if not source_path:
            continue
        if source_path in OFFICE_SOURCE_TEXT_CACHE:
            return OFFICE_SOURCE_TEXT_CACHE[source_path]
        path = Path(source_path)
        candidates = [path, Path.cwd() / path]
        repo_root = find_repo_root(Path.cwd())
        candidates.append(repo_root / path)
        for candidate in candidates:
            if not candidate.exists() or not candidate.is_file():
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="ignore")[:limit]
            except OSError:
                continue
            text = normalize_text(text)
            OFFICE_SOURCE_TEXT_CACHE[source_path] = text
            return text
    return ""


def recent_two_year_outcome_years(text: str) -> list[str]:
    match = re.search(
        r"(20\d{2})\s*학\s*년도.{0,80}?모집\s*현황.{0,40}?최근\s*2\s*개년\s*입시\s*결과",
        text,
        re.I,
    )
    if not match:
        return []
    headline_year = int(match.group(1))
    return [str(headline_year - 2), str(headline_year - 1)]


def hanil_application_status_collection_years(row: dict[str, str]) -> list[str]:
    source_labels = normalize_text(row.get("sourceLabels"))
    if "gap_manual_hanil_docs" not in source_labels:
        return []
    text = office_candidate_guard_text(row)
    if not (
        "hanil.ac.kr" in text
        and "html-results-gap_manual_hanil" in text
        and "admission_result_html" in normalize_text(row.get("sourceLinkRoles"))
    ):
        return []
    collection_years = [
        year
        for year in split_joined(row.get("collectionYears"))
        if re.fullmatch(r"20\d{2}", year)
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years if len(unique_years) == 1 else []


def office_admission_rule_years(row: dict[str, str]) -> list[str]:
    text = office_candidate_guard_text(row)
    years = set(year for year, _ in GUIDE_TITLE_YEAR_PATTERN.findall(text))
    compact_text = re.sub(r"\s+", "", text)
    years.update(year for year, _ in GUIDE_TITLE_YEAR_PATTERN.findall(compact_text))
    if years:
        return sorted(years)
    detected_years = split_joined(row.get("detectedAdmissionYears"))
    if "regular_admission_guide" in text:
        guide_year_candidates = [
            int(year)
            for year in detected_years
            if int_or_none(year) is not None and 2021 <= int(year) <= 2027
        ]
        if guide_year_candidates:
            return [str(max(guide_year_candidates))]
    return detected_years


def role_matches_rule_category(role: str, required_rule_category: str) -> bool:
    role_markers = {
        "csat_reflection": ["csat", "수능", "reflection"],
        "recruitment_quota": ["quota", "모집인원"],
        "screening_method": ["screening", "전형방법", "evaluation"],
        "school_record_reflection": ["school", "학생부", "record"],
        "eligibility": ["eligibility", "지원자격", "qualification"],
    }.get(required_rule_category, [required_rule_category])
    return required_rule_category in role or any(marker in role for marker in role_markers)


SOURCE_GUARD_FIELDS = (
    "attachmentUrl",
    "attachmentUrls",
    "rawPath",
    "rawPaths",
    "sourceCandidateUrl",
    "sourceCandidateUrls",
    "sourceLabels",
    "sourcePath",
    "sourcePaths",
    "sourceUrl",
    "sourceUrls",
    "viewUrl",
)


def row_has_blocked_helper_source(row: dict[str, Any]) -> bool:
    return any(
        BLOCKED_HELPER_SOURCE_PATTERN.search(join_values(row.get(field_name)))
        for field_name in SOURCE_GUARD_FIELDS
    )


def dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        row = candidate["source"]
        key = "|".join(
            [
                candidate["sourceKind"],
                normalize_text(row.get("sourceArtifact")),
                normalize_text(row.get("sourceRecordId") or row.get("evidenceCandidateSha256")),
                normalize_text(row.get("sourceUrls") or row.get("sourceCandidateUrl") or row.get("sourceUrl")),
                normalize_text(row.get("attachmentUrls") or row.get("attachmentUrl")),
                normalize_text(row.get("rawPaths") or row.get("rawPath")),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def make_no_source_row(gap: dict[str, str]) -> dict[str, Any]:
    base = gap_base(gap)
    base.update(
        {
            "gapSourceCandidateId": deterministic_uuid(f"gap-source:none:{gap.get('gapActionId')}"),
            "artifactType": "foundation_gap_source_candidate",
            "candidateRank": 1,
            "candidateStatus": "source_collection_required",
            "candidateMatchType": "no_existing_source_candidate",
            "candidateMatchScore": 0,
            "sourceKind": "",
            "sourceProvider": "",
            "sourceArtifact": "",
            "sourceRecordId": "",
            "sourceTargetEntity": "",
            "sourceRuleCategory": "",
            "sourceActionOrRole": "",
            "sourcePriorityTier": "",
            "sourceReviewPriorityScore": "",
            "sourceReviewStrength": "",
            "sourceConfidence": "",
            "sourceReviewStatus": "",
            "sourceYears": "",
            "sourceEvidenceSummary": "",
            "sourceUrls": "",
            "attachmentUrls": "",
            "rawPaths": "",
            "sourcePaths": "",
            "textPreview": "",
            "operatorNextStep": operator_next_step(gap, "source_collection_required"),
        }
    )
    return base


def make_source_row(gap: dict[str, str], candidate: dict[str, Any], rank: int) -> dict[str, Any]:
    source = candidate["source"]
    base = gap_base(gap)
    source_artifact = normalize_text(source.get("sourceArtifact")) or (
        "foundation_admission_office_evidence_links"
        if candidate["sourceKind"] == "admission_office_evidence"
        else ""
    )
    source_record_id = normalize_text(source.get("sourceRecordId") or source.get("evidenceCandidateSha256"))
    display_years = source_years(source) or split_joined(source.get("collectionYears"))
    if candidate["sourceKind"] == "admission_office_evidence":
        display_years = office_relevant_years_for_gap(gap, source) or display_years

    base.update(
        {
            "gapSourceCandidateId": deterministic_uuid(
                f"gap-source:{gap.get('gapActionId')}:{candidate['sourceKind']}:{source_artifact}:{source_record_id}:{rank}"
            ),
            "artifactType": "foundation_gap_source_candidate",
            "candidateRank": rank,
            "candidateStatus": "source_candidate_available",
            "candidateMatchType": candidate["matchType"],
            "candidateMatchScore": candidate["matchScore"],
            "sourceKind": candidate["sourceKind"],
            "sourceProvider": normalize_text(source.get("provider") or source.get("sourceProvider")),
            "sourceArtifact": source_artifact,
            "sourceRecordId": source_record_id,
            "sourceTargetEntity": normalize_text(source.get("targetEntity") or source.get("evidenceTarget")),
            "sourceRuleCategory": normalize_text(source.get("ruleCategory")),
            "sourceActionOrRole": normalize_text(source.get("promotionAction") or source.get("evidenceRole")),
            "sourcePriorityTier": normalize_text(source.get("priorityTier")),
            "sourceReviewPriorityScore": normalize_text(
                source.get("reviewPriorityScore") or source.get("reviewPriority")
            ),
            "sourceReviewStrength": normalize_text(source.get("reviewStrength")),
            "sourceConfidence": normalize_text(source.get("confidence")),
            "sourceReviewStatus": normalize_text(source.get("reviewStatus")),
            "sourceYears": join_values(display_years),
            "sourceEvidenceSummary": normalize_text(
                source.get("evidenceSummary")
                or source.get("textPreview")
                or source.get("draftFlags")
                or source.get("blockerFlags")
            )[:700],
            "sourceUrls": normalize_text(
                source.get("sourceUrls") or source.get("sourceCandidateUrl") or source.get("sourceUrl")
            ),
            "attachmentUrls": normalize_text(source.get("attachmentUrls") or source.get("attachmentUrl")),
            "rawPaths": normalize_text(source.get("rawPaths") or source.get("rawPath") or source.get("rawAttachmentPath")),
            "sourcePaths": normalize_text(source.get("sourcePaths") or source.get("sourcePath")),
            "textPreview": normalize_text(source.get("textPreview"))[:700],
            "operatorNextStep": operator_next_step(gap, "source_candidate_available"),
        }
    )
    return base


def gap_base(gap: dict[str, str]) -> dict[str, Any]:
    return {
        "gapActionId": normalize_text(gap.get("gapActionId")),
        "gapPriorityTier": normalize_text(gap.get("priorityTier")),
        "gapActionPriorityScore": int_or_none(gap.get("actionPriorityScore")) or 0,
        "universityKey": normalize_text(gap.get("universityKey")),
        "unvCd": normalize_text(gap.get("unvCd")),
        "universityName": normalize_text(gap.get("universityName")),
        "admissionYear": int_or_none(gap.get("admissionYear")) or "",
        "coverageTier": normalize_text(gap.get("coverageTier")),
        "coverageScore": int_or_none(gap.get("coverageScore")) or 0,
        "missingFlag": normalize_text(gap.get("missingFlag")),
        "gapCategory": normalize_text(gap.get("gapCategory")),
        "targetEntity": normalize_text(gap.get("targetEntity")),
        "recommendedAction": normalize_text(gap.get("recommendedAction")),
        "expectedAvailability": normalize_text(gap.get("expectedAvailability")),
        "gapBlockingReason": normalize_text(gap.get("blockingReason")),
    }


def operator_next_step(gap: dict[str, str], candidate_status: str) -> str:
    action = normalize_text(gap.get("recommendedAction"))
    if candidate_status == "source_collection_required":
        return f"{action}: collect new public source or re-run provider crawler for sourceHint={gap.get('sourceHint')}"
    if action.startswith("collect_or_parse"):
        return f"{action}: inspect matched source, improve parser/year mapping, then rebuild foundation artifacts"
    return f"{action}: inspect matched source and resolve review before DB promotion"


def source_years(row: dict[str, str]) -> list[str]:
    values: list[str] = []
    for key in ["admissionYear", "academicYear", "year", "firstYear", "detectedAdmissionYears", "collectionYears"]:
        for value in split_joined(row.get(key)):
            if re.fullmatch(r"\d{4}", value):
                values.append(value)
    return sorted(set(values))


def summarize(
    repo_root: Path,
    inputs: list[Path],
    source_rows: list[dict[str, Any]],
    gap_rows: list[dict[str, str]],
    included_priority_tiers: list[str],
    max_candidates_per_gap: int,
) -> dict[str, Any]:
    gap_ids_with_sources = {
        str(row.get("gapActionId"))
        for row in source_rows
        if row.get("candidateStatus") == "source_candidate_available"
    }
    all_gap_ids = {str(row.get("gapActionId")) for row in gap_rows}
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_source_candidates_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in inputs
        ],
        "includedGapPriorityTiers": included_priority_tiers,
        "maxCandidatesPerGap": max_candidates_per_gap,
        "gapActions": {
            "total": len(all_gap_ids),
            "withSourceCandidates": len(gap_ids_with_sources),
            "withoutSourceCandidates": len(all_gap_ids - gap_ids_with_sources),
        },
        "sourceCandidateRows": {
            "total": len(source_rows),
            "available": sum(1 for row in source_rows if row.get("candidateStatus") == "source_candidate_available"),
            "sourceCollectionRequired": sum(
                1 for row in source_rows if row.get("candidateStatus") == "source_collection_required"
            ),
        },
        "byCandidateStatus": counter_rows(Counter(str(row.get("candidateStatus")) for row in source_rows)),
        "byCandidateMatchType": counter_rows(Counter(str(row.get("candidateMatchType")) for row in source_rows), 40),
        "byMissingFlag": counter_rows(Counter(str(row.get("missingFlag")) for row in source_rows), 30),
        "byTargetEntity": counter_rows(Counter(str(row.get("targetEntity")) for row in source_rows), 30),
        "byAdmissionYear": dict(sorted(Counter(str(row.get("admissionYear")) for row in source_rows).items())),
        "bySourceArtifact": counter_rows(
            Counter(str(row.get("sourceArtifact") or "no_existing_source_candidate") for row in source_rows),
            30,
        ),
        "notes": [
            "Rows are source-level candidates for gap actions, not verified fixes.",
            "A gap can have up to maxCandidatesPerGap source candidates; no-source rows indicate crawler/source collection work remains.",
            "candidateMatchScore is heuristic and should be used for review ordering only.",
        ],
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "gapSourceCandidateId",
        "artifactType",
        "gapActionId",
        "gapPriorityTier",
        "gapActionPriorityScore",
        "universityKey",
        "unvCd",
        "universityName",
        "admissionYear",
        "coverageTier",
        "coverageScore",
        "missingFlag",
        "gapCategory",
        "targetEntity",
        "recommendedAction",
        "expectedAvailability",
        "gapBlockingReason",
        "candidateRank",
        "candidateStatus",
        "candidateMatchType",
        "candidateMatchScore",
        "sourceKind",
        "sourceProvider",
        "sourceArtifact",
        "sourceRecordId",
        "sourceTargetEntity",
        "sourceRuleCategory",
        "sourceActionOrRole",
        "sourcePriorityTier",
        "sourceReviewPriorityScore",
        "sourceReviewStrength",
        "sourceConfidence",
        "sourceReviewStatus",
        "sourceYears",
        "sourceEvidenceSummary",
        "sourceUrls",
        "attachmentUrls",
        "rawPaths",
        "sourcePaths",
        "textPreview",
        "operatorNextStep",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def split_csv_arg(value: str) -> list[str]:
    return [normalize_text(part) for part in value.split(",") if normalize_text(part)]


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [part for part in re.split(r"[|,;]", text) if part]


def join_values(values: Any) -> str:
    if isinstance(values, str):
        return "|".join(split_joined(values))
    if not values:
        return ""
    return "|".join(str(value) for value in values if normalize_text(value))


def priority_sort(value: Any) -> int:
    return {"p0": 0, "p1": 1, "p2": 2, "p3": 3}.get(normalize_text(value), 9)


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def bool_value(value: Any) -> bool:
    return normalize_text(value).lower() in {"1", "true", "yes", "y"}


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
