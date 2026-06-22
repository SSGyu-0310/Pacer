#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import glob
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
DEFAULT_GAP_COLLECTION_TARGETS = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_collection_targets.csv"
)
DEFAULT_ADIGA_IMAGE_REFERENCES = (
    "packages/reference-data/data/public/adiga/"
    "adiga_image_source_references.csv"
)
DEFAULT_ADIGA_IMAGE_OCR_EVIDENCE = (
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_image_ocr_evidence_index.jsonl"
)
DEFAULT_ADMISSION_OFFICE_PAGE_IMAGE_GLOBS = [
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_low_text_pdf_page_images_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-file-attachments/"
    "university_admission_low_text_pdf_page_images_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-html-route-nested-high-value/"
    "university_admission_low_text_pdf_page_images_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-ready-attachments-20260608/"
    "university_admission_low_text_pdf_page_images_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-ready-detail-fetch-attachments-20260608/"
    "university_admission_low_text_pdf_page_images_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/extracted-zip-entries/"
    "university_admission_low_text_pdf_page_images_*.jsonl",
]
DEFAULT_ADMISSION_OFFICE_OCR_EVIDENCE_GLOBS = [
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_low_text_pdf_page_ocr_evidence_index_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-file-attachments/"
    "university_admission_low_text_pdf_page_ocr_evidence_index_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-html-route-nested-high-value/"
    "university_admission_low_text_pdf_page_ocr_evidence_index_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-ready-attachments-20260608/"
    "university_admission_low_text_pdf_page_ocr_evidence_index_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-ready-detail-fetch-attachments-20260608/"
    "university_admission_low_text_pdf_page_ocr_evidence_index_*.jsonl",
    "packages/reference-data/data/public/university-admission-sites/extracted-zip-entries/"
    "university_admission_low_text_pdf_page_ocr_evidence_index_*.jsonl",
]

OUTPUT_JSONL = "foundation_gap_image_source_candidates.jsonl"
OUTPUT_CSV = "foundation_gap_image_source_candidates.csv"
OUTPUT_SUMMARY = "foundation_gap_image_source_candidates_summary.json"

MIN_REVIEW_IMAGE_DIMENSION = 120
MIN_REVIEW_IMAGE_BYTES = 8_000
TARGET_RELEVANCE = {
    "HistoricalOutcome": {
        "missing_historical_outcomes",
        "missing_outcome_scores",
        "missing_quota_competition",
        "missing_admission_units",
    },
    "AdmissionRule": {
        "missing_csat_rule_draft",
        "missing_recruitment_quota_draft",
        "missing_screening_method_draft",
        "missing_school_record_rule_draft",
        "missing_eligibility_rule_draft",
    },
    "AdmissionSchedule": {
        "missing_schedule_draft",
    },
    "AdmissionUnit": {
        "missing_admission_units",
    },
    "AdmissionOfficeEvidence": {
        "missing_admission_office_detected_year_evidence",
    },
    "OCRReviewQueue": set(),
    "ReviewQueue": set(),
}
ADMISSION_POSITIVE_OCR_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전형\s*결과|경쟁률|모집\s*단위|모집단위|모집\s*학과|"
    r"모집\s*인원|지원\s*인원|등록\s*인원|충원|예비|환산|백분위|수능|"
    r"전형\s*요소|반영\s*비율|모집\s*요강|입학\s*전형|원서\s*접수|합격자"
)
HISTORICAL_OUTCOME_STRONG_OCR_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전형\s*결과|최종\s*결과|경쟁률|지원\s*인원|"
    r"등록\s*인원|최종\s*등록자|충원\s*합격|충원\s*/\s*합격|예비\s*순위|"
    r"70\s*%\s*cut|백분위|환산|합격자\s*성적",
    re.I,
)
HISTORICAL_OUTCOME_RESULT_TABLE_OCR_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전형\s*결과|최종\s*결과|경쟁률|지원\s*인원|"
    r"등록\s*인원|충원\s*합격|충원\s*/\s*합격|예비\s*순위|"
    r"70\s*%\s*cut|70\s*%|합격자\s*성적|대학별\s*환산|"
    r"평균\s*성적|최저\s*성적|최고\s*성적|최종\s*등록자.{0,30}(성적|평균|환산|백분위|cut)",
    re.I,
)
HISTORICAL_OUTCOME_RULE_NOISE_OCR_PATTERN = re.compile(
    r"성적\s*반영\s*방법|학생부\s*성적\s*반영|검정고시.*성적\s*반영|"
    r"성적\s*산출\s*방법|석차\s*등급\s*산출|등급\s*점수|가산점|"
    r"진로\s*선택\s*과목|반영\s*교과|반영교과|선발\s*원칙|사정\s*순위|"
    r"학교\s*생활\s*기록부\s*기재\s*금지|기재\s*금지\s*항목|공인\s*어학\s*시험|"
    r"수상\s*실적|모의\s*고사|전국\s*연합\s*학력\s*평가|창업\s*장학금|"
    r"창업\s*포인트|창업\s*활동|학사\s*안내|등록\s*안내|등록금|장학금|"
    r"기숙사|우리\s*학교\s*환산\s*등급|환산\s*학생부\s*교과\s*성적\s*등급|"
    r"학생부\s*반영\s*방법|수능\s*최저\s*기준|성적\s*처리",
    re.I,
)
HISTORICAL_OUTCOME_NON_FRESHMAN_OCR_PATTERN = re.compile(
    r"편입\s*학|전적\s*대학\s*성적|전적대학성적",
    re.I,
)
HISTORICAL_OUTCOME_NOTICE_ONLY_OCR_PATTERN = re.compile(
    r"선발\s*원칙|등록\s*안내|등록금\s*납부|등록\s*포기|"
    r"합격자\s*(?:발표|등록|안내)|충원\s*합격자\s*발표|면접\s*고사",
    re.I,
)
HISTORICAL_OUTCOME_RESULT_SIGNAL_OCR_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전형\s*결과|모집\s*결과|경쟁률|"
    r"최종\s*등록자|합격자\s*성적|성적\s*통계|70\s*%\s*cut|"
    r"백분위|환산",
    re.I,
)
HISTORICAL_OUTCOME_QUOTA_COMPETITION_OCR_PATTERN = re.compile(
    r"모집\s*(?:인원|정원)|지원\s*(?:인원|자)|경쟁\s*률|경정률|경생통|"
    r"모집\s*\d+\s*(?:명|/)|지원\s*\d+\s*(?:명|/)|\d+(?:\.\d+)?\s*:\s*1",
    re.I,
)
ADMISSION_RULE_STRONG_OCR_PATTERN = re.compile(
    r"수능\s*성적\s*산출|수능\s*반영|전형\s*요소.{0,20}반영|반영\s*비율|"
    r"영역별\s*반영|선발\s*방법|최저\s*학력\s*기준|학생부\s*반영|"
    r"교과\s*성적|석차\s*등급",
    re.I,
)
SMALL_FORMULA_OR_LABEL_OCR_PATTERN = re.compile(
    r"Σ|\\frac|frac|반영\s*교과|반영교과|반영\s*비[율온]|교과.*반영",
    re.I,
)
NON_ADMISSION_LOW_SIGNAL_OCR_PATTERN = re.compile(
    r"전공\s*역량\s*강화|재학생|학생\s*주도\s*프로그램|프로그램\s*내용|"
    r"참여\s*인원|참여자\s*모집|참여\s*후기|만족도|도서관|집단\s*상담|"
    r"학생\s*상담\s*센터|학생상[담당]셋터|상담\s*센터|상당셋터|"
    r"대학\s*혁신\s*사업|대학형신사업|혁신\s*사업|서포터즈|"
    r"캠퍼스\s*안내|간호\s*시뮬레이션\s*센터|간호시물레이션셋터|"
    r"Student\s+Union|학우|제학생|대학\s*생활|마음\s*건강|"
    r"취업\s*지원|국제\s*교류\s*프로그램|총장|축장|체험\s*부스|"
    r"NEWSLETTER|선배찬스|튜터링|멘토링|트터림|프로그램에\s*참여|"
    r"교육\s*봉사|문화\s*탐방|응급실|옥급실|신속\s*대응|대학형신지원사업단|"
    r"학부\s*개요|학과\s*소개|학부\s*소개|입학\s*담당|입학당당|전형료|"
    r"장학금|등록금|수업료|학사\s*제도|모집\s*단위\s*이동|전과\s*제도|"
    r"교육\s*과정|교수\s*/|Dept\.|신입생\s*등록자|입학\s*후\s*생활|"
    r"기숙사|건강\s*검진|결핵\s*검|"
    r"러브커버스|SCHOOL\b|NAMSEOUL\s+UNIVERSITY|HANSUNG\s+UNIVERSITY|"
    r"DEO\s+SOLI\s+GLORIA|교통\s*안내|대중\s*교통",
    re.I,
)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    collection_targets_path = resolve(repo_root, args.gap_collection_targets)
    image_refs_path = resolve(repo_root, args.adiga_image_references)
    ocr_evidence_path = resolve(repo_root, args.adiga_image_ocr_evidence)
    office_page_image_paths = resolve_globs(repo_root, args.admission_office_page_images_glob)
    office_ocr_evidence_paths = resolve_globs(repo_root, args.admission_office_ocr_evidence_glob)
    foundation_dir.mkdir(parents=True, exist_ok=True)

    collection_targets = read_csv(collection_targets_path)
    adiga_targets = [
        row
        for row in collection_targets
        if normalize_text(row.get("collectionRoute")) == "adiga_selection_detail"
    ]
    image_refs = read_csv(image_refs_path)
    ocr_evidence_rows = read_jsonl(ocr_evidence_path)
    office_page_rows = read_jsonl_many(office_page_image_paths)
    office_ocr_rows = read_jsonl_many(office_ocr_evidence_paths)

    candidates = build_adiga_candidates(adiga_targets, image_refs, ocr_evidence_rows)
    candidates.extend(
        build_admission_office_page_candidates(
            collection_targets=collection_targets,
            page_rows=office_page_rows,
            ocr_rows=office_ocr_rows,
        )
    )
    candidates.sort(
        key=lambda row: (
            -int_or_none(row.get("imageReviewPriorityScore") or 0),
            str(row.get("universityName") or ""),
            int_or_none(row.get("admissionYear")) or 9999,
            str(row.get("imageEvidenceTarget") or ""),
            str(row.get("canonicalImageKey") or ""),
        )
    )

    write_jsonl(foundation_dir / OUTPUT_JSONL, candidates)
    write_csv(foundation_dir / OUTPUT_CSV, candidates)
    summary = summarize(
        repo_root=repo_root,
        inputs=[
            collection_targets_path,
            image_refs_path,
            ocr_evidence_path,
            *office_page_image_paths,
            *office_ocr_evidence_paths,
        ],
        collection_targets=collection_targets,
        adiga_targets=adiga_targets,
        image_refs=image_refs,
        office_page_rows=office_page_rows,
        office_ocr_rows=office_ocr_rows,
        candidates=candidates,
    )
    (foundation_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap image source candidates complete. "
        f"adigaTargets={len(adiga_targets)} imageCandidates={len(candidates)} "
        f"officeOcrPages={len(office_ocr_rows)} "
        f"withOcr={summary['imageSourceCandidates']['withOcrEvidence']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--gap-collection-targets", default=DEFAULT_GAP_COLLECTION_TARGETS)
    parser.add_argument("--adiga-image-references", default=DEFAULT_ADIGA_IMAGE_REFERENCES)
    parser.add_argument("--adiga-image-ocr-evidence", default=DEFAULT_ADIGA_IMAGE_OCR_EVIDENCE)
    parser.add_argument(
        "--admission-office-page-images-glob",
        action="append",
        default=list(DEFAULT_ADMISSION_OFFICE_PAGE_IMAGE_GLOBS),
        help="Glob(s) for rendered low-text admission-office PDF page image manifests.",
    )
    parser.add_argument(
        "--admission-office-ocr-evidence-glob",
        action="append",
        default=list(DEFAULT_ADMISSION_OFFICE_OCR_EVIDENCE_GLOBS),
        help="Glob(s) for OCR evidence indexes built from rendered admission-office PDF pages.",
    )
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


def resolve_globs(repo_root: Path, values: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[str] = set()
    for value in values:
        for pattern in split_glob_arg(value):
            pattern_path = resolve(repo_root, pattern)
            for match in sorted(glob.glob(str(pattern_path))):
                path = Path(match)
                key = str(path.resolve())
                if key not in seen:
                    seen.add(key)
                    paths.append(path)
    return paths


def split_glob_arg(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def build_adiga_candidates(
    adiga_targets: list[dict[str, str]],
    image_refs: list[dict[str, str]],
    ocr_evidence_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets_by_group = {
        (normalize_text(row.get("unvCd")), normalize_text(row.get("admissionYear"))): row
        for row in adiga_targets
    }
    refs_by_group: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in image_refs:
        group = (normalize_text(row.get("unvCd")), normalize_text(row.get("year")))
        if group in targets_by_group:
            refs_by_group[group].append(row)

    ocr_by_key = {
        normalize_text(row.get("canonicalImageKey")): row
        for row in ocr_evidence_rows
        if normalize_text(row.get("canonicalImageKey"))
    }
    years_by_university_image_key: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in image_refs:
        university_code = normalize_text(row.get("unvCd"))
        image_key = normalize_text(row.get("canonicalImageKey"))
        year = normalize_text(row.get("year"))
        if university_code and image_key and year:
            years_by_university_image_key[(university_code, image_key)].add(year)

    candidates: list[dict[str, Any]] = []
    for group, target in targets_by_group.items():
        for ref in refs_by_group.get(group, []):
            ocr = ocr_by_key.get(normalize_text(ref.get("canonicalImageKey")))
            if is_repeated_adiga_brand_image_without_ocr(ref, ocr, years_by_university_image_key):
                continue
            if not is_reviewable_image(ref, ocr):
                continue
            evidence_target = normalize_text((ocr or {}).get("evidenceTarget")) or "OCRReviewQueue"
            if not is_relevant_image_evidence_to_target(target, evidence_target):
                continue
            candidates.append(make_adiga_candidate(target, ref, ocr))
    return candidates


def build_admission_office_page_candidates(
    collection_targets: list[dict[str, str]],
    page_rows: list[dict[str, Any]],
    ocr_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets_by_group: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in collection_targets:
        group = (normalize_text(row.get("unvCd")), normalize_text(row.get("admissionYear")))
        if group[0] and group[1]:
            targets_by_group[group].append(row)

    pages_by_scope_and_sha: dict[tuple[str, str], dict[str, Any]] = {}
    for row in page_rows:
        scope = admission_office_scope(row)
        sha = normalize_text(row.get("pageImageSha256"))
        if scope and sha:
            pages_by_scope_and_sha[(scope, sha)] = row

    candidates: list[dict[str, Any]] = []
    seen_candidate_keys: set[tuple[str, str, str, str, str, str]] = set()
    for ocr in ocr_rows:
        if is_low_signal_non_admission_ocr(ocr):
            continue
        if is_misclassified_admission_ocr(ocr):
            continue
        group = (normalize_text(ocr.get("unvCd")), normalize_text(ocr.get("year")))
        if group not in targets_by_group:
            continue
        scope = admission_office_scope(ocr)
        source_specific = ocr.get("sourceSpecific") if isinstance(ocr.get("sourceSpecific"), dict) else {}
        page_sha = normalize_text(source_specific.get("pageImageSha256"))
        page = pages_by_scope_and_sha.get((scope, page_sha), {})
        for target in targets_by_group[group]:
            if is_relevant_office_ocr_page(target, ocr):
                candidate_key = (
                    group[0],
                    group[1],
                    scope,
                    page_sha or normalize_text(ocr.get("sourcePath")),
                    normalize_text(ocr.get("evidenceTarget")) or "OCRReviewQueue",
                    normalize_text(ocr.get("evidenceRole")) or "pdf_page_image_ocr",
                )
                if candidate_key in seen_candidate_keys:
                    continue
                seen_candidate_keys.add(candidate_key)
                candidates.append(make_admission_office_page_candidate(target, ocr, page, scope))
    return candidates


def is_relevant_office_ocr_page(target: dict[str, str], ocr: dict[str, Any]) -> bool:
    if is_temporally_mismatched_office_ocr_page(target, ocr):
        return False
    if is_metric_mismatched_historical_outcome_ocr_page(target, ocr):
        return False
    evidence_target = normalize_text(ocr.get("evidenceTarget")) or "OCRReviewQueue"
    return is_relevant_image_evidence_to_target(target, evidence_target)


def is_temporally_mismatched_office_ocr_page(
    target: dict[str, str], ocr: dict[str, Any]
) -> bool:
    target_year = int_or_none(target.get("admissionYear"))
    if target_year is None:
        return False
    text = normalize_text(ocr.get("textPreview") or ocr.get("text") or "")
    if re.search(rf"{target_year}\s*학\s*년\s*도", text):
        return False
    text_years = [int(value) for value in re.findall(r"20\d{2}", text)]
    if text_years and target_year not in text_years and max(text_years) <= target_year - 3:
        return True
    source_context = normalize_text(
        " ".join(
            [
                str(ocr.get("sourceCandidateUrl") or ""),
                str(ocr.get("attachmentUrl") or ""),
                str(ocr.get("detectedDocumentRole") or ""),
            ]
        )
    )
    source_years = [int(value) for value in re.findall(r"20\d{2}", source_context)]
    if not source_years:
        return False
    return min(source_years) >= target_year + 3


def is_metric_mismatched_historical_outcome_ocr_page(
    target: dict[str, str], ocr: dict[str, Any]
) -> bool:
    evidence_target = normalize_text(ocr.get("evidenceTarget")) or "OCRReviewQueue"
    if evidence_target != "HistoricalOutcome":
        return False
    missing_flags = set(split_joined(target.get("missingFlags")))
    if "missing_quota_competition" not in missing_flags:
        return False
    text = normalize_text(ocr.get("textPreview") or ocr.get("text") or "")
    if not text:
        return False
    return not bool(HISTORICAL_OUTCOME_QUOTA_COMPETITION_OCR_PATTERN.search(text))


def is_relevant_image_evidence_to_target(target: dict[str, str], evidence_target: str) -> bool:
    if evidence_target == "OCRReviewQueue":
        target_entities = set(split_joined(target.get("targetEntities")))
        missing_flags = set(split_joined(target.get("missingFlags")))
        return bool(
            target_entities.intersection({"HistoricalOutcome", "AdmissionRule", "AdmissionUnit"})
            or missing_flags.intersection(
                {
                    "missing_historical_outcomes",
                    "missing_outcome_scores",
                    "missing_quota_competition",
                    "missing_admission_units",
                    "missing_csat_rule_draft",
                    "missing_recruitment_quota_draft",
                    "missing_screening_method_draft",
                    "missing_school_record_rule_draft",
                    "missing_eligibility_rule_draft",
                }
            )
        )
    target_entities = set(split_joined(target.get("targetEntities")))
    if evidence_target in target_entities:
        return True
    missing_flags = set(split_joined(target.get("missingFlags")))
    return bool(TARGET_RELEVANCE.get(evidence_target, set()).intersection(missing_flags))


def make_admission_office_page_candidate(
    target: dict[str, str],
    ocr: dict[str, Any],
    page: dict[str, Any],
    scope: str,
) -> dict[str, Any]:
    missing_flags = split_joined(target.get("missingFlags"))
    source_specific = ocr.get("sourceSpecific") if isinstance(ocr.get("sourceSpecific"), dict) else {}
    evidence_target = normalize_text(ocr.get("evidenceTarget")) or "OCRReviewQueue"
    evidence_role = normalize_text(ocr.get("evidenceRole")) or "pdf_page_image_ocr"
    ocr_priority = int_or_none(ocr.get("priorityScore")) or 0
    page_sha = first_nonempty_any(source_specific.get("pageImageSha256"), page.get("pageImageSha256"))
    page_path = first_nonempty_any(source_specific.get("pageImagePath"), page.get("pageImagePath"))
    page_bytes = int_or_none(source_specific.get("pageImageBytes")) or int_or_none(page.get("pageImageBytes")) or 0
    raw_pdf_path = first_nonempty_any(ocr.get("rawPath"), page.get("rawPdfPath"))
    image_score = office_page_review_score(
        page_bytes=page_bytes,
        evidence_target=evidence_target,
        evidence_role=evidence_role,
        ocr_priority=ocr_priority,
        missing_flags=missing_flags,
        source_scope=scope,
    )
    return {
        "gapImageSourceCandidateId": deterministic_uuid(
            "gap-image-source:admission-office-page:"
            f"{target.get('collectionTargetId')}:{scope}:{page_sha}:{ocr.get('sourcePath')}"
        ),
        "artifactType": "foundation_gap_image_source_candidate",
        "collectionTargetId": normalize_text(target.get("collectionTargetId")),
        "priorityTier": normalize_text(target.get("priorityTier")) or "p0",
        "imageReviewPriorityScore": image_score,
        "candidateStatus": "ocr_evidence_available",
        "imageSourceKind": "admission_office_low_text_pdf_page",
        "sourceProvider": normalize_text(ocr.get("provider")) or "university-admission-office",
        "sourceArtifactScope": scope,
        "unvCd": normalize_text(target.get("unvCd")),
        "universityName": normalize_text(target.get("universityName")),
        "admissionYear": int_or_none(target.get("admissionYear")) or normalize_text(target.get("admissionYear")),
        "gapCount": int_or_none(target.get("gapCount")) or 0,
        "missingFlags": normalize_text(target.get("missingFlags")),
        "targetEntities": normalize_text(target.get("targetEntities")),
        "recommendedActions": normalize_text(target.get("recommendedActions")),
        "canonicalImageKey": f"{scope}:{page_sha}" if page_sha else normalize_text(ocr.get("sourcePath")),
        "imageUrl": "",
        "rawImagePath": page_path,
        "detailRawPath": raw_pdf_path,
        "downloadStatus": normalize_text(page.get("renderStatus")) or "rendered_pdf_page_image",
        "detectedImageKind": "pdf_page_png",
        "width": 0,
        "height": 0,
        "imageBytes": page_bytes,
        "imageEvidenceTarget": evidence_target,
        "imageEvidenceRole": evidence_role,
        "ocrPriorityScore": ocr_priority,
        "ocrEvidenceSha256": normalize_text(ocr.get("evidenceSha256")),
        "ocrSourcePath": normalize_text(ocr.get("sourcePath")),
        "ocrTextPreview": normalize_text(ocr.get("textPreview"))[:500],
        "matchedKeywords": join_values(ocr.get("matchedKeywords")),
        "sourceLinkRole": normalize_text(ocr.get("sourceLinkRole")),
        "attachmentRole": normalize_text(ocr.get("attachmentRole")),
        "detectedDocumentRole": normalize_text(ocr.get("detectedDocumentRole")),
        "pageNumber": int_or_none(source_specific.get("pageNumber")) or int_or_none(page.get("pageNumber")) or 0,
        "pageImagePath": page_path,
        "pageImageSha256": page_sha,
        "rawPdfPath": raw_pdf_path,
        "rawPdfSha256": first_nonempty_any(source_specific.get("rawPdfSha256"), page.get("rawPdfSha256")),
        "sourceCandidateUrl": normalize_text(ocr.get("sourceCandidateUrl") or page.get("sourceCandidateUrl")),
        "attachmentUrl": normalize_text(ocr.get("attachmentUrl") or page.get("attachmentUrl")),
        "candidateReason": office_page_candidate_reason(
            scope=scope,
            page_bytes=page_bytes,
            evidence_target=evidence_target,
            evidence_role=evidence_role,
            missing_flags=missing_flags,
            ocr=ocr,
        ),
        "operatorNextStep": operator_next_step(evidence_target, evidence_role, ocr),
    }


def make_adiga_candidate(
    target: dict[str, str],
    ref: dict[str, str],
    ocr: dict[str, Any] | None,
) -> dict[str, Any]:
    missing_flags = split_joined(target.get("missingFlags"))
    evidence_target = normalize_text((ocr or {}).get("evidenceTarget")) or "OCRReviewQueue"
    evidence_role = normalize_text((ocr or {}).get("evidenceRole")) or "image_review_required"
    ocr_priority = int_or_none((ocr or {}).get("priorityScore")) or 0
    image_score = image_review_score(ref, evidence_target, evidence_role, ocr_priority, missing_flags)
    candidate_status = "ocr_evidence_available" if ocr else "image_review_required_no_ocr_evidence"
    return {
        "gapImageSourceCandidateId": deterministic_uuid(
            "gap-image-source:"
            f"{target.get('collectionTargetId')}:{ref.get('canonicalImageKey')}:{ref.get('rawImagePath')}"
        ),
        "artifactType": "foundation_gap_image_source_candidate",
        "collectionTargetId": normalize_text(target.get("collectionTargetId")),
        "priorityTier": normalize_text(target.get("priorityTier")) or "p0",
        "imageReviewPriorityScore": image_score,
        "candidateStatus": candidate_status,
        "imageSourceKind": "adiga_detail_image",
        "sourceProvider": "adiga",
        "sourceArtifactScope": "adiga_selection_detail",
        "unvCd": normalize_text(target.get("unvCd")),
        "universityName": normalize_text(target.get("universityName")),
        "admissionYear": int_or_none(target.get("admissionYear")) or normalize_text(target.get("admissionYear")),
        "gapCount": int_or_none(target.get("gapCount")) or 0,
        "missingFlags": normalize_text(target.get("missingFlags")),
        "targetEntities": normalize_text(target.get("targetEntities")),
        "recommendedActions": normalize_text(target.get("recommendedActions")),
        "canonicalImageKey": normalize_text(ref.get("canonicalImageKey")),
        "imageUrl": normalize_text(ref.get("imageUrl")),
        "rawImagePath": normalize_text(ref.get("rawImagePath")),
        "detailRawPath": normalize_text(ref.get("detailRawPath")),
        "downloadStatus": normalize_text(ref.get("downloadStatus")),
        "detectedImageKind": normalize_text(ref.get("detectedImageKind")),
        "width": int_or_none(ref.get("width")) or 0,
        "height": int_or_none(ref.get("height")) or 0,
        "imageBytes": int_or_none(ref.get("imageBytes")) or 0,
        "imageEvidenceTarget": evidence_target,
        "imageEvidenceRole": evidence_role,
        "ocrPriorityScore": ocr_priority,
        "ocrEvidenceSha256": normalize_text((ocr or {}).get("evidenceSha256")),
        "ocrSourcePath": normalize_text((ocr or {}).get("sourcePath")),
        "ocrTextPreview": normalize_text((ocr or {}).get("textPreview"))[:500],
        "matchedKeywords": join_values((ocr or {}).get("matchedKeywords")),
        "sourceLinkRole": "adiga_selection_detail",
        "attachmentRole": "",
        "detectedDocumentRole": "",
        "pageNumber": 0,
        "pageImagePath": "",
        "pageImageSha256": "",
        "rawPdfPath": "",
        "rawPdfSha256": "",
        "sourceCandidateUrl": normalize_text(target.get("sourceUrl")),
        "attachmentUrl": "",
        "candidateReason": candidate_reason(ref, evidence_target, evidence_role, missing_flags, ocr),
        "operatorNextStep": operator_next_step(evidence_target, evidence_role, ocr),
    }


def is_reviewable_image(ref: dict[str, str], ocr: dict[str, Any] | None) -> bool:
    if normalize_text(ref.get("downloadStatus")) == "not_image_response":
        return False
    if is_low_signal_non_admission_ocr(ocr):
        return False
    if is_small_formula_or_label_image(ref, ocr):
        return False
    width = int_or_none(ref.get("width")) or 0
    height = int_or_none(ref.get("height")) or 0
    image_bytes = int_or_none(ref.get("imageBytes")) or 0
    evidence_target = normalize_text((ocr or {}).get("evidenceTarget"))
    evidence_role = normalize_text((ocr or {}).get("evidenceRole"))

    if not ocr:
        return (
            width >= MIN_REVIEW_IMAGE_DIMENSION * 2
            and height >= MIN_REVIEW_IMAGE_DIMENSION * 2
        ) or image_bytes >= 50_000
    if evidence_target in {"HistoricalOutcome", "AdmissionRule", "ReviewQueue"}:
        return width >= 80 or height >= 30 or image_bytes >= MIN_REVIEW_IMAGE_BYTES
    if evidence_role in {"admission_result_image", "score_distribution_image", "recruitment_rule_image"}:
        return True
    return (
        width >= MIN_REVIEW_IMAGE_DIMENSION * 2
        or height >= MIN_REVIEW_IMAGE_DIMENSION * 2
        or image_bytes >= 50_000
    )


def is_repeated_adiga_brand_image_without_ocr(
    ref: dict[str, str],
    ocr: dict[str, Any] | None,
    years_by_university_image_key: dict[tuple[str, str], set[str]],
) -> bool:
    if ocr:
        return False
    image_key = normalize_text(ref.get("canonicalImageKey"))
    university_code = normalize_text(ref.get("unvCd"))
    years = years_by_university_image_key.get((university_code, image_key), set())
    if len(years) < 4:
        return False
    image_kind = normalize_text(ref.get("detectedImageKind")).lower()
    if image_kind not in {"gif", "png", "jpeg", "jpg"}:
        return False
    width = int_or_none(ref.get("width")) or 0
    height = int_or_none(ref.get("height")) or 0
    image_bytes = int_or_none(ref.get("imageBytes")) or 0
    if width < 180 or height < 180 or image_bytes > 75_000:
        return False
    aspect = max(width, height) / max(1, min(width, height))
    return aspect <= 1.35


def is_small_formula_or_label_image(ref: dict[str, str], ocr: dict[str, Any] | None) -> bool:
    if not ocr:
        return False
    width = int_or_none(ref.get("width")) or 0
    height = int_or_none(ref.get("height")) or 0
    if not width or not height:
        return False
    if width * height > 20_000 or height > 90:
        return False
    evidence_role = normalize_text(ocr.get("evidenceRole"))
    if evidence_role != "recruitment_rule_image":
        return False
    text = normalize_text(ocr.get("textPreview") or ocr.get("text") or "")
    return bool(SMALL_FORMULA_OR_LABEL_OCR_PATTERN.search(text))


def is_low_signal_non_admission_ocr(ocr: dict[str, Any] | None) -> bool:
    if not ocr:
        return False
    evidence_target = normalize_text(ocr.get("evidenceTarget"))
    evidence_role = normalize_text(ocr.get("evidenceRole"))
    if evidence_target not in {"", "OCRReviewQueue", "ReviewQueue"}:
        return False
    if evidence_role not in {"", "low_signal_ocr_page", "low_signal_image", "image_review_required"}:
        return False
    text = normalize_text(ocr.get("textPreview") or ocr.get("text") or "")
    if not text:
        return False
    has_strong_admission_signal = bool(
        HISTORICAL_OUTCOME_STRONG_OCR_PATTERN.search(text)
        or ADMISSION_RULE_STRONG_OCR_PATTERN.search(text)
    )
    if has_strong_admission_signal:
        return False
    if evidence_target in {"", "OCRReviewQueue", "ReviewQueue"}:
        return True
    if len(re.sub(r"\W+", "", text)) < 30:
        return True
    return bool(NON_ADMISSION_LOW_SIGNAL_OCR_PATTERN.search(text))


def is_misclassified_admission_ocr(ocr: dict[str, Any]) -> bool:
    evidence_target = normalize_text(ocr.get("evidenceTarget"))
    evidence_role = normalize_text(ocr.get("evidenceRole"))
    text = normalize_text(ocr.get("textPreview") or ocr.get("text") or "")
    if not text:
        return False
    if evidence_target == "HistoricalOutcome":
        if is_non_freshman_or_notice_only_historical_outcome_ocr(ocr, text):
            return True
        if (
            HISTORICAL_OUTCOME_RULE_NOISE_OCR_PATTERN.search(text)
            and not HISTORICAL_OUTCOME_RESULT_TABLE_OCR_PATTERN.search(text)
        ):
            return True
        if HISTORICAL_OUTCOME_STRONG_OCR_PATTERN.search(text):
            return False
        if ADMISSION_RULE_STRONG_OCR_PATTERN.search(text):
            return True
        if evidence_role in {"admission_result_ocr_page", "competition_rate_ocr_page"}:
            return True
    if evidence_target == "AdmissionRule":
        if ADMISSION_RULE_STRONG_OCR_PATTERN.search(text):
            return False
        if evidence_role in {"screening_method_ocr_page", "csat_rule_ocr_page"}:
            return True
    return False


def is_non_freshman_or_notice_only_historical_outcome_ocr(
    ocr: dict[str, Any], text: str
) -> bool:
    source_context = normalize_text(
        " ".join(
            [
                str(ocr.get("sourceLinkRole") or ""),
                str(ocr.get("attachmentRole") or ""),
                str(ocr.get("detectedDocumentRole") or ""),
                str(ocr.get("sourceCandidateUrl") or ""),
                str(ocr.get("attachmentUrl") or ""),
            ]
        )
    )
    if HISTORICAL_OUTCOME_NON_FRESHMAN_OCR_PATTERN.search(text) or re.search(
        r"편입\s*학", source_context, re.I
    ):
        return True
    if "recruitment_notice" not in source_context:
        return False
    return bool(
        HISTORICAL_OUTCOME_NOTICE_ONLY_OCR_PATTERN.search(text)
        and not HISTORICAL_OUTCOME_RESULT_SIGNAL_OCR_PATTERN.search(text)
    )


def image_review_score(
    ref: dict[str, str],
    evidence_target: str,
    evidence_role: str,
    ocr_priority: int,
    missing_flags: list[str],
) -> int:
    width = int_or_none(ref.get("width")) or 0
    height = int_or_none(ref.get("height")) or 0
    image_bytes = int_or_none(ref.get("imageBytes")) or 0
    score = 70
    score += min(35, (width * height) // 25_000)
    score += min(20, image_bytes // 30_000)
    score += min(25, ocr_priority)
    if evidence_target in {"HistoricalOutcome", "AdmissionRule"}:
        score += 25
    if evidence_role in {"admission_result_image", "score_distribution_image", "recruitment_rule_image"}:
        score += 18
    relevant_flags = TARGET_RELEVANCE.get(evidence_target, set())
    if relevant_flags.intersection(missing_flags):
        score += 20
    if evidence_target == "OCRReviewQueue":
        score -= 15
    return max(0, score)


def office_page_review_score(
    page_bytes: int,
    evidence_target: str,
    evidence_role: str,
    ocr_priority: int,
    missing_flags: list[str],
    source_scope: str,
) -> int:
    score = 65
    score += min(35, page_bytes // 80_000)
    score += min(35, ocr_priority)
    if evidence_target in {"HistoricalOutcome", "AdmissionRule", "AdmissionSchedule"}:
        score += 25
    if evidence_role in {
        "admission_result_ocr_page",
        "competition_rate_ocr_page",
        "screening_method_ocr_page",
        "csat_rule_ocr_page",
        "schedule_ocr_page",
    }:
        score += 18
    relevant_flags = TARGET_RELEVANCE.get(evidence_target, set()).intersection(missing_flags)
    if relevant_flags:
        score += 20
    if source_scope == "gap_homepage_file_attachment":
        score += 8
    if source_scope == "zip_entry":
        score -= 10
    if evidence_target == "OCRReviewQueue":
        score -= 12
    return max(0, score)


def office_page_candidate_reason(
    scope: str,
    page_bytes: int,
    evidence_target: str,
    evidence_role: str,
    missing_flags: list[str],
    ocr: dict[str, Any],
) -> str:
    parts = [
        "admission_office_low_text_pdf_rendered_page_has_visual_or_ocr_review_value",
        f"scope={scope}",
        f"page_bytes={page_bytes}",
        f"ocr_role={evidence_role}",
        f"ocr_target={evidence_target}",
    ]
    relevant_flags = sorted(TARGET_RELEVANCE.get(evidence_target, set()).intersection(missing_flags))
    if relevant_flags:
        parts.append(f"matches_gap_flags={','.join(relevant_flags)}")
    matched_keywords = join_values(ocr.get("matchedKeywords"))
    if matched_keywords:
        parts.append(f"matched_keywords={matched_keywords}")
    return "; ".join(parts)


def candidate_reason(
    ref: dict[str, str],
    evidence_target: str,
    evidence_role: str,
    missing_flags: list[str],
    ocr: dict[str, Any] | None,
) -> str:
    parts = [
        "adiga_detail_has_no_html_table_but_has_reviewable_image",
        f"image={ref.get('width')}x{ref.get('height')}",
    ]
    if ocr:
        parts.append(f"ocr_role={evidence_role}")
        parts.append(f"ocr_target={evidence_target}")
    else:
        parts.append("ocr_evidence_missing")
    relevant_flags = sorted(TARGET_RELEVANCE.get(evidence_target, set()).intersection(missing_flags))
    if relevant_flags:
        parts.append(f"matches_gap_flags={','.join(relevant_flags)}")
    return "; ".join(parts)


def operator_next_step(evidence_target: str, evidence_role: str, ocr: dict[str, Any] | None) -> str:
    if not ocr:
        return "Run or inspect OCR for this Adiga image, then classify it before DB promotion."
    if evidence_target == "HistoricalOutcome":
        return "Review image/OCR against the visual table and extract structured HistoricalOutcome candidates."
    if evidence_target == "AdmissionRule":
        return "Review image/OCR against the visual table and extract structured AdmissionRule draft values."
    return "Visually inspect image and OCR text; reclassify or discard before promotion."


def summarize(
    repo_root: Path,
    inputs: list[Path],
    collection_targets: list[dict[str, str]],
    adiga_targets: list[dict[str, str]],
    image_refs: list[dict[str, str]],
    office_page_rows: list[dict[str, Any]],
    office_ocr_rows: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    target_groups = {
        (normalize_text(row.get("unvCd")), normalize_text(row.get("admissionYear")))
        for row in adiga_targets
    }
    target_image_refs = [
        row
        for row in image_refs
        if (normalize_text(row.get("unvCd")), normalize_text(row.get("year"))) in target_groups
    ]
    candidate_groups = {
        (normalize_text(row.get("unvCd")), str(row.get("admissionYear")))
        for row in candidates
    }
    adiga_candidates = [row for row in candidates if row.get("imageSourceKind") == "adiga_detail_image"]
    office_candidates = [
        row for row in candidates if row.get("imageSourceKind") == "admission_office_low_text_pdf_page"
    ]
    office_target_rows = [
        row
        for row in collection_targets
        if normalize_text(row.get("collectionRoute")) != "adiga_selection_detail"
    ]
    office_target_groups = {
        (normalize_text(row.get("unvCd")), normalize_text(row.get("admissionYear")))
        for row in office_target_rows
    }
    office_candidate_groups = {
        (normalize_text(row.get("unvCd")), str(row.get("admissionYear")))
        for row in office_candidates
    }
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_gap_image_source_candidates_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in inputs
            if path.exists()
        ],
        "adigaCollectionTargets": {
            "total": len(adiga_targets),
            "withReviewableImages": len(
                {
                    (normalize_text(row.get("unvCd")), str(row.get("admissionYear")))
                    for row in adiga_candidates
                }
            ),
            "withoutReviewableImages": len(
                target_groups
                - {
                    (normalize_text(row.get("unvCd")), str(row.get("admissionYear")))
                    for row in adiga_candidates
                }
            ),
        },
        "admissionOfficeCollectionTargets": {
            "totalRows": len(office_target_rows),
            "uniqueUniversityYearGroups": len(office_target_groups),
            "withReviewablePageImageGroups": len(office_candidate_groups),
            "withoutReviewablePageImageGroups": len(office_target_groups - office_candidate_groups),
        },
        "imageReferencesForTargets": {
            "total": len(target_image_refs),
            "reviewable": len(adiga_candidates),
            "smallOrIconSkipped": len(target_image_refs) - len(adiga_candidates),
            "uniqueImageKeys": len({normalize_text(row.get("canonicalImageKey")) for row in target_image_refs}),
        },
        "admissionOfficePageImagesForTargets": {
            "sourcePageImages": len(office_page_rows),
            "sourceOcrEvidenceRows": len(office_ocr_rows),
            "reviewableGapLinkedCandidates": len(office_candidates),
            "uniquePageImages": len({normalize_text(row.get("canonicalImageKey")) for row in office_candidates}),
        },
        "imageSourceCandidates": {
            "total": len(candidates),
            "withOcrEvidence": sum(1 for row in candidates if row.get("candidateStatus") == "ocr_evidence_available"),
            "withoutOcrEvidence": sum(
                1 for row in candidates if row.get("candidateStatus") == "image_review_required_no_ocr_evidence"
            ),
        },
        "byImageSourceKind": counter_rows(Counter(str(row.get("imageSourceKind")) for row in candidates), 20),
        "bySourceArtifactScope": counter_rows(Counter(str(row.get("sourceArtifactScope")) for row in candidates), 20),
        "byCandidateStatus": counter_rows(Counter(str(row.get("candidateStatus")) for row in candidates), 20),
        "byImageEvidenceTarget": counter_rows(Counter(str(row.get("imageEvidenceTarget")) for row in candidates), 20),
        "byImageEvidenceRole": counter_rows(Counter(str(row.get("imageEvidenceRole")) for row in candidates), 20),
        "byAdmissionYear": dict(sorted(Counter(str(row.get("admissionYear")) for row in candidates).items())),
        "byMissingFlags": counter_rows(Counter(str(row.get("missingFlags")) for row in candidates), 40),
        "notes": [
            "This queue links Adiga image artifacts and rendered admission-office PDF page images to p0 gaps where text/table extraction is absent or insufficient.",
            "Rows are visual/OCR review candidates, not verified structured HistoricalOutcome or AdmissionRule records.",
            "Small common Adiga icons are skipped so reviewers focus on table-like or content-bearing images; low-text PDF pages are retained when OCR evidence links them to an active gap.",
        ],
    }


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_jsonl_many(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for row in read_jsonl(path):
            row["_sourceManifestPath"] = str(path)
            rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "gapImageSourceCandidateId",
        "artifactType",
        "collectionTargetId",
        "priorityTier",
        "imageReviewPriorityScore",
        "candidateStatus",
        "imageSourceKind",
        "sourceProvider",
        "sourceArtifactScope",
        "unvCd",
        "universityName",
        "admissionYear",
        "gapCount",
        "missingFlags",
        "targetEntities",
        "recommendedActions",
        "canonicalImageKey",
        "imageUrl",
        "rawImagePath",
        "detailRawPath",
        "downloadStatus",
        "detectedImageKind",
        "width",
        "height",
        "imageBytes",
        "imageEvidenceTarget",
        "imageEvidenceRole",
        "ocrPriorityScore",
        "ocrEvidenceSha256",
        "ocrSourcePath",
        "ocrTextPreview",
        "matchedKeywords",
        "sourceLinkRole",
        "attachmentRole",
        "detectedDocumentRole",
        "pageNumber",
        "pageImagePath",
        "pageImageSha256",
        "rawPdfPath",
        "rawPdfSha256",
        "sourceCandidateUrl",
        "attachmentUrl",
        "candidateReason",
        "operatorNextStep",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    if not text:
        return []
    return [part for part in re.split(r"[|,;]", text) if part]


def join_values(values: Any) -> str:
    if isinstance(values, str):
        return values
    if not values:
        return ""
    return "|".join(normalize_text(value) for value in values if normalize_text(value))


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def first_nonempty_any(*values: Any) -> str:
    for value in values:
        text = normalize_text(value)
        if text:
            return text
    return ""


def admission_office_scope(row: dict[str, Any]) -> str:
    source_path = normalize_text(row.get("_sourceManifestPath"))
    page_path = normalize_text(row.get("pageImagePath"))
    source_specific = row.get("sourceSpecific") if isinstance(row.get("sourceSpecific"), dict) else {}
    source_path = source_path or page_path or normalize_text(source_specific.get("pageImagePath"))
    if "extracted-gap-homepage-html-route-nested-high-value" in source_path:
        return "gap_homepage_html_route_nested_high_value"
    if "extracted-gap-homepage-file-attachments" in source_path:
        return "gap_homepage_file_attachment"
    if "extracted-zip-entries" in source_path:
        return "zip_entry"
    if "university-admission-sites/extracted" in source_path:
        return "primary_admission_office"
    return "admission_office"


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


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
