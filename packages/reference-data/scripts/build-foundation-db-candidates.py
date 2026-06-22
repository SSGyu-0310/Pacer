#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ADIGA_OUTCOMES = (
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_csat_outcome_row_candidates.jsonl"
)
DEFAULT_ADIGA_STUDENT_OUTCOME_SUPPLEMENTS = (
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_yewon_20260615.jsonl",
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_halla_2026_20260615.jsonl",
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_p0_batch_20260615.jsonl",
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_p0_batch2_20260615.jsonl",
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_shinhan_2021_20260615.jsonl",
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_p0_batch3_20260615.jsonl",
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_hufs_2021_20260616.jsonl",
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_p0_batch4_20260616.jsonl",
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_student_outcome_supplement_p0_batch5_20260616.jsonl",
)
DEFAULT_ADIGA_UNIVERSITIES_GLOB = "packages/reference-data/data/public/adiga/adiga_universities_*.csv"
DEFAULT_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/extracted/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-file-attachments/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_NESTED_HIGH_VALUE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-html-route-nested-high-value/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_RELATED_DETAIL_HIGH_VALUE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-related-detail-high-value-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_CURRENT_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-current-file-attachments-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_CURRENT_RELATED_DETAIL_HIGH_VALUE_OFFICIALISH_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-current-related-detail-high-value-officialish-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_LINKS_GOAL_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-links-goal-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_LINKS_GOAL2_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-links-goal2-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_HOMEPAGE_HTML_P0_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-homepage-html-p0-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_FAILED_HOMEPAGE_RETRY_CURL_FALLBACK_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-failed-homepage-retry-curl-fallback-files-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_LINKS_NESTED_FILTERED_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-links-nested-filtered-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_RELATED_DETAIL_FOLLOWUP_CORE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-related-detail-followup-core-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_WORKLIST_FETCHED_UNCOVERED_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-fetched-uncovered-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_SYU_RELATED_DETAIL_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-syu-related-detail-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DCATHOLIC_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dcatholic-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_CALVIN_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-calvin-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_YTUS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-ytus-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_YTUS_2021_ARCHIVE_REGULAR_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-ytus-archive-regular-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_BPU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-bpu-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_YOUNGSAN_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-youngsan-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_CRAWLER_READY_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-ready-attachments-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_CRAWLER_DETAIL_FETCH_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-ready-detail-fetch-attachments-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_CRAWLER_ATTACHMENT_READY_RELATED_DETAIL_HIGH_VALUE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-attachment-ready-related-detail-high-value-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_CRAWLER_RESIDUAL_HIDDEN_DOWNLOAD_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-residual-hidden-download-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_KWANGSHIN_CURRENT_UNDERGRAD_HIDDEN_DOWNLOAD_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-kwangshin-current-undergrad-hidden-download-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_KWANGSHIN_COMPETITION_INLINE_OCR_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-kwangshin-competition-inline-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_IMAGE_ATTACHMENT_OCR_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-image-attachment-ocr-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_MANUAL_YEWON_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-manual-yewon-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_RELATED_DETAIL_READY_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-related-detail-ready-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_LINK_READY_MANUAL_GNU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-link-ready-manual-gnu-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_GNU_ARCHIVE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-gnu-archive-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_RENDERED_EULJI_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-rendered-eulji-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_GJC_EXISTING_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-gjc-existing-file-artifacts-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_GJC_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-gjc-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_ANYANG_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-anyang-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_CATHOLIC_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-catholic-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_CATHOLIC_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-catholic-results-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_CATHOLIC_REGULAR_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-catholic-regular-results-0000048-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_CATHOLIC_REGULAR_RESULTS_0000049_2022_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-catholic-regular-results-0000049-2022-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_MJU_REGULAR_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-mju-regular-results-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_KONYANG_REGULAR_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-konyang-regular-results-0000055-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_CAU_REGULAR_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-cau-regular-results-0000174-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_GWNU_REGULAR_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gwnu-regular-results-0003363-0003364-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_GWNU_OLDER_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gwnu-official-results-older-0003363-0003364-20260615/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_GINUE_REGULAR_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-ginue-regular-results-0000256-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_ICCU_2025_RESULT_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-iccu-2025-result-0000168-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_ICCU_RESULT_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-iccu-2021-2024-2026-results-0000168-20260614/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_CATHOLIC_SONGSIN_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-catholic-songsin-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_SCU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-scu-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_JNUE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-jnue-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_KYONGGI_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-kyonggi-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_LTU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-ltu-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_MOKWON_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-mokwon-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_SKHU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-skhu-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DONGGUK_WISE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dongguk-wise-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_KOREA_SEJONG_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-korea-sejong-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_KANGWON_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-kangwon-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DGAU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dgau-core-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DGAU_RECRUITMENT_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dgau-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DGAU_RESULT_INLINE_OCR_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dgau-result-inline-ocr-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DGAU_2022_RESULT_INLINE_OCR_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dgau-2022-result-inline-ocr-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_KBTUS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-kbtus-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_HTTPS_HOMEPAGE_RETRY_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-https-homepage-retry-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_HANIL_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-hanil-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DONGDUK_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dongduk-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DANKOOK_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dankook-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_SHINHAN_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-shinhan-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_CHOSUN_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-chosun-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_HSMU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-hsmu-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_HSMU_RETRY_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-hsmu-retry-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_RETRY_EXPANDED_FILES_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-retry-expanded-files-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_KOREATECH_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-koreatech-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_KANGNAM_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-kangnam-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_PUSAN_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-pusan-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_JEJUNU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-jejunu-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_DCU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-dcu-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_CNUE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-cnue-20260609/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_HANSEO_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-hanseo-20260611/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_MTU_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-mtu-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_CUP_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-cup-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_SOOKMYUNG_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-sookmyung-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_SUNMOON_SUNGKYUL_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-sunmoon-sungkyul-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_SCHEDULE_P0_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-schedule-p0-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_SCHEDULE_TOP_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-schedule-top-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_CUE_EXISTING_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-cue-existing-uncovered-file-artifacts-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_SEMYUNG_UWAY_COMPETITION_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-semyung-uway-competition-existing-uncovered-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_CJU_EXISTING_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-cju-existing-uncovered-file-artifacts-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_SMALL_ADMISSION_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-small-admission-results-existing-uncovered-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_SEJONG_ADMISSION_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-sejong-admission-results-existing-uncovered-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_SEOWON_NESTED_FILE_ROUTES_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-seowon-nested-file-routes-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_CRAWLER_FETCH_READY_REMAINING_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-crawler-fetch-ready-remaining-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_SCRIPT_NAV_REPARSE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-script-nav-reparse-attachments-20260608/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_SCRIPT_NAV_REPARSE_NESTED_OFFICIAL_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-goal-script-nav-reparse-nested-official-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_WORKLIST_HTML_BRIDGE_SECOND_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-html-bridge-second-files-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_WORKLIST_HTML_BRIDGE_THIRD_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-html-bridge-post-second-third-files-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_MANUAL_HOMEPAGE_SEED_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-homepage-seeds-files-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_WORKLIST_HTML_BRIDGE_POST_MANUAL_SEED_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-html-bridge-post-manual-seed-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_WORKLIST_HTML_BRIDGE_POST_SECOND_HTML_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-html-bridge-post-second-html-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_WORKLIST_HTML_BRIDGE_POST_DELTA_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-html-bridge-post-delta-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_SEHAN_CURRENT_APPLY_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-sehan-current-apply-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_SUWON_CATHOLIC_CURRENT_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-suwon-catholic-current-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_KAYA_CURRENT_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-kaya-current-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_LINKS_POST_MANUAL_SEED_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-links-post-manual-seed-20260612/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_LINKS_REFINED_DIRECT_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-links-refined-20260613-direct-file/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HOMEPAGE_LINKS_P0_20260615_RUN2_DIRECT_FILE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-homepage-file-attachments-p0-20260615-run2/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_COLLECTION_LINK_CANDIDATES_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-collection-link-candidates/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_COLLECTION_TARGETS_P0_YSU_GNU_FILES_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-collection-targets-p0-ysu-gnu-files-20260615-run3/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_MANUAL_GNU_2023_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-gnu-2023-official-results-20260615/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_SEOWON_2022_RESULT_DETAILS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-seowon-2022-result-details-20260614/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_SEOWON_2022_RESULT_DETAIL_FILES_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-seowon-2022-result-detail-files-20260614/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_HANSEI_POST_ADIGA_SLASH_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-hansei-post-adiga-slash-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_YSU_2021_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-ysu-2021-official-results-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_YSU_2022_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-ysu-2022-official-results-20260614/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_YEWON_2021_LEGACY_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-yewon-2021-legacy-results-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_YEWON_2022_LEGACY_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-yewon-2022-legacy-results-20260614/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_KYONGGI_2024_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-kyonggi-2024-official-results-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_KYONGGI_2022_OFFICIAL_SCORE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-kyonggi-2022-score-20260615/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_KYONGGI_2022_OFFICIAL_SUPPORT_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-kyonggi-2022-result-20260615/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_KYONGGI_2025_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-kyonggi-2025-official-results-20260614/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_JOONGBU_OFFICIAL_HTML_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-joongbu-official-html-results-20260614/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GKNU_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-gknu-results-20260616/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GACHON_2022_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-gachon-2022-results-20260616/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_SKUNIV_2026_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-skuniv-2026-results-20260616/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_ULSAN_2021_OFFICIAL_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-manual-ulsan-2021-results-20260616/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_SCNU_HTML_RESULTS_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-scnu-html-results-20260615/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_LTU_2021_OFFICIAL_RESULT_IMAGE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-ltu-2021-official-result-image-20260613/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_WORKLIST_FILE_HIGH_VALUE_PROMOTION_QUEUE = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-file-high-value/"
    "university_admission_promotion_review_candidates.jsonl"
)
DEFAULT_GAP_WORKLIST_LINKED_UNPROMOTED_PROMOTION_QUEUES = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-linked-unpromoted-20260613/"
    "university_admission_promotion_review_candidates.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-worklist-linked-unpromoted-20260617/"
    "university_admission_promotion_review_candidates.jsonl",
)
DEFAULT_JS_DOWNLOAD_FILE_PROMOTION_QUEUES = (
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-js-download-files/oku/"
    "university_admission_promotion_review_candidates.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-js-download-files/kyonggi/"
    "university_admission_promotion_review_candidates.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-scnu-competition-files-20260614/"
    "university_admission_promotion_review_candidates.jsonl",
    "packages/reference-data/data/public/university-admission-sites/"
    "extracted-gap-manual-scnu-result-competition-files-20260615/"
    "university_admission_promotion_review_candidates.jsonl",
)
DEFAULT_ZIP_ENTRY_PROMOTION_QUEUES = (
    (
        "packages/reference-data/data/public/university-admission-sites/"
        "extracted-zip-entries/"
        "university_admission_promotion_review_candidates.jsonl"
    ),
    (
        "packages/reference-data/data/public/university-admission-sites/"
        "extracted-gap-remaining-homepage-downloads-20260613/"
        "university_admission_promotion_review_candidates.jsonl"
    ),
)
DEFAULT_ACADEMYINFO_ROWS = (
    "packages/reference-data/data/public/academyinfo/extracted/"
    "academyinfo_row_candidates.jsonl"
)
DEFAULT_ADIGA_RULE_TABLES_GLOB = (
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_extracted_tables_*.jsonl"
)
DEFAULT_ADIGA_OCR_EVIDENCE = (
    "packages/reference-data/data/public/adiga/extracted/"
    "adiga_image_ocr_evidence_index.jsonl"
)
DEFAULT_KICE_GRADE_CUTS = (
    "packages/reference-data/data/public/kice/extracted/"
    "kice_grade_cut_candidates.csv"
)
DEFAULT_KICE_DISTRIBUTIONS = (
    "packages/reference-data/data/public/kice/extracted/"
    "kice_standard_score_distribution_candidates.csv"
)
DEFAULT_KICE_PRESS_SNIPPETS = (
    "packages/reference-data/data/public/kice/extracted/"
    "kice_suneung_press_snippet_index.csv"
)
DEFAULT_KCUE_SNIPPETS = (
    "packages/reference-data/data/public/kcue/extracted/"
    "kcue_admissions_press_snippets.jsonl"
)
DEFAULT_MANUAL_ADMISSION_UNIT_SUPPLEMENTS = (
    "packages/reference-data/data/sources/foundation_manual_admission_unit_supplements.csv"
)
DEFAULT_MANUAL_ADMISSION_OFFICE_EVIDENCE_SUPPLEMENTS = (
    "packages/reference-data/data/sources/foundation_manual_admission_office_evidence_supplements.csv"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/foundation"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027
BLOCKED_HELPER_SOURCE_PATTERN = re.compile(
    r"jinhak|jinhakapply|uway|uwayapply|telegr|01consulting|nesin|고속성장|진학사|유웨이",
    re.I,
)
BLOCKED_MALFORMED_SOURCE_PATTERN = re.compile(r"IE=edge", re.I)

OFFICE_ADMISSION_UNIT_ROLES = {
    "admission_result_table",
    "admission_result_row",
    "admission_result_ocr_page",
    "competition_rate_table",
    "competition_rate_row",
    "competition_rate_ocr_page",
    "recruitment_quota_table",
    "recruitment_quota_row",
}
OFFICE_UNIT_TABLE_CONTEXT = re.compile(r"모집\s*/?\s*단위|모집단위")
OFFICE_YTUS_UNIT_TABLE_CONTEXT = re.compile(
    r"모집\s*학과\s*(?:및\s*인원|인원)|모집\s*학과\b"
)
OFFICE_YTUS_UNIT_NAME_PATTERN = re.compile(
    r"글로벌케어서비스학부|국제언어다문화학과|기독교교육학과|기독교융합학부|사회복지학과|상담심리학과|자율전공학부|신학부|신학과"
)
OFFICE_UNIT_RESULT_CONTEXT = re.compile(
    r"모집\s*인원|지원\s*인원|경쟁률|입시\s*결과|전형별\s*모집\s*인원|정원\s*내|정원\s*외"
)
OFFICE_UNIT_NAME_PATTERN = re.compile(
    r"[가-힣A-Za-z0-9·ㆍ&()./+ -]{1,48}(?:학과|교육과|어과|학부|전공|계열)"
)
OFFICE_UNIT_SUFFIX_PATTERN = re.compile(r"(?:학과|교육과|어과|학부|전공|계열)$")
OFFICE_UNIT_NOISE_PATTERN = re.compile(
    r"모집단위|전모집단위|전체모집단위|대학입학|입학전형|지원자격|원서|등록|합격|"
    r"성적|반영|교과|수능|학교생활|선수과목|유의사항|안내|기간|일정|"
    r"기준|동일|모집|지원|전체|전형|평가|가이드북|선발단위|단과대학|"
    r"세부전공|고교계열|동종계열|학년|장소|불가|첨단학과|첨단학부"
)
OFFICE_UNIT_GENERIC_NOISE_VALUES = {
    "아래학과",
    "일반학과",
    "전체학과",
    "전학과",
    "모든학과",
    "해당학과",
    "학부학과",
}
ADMISSION_YEAR_CONTEXT_PATTERN = re.compile(r"(?<!\d)(20\d{2})\s*학\s*년\s*도")
OFFICE_HISTORICAL_OUTCOME_ROLES = {
    "admission_result_table",
    "admission_result_row",
    "admission_result_ocr_page",
    "admission_result_image_ocr",
    "competition_rate_table",
    "competition_rate_row",
    "competition_rate_ocr_page",
    "competition_rate_image_ocr",
}
OFFICE_OUTCOME_STRONG_CONTEXT = re.compile(r"입시\s*결과|최종\s*결과|경쟁률")
OFFICE_OUTCOME_TABLE_CONTEXT = re.compile(
    r"모집\s*단위|모집단위|모집단위명|모집\s*학과|모집학과|학과"
)
OFFICE_OUTCOME_RESULT_CONTEXT = re.compile(
    r"모집\s*인원|지원\s*인원|지원인원|등록\s*인원|경쟁률|지원율|지원률"
)
OFFICE_COMPETITION_LINE_PATTERN = re.compile(
    r"^\s*"
    r"(?:(?:[「『]?\s*(?P<group>[가나다])\s*[」』]?\s*군)\s+)?"
    r"(?P<label>[가-힣A-Za-z0-9·ㆍ&()./+()\[\] -]{2,70}?)"
    r"\s+(?P<quota>\d{1,4})"
    r"\s+(?P<applicants>\d{1,5})"
    r"\s+(?P<competition>\d{1,3}(?:\.\d+)?)\s*:?\s*1\s*$"
)
OFFICE_RECRUITMENT_GROUP_PATTERN = re.compile(r"[「『]?\s*([가나다])\s*[」』]?\s*군")
OFFICE_COMPETITION_LINE_SECTION_HEADER_PATTERN = re.compile(
    r"\d{4}\s*학\s*년\s*도\s*(?:수시|정시)\s*모집\s*(?P<section>일반전형|특별전형|정원외)"
)
OFFICE_COMPETITION_LINE_UNIT_HINT_PATTERN = re.compile(
    r"신학|복지|경영|음악|무용|뮤지컬|심리|상담|운동|건강|체육|간호|"
    r"디자인|미술|영상|연기|영화|관광|호텔|조리|뷰티|아동|청소년|"
    r"유아|보육|재활|치위생|물리치료|작업치료|방사선|임상병리|응급구조|"
    r"안경|소방|경찰|항공|컴퓨터|소프트웨어|인공지능|AI|바이오"
)
OFFICE_COMPETITION_LINE_LABEL_NOISE_PATTERN = re.compile(
    r"총계|합계|소계|전형\s*전체|모집\s*단위|모집단위|모집\s*시기|모집군|"
    r"전형\s*구분|전형구분|지원\s*인원|지원인원|경쟁률|모집\s*인원|모집인원|"
    r"지원자격|등록|합격|최종"
)
OFFICE_COMPETITION_LINE_SELECTION_TOKEN_PATTERN = re.compile(
    r"^(?:일반전형|특별전형|정원내|정원외|SCU인재|고른기회|기회균형|"
    r"학교장|추천자|학교장추천자|사회봉사자|평생학습자|교회추천자|만학도|"
    r"농어촌|농어촌출신자|기초생활|기초생활수급자|차상위계층|특성화고교|"
    r"특성화고교출신자|경시대회입상자|대회실적우수자|리더십|휴먼|서비스|"
    r"휴먼서비스|휴먼힐링|힐링|예술|휴먼힐링예술|학부)$"
)
OFFICE_OUTCOME_SCORE_CONTEXT = re.compile(
    r"최종\s*등록자|성적|평균|최저|최고|등급|환산|백분위|표준점수|50%\s*cut|70%\s*cut|70%\s*Cut",
    re.I,
)
OFFICE_OUTCOME_ROW_NOISE_CONTEXT = re.compile(
    r"(?:이론|실습|요일|강의실|교수|학점|교과목|수업|강좌|담당)|\d{3,4}\s*-\s*\d{3,4}"
)
OFFICE_NON_ADMISSION_SOURCE_PATTERN = re.compile(
    r"tuitionReview|bn=29985|개설\s*강좌|시간제\s*등록생|등록금\s*심의|대학\s*정보\s*공시",
    re.I,
)
OFFICE_RECRUITMENT_GUIDE_CONTEXT_PATTERN = re.compile(
    r"모집\s*요강|입학\s*전형\s*(?:시행\s*)?계획|전형\s*유형별|전형\s*요소|지원\s*자격|"
    r"수능\s*최저|반영\s*비율|채점\s*기준|모집\s*단위별\s*모집\s*인원|"
    r"전형\s*일정|원서\s*접수|전형료",
    re.I,
)
OFFICE_RECRUITMENT_GUIDE_SOURCE_PATTERN = re.compile(
    r"recruitment_notice|admission_guide|implementation_plan|regular_admission_guide|"
    r"early_admission_guide|모집\s*요강|전형\s*계획",
    re.I,
)
OFFICE_HISTORICAL_OUTCOME_POSITIVE_CONTEXT_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전년도|전년|경쟁률|지원\s*인원|지원자\s*수|지원\s*현황|"
    r"충원\s*(?:인원|율|순위|번호)|충원\s*합격\s*(?:인원|율|순위|번호|자\s*수)|"
    r"추가\s*합격\s*(?:인원|율|순위|번호|자\s*수)|최종\s*등록|등록\s*인원|합격자\s*(?:평균|최저|최고)|"
    r"70\s*%\s*(?:cut|컷)|50\s*%\s*(?:cut|컷)|환산\s*점수|백분위",
    re.I,
)
OFFICE_RECRUITMENT_NOTICE_OUTCOME_KEEP_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|경쟁률|지원\s*인원|지원자\s*수|지원\s*현황|등록\s*인원|"
    r"충원\s*(?:인원|율|순위|번호)|충원\s*합격\s*(?:인원|율|순위|번호|자\s*수)|"
    r"추가\s*합격\s*(?:인원|율|순위|번호|자\s*수)|합격자\s*(?:평균|최저|최고)|"
    r"70\s*%\s*(?:cut|컷)|50\s*%\s*(?:cut|컷)|"
    r"환산\s*점수.{0,24}(?:평균|최저|최고|70\s*%|50\s*%)|"
    r"(?:평균|최저|최고|70\s*%|50\s*%).{0,24}환산\s*점수",
    re.I,
)
OFFICE_COURSE_TIMETABLE_TIME_PATTERN = re.compile(
    r"(?:월|화|수|목|금|토|일)요일|\d{3,4}\s*-\s*\d{3,4}|[A-Z]\d{3,4}"
)
OFFICE_COURSE_TIMETABLE_CONTEXT_PATTERN = re.compile(
    r"이론|실습|강의실|교수|학점|교과목|수업|강좌|담당"
)
OFFICE_ADMISSION_RESULT_CONTEXT_PATTERN = re.compile(
    r"모집\s*인원|지원\s*(?:인원|자)|경쟁률|합격|충원|최종\s*등록|전형|수능|학생부"
)
OFFICE_OUTCOME_COMPETITION_ROW_HEADER_CONTEXTS = (
    re.compile(r"모집\s*인원|모집인원"),
    re.compile(r"지원\s*(?:인원|자)|지원인원|지원자"),
    re.compile(r"경쟁률|지원율|지원률"),
)
OFFICE_OUTCOME_NUMBER_PATTERN = re.compile(
    r"(?<![\d.])(\d{1,4}(?:\.\d+)?)(?:\s*:\s*1)?(?![\d.])"
)
OFFICE_HTML_ROW_PATTERN = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
OFFICE_HTML_CELL_PATTERN = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
OFFICE_HTML_CELL_WITH_ATTR_PATTERN = re.compile(
    r"<t[dh]\b([^>]*)>(.*?)</t[dh]>",
    re.I | re.S,
)
OFFICE_WORKBOOK_CONTEXT_ROW_CACHE: dict[str, list[list[str]]] = {}
OFFICE_WORKBOOK_CONTEXT_TEXT_CACHE: dict[tuple[str, int], list[str]] = {}
OFFICE_WORKBOOK_SOURCE_PATH_CACHE: dict[str, Path | None] = {}
OFFICE_TEXT_SOURCE_PATH_CACHE: dict[str, Path | None] = {}
OFFICE_TEXT_SOURCE_INTRO_CACHE: dict[str, str] = {}
OFFICE_RAW_TEXT_SOURCE_CACHE: dict[str, str] = {}
OFFICE_TEXT_SOURCE_CACHE: dict[str, str] = {}
REPO_ROOT_CACHE: Path | None = None


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    adiga_rows = read_jsonl(resolve(repo_root, args.adiga_outcomes))
    for supplemental_path in args.adiga_student_outcome_supplement:
        adiga_rows.extend(read_jsonl(resolve(repo_root, supplemental_path)))
    primary_promotion_rows = read_jsonl(resolve(repo_root, args.promotion_queue))
    gap_homepage_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_file_promotion_queue)
    )
    gap_homepage_nested_high_value_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_nested_high_value_promotion_queue)
    )
    gap_homepage_related_detail_high_value_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_related_detail_high_value_promotion_queue)
    )
    gap_homepage_current_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_current_file_promotion_queue)
    )
    gap_homepage_current_related_detail_high_value_officialish_promotion_rows = read_jsonl(
        resolve(
            repo_root,
            args.gap_homepage_current_related_detail_high_value_officialish_promotion_queue,
        )
    )
    gap_homepage_links_goal_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_links_goal_promotion_queue)
    )
    gap_homepage_links_goal2_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_links_goal2_promotion_queue)
    )
    failed_homepage_retry_curl_fallback_promotion_rows = read_jsonl(
        resolve(repo_root, args.failed_homepage_retry_curl_fallback_promotion_queue)
    )
    gap_homepage_links_nested_filtered_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_links_nested_filtered_promotion_queue)
    )
    gap_related_detail_followup_core_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_related_detail_followup_core_promotion_queue)
    )
    gap_worklist_fetched_uncovered_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_worklist_fetched_uncovered_promotion_queue)
    )
    gap_syu_related_detail_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_syu_related_detail_promotion_queue)
    )
    gap_manual_dcatholic_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_dcatholic_promotion_queue)
    )
    gap_manual_calvin_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_calvin_promotion_queue)
    )
    gap_manual_ytus_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_ytus_promotion_queue)
    )
    gap_ytus_2021_archive_regular_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_ytus_2021_archive_regular_promotion_queue)
    )
    gap_manual_bpu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_bpu_promotion_queue)
    )
    gap_manual_youngsan_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_youngsan_promotion_queue)
    )
    gap_crawler_ready_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_crawler_ready_promotion_queue)
    )
    gap_crawler_detail_fetch_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_crawler_detail_fetch_promotion_queue)
    )
    gap_crawler_attachment_ready_related_detail_high_value_promotion_rows = read_jsonl(
        resolve(
            repo_root,
            args.gap_crawler_attachment_ready_related_detail_high_value_promotion_queue,
        )
    )
    gap_crawler_residual_hidden_download_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_crawler_residual_hidden_download_promotion_queue)
    )
    gap_kwangshin_current_undergrad_hidden_download_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_kwangshin_current_undergrad_hidden_download_promotion_queue)
    )
    gap_kwangshin_competition_inline_ocr_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_kwangshin_competition_inline_ocr_promotion_queue)
    )
    gap_image_attachment_ocr_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_image_attachment_ocr_promotion_queue)
    )
    gap_homepage_manual_yewon_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_manual_yewon_promotion_queue)
    )
    gap_related_detail_ready_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_related_detail_ready_promotion_queue)
    )
    gap_link_ready_manual_gnu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_link_ready_manual_gnu_promotion_queue)
    )
    manual_gnu_archive_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_gnu_archive_promotion_queue)
    )
    gap_rendered_eulji_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_rendered_eulji_promotion_queue)
    )
    gap_manual_gjc_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_gjc_promotion_queue)
    )
    gap_manual_anyang_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_anyang_promotion_queue)
    )
    gap_manual_catholic_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_catholic_promotion_queue)
    )
    manual_catholic_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_catholic_results_promotion_queue)
    )
    manual_catholic_regular_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_catholic_regular_results_promotion_queue)
    )
    manual_catholic_regular_results_0000049_2022_promotion_rows = read_jsonl(
        resolve(
            repo_root,
            args.manual_catholic_regular_results_0000049_2022_promotion_queue,
        )
    )
    manual_catholic_regular_results_promotion_rows.extend(
        manual_catholic_regular_results_0000049_2022_promotion_rows
    )
    manual_mju_regular_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_mju_regular_results_promotion_queue)
    )
    manual_konyang_regular_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_konyang_regular_results_promotion_queue)
    )
    manual_cau_regular_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_cau_regular_results_promotion_queue)
    )
    manual_gwnu_regular_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_gwnu_regular_results_promotion_queue)
    )
    manual_gwnu_older_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_gwnu_older_results_promotion_queue)
    )
    manual_gwnu_regular_results_promotion_rows.extend(
        manual_gwnu_older_results_promotion_rows
    )
    manual_ginue_regular_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_ginue_regular_results_promotion_queue)
    )
    manual_iccu_2025_result_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_iccu_2025_result_promotion_queue)
    )
    manual_iccu_result_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_iccu_result_promotion_queue)
    )
    gap_manual_catholic_songsin_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_catholic_songsin_promotion_queue)
    )
    gap_manual_scu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_scu_promotion_queue)
    )
    gap_manual_jnue_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_jnue_promotion_queue)
    )
    gap_manual_kyonggi_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_kyonggi_promotion_queue)
    )
    gap_manual_ltu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_ltu_promotion_queue)
    )
    gap_manual_mokwon_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_mokwon_promotion_queue)
    )
    gap_manual_skhu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_skhu_promotion_queue)
    )
    gap_manual_dongguk_wise_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_dongguk_wise_promotion_queue)
    )
    gap_manual_korea_sejong_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_korea_sejong_promotion_queue)
    )
    gap_manual_kangwon_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_kangwon_promotion_queue)
    )
    gap_manual_dgau_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_dgau_promotion_queue)
    )
    gap_manual_dgau_recruitment_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_dgau_recruitment_promotion_queue)
    )
    gap_manual_dgau_result_inline_ocr_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_dgau_result_inline_ocr_promotion_queue)
    )
    gap_manual_dgau_result_inline_ocr_promotion_rows.extend(
        read_jsonl(
            resolve(
                repo_root,
                args.gap_manual_dgau_2022_result_inline_ocr_promotion_queue,
            )
        )
    )
    gap_manual_kbtus_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_kbtus_promotion_queue)
    )
    manual_https_homepage_retry_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_https_homepage_retry_promotion_queue)
    )
    gap_manual_hanil_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_hanil_promotion_queue)
    )
    gap_manual_dongduk_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_dongduk_promotion_queue)
    )
    gap_manual_dankook_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_dankook_promotion_queue)
    )
    gap_manual_shinhan_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_shinhan_promotion_queue)
    )
    gap_manual_chosun_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_chosun_promotion_queue)
    )
    gap_manual_hsmu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_hsmu_promotion_queue)
    )
    gap_homepage_hsmu_retry_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_hsmu_retry_promotion_queue)
    )
    gap_homepage_retry_expanded_files_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_retry_expanded_files_promotion_queue)
    )
    gap_manual_koreatech_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_koreatech_promotion_queue)
    )
    gap_manual_kangnam_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_kangnam_promotion_queue)
    )
    gap_manual_pusan_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_pusan_promotion_queue)
    )
    gap_manual_jejunu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_jejunu_promotion_queue)
    )
    gap_manual_dcu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_dcu_promotion_queue)
    )
    gap_manual_cnue_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_cnue_promotion_queue)
    )
    gap_manual_hanseo_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_hanseo_promotion_queue)
    )
    gap_manual_mtu_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_mtu_promotion_queue)
    )
    gap_manual_cup_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_cup_promotion_queue)
    )
    gap_manual_sookmyung_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_sookmyung_promotion_queue)
    )
    gap_manual_sunmoon_sungkyul_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_sunmoon_sungkyul_promotion_queue)
    )
    gap_manual_schedule_p0_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_schedule_p0_promotion_queue)
    )
    homepage_html_p0_promotion_rows = read_jsonl(
        resolve(repo_root, args.homepage_html_p0_promotion_queue)
    )
    manual_schedule_top_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_schedule_top_promotion_queue)
    )
    gap_gjc_existing_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_gjc_existing_file_promotion_queue)
    )
    gap_cue_existing_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_cue_existing_file_promotion_queue)
    )
    gap_semyung_uway_competition_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_semyung_uway_competition_promotion_queue)
    )
    gap_cju_existing_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_cju_existing_file_promotion_queue)
    )
    gap_small_admission_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_small_admission_results_promotion_queue)
    )
    gap_sejong_admission_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_sejong_admission_results_promotion_queue)
    )
    gap_seowon_nested_file_routes_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_seowon_nested_file_routes_promotion_queue)
    )
    gap_crawler_fetch_ready_remaining_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_crawler_fetch_ready_remaining_promotion_queue)
    )
    script_nav_reparse_promotion_rows = read_jsonl(
        resolve(repo_root, args.script_nav_reparse_promotion_queue)
    )
    script_nav_reparse_nested_official_promotion_rows = read_jsonl(
        resolve(repo_root, args.script_nav_reparse_nested_official_promotion_queue)
    )
    gap_worklist_html_bridge_second_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_worklist_html_bridge_second_file_promotion_queue)
    )
    gap_worklist_html_bridge_third_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_worklist_html_bridge_third_file_promotion_queue)
    )
    manual_homepage_seed_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.manual_homepage_seed_file_promotion_queue)
    )
    gap_worklist_html_bridge_post_manual_seed_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_worklist_html_bridge_post_manual_seed_promotion_queue)
    )
    gap_worklist_html_bridge_post_second_html_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_worklist_html_bridge_post_second_html_promotion_queue)
    )
    gap_worklist_html_bridge_post_delta_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_worklist_html_bridge_post_delta_promotion_queue)
    )
    gap_manual_sehan_current_apply_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_sehan_current_apply_promotion_queue)
    )
    gap_manual_suwon_catholic_current_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_suwon_catholic_current_promotion_queue)
    )
    gap_manual_kaya_current_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_kaya_current_promotion_queue)
    )
    gap_homepage_links_post_manual_seed_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_links_post_manual_seed_promotion_queue)
    )
    gap_homepage_links_refined_direct_file_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_homepage_links_refined_direct_file_promotion_queue)
    )
    gap_homepage_links_p0_20260615_run2_direct_file_promotion_rows = read_jsonl(
        resolve(
            repo_root,
            args.gap_homepage_links_p0_20260615_run2_direct_file_promotion_queue,
        )
    )
    gap_collection_link_candidates_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_collection_link_candidates_promotion_queue)
    )
    gap_collection_targets_p0_ysu_gnu_files_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_collection_targets_p0_ysu_gnu_files_promotion_queue)
    )
    gap_manual_gnu_2023_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_manual_gnu_2023_official_results_promotion_queue)
    )
    seowon_2022_result_details_promotion_rows = read_jsonl(
        resolve(repo_root, args.seowon_2022_result_details_promotion_queue)
    )
    seowon_2022_result_detail_files_promotion_rows = read_jsonl(
        resolve(repo_root, args.seowon_2022_result_detail_files_promotion_queue)
    )
    gap_hansei_post_adiga_slash_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_hansei_post_adiga_slash_promotion_queue)
    )
    gap_ysu_2021_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_ysu_2021_official_results_promotion_queue)
    )
    gap_ysu_2022_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_ysu_2022_official_results_promotion_queue)
    )
    gap_yewon_2021_legacy_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_yewon_2021_legacy_results_promotion_queue)
    )
    gap_yewon_2022_legacy_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_yewon_2022_legacy_results_promotion_queue)
    )
    gap_kyonggi_2022_official_score_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_kyonggi_2022_official_score_promotion_queue)
    )
    gap_kyonggi_2022_official_support_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_kyonggi_2022_official_support_promotion_queue)
    )
    gap_kyonggi_2024_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_kyonggi_2024_official_results_promotion_queue)
    )
    gap_kyonggi_2025_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_kyonggi_2025_official_results_promotion_queue)
    )
    joongbu_official_html_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.joongbu_official_html_results_promotion_queue)
    )
    gknu_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gknu_official_results_promotion_queue)
    )
    gachon_2022_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.gachon_2022_official_results_promotion_queue)
    )
    skuniv_2026_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.skuniv_2026_official_results_promotion_queue)
    )
    ulsan_2021_official_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.ulsan_2021_official_results_promotion_queue)
    )
    scnu_html_results_promotion_rows = read_jsonl(
        resolve(repo_root, args.scnu_html_results_promotion_queue)
    )
    gap_ltu_2021_official_result_image_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_ltu_2021_official_result_image_promotion_queue)
    )
    gap_worklist_file_high_value_promotion_rows = read_jsonl(
        resolve(repo_root, args.gap_worklist_file_high_value_promotion_queue)
    )
    gap_worklist_linked_unpromoted_promotion_rows = read_jsonl_many(
        [resolve(repo_root, value) for value in args.gap_worklist_linked_unpromoted_promotion_queue]
    )
    js_download_file_promotion_rows = read_jsonl_many(
        [resolve(repo_root, value) for value in args.js_download_file_promotion_queue]
    )
    zip_entry_promotion_rows = read_jsonl_many(
        [resolve(repo_root, value) for value in args.zip_entry_promotion_queue]
    )
    promotion_rows, promotion_source_counts = combine_promotion_rows(
        primary_promotion_rows,
        gap_homepage_file_promotion_rows,
        gap_homepage_nested_high_value_promotion_rows,
        gap_homepage_related_detail_high_value_promotion_rows,
        gap_homepage_current_file_promotion_rows,
        gap_homepage_current_related_detail_high_value_officialish_promotion_rows,
        gap_homepage_links_goal_promotion_rows,
        gap_homepage_links_goal2_promotion_rows,
        failed_homepage_retry_curl_fallback_promotion_rows,
        gap_homepage_links_nested_filtered_promotion_rows,
        gap_related_detail_followup_core_promotion_rows,
        gap_worklist_fetched_uncovered_promotion_rows,
        gap_syu_related_detail_promotion_rows,
        gap_manual_dcatholic_promotion_rows,
        gap_manual_calvin_promotion_rows,
        gap_manual_ytus_promotion_rows,
        gap_ytus_2021_archive_regular_promotion_rows,
        gap_manual_bpu_promotion_rows,
        gap_manual_youngsan_promotion_rows,
        gap_crawler_ready_promotion_rows,
        gap_crawler_detail_fetch_promotion_rows,
        gap_crawler_attachment_ready_related_detail_high_value_promotion_rows,
        gap_crawler_residual_hidden_download_promotion_rows,
        gap_kwangshin_current_undergrad_hidden_download_promotion_rows,
        gap_kwangshin_competition_inline_ocr_promotion_rows,
        gap_image_attachment_ocr_promotion_rows,
        gap_homepage_manual_yewon_promotion_rows,
        gap_related_detail_ready_promotion_rows,
        gap_link_ready_manual_gnu_promotion_rows,
        manual_gnu_archive_promotion_rows,
        gap_rendered_eulji_promotion_rows,
        gap_manual_gjc_promotion_rows,
        gap_manual_anyang_promotion_rows,
        gap_manual_catholic_promotion_rows,
        manual_catholic_results_promotion_rows,
        manual_catholic_regular_results_promotion_rows,
        manual_mju_regular_results_promotion_rows,
        manual_konyang_regular_results_promotion_rows,
        manual_cau_regular_results_promotion_rows,
        manual_gwnu_regular_results_promotion_rows,
        manual_ginue_regular_results_promotion_rows,
        manual_iccu_2025_result_promotion_rows,
        manual_iccu_result_promotion_rows,
        gap_manual_catholic_songsin_promotion_rows,
        gap_manual_scu_promotion_rows,
        gap_manual_jnue_promotion_rows,
        gap_manual_kyonggi_promotion_rows,
        gap_manual_ltu_promotion_rows,
        gap_manual_mokwon_promotion_rows,
        gap_manual_skhu_promotion_rows,
        gap_manual_dongguk_wise_promotion_rows,
        gap_manual_korea_sejong_promotion_rows,
        gap_manual_kangwon_promotion_rows,
        gap_manual_dgau_promotion_rows,
        gap_manual_dgau_recruitment_promotion_rows,
        gap_manual_dgau_result_inline_ocr_promotion_rows,
        gap_manual_kbtus_promotion_rows,
        manual_https_homepage_retry_promotion_rows,
        gap_manual_hanil_promotion_rows,
        gap_manual_dongduk_promotion_rows,
        gap_manual_dankook_promotion_rows,
        gap_manual_shinhan_promotion_rows,
        gap_manual_chosun_promotion_rows,
        gap_manual_hsmu_promotion_rows,
        gap_homepage_hsmu_retry_promotion_rows,
        gap_homepage_retry_expanded_files_promotion_rows,
        gap_manual_koreatech_promotion_rows,
        gap_manual_kangnam_promotion_rows,
        gap_manual_pusan_promotion_rows,
        gap_manual_jejunu_promotion_rows,
        gap_manual_dcu_promotion_rows,
        gap_manual_cnue_promotion_rows,
        gap_manual_hanseo_promotion_rows,
        gap_manual_mtu_promotion_rows,
        gap_manual_cup_promotion_rows,
        gap_manual_sookmyung_promotion_rows,
        gap_manual_sunmoon_sungkyul_promotion_rows,
        gap_manual_schedule_p0_promotion_rows,
        homepage_html_p0_promotion_rows,
        manual_schedule_top_promotion_rows,
        gap_gjc_existing_file_promotion_rows,
        gap_cue_existing_file_promotion_rows,
        gap_semyung_uway_competition_promotion_rows,
        gap_cju_existing_file_promotion_rows,
        gap_small_admission_results_promotion_rows,
        gap_sejong_admission_results_promotion_rows,
        gap_seowon_nested_file_routes_promotion_rows,
        gap_crawler_fetch_ready_remaining_promotion_rows,
        script_nav_reparse_promotion_rows,
        script_nav_reparse_nested_official_promotion_rows,
        gap_worklist_html_bridge_second_file_promotion_rows,
        gap_worklist_html_bridge_third_file_promotion_rows,
        manual_homepage_seed_file_promotion_rows,
        gap_worklist_html_bridge_post_manual_seed_promotion_rows,
        gap_worklist_html_bridge_post_second_html_promotion_rows,
        gap_worklist_html_bridge_post_delta_promotion_rows,
        gap_manual_sehan_current_apply_promotion_rows,
        gap_manual_suwon_catholic_current_promotion_rows,
        gap_manual_kaya_current_promotion_rows,
        gap_homepage_links_post_manual_seed_promotion_rows,
        gap_homepage_links_refined_direct_file_promotion_rows,
        gap_homepage_links_p0_20260615_run2_direct_file_promotion_rows,
        gap_collection_link_candidates_promotion_rows,
        gap_collection_targets_p0_ysu_gnu_files_promotion_rows,
        gap_manual_gnu_2023_official_results_promotion_rows,
        seowon_2022_result_details_promotion_rows,
        seowon_2022_result_detail_files_promotion_rows,
        gap_hansei_post_adiga_slash_promotion_rows,
        gap_ysu_2021_official_results_promotion_rows,
        gap_ysu_2022_official_results_promotion_rows,
        gap_yewon_2021_legacy_results_promotion_rows,
        gap_yewon_2022_legacy_results_promotion_rows,
        gap_kyonggi_2022_official_score_promotion_rows,
        gap_kyonggi_2022_official_support_promotion_rows,
        gap_kyonggi_2024_official_results_promotion_rows,
        gap_kyonggi_2025_official_results_promotion_rows,
        joongbu_official_html_results_promotion_rows,
        gknu_official_results_promotion_rows,
        gachon_2022_official_results_promotion_rows,
        skuniv_2026_official_results_promotion_rows,
        ulsan_2021_official_results_promotion_rows,
        scnu_html_results_promotion_rows,
        gap_ltu_2021_official_result_image_promotion_rows,
        gap_worklist_file_high_value_promotion_rows,
        gap_worklist_linked_unpromoted_promotion_rows,
        js_download_file_promotion_rows,
        zip_entry_promotion_rows,
    )
    academyinfo_rows = read_jsonl(resolve(repo_root, args.academyinfo_rows))
    adiga_rule_table_rows = read_jsonl_many(resolve_glob(repo_root, args.adiga_rule_tables_glob))
    adiga_ocr_evidence_rows = read_jsonl(resolve(repo_root, args.adiga_ocr_evidence))
    kice_grade_cut_rows = read_csv(resolve(repo_root, args.kice_grade_cuts))
    kice_distribution_rows = read_csv(resolve(repo_root, args.kice_distributions))
    kice_press_snippet_rows = read_csv(resolve(repo_root, args.kice_press_snippets))
    kcue_snippet_rows = read_jsonl(resolve(repo_root, args.kcue_snippets))
    adiga_university_rows = read_csv_many(resolve_glob(repo_root, args.adiga_universities_glob))
    manual_admission_unit_rows = read_csv(resolve(repo_root, args.manual_admission_unit_supplements))
    manual_admission_office_evidence_rows = read_csv(
        resolve(repo_root, args.manual_admission_office_evidence_supplements)
    )

    context = build_context(
        adiga_rows,
        adiga_university_rows,
        promotion_rows,
        promotion_source_counts,
        manual_admission_unit_rows,
        manual_admission_office_evidence_rows,
        academyinfo_rows,
        adiga_rule_table_rows,
        adiga_ocr_evidence_rows,
        kice_grade_cut_rows,
        kice_distribution_rows,
        kice_press_snippet_rows,
        kcue_snippet_rows,
    )
    write_outputs(output_dir, context)

    print(
        "foundation database candidate build complete. "
        f"universities={len(context['universities'])} "
        f"units={len(context['admissionUnits'])} "
        f"outcomes={len(context['historicalOutcomes'])} "
        f"admissionOfficeEvidence={len(context['admissionOfficeEvidenceLinks'])} "
        f"admissionRuleCandidates={len(context['admissionRuleReviewCandidates'])} "
        f"academyinfoSummaries={len(context['academyinfoSummaries'])} "
        f"kiceGradeCuts={len(context['kiceGradeCuts'])} "
        f"kiceDistributions={len(context['kiceStandardScoreDistributions'])} "
        f"kiceEvidence={len(context['kicePressEvidenceLinks'])} "
        f"kcueEvidence={len(context['kcuePolicyEvidenceLinks'])}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--adiga-outcomes", default=DEFAULT_ADIGA_OUTCOMES)
    parser.add_argument(
        "--adiga-student-outcome-supplement",
        action="append",
        default=list(DEFAULT_ADIGA_STUDENT_OUTCOME_SUPPLEMENTS),
    )
    parser.add_argument("--adiga-universities-glob", default=DEFAULT_ADIGA_UNIVERSITIES_GLOB)
    parser.add_argument("--promotion-queue", default=DEFAULT_PROMOTION_QUEUE)
    parser.add_argument(
        "--gap-homepage-file-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-nested-high-value-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_NESTED_HIGH_VALUE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-related-detail-high-value-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_RELATED_DETAIL_HIGH_VALUE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-current-file-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_CURRENT_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-current-related-detail-high-value-officialish-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_CURRENT_RELATED_DETAIL_HIGH_VALUE_OFFICIALISH_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-links-goal-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_LINKS_GOAL_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-links-goal2-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_LINKS_GOAL2_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--failed-homepage-retry-curl-fallback-promotion-queue",
        default=DEFAULT_FAILED_HOMEPAGE_RETRY_CURL_FALLBACK_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-links-nested-filtered-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_LINKS_NESTED_FILTERED_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-related-detail-followup-core-promotion-queue",
        default=DEFAULT_GAP_RELATED_DETAIL_FOLLOWUP_CORE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-worklist-fetched-uncovered-promotion-queue",
        default=DEFAULT_GAP_WORKLIST_FETCHED_UNCOVERED_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-syu-related-detail-promotion-queue",
        default=DEFAULT_GAP_SYU_RELATED_DETAIL_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dcatholic-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DCATHOLIC_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-calvin-promotion-queue",
        default=DEFAULT_GAP_MANUAL_CALVIN_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-ytus-promotion-queue",
        default=DEFAULT_GAP_MANUAL_YTUS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-ytus-2021-archive-regular-promotion-queue",
        default=DEFAULT_GAP_YTUS_2021_ARCHIVE_REGULAR_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-bpu-promotion-queue",
        default=DEFAULT_GAP_MANUAL_BPU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-youngsan-promotion-queue",
        default=DEFAULT_GAP_MANUAL_YOUNGSAN_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-crawler-ready-promotion-queue",
        default=DEFAULT_GAP_CRAWLER_READY_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-crawler-detail-fetch-promotion-queue",
        default=DEFAULT_GAP_CRAWLER_DETAIL_FETCH_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-crawler-attachment-ready-related-detail-high-value-promotion-queue",
        default=DEFAULT_GAP_CRAWLER_ATTACHMENT_READY_RELATED_DETAIL_HIGH_VALUE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-crawler-residual-hidden-download-promotion-queue",
        default=DEFAULT_GAP_CRAWLER_RESIDUAL_HIDDEN_DOWNLOAD_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-kwangshin-current-undergrad-hidden-download-promotion-queue",
        default=DEFAULT_GAP_KWANGSHIN_CURRENT_UNDERGRAD_HIDDEN_DOWNLOAD_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-kwangshin-competition-inline-ocr-promotion-queue",
        default=DEFAULT_GAP_KWANGSHIN_COMPETITION_INLINE_OCR_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-image-attachment-ocr-promotion-queue",
        default=DEFAULT_GAP_IMAGE_ATTACHMENT_OCR_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-manual-yewon-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_MANUAL_YEWON_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-related-detail-ready-promotion-queue",
        default=DEFAULT_GAP_RELATED_DETAIL_READY_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-link-ready-manual-gnu-promotion-queue",
        default=DEFAULT_GAP_LINK_READY_MANUAL_GNU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-gnu-archive-promotion-queue",
        default=DEFAULT_MANUAL_GNU_ARCHIVE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-rendered-eulji-promotion-queue",
        default=DEFAULT_GAP_RENDERED_EULJI_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-gjc-promotion-queue",
        default=DEFAULT_GAP_MANUAL_GJC_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-anyang-promotion-queue",
        default=DEFAULT_GAP_MANUAL_ANYANG_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-catholic-promotion-queue",
        default=DEFAULT_GAP_MANUAL_CATHOLIC_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-catholic-results-promotion-queue",
        default=DEFAULT_MANUAL_CATHOLIC_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-catholic-regular-results-promotion-queue",
        default=DEFAULT_MANUAL_CATHOLIC_REGULAR_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-catholic-regular-results-0000049-2022-promotion-queue",
        default=DEFAULT_MANUAL_CATHOLIC_REGULAR_RESULTS_0000049_2022_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-mju-regular-results-promotion-queue",
        default=DEFAULT_MANUAL_MJU_REGULAR_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-konyang-regular-results-promotion-queue",
        default=DEFAULT_MANUAL_KONYANG_REGULAR_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-cau-regular-results-promotion-queue",
        default=DEFAULT_MANUAL_CAU_REGULAR_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-gwnu-regular-results-promotion-queue",
        default=DEFAULT_MANUAL_GWNU_REGULAR_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-gwnu-older-results-promotion-queue",
        default=DEFAULT_MANUAL_GWNU_OLDER_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-ginue-regular-results-promotion-queue",
        default=DEFAULT_MANUAL_GINUE_REGULAR_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-iccu-2025-result-promotion-queue",
        default=DEFAULT_MANUAL_ICCU_2025_RESULT_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-iccu-result-promotion-queue",
        default=DEFAULT_MANUAL_ICCU_RESULT_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-catholic-songsin-promotion-queue",
        default=DEFAULT_GAP_MANUAL_CATHOLIC_SONGSIN_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-scu-promotion-queue",
        default=DEFAULT_GAP_MANUAL_SCU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-jnue-promotion-queue",
        default=DEFAULT_GAP_MANUAL_JNUE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-kyonggi-promotion-queue",
        default=DEFAULT_GAP_MANUAL_KYONGGI_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-ltu-promotion-queue",
        default=DEFAULT_GAP_MANUAL_LTU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-mokwon-promotion-queue",
        default=DEFAULT_GAP_MANUAL_MOKWON_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-skhu-promotion-queue",
        default=DEFAULT_GAP_MANUAL_SKHU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dongguk-wise-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DONGGUK_WISE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-korea-sejong-promotion-queue",
        default=DEFAULT_GAP_MANUAL_KOREA_SEJONG_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-kangwon-promotion-queue",
        default=DEFAULT_GAP_MANUAL_KANGWON_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dgau-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DGAU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dgau-recruitment-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DGAU_RECRUITMENT_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dgau-result-inline-ocr-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DGAU_RESULT_INLINE_OCR_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dgau-2022-result-inline-ocr-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DGAU_2022_RESULT_INLINE_OCR_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-kbtus-promotion-queue",
        default=DEFAULT_GAP_MANUAL_KBTUS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-https-homepage-retry-promotion-queue",
        default=DEFAULT_MANUAL_HTTPS_HOMEPAGE_RETRY_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-hanil-promotion-queue",
        default=DEFAULT_GAP_MANUAL_HANIL_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dongduk-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DONGDUK_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dankook-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DANKOOK_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-shinhan-promotion-queue",
        default=DEFAULT_GAP_MANUAL_SHINHAN_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-chosun-promotion-queue",
        default=DEFAULT_GAP_MANUAL_CHOSUN_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-hsmu-promotion-queue",
        default=DEFAULT_GAP_MANUAL_HSMU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-hsmu-retry-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_HSMU_RETRY_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-retry-expanded-files-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_RETRY_EXPANDED_FILES_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-koreatech-promotion-queue",
        default=DEFAULT_GAP_MANUAL_KOREATECH_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-kangnam-promotion-queue",
        default=DEFAULT_GAP_MANUAL_KANGNAM_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-pusan-promotion-queue",
        default=DEFAULT_GAP_MANUAL_PUSAN_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-jejunu-promotion-queue",
        default=DEFAULT_GAP_MANUAL_JEJUNU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-dcu-promotion-queue",
        default=DEFAULT_GAP_MANUAL_DCU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-cnue-promotion-queue",
        default=DEFAULT_GAP_MANUAL_CNUE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-hanseo-promotion-queue",
        default=DEFAULT_GAP_MANUAL_HANSEO_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-mtu-promotion-queue",
        default=DEFAULT_GAP_MANUAL_MTU_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-cup-promotion-queue",
        default=DEFAULT_GAP_MANUAL_CUP_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-sookmyung-promotion-queue",
        default=DEFAULT_GAP_MANUAL_SOOKMYUNG_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-sunmoon-sungkyul-promotion-queue",
        default=DEFAULT_GAP_MANUAL_SUNMOON_SUNGKYUL_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-schedule-p0-promotion-queue",
        default=DEFAULT_GAP_MANUAL_SCHEDULE_P0_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--homepage-html-p0-promotion-queue",
        default=DEFAULT_HOMEPAGE_HTML_P0_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-schedule-top-promotion-queue",
        default=DEFAULT_MANUAL_SCHEDULE_TOP_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-gjc-existing-file-promotion-queue",
        default=DEFAULT_GAP_GJC_EXISTING_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-cue-existing-file-promotion-queue",
        default=DEFAULT_GAP_CUE_EXISTING_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-semyung-uway-competition-promotion-queue",
        default=DEFAULT_GAP_SEMYUNG_UWAY_COMPETITION_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-cju-existing-file-promotion-queue",
        default=DEFAULT_GAP_CJU_EXISTING_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-small-admission-results-promotion-queue",
        default=DEFAULT_GAP_SMALL_ADMISSION_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-sejong-admission-results-promotion-queue",
        default=DEFAULT_GAP_SEJONG_ADMISSION_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-seowon-nested-file-routes-promotion-queue",
        default=DEFAULT_GAP_SEOWON_NESTED_FILE_ROUTES_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-crawler-fetch-ready-remaining-promotion-queue",
        default=DEFAULT_GAP_CRAWLER_FETCH_READY_REMAINING_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--script-nav-reparse-promotion-queue",
        default=DEFAULT_SCRIPT_NAV_REPARSE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--script-nav-reparse-nested-official-promotion-queue",
        default=DEFAULT_SCRIPT_NAV_REPARSE_NESTED_OFFICIAL_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-worklist-html-bridge-second-file-promotion-queue",
        default=DEFAULT_GAP_WORKLIST_HTML_BRIDGE_SECOND_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-worklist-html-bridge-third-file-promotion-queue",
        default=DEFAULT_GAP_WORKLIST_HTML_BRIDGE_THIRD_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--manual-homepage-seed-file-promotion-queue",
        default=DEFAULT_MANUAL_HOMEPAGE_SEED_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-worklist-html-bridge-post-manual-seed-promotion-queue",
        default=DEFAULT_GAP_WORKLIST_HTML_BRIDGE_POST_MANUAL_SEED_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-worklist-html-bridge-post-second-html-promotion-queue",
        default=DEFAULT_GAP_WORKLIST_HTML_BRIDGE_POST_SECOND_HTML_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-worklist-html-bridge-post-delta-promotion-queue",
        default=DEFAULT_GAP_WORKLIST_HTML_BRIDGE_POST_DELTA_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-sehan-current-apply-promotion-queue",
        default=DEFAULT_GAP_MANUAL_SEHAN_CURRENT_APPLY_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-suwon-catholic-current-promotion-queue",
        default=DEFAULT_GAP_MANUAL_SUWON_CATHOLIC_CURRENT_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-kaya-current-promotion-queue",
        default=DEFAULT_GAP_MANUAL_KAYA_CURRENT_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-links-post-manual-seed-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_LINKS_POST_MANUAL_SEED_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-links-refined-direct-file-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_LINKS_REFINED_DIRECT_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-homepage-links-p0-20260615-run2-direct-file-promotion-queue",
        default=DEFAULT_GAP_HOMEPAGE_LINKS_P0_20260615_RUN2_DIRECT_FILE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-collection-link-candidates-promotion-queue",
        default=DEFAULT_GAP_COLLECTION_LINK_CANDIDATES_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-collection-targets-p0-ysu-gnu-files-promotion-queue",
        default=DEFAULT_GAP_COLLECTION_TARGETS_P0_YSU_GNU_FILES_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-manual-gnu-2023-official-results-promotion-queue",
        default=DEFAULT_GAP_MANUAL_GNU_2023_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--seowon-2022-result-details-promotion-queue",
        default=DEFAULT_SEOWON_2022_RESULT_DETAILS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--seowon-2022-result-detail-files-promotion-queue",
        default=DEFAULT_SEOWON_2022_RESULT_DETAIL_FILES_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-hansei-post-adiga-slash-promotion-queue",
        default=DEFAULT_GAP_HANSEI_POST_ADIGA_SLASH_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-ysu-2021-official-results-promotion-queue",
        default=DEFAULT_GAP_YSU_2021_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-ysu-2022-official-results-promotion-queue",
        default=DEFAULT_GAP_YSU_2022_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-yewon-2021-legacy-results-promotion-queue",
        default=DEFAULT_GAP_YEWON_2021_LEGACY_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-yewon-2022-legacy-results-promotion-queue",
        default=DEFAULT_GAP_YEWON_2022_LEGACY_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-kyonggi-2022-official-score-promotion-queue",
        default=DEFAULT_GAP_KYONGGI_2022_OFFICIAL_SCORE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-kyonggi-2022-official-support-promotion-queue",
        default=DEFAULT_GAP_KYONGGI_2022_OFFICIAL_SUPPORT_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-kyonggi-2024-official-results-promotion-queue",
        default=DEFAULT_GAP_KYONGGI_2024_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-kyonggi-2025-official-results-promotion-queue",
        default=DEFAULT_GAP_KYONGGI_2025_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--joongbu-official-html-results-promotion-queue",
        default=DEFAULT_JOONGBU_OFFICIAL_HTML_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gknu-official-results-promotion-queue",
        default=DEFAULT_GKNU_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gachon-2022-official-results-promotion-queue",
        default=DEFAULT_GACHON_2022_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--skuniv-2026-official-results-promotion-queue",
        default=DEFAULT_SKUNIV_2026_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--ulsan-2021-official-results-promotion-queue",
        default=DEFAULT_ULSAN_2021_OFFICIAL_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--scnu-html-results-promotion-queue",
        default=DEFAULT_SCNU_HTML_RESULTS_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-ltu-2021-official-result-image-promotion-queue",
        default=DEFAULT_GAP_LTU_2021_OFFICIAL_RESULT_IMAGE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-worklist-file-high-value-promotion-queue",
        default=DEFAULT_GAP_WORKLIST_FILE_HIGH_VALUE_PROMOTION_QUEUE,
    )
    parser.add_argument(
        "--gap-worklist-linked-unpromoted-promotion-queue",
        action="append",
        default=list(DEFAULT_GAP_WORKLIST_LINKED_UNPROMOTED_PROMOTION_QUEUES),
    )
    parser.add_argument(
        "--js-download-file-promotion-queue",
        action="append",
        default=list(DEFAULT_JS_DOWNLOAD_FILE_PROMOTION_QUEUES),
    )
    parser.add_argument(
        "--zip-entry-promotion-queue",
        action="append",
        default=list(DEFAULT_ZIP_ENTRY_PROMOTION_QUEUES),
    )
    parser.add_argument("--academyinfo-rows", default=DEFAULT_ACADEMYINFO_ROWS)
    parser.add_argument("--adiga-rule-tables-glob", default=DEFAULT_ADIGA_RULE_TABLES_GLOB)
    parser.add_argument("--adiga-ocr-evidence", default=DEFAULT_ADIGA_OCR_EVIDENCE)
    parser.add_argument("--kice-grade-cuts", default=DEFAULT_KICE_GRADE_CUTS)
    parser.add_argument("--kice-distributions", default=DEFAULT_KICE_DISTRIBUTIONS)
    parser.add_argument("--kice-press-snippets", default=DEFAULT_KICE_PRESS_SNIPPETS)
    parser.add_argument("--kcue-snippets", default=DEFAULT_KCUE_SNIPPETS)
    parser.add_argument(
        "--manual-admission-unit-supplements",
        default=DEFAULT_MANUAL_ADMISSION_UNIT_SUPPLEMENTS,
    )
    parser.add_argument(
        "--manual-admission-office-evidence-supplements",
        default=DEFAULT_MANUAL_ADMISSION_OFFICE_EVIDENCE_SUPPLEMENTS,
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
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


def resolve_glob(repo_root: Path, pattern: str) -> list[Path]:
    path = Path(pattern)
    if path.is_absolute():
        return [Path(match) for match in sorted(path.parent.glob(path.name))]
    return [Path(match) for match in sorted(repo_root.glob(pattern))]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_jsonl_many(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(read_jsonl(path))
    return rows


def read_csv_many(paths: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(read_csv(path))
    return rows


def read_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def combine_promotion_rows(
    primary_rows: list[dict[str, Any]],
    gap_homepage_file_rows: list[dict[str, Any]],
    gap_homepage_nested_high_value_rows: list[dict[str, Any]],
    gap_homepage_related_detail_high_value_rows: list[dict[str, Any]],
    gap_homepage_current_file_rows: list[dict[str, Any]],
    gap_homepage_current_related_detail_high_value_officialish_rows: list[dict[str, Any]],
    gap_homepage_links_goal_rows: list[dict[str, Any]],
    gap_homepage_links_goal2_rows: list[dict[str, Any]],
    failed_homepage_retry_curl_fallback_rows: list[dict[str, Any]],
    gap_homepage_links_nested_filtered_rows: list[dict[str, Any]],
    gap_related_detail_followup_core_rows: list[dict[str, Any]],
    gap_worklist_fetched_uncovered_rows: list[dict[str, Any]],
    gap_syu_related_detail_rows: list[dict[str, Any]],
    gap_manual_dcatholic_rows: list[dict[str, Any]],
    gap_manual_calvin_rows: list[dict[str, Any]],
    gap_manual_ytus_rows: list[dict[str, Any]],
    gap_ytus_2021_archive_regular_rows: list[dict[str, Any]],
    gap_manual_bpu_rows: list[dict[str, Any]],
    gap_manual_youngsan_rows: list[dict[str, Any]],
    gap_crawler_ready_rows: list[dict[str, Any]],
    gap_crawler_detail_fetch_rows: list[dict[str, Any]],
    gap_crawler_attachment_ready_related_detail_high_value_rows: list[dict[str, Any]],
    gap_crawler_residual_hidden_download_rows: list[dict[str, Any]],
    gap_kwangshin_current_undergrad_hidden_download_rows: list[dict[str, Any]],
    gap_kwangshin_competition_inline_ocr_rows: list[dict[str, Any]],
    gap_image_attachment_ocr_rows: list[dict[str, Any]],
    gap_homepage_manual_yewon_rows: list[dict[str, Any]],
    gap_related_detail_ready_rows: list[dict[str, Any]],
    gap_link_ready_manual_gnu_rows: list[dict[str, Any]],
    manual_gnu_archive_rows: list[dict[str, Any]],
    gap_rendered_eulji_rows: list[dict[str, Any]],
    gap_manual_gjc_rows: list[dict[str, Any]],
    gap_manual_anyang_rows: list[dict[str, Any]],
    gap_manual_catholic_rows: list[dict[str, Any]],
    manual_catholic_results_rows: list[dict[str, Any]],
    manual_catholic_regular_results_rows: list[dict[str, Any]],
    manual_mju_regular_results_rows: list[dict[str, Any]],
    manual_konyang_regular_results_rows: list[dict[str, Any]],
    manual_cau_regular_results_rows: list[dict[str, Any]],
    manual_gwnu_regular_results_rows: list[dict[str, Any]],
    manual_ginue_regular_results_rows: list[dict[str, Any]],
    manual_iccu_2025_result_rows: list[dict[str, Any]],
    manual_iccu_result_rows: list[dict[str, Any]],
    gap_manual_catholic_songsin_rows: list[dict[str, Any]],
    gap_manual_scu_rows: list[dict[str, Any]],
    gap_manual_jnue_rows: list[dict[str, Any]],
    gap_manual_kyonggi_rows: list[dict[str, Any]],
    gap_manual_ltu_rows: list[dict[str, Any]],
    gap_manual_mokwon_rows: list[dict[str, Any]],
    gap_manual_skhu_rows: list[dict[str, Any]],
    gap_manual_dongguk_wise_rows: list[dict[str, Any]],
    gap_manual_korea_sejong_rows: list[dict[str, Any]],
    gap_manual_kangwon_rows: list[dict[str, Any]],
    gap_manual_dgau_rows: list[dict[str, Any]],
    gap_manual_dgau_recruitment_rows: list[dict[str, Any]],
    gap_manual_dgau_result_inline_ocr_rows: list[dict[str, Any]],
    gap_manual_kbtus_rows: list[dict[str, Any]],
    manual_https_homepage_retry_rows: list[dict[str, Any]],
    gap_manual_hanil_rows: list[dict[str, Any]],
    gap_manual_dongduk_rows: list[dict[str, Any]],
    gap_manual_dankook_rows: list[dict[str, Any]],
    gap_manual_shinhan_rows: list[dict[str, Any]],
    gap_manual_chosun_rows: list[dict[str, Any]],
    gap_manual_hsmu_rows: list[dict[str, Any]],
    gap_homepage_hsmu_retry_rows: list[dict[str, Any]],
    gap_homepage_retry_expanded_files_rows: list[dict[str, Any]],
    gap_manual_koreatech_rows: list[dict[str, Any]],
    gap_manual_kangnam_rows: list[dict[str, Any]],
    gap_manual_pusan_rows: list[dict[str, Any]],
    gap_manual_jejunu_rows: list[dict[str, Any]],
    gap_manual_dcu_rows: list[dict[str, Any]],
    gap_manual_cnue_rows: list[dict[str, Any]],
    gap_manual_hanseo_rows: list[dict[str, Any]],
    gap_manual_mtu_rows: list[dict[str, Any]],
    gap_manual_cup_rows: list[dict[str, Any]],
    gap_manual_sookmyung_rows: list[dict[str, Any]],
    gap_manual_sunmoon_sungkyul_rows: list[dict[str, Any]],
    gap_manual_schedule_p0_rows: list[dict[str, Any]],
    homepage_html_p0_rows: list[dict[str, Any]],
    manual_schedule_top_rows: list[dict[str, Any]],
    gap_gjc_existing_file_rows: list[dict[str, Any]],
    gap_cue_existing_file_rows: list[dict[str, Any]],
    gap_semyung_uway_competition_rows: list[dict[str, Any]],
    gap_cju_existing_file_rows: list[dict[str, Any]],
    gap_small_admission_results_rows: list[dict[str, Any]],
    gap_sejong_admission_results_rows: list[dict[str, Any]],
    gap_seowon_nested_file_routes_rows: list[dict[str, Any]],
    gap_crawler_fetch_ready_remaining_rows: list[dict[str, Any]],
    script_nav_reparse_rows: list[dict[str, Any]],
    script_nav_reparse_nested_official_rows: list[dict[str, Any]],
    gap_worklist_html_bridge_second_file_rows: list[dict[str, Any]],
    gap_worklist_html_bridge_third_file_rows: list[dict[str, Any]],
    manual_homepage_seed_file_rows: list[dict[str, Any]],
    gap_worklist_html_bridge_post_manual_seed_rows: list[dict[str, Any]],
    gap_worklist_html_bridge_post_second_html_rows: list[dict[str, Any]],
    gap_worklist_html_bridge_post_delta_rows: list[dict[str, Any]],
    gap_manual_sehan_current_apply_rows: list[dict[str, Any]],
    gap_manual_suwon_catholic_current_rows: list[dict[str, Any]],
    gap_manual_kaya_current_rows: list[dict[str, Any]],
    gap_homepage_links_post_manual_seed_rows: list[dict[str, Any]],
    gap_homepage_links_refined_direct_file_rows: list[dict[str, Any]],
    gap_homepage_links_p0_20260615_run2_direct_file_rows: list[dict[str, Any]],
    gap_collection_link_candidates_rows: list[dict[str, Any]],
    gap_collection_targets_p0_ysu_gnu_files_rows: list[dict[str, Any]],
    gap_manual_gnu_2023_official_results_rows: list[dict[str, Any]],
    seowon_2022_result_details_rows: list[dict[str, Any]],
    seowon_2022_result_detail_files_rows: list[dict[str, Any]],
    gap_hansei_post_adiga_slash_rows: list[dict[str, Any]],
    gap_ysu_2021_official_results_rows: list[dict[str, Any]],
    gap_ysu_2022_official_results_rows: list[dict[str, Any]],
    gap_yewon_2021_legacy_results_rows: list[dict[str, Any]],
    gap_yewon_2022_legacy_results_rows: list[dict[str, Any]],
    gap_kyonggi_2022_official_score_rows: list[dict[str, Any]],
    gap_kyonggi_2022_official_support_rows: list[dict[str, Any]],
    gap_kyonggi_2024_official_results_rows: list[dict[str, Any]],
    gap_kyonggi_2025_official_results_rows: list[dict[str, Any]],
    joongbu_official_html_results_rows: list[dict[str, Any]],
    gknu_official_results_rows: list[dict[str, Any]],
    gachon_2022_official_results_rows: list[dict[str, Any]],
    skuniv_2026_official_results_rows: list[dict[str, Any]],
    ulsan_2021_official_results_rows: list[dict[str, Any]],
    scnu_html_results_rows: list[dict[str, Any]],
    gap_ltu_2021_official_result_image_rows: list[dict[str, Any]],
    gap_worklist_file_high_value_rows: list[dict[str, Any]],
    gap_worklist_linked_unpromoted_rows: list[dict[str, Any]],
    js_download_file_rows: list[dict[str, Any]],
    zip_entry_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows_by_sha: dict[str, dict[str, Any]] = {}
    duplicate_rows = 0
    blocked_helper_rows = 0
    gnu_2021_result_year_mismatch_rows = 0
    manual_schedule_top_year_mismatch_rows = 0
    script_nav_reparse_nested_official_filtered_rows = 0
    input_rows = 0
    for source_label, rows in (
        ("primary_admission_office", primary_rows),
        ("gap_homepage_file_docs", gap_homepage_file_rows),
        ("gap_homepage_nested_high_value_docs", gap_homepage_nested_high_value_rows),
        (
            "gap_homepage_related_detail_high_value_docs",
            gap_homepage_related_detail_high_value_rows,
        ),
        ("gap_homepage_current_file_docs", gap_homepage_current_file_rows),
        (
            "gap_homepage_current_related_detail_high_value_officialish_docs",
            gap_homepage_current_related_detail_high_value_officialish_rows,
        ),
        ("gap_homepage_links_goal_docs", gap_homepage_links_goal_rows),
        ("gap_homepage_links_goal2_docs", gap_homepage_links_goal2_rows),
        (
            "failed_homepage_retry_curl_fallback_docs",
            failed_homepage_retry_curl_fallback_rows,
        ),
        (
            "gap_homepage_links_nested_filtered_docs",
            gap_homepage_links_nested_filtered_rows,
        ),
        (
            "gap_related_detail_followup_core_docs",
            gap_related_detail_followup_core_rows,
        ),
        ("gap_worklist_fetched_uncovered_docs", gap_worklist_fetched_uncovered_rows),
        ("gap_syu_related_detail_docs", gap_syu_related_detail_rows),
        ("gap_manual_dcatholic_docs", gap_manual_dcatholic_rows),
        ("gap_manual_calvin_docs", gap_manual_calvin_rows),
        ("gap_manual_ytus_docs", gap_manual_ytus_rows),
        ("gap_ytus_2021_archive_regular_docs", gap_ytus_2021_archive_regular_rows),
        ("gap_manual_bpu_docs", gap_manual_bpu_rows),
        ("gap_manual_youngsan_docs", gap_manual_youngsan_rows),
        ("gap_crawler_ready_docs", gap_crawler_ready_rows),
        ("gap_crawler_detail_fetch_docs", gap_crawler_detail_fetch_rows),
        (
            "gap_crawler_attachment_ready_related_detail_high_value_docs",
            gap_crawler_attachment_ready_related_detail_high_value_rows,
        ),
        ("gap_crawler_residual_hidden_download_docs", gap_crawler_residual_hidden_download_rows),
        (
            "gap_kwangshin_current_undergrad_hidden_download_docs",
            gap_kwangshin_current_undergrad_hidden_download_rows,
        ),
        (
            "gap_kwangshin_competition_inline_ocr_docs",
            gap_kwangshin_competition_inline_ocr_rows,
        ),
        ("gap_image_attachment_ocr_docs", gap_image_attachment_ocr_rows),
        ("gap_homepage_manual_yewon_docs", gap_homepage_manual_yewon_rows),
        ("gap_related_detail_ready_docs", gap_related_detail_ready_rows),
        ("gap_link_ready_manual_gnu_docs", gap_link_ready_manual_gnu_rows),
        ("manual_gnu_archive_docs", manual_gnu_archive_rows),
        ("gap_rendered_eulji_docs", gap_rendered_eulji_rows),
        ("gap_manual_gjc_docs", gap_manual_gjc_rows),
        ("gap_manual_anyang_docs", gap_manual_anyang_rows),
        ("gap_manual_catholic_docs", gap_manual_catholic_rows),
        ("manual_catholic_results_docs", manual_catholic_results_rows),
        (
            "manual_catholic_regular_results_docs",
            manual_catholic_regular_results_rows,
        ),
        ("manual_mju_regular_results_docs", manual_mju_regular_results_rows),
        ("manual_konyang_regular_results_docs", manual_konyang_regular_results_rows),
        ("manual_cau_regular_results_docs", manual_cau_regular_results_rows),
        ("manual_gwnu_regular_results_docs", manual_gwnu_regular_results_rows),
        ("manual_ginue_regular_results_docs", manual_ginue_regular_results_rows),
        ("manual_iccu_2025_result_docs", manual_iccu_2025_result_rows),
        ("manual_iccu_result_docs", manual_iccu_result_rows),
        ("gap_manual_catholic_songsin_docs", gap_manual_catholic_songsin_rows),
        ("gap_manual_scu_docs", gap_manual_scu_rows),
        ("gap_manual_jnue_docs", gap_manual_jnue_rows),
        ("gap_manual_kyonggi_docs", gap_manual_kyonggi_rows),
        ("gap_manual_ltu_docs", gap_manual_ltu_rows),
        ("gap_manual_mokwon_docs", gap_manual_mokwon_rows),
        ("gap_manual_skhu_docs", gap_manual_skhu_rows),
        ("gap_manual_dongguk_wise_docs", gap_manual_dongguk_wise_rows),
        ("gap_manual_korea_sejong_docs", gap_manual_korea_sejong_rows),
        ("gap_manual_kangwon_docs", gap_manual_kangwon_rows),
        ("gap_manual_dgau_docs", gap_manual_dgau_rows),
        ("gap_manual_dgau_recruitment_docs", gap_manual_dgau_recruitment_rows),
        ("gap_manual_dgau_result_inline_ocr_docs", gap_manual_dgau_result_inline_ocr_rows),
        ("gap_manual_kbtus_docs", gap_manual_kbtus_rows),
        ("manual_https_homepage_retry_docs", manual_https_homepage_retry_rows),
        ("gap_manual_hanil_docs", gap_manual_hanil_rows),
        ("gap_manual_dongduk_docs", gap_manual_dongduk_rows),
        ("gap_manual_dankook_docs", gap_manual_dankook_rows),
        ("gap_manual_shinhan_docs", gap_manual_shinhan_rows),
        ("gap_manual_chosun_docs", gap_manual_chosun_rows),
        ("gap_manual_hsmu_docs", gap_manual_hsmu_rows),
        ("gap_homepage_hsmu_retry_docs", gap_homepage_hsmu_retry_rows),
        (
            "gap_homepage_retry_expanded_files_docs",
            gap_homepage_retry_expanded_files_rows,
        ),
        ("gap_manual_koreatech_docs", gap_manual_koreatech_rows),
        ("gap_manual_kangnam_docs", gap_manual_kangnam_rows),
        ("gap_manual_pusan_docs", gap_manual_pusan_rows),
        ("gap_manual_jejunu_docs", gap_manual_jejunu_rows),
        ("gap_manual_dcu_docs", gap_manual_dcu_rows),
        ("gap_manual_cnue_docs", gap_manual_cnue_rows),
        ("gap_manual_hanseo_docs", gap_manual_hanseo_rows),
        ("gap_manual_mtu_docs", gap_manual_mtu_rows),
        ("gap_manual_cup_docs", gap_manual_cup_rows),
        ("gap_manual_sookmyung_docs", gap_manual_sookmyung_rows),
        ("gap_manual_sunmoon_sungkyul_docs", gap_manual_sunmoon_sungkyul_rows),
        ("gap_manual_schedule_p0_docs", gap_manual_schedule_p0_rows),
        ("homepage_html_p0_docs", homepage_html_p0_rows),
        ("manual_schedule_top_docs", manual_schedule_top_rows),
        ("gap_gjc_existing_file_docs", gap_gjc_existing_file_rows),
        ("gap_cue_existing_file_docs", gap_cue_existing_file_rows),
        ("gap_semyung_uway_competition_docs", gap_semyung_uway_competition_rows),
        ("gap_cju_existing_file_docs", gap_cju_existing_file_rows),
        ("gap_small_admission_results_docs", gap_small_admission_results_rows),
        ("gap_sejong_admission_results_docs", gap_sejong_admission_results_rows),
        ("gap_seowon_nested_file_routes_docs", gap_seowon_nested_file_routes_rows),
        ("gap_crawler_fetch_ready_remaining_docs", gap_crawler_fetch_ready_remaining_rows),
        ("script_nav_reparse_docs", script_nav_reparse_rows),
        (
            "script_nav_reparse_nested_official_docs",
            script_nav_reparse_nested_official_rows,
        ),
        (
            "gap_worklist_html_bridge_second_file_docs",
            gap_worklist_html_bridge_second_file_rows,
        ),
        (
            "gap_worklist_html_bridge_third_file_docs",
            gap_worklist_html_bridge_third_file_rows,
        ),
        ("manual_homepage_seed_file_docs", manual_homepage_seed_file_rows),
        (
            "gap_worklist_html_bridge_post_manual_seed_html_docs",
            gap_worklist_html_bridge_post_manual_seed_rows,
        ),
        (
            "gap_worklist_html_bridge_post_second_html_docs",
            gap_worklist_html_bridge_post_second_html_rows,
        ),
        (
            "gap_worklist_html_bridge_post_delta_docs",
            gap_worklist_html_bridge_post_delta_rows,
        ),
        ("gap_manual_sehan_current_apply_docs", gap_manual_sehan_current_apply_rows),
        (
            "gap_manual_suwon_catholic_current_docs",
            gap_manual_suwon_catholic_current_rows,
        ),
        ("gap_manual_kaya_current_docs", gap_manual_kaya_current_rows),
        (
            "gap_homepage_links_post_manual_seed_html_docs",
            gap_homepage_links_post_manual_seed_rows,
        ),
        (
            "gap_homepage_links_refined_direct_file_docs",
            gap_homepage_links_refined_direct_file_rows,
        ),
        (
            "gap_homepage_links_p0_20260615_run2_direct_file_docs",
            gap_homepage_links_p0_20260615_run2_direct_file_rows,
        ),
        (
            "gap_collection_link_candidates_docs",
            gap_collection_link_candidates_rows,
        ),
        (
            "gap_collection_targets_p0_ysu_gnu_files_docs",
            gap_collection_targets_p0_ysu_gnu_files_rows,
        ),
        (
            "gap_manual_gnu_2023_official_results_docs",
            gap_manual_gnu_2023_official_results_rows,
        ),
        ("seowon_2022_result_details_docs", seowon_2022_result_details_rows),
        (
            "seowon_2022_result_detail_files_docs",
            seowon_2022_result_detail_files_rows,
        ),
        ("gap_hansei_post_adiga_slash_docs", gap_hansei_post_adiga_slash_rows),
        ("gap_ysu_2021_official_results_docs", gap_ysu_2021_official_results_rows),
        ("gap_ysu_2022_official_results_docs", gap_ysu_2022_official_results_rows),
        ("gap_yewon_2021_legacy_results_docs", gap_yewon_2021_legacy_results_rows),
        ("gap_yewon_2022_legacy_results_docs", gap_yewon_2022_legacy_results_rows),
        ("gap_kyonggi_2022_official_score_docs", gap_kyonggi_2022_official_score_rows),
        (
            "gap_kyonggi_2022_official_support_docs",
            gap_kyonggi_2022_official_support_rows,
        ),
        ("gap_kyonggi_2024_official_results_docs", gap_kyonggi_2024_official_results_rows),
        ("gap_kyonggi_2025_official_results_docs", gap_kyonggi_2025_official_results_rows),
        ("joongbu_official_html_results_docs", joongbu_official_html_results_rows),
        ("gknu_official_results_docs", gknu_official_results_rows),
        ("gachon_2022_official_results_docs", gachon_2022_official_results_rows),
        ("skuniv_2026_official_results_docs", skuniv_2026_official_results_rows),
        ("ulsan_2021_official_results_docs", ulsan_2021_official_results_rows),
        ("scnu_html_results_docs", scnu_html_results_rows),
        ("gap_ltu_2021_official_result_image_docs", gap_ltu_2021_official_result_image_rows),
        ("gap_worklist_file_high_value_docs", gap_worklist_file_high_value_rows),
        ("gap_worklist_linked_unpromoted_docs", gap_worklist_linked_unpromoted_rows),
        ("js_download_file_docs", js_download_file_rows),
        ("zip_entry_docs", zip_entry_rows),
    ):
        for index, row in enumerate(rows):
            input_rows += 1
            if source_label == "manual_schedule_top_docs" and not (
                promotion_row_has_collection_detected_year_overlap(row)
            ):
                manual_schedule_top_year_mismatch_rows += 1
                continue
            if source_label == "script_nav_reparse_nested_official_docs" and not (
                is_script_nav_reparse_nested_official_promotable(row)
            ):
                script_nav_reparse_nested_official_filtered_rows += 1
                continue
            if promotion_row_has_blocked_helper_source(row):
                blocked_helper_rows += 1
                continue
            if promotion_row_has_gnu_2021_result_year_mismatch(row):
                gnu_2021_result_year_mismatch_rows += 1
                continue
            candidate_sha = normalize_text(row.get("candidateSha256")) or deterministic_hash(
                f"{source_label}:{index}:{json.dumps(row, ensure_ascii=False, sort_keys=True)}"
            )
            if candidate_sha in rows_by_sha:
                duplicate_rows += 1
                merge_promotion_source(rows_by_sha[candidate_sha], row, source_label)
                continue
            rows_by_sha[candidate_sha] = initialize_promotion_source(row, source_label)
    return (
        list(rows_by_sha.values()),
        {
            "admissionOfficePromotionInputRows": input_rows,
            "admissionOfficePrimaryPromotionRows": len(primary_rows),
            "admissionOfficeGapHomepageFilePromotionRows": len(gap_homepage_file_rows),
            "admissionOfficeGapHomepageNestedHighValuePromotionRows": len(
                gap_homepage_nested_high_value_rows
            ),
            "admissionOfficeGapHomepageRelatedDetailHighValuePromotionRows": len(
                gap_homepage_related_detail_high_value_rows
            ),
            "admissionOfficeGapHomepageCurrentFilePromotionRows": len(
                gap_homepage_current_file_rows
            ),
            "admissionOfficeGapHomepageCurrentRelatedDetailHighValueOfficialishPromotionRows": (
                len(gap_homepage_current_related_detail_high_value_officialish_rows)
            ),
            "admissionOfficeGapHomepageLinksGoalPromotionRows": len(
                gap_homepage_links_goal_rows
            ),
            "admissionOfficeGapHomepageLinksGoal2PromotionRows": len(
                gap_homepage_links_goal2_rows
            ),
            "admissionOfficeFailedHomepageRetryCurlFallbackPromotionRows": len(
                failed_homepage_retry_curl_fallback_rows
            ),
            "admissionOfficeGapHomepageLinksNestedFilteredPromotionRows": len(
                gap_homepage_links_nested_filtered_rows
            ),
            "admissionOfficeGapRelatedDetailFollowupCorePromotionRows": len(
                gap_related_detail_followup_core_rows
            ),
            "admissionOfficeGapWorklistFetchedUncoveredPromotionRows": len(
                gap_worklist_fetched_uncovered_rows
            ),
            "admissionOfficeGapSyuRelatedDetailPromotionRows": len(
                gap_syu_related_detail_rows
            ),
            "admissionOfficeGapManualDcatholicPromotionRows": len(
                gap_manual_dcatholic_rows
            ),
            "admissionOfficeGapManualCalvinPromotionRows": len(gap_manual_calvin_rows),
            "admissionOfficeGapManualYtusPromotionRows": len(gap_manual_ytus_rows),
            "admissionOfficeGapYtus2021ArchiveRegularPromotionRows": len(
                gap_ytus_2021_archive_regular_rows
            ),
            "admissionOfficeGapManualBpuPromotionRows": len(gap_manual_bpu_rows),
            "admissionOfficeGapManualYoungsanPromotionRows": len(gap_manual_youngsan_rows),
            "admissionOfficeGapCrawlerReadyPromotionRows": len(gap_crawler_ready_rows),
            "admissionOfficeGapCrawlerDetailFetchPromotionRows": len(
                gap_crawler_detail_fetch_rows
            ),
            "admissionOfficeGapCrawlerAttachmentReadyRelatedDetailHighValuePromotionRows": len(
                gap_crawler_attachment_ready_related_detail_high_value_rows
            ),
            "admissionOfficeGapCrawlerResidualHiddenDownloadPromotionRows": len(
                gap_crawler_residual_hidden_download_rows
            ),
            "admissionOfficeGapKwangshinCurrentUndergradHiddenDownloadPromotionRows": len(
                gap_kwangshin_current_undergrad_hidden_download_rows
            ),
            "admissionOfficeGapKwangshinCompetitionInlineOcrPromotionRows": len(
                gap_kwangshin_competition_inline_ocr_rows
            ),
            "admissionOfficeGapImageAttachmentOcrPromotionRows": len(
                gap_image_attachment_ocr_rows
            ),
            "admissionOfficeGapHomepageManualYewonPromotionRows": len(
                gap_homepage_manual_yewon_rows
            ),
            "admissionOfficeGapRelatedDetailReadyPromotionRows": len(
                gap_related_detail_ready_rows
            ),
            "admissionOfficeGapLinkReadyManualGnuPromotionRows": len(
                gap_link_ready_manual_gnu_rows
            ),
            "admissionOfficeManualGnuArchivePromotionRows": len(manual_gnu_archive_rows),
            "admissionOfficeGapRenderedEuljiPromotionRows": len(gap_rendered_eulji_rows),
            "admissionOfficeGapManualGjcPromotionRows": len(gap_manual_gjc_rows),
            "admissionOfficeGapManualAnyangPromotionRows": len(gap_manual_anyang_rows),
            "admissionOfficeGapManualCatholicPromotionRows": len(
                gap_manual_catholic_rows
            ),
            "admissionOfficeManualCatholicResultsPromotionRows": len(
                manual_catholic_results_rows
            ),
            "admissionOfficeManualCatholicRegularResultsPromotionRows": len(
                manual_catholic_regular_results_rows
            ),
            "admissionOfficeManualMjuRegularResultsPromotionRows": len(
                manual_mju_regular_results_rows
            ),
            "admissionOfficeManualKonyangRegularResultsPromotionRows": len(
                manual_konyang_regular_results_rows
            ),
            "admissionOfficeManualCauRegularResultsPromotionRows": len(
                manual_cau_regular_results_rows
            ),
            "admissionOfficeManualGwnuRegularResultsPromotionRows": len(
                manual_gwnu_regular_results_rows
            ),
            "admissionOfficeManualIccu2025ResultPromotionRows": len(
                manual_iccu_2025_result_rows
            ),
            "admissionOfficeManualIccuResultPromotionRows": len(
                manual_iccu_result_rows
            ),
            "admissionOfficeGapManualCatholicSongsinPromotionRows": len(
                gap_manual_catholic_songsin_rows
            ),
            "admissionOfficeGapManualScuPromotionRows": len(gap_manual_scu_rows),
            "admissionOfficeGapManualJnuePromotionRows": len(gap_manual_jnue_rows),
            "admissionOfficeGapManualKyonggiPromotionRows": len(
                gap_manual_kyonggi_rows
            ),
            "admissionOfficeGapManualLtuPromotionRows": len(gap_manual_ltu_rows),
            "admissionOfficeGapManualMokwonPromotionRows": len(
                gap_manual_mokwon_rows
            ),
            "admissionOfficeGapManualSkhuPromotionRows": len(
                gap_manual_skhu_rows
            ),
            "admissionOfficeGapManualDonggukWisePromotionRows": len(
                gap_manual_dongguk_wise_rows
            ),
            "admissionOfficeGapManualKoreaSejongPromotionRows": len(
                gap_manual_korea_sejong_rows
            ),
            "admissionOfficeGapManualKangwonPromotionRows": len(
                gap_manual_kangwon_rows
            ),
            "admissionOfficeGapManualDgauPromotionRows": len(
                gap_manual_dgau_rows
            ),
            "admissionOfficeGapManualDgauRecruitmentPromotionRows": len(
                gap_manual_dgau_recruitment_rows
            ),
            "admissionOfficeGapManualDgauResultInlineOcrPromotionRows": len(
                gap_manual_dgau_result_inline_ocr_rows
            ),
            "admissionOfficeGapManualKbtusPromotionRows": len(
                gap_manual_kbtus_rows
            ),
            "admissionOfficeManualHttpsHomepageRetryPromotionRows": len(
                manual_https_homepage_retry_rows
            ),
            "admissionOfficeGapManualHanilPromotionRows": len(
                gap_manual_hanil_rows
            ),
            "admissionOfficeGapManualDongdukPromotionRows": len(
                gap_manual_dongduk_rows
            ),
            "admissionOfficeGapManualDankookPromotionRows": len(
                gap_manual_dankook_rows
            ),
            "admissionOfficeGapManualShinhanPromotionRows": len(
                gap_manual_shinhan_rows
            ),
            "admissionOfficeGapManualChosunPromotionRows": len(
                gap_manual_chosun_rows
            ),
            "admissionOfficeGapManualHsmuPromotionRows": len(
                gap_manual_hsmu_rows
            ),
            "admissionOfficeGapHomepageHsmuRetryPromotionRows": len(
                gap_homepage_hsmu_retry_rows
            ),
            "admissionOfficeGapHomepageRetryExpandedFilesPromotionRows": len(
                gap_homepage_retry_expanded_files_rows
            ),
            "admissionOfficeGapManualKoreatechPromotionRows": len(
                gap_manual_koreatech_rows
            ),
            "admissionOfficeGapManualKangnamPromotionRows": len(
                gap_manual_kangnam_rows
            ),
            "admissionOfficeGapManualPusanPromotionRows": len(
                gap_manual_pusan_rows
            ),
            "admissionOfficeGapManualJejunuPromotionRows": len(
                gap_manual_jejunu_rows
            ),
            "admissionOfficeGapManualDcuPromotionRows": len(
                gap_manual_dcu_rows
            ),
            "admissionOfficeGapManualCnuePromotionRows": len(
                gap_manual_cnue_rows
            ),
            "admissionOfficeGapManualHanseoPromotionRows": len(
                gap_manual_hanseo_rows
            ),
            "admissionOfficeGapManualMtuPromotionRows": len(gap_manual_mtu_rows),
            "admissionOfficeGapManualCupPromotionRows": len(gap_manual_cup_rows),
            "admissionOfficeGapManualSookmyungPromotionRows": len(
                gap_manual_sookmyung_rows
            ),
            "admissionOfficeGapManualSunmoonSungkyulPromotionRows": len(
                gap_manual_sunmoon_sungkyul_rows
            ),
            "admissionOfficeGapManualScheduleP0PromotionRows": len(
                gap_manual_schedule_p0_rows
            ),
            "admissionOfficeHomepageHtmlP0PromotionRows": len(homepage_html_p0_rows),
            "admissionOfficeManualScheduleTopPromotionRows": len(
                manual_schedule_top_rows
            ),
            "admissionOfficeManualScheduleTopYearMismatchRows": (
                manual_schedule_top_year_mismatch_rows
            ),
            "admissionOfficeGapGjcExistingFilePromotionRows": len(
                gap_gjc_existing_file_rows
            ),
            "admissionOfficeGapCueExistingFilePromotionRows": len(
                gap_cue_existing_file_rows
            ),
            "admissionOfficeGapSemyungUwayCompetitionPromotionRows": len(
                gap_semyung_uway_competition_rows
            ),
            "admissionOfficeGapCjuExistingFilePromotionRows": len(
                gap_cju_existing_file_rows
            ),
            "admissionOfficeGapSmallAdmissionResultsPromotionRows": len(
                gap_small_admission_results_rows
            ),
            "admissionOfficeGapSejongAdmissionResultsPromotionRows": len(
                gap_sejong_admission_results_rows
            ),
            "admissionOfficeGapSeowonNestedFileRoutesPromotionRows": len(
                gap_seowon_nested_file_routes_rows
            ),
            "admissionOfficeGapCrawlerFetchReadyRemainingPromotionRows": len(
                gap_crawler_fetch_ready_remaining_rows
            ),
            "admissionOfficeScriptNavReparsePromotionRows": len(script_nav_reparse_rows),
            "admissionOfficeScriptNavReparseNestedOfficialPromotionRows": len(
                script_nav_reparse_nested_official_rows
            ),
            "admissionOfficeScriptNavReparseNestedOfficialFilteredRows": (
                script_nav_reparse_nested_official_filtered_rows
            ),
            "admissionOfficeGapWorklistHtmlBridgeSecondFilePromotionRows": len(
                gap_worklist_html_bridge_second_file_rows
            ),
            "admissionOfficeGapWorklistHtmlBridgeThirdFilePromotionRows": len(
                gap_worklist_html_bridge_third_file_rows
            ),
            "admissionOfficeManualHomepageSeedFilePromotionRows": len(
                manual_homepage_seed_file_rows
            ),
            "admissionOfficeGapWorklistHtmlBridgePostManualSeedPromotionRows": len(
                gap_worklist_html_bridge_post_manual_seed_rows
            ),
            "admissionOfficeGapWorklistHtmlBridgePostSecondHtmlPromotionRows": len(
                gap_worklist_html_bridge_post_second_html_rows
            ),
            "admissionOfficeGapWorklistHtmlBridgePostDeltaPromotionRows": len(
                gap_worklist_html_bridge_post_delta_rows
            ),
            "admissionOfficeGapManualSehanCurrentApplyPromotionRows": len(
                gap_manual_sehan_current_apply_rows
            ),
            "admissionOfficeGapManualSuwonCatholicCurrentPromotionRows": len(
                gap_manual_suwon_catholic_current_rows
            ),
            "admissionOfficeGapManualKayaCurrentPromotionRows": len(
                gap_manual_kaya_current_rows
            ),
            "admissionOfficeGapHomepageLinksPostManualSeedPromotionRows": len(
                gap_homepage_links_post_manual_seed_rows
            ),
            "admissionOfficeGapHomepageLinksRefinedDirectFilePromotionRows": len(
                gap_homepage_links_refined_direct_file_rows
            ),
            "admissionOfficeGapHomepageLinksP020260615Run2DirectFilePromotionRows": len(
                gap_homepage_links_p0_20260615_run2_direct_file_rows
            ),
            "admissionOfficeGapCollectionLinkCandidatesPromotionRows": len(
                gap_collection_link_candidates_rows
            ),
            "admissionOfficeGapCollectionTargetsP0YsuGnuFilesPromotionRows": len(
                gap_collection_targets_p0_ysu_gnu_files_rows
            ),
            "admissionOfficeGapManualGnu2023OfficialResultsPromotionRows": len(
                gap_manual_gnu_2023_official_results_rows
            ),
            "admissionOfficeSeowon2022ResultDetailsPromotionRows": len(
                seowon_2022_result_details_rows
            ),
            "admissionOfficeSeowon2022ResultDetailFilesPromotionRows": len(
                seowon_2022_result_detail_files_rows
            ),
            "admissionOfficeGapHanseiPostAdigaSlashPromotionRows": len(
                gap_hansei_post_adiga_slash_rows
            ),
            "admissionOfficeGapYsu2021OfficialResultsPromotionRows": len(
                gap_ysu_2021_official_results_rows
            ),
            "admissionOfficeGapYewon2021LegacyResultsPromotionRows": len(
                gap_yewon_2021_legacy_results_rows
            ),
            "admissionOfficeGapYewon2022LegacyResultsPromotionRows": len(
                gap_yewon_2022_legacy_results_rows
            ),
            "admissionOfficeGapKyonggi2022OfficialScorePromotionRows": len(
                gap_kyonggi_2022_official_score_rows
            ),
            "admissionOfficeGapKyonggi2022OfficialSupportPromotionRows": len(
                gap_kyonggi_2022_official_support_rows
            ),
            "admissionOfficeGapKyonggi2024OfficialResultsPromotionRows": len(
                gap_kyonggi_2024_official_results_rows
            ),
            "admissionOfficeGapKyonggi2025OfficialResultsPromotionRows": len(
                gap_kyonggi_2025_official_results_rows
            ),
            "admissionOfficeJoongbuOfficialHtmlResultsPromotionRows": len(
                joongbu_official_html_results_rows
            ),
            "admissionOfficeGapLtu2021OfficialResultImagePromotionRows": len(
                gap_ltu_2021_official_result_image_rows
            ),
            "admissionOfficeGapWorklistFileHighValuePromotionRows": len(
                gap_worklist_file_high_value_rows
            ),
            "admissionOfficeGapWorklistLinkedUnpromotedPromotionRows": len(
                gap_worklist_linked_unpromoted_rows
            ),
            "admissionOfficeJsDownloadFilePromotionRows": len(js_download_file_rows),
            "admissionOfficeZipEntryPromotionRows": len(zip_entry_rows),
            "admissionOfficeBlockedHelperPromotionRows": blocked_helper_rows,
            "admissionOfficeGnu2021ResultYearMismatchRows": (
                gnu_2021_result_year_mismatch_rows
            ),
            "admissionOfficePromotionDuplicateRows": duplicate_rows,
            "admissionOfficePromotionRows": len(rows_by_sha),
        },
    )


PROMOTION_SOURCE_LIST_FIELDS = (
    "attachmentRoles",
    "attachmentUrls",
    "collectionYears",
    "detectedAdmissionYears",
    "detectedDocumentRoles",
    "evidenceSha256Values",
    "evidenceTypes",
    "rawPaths",
    "sourceCandidateUrls",
    "sourceDocumentKinds",
    "sourceLinkRoles",
    "sourcePaths",
    "sourceSha256Values",
)


PROMOTION_SOURCE_GUARD_FIELDS = (
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


def promotion_row_has_blocked_helper_source(row: dict[str, Any]) -> bool:
    return any(
        BLOCKED_HELPER_SOURCE_PATTERN.search(join_values(row.get(field_name)))
        or BLOCKED_MALFORMED_SOURCE_PATTERN.search(join_values(row.get(field_name)))
        for field_name in PROMOTION_SOURCE_GUARD_FIELDS
    )


def promotion_row_has_gnu_2021_result_year_mismatch(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000007":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    source_locations = "|".join(
        join_values(row.get(field_name)) for field_name in PROMOTION_SOURCE_GUARD_FIELDS
    )
    is_2021_result_workbook = (
        "fileKey=1456" in source_locations
        or "8fe5a7de5a2578224950917b897760dc6af7a80cff5601577400fa6de6280313"
        in source_locations
    )
    if not is_2021_result_workbook:
        return False
    collection_years = {
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None
    }
    if collection_years and collection_years.isdisjoint({2022, 2023}):
        return False
    detected_years = {
        year
        for year in (int_or_none(value) for value in split_joined(row.get("detectedAdmissionYears")))
        if year is not None
    }
    return not detected_years or detected_years <= {2021}


def is_script_nav_reparse_nested_official_promotable(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_table":
        return False
    text = normalize_text(row.get("sampleText") or row.get("textPreview"))
    if "한국항공대학교 입시결과" not in text:
        return False
    source_locations = "|".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
        ]
    )
    if "ibhak.kau.ac.kr" not in source_locations:
        return False
    detected_years = {
        year
        for year in (int_or_none(value) for value in split_joined(row.get("detectedAdmissionYears")))
        if year is not None
    }
    return detected_years == {2025}


def promotion_row_has_collection_detected_year_overlap(row: dict[str, Any]) -> bool:
    collection_years = {
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None
    }
    detected_years = {
        year
        for year in (int_or_none(value) for value in split_joined(row.get("detectedAdmissionYears")))
        if year is not None
    }
    return len(collection_years) == 1 and bool(detected_years and collection_years & detected_years)


def initialize_promotion_source(row: dict[str, Any], source_label: str) -> dict[str, Any]:
    initialized = dict(row)
    for field_name in PROMOTION_SOURCE_LIST_FIELDS:
        initialized[field_name] = unique_values(row.get(field_name))
    initialized["sourceLabels"] = unique_values([source_label])
    initialized["sourceRowCount"] = 1
    initialized["duplicateSourceCount"] = 0
    initialized["rawPathCount"] = len(initialized.get("rawPaths") or [])
    initialized["sourceDocumentCount"] = max(
        int_or_none(row.get("sourceDocumentCount")) or 0,
        len(initialized.get("sourcePaths") or []),
        len(initialized.get("rawPaths") or []),
    )
    return initialized


def merge_promotion_source(
    existing: dict[str, Any], incoming: dict[str, Any], source_label: str
) -> None:
    for field_name in PROMOTION_SOURCE_LIST_FIELDS:
        existing[field_name] = merge_unique_values(existing.get(field_name), incoming.get(field_name))
    existing["sourceLabels"] = merge_unique_values(existing.get("sourceLabels"), [source_label])
    source_row_count = (int_or_none(existing.get("sourceRowCount")) or 1) + 1
    existing["sourceRowCount"] = source_row_count
    existing["duplicateSourceCount"] = max(0, source_row_count - 1)
    existing["reviewPriorityScore"] = max(
        int_or_none(existing.get("reviewPriorityScore")) or 0,
        int_or_none(incoming.get("reviewPriorityScore")) or 0,
    )
    existing["maxPriorityScore"] = max(
        int_or_none(existing.get("maxPriorityScore")) or 0,
        int_or_none(incoming.get("maxPriorityScore")) or 0,
    )
    existing["evidenceCount"] = max(
        int_or_none(existing.get("evidenceCount")) or 0,
        int_or_none(incoming.get("evidenceCount")) or 0,
    )
    existing["rawPathCount"] = len(existing.get("rawPaths") or [])
    existing["sourceDocumentCount"] = max(
        int_or_none(existing.get("sourceDocumentCount")) or 0,
        int_or_none(incoming.get("sourceDocumentCount")) or 0,
        len(existing.get("sourcePaths") or []),
        len(existing.get("rawPaths") or []),
    )
    existing["evidenceCountByCollectionYear"] = merge_count_maps(
        existing.get("evidenceCountByCollectionYear"),
        incoming.get("evidenceCountByCollectionYear"),
    )
    existing["sourceSpecificSamples"] = merge_sample_objects(
        existing.get("sourceSpecificSamples"), incoming.get("sourceSpecificSamples")
    )


def build_context(
    adiga_rows: list[dict[str, Any]],
    adiga_university_rows: list[dict[str, Any]],
    promotion_rows: list[dict[str, Any]],
    promotion_source_counts: dict[str, int],
    manual_admission_unit_rows: list[dict[str, Any]],
    manual_admission_office_evidence_rows: list[dict[str, Any]],
    academyinfo_rows: list[dict[str, Any]],
    adiga_rule_table_rows: list[dict[str, Any]],
    adiga_ocr_evidence_rows: list[dict[str, Any]],
    kice_grade_cut_rows: list[dict[str, Any]],
    kice_distribution_rows: list[dict[str, Any]],
    kice_press_snippet_rows: list[dict[str, Any]],
    kcue_snippet_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    universities: dict[str, dict[str, Any]] = {}
    units: dict[str, dict[str, Any]] = {}
    outcomes: list[dict[str, Any]] = []

    for row in adiga_rows:
        if str(row.get("status") or "") != "candidate":
            continue
        if is_noisy_adiga_outcome_row(row):
            continue
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        if not unv_cd or not university_name:
            continue
        ensure_university(universities, unv_cd, university_name, "adiga")
        unit = ensure_unit(units, universities[unv_cd], row)
        outcome = make_outcome_candidate(unit, row)
        outcomes.append(outcome)
        unit["outcomeRows"] += 1
        add_limited(unit["sourceCandidateSha256Values"], row.get("candidateSha256"), 20)
        if row.get("quota") is not None:
            unit["quotaCandidates"].add(number_string(row.get("quota")))
        universities[unv_cd]["adigaOutcomeRows"] += 1
        universities[unv_cd]["years"].add(int_or_none(row.get("year")))

    scoped_promotion_rows = [
        row for row in promotion_rows if not is_out_of_scope_admission_office_row(row)
    ]

    promotion_links = []
    for row in scoped_promotion_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        if unv_cd and university_name:
            ensure_university(universities, unv_cd, university_name, "university-admission-office")
            universities[unv_cd]["admissionOfficeEvidenceCandidates"] += 1
            for year in row.get("collectionYears") or []:
                universities[unv_cd]["years"].add(int_or_none(year))
        promotion_links.append(make_promotion_link(row))

    manual_evidence_links = build_manual_admission_office_evidence_links(
        manual_admission_office_evidence_rows
    )
    for link in manual_evidence_links:
        unv_cd = normalize_text(link.get("unvCd"))
        university_name = normalize_text(link.get("universityName"))
        if not unv_cd or not university_name:
            continue
        ensure_university(universities, unv_cd, university_name, "university-admission-office")
        universities[unv_cd]["admissionOfficeEvidenceCandidates"] += (
            int_or_none(link.get("evidenceCount")) or 1
        )
        for year in split_joined(link.get("collectionYears")):
            universities[unv_cd]["years"].add(int_or_none(year))
        for year in split_joined(link.get("detectedAdmissionYears")):
            universities[unv_cd]["years"].add(int_or_none(year))
    promotion_links.extend(manual_evidence_links)

    office_unit_rows = build_office_admission_unit_rows(scoped_promotion_rows)
    for row in office_unit_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        if not unv_cd or not university_name:
            continue
        ensure_university(universities, unv_cd, university_name, "university-admission-office")
        unit = ensure_unit(units, universities[unv_cd], row)
        add_limited(unit["sourceCandidateSha256Values"], row.get("candidateSha256"), 20)
        universities[unv_cd]["years"].add(int_or_none(row.get("year")))

    adiga_unit_rows = build_adiga_admission_unit_rows(adiga_rule_table_rows)
    for row in adiga_unit_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        if not unv_cd or not university_name:
            continue
        ensure_university(universities, unv_cd, university_name, "adiga")
        unit = ensure_unit(units, universities[unv_cd], row)
        add_limited(unit["sourceCandidateSha256Values"], row.get("candidateSha256"), 20)
        if row.get("quota") is not None:
            unit["quotaCandidates"].add(number_string(row.get("quota")))
        universities[unv_cd]["years"].add(int_or_none(row.get("year")))

    manual_unit_rows = build_manual_admission_unit_rows(manual_admission_unit_rows)
    for row in manual_unit_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        if not unv_cd or not university_name:
            continue
        ensure_university(universities, unv_cd, university_name, "university-admission-office")
        unit = ensure_unit(units, universities[unv_cd], row)
        add_limited(unit["sourceCandidateSha256Values"], row.get("candidateSha256"), 20)
        if row.get("quota") is not None:
            unit["quotaCandidates"].add(number_string(row.get("quota")))
        universities[unv_cd]["years"].add(int_or_none(row.get("year")))

    office_outcome_rows = build_office_historical_outcome_rows(scoped_promotion_rows)
    for row in office_outcome_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        if not unv_cd or not university_name:
            continue
        ensure_university(universities, unv_cd, university_name, "university-admission-office")
        unit = ensure_unit(units, universities[unv_cd], row)
        outcome = make_office_outcome_candidate(unit, row)
        outcomes.append(outcome)
        unit["outcomeRows"] += 1
        add_limited(unit["sourceCandidateSha256Values"], row.get("candidateSha256"), 20)
        if row.get("quota") is not None:
            unit["quotaCandidates"].add(number_string(row.get("quota")))
        universities[unv_cd]["years"].add(int_or_none(row.get("year")))

    adiga_ocr_outcome_rows = build_adiga_ocr_historical_outcome_rows(adiga_ocr_evidence_rows)
    for row in adiga_ocr_outcome_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        if not unv_cd or not university_name:
            continue
        ensure_university(universities, unv_cd, university_name, "adiga")
        unit = ensure_unit(units, universities[unv_cd], row)
        outcome = make_adiga_ocr_outcome_candidate(unit, row)
        outcomes.append(outcome)
        unit["outcomeRows"] += 1
        add_limited(unit["sourceCandidateSha256Values"], row.get("candidateSha256"), 20)
        if row.get("quota") is not None:
            unit["quotaCandidates"].add(number_string(row.get("quota")))
        universities[unv_cd]["years"].add(int_or_none(row.get("year")))

    for row in adiga_rule_table_rows:
        if not is_adiga_rule_table(row):
            continue
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        if unv_cd and university_name:
            ensure_university(universities, unv_cd, university_name, "adiga")
            universities[unv_cd]["years"].add(int_or_none(row.get("year")))

    for row in adiga_ocr_evidence_rows:
        if not is_adiga_ocr_rule_candidate(row):
            continue
        for ref in row.get("sampleReferences") or []:
            unv_cd = normalize_text(ref.get("unvCd"))
            university_name = normalize_text(ref.get("universityName"))
            if unv_cd and university_name:
                ensure_university(universities, unv_cd, university_name, "adiga")
                universities[unv_cd]["years"].add(int_or_none(ref.get("year")))

    admission_rule_candidates = build_admission_rule_candidates(
        [*scoped_promotion_rows, *manual_evidence_links],
        adiga_rule_table_rows,
        adiga_ocr_evidence_rows,
    )
    for row in admission_rule_candidates:
        unv_cd = normalize_text(row.get("unvCd"))
        if unv_cd and unv_cd in universities:
            universities[unv_cd]["admissionRuleReviewCandidates"] += 1

    for row in adiga_university_rows:
        unv_cd = normalize_text(row.get("unvCd"))
        year = int_or_none(row.get("year"))
        if unv_cd and year is not None and unv_cd in universities:
            universities[unv_cd]["sourceProviders"].add("adiga")
            universities[unv_cd]["years"].add(year)

    adiga_name_index = build_university_name_index(universities)
    academyinfo_summaries = build_academyinfo_summaries(academyinfo_rows, adiga_name_index)
    for summary in academyinfo_summaries:
        unv_cd = summary.get("matchedUnvCd")
        if unv_cd and unv_cd in universities:
            universities[unv_cd]["sourceProviders"].add("academyinfo")
            universities[unv_cd]["academyinfoSummaryRows"] += int(summary.get("sourceRows") or 0)

    kice_grade_cuts = [make_kice_grade_cut_candidate(row) for row in kice_grade_cut_rows]
    kice_distributions = [make_kice_distribution_candidate(row) for row in kice_distribution_rows]
    kice_press_evidence = [make_kice_press_evidence_link(row) for row in kice_press_snippet_rows]
    kcue_policy_evidence = [make_kcue_policy_evidence_link(row) for row in kcue_snippet_rows]

    finalized_universities = [finalize_university(row) for row in universities.values()]
    finalized_units = [finalize_unit(row) for row in units.values()]
    finalized_universities.sort(key=lambda row: (str(row.get("universityName") or ""), str(row.get("unvCd") or "")))
    finalized_units.sort(
        key=lambda row: (
            str(row.get("universityName") or ""),
            int(row.get("year") or 0),
            str(row.get("recruitmentGroup") or ""),
            str(row.get("admissionUnitCanonicalName") or ""),
        )
    )
    outcomes.sort(
        key=lambda row: (
            str(row.get("universityName") or ""),
            int(row.get("year") or 0),
            str(row.get("admissionUnitName") or ""),
            str(row.get("outcomeCandidateId") or ""),
        )
    )
    promotion_links.sort(
        key=lambda row: (
            str(row.get("evidenceTarget") or ""),
            str(row.get("universityName") or ""),
            -int(row.get("reviewPriorityScore") or 0),
            str(row.get("evidenceCandidateSha256") or ""),
        )
    )
    academyinfo_summaries.sort(
        key=lambda row: (
            str(row.get("universityName") or ""),
            int(row.get("surveyYear") or 0),
            str(row.get("relevanceRole") or ""),
        )
    )
    admission_rule_candidates.sort(
        key=lambda row: (
            str(row.get("sourceProvider") or ""),
            str(row.get("universityName") or ""),
            int(first_int_from_joined(row.get("admissionYears")) or 0),
            str(row.get("ruleCategory") or ""),
            -int(row.get("reviewPriorityScore") or 0),
            str(row.get("ruleCandidateId") or ""),
        )
    )
    kice_grade_cuts.sort(
        key=lambda row: (
            int(row.get("academicYear") or 0),
            str(row.get("examType") or ""),
            str(row.get("subjectNameNormalized") or ""),
            int(row.get("grade") or 0),
            str(row.get("gradeCutCandidateId") or ""),
        )
    )
    kice_distributions.sort(
        key=lambda row: (
            int(row.get("academicYear") or 0),
            str(row.get("examType") or ""),
            str(row.get("subjectNameNormalized") or ""),
            -int(row.get("standardScore") or 0),
            str(row.get("distributionCandidateId") or ""),
        )
    )
    kice_press_evidence.sort(
        key=lambda row: (
            int(row.get("academicYear") or 0),
            str(row.get("examType") or ""),
            str(row.get("targetEntity") or ""),
            -int(row.get("reviewPriorityScore") or 0),
            str(row.get("evidenceCandidateSha256") or ""),
        )
    )
    kcue_policy_evidence.sort(
        key=lambda row: (
            int(row.get("academicYear") or 0),
            str(row.get("targetEntity") or ""),
            str(row.get("snippetRole") or ""),
            -int(row.get("reviewPriorityScore") or 0),
            str(row.get("evidenceCandidateSha256") or ""),
        )
    )

    return {
        "universities": finalized_universities,
        "admissionUnits": finalized_units,
        "historicalOutcomes": outcomes,
        "admissionOfficeEvidenceLinks": promotion_links,
        "admissionRuleReviewCandidates": admission_rule_candidates,
        "academyinfoSummaries": academyinfo_summaries,
        "kiceGradeCuts": kice_grade_cuts,
        "kiceStandardScoreDistributions": kice_distributions,
        "kicePressEvidenceLinks": kice_press_evidence,
        "kcuePolicyEvidenceLinks": kcue_policy_evidence,
        "summary": summarize(
            finalized_universities,
            finalized_units,
            outcomes,
            promotion_links,
            admission_rule_candidates,
            academyinfo_summaries,
            kice_grade_cuts,
            kice_distributions,
            kice_press_evidence,
            kcue_policy_evidence,
            adiga_rows,
            promotion_rows,
            promotion_source_counts,
            academyinfo_rows,
            adiga_rule_table_rows,
            adiga_ocr_evidence_rows,
            kice_grade_cut_rows,
            kice_distribution_rows,
            kice_press_snippet_rows,
            kcue_snippet_rows,
        ),
    }


def ensure_university(
    universities: dict[str, dict[str, Any]],
    unv_cd: str,
    university_name: str,
    provider: str,
) -> None:
    if unv_cd not in universities:
        universities[unv_cd] = {
            "universityCandidateId": deterministic_uuid(f"university:{unv_cd}"),
            "unvCd": unv_cd,
            "universityName": university_name,
            "universityNameCanonical": canonical_name(university_name),
            "campus": "",
            "region": "",
            "type": "",
            "sourceProviders": set(),
            "years": set(),
            "adigaOutcomeRows": 0,
            "admissionOfficeEvidenceCandidates": 0,
            "admissionRuleReviewCandidates": 0,
            "academyinfoSummaryRows": 0,
            "reviewStatus": "needs_human_verification",
        }
    universities[unv_cd]["sourceProviders"].add(provider)


def ensure_unit(
    units: dict[str, dict[str, Any]],
    university: dict[str, Any],
    row: dict[str, Any],
) -> dict[str, Any]:
    year = int_or_none(row.get("year")) or 0
    recruitment_group = recruitment_group_value(row.get("recruitmentGroup"))
    unit_name = normalize_text(row.get("admissionUnitName"))
    canonical_unit = normalize_text(row.get("admissionUnitCanonicalCandidate")) or canonical_name(unit_name)
    key = f"{university['unvCd']}:{year}:{recruitment_group}:{canonical_unit}"
    provider = normalize_text(row.get("sourceProvider")) or "adiga"
    if key not in units:
        units[key] = {
            "unitCandidateId": deterministic_uuid(f"admission-unit:{key}"),
            "universityCandidateId": university["universityCandidateId"],
            "unvCd": university["unvCd"],
            "universityName": university["universityName"],
            "year": year,
            "admissionUnitName": unit_name,
            "admissionUnitCanonicalName": canonical_unit,
            "recruitmentGroup": recruitment_group,
            "majorGroup": infer_major_group(unit_name),
            "quotaCandidates": set(),
            "outcomeRows": 0,
            "sourceProviders": {provider},
            "sourceCandidateSha256Values": [],
            "reviewStatus": "needs_human_verification",
        }
    else:
        units[key]["sourceProviders"].add(provider)
    return units[key]


def build_office_admission_unit_rows(promotion_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in promotion_rows:
        if not is_office_admission_unit_source(row):
            continue
        years = office_admission_unit_years(row)
        if not years:
            continue
        text = office_admission_unit_source_text(row)
        if is_ytus_gap_manual_row(row):
            unit_names = extract_ytus_admission_unit_names(text)
        else:
            unit_names = extract_office_admission_unit_names(text)
        if not unit_names:
            continue
        for year in years:
            for unit_name in unit_names:
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": year,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_name(unit_name),
                        "recruitmentGroup": infer_recruitment_group_near_unit(text, unit_name),
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                    }
                )
    return rows


def is_office_admission_unit_source(row: dict[str, Any]) -> bool:
    role = normalize_text(row.get("evidenceRole"))
    target = normalize_text(row.get("evidenceTarget"))
    if role not in OFFICE_ADMISSION_UNIT_ROLES:
        return False
    if target not in {"HistoricalOutcome", "AdmissionRule"}:
        return False
    text = office_admission_unit_filter_text(row)
    has_unit_context = bool(OFFICE_UNIT_TABLE_CONTEXT.search(text))
    if not has_unit_context and is_ytus_gap_manual_row(row):
        has_unit_context = bool(OFFICE_YTUS_UNIT_TABLE_CONTEXT.search(text))
    return bool(has_unit_context and OFFICE_UNIT_RESULT_CONTEXT.search(text))


def office_admission_unit_filter_text(row: dict[str, Any]) -> str:
    if is_ytus_gap_manual_hwp_text_row(row):
        return ""
    if is_ytus_gap_manual_row(row):
        return office_text_candidate_full_text(row)
    return normalize_text(row.get("sampleText") or row.get("textPreview"))


def office_admission_unit_source_text(row: dict[str, Any]) -> str:
    if "workbook_row" in join_values(row.get("evidenceTypes")):
        return office_workbook_row_text(row)
    if is_ytus_gap_manual_hwp_text_row(row):
        return ""
    if is_ytus_gap_manual_row(row):
        raw_text = office_text_candidate_raw_text(row)
        return ytus_admission_unit_sections_text(raw_text) or normalize_text(raw_text)
    return office_workbook_row_text(row)


def is_ytus_gap_manual_row(row: dict[str, Any]) -> bool:
    source_paths = join_values(row.get("sourcePaths"))
    return normalize_text(row.get("unvCd")) == "0000153" and (
        "extracted-gap-manual-ytus" in source_paths
        or "extracted-ytus-archive-regular" in source_paths
    )


def is_ytus_gap_manual_hwp_text_row(row: dict[str, Any]) -> bool:
    return is_ytus_gap_manual_row(row) and "hwp-text" in join_values(row.get("sourcePaths"))


def office_text_candidate_raw_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is not None:
        source_text = raw_office_text_source(source_path)
        if source_text:
            return source_text
    return office_workbook_row_text(row)


def ytus_admission_unit_sections_text(text: str) -> str:
    lines = text.splitlines()
    sections: list[str] = []
    seen: set[str] = set()
    for index, line in enumerate(lines):
        if not is_ytus_admission_unit_section_header(line):
            continue
        section_lines = []
        for current in lines[index : index + 36]:
            if section_lines and re.match(r"^\s*(?:[0-9]{1,2})\.\s+", current):
                if not is_ytus_admission_unit_section_header(current):
                    break
            if section_lines and re.match(r"^\s*[가-힣]\.\s+", current):
                break
            section_lines.append(current)
            if section_lines and re.search(r"합\s*계", normalize_text(current)):
                break
        section = normalize_text("\n".join(section_lines))
        if section and section not in seen:
            seen.add(section)
            sections.append(section)
    if sections:
        return "\n".join(sections)
    return ytus_admission_unit_inline_sections_text(text)


def ytus_admission_unit_inline_sections_text(text: str) -> str:
    normalized = normalize_text(text)
    if not normalized:
        return ""
    header_pattern = re.compile(
        r"모집\s*학과\s*및\s*인원|모집\s*단위\s*·\s*전공|모집단위별\s*(?:\([^)]*\))?\s*모집인원"
    )
    sections: list[str] = []
    seen: set[str] = set()
    for match in header_pattern.finditer(normalized):
        tail = normalized[match.start() : match.start() + 2600]
        end_match = re.search(r"합\s*계(?:\s+[-\d]+){1,16}", tail)
        section = tail[: end_match.end()] if end_match else tail[:1400]
        section = normalize_text(section)
        if section and section not in seen:
            seen.add(section)
            sections.append(section)
    return "\n".join(sections)


def is_ytus_admission_unit_section_header(line: str) -> bool:
    normalized = normalize_text(line)
    return bool(
        re.search(r"모집\s*학과\s*(?:및\s*인원|인원)?$", normalized)
        or re.search(r"모집\s*단위\s*[·(]", normalized)
        or re.search(r"모집단위\s*[(]", normalized)
        or re.search(r"모집단위별\s*[(]", normalized)
    )


def is_out_of_scope_admission_office_row(row: dict[str, Any]) -> bool:
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("sourceUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if OFFICE_NON_ADMISSION_SOURCE_PATTERN.search(source_context):
        return True
    if is_course_timetable_workbook_evidence(row):
        return True
    if is_recruitment_guide_misclassified_outcome(row):
        return True
    context = " ".join(
        [
            normalize_text(row.get("sourceLabels")),
            normalize_text(row.get("sourceCandidateUrls")),
            normalize_text(row.get("attachmentUrls")),
            normalize_text(row.get("sampleText") or row.get("textPreview"))[:260],
        ]
    )
    if is_out_of_scope_admission_office_context(context):
        return True
    return is_out_of_scope_admission_office_context(office_text_source_intro(row))


def is_course_timetable_workbook_evidence(row: dict[str, Any]) -> bool:
    source_locations = " ".join(
        [
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
            join_values(row.get("attachmentUrls")),
        ]
    )
    evidence_types = join_values(row.get("evidenceTypes"))
    if "workbook_row" not in evidence_types and not re.search(
        r"workbook-sheets|\.xlsx\b|\.xls\b|\.csv\b",
        source_locations,
        re.I,
    ):
        return False
    text = normalize_text(row.get("sampleText") or row.get("textPreview"))
    if not text:
        return False
    return bool(
        OFFICE_COURSE_TIMETABLE_TIME_PATTERN.search(text)
        and OFFICE_COURSE_TIMETABLE_CONTEXT_PATTERN.search(text)
        and not OFFICE_ADMISSION_RESULT_CONTEXT_PATTERN.search(text)
    )


def is_recruitment_guide_misclassified_outcome(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    text = normalize_text(
        row.get("sampleText") or row.get("textPreview") or row.get("representativeText")
    )
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("sourceUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    role_context = " ".join(
        [
            join_values(row.get("sourceLinkRoles")),
            join_values(row.get("detectedDocumentRoles")),
            join_values(row.get("sourceDocumentKinds")),
            normalize_text(row.get("sourceLabels")),
        ]
    )
    combined_context = " ".join([text, source_context, role_context])
    is_recruitment_notice_source = bool(
        OFFICE_RECRUITMENT_GUIDE_SOURCE_PATTERN.search(role_context)
    )
    is_guide_like = bool(
        OFFICE_RECRUITMENT_GUIDE_CONTEXT_PATTERN.search(text)
        or OFFICE_RECRUITMENT_GUIDE_SOURCE_PATTERN.search(role_context)
    )
    if not is_guide_like:
        return False
    if is_recruitment_notice_source:
        return not OFFICE_RECRUITMENT_NOTICE_OUTCOME_KEEP_PATTERN.search(combined_context)
    return not OFFICE_HISTORICAL_OUTCOME_POSITIVE_CONTEXT_PATTERN.search(combined_context)


def office_text_source_intro(row: dict[str, Any]) -> str:
    repo_root = cached_repo_root()
    for raw_path in split_joined(row.get("sourcePaths"))[:3]:
        source_path = Path(raw_path)
        if not source_path.is_absolute() and repo_root is not None:
            source_path = repo_root / source_path
        text = cached_office_text_source_intro(source_path)
        if text:
            return text[:700]
    return ""


def cached_office_text_source_intro(path: Path) -> str:
    cache_key = str(path)
    if cache_key not in OFFICE_TEXT_SOURCE_INTRO_CACHE:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                OFFICE_TEXT_SOURCE_INTRO_CACHE[cache_key] = normalize_text(handle.read(12000))
        except OSError:
            OFFICE_TEXT_SOURCE_INTRO_CACHE[cache_key] = ""
    return OFFICE_TEXT_SOURCE_INTRO_CACHE[cache_key]


def is_out_of_scope_admission_office_context(context: str) -> bool:
    if re.search(r"(?:일반|학사)?\s*편입학(?:전형|모집|기본계획|모집요강|추가모집|결과)?", context):
        return True
    if re.search(r"편입\s*(?:시행|미시행|전형|모집|모집요강|학과)", context):
        return True
    if re.search(r"전적\s*대학(?:의)?(?:\s*성적)?", context):
        return True
    if re.search(r"(?:일반|학사)\s*편입|편입\s*원서", context):
        return True
    if re.search(r"대학원\s*(?:신입생|모집|입학|전형|모집요강)", context):
        return True
    if re.search(r"시간제\s*등록(?:생)?\s*(?:모집|입학|전형|모집요강)", context):
        return True
    if re.search(r"재외\s*국민\s*(?:전형|모집|모집요강|입시결과)", context):
        return True
    if re.search(r"선행\s*학습\s*영향\s*평가|자체\s*평가\s*보고서", context):
        return True
    if re.search(r"검정\s*고시.*(?:성적|학생부).*(?:산출|프로그램)", context):
        return True
    if re.search(r"(?:간호학과|학과)\s*[_ -]*.*규정집|규정집", context):
        return True
    return False


def office_admission_unit_years(row: dict[str, Any]) -> list[int]:
    ysu_2021_year = ysu_2021_official_results_collection_year(row)
    if ysu_2021_year:
        return [ysu_2021_year]
    ysu_2022_year = ysu_2022_official_results_collection_year(row)
    if ysu_2022_year:
        return [ysu_2022_year]
    yewon_2021_year = yewon_2021_legacy_results_collection_year(row)
    if yewon_2021_year:
        return [yewon_2021_year]
    yewon_2022_year = yewon_2022_legacy_results_collection_year(row)
    if yewon_2022_year:
        return [yewon_2022_year]
    seowon_2022_regular_year = seowon_2022_regular_result_source_year(row)
    if seowon_2022_regular_year:
        return [seowon_2022_regular_year]
    kyonggi_2026_susi_guide_year = kyonggi_2026_susi_guide_result_collection_year(row)
    if kyonggi_2026_susi_guide_year:
        return [kyonggi_2026_susi_guide_year]
    kyonggi_2024_year = kyonggi_2024_official_results_collection_year(row)
    if kyonggi_2024_year:
        return [kyonggi_2024_year]
    kyonggi_2022_year = kyonggi_2022_official_score_collection_year(row)
    if kyonggi_2022_year:
        return [kyonggi_2022_year]
    kyonggi_2025_year = kyonggi_2025_official_results_collection_year(row)
    if kyonggi_2025_year:
        return [kyonggi_2025_year]
    if is_ytus_gap_manual_row(row):
        source_year = first_ytus_source_admission_year(row)
        if source_year is not None:
            if RECENT_YEAR_MIN <= source_year <= RECENT_YEAR_MAX:
                return [source_year]
            return []
    text = normalize_text(row.get("sampleText") or row.get("textPreview"))
    contextual = recent_contextual_years(text)
    if contextual:
        return contextual[:1]
    for field in ("sourceCandidateUrls", "attachmentUrls", "sourceLabels"):
        contextual = recent_contextual_years(join_values(row.get(field)))
        if contextual:
            return contextual[:1]
    detected_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("detectedAdmissionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    if len(set(detected_years)) == 1:
        return list(dict.fromkeys(detected_years))
    return []


def first_ytus_source_admission_year(row: dict[str, Any]) -> int | None:
    text = office_text_candidate_raw_text(row)[:2000]
    for match in ADMISSION_YEAR_CONTEXT_PATTERN.finditer(text):
        year = int_or_none(match.group(1))
        if year is not None and 2020 <= year <= 2035:
            return year
    return None


def recent_contextual_years(text: str) -> list[int]:
    years = []
    for match in ADMISSION_YEAR_CONTEXT_PATTERN.finditer(text):
        year = int_or_none(match.group(1))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX and year not in years:
            years.append(year)
    return years


def extract_office_admission_unit_names(text: str) -> list[str]:
    values = []
    for match in OFFICE_UNIT_NAME_PATTERN.finditer(text):
        value = clean_office_admission_unit_name(match.group(0))
        if is_useful_office_admission_unit_name(value):
            values.append(value)
    return unique_preserve_order(values)[:120]


def extract_ytus_admission_unit_names(text: str) -> list[str]:
    return unique_preserve_order(OFFICE_YTUS_UNIT_NAME_PATTERN.findall(text))


def clean_office_admission_unit_name(value: str) -> str:
    value = normalize_text(value)
    value = value.replace("*", "")
    value = value.strip(" /,.:;·ㆍ-[]()")
    parts = [part.strip(" /,.:;·ㆍ-[]()") for part in value.split() if part.strip()]
    suffix_parts = [part for part in parts if OFFICE_UNIT_SUFFIX_PATTERN.search(part)]
    if suffix_parts:
        value = suffix_parts[-1]
    value = re.sub(r"^\d+(?:명|명이내)?", "", value)
    value = re.sub(r"^[가나다]군", "", value)
    value = value.strip(" /,.:;·ㆍ-[]()")
    return value[:60]


def is_useful_office_admission_unit_name(value: str) -> bool:
    if len(value) < 3 or len(value) > 40:
        return False
    if value in {
        "계약학과",
        "모집학과",
        "지원학과",
        "기준학과",
        "동일학과",
        "동일계열",
        *OFFICE_UNIT_GENERIC_NOISE_VALUES,
    }:
        return False
    if re.search(r"[()\[\]/]", value):
        return False
    if not OFFICE_UNIT_SUFFIX_PATTERN.search(value):
        return False
    if value.endswith("계열"):
        return False
    if OFFICE_UNIT_NOISE_PATTERN.search(value):
        return False
    if re.fullmatch(r"(?:인문|사회|자연|예체능|공학|의학|보건|사범|글로벌)?계열", value):
        return False
    return True


def build_adiga_admission_unit_rows(adiga_rule_table_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    for row in adiga_rule_table_rows:
        if not is_adiga_rule_table(row):
            continue
        text = normalize_text(row.get("textSnippet") or row.get("headerText"))
        if not OFFICE_UNIT_TABLE_CONTEXT.search(text):
            continue
        year = int_or_none(row.get("year"))
        if year is None or year < RECENT_YEAR_MIN or year > RECENT_YEAR_MAX:
            continue
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        table_sha = normalize_text(row.get("tableSha256"))
        for unit_name in extract_adiga_admission_unit_names(row):
            recruitment_group = infer_recruitment_group_near_unit(text, unit_name)
            key = (unv_cd, year, recruitment_group, canonical_name(unit_name))
            if key in seen:
                continue
            seen.add(key)
            payload = {
                "source": "adiga-rule-table-unit",
                "tableSha256": table_sha,
                "unvCd": unv_cd,
                "year": year,
                "unitName": unit_name,
                "recruitmentGroup": recruitment_group,
            }
            rows.append(
                {
                    "unvCd": unv_cd,
                    "universityName": university_name,
                    "year": year,
                    "admissionUnitName": unit_name,
                    "admissionUnitCanonicalCandidate": canonical_name(unit_name),
                    "recruitmentGroup": recruitment_group,
                    "candidateSha256": hashlib.sha256(
                        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest(),
                    "sourceProvider": "adiga",
                }
            )
    return rows


def extract_adiga_admission_unit_names(row: dict[str, Any]) -> list[str]:
    values: list[str] = []
    grid = row.get("grid") if isinstance(row.get("grid"), list) else []
    for grid_row in grid:
        if not isinstance(grid_row, list):
            continue
        for cell in grid_row:
            for match in OFFICE_UNIT_NAME_PATTERN.finditer(normalize_text(cell)):
                value = clean_office_admission_unit_name(match.group(0))
                if is_useful_office_admission_unit_name(value):
                    values.append(value)
    text = normalize_text(row.get("textSnippet") or row.get("headerText"))
    for match in OFFICE_UNIT_NAME_PATTERN.finditer(text):
        value = clean_office_admission_unit_name(match.group(0))
        if is_useful_office_admission_unit_name(value):
            values.append(value)
    return unique_preserve_order(values)[:120]


def infer_recruitment_group_near_unit(text: str, unit_name: str) -> str:
    index = text.find(unit_name)
    window = text[max(0, index - 80) : index + len(unit_name) + 20] if index >= 0 else text[:160]
    if re.search(r"가\s*군", window):
        return "ga"
    if re.search(r"나\s*군", window):
        return "na"
    if re.search(r"다\s*군", window):
        return "da"
    return "none"


def is_office_line_competition_historical_outcome_source(row: dict[str, Any]) -> bool:
    role = normalize_text(row.get("evidenceRole"))
    target = normalize_text(row.get("evidenceTarget"))
    if target != "HistoricalOutcome" or role != "competition_rate_table":
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    if "competition_rate" not in join_values(row.get("sourceLinkRoles")):
        return False
    return first_existing_office_text_source_path(row) is not None


def parse_office_line_competition_outcome_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    lines = office_competition_source_lines(row)
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, int, int, str]] = set()
    section = ""
    for line_index, line in enumerate(lines):
        normalized_line = normalize_text(line)
        if not normalized_line:
            continue
        header_match = OFFICE_COMPETITION_LINE_SECTION_HEADER_PATTERN.search(normalized_line)
        if header_match:
            section = normalize_text(header_match.group("section"))
            continue
        if section and section != "일반전형":
            continue
        match = OFFICE_COMPETITION_LINE_PATTERN.match(line)
        if not match:
            continue
        unit_name = clean_office_competition_line_unit_name(match.group("label"))
        if not is_useful_office_competition_line_unit_name(unit_name):
            continue
        quota = int_or_none(match.group("quota"))
        applicants = int_or_none(match.group("applicants"))
        competition = number_or_none(match.group("competition"))
        if quota is None or applicants is None or competition is None:
            continue
        if not is_consistent_office_html_competition(quota, applicants, float(competition)):
            continue
        recruitment_group = recruitment_group_from_korean(match.group("group"))
        if recruitment_group == "none":
            recruitment_group = infer_office_line_recruitment_group(lines, line_index)
        key = (canonical_name(unit_name), quota, applicants, number_string(competition))
        if (*key, recruitment_group) in seen:
            continue
        seen.add((*key, recruitment_group))
        entries.append(
            {
                "unitName": unit_name,
                "recruitmentGroup": recruitment_group,
                "rowIndex": line_index + 1,
                "parsed": {
                    "quota": quota,
                    "applicants": applicants,
                    "competitionRate": round(float(competition), 2),
                    "additionalPass": None,
                    "avgScoreCandidate": "",
                    "cutScoreCandidate": "",
                    "percentileCutCandidate": "",
                    "scoreAvailability": "office_quota_competition_candidate",
                    "metricCount": 0,
                    "hasQuotaAndCompetition": True,
                    "hasOutcomeScore": False,
                },
            }
        )
    return entries


def office_competition_source_lines(row: dict[str, Any]) -> list[str]:
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return []
    source_text = raw_office_text_source(source_path)
    if not source_text:
        return []
    sample = office_text_source_sample(row)
    page_number = int_or_none(sample.get("pageNumber"))
    if page_number is None:
        return source_text.splitlines()
    pages = source_text.split("\f")
    if page_number < 1 or page_number > len(pages):
        return source_text.splitlines()
    return pages[page_number - 1].splitlines()


def clean_office_competition_line_unit_name(value: str) -> str:
    value = normalize_text(value)
    value = OFFICE_RECRUITMENT_GROUP_PATTERN.sub(" ", value)
    value = re.sub(r"\[[^\]]+\]", " ", value)
    value = value.replace("*", " ")
    value = value.strip(" /,.:;·ㆍ-[]")
    tokens = [
        token.strip(" /,.:;·ㆍ-[]")
        for token in re.split(r"\s+", value)
        if token.strip(" /,.:;·ㆍ-[]")
    ]
    cleaned_tokens = [
        token
        for token in tokens
        if not OFFICE_COMPETITION_LINE_SELECTION_TOKEN_PATTERN.fullmatch(token)
    ]
    if not cleaned_tokens:
        return ""
    hinted_tokens = [
        token
        for token in cleaned_tokens
        if OFFICE_UNIT_SUFFIX_PATTERN.search(token)
        or OFFICE_COMPETITION_LINE_UNIT_HINT_PATTERN.search(token)
    ]
    unit_name = hinted_tokens[-1] if hinted_tokens else cleaned_tokens[-1]
    return unit_name.strip(" /,.:;·ㆍ-[]")[:60]


def is_useful_office_competition_line_unit_name(value: str) -> bool:
    value = normalize_text(value).strip(" /,.:;·ㆍ-[]")
    if len(value) < 2 or len(value) > 40:
        return False
    if OFFICE_COMPETITION_LINE_LABEL_NOISE_PATTERN.search(value):
        return False
    if OFFICE_COMPETITION_LINE_SELECTION_TOKEN_PATTERN.fullmatch(value):
        return False
    if re.fullmatch(r"[가나다]\s*군", value):
        return False
    if OFFICE_UNIT_SUFFIX_PATTERN.search(value):
        return is_useful_office_admission_unit_name(value)
    if OFFICE_UNIT_NOISE_PATTERN.search(value):
        return False
    return bool(OFFICE_COMPETITION_LINE_UNIT_HINT_PATTERN.search(value))


def infer_office_line_recruitment_group(lines: list[str], line_index: int) -> str:
    for radius in range(0, 6):
        for index in (line_index - radius, line_index + radius):
            if index < 0 or index >= len(lines):
                continue
            group = recruitment_group_from_korean_text(lines[index])
            if group != "none":
                return group
    return "none"


def recruitment_group_from_korean_text(value: str) -> str:
    match = OFFICE_RECRUITMENT_GROUP_PATTERN.search(normalize_text(value))
    if not match:
        return "none"
    return recruitment_group_from_korean(match.group(1))


def recruitment_group_from_korean(value: Any) -> str:
    normalized = normalize_text(value)
    if normalized == "가":
        return "ga"
    if normalized == "나":
        return "na"
    if normalized == "다":
        return "da"
    return "none"


def build_office_historical_outcome_rows(promotion_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in promotion_rows:
        iccu_result_source = is_iccu_result_source(row)
        anyang_2022_2024_result_source = is_anyang_2022_2024_result_source(row)
        anyang_2025_regular_result_source = is_anyang_2025_regular_result_source(row)
        cau_2025_regular_result_source = is_cau_2025_regular_result_source(row)
        kookmin_2026_susi_result_source = is_kookmin_2026_susi_result_source(row)
        halla_2026_susi_result_source = is_halla_2026_susi_result_source(row)
        jnue_result_source = is_jnue_result_source(row)
        cnue_result_source = is_cnue_result_source(row)
        chosun_2021_workbook_result_source = is_chosun_2021_workbook_result_source(row)
        ltu_2021_result_image_source = is_ltu_2021_official_result_image_source(row)
        wsu_2026_susi_result_source = is_wsu_2026_susi_result_appendix_source(row)
        hansei_2026_regular_result_source = is_hansei_2026_regular_result_source(row)
        ysu_2021_susi_result_source = is_ysu_2021_susi_result_workbook_source(row)
        ysu_2022_susi_result_source = is_ysu_2022_susi_result_workbook_source(row)
        yewon_2022_susi_result_source = is_yewon_2022_susi_result_pdf_source(row)
        seowon_2021_susi_result_source = is_seowon_2021_susi_result_source(row)
        seowon_2022_regular_result_source = is_seowon_2022_regular_result_source(row)
        kyonggi_2026_susi_guide_result_source = (
            is_kyonggi_2026_susi_guide_result_source(row)
        )
        kyonggi_2022_score_source = is_kyonggi_2022_official_score_source(row)
        kyonggi_2025_result_source = is_kyonggi_2025_official_result_source(row)
        joongbu_html_result_source = is_joongbu_official_html_result_source(row)
        skuniv_2026_result_source = is_skuniv_2026_official_result_source(row)
        scnu_admission_result_source = (
            scnu_admission_result_workbook_collection_year(row) is not None
        )
        scnu_competition_result_source = (
            scnu_competition_results_collection_year(row) is not None
        )
        catholic_songsin_2023_regular_remap_source = (
            is_catholic_songsin_2023_regular_result_remap_source(row)
        )
        gwnu_athletics_score_source = is_gwnu_2021_2022_athletics_score_workbook_source(row)
        gwnu_2023_region_subject_image_source = (
            is_gwnu_2023_region_subject_image_ocr_source(row)
        )
        html_table_source = is_office_html_table_historical_outcome_source(row)
        line_competition_source = is_office_line_competition_historical_outcome_source(row)
        if (
            not is_office_historical_outcome_source(row)
            and not iccu_result_source
            and not anyang_2022_2024_result_source
            and not anyang_2025_regular_result_source
            and not cau_2025_regular_result_source
            and not kookmin_2026_susi_result_source
            and not halla_2026_susi_result_source
            and not jnue_result_source
            and not cnue_result_source
            and not chosun_2021_workbook_result_source
            and not ltu_2021_result_image_source
            and not wsu_2026_susi_result_source
            and not hansei_2026_regular_result_source
            and not ysu_2021_susi_result_source
            and not ysu_2022_susi_result_source
            and not yewon_2022_susi_result_source
            and not seowon_2021_susi_result_source
            and not seowon_2022_regular_result_source
            and not kyonggi_2026_susi_guide_result_source
            and not kyonggi_2022_score_source
            and not kyonggi_2025_result_source
            and not joongbu_html_result_source
            and not skuniv_2026_result_source
            and not scnu_admission_result_source
            and not scnu_competition_result_source
            and not catholic_songsin_2023_regular_remap_source
            and not gwnu_athletics_score_source
            and not gwnu_2023_region_subject_image_source
            and not html_table_source
            and not line_competition_source
        ):
            continue
        score_workbook_row_source = is_score_bearing_office_workbook_outcome_row(row)
        competition_workbook_row_source = is_competition_only_office_workbook_outcome_row(row)
        structured_workbook_row_source = is_structured_office_workbook_outcome_row(row)
        text = office_workbook_row_text(row)
        years = office_historical_outcome_years(row)
        if not years:
            continue
        catholic_songsin_2023_regular_entries = (
            parse_catholic_songsin_2023_regular_result_remap_entries(row)
            if catholic_songsin_2023_regular_remap_source
            else []
        )
        for entry in catholic_songsin_2023_regular_entries:
            unit_name = entry["unitName"]
            canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                unit_name
            )
            parsed = entry["parsed"]
            recruitment_group = entry["recruitmentGroup"]
            year = entry["year"]
            source_url = first_for_year(row.get("sourceCandidateUrls"), year)
            raw_path = first_for_year(row.get("rawPaths"), year)
            dedupe_key = (
                "0000049",
                year,
                canonical_unit,
                recruitment_group,
                parsed["quota"],
                parsed.get("applicants"),
                number_string(parsed["competitionRate"]),
                number_string(parsed.get("additionalPass")),
                normalize_text(entry.get("sectionId")),
                normalize_text(entry.get("rowIndex")),
            )
            if dedupe_key not in seen:
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": "0000049",
                        "universityName": "가톨릭대학교",
                        "year": year,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": recruitment_group,
                        "quota": parsed["quota"],
                        "applicants": parsed.get("applicants"),
                        "competitionRate": parsed["competitionRate"],
                        "additionalPass": parsed.get("additionalPass"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": 0,
                        "hasQuotaAndCompetition": parsed.get("hasQuotaAndCompetition", True),
                        "hasOutcomeScore": parsed["hasOutcomeScore"],
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": (
                            "source_preserving_office_catholic_0000049_2023_regular_ocr_remap_review"
                        ),
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": normalize_text(entry.get("tableIndex")),
                        "rowIndex": normalize_text(entry.get("rowIndex")),
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
        iccu_entries = parse_iccu_result_entries(row) if iccu_result_source else []
        if iccu_entries:
            for entry in iccu_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                entry_years = [entry["year"]] if entry.get("year") else years
                for year in entry_years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("avgScoreCandidate")),
                        source_url,
                        raw_path,
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_iccu_pdf_result_table_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        ltu_2021_entries = (
            parse_ltu_2021_official_result_image_entries(row)
            if ltu_2021_result_image_source
            else []
        )
        if ltu_2021_entries:
            for entry in ltu_2021_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                entry_years = [entry["year"]] if entry.get("year") else years
                for year in entry_years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_ltu_image_result_table_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        skuniv_2026_entries = (
            parse_skuniv_2026_official_result_pdf_entries(row)
            if skuniv_2026_result_source
            else []
        )
        if skuniv_2026_entries:
            for entry in skuniv_2026_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                source_url = first_for_year(row.get("sourceCandidateUrls"), 2026)
                raw_path = first_for_year(row.get("rawPaths"), 2026)
                dedupe_key = (
                    "0000121",
                    2026,
                    normalize_text(entry.get("sectionId")),
                    canonical_unit,
                    recruitment_group,
                    parsed["quota"],
                    parsed.get("applicants"),
                    number_string(parsed["competitionRate"]),
                    number_string(parsed.get("additionalPass")),
                    number_string(parsed.get("convertedScore50Cut")),
                    number_string(parsed.get("convertedScore70Cut")),
                    entry["rowIndex"],
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": "0000121",
                        "universityName": "서경대학교",
                        "year": 2026,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": recruitment_group,
                        "quota": parsed["quota"],
                        "applicants": parsed.get("applicants"),
                        "competitionRate": parsed["competitionRate"],
                        "additionalPass": parsed.get("additionalPass"),
                        "convertedScore50Cut": parsed.get("convertedScore50Cut"),
                        "convertedScore70Cut": parsed.get("convertedScore70Cut"),
                        "totalScore": parsed.get("totalScore"),
                        "percentile70Average": parsed.get("percentile70Average"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": parsed.get("subjectMetricCount", 0),
                        "hasQuotaAndCompetition": True,
                        "hasOutcomeScore": parsed["hasOutcomeScore"],
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": (
                            "source_preserving_office_skuniv_2026_pdf_result_table_review"
                        ),
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": normalize_text(entry.get("tableIndex")),
                        "rowIndex": entry["rowIndex"],
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
            continue
        wsu_2026_susi_entries = (
            parse_wsu_2026_susi_result_appendix_entries(row)
            if wsu_2026_susi_result_source
            else []
        )
        if wsu_2026_susi_entries:
            for entry in wsu_2026_susi_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        entry["rowIndex"],
                        entry["track"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": "none",
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": True,
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_wsu_2026_susi_result_appendix_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": f"2026_susi_final_registrant_result:{entry['track']}",
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        ysu_2021_susi_entries = (
            parse_ysu_2021_susi_result_workbook_entries(row)
            if ysu_2021_susi_result_source
            else []
        )
        ysu_2022_susi_entries = (
            parse_ysu_2022_susi_result_workbook_entries(row)
            if ysu_2022_susi_result_source
            else []
        )
        ysu_susi_entries = ysu_2021_susi_entries or ysu_2022_susi_entries
        if ysu_susi_entries:
            ysu_source_year = 2021 if ysu_2021_susi_entries else 2022
            for entry in ysu_susi_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        normalize_text(entry.get("track")),
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": "none",
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", False
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                f"source_preserving_office_ysu_{ysu_source_year}_susi_result_workbook_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": f"ysu_{ysu_source_year}_susi:{entry['track']}",
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        kyonggi_2026_susi_guide_entries = (
            parse_kyonggi_2026_susi_guide_result_entries(row)
            if kyonggi_2026_susi_guide_result_source
            else []
        )
        if kyonggi_2026_susi_guide_entries:
            for entry in kyonggi_2026_susi_guide_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                source_url = first_for_year(row.get("sourceCandidateUrls"), entry["year"])
                raw_path = first_for_year(row.get("rawPaths"), entry["year"])
                dedupe_key = (
                    normalize_text(row.get("unvCd")),
                    entry["year"],
                    canonical_unit,
                    normalize_text(entry.get("track")),
                    normalize_text(entry.get("recruitmentGroup")),
                    parsed["quota"],
                    parsed.get("applicants"),
                    number_string(parsed["competitionRate"]),
                    number_string(parsed.get("avgScoreCandidate")),
                    number_string(parsed.get("cutScoreCandidate")),
                    number_string(parsed.get("percentileCutCandidate")),
                    entry["rowIndex"],
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": entry["year"],
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": entry["recruitmentGroup"],
                        "quota": parsed["quota"],
                        "applicants": parsed.get("applicants"),
                        "competitionRate": parsed["competitionRate"],
                        "additionalPass": parsed.get("additionalPass"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": 0,
                        "hasQuotaAndCompetition": parsed.get("hasQuotaAndCompetition", True),
                        "hasOutcomeScore": parsed["hasOutcomeScore"],
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": (
                            "source_preserving_office_kyonggi_2026_susi_guide_result_pdf_review"
                        ),
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": "",
                        "rowIndex": entry["rowIndex"],
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
            continue
        kyonggi_2022_score_entries = (
            parse_kyonggi_2022_official_score_entries(row)
            if kyonggi_2022_score_source
            else []
        )
        if kyonggi_2022_score_entries:
            for entry in kyonggi_2022_score_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                source_url = first_for_year(row.get("sourceCandidateUrls"), entry["year"])
                raw_path = first_for_year(row.get("rawPaths"), entry["year"])
                dedupe_key = (
                    normalize_text(row.get("unvCd")),
                    entry["year"],
                    canonical_unit,
                    normalize_text(entry.get("track")),
                    normalize_text(entry.get("recruitmentGroup")),
                    number_string(parsed.get("avgScoreCandidate")),
                    number_string(parsed.get("cutScoreCandidate")),
                    number_string(parsed.get("percentileCutCandidate")),
                    entry["rowIndex"],
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": entry["year"],
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": entry["recruitmentGroup"],
                        "quota": parsed.get("quota"),
                        "competitionRate": parsed.get("competitionRate"),
                        "additionalPass": parsed.get("additionalPass"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": 0,
                        "hasQuotaAndCompetition": False,
                        "hasOutcomeScore": True,
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": (
                            "source_preserving_office_kyonggi_2022_regular_score_pdf_review"
                        ),
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": "",
                        "rowIndex": entry["rowIndex"],
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
            continue
        kyonggi_2025_entries = (
            parse_kyonggi_2025_official_result_entries(row)
            if kyonggi_2025_result_source
            else []
        )
        if kyonggi_2025_entries:
            for entry in kyonggi_2025_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                entry_years = [entry["year"]] if entry.get("year") else years
                for year in entry_years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        normalize_text(entry.get("track")),
                        normalize_text(entry.get("recruitmentGroup")),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        number_string(parsed.get("percentileCutCandidate")),
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": entry["recruitmentGroup"],
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", False
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                normalize_text(entry.get("sourceConfidence"))
                                or "source_preserving_office_kyonggi_2025_result_detail_pdf_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(entry.get("sectionId"))
                            or f"kyonggi_2025_detail:{entry['track']}",
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        yewon_2022_susi_entries = (
            parse_yewon_2022_susi_result_pdf_entries(row)
            if yewon_2022_susi_result_source
            else []
        )
        if yewon_2022_susi_entries:
            for entry in yewon_2022_susi_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        normalize_text(entry.get("track")),
                        parsed["quota"],
                        parsed.get("applicants"),
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        number_string(parsed.get("additionalPass")),
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": "none",
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_yewon_2022_susi_result_pdf_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": f"yewon_2022_susi:{entry['track']}",
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        anyang_2022_2024_entries = (
            parse_anyang_2022_2024_result_entries(row)
            if anyang_2022_2024_result_source
            else []
        )
        if anyang_2022_2024_entries:
            for entry in anyang_2022_2024_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("additionalPass")),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_anyang_campus_result_pdf_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(entry.get("sectionTitle"))
                            or normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        anyang_entries = (
            parse_anyang_2025_regular_result_entries(row)
            if anyang_2025_regular_result_source
            else []
        )
        if anyang_entries:
            for entry in anyang_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("additionalPass")),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_anyang_regular_result_pdf_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        cau_entries = (
            parse_cau_2025_regular_result_entries(row)
            if cau_2025_regular_result_source
            else []
        )
        if cau_entries:
            for entry in cau_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                entry_years = [entry["year"]] if entry.get("year") else years
                for year in entry_years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("additionalPass")),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                normalize_text(entry.get("sourceConfidence"))
                                or "source_preserving_office_cau_regular_result_pdf_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(entry.get("sectionId"))
                            or normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        kookmin_entries = (
            parse_kookmin_2026_susi_result_entries(row)
            if kookmin_2026_susi_result_source
            else []
        )
        if kookmin_entries:
            for entry in kookmin_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                year = entry["year"]
                source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                raw_path = first_for_year(row.get("rawPaths"), year)
                dedupe_key = (
                    normalize_text(row.get("unvCd")),
                    year,
                    canonical_unit,
                    normalize_text(entry.get("sectionId")),
                    parsed["quota"],
                    number_string(parsed["competitionRate"]),
                    number_string(parsed.get("additionalPass")),
                    number_string(parsed.get("avgScoreCandidate")),
                    number_string(parsed.get("cutScoreCandidate")),
                    entry["rowIndex"],
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": year,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": "none",
                        "quota": parsed["quota"],
                        "competitionRate": parsed["competitionRate"],
                        "additionalPass": parsed.get("additionalPass"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": 0,
                        "hasQuotaAndCompetition": parsed.get("hasQuotaAndCompetition", True),
                        "hasOutcomeScore": parsed["hasOutcomeScore"],
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": "source_preserving_office_kookmin_2026_susi_result_pdf_review",
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": "",
                        "rowIndex": entry["rowIndex"],
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
            continue
        halla_entries = (
            parse_halla_2026_susi_result_entries(row)
            if halla_2026_susi_result_source
            else []
        )
        if halla_entries:
            for entry in halla_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        normalize_text(entry.get("sectionId")),
                        number_string(parsed.get("cutScoreCandidate")),
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", False
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_halla_susi_75cut_pdf_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(entry.get("sectionId")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        seowon_2021_susi_entries = (
            parse_seowon_2021_susi_result_entries(row)
            if seowon_2021_susi_result_source
            else []
        )
        if seowon_2021_susi_entries:
            for entry in seowon_2021_susi_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                year = entry["year"]
                source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                raw_path = first_for_year(row.get("rawPaths"), year)
                dedupe_key = (
                    normalize_text(row.get("unvCd")),
                    year,
                    canonical_unit,
                    normalize_text(entry.get("sectionId")),
                    number_string(parsed.get("avgScoreCandidate")),
                    number_string(parsed.get("cutScoreCandidate")),
                    entry["rowIndex"],
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": year,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": "none",
                        "quota": parsed["quota"],
                        "competitionRate": parsed["competitionRate"],
                        "additionalPass": parsed.get("additionalPass"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": 0,
                        "hasQuotaAndCompetition": parsed.get(
                            "hasQuotaAndCompetition", False
                        ),
                        "hasOutcomeScore": parsed["hasOutcomeScore"],
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": (
                            "source_preserving_office_seowon_2021_susi_result_pdf_review"
                        ),
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": "",
                        "rowIndex": entry["rowIndex"],
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
            continue
        seowon_2022_regular_entries = (
            parse_seowon_2022_regular_result_entries(row)
            if seowon_2022_regular_result_source
            else []
        )
        if seowon_2022_regular_entries:
            for entry in seowon_2022_regular_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                year = entry["year"]
                source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                raw_path = first_for_year(row.get("rawPaths"), year)
                dedupe_key = (
                    normalize_text(row.get("unvCd")),
                    year,
                    canonical_unit,
                    recruitment_group,
                    parsed["quota"],
                    parsed["applicants"],
                    number_string(parsed["competitionRate"]),
                    number_string(parsed.get("additionalPass")),
                    number_string(parsed.get("avgScoreCandidate")),
                    number_string(parsed.get("cutScoreCandidate")),
                    entry["rowIndex"],
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": year,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": recruitment_group,
                        "quota": parsed["quota"],
                        "applicants": parsed["applicants"],
                        "competitionRate": parsed["competitionRate"],
                        "additionalPass": parsed.get("additionalPass"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": 0,
                        "hasQuotaAndCompetition": parsed.get("hasQuotaAndCompetition", True),
                        "hasOutcomeScore": parsed["hasOutcomeScore"],
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": (
                            "source_preserving_office_seowon_2022_regular_result_pdf_review"
                        ),
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": "",
                        "rowIndex": entry["rowIndex"],
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
            continue
        hansei_2026_entries = (
            parse_hansei_2026_regular_result_entries(row)
            if hansei_2026_regular_result_source
            else []
        )
        if hansei_2026_entries:
            for entry in hansei_2026_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        normalize_text(entry.get("track")),
                        parsed["quota"],
                        parsed["applicants"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "applicants": parsed["applicants"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_hansei_2026_regular_result_pdf_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        joongbu_entries = (
            parse_joongbu_official_html_result_entries(row)
            if joongbu_html_result_source
            else []
        )
        if joongbu_entries:
            for entry in joongbu_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                entry_years = [entry["year"]] if entry.get("year") else years
                for year in entry_years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        normalize_text(entry.get("sectionId")),
                        parsed["quota"],
                        parsed.get("applicants"),
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("additionalPass")),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                        entry["tableIndex"],
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "applicants": parsed.get("applicants"),
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                f"source_preserving_office_joongbu_{year}_html_result_table_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(entry.get("sectionId")),
                            "tableIndex": entry["tableIndex"],
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        chosun_2021_entries = (
            parse_chosun_2021_workbook_result_entries(row)
            if chosun_2021_workbook_result_source
            else []
        )
        if chosun_2021_entries:
            for entry in chosun_2021_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("additionalPass")),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_chosun_2021_workbook_result_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        html_entries = parse_office_html_table_outcome_entries(row) if html_table_source else []
        if html_entries:
            for entry in html_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(
                    entry.get("canonicalCandidate")
                ) or canonical_name(unit_name)
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        source_url,
                        raw_path,
                        entry["rowIndex"],
                        entry["tripleIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_viewer_html_result_table_review"
                                if "manual_ginue_regular_results_docs"
                                in join_values(row.get("sourceLabels"))
                                else "source_preserving_office_hanil_application_status_html_review"
                                if "gap_manual_hanil_docs"
                                in join_values(row.get("sourceLabels"))
                                else "source_preserving_office_html_ocr_result_table_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        jnue_entries = parse_jnue_result_entries(row) if jnue_result_source else []
        if jnue_entries:
            for entry in jnue_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("additionalPass")),
                        number_string(parsed.get("cutScoreCandidate")),
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": "source_preserving_office_jnue_result_pdf_review",
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        cnue_entries = parse_cnue_result_entries(row) if cnue_result_source else []
        if cnue_entries:
            for entry in cnue_entries:
                unit_name = entry["unitName"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_unit,
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        number_string(parsed.get("avgScoreCandidate")),
                        number_string(parsed.get("cutScoreCandidate")),
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_unit,
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": "source_preserving_office_cnue_result_document_review",
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        gwnu_athletics_entries = (
            parse_gwnu_2021_2022_athletics_score_workbook_entries(row)
            if gwnu_athletics_score_source
            else []
        )
        if gwnu_athletics_entries:
            for entry in gwnu_athletics_entries:
                unit_name = entry["unitName"]
                parsed = entry["parsed"]
                year = entry["year"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                recruitment_group = entry["recruitmentGroup"]
                source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                raw_path = first_for_year(row.get("rawPaths"), year)
                dedupe_key = (
                    normalize_text(row.get("unvCd")),
                    year,
                    canonical_unit,
                    recruitment_group,
                    number_string(parsed.get("avgScoreCandidate")),
                    number_string(parsed.get("cutScoreCandidate")),
                    number_string(parsed.get("percentileCutCandidate")),
                    source_url,
                    raw_path,
                    entry["rowIndex"],
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": year,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": recruitment_group,
                        "quota": None,
                        "competitionRate": "",
                        "additionalPass": None,
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": parsed.get("subjectMetricCount", 0),
                        "hasQuotaAndCompetition": False,
                        "hasOutcomeScore": True,
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": (
                            "source_preserving_office_gwnu_athletics_score_workbook_review"
                        ),
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": normalize_text(entry.get("tableIndex")),
                        "rowIndex": normalize_text(entry.get("rowIndex")),
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
            continue
        gwnu_2023_region_subject_entries = (
            parse_gwnu_2023_region_subject_image_ocr_entries(row)
            if gwnu_2023_region_subject_image_source
            else []
        )
        if gwnu_2023_region_subject_entries:
            for entry in gwnu_2023_region_subject_entries:
                unit_name = entry["unitName"]
                parsed = entry["parsed"]
                year = entry["year"]
                canonical_unit = normalize_text(entry.get("canonicalCandidate")) or canonical_name(
                    unit_name
                )
                recruitment_group = entry["recruitmentGroup"]
                source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                raw_path = first_for_year(row.get("rawPaths"), year)
                competition_rate = parsed.get("competitionRate")
                dedupe_key = (
                    normalize_text(row.get("unvCd")),
                    year,
                    canonical_unit,
                    recruitment_group,
                    parsed.get("quota"),
                    number_string(competition_rate),
                    number_string(parsed.get("avgScoreCandidate")),
                    number_string(parsed.get("cutScoreCandidate")),
                    source_url,
                    raw_path,
                    entry["rowIndex"],
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": year,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_unit,
                        "recruitmentGroup": recruitment_group,
                        "quota": parsed.get("quota"),
                        "competitionRate": (
                            number_string(competition_rate)
                            if competition_rate is not None
                            else ""
                        ),
                        "additionalPass": parsed.get("additionalPass"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": parsed.get("subjectMetricCount", 0),
                        "hasQuotaAndCompetition": True,
                        "hasOutcomeScore": True,
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": (
                            "source_preserving_office_gwnu_2023_region_subject_image_review"
                        ),
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(entry.get("sectionId")),
                        "tableIndex": normalize_text(entry.get("tableIndex")),
                        "rowIndex": normalize_text(entry.get("rowIndex")),
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
            continue
        line_entries = (
            parse_office_line_competition_outcome_entries(row)
            if line_competition_source
            else []
        )
        if line_entries:
            for entry in line_entries:
                unit_name = entry["unitName"]
                parsed = entry["parsed"]
                recruitment_group = entry["recruitmentGroup"]
                for year in years:
                    source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                    raw_path = first_for_year(row.get("rawPaths"), year)
                    dedupe_key = (
                        normalize_text(row.get("unvCd")),
                        year,
                        canonical_name(unit_name),
                        recruitment_group,
                        parsed["quota"],
                        number_string(parsed["competitionRate"]),
                        source_url,
                        raw_path,
                        entry["rowIndex"],
                    )
                    if dedupe_key in seen:
                        continue
                    seen.add(dedupe_key)
                    rows.append(
                        {
                            "unvCd": normalize_text(row.get("unvCd")),
                            "universityName": normalize_text(row.get("universityName")),
                            "year": year,
                            "admissionUnitName": unit_name,
                            "admissionUnitCanonicalCandidate": canonical_name(unit_name),
                            "recruitmentGroup": recruitment_group,
                            "quota": parsed["quota"],
                            "competitionRate": parsed["competitionRate"],
                            "additionalPass": parsed.get("additionalPass"),
                            "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                            "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                            "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                            "scoreAvailability": parsed["scoreAvailability"],
                            "metricCount": parsed["metricCount"],
                            "subjectMetricCount": 0,
                            "hasQuotaAndCompetition": parsed.get(
                                "hasQuotaAndCompetition", True
                            ),
                            "hasOutcomeScore": parsed["hasOutcomeScore"],
                            "candidateSha256": normalize_text(row.get("candidateSha256")),
                            "sourceProvider": "university-admission-office",
                            "sourceConfidence": (
                                "source_preserving_office_competition_pdf_line_review"
                            ),
                            "sourceUrl": source_url,
                            "rawPath": raw_path,
                            "sectionId": normalize_text(row.get("evidenceRole")),
                            "tableIndex": "",
                            "rowIndex": entry["rowIndex"],
                            "reviewStatus": normalize_text(row.get("reviewStatus"))
                            or "needs_human_verification",
                        }
                    )
            continue
        matches = office_outcome_unit_matches(text)
        if not matches:
            continue
        for index, (unit_name, start, end) in enumerate(matches):
            next_start = matches[index + 1][1] if index + 1 < len(matches) else len(text)
            segment = text[end:next_start]
            parsed = parse_office_outcome_segment(
                segment,
                text,
                allow_direct_competition=office_direct_competition_fallback_allowed(row),
            )
            if parsed is None and structured_workbook_row_source:
                parsed = parse_office_score_only_workbook_outcome_row(row)
            if parsed is None:
                continue
            if score_workbook_row_source and not parsed.get("hasOutcomeScore"):
                continue
            if competition_workbook_row_source and parsed.get("hasOutcomeScore"):
                continue
            recruitment_group = infer_recruitment_group_near_outcome_unit(text, unit_name, segment)
            for year in years:
                source_url = first_for_year(row.get("sourceCandidateUrls"), year)
                raw_path = first_for_year(row.get("rawPaths"), year)
                dedupe_key = (
                    normalize_text(row.get("unvCd")),
                    year,
                    canonical_name(unit_name),
                    recruitment_group,
                    parsed["quota"],
                    number_string(parsed["competitionRate"]),
                    source_url,
                    raw_path,
                )
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "unvCd": normalize_text(row.get("unvCd")),
                        "universityName": normalize_text(row.get("universityName")),
                        "year": year,
                        "admissionUnitName": unit_name,
                        "admissionUnitCanonicalCandidate": canonical_name(unit_name),
                        "recruitmentGroup": recruitment_group,
                        "quota": parsed["quota"],
                        "competitionRate": parsed["competitionRate"],
                        "additionalPass": parsed.get("additionalPass"),
                        "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                        "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                        "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                        "scoreAvailability": parsed["scoreAvailability"],
                        "metricCount": parsed["metricCount"],
                        "subjectMetricCount": 0,
                        "hasQuotaAndCompetition": parsed.get("hasQuotaAndCompetition", True),
                        "hasOutcomeScore": parsed["hasOutcomeScore"],
                        "candidateSha256": normalize_text(row.get("candidateSha256")),
                        "sourceProvider": "university-admission-office",
                        "sourceConfidence": "source_preserving_office_result_table_review",
                        "sourceUrl": source_url,
                        "rawPath": raw_path,
                        "sectionId": normalize_text(row.get("evidenceRole")),
                        "tableIndex": "",
                        "rowIndex": index,
                        "reviewStatus": normalize_text(row.get("reviewStatus"))
                        or "needs_human_verification",
                    }
                )
    return rows


def is_office_html_table_historical_outcome_source(row: dict[str, Any]) -> bool:
    role = normalize_text(row.get("evidenceRole"))
    target = normalize_text(row.get("evidenceTarget"))
    evidence_types = join_values(row.get("evidenceTypes"))
    source_roles = join_values(row.get("sourceLinkRoles"))
    source_labels = join_values(row.get("sourceLabels"))
    catholic_regular_source = "manual_catholic_regular_results_docs" in source_labels
    ginue_regular_source = "manual_ginue_regular_results_docs" in source_labels
    ulsan_2021_official_result_source = (
        "ulsan_2021_official_results_docs" in source_labels
    )
    scnu_html_result_source = "scnu_html_results_docs" in source_labels
    hanil_application_status_source = is_hanil_application_status_html_source(row)
    if role not in OFFICE_HISTORICAL_OUTCOME_ROLES and not (
        catholic_regular_source and role == "csat_rule_ocr_page"
    ):
        return False
    legacy_image_ocr_table = "image_ocr" in evidence_types and "competition_rate" in source_roles
    catholic_regular_pdf_ocr_table = (
        "pdf_page_ocr" in evidence_types
        and catholic_regular_source
        and (
            "competition_rate" in source_roles
            or "admission_result" in source_roles
            or role in {"admission_result_ocr_page", "competition_rate_ocr_page"}
            or role == "csat_rule_ocr_page"
        )
    )
    ginue_viewer_html_table = (
        "html_table" in evidence_types
        and ginue_regular_source
        and "admission_result" in source_roles
    )
    ulsan_2021_html_result_table = (
        "html_table" in evidence_types
        and ulsan_2021_official_result_source
        and "admission_result" in source_roles
    )
    scnu_html_result_table = (
        "html_table" in evidence_types
        and scnu_html_result_source
        and "admission_result" in source_roles
    )
    if not (
        legacy_image_ocr_table
        or catholic_regular_pdf_ocr_table
        or ginue_viewer_html_table
        or ulsan_2021_html_result_table
        or scnu_html_result_table
        or hanil_application_status_source
    ):
        return False
    text = office_text_candidate_full_text(row)
    if catholic_regular_pdf_ocr_table and not re.search(r"정시\s*모집", text):
        return False
    if target != "HistoricalOutcome" and not (
        catholic_regular_source
        and target == "AdmissionRule"
        and role == "csat_rule_ocr_page"
        and re.search(r"정시\s*모집|최종\s*전형\s*점수|최종\s*점수|백\s*분\s*위|백분위", text)
    ):
        return False
    if "<tr" not in text or "<td" not in text:
        return False
    return bool(OFFICE_HTML_ROW_PATTERN.search(text) and OFFICE_HTML_CELL_PATTERN.search(text))


def parse_office_html_table_outcome_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = office_text_candidate_full_text(row)
    entries: list[dict[str, Any]] = []
    source_labels = join_values(row.get("sourceLabels"))
    if "gap_manual_hanil_docs" in source_labels:
        return parse_hanil_application_status_html_entries(row)
    if "manual_ginue_regular_results_docs" in source_labels:
        return parse_ginue_regular_results_html_entries(row)
    expanded_grid_allowed = "manual_catholic_regular_results_docs" in source_labels
    rowspan_grid_allowed = (
        "image_ocr" in join_values(row.get("evidenceTypes"))
        and "competition_rate" in join_values(row.get("sourceLinkRoles"))
    )
    table_rows = (
        office_html_table_grid(text)
        if expanded_grid_allowed or rowspan_grid_allowed
        else [
            [clean_office_html_cell(cell) for cell in OFFICE_HTML_CELL_PATTERN.findall(match.group(1))]
            for match in OFFICE_HTML_ROW_PATTERN.finditer(text)
        ]
    )
    for row_index, cells in enumerate(table_rows):
        cells = [cell for cell in cells if cell or cell == "0"]
        if len(cells) < 4:
            continue
        unit_index, unit_name = office_html_table_unit_cell(cells)
        if unit_index is None or not unit_name:
            continue
        unit_name = office_html_table_display_unit_name(row, unit_name)
        canonical_candidate = office_html_table_canonical_candidate(row, unit_name)
        recruitment_group = office_html_table_recruitment_group(cells[: unit_index + 1])
        appended_competition_entry = False
        for triple_index, quota, applicants, competition_rate in office_html_table_competition_triples(
            cells[unit_index + 1 :]
        ):
            appended_competition_entry = True
            entries.append(
                {
                    "unitName": unit_name,
                    "canonicalCandidate": canonical_candidate,
                    "recruitmentGroup": recruitment_group,
                    "rowIndex": row_index,
                    "tripleIndex": triple_index,
                    "parsed": {
                        "quota": quota,
                        "applicants": applicants,
                        "competitionRate": round(competition_rate, 2),
                        "additionalPass": None,
                        "avgScoreCandidate": "",
                        "cutScoreCandidate": "",
                        "percentileCutCandidate": "",
                        "scoreAvailability": "office_quota_competition_candidate",
                        "metricCount": 0,
                        "hasQuotaAndCompetition": True,
                        "hasOutcomeScore": False,
                    },
                }
            )
        if appended_competition_entry:
            continue
        if not expanded_grid_allowed:
            continue
        score_metrics = office_html_table_score_metrics(cells[unit_index + 1 :], text)
        if score_metrics is None:
            continue
        entries.append(
            {
                "unitName": unit_name,
                "canonicalCandidate": canonical_candidate,
                "recruitmentGroup": recruitment_group,
                "rowIndex": row_index,
                "tripleIndex": 0,
                "parsed": score_metrics,
            }
        )
    return entries


CATHOLIC_SONGSIN_2023_REGULAR_SINHAK_ROW_PATTERN = re.compile(
    r"<t[dh][^>]*>\s*신학과\s*</t[dh]>\s*"
    r"<t[dh][^>]*>\s*(?P<quota>13)\s*</t[dh]>\s*"
    r"<t[dh][^>]*>\s*(?P<applicants>26)\s*</t[dh]>\s*"
    r"<t[dh][^>]*>\s*(?P<competition>2[,\.]00)\s*</t[dh]>\s*"
    r"<t[dh][^>]*>\s*0[,\.]76\s*</t[dh]>\s*"
    r"<t[dh][^>]*>\s*(?P<additional>0)\s*</t[dh]>",
    re.I,
)


def is_catholic_songsin_2023_regular_result_remap_source(row: dict[str, Any]) -> bool:
    source_labels = join_values(row.get("sourceLabels"))
    if "manual_catholic_regular_results_docs" not in source_labels:
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    source_context = join_values(
        [
            row.get("sourceCandidateUrls"),
            row.get("attachmentUrls"),
            row.get("sourcePaths"),
            row.get("rawPaths"),
        ]
    )
    if "board_seq=30259" not in source_context and "2023_info.pdf" not in source_context:
        return False
    if "page-0022" not in source_context and "page-22" not in source_context:
        return False
    text = office_text_candidate_full_text(row)
    return bool(
        "2023학년도" in text
        and "정시모집" in text
        and CATHOLIC_SONGSIN_2023_REGULAR_SINHAK_ROW_PATTERN.search(text)
    )


def parse_catholic_songsin_2023_regular_result_remap_entries(
    row: dict[str, Any]
) -> list[dict[str, Any]]:
    text = office_text_candidate_full_text(row)
    match = CATHOLIC_SONGSIN_2023_REGULAR_SINHAK_ROW_PATTERN.search(text)
    if not match:
        return []
    quota = office_html_integer_cell_value(match.group("quota"))
    applicants = office_html_integer_cell_value(match.group("applicants"))
    competition = office_html_competition_cell_value(match.group("competition"))
    additional_pass = office_html_integer_cell_value(match.group("additional"))
    if quota is None or applicants is None or competition is None:
        return []
    if not is_consistent_office_html_competition(quota, applicants, competition):
        return []
    return [
        {
            "year": 2023,
            "unitName": "신학과",
            "canonicalCandidate": "신학과",
            "recruitmentGroup": "ga",
            "sectionId": "catholic_0000049_2023_regular_competition_rate",
            "tableIndex": "2023_regular_page_22",
            "rowIndex": "catholic_0000049_2023_regular_sinhak",
            "parsed": {
                "quota": quota,
                "applicants": applicants,
                "competitionRate": round(float(competition), 2),
                "additionalPass": additional_pass,
                "avgScoreCandidate": "",
                "cutScoreCandidate": "",
                "percentileCutCandidate": "",
                "scoreAvailability": "office_quota_competition_candidate",
                "metricCount": 0,
                "hasQuotaAndCompetition": True,
                "hasOutcomeScore": False,
            },
        }
    ]


def is_ltu_2021_official_result_image_source(row: dict[str, Any]) -> bool:
    if "gap_ltu_2021_official_result_image_docs" not in join_values(row.get("sourceLabels")):
        return False
    if normalize_text(row.get("unvCd")) != "0000108":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_image_ocr":
        return False
    if "image_ocr" not in join_values(row.get("evidenceTypes")):
        return False
    text = office_text_candidate_full_text(row)
    return bool("<tr" in text and "<td" in text and "디아코니아" in text)


def parse_ltu_2021_official_result_image_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = office_text_candidate_full_text(row)
    entries: list[dict[str, Any]] = []
    unit_name = "디아코니아학부"
    for row_index, match in enumerate(OFFICE_HTML_ROW_PATTERN.finditer(text)):
        cells = [clean_office_html_cell(cell) for cell in OFFICE_HTML_CELL_PATTERN.findall(match.group(1))]
        cells = [cell for cell in cells if cell or cell == "0"]
        if len(cells) >= 10:
            offset = 3
            if "디아코니아" in "".join(cells[:3]):
                unit_name = "디아코니아학부"
            else:
                continue
        elif len(cells) >= 7:
            offset = 1
        else:
            continue
        quota = office_html_integer_cell_value(cells[offset])
        applicants = office_html_integer_cell_value(cells[offset + 1])
        registrants = office_html_integer_cell_value(cells[offset + 2])
        competition = office_html_competition_cell_value(cells[offset + 3])
        if quota is None or applicants is None or competition is None:
            continue
        if not is_consistent_office_html_competition(quota, applicants, float(competition)):
            continue
        avg_score = office_html_score_cell_value(cells[offset + 4]) if len(cells) > offset + 4 else None
        cut_score = office_html_score_cell_value(cells[offset + 5]) if len(cells) > offset + 5 else None
        metric_count = 1 + int(avg_score is not None) + int(cut_score is not None)
        entries.append(
            {
                "unitName": unit_name,
                "recruitmentGroup": "none",
                "rowIndex": row_index,
                "parsed": {
                    "quota": quota,
                    "applicants": applicants,
                    "competitionRate": round(float(competition), 2),
                    "additionalPass": None,
                    "avgScoreCandidate": number_string(avg_score) if avg_score is not None else "",
                    "cutScoreCandidate": number_string(cut_score) if cut_score is not None else "",
                    "percentileCutCandidate": "",
                    "registeredCountCandidate": registrants,
                    "scoreAvailability": (
                        "office_score_metric_candidate"
                        if avg_score is not None or cut_score is not None
                        else "office_quota_competition_candidate"
                    ),
                    "metricCount": metric_count,
                    "hasQuotaAndCompetition": True,
                    "hasOutcomeScore": avg_score is not None or cut_score is not None,
                },
            }
        )
    return entries


def is_wsu_2026_susi_result_appendix_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000240":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_table":
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if "ent.wsu.ac.kr" not in source_context or "2027susi.pdf" not in source_context:
        return False
    text = wsu_2026_susi_result_source_text(row)
    return bool(
        "2026학년도 최종등록자 수시모집 결과" in text
        and "학생부 교과 [ 교과중심 ]" in text
        and "WOOSONG UNIVERSITY" in text
    )


def wsu_2026_susi_result_source_year(row: dict[str, Any]) -> int | None:
    return 2026 if is_wsu_2026_susi_result_appendix_source(row) else None


def wsu_2026_susi_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is not None:
        text = raw_office_text_source(source_path)
        if text:
            return text
    return office_text_candidate_raw_text(row)


def parse_wsu_2026_susi_result_appendix_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = wsu_2026_susi_result_source_text(row)
    page_text = wsu_2026_susi_result_page_text(text)
    entries: list[dict[str, Any]] = []
    for line_index, raw_line in enumerate(page_text.splitlines()):
        line = normalize_text(raw_line)
        if not line or not wsu_2026_susi_result_data_line(line):
            continue
        unit_name, tail = split_wsu_2026_susi_unit_and_tail(raw_line)
        if not unit_name:
            continue
        cells = re.findall(r"-|\d+(?:\.\d+)?", tail)
        if len(cells) < 15:
            continue
        for track, offset, width in (
            ("student_record_curriculum", 0, 5),
            ("student_record_interview", 5, 6),
            ("student_record_comprehensive_document", 11, 4),
        ):
            parsed = parse_wsu_2026_susi_track_cells(cells[offset : offset + width], track)
            if parsed is None:
                continue
            entries.append(
                {
                    "unitName": unit_name,
                    "canonicalCandidate": canonical_name(unit_name),
                    "track": track,
                    "rowIndex": line_index,
                    "parsed": parsed,
                }
            )
    return entries


def wsu_2026_susi_result_page_text(text: str) -> str:
    for page in text.split("\f"):
        if (
            "2026학년도 최종등록자 수시모집 결과" in page
            and "학생부 교과 [ 교과중심 ]" in page
        ):
            return page
    return text


def wsu_2026_susi_result_data_line(line: str) -> bool:
    if "학과" not in line and "학부" not in line and "전공" not in line and "교육과" not in line:
        return False
    if line.startswith("※") or "신 설 학 과" in line:
        return False
    if len(re.findall(r"\d+(?:\.\d+)?|-", line)) < 12:
        return False
    return bool(OFFICE_UNIT_NAME_PATTERN.search(line))


def split_wsu_2026_susi_unit_and_tail(line: str) -> tuple[str, str]:
    number_match = re.search(r"\s(?:-|\d+(?:\.\d+)?)\s", line)
    if number_match is None:
        return "", ""
    prefix = line[: number_match.start()]
    chunks = [
        normalize_text(chunk)
        for chunk in re.split(r"\s{2,}", prefix)
        if normalize_text(chunk)
    ]
    unit_name = ""
    for chunk in reversed(chunks):
        chunk = re.sub(r"^[★◉\s]+", "", chunk)
        match = re.search(
            r"([가-힣A-Za-z0-9·ㆍ&()./+,-]{1,56}(?:학과|교육과|학부|전공))$",
            chunk,
        )
        if not match:
            continue
        unit_name = clean_office_admission_unit_name(match.group(1))
        break
    if not is_useful_office_admission_unit_name(unit_name):
        return "", ""
    return unit_name, line[number_match.start() :]


def parse_wsu_2026_susi_track_cells(
    cells: list[str], track: str
) -> dict[str, Any] | None:
    if track == "student_record_curriculum":
        if len(cells) < 5:
            return None
        quota, competition, avg_score, cut_score, additional = cells[:5]
        cut_score_candidates = [cut_score]
    elif track == "student_record_interview":
        if len(cells) < 6:
            return None
        quota, competition, avg_score, cut_70, cut_100, additional = cells[:6]
        cut_score_candidates = [cut_70, cut_100]
    else:
        if len(cells) < 4:
            return None
        quota, competition, avg_score, additional = cells[:4]
        cut_score_candidates = []
    quota_value = office_html_integer_cell_value(quota)
    competition_value = office_html_competition_cell_value(competition)
    if quota_value is None or competition_value is None:
        return None
    avg_value = office_html_score_cell_value(avg_score)
    cut_values = [
        value
        for value in (office_html_score_cell_value(candidate) for candidate in cut_score_candidates)
        if value is not None
    ]
    score_values = ([avg_value] if avg_value is not None else []) + cut_values
    additional_value = office_html_integer_cell_value(additional)
    return {
        "quota": quota_value,
        "competitionRate": round(float(competition_value), 2),
        "additionalPass": additional_value,
        "avgScoreCandidate": number_string(avg_value) if avg_value is not None else "",
        "cutScoreCandidate": number_string(cut_values[0]) if cut_values else "",
        "percentileCutCandidate": "",
        "scoreAvailability": (
            "office_score_metric_candidate"
            if score_values
            else "office_quota_competition_candidate"
        ),
        "metricCount": len(score_values),
        "hasOutcomeScore": bool(score_values),
    }


HANSEI_2026_REGULAR_ROW_PATTERN = re.compile(
    r"^(?P<label>.+?)\s+"
    r"(?P<quota>\d{1,4})\s+"
    r"(?P<applicants>\d{1,5})\s+"
    r"(?P<competition>\d{1,3}(?:\.\d+)?)\s*:\s*1\s+"
    r"(?P<scores>(?:\d{1,3}\.\d{1,2}\s+){5}\d{1,3}\.\d{1,2})\s*$"
)
HANSEI_2026_REGULAR_TRACK_LABELS = [
    "특성화고교졸업자(정원외)",
    "농어촌학생(정원외)",
    "일반(공연예술)",
    "일반(디자인)",
    "일반(음악)",
    "재외국민",
    "일반",
]


def is_hansei_2026_regular_result_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000201":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    source_context = join_values(
        [
            row.get("sourcePaths"),
            row.get("rawPaths"),
            row.get("attachmentUrls"),
            row.get("sourceCandidateUrls"),
        ]
    )
    if (
        "extracted-hansei-2026-regular-results-20260614" not in source_context
        and "23027/download.do" not in source_context
    ):
        return False
    text = hansei_2026_regular_result_source_text(row)
    return bool(
        "2026학년도 신입생 정시모집 - 지원현황, 수능 성적" in text
        and "수능(백분위)" in text
        and "최종등록자" in text
    )


def hansei_2026_regular_result_source_year(row: dict[str, Any]) -> int | None:
    return 2026 if is_hansei_2026_regular_result_source(row) else None


def hansei_2026_regular_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is not None:
        return raw_office_text_source(source_path)
    return office_text_candidate_full_text(row)


def parse_hansei_2026_regular_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = hansei_2026_regular_result_source_text(row)
    entries: list[dict[str, Any]] = []
    current_group = "ga"
    current_track = "일반"
    for line_index, raw_line in enumerate(text.splitlines()):
        line = normalize_text(raw_line)
        if not line:
            continue
        current_group, current_track = hansei_2026_regular_update_context(
            line, current_group, current_track
        )
        match = HANSEI_2026_REGULAR_ROW_PATTERN.match(line)
        if not match:
            continue
        group, track, unit_name = hansei_2026_regular_split_label(
            match.group("label"),
            current_group,
            current_track,
        )
        if not unit_name or not hansei_2026_regular_is_useful_unit_name(unit_name):
            continue
        if unit_name.startswith("음악전공 ") and track != "재외국민":
            group = "da"
            track = "일반(음악)"
        current_group = group
        current_track = track
        quota = int(match.group("quota"))
        applicants = int(match.group("applicants"))
        competition_rate = float(match.group("competition"))
        if quota <= 0 or applicants < 0:
            continue
        if not is_consistent_office_html_competition(quota, applicants, competition_rate):
            continue
        score_values = [
            float(value)
            for value in re.findall(r"\d{1,3}\.\d{1,2}", match.group("scores"))
        ]
        if len(score_values) != 6 or not all(0 < value <= 100 for value in score_values):
            continue
        final_high, final_avg, final_low = score_values[3:]
        display_unit = f"{unit_name} / {track}"
        entries.append(
            {
                "unitName": display_unit,
                "canonicalCandidate": f"{canonical_name(unit_name)}({track})",
                "recruitmentGroup": group,
                "track": track,
                "rowIndex": line_index + 1,
                "parsed": {
                    "quota": quota,
                    "applicants": applicants,
                    "competitionRate": round(competition_rate, 2),
                    "additionalPass": None,
                    "avgScoreCandidate": number_string(final_avg),
                    "cutScoreCandidate": number_string(final_low),
                    "percentileCutCandidate": number_string(final_low),
                    "scoreAvailability": (
                        "office_quota_competition_and_score_metric_candidate"
                    ),
                    "metricCount": 6,
                    "hasQuotaAndCompetition": True,
                    "hasOutcomeScore": True,
                    "finalRegisteredHighScoreCandidate": number_string(final_high),
                },
            }
        )
    return entries


def hansei_2026_regular_update_context(
    line: str, current_group: str, current_track: str
) -> tuple[str, str]:
    group = current_group
    track = current_track
    if "가군" in line:
        group = "ga"
    elif "나군" in line:
        group = "na"
    elif "다군" in line:
        group = "da"
    for label in HANSEI_2026_REGULAR_TRACK_LABELS:
        if label in line:
            track = label
            break
    return group, track


def hansei_2026_regular_split_label(
    label: str, current_group: str, current_track: str
) -> tuple[str, str, str]:
    text = normalize_text(label)
    group, track = hansei_2026_regular_update_context(text, current_group, current_track)
    text = re.sub(r"^(?:가군|나군|다군)\s+", "", text).strip()
    for track_label in HANSEI_2026_REGULAR_TRACK_LABELS:
        if text.startswith(track_label):
            text = text[len(track_label) :].strip()
            break
    return group, track, hansei_2026_regular_clean_unit_name(text)


def hansei_2026_regular_clean_unit_name(value: str) -> str:
    text = normalize_text(value).strip(" /,.:;·ㆍ-[]()")
    if text.startswith("음악전공 "):
        return text[:60]
    return clean_office_admission_unit_name(text)


def hansei_2026_regular_is_useful_unit_name(value: str) -> bool:
    text = normalize_text(value)
    if text.startswith("음악전공 "):
        return bool(re.search(r"피아노|성악|관현악|아트앤미디어작곡", text))
    return is_useful_office_admission_unit_name(text)


def is_hanil_application_status_html_source(row: dict[str, Any]) -> bool:
    source_labels = join_values(row.get("sourceLabels"))
    if "gap_manual_hanil_docs" not in source_labels:
        return False
    if normalize_text(row.get("unvCd")) != "0000206":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_table":
        return False
    if "html_table" not in join_values(row.get("evidenceTypes")):
        return False
    if "admission_result_html" not in join_values(row.get("sourceLinkRoles")):
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if "hanil.ac.kr" not in source_context and "html-results-gap_manual_hanil" not in source_context:
        return False
    text = office_text_candidate_full_text(row)
    return bool(
        re.search(r"신입학\s*수시모집\s*지원현황", text)
        and re.search(r"모집단위", text)
        and re.search(r"경쟁률", text)
    )


def parse_hanil_application_status_html_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = office_text_candidate_full_text(row)
    if not text:
        return []
    table_html_values = re.findall(r"<table\b[^>]*>.*?</table>", text, re.I | re.S) or [text]
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, int, int, str]] = set()
    for table_index, table_html in enumerate(table_html_values):
        table_text = normalize_text(html.unescape(re.sub(r"<[^>]+>", " ", table_html)))
        if "정원내" not in table_text or "경쟁률" not in table_text:
            continue
        grid = office_html_table_grid(table_html)
        header_top: list[str] = []
        header_bottom: list[str] = []
        data_start = 0
        for index, cells in enumerate(grid):
            normalized_cells = [clean_office_html_cell(cell) for cell in cells]
            if (
                "모집단위" in normalized_cells
                and "일반학생" in normalized_cells
                and "소계" in normalized_cells
            ):
                header_top = normalized_cells
                if index + 1 < len(grid):
                    header_bottom = [clean_office_html_cell(cell) for cell in grid[index + 1]]
                    data_start = index + 2
                break
        if not header_top or not header_bottom:
            continue
        for row_index, cells in enumerate(grid[data_start:], start=data_start):
            cells = [clean_office_html_cell(cell) for cell in cells]
            if not cells:
                continue
            if any(cell == "정원외" for cell in cells):
                break
            unit_base = clean_office_html_table_unit_name(cells[0] if len(cells) > 0 else "")
            if not unit_base:
                continue
            if unit_base == "합계":
                break
            limit = min(len(cells), len(header_top), len(header_bottom))
            column = 2
            while column + 2 < limit:
                if not (
                    header_bottom[column] == "모집"
                    and header_bottom[column + 1] == "지원"
                    and header_bottom[column + 2] == "경쟁률"
                ):
                    column += 1
                    continue
                track_name = clean_hanil_application_status_track_name(header_top[column])
                if not track_name:
                    column += 3
                    continue
                quota = office_html_integer_cell_value(cells[column])
                applicants = office_html_integer_cell_value(cells[column + 1])
                competition_rate = office_html_competition_cell_value(cells[column + 2])
                if quota is None or applicants is None or competition_rate is None:
                    column += 3
                    continue
                if not is_consistent_office_html_competition(
                    quota, applicants, competition_rate
                ):
                    column += 3
                    continue
                key = (
                    canonical_name(unit_base),
                    track_name,
                    quota,
                    applicants,
                    number_string(competition_rate),
                )
                if key in seen:
                    column += 3
                    continue
                seen.add(key)
                unit_name = f"{unit_base} / {track_name}"
                entries.append(
                    {
                        "unitName": unit_name,
                        "canonicalCandidate": f"{canonical_name(unit_base)}({track_name})",
                        "recruitmentGroup": "none",
                        "rowIndex": (table_index * 1000) + row_index,
                        "tripleIndex": column,
                        "parsed": {
                            "quota": quota,
                            "applicants": applicants,
                            "competitionRate": round(competition_rate, 2),
                            "additionalPass": None,
                            "avgScoreCandidate": "",
                            "cutScoreCandidate": "",
                            "percentileCutCandidate": "",
                            "scoreAvailability": "office_quota_competition_candidate",
                            "metricCount": 0,
                            "hasQuotaAndCompetition": True,
                            "hasOutcomeScore": False,
                        },
                    }
                )
                column += 3
    return entries


def clean_hanil_application_status_track_name(value: str) -> str:
    text = clean_office_html_cell(value)
    text = text.replace(" ", "")
    if not text or text in {"소계", "모집정원", "모집단위"}:
        return ""
    if not re.search(r"일반학생|지역인재|수급자|특기자", text):
        return ""
    return text[:40]


ANYANG_2022_2024_RESULT_BBS_YEAR: dict[str, int] = {
    "bbs_seq=2345": 2022,
    "bbs_seq=2364": 2022,
    "bbs_seq=2366": 2023,
    "bbs_seq=2367": 2023,
    "bbs_seq=2378": 2024,
    "bbs_seq=2379": 2024,
}

ANYANG_CAMPUS_RESULT_ROW_PATTERN = re.compile(
    r"^\s*"
    r"(?P<label>[가-힣A-Za-z0-9·ㆍ&()./+()\[\] -]{2,80}?)"
    r"\s+(?P<quota>\d{1,4})"
    r"\s+(?P<competition>\d{1,3}(?:\.\d+)?)\s*:\s*1"
    r"\s+(?P<rest>.+?)\s*$"
)

ANYANG_CAMPUS_RESULT_NUMBER_PATTERN = re.compile(
    r"-|\d+(?:\.\d+)?%|\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"
)

ANYANG_GANGHWA_UNIT_HINT_PATTERN = re.compile(
    r"게임[콘컨]텐츠학과|스마트시티공학과|해양바이오공학과|스포츠지도학과|"
    r"스포츠과학과|스포츠산업학과|스포츠응용산업학과|스포츠계열자유전공|"
    r"실용음악과|체육학과"
)


def is_anyang_2022_2024_result_source(row: dict[str, Any]) -> bool:
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if normalize_text(row.get("unvCd")) != "0000148":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    if "enter.anyang.ac.kr" not in source_context:
        return False
    if not any(marker in source_context for marker in ANYANG_2022_2024_RESULT_BBS_YEAR):
        return False
    text = normalize_text(anyang_2022_2024_result_source_text(row))
    return bool(
        re.search(r"202[234]\s*학년도", text)
        and re.search(r"(?:수시|정시|신입학).{0,20}(?:입시결과|통계자료|성적\s*결과)", text)
    )


def parse_anyang_2022_2024_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = anyang_2022_2024_result_source_text(row)
    if not text:
        return []
    lines = text.splitlines()
    entries: list[dict[str, Any]] = []
    section_title = ""
    for line_index, line in enumerate(lines):
        normalized = normalize_text(line)
        if normalized.startswith("◉"):
            section_title = clean_anyang_result_section_title(normalized)
            continue
        parsed = parse_anyang_campus_result_line(line)
        if parsed is None:
            continue
        unit_name = parsed.pop("unitName")
        track_label = anyang_result_track_label(section_title, row)
        recruitment_group = recruitment_group_from_korean_text(section_title)
        entries.append(
            {
                "unitName": f"{unit_name} / {track_label}",
                "canonicalCandidate": f"{unit_name}({track_label})",
                "recruitmentGroup": recruitment_group,
                "rowIndex": line_index + 1,
                "parsed": parsed,
                "sectionTitle": section_title,
            }
        )
    return entries


def parse_anyang_campus_result_line(line: str) -> dict[str, Any] | None:
    match = ANYANG_CAMPUS_RESULT_ROW_PATTERN.match(line)
    if not match:
        return None
    unit_name = clean_anyang_campus_result_unit_name(match.group("label"))
    if not unit_name or not ANYANG_GANGHWA_UNIT_HINT_PATTERN.search(unit_name):
        return None
    quota = int_or_none(match.group("quota"))
    competition = number_or_none(match.group("competition"))
    if quota is None or competition is None:
        return None
    rest_values = ANYANG_CAMPUS_RESULT_NUMBER_PATTERN.findall(match.group("rest"))
    if len(rest_values) < 3:
        return None
    rate_index = next(
        (index for index, value in enumerate(rest_values) if value.endswith("%")),
        len(rest_values),
    )
    metric_tokens = rest_values[:rate_index]
    additional_token = ""
    if rate_index < len(rest_values) and metric_tokens:
        additional_token = metric_tokens[-1]
        metric_tokens = metric_tokens[:-1]
    elif len(metric_tokens) >= 2 and metric_tokens[-1] == "-":
        additional_token = metric_tokens[-2]
        metric_tokens = metric_tokens[:-2]
    score_values: list[float] = []
    for value in metric_tokens:
        if value == "-":
            break
        score_value = number_or_none(value)
        if score_value is None:
            break
        score_values.append(float(score_value))
    if len(score_values) < 2:
        return None
    additional_pass = None
    if additional_token and additional_token != "-":
        additional_pass = int_or_none(additional_token)
    avg_score = score_values[0]
    cut_score = score_values[1]
    competition_float = float(competition)
    if not (0 < quota <= 1000 and 0 < competition_float <= 300):
        return None
    if not (0 < avg_score <= 100 and 0 < cut_score <= 100):
        return None
    if additional_pass is not None and not (0 <= additional_pass <= 5000):
        return None
    return {
        "unitName": unit_name,
        "quota": quota,
        "competitionRate": round(competition_float, 2),
        "additionalPass": additional_pass,
        "avgScoreCandidate": number_string(avg_score),
        "cutScoreCandidate": number_string(cut_score),
        "percentileCutCandidate": number_string(cut_score),
        "scoreAvailability": "office_quota_competition_and_score_metric_candidate",
        "metricCount": 2,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": True,
    }


def clean_anyang_campus_result_unit_name(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"^(?:안양|강화|인천강화|\(인천\)|캠퍼스)\s+", "", text)
    text = text.replace("게임컨텐츠학과", "게임콘텐츠학과")
    text = re.sub(r"\(신설\)", "", text)
    text = text.strip(" /,.:;·ㆍ-[]")
    if not text or text in {"안양", "강화", "인천강화", "캠퍼스"}:
        return ""
    if re.search(r"모집단위|모집인원|경쟁률|통계자료|충원인원|추합인원", text):
        return ""
    if not re.search(r"(?:학과|전공|계열)(?:\([^)]{1,12}\))?$", text):
        return ""
    return text[:60]


def clean_anyang_result_section_title(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"^◉\s*", "", text)
    text = re.sub(r"\s*통계자료\s*$", "", text)
    text = re.sub(r"\s*입시\s*결과\s*$", "", text)
    return text.strip()


def anyang_result_track_label(section_title: str, row: dict[str, Any]) -> str:
    title = clean_anyang_result_section_title(section_title)
    source_context = join_values(row.get("sourceCandidateUrls"))
    if "10000015" in source_context and title and not title.startswith("수시"):
        return f"수시 {title}"
    if "10000020" in source_context and title and not title.startswith("정시"):
        return f"정시 {title}"
    return title or "입시결과"


def anyang_2022_2024_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return ""
    return raw_office_text_source(source_path)


def anyang_2022_2024_result_source_year(row: dict[str, Any]) -> int | None:
    if not is_anyang_2022_2024_result_source(row):
        return None
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    for marker, year in ANYANG_2022_2024_RESULT_BBS_YEAR.items():
        if marker in source_context:
            return year
    return None


ANYANG_2025_RESULT_ROW_PATTERN = re.compile(
    r"^\s*"
    r"(?P<label>.+?)"
    r"\s+(?P<quota>\d{1,4})"
    r"\s+(?P<competition>\d{1,3}(?:\.\d+)?)\s*:\s*1"
    r"\s+(?P<avg>\d{1,3}(?:\.\d+)?)"
    r"\s+(?P<cut>\d{1,3}(?:\.\d+)?)"
    r"\s+(?P<additional>\d{1,4}|-)"
    r"\s*$"
)

ANYANG_2025_RESULT_SECTIONS: tuple[tuple[str, str, str, str], ...] = (
    ("2", "na", "정시 일반", "나군 수능위주(일반학생) 통계자료"),
    ("3", "na", "정시 실기", "나군 실기/실적(실기우수자) 통계자료"),
    ("4", "da", "정시 일반", "다군 수능위주(일반학생) 통계자료"),
    ("5", "da", "정시 실기", "다군 실기/실적(실기우수자) 통계자료"),
)


def is_anyang_2025_regular_result_source(row: dict[str, Any]) -> bool:
    source_labels = join_values(row.get("sourceLabels"))
    if "gap_manual_anyang_docs" not in source_labels:
        return False
    if normalize_text(row.get("unvCd")) not in {"0000147", "0000148"}:
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if (
        "extracted-gap-manual-anyang-20260608" not in source_context
        and "enter.anyang.ac.kr" not in source_context
    ):
        return False
    text = normalize_text(anyang_2025_regular_result_source_text(row))
    return bool(
        re.search(r"안양대학교\s*2026\s*학년도\s*정시\s*모집요강", text)
        and re.search(r"2025\s*학년도\s*정시\s*입시결과", text)
        and re.search(r"나군\s*수능위주\s*\(일반학생\)\s*통계자료", text)
        and re.search(r"다군\s*수능위주\s*\(일반학생\)\s*통계자료", text)
    )


def parse_anyang_2025_regular_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = anyang_2025_regular_result_source_text(row)
    if not text:
        return []
    lines = text.splitlines()
    section_starts: list[tuple[int, str, str, str]] = []
    for line_index, line in enumerate(lines):
        normalized = normalize_text(line)
        for section_no, recruitment_group, track_label, title in ANYANG_2025_RESULT_SECTIONS:
            if normalized == f"{section_no} {title}":
                section_starts.append((line_index, recruitment_group, track_label, title))
    entries: list[dict[str, Any]] = []
    for index, (start_index, recruitment_group, track_label, title) in enumerate(section_starts):
        next_start = (
            section_starts[index + 1][0]
            if index + 1 < len(section_starts)
            else len(lines)
        )
        for line_index in range(start_index + 1, next_start):
            if normalize_text(lines[line_index]).startswith("※ 모집군 변경"):
                break
            parsed = parse_anyang_2025_regular_result_line(lines[line_index])
            if parsed is None:
                continue
            unit_name = parsed.pop("unitName")
            entries.append(
                {
                    "unitName": f"{unit_name} / {track_label}",
                    "canonicalCandidate": f"{unit_name}({track_label})",
                    "recruitmentGroup": recruitment_group,
                    "rowIndex": line_index + 1,
                    "parsed": parsed,
                    "sectionTitle": title,
                }
            )
    return entries


def parse_anyang_2025_regular_result_line(line: str) -> dict[str, Any] | None:
    match = ANYANG_2025_RESULT_ROW_PATTERN.match(line)
    if not match:
        return None
    unit_name = clean_anyang_2025_result_unit_name(match.group("label"))
    if not unit_name:
        return None
    quota = int_or_none(match.group("quota"))
    competition = number_or_none(match.group("competition"))
    avg_score = number_or_none(match.group("avg"))
    cut_score = number_or_none(match.group("cut"))
    additional_pass = (
        None
        if match.group("additional") == "-"
        else int_or_none(match.group("additional"))
    )
    if quota is None or competition is None or avg_score is None or cut_score is None:
        return None
    competition_float = float(competition)
    avg_score_float = float(avg_score)
    cut_score_float = float(cut_score)
    if not (0 < quota <= 1000 and 0 < competition_float <= 300):
        return None
    if not (0 < avg_score_float <= 100 and 0 < cut_score_float <= 100):
        return None
    if additional_pass is not None and not (0 <= additional_pass <= 5000):
        return None
    return {
        "unitName": unit_name,
        "quota": quota,
        "competitionRate": round(competition_float, 2),
        "additionalPass": additional_pass,
        "avgScoreCandidate": number_string(avg_score_float),
        "cutScoreCandidate": number_string(cut_score_float),
        "percentileCutCandidate": number_string(cut_score_float),
        "scoreAvailability": "office_quota_competition_and_score_metric_candidate",
        "metricCount": 2,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": True,
    }


def clean_anyang_2025_result_unit_name(value: str) -> str:
    text = normalize_text(value.replace("\f", " "))
    text = re.sub(r"^\(인천\)\s*강화\s+", "", text)
    text = re.sub(r"^(?:안양|\(인천\)|강화|캠퍼스)\s+", "", text)
    text = text.strip(" /,.:;·ㆍ-[]")
    if not text or text in {"안양", "강화", "(인천)", "캠퍼스"}:
        return ""
    if re.search(r"모집단위|모집인원|경쟁률|통계자료|충원인원", text):
        return ""
    if not re.search(r"(?:학과|교육과|어과|학부|전공|계열)(?:\([^)]{1,12}\))?$", text):
        return ""
    return text[:60]


def anyang_2025_regular_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return ""
    return raw_office_text_source(source_path)


def anyang_2025_regular_result_source_year(row: dict[str, Any]) -> int | None:
    if not is_anyang_2025_regular_result_source(row):
        return None
    return 2025


CAU_2025_RESULT_NUMBER_PATTERN = re.compile(
    r"-|\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?"
)

CAU_GENERAL_2025_COLUMN_RANGES: tuple[tuple[str, int, int], ...] = (
    ("ga", 68, 101),
    ("na", 101, 139),
    ("da", 139, 172),
)

CAU_PERFORMANCE_2025_COLUMN_RANGES: tuple[tuple[str, int, int], ...] = (
    ("ga", 116, 153),
    ("na", 158, 196),
)

CAU_GENERAL_RESULT_RANGE_SPECS: dict[int, tuple[tuple[int, str, int, int], ...]] = {
    2024: (
        (2023, "ga", 68, 101),
        (2023, "na", 101, 139),
        (2023, "da", 139, 172),
    ),
    2026: (
        (2025, "ga", 68, 101),
        (2025, "na", 101, 139),
        (2025, "da", 139, 172),
        (2024, "ga", 172, 215),
        (2024, "na", 215, 255),
        (2024, "da", 255, 300),
    ),
}

CAU_PERFORMANCE_RESULT_RANGE_SPECS: dict[int, tuple[tuple[int, str, int, int], ...]] = {
    2024: (
        (2023, "ga", 96, 138),
        (2023, "na", 138, 185),
    ),
    2026: (
        (2025, "ga", 116, 153),
        (2025, "na", 158, 196),
        (2024, "ga", 200, 243),
        (2024, "na", 243, 290),
    ),
}

CAU_UNIT_CONTEXT_TOKENS = {
    "계열",
    "단과대학",
    "학과",
    "전공",
    "소재지",
    "인문",
    "자연",
    "예",
    "체",
    "능",
    "예체능",
    "서울",
    "다빈치",
    "창의ICT",
    "인문대학",
    "사회과학대학",
    "사범대학",
    "경영경제대학",
    "적십자간호대학",
    "자연과학대학",
    "공과대학",
    "창의ICT공과대학",
    "소프트웨어대학",
    "약학대학",
    "의과대학",
    "생명공학대학",
    "예술공학대학",
    "예술대학",
    "체육대학",
}


def is_cau_2025_regular_result_source(row: dict[str, Any]) -> bool:
    source_labels = join_values(row.get("sourceLabels"))
    if "manual_cau_regular_results_docs" not in source_labels:
        return False
    if normalize_text(row.get("unvCd")) != "0000174":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if (
        "extracted-cau-regular-results-0000174-20260613" not in source_context
        and "admission.cau.ac.kr" not in source_context
    ):
        return False
    text = normalize_text(cau_2025_regular_result_source_text(row))
    headline_year = cau_regular_result_headline_year(text)
    return bool(
        headline_year in CAU_GENERAL_RESULT_RANGE_SPECS
        and re.search(r"정시\s*일반전형\s*모집계획", text)
        and re.search(r"정시\s*실기전형\s*모집계획", text)
    )


def parse_cau_2025_regular_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = cau_2025_regular_result_source_text(row)
    if not text:
        return []
    lines = text.splitlines()
    headline_year = cau_regular_result_headline_year(text)
    if headline_year not in CAU_GENERAL_RESULT_RANGE_SPECS:
        return []
    entries: list[dict[str, Any]] = []
    entries.extend(cau_2025_general_result_entries(lines, headline_year))
    entries.extend(cau_2025_performance_result_entries(lines, headline_year))
    return entries


def cau_2025_regular_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return ""
    return raw_office_text_source(source_path)


def cau_2025_regular_result_source_year(row: dict[str, Any]) -> int | None:
    if not is_cau_2025_regular_result_source(row):
        return None
    headline_year = cau_regular_result_headline_year(cau_2025_regular_result_source_text(row))
    if headline_year is None:
        return None
    return headline_year - 1


def cau_regular_result_headline_year(text: str) -> int | None:
    match = re.search(
        r"(20\d{2})\s*학년도\s*중앙대학교\s*정시\s*모집현황\s*및\s*최근\s*2\s*개년\s*입시결과",
        normalize_text(text),
    )
    if not match:
        return None
    year = int_or_none(match.group(1))
    if year is None:
        return None
    return year


JOONGBU_OFFICIAL_HTML_TABLE_PATTERN = re.compile(
    r"<table\b[\s\S]*?</table>",
    re.I,
)

JOONGBU_SUSI_TRACKS: tuple[tuple[str, str], ...] = (
    ("school_life_excellence", "학교생활우수자전형"),
    ("student_record_excellence", "학생부우수자전형"),
    ("regional_talent", "지역인재전형"),
    ("practical_excellence", "실기우수자전형"),
)

JOONGBU_CAMPUS_CANONICALS = {
    "충청국제",
    "충청국제캠퍼스",
    "고양창의",
    "고양창의캠퍼스",
}

JOONGBU_UNIT_NOISE_PATTERN = re.compile(
    r"모집|지원|경쟁률|충원|최종|등록자|평균|최저|전형|구분|캠퍼스|신설|미실시"
)


def is_joongbu_official_html_result_source(row: dict[str, Any]) -> bool:
    if "joongbu_official_html_results_docs" not in join_values(row.get("sourceLabels")):
        return False
    if normalize_text(row.get("unvCd")) != "0000173":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if not (
        "html_table" in join_values(row.get("evidenceTypes"))
        or "html_text_snippet" in join_values(row.get("evidenceTypes"))
    ):
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    return bool(
        "ipsi.joongbu.ac.kr/menu.es" in source_context
        or "extracted-joongbu-official-html-results-20260614" in source_context
    )


def parse_joongbu_official_html_result_entries(
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    year = joongbu_official_html_result_collection_year(row)
    if year not in {2025, 2026}:
        return []
    tables = joongbu_official_html_result_tables(row)
    if not tables:
        return []
    if year == 2026:
        return joongbu_susi_html_result_entries(tables, year)
    return joongbu_regular_html_result_entries(tables, year)


def joongbu_official_html_result_collection_year(row: dict[str, Any]) -> int | None:
    if not is_joongbu_official_html_result_source(row):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if len(unique_years) == 1 else None


def ulsan_2021_official_results_collection_year(row: dict[str, Any]) -> int | None:
    if normalize_text(row.get("unvCd")) != "0000158":
        return None
    if "ulsan_2021_official_results_docs" not in join_values(row.get("sourceLabels")):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if unique_years == [2021] else None


def joongbu_official_html_result_tables(
    row: dict[str, Any],
) -> list[tuple[int, list[list[str]]]]:
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return []
    text = raw_office_text_source(source_path)
    if not text:
        return []
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    tables: list[tuple[int, list[list[str]]]] = []
    for table_index, table_match in enumerate(
        JOONGBU_OFFICIAL_HTML_TABLE_PATTERN.finditer(text),
        start=1,
    ):
        table_rows: list[list[str]] = []
        for row_match in OFFICE_HTML_ROW_PATTERN.finditer(table_match.group(0)):
            cells = [
                clean_office_html_cell(cell)
                for cell in OFFICE_HTML_CELL_PATTERN.findall(row_match.group(1))
            ]
            if any(cells):
                table_rows.append(cells)
        if table_rows:
            tables.append((table_index, table_rows))
    return tables


def joongbu_susi_html_result_entries(
    tables: list[tuple[int, list[list[str]]]],
    year: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for table_index, rows in tables:
        header_text = " ".join(" ".join(row) for row in rows[:4])
        if "학교생활우수자전형" not in header_text or "학생부우수자전형" not in header_text:
            continue
        parent_unit = ""
        for row_index, cells in enumerate(rows[4:], start=4):
            unit_name, offset, parent_unit = joongbu_result_unit_and_offset(
                cells,
                parent_unit,
            )
            if not unit_name:
                continue
            for track_index, (track_id, track_label) in enumerate(JOONGBU_SUSI_TRACKS):
                base = offset + track_index * 6
                parsed = joongbu_susi_result_slice(cells[base : base + 6])
                if parsed is None:
                    continue
                entries.append(
                    {
                        "year": year,
                        "unitName": unit_name,
                        "canonicalCandidate": canonical_name(unit_name),
                        "recruitmentGroup": "none",
                        "sectionId": f"joongbu_{year}_susi_{track_id}",
                        "track": track_label,
                        "tableIndex": table_index,
                        "rowIndex": row_index * 10 + track_index,
                        "parsed": parsed,
                    }
                )
    return entries


def joongbu_regular_html_result_entries(
    tables: list[tuple[int, list[list[str]]]],
    year: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for table_index, rows in tables:
        header_text = " ".join(" ".join(row) for row in rows[:2])
        if "2026 모집군" not in header_text or "수능환산점수" not in header_text:
            continue
        section_id, track_label = joongbu_regular_section_label(rows, year)
        parent_unit = ""
        for row_index, cells in enumerate(rows[2:], start=2):
            (
                unit_name,
                recruitment_group,
                offset,
                parent_unit,
            ) = joongbu_regular_result_unit_group_offset(cells, parent_unit)
            if not unit_name or recruitment_group == "none":
                continue
            parsed = joongbu_regular_result_slice(cells[offset : offset + 10])
            if parsed is None:
                continue
            entries.append(
                {
                    "year": year,
                    "unitName": unit_name,
                    "canonicalCandidate": canonical_name(unit_name),
                    "recruitmentGroup": recruitment_group,
                    "sectionId": section_id,
                    "track": track_label,
                    "tableIndex": table_index,
                    "rowIndex": row_index,
                    "parsed": parsed,
                }
            )
    return entries


def joongbu_regular_section_label(
    rows: list[list[str]],
    year: int,
) -> tuple[str, str]:
    header_text = " ".join(" ".join(row) for row in rows[:2])
    if "300점" in header_text:
        return f"joongbu_{year}_regular_practical_excellence", "실기우수자전형"
    if "800점" in header_text:
        return f"joongbu_{year}_regular_teacher_education", "사범계전형"
    return f"joongbu_{year}_regular_csat_excellence", "수능우수자전형"


def joongbu_result_unit_and_offset(
    cells: list[str],
    parent_unit: str,
) -> tuple[str, int, str]:
    if not cells:
        return "", 0, parent_unit
    index = 1 if joongbu_is_campus_cell(cells[0]) and len(cells) > 1 else 0
    first = joongbu_clean_unit_fragment(cells[index] if index < len(cells) else "")
    second = joongbu_clean_unit_fragment(
        cells[index + 1] if index + 1 < len(cells) else ""
    )
    if not first:
        return "", index + 1, parent_unit
    if second and not joongbu_numeric_or_empty_cell(second):
        parent = first if joongbu_is_parent_unit(first) else parent_unit
        unit = joongbu_join_parent_unit(first, second)
        return unit, index + 2, parent
    if joongbu_is_parent_unit(first):
        return first, index + 1, first
    if parent_unit:
        return joongbu_join_parent_unit(parent_unit, first), index + 1, parent_unit
    return "", index + 1, parent_unit


def joongbu_regular_result_unit_group_offset(
    cells: list[str],
    parent_unit: str,
) -> tuple[str, str, int, str]:
    if not cells:
        return "", "none", 0, parent_unit
    index = 1 if joongbu_is_campus_cell(cells[0]) and len(cells) > 1 else 0
    first = joongbu_clean_unit_fragment(cells[index] if index < len(cells) else "")
    second = joongbu_clean_unit_fragment(
        cells[index + 1] if index + 1 < len(cells) else ""
    )
    third = joongbu_clean_unit_fragment(
        cells[index + 2] if index + 2 < len(cells) else ""
    )
    if not first:
        return "", "none", index + 1, parent_unit
    if joongbu_is_regular_group_cell(second):
        unit = first if joongbu_is_parent_unit(first) else joongbu_join_parent_unit(
            parent_unit,
            first,
        )
        parent = first if joongbu_is_parent_unit(first) else parent_unit
        return unit, joongbu_recruitment_group(second), index + 2, parent
    if second and joongbu_is_regular_group_cell(third):
        unit = joongbu_join_parent_unit(first, second)
        parent = first if joongbu_is_parent_unit(first) else parent_unit
        return unit, joongbu_recruitment_group(third), index + 3, parent
    return "", "none", index + 1, parent_unit


def joongbu_susi_result_slice(cells: list[str]) -> dict[str, Any] | None:
    if len(cells) < 6:
        return None
    quota = joongbu_integer_cell_value(cells[0])
    applicants = joongbu_integer_cell_value(cells[1])
    competition = office_html_competition_cell_value(cells[2])
    if quota is None or applicants is None or competition is None:
        return None
    if not is_consistent_office_html_competition(quota, applicants, competition):
        return None
    additional_pass = joongbu_integer_cell_value(cells[3])
    avg_score = joongbu_grade_score_cell_value(cells[4])
    cut_score = joongbu_grade_score_cell_value(cells[5])
    metric_count = sum(value is not None for value in (avg_score, cut_score))
    return {
        "quota": quota,
        "applicants": applicants,
        "competitionRate": round(competition, 2),
        "additionalPass": additional_pass,
        "avgScoreCandidate": number_string(avg_score) if avg_score is not None else "",
        "cutScoreCandidate": number_string(cut_score) if cut_score is not None else "",
        "percentileCutCandidate": "",
        "scoreAvailability": (
            "office_quota_competition_and_school_record_grade_candidate"
            if metric_count
            else "office_quota_competition_candidate"
        ),
        "metricCount": metric_count,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": metric_count > 0,
    }


def joongbu_regular_result_slice(cells: list[str]) -> dict[str, Any] | None:
    if len(cells) < 10 or "미실시" in " ".join(cells[:4]):
        return None
    quota = joongbu_integer_cell_value(cells[0])
    applicants = joongbu_integer_cell_value(cells[1])
    competition = office_html_competition_cell_value(cells[2])
    if quota is None or applicants is None or competition is None:
        return None
    if not is_consistent_office_html_competition(quota, applicants, competition):
        return None
    additional_pass = joongbu_integer_cell_value(cells[3])
    percentile_scores = [office_html_score_cell_value(cell) for cell in cells[4:8]]
    avg_score = office_html_score_cell_value(cells[8])
    cut_score = office_html_score_cell_value(cells[9])
    metric_count = sum(value is not None for value in (*percentile_scores, avg_score, cut_score))
    return {
        "quota": quota,
        "applicants": applicants,
        "competitionRate": round(competition, 2),
        "additionalPass": additional_pass,
        "avgScoreCandidate": number_string(avg_score) if avg_score is not None else "",
        "cutScoreCandidate": number_string(cut_score) if cut_score is not None else "",
        "percentileCutCandidate": "",
        "scoreAvailability": (
            "office_quota_competition_and_converted_score_candidate"
            if avg_score is not None or cut_score is not None
            else "office_quota_competition_candidate"
        ),
        "metricCount": metric_count,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": avg_score is not None or cut_score is not None,
    }


def joongbu_clean_unit_fragment(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"\s*\(.*$", "", text)
    text = text.strip(" /,.:;·ㆍ-[]()")
    if not text or JOONGBU_UNIT_NOISE_PATTERN.search(text):
        return ""
    if len(text) > 60 or not re.search(r"[가-힣A-Za-z]", text):
        return ""
    return text


def joongbu_join_parent_unit(parent_unit: str, unit_fragment: str) -> str:
    parent = joongbu_clean_unit_fragment(parent_unit)
    fragment = joongbu_clean_unit_fragment(unit_fragment)
    if not fragment:
        return parent
    if not parent or fragment.startswith(parent):
        return fragment
    return f"{parent} {fragment}"


def joongbu_is_campus_cell(value: str) -> bool:
    return canonical_name(value) in JOONGBU_CAMPUS_CANONICALS


def joongbu_is_parent_unit(value: str) -> bool:
    return bool(re.search(r"학과|학부|전공|교육과|자유전공|자율설계", value))


def joongbu_is_regular_group_cell(value: str) -> bool:
    return bool(re.fullmatch(r"[가나다]\s*군", normalize_text(value)))


def joongbu_recruitment_group(value: str) -> str:
    normalized = re.sub(r"\s*군$", "", normalize_text(value))
    return recruitment_group_from_korean(normalized)


def joongbu_numeric_or_empty_cell(value: str) -> bool:
    text = normalize_text(value)
    return bool(
        not text
        or text == "-"
        or joongbu_integer_cell_value(text) is not None
        or office_html_competition_cell_value(text) is not None
        or joongbu_grade_score_cell_value(text) is not None
    )


def joongbu_integer_cell_value(value: str) -> int | None:
    text = normalize_text(value).replace(",", "")
    if text in {"", "-"} or not re.fullmatch(r"\d{1,5}", text):
        return None
    number = int(text)
    if number < 0 or number > 20000:
        return None
    return number


def joongbu_grade_score_cell_value(value: str) -> float | None:
    score = office_html_score_cell_value(value)
    if score is None or not (1 <= score <= 9.99):
        return None
    return score


HALLA_2026_SUSI_SCORE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("halla_2026_susi_student_record_subject", "교과중심"),
    ("halla_2026_susi_student_record_interview", "면접중심"),
    ("halla_2026_susi_regional_talent", "지역인재"),
    ("halla_2026_susi_ungok_talent", "운곡인재"),
)

HALLA_2026_SUSI_UNIT_CORRECTIONS = {
    "미래모블리티공학과": "미래모빌리티공학과",
    "레퍼터공학과": "컴퓨터공학과",
    "IT소프트웨어공학과": "IT소프트웨어학과",
    "쟁도온전시스템전공": "철도운전시스템전공",
    "미디어공고군탄츠학과": "미디어광고콘텐츠학과",
    "사회북지학과": "사회복지학과",
    "호텔학공의식경영학과": "호텔항공외식경영학과",
    "부터디자인학과": "뷰티디자인학과",
    "건축학과(4년제/5년제": "건축학과(4년제/5년제)",
}


KOOKMIN_2026_SUSI_TRACKS: tuple[tuple[str, str], ...] = (
    ("curriculum_excellence", "교과성적우수자"),
    ("kookmin_frontier", "국민프런티어"),
)
KOOKMIN_2026_SUSI_TOKEN_PATTERN = re.compile(
    r"\d{1,3}(?:\.\d+)?\s*:\s*1|-|\d{1,4}(?:\.\d+)?"
)
KOOKMIN_2026_SUSI_LEADING_COLLEGE_PATTERN = re.compile(
    r"^(?:(?:글로벌\s*)?인문·지역\s+|"
    r"(?:사회과학|법과|경상|경영|공과|바이오융합|양자융합|"
    r"소프트웨어\s*융합|건축|조형|체육|미래융합)대학\s+)"
)
KOOKMIN_2026_SUSI_UNIT_SUFFIX_PATTERN = re.compile(
    r"(?:학과|교육과|어과|학부|전공|계열|대학)(?:\[[가-힣A-Za-z0-9]+\])?"
    r"(?:\([A-Za-z0-9가-힣]+\))?$"
)


def is_kookmin_2026_susi_result_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000078":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "competition_rate_table":
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if "kookmin.ac.kr" not in source_context and "국민" not in source_context:
        return False
    section = kookmin_2026_susi_result_section(
        kookmin_2026_susi_result_source_text(row)
    )
    return bool(
        section
        and "2026학년도 교과성적우수자" in section
        and "2026학년도 국민프런티어" in section
    )


def kookmin_2026_susi_result_source_year(row: dict[str, Any]) -> int | None:
    return 2026 if is_kookmin_2026_susi_result_source(row) else None


def parse_kookmin_2026_susi_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    section = kookmin_2026_susi_result_section(
        kookmin_2026_susi_result_source_text(row)
    )
    if not section:
        return []
    entries: list[dict[str, Any]] = []
    for line_index, line in enumerate(section.splitlines(), start=1):
        parsed_line = parse_kookmin_2026_susi_result_line(line)
        if parsed_line is None:
            continue
        unit_name, track_cells = parsed_line
        for track_index, ((track_key, _track_label), cells) in enumerate(
            zip(KOOKMIN_2026_SUSI_TRACKS, track_cells),
            start=1,
        ):
            parsed = parse_kookmin_2026_susi_track_cells(cells)
            if parsed is None:
                continue
            entries.append(
                {
                    "year": 2026,
                    "unitName": unit_name,
                    "canonicalCandidate": canonical_name(unit_name),
                    "sectionId": f"kookmin_2026_susi:{track_key}",
                    "rowIndex": line_index * 10 + track_index,
                    "parsed": parsed,
                }
            )
    return entries


def parse_kookmin_2026_susi_result_line(
    line: str,
) -> tuple[str, list[list[str]]] | None:
    matches = list(KOOKMIN_2026_SUSI_TOKEN_PATTERN.finditer(line))
    if len(matches) < 12:
        return None
    metric_matches = matches[-12:]
    unit_name = kookmin_2026_susi_unit_name(line[: metric_matches[0].start()])
    if not unit_name:
        return None
    tokens = [normalize_text(match.group(0)) for match in metric_matches]
    return unit_name, [tokens[:6], tokens[6:12]]


def parse_kookmin_2026_susi_track_cells(cells: list[str]) -> dict[str, Any] | None:
    if len(cells) < 6:
        return None
    quota = kookmin_2026_susi_integer_cell_value(cells[0])
    competition = kookmin_2026_susi_competition_cell_value(cells[1])
    if quota is None or competition is None:
        return None
    additional_pass = kookmin_2026_susi_integer_cell_value(cells[2])
    best_score = kookmin_2026_susi_grade_cell_value(cells[3])
    avg_score = kookmin_2026_susi_grade_cell_value(cells[4])
    cut_score = kookmin_2026_susi_grade_cell_value(cells[5])
    score_values = [
        value for value in (best_score, avg_score, cut_score) if value is not None
    ]
    if not (0 < quota <= 1000 and 0 < competition <= 300):
        return None
    if additional_pass is not None and not (0 <= additional_pass <= 5000):
        return None
    return {
        "quota": quota,
        "competitionRate": round(float(competition), 2),
        "additionalPass": additional_pass,
        "avgScoreCandidate": number_string(avg_score) if avg_score is not None else "",
        "cutScoreCandidate": number_string(cut_score) if cut_score is not None else "",
        "percentileCutCandidate": "",
        "scoreAvailability": (
            "office_quota_competition_and_score_metric_candidate"
            if score_values
            else "office_quota_competition_candidate"
        ),
        "metricCount": len(score_values),
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": bool(score_values),
    }


def kookmin_2026_susi_result_section(text: str) -> str:
    if not text:
        return ""
    start = text.rfind("2026학년도 수시모집 입시결과")
    if start < 0:
        return ""
    section = text[start:]
    end = section.find("16 국민대학교 약도")
    if end >= 0:
        section = section[:end]
    return section


def kookmin_2026_susi_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is not None:
        text = raw_office_text_source(source_path)
        if text:
            return text
    return office_text_candidate_full_text(row)


def kookmin_2026_susi_unit_name(value: str) -> str:
    text = normalize_text(value)
    text = text.replace("※", " ")
    text = re.sub(r"\s+", " ", text).strip(" /,.:;·ㆍ-[]")
    previous = None
    while previous != text:
        previous = text
        text = KOOKMIN_2026_SUSI_LEADING_COLLEGE_PATTERN.sub("", text).strip()
    text = text.strip(" /,.:;·ㆍ-[]")
    if not text or re.search(r"모집단위|모집인원|경쟁률|예비|최고|평균|최저", text):
        return ""
    if not KOOKMIN_2026_SUSI_UNIT_SUFFIX_PATTERN.search(text):
        return ""
    if len(text) > 70:
        return ""
    return text


def kookmin_2026_susi_integer_cell_value(value: str) -> int | None:
    text = normalize_text(value).replace(",", "")
    if text in {"", "-"} or not re.fullmatch(r"\d{1,5}", text):
        return None
    return int(text)


def kookmin_2026_susi_competition_cell_value(value: str) -> float | None:
    text = normalize_text(value)
    if text in {"", "-"}:
        return None
    match = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)\s*:\s*1", text)
    if not match:
        return None
    competition = number_or_none(match.group(1))
    return float(competition) if competition is not None else None


def kookmin_2026_susi_grade_cell_value(value: str) -> float | None:
    text = normalize_text(value)
    if text in {"", "-"}:
        return None
    score = number_or_none(text)
    if score is None:
        return None
    score_value = float(score)
    if not (1 <= score_value <= 9.99):
        return None
    return score_value


def is_halla_2026_susi_result_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000197":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_ocr_page":
        return False
    if "pdf_page_ocr" not in join_values(row.get("evidenceTypes")):
        return False
    if not halla_2026_susi_has_glm_sidecar(row):
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if "450b232a9f76a9c7" not in source_context and "a_202606010949400" not in source_context:
        return False
    text = normalize_text(halla_2026_susi_result_source_text(row))
    return bool(
        "<table" in text
        and re.search(r"2026\s*학년도\s*수시", text)
        and re.search(r"(입시|일시).{0,8}(결과|급과)", text)
        and re.search(r"최종\s*등록자|75\s*%\s*컷|75\s*%\s*최|75%컷", text)
    )


def parse_halla_2026_susi_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = halla_2026_susi_result_source_text(row)
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    for row_index, cells in enumerate(office_html_table_grid(text)):
        if len(cells) < 5:
            continue
        unit_name = halla_2026_susi_unit_name(cells[0])
        if not unit_name:
            continue
        for metric_index, (section_id, _section_label) in enumerate(
            HALLA_2026_SUSI_SCORE_COLUMNS,
            start=1,
        ):
            if metric_index >= len(cells):
                continue
            score = number_or_none(cells[metric_index])
            if score is None:
                continue
            score_value = float(score)
            if not (1 <= score_value <= 9.99):
                continue
            entries.append(
                {
                    "unitName": unit_name,
                    "canonicalCandidate": canonical_name(unit_name),
                    "recruitmentGroup": "none",
                    "sectionId": section_id,
                    "rowIndex": row_index * 10 + metric_index,
                    "parsed": {
                        "quota": None,
                        "competitionRate": "",
                        "additionalPass": None,
                        "avgScoreCandidate": "",
                        "cutScoreCandidate": number_string(score_value),
                        "percentileCutCandidate": "",
                        "scoreAvailability": "office_score_metric_candidate",
                        "metricCount": 1,
                        "hasQuotaAndCompetition": False,
                        "hasOutcomeScore": True,
                    },
                }
            )
    return entries


def halla_2026_susi_unit_name(value: str) -> str:
    text = clean_office_html_table_unit_name(value)
    text = HALLA_2026_SUSI_UNIT_CORRECTIONS.get(text, text)
    if not re.search(r"학과|학부|전공", text):
        return ""
    return text


def halla_2026_susi_result_source_text(row: dict[str, Any]) -> str:
    source_path = halla_2026_susi_glm_text_path(row)
    if source_path is not None:
        return raw_office_text_source(source_path)
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return ""
    return raw_office_text_source(source_path)


def halla_2026_susi_result_source_year(row: dict[str, Any]) -> int | None:
    if not is_halla_2026_susi_result_source(row):
        return None
    return 2026


def halla_2026_susi_has_glm_sidecar(row: dict[str, Any]) -> bool:
    return halla_2026_susi_glm_text_path(row) is not None


def halla_2026_susi_glm_text_path(row: dict[str, Any]) -> Path | None:
    for value in split_joined(row.get("sourcePaths")):
        path = Path(value)
        candidates = [path, Path.cwd() / path]
        repo_root = cached_repo_root()
        if repo_root is not None:
            candidates.append(repo_root / path)
        for candidate in candidates:
            if candidate.exists() and Path(f"{candidate}.glm.json").exists():
                return candidate
    return None


def cau_2025_general_result_entries(
    lines: list[str],
    headline_year: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    in_section = False
    range_specs = CAU_GENERAL_RESULT_RANGE_SPECS.get(headline_year, ())
    for line_index, line in enumerate(lines, start=1):
        if "정시 일반전형 모집계획" in line:
            in_section = True
            continue
        if in_section and "정시 실기전형 모집계획" in line:
            break
        if not in_section:
            continue
        number_tokens = cau_positioned_number_tokens(line)
        if not number_tokens:
            continue
        for result_year, recruitment_group, start, end in range_specs:
            parsed = cau_parse_general_2025_cluster(number_tokens, start, end)
            if parsed is None:
                continue
            unit_name = cau_result_unit_name(lines, line_index, number_tokens)
            if not unit_name:
                continue
            entries.append(
                {
                    "year": result_year,
                    "unitName": f"{unit_name} / 정시 일반",
                    "canonicalCandidate": f"{unit_name}(정시 일반)",
                    "recruitmentGroup": recruitment_group,
                    "rowIndex": line_index,
                    "sectionId": f"cau_{result_year}_regular_general_result",
                    "sourceConfidence": (
                        f"source_preserving_office_cau_{result_year}_regular_becaus_result_pdf_review"
                    ),
                    "parsed": parsed,
                }
            )
    return entries


def cau_2025_performance_result_entries(
    lines: list[str],
    headline_year: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    in_section = False
    range_specs = CAU_PERFORMANCE_RESULT_RANGE_SPECS.get(headline_year, ())
    for line_index, line in enumerate(lines, start=1):
        if "정시 실기전형 모집계획" in line:
            in_section = True
            continue
        if not in_section:
            continue
        number_tokens = cau_positioned_number_tokens(line)
        if not number_tokens:
            continue
        for result_year, recruitment_group, start, end in range_specs:
            parsed = cau_parse_performance_2025_cluster(number_tokens, start, end)
            if parsed is None:
                continue
            unit_name = cau_result_unit_name(lines, line_index, number_tokens)
            if not unit_name:
                continue
            entries.append(
                {
                    "year": result_year,
                    "unitName": f"{unit_name} / 정시 실기",
                    "canonicalCandidate": f"{unit_name}(정시 실기)",
                    "recruitmentGroup": recruitment_group,
                    "rowIndex": 1000 + line_index,
                    "sectionId": f"cau_{result_year}_regular_performance_result",
                    "sourceConfidence": (
                        f"source_preserving_office_cau_{result_year}_regular_becaus_result_pdf_review"
                    ),
                    "parsed": parsed,
                }
            )
    return entries


def cau_positioned_number_tokens(line: str) -> list[tuple[int, str]]:
    return [
        (match.start(), match.group())
        for match in CAU_2025_RESULT_NUMBER_PATTERN.finditer(line)
    ]


def cau_parse_general_2025_cluster(
    number_tokens: list[tuple[int, str]], start: int, end: int
) -> dict[str, Any] | None:
    tokens = [
        token
        for position, token in number_tokens
        if start <= position < end and token != "-"
    ]
    if len(tokens) < 5:
        return None
    quota = int_or_none(tokens[0].replace(",", ""))
    rollover = int_or_none(tokens[1].replace(",", ""))
    competition = number_or_none(tokens[2])
    additional_rate = number_or_none(tokens[3])
    additional_pass = int_or_none(tokens[4].replace(",", ""))
    if (
        quota is None
        or rollover is None
        or competition is None
        or additional_rate is None
        or additional_pass is None
    ):
        return None
    competition_float = float(competition)
    additional_rate_float = float(additional_rate)
    if not (0 < quota <= 1000 and 0 <= rollover <= quota + 30):
        return None
    if not (0 < competition_float <= 300 and 0 <= additional_rate_float <= 2000):
        return None
    if not (0 <= additional_pass <= 5000):
        return None
    return {
        "quota": quota,
        "competitionRate": round(competition_float, 2),
        "additionalPass": additional_pass,
        "avgScoreCandidate": "",
        "cutScoreCandidate": "",
        "percentileCutCandidate": "",
        "scoreAvailability": "office_quota_competition_candidate",
        "metricCount": 0,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": False,
    }


def cau_parse_performance_2025_cluster(
    number_tokens: list[tuple[int, str]], start: int, end: int
) -> dict[str, Any] | None:
    tokens = [
        token
        for position, token in number_tokens
        if start <= position < end and token != "-"
    ]
    if len(tokens) < 4:
        return None
    quota = int_or_none(tokens[0].replace(",", ""))
    competition = number_or_none(tokens[1])
    fill_rate = number_or_none(tokens[2])
    performance_score = number_or_none(tokens[3])
    if (
        quota is None
        or competition is None
        or fill_rate is None
        or performance_score is None
    ):
        return None
    competition_float = float(competition)
    fill_rate_float = float(fill_rate)
    performance_score_float = float(performance_score)
    if not (0 < quota <= 1000 and 0 < competition_float <= 300):
        return None
    if not (0 <= fill_rate_float <= 2000 and 0 < performance_score_float <= 200):
        return None
    return {
        "quota": quota,
        "competitionRate": round(competition_float, 2),
        "additionalPass": None,
        "avgScoreCandidate": number_string(performance_score_float),
        "cutScoreCandidate": "",
        "percentileCutCandidate": "",
        "scoreAvailability": "office_quota_competition_and_score_metric_candidate",
        "metricCount": 1,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": True,
    }


def cau_result_unit_name(
    lines: list[str], line_index: int, number_tokens: list[tuple[int, str]]
) -> str:
    if not number_tokens:
        return ""
    first_number_position = min(position for position, _token in number_tokens)
    name = cau_clean_unit_name_fragment(lines[line_index - 1][:first_number_position])
    if name and cau_unit_name_needs_nearby_context(name):
        context = cau_nearby_unit_context(lines, line_index)
        if context:
            name = f"{context} {name}"
    return normalize_text(name).strip(" /")


def cau_unit_name_needs_nearby_context(name: str) -> bool:
    if re.search(r"학과|학부|\[전공개방", name):
        return False
    return not any(token.endswith(("과", "부")) for token in name.split())


def cau_nearby_unit_context(lines: list[str], line_index: int) -> str:
    for offset in (-1, 1, -2, 2):
        nearby_index = line_index - 1 + offset
        if nearby_index < 0 or nearby_index >= len(lines):
            continue
        line = lines[nearby_index]
        if cau_positioned_number_tokens(line):
            continue
        context = cau_clean_unit_name_fragment(line)
        if context and re.search(r"학부|학과", context):
            return context
    return ""


def cau_clean_unit_name_fragment(value: str) -> str:
    text = normalize_text(value.replace("\f", " "))
    if not text:
        return ""
    tokens: list[str] = []
    for token in text.split():
        token = token.strip(" /,;:")
        if not token:
            continue
        if token in CAU_UNIT_CONTEXT_TOKENS:
            continue
        if token.endswith("대학"):
            continue
        tokens.append(token)
    if not tokens:
        return ""
    parenthetical_units = [
        token
        for token in tokens
        if re.search(r"(?:학부|학과|학부대학)\(", token)
    ]
    if parenthetical_units:
        return parenthetical_units[-1]
    return normalize_text(" ".join(tokens)).strip(" /")


def is_jnue_result_source(row: dict[str, Any]) -> bool:
    source_labels = join_values(row.get("sourceLabels"))
    if "gap_manual_jnue_docs" not in source_labels:
        return False
    if normalize_text(row.get("unvCd")) != "0000258":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    evidence_types = join_values(row.get("evidenceTypes"))
    if "pdf_snippet" not in evidence_types and "hwp_snippet" not in evidence_types:
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if "jnue.kr" not in source_context and "extracted-gap-manual-jnue-20260608" not in source_context:
        return False
    text = normalize_text(jnue_result_source_text(row))
    return bool(
        re.search(
            r"\d{4}\s*학년도\s*(?:신입생\s*)?(?:수시|정시)\s*모집\s*(?:입학전형\s*)?결과",
            text,
        )
        and re.search(r"입학자\s*현황", text)
        and re.search(r"경쟁률", text)
    )


def parse_jnue_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = normalize_text(jnue_result_source_text(row))
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    entries.extend(jnue_early_result_entries(text))
    entries.extend(jnue_regular_result_entries(text))
    return entries


def jnue_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is not None:
        return raw_office_text_source(source_path)
    return office_text_candidate_full_text(row)


def jnue_result_source_year(row: dict[str, Any]) -> int | None:
    if not is_jnue_result_source(row):
        return None
    text = normalize_text(jnue_result_source_text(row))
    for match in re.finditer(
        r"(\d{4})\s*학년도\s*(?:신입생\s*)?(?:수시|정시)\s*모집\s*(?:입학전형\s*)?결과",
        text,
    ):
        year = int_or_none(match.group(1))
        if year is None or not (RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX):
            continue
        window = text[match.end() : match.end() + 1100]
        if re.search(r"입학자\s*현황", window) and re.search(r"경쟁률", window):
            return year
    return None


def jnue_early_result_entries(text: str) -> list[dict[str, Any]]:
    section = jnue_result_table_section(text, "수시")
    if not section:
        return []
    labels = [
        "교직적성우수자",
        "지역인재선발",
        "국가보훈대상자",
        "다문화가정자녀",
        "농어촌학생",
        "기회균형선발",
        "장애인등대상자",
    ]
    entries: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        parsed = jnue_quota_competition_from_result_section(section, label)
        if parsed is None:
            continue
        entries.append(
            {
                "unitName": f"초등교육과 / 수시 {label}",
                "canonicalCandidate": f"초등교육과(수시 {label})",
                "recruitmentGroup": "none",
                "rowIndex": index,
                "parsed": parsed,
            }
        )
    return entries


def jnue_regular_result_entries(text: str) -> list[dict[str, Any]]:
    section = jnue_result_table_section(text, "정시")
    if not section:
        return []
    score_metrics = jnue_regular_score_metrics(text)
    labels = ["일반학생", "농어촌학생", "기회균형선발"]
    entries: list[dict[str, Any]] = []
    for index, label in enumerate(labels):
        parsed = jnue_quota_competition_from_result_section(section, label)
        if parsed is None:
            continue
        additional_pass, cut_score, avg_score = score_metrics.get(label, (None, "", ""))
        parsed["additionalPass"] = additional_pass
        if cut_score:
            parsed["cutScoreCandidate"] = cut_score
        if avg_score:
            parsed["avgScoreCandidate"] = avg_score
        if cut_score or avg_score:
            parsed["scoreAvailability"] = "office_quota_competition_and_score_metric_candidate"
            parsed["metricCount"] = 1
            parsed["hasOutcomeScore"] = True
        entries.append(
            {
                "unitName": f"초등교육과 / 정시 {label}",
                "canonicalCandidate": f"초등교육과(정시 {label})",
                "recruitmentGroup": "none",
                "rowIndex": 100 + index,
                "parsed": parsed,
            }
        )
    return entries


def jnue_result_table_section(text: str, phase: str) -> str:
    pattern = re.compile(
        rf"\d{{4}}\s*학년도\s*(?:신입생\s*)?{phase}\s*모집\s*(?:입학전형\s*)?결과"
    )
    for match in reversed(list(pattern.finditer(text))):
        window = text[match.end() : match.end() + 2200]
        if not (re.search(r"입학자\s*현황", window) and re.search(r"경쟁률", window)):
            continue
        start = match.start()
        end_match = re.search(r"\s2\.\s*전형별", text[match.end() : match.end() + 2600])
        if end_match:
            return text[start : match.end() + end_match.start()]
        return text[start : match.end() + 2200]
    return ""


def jnue_regular_score_section(text: str) -> str:
    match = re.search(r"2\.\s*전형별\s*수능\s*환산점수\s*현황", text)
    if match is None:
        return ""
    section = text[match.start() : match.start() + 1200]
    end_match = re.search(r"\s3\.\s*전형요소별", section)
    return section[: end_match.start()] if end_match else section


def jnue_regular_score_metrics(text: str) -> dict[str, tuple[int | None, str, str]]:
    metrics: dict[str, tuple[int | None, str, str]] = {}
    section = jnue_regular_score_section(text)
    if not section:
        return jnue_regular_average_score_metrics(text)
    for label in ("일반학생", "농어촌학생", "기회균형선발"):
        match = re.search(
            rf"{re.escape(label)}\s+(\d+)\s+(\d{{2,4}}(?:\.\d+)?)",
            section,
        )
        if match is None:
            dash_match = re.search(rf"{re.escape(label)}\s+(\d+)\s+-", section)
            if dash_match is not None:
                metrics[label] = (int_or_none(dash_match.group(1)), "", "")
            continue
        score = office_html_score_cell_value(match.group(2))
        if score is None:
            continue
        metrics[label] = (int_or_none(match.group(1)), number_string(score), "")
    if metrics:
        return metrics
    return jnue_regular_average_score_metrics(text)


def jnue_regular_average_score_metrics(text: str) -> dict[str, tuple[int | None, str, str]]:
    metrics: dict[str, tuple[int | None, str, str]] = {}
    match = re.search(r"대학수학능력시험\s*성적\s*\(\s*600\s*점\s*만점\s*\)", text)
    if match is None:
        return metrics
    section = text[match.end() : match.end() + 1100]
    end_match = re.search(r"\s[·ㆍ]\s*면접|면접고사\s*성적|\s3\.", section)
    if end_match is not None:
        section = section[: end_match.start()]
    label_aliases = {
        "일반학생": "일반학생",
        "농어촌학생": "농어촌전형",
        "기회균형선발": "기회균형선발",
    }
    for label, source_label in label_aliases.items():
        row_match = re.search(
            rf"{re.escape(source_label)}\s+(?:\d+\s+){{7}}(\d+)\s+(\d{{2,4}}(?:\.\d+)?)",
            section,
        )
        if row_match is None:
            continue
        score = office_html_score_cell_value(row_match.group(2))
        if score is None:
            continue
        metrics[label] = (None, "", number_string(score))
    return metrics


def jnue_quota_competition_from_result_section(
    section: str, label: str
) -> dict[str, Any] | None:
    match = re.search(
        rf"{re.escape(label)}\s+"
        r"(\d{1,3})(?:\d\)|\*)?\s+(\d+)\s+(\d+)\s+(\d+)\s+"
        r"(\d+)\s+(\d+)\s+(\d+)\s+"
        r"(\d+)\s+(\d+)\s+(\d+)\s+"
        r"(\d+(?:\.\d+)?)\s*(?::\s*1)?",
        section,
    )
    if match is None:
        return None
    quota = int_or_none(match.group(1))
    applicants = int_or_none(match.group(4))
    competition = number_or_none(match.group(11))
    if quota is None or applicants is None or competition is None:
        return None
    competition_float = float(competition)
    if not is_consistent_office_html_competition(
        quota, applicants, competition_float
    ):
        return None
    return {
        "quota": quota,
        "applicants": applicants,
        "competitionRate": round(competition_float, 2),
        "additionalPass": None,
        "avgScoreCandidate": "",
        "cutScoreCandidate": "",
        "percentileCutCandidate": "",
        "scoreAvailability": "office_quota_competition_candidate",
        "metricCount": 0,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": False,
    }


def is_cnue_result_source(row: dict[str, Any]) -> bool:
    source_labels = join_values(row.get("sourceLabels"))
    if "gap_manual_cnue_docs" not in source_labels:
        return False
    if normalize_text(row.get("unvCd")) != "0000262":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    evidence_types = join_values(row.get("evidenceTypes"))
    if "pdf_snippet" not in evidence_types and "hwp_snippet" not in evidence_types:
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if "cnue.ac.kr" not in source_context and "extracted-gap-manual-cnue-20260609" not in source_context:
        return False
    text = normalize_text(cnue_result_source_text(row))
    return bool(
        re.search(r"\d{4}\s*학년도\s*춘천교육대학교\s*입학\s*전형\s*결과", text)
        and re.search(r"수시\s*모집|수시\s*경쟁률", text)
        and re.search(r"정시\s*모집|정시\s*경쟁률", text)
        and re.search(r"경쟁률", text)
    )


def parse_cnue_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = normalize_text(cnue_result_source_text(row))
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    entries.extend(cnue_early_result_entries(text))
    entries.extend(cnue_regular_result_entries(text))
    return entries


def cnue_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is not None:
        return raw_office_text_source(source_path)
    return office_text_candidate_full_text(row)


def cnue_result_source_year(row: dict[str, Any]) -> int | None:
    if not is_cnue_result_source(row):
        return None
    text = normalize_text(cnue_result_source_text(row))
    match = re.search(
        r"(\d{4})\s*학년도\s*춘천교육대학교\s*입학\s*전형\s*결과",
        text,
    )
    if match is None:
        return None
    year = int_or_none(match.group(1))
    if year is None or not (RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX):
        return None
    return year


def is_chosun_2021_workbook_result_source(row: dict[str, Any]) -> bool:
    if chosun_2021_workbook_result_collection_year(row) != 2021:
        return False
    if normalize_text(row.get("unvCd")) != "0000172":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in {
        "admission_result_row",
        "competition_rate_row",
    }:
        return False
    if "gap_manual_chosun_docs" not in join_values(row.get("sourceLabels")):
        return False
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return False
    if "admission_result" not in join_values(row.get("sourceLinkRoles")):
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if "i.chosun.ac.kr" not in source_context and "/2021/0000172/" not in source_context:
        return False
    cells = chosun_2021_workbook_preview_cells(row)
    return bool(len(cells) >= 8 and chosun_2021_workbook_unit_name(row))


def chosun_2021_workbook_result_collection_year(row: dict[str, Any]) -> int | None:
    if normalize_text(row.get("unvCd")) != "0000172":
        return None
    if "gap_manual_chosun_docs" not in join_values(row.get("sourceLabels")):
        return None
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    if unique_years != [2021]:
        return None
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourcePaths")),
        ]
    )
    if "/2021/0000172/" not in source_context and "filedown/98" not in source_context:
        return None
    return 2021


def parse_chosun_2021_workbook_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    unit_name = chosun_2021_workbook_unit_name(row)
    if not unit_name:
        return []
    cells = chosun_2021_workbook_preview_cells(row)
    numeric_values = chosun_2021_numeric_values_by_col(row)
    if len(cells) < 8 or not numeric_values:
        return []
    quota = chosun_2021_int_at(numeric_values, 5, minimum=1, maximum=1000)
    applicants = chosun_2021_int_at(numeric_values, 6, minimum=0, maximum=10000)
    competition = chosun_2021_number_at(numeric_values, 8, minimum=0, maximum=300)
    if quota is None or applicants is None or competition is None:
        return []
    competition_float = float(competition)
    if not is_consistent_office_html_competition(
        quota, applicants, competition_float
    ):
        return []
    recruitment_group = recruitment_group_from_korean_text(cells[0])
    sample = office_workbook_source_sample(row)
    row_index = int_or_none(sample.get("rowIndex")) or 0
    period = normalize_text(cells[0])
    regular_layout = "정시" in period or "추가" in period
    if regular_layout:
        avg_score = chosun_2021_score_at(numeric_values, 26)
        cut_score = chosun_2021_score_at(numeric_values, 27)
        fallback_avg = chosun_2021_score_at(numeric_values, 33)
        fallback_cut = chosun_2021_score_at(numeric_values, 35)
        metric_columns = (15, 17, 18, 19, 20, 21, 22, 24, 26, 27, 33, 35)
    else:
        avg_score = chosun_2021_score_at(numeric_values, 33)
        cut_score = chosun_2021_score_at(numeric_values, 35)
        fallback_avg = chosun_2021_score_at(numeric_values, 20)
        fallback_cut = chosun_2021_score_at(numeric_values, 22)
        metric_columns = (16, 18, 19, 20, 22, 23, 25, 26, 28, 33, 35)
    if not avg_score:
        avg_score = fallback_avg
    if not cut_score:
        cut_score = fallback_cut
    additional_pass = chosun_2021_int_at(
        numeric_values,
        14 if regular_layout else 15,
        minimum=0,
        maximum=10000,
    )
    metric_count = sum(1 for column in metric_columns if chosun_2021_score_at(numeric_values, column))
    has_score = bool(avg_score or cut_score)
    return [
        {
            "unitName": unit_name,
            "canonicalCandidate": canonical_name(unit_name),
            "recruitmentGroup": recruitment_group,
            "rowIndex": row_index,
            "parsed": {
                "quota": quota,
                "competitionRate": round(competition_float, 2),
                "additionalPass": additional_pass,
                "avgScoreCandidate": avg_score,
                "cutScoreCandidate": cut_score,
                "percentileCutCandidate": "",
                "scoreAvailability": (
                    "office_quota_competition_and_score_metric_candidate"
                    if has_score
                    else "office_quota_competition_candidate"
                ),
                "metricCount": metric_count,
                "hasQuotaAndCompetition": True,
                "hasOutcomeScore": has_score,
            },
        }
    ]


def chosun_2021_workbook_preview_cells(row: dict[str, Any]) -> list[str]:
    text = normalize_text(
        row.get("textPreview") or row.get("sampleText") or row.get("representativeText")
    )
    return [normalize_text(part) for part in text.split("|") if normalize_text(part)]


def chosun_2021_workbook_unit_name(row: dict[str, Any]) -> str:
    cells = chosun_2021_workbook_preview_cells(row)
    if len(cells) < 4:
        return ""
    unit_name = clean_office_admission_unit_name(cells[3])
    if is_useful_office_admission_unit_name(unit_name):
        return unit_name
    if re.search(r"(?:의예과|치의예과|한의예과|수의예과|약학과)$", unit_name):
        return unit_name
    return ""


def chosun_2021_numeric_values_by_col(row: dict[str, Any]) -> dict[int, str]:
    values: dict[int, str] = {}
    sample = office_workbook_source_sample(row)
    for value in sample.get("numericValues") or []:
        column = int_or_none(value.get("colIndex"))
        if column is None:
            continue
        values[column] = normalize_text(value.get("raw") or value.get("value"))
    return values


def chosun_2021_number_at(
    values: dict[int, str],
    column: int,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> int | float | None:
    raw = normalize_text(values.get(column))
    if not raw or "명이하" in raw:
        return None
    value = number_or_none(raw)
    if value is None:
        return None
    if minimum is not None and float(value) < minimum:
        return None
    if maximum is not None and float(value) > maximum:
        return None
    return value


def chosun_2021_int_at(
    values: dict[int, str],
    column: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int | None:
    value = chosun_2021_number_at(values, column, minimum=minimum, maximum=maximum)
    if value is None:
        return None
    if float(value) != int(float(value)):
        return None
    return int(float(value))


def chosun_2021_score_at(values: dict[int, str], column: int) -> str:
    value = chosun_2021_number_at(values, column, minimum=0, maximum=2000)
    if value is None:
        return ""
    return number_string(value)


def cnue_early_result_entries(text: str) -> list[dict[str, Any]]:
    section = cnue_result_section(
        text,
        [r"1\.\s*수시\s*경쟁률", r"□\s*수시모집\s*◯\s*경쟁률"],
        [r"2\.\s*수시\s*서류평가", r"◯\s*서류평가", r"◯\s*학생부\s*등급"],
    )
    if not section:
        return []
    entries: list[dict[str, Any]] = []
    for index, (label, label_pattern) in enumerate(cnue_early_result_label_patterns()):
        parsed = cnue_early_quota_competition(section, label_pattern)
        if parsed is None:
            continue
        entries.append(
            {
                "unitName": f"초등교육과 / 수시 {label}",
                "canonicalCandidate": f"초등교육과(수시 {label})",
                "recruitmentGroup": "none",
                "rowIndex": index,
                "parsed": parsed,
            }
        )
    return entries


def cnue_regular_result_entries(text: str) -> list[dict[str, Any]]:
    section = cnue_result_section(
        text,
        [r"6\.\s*정시\s*경쟁률", r"□\s*정시모집\s*◯\s*경쟁률"],
        [r"7\.\s*정시\s*수능", r"◯\s*수능성적"],
    )
    if not section:
        return []
    score_section = cnue_result_section(
        text,
        [r"7\.\s*정시\s*수능\s*점수\s*및\s*등급", r"◯\s*수능성적\s*-\s*표준점수"],
        [r"\s-\s*등급", r"8\.\s*기타", r"◯\s*등록\s*통계", r"□\s*기타"],
    )
    score_metrics = cnue_regular_score_metrics(score_section)
    entries: list[dict[str, Any]] = []
    for index, (label, label_pattern) in enumerate(cnue_regular_result_label_patterns()):
        parsed = cnue_regular_quota_competition(section, label_pattern)
        if parsed is None:
            continue
        avg_score, cut_score = score_metrics.get(label, ("", ""))
        if cut_score:
            parsed["avgScoreCandidate"] = avg_score
            parsed["cutScoreCandidate"] = cut_score
            parsed["scoreAvailability"] = "office_quota_competition_and_score_metric_candidate"
            parsed["metricCount"] = 6
            parsed["hasOutcomeScore"] = True
        entries.append(
            {
                "unitName": f"초등교육과 / 정시 {label}",
                "canonicalCandidate": f"초등교육과(정시 {label})",
                "recruitmentGroup": "none",
                "rowIndex": 100 + index,
                "parsed": parsed,
            }
        )
    return entries


def cnue_result_section(text: str, start_patterns: list[str], end_patterns: list[str]) -> str:
    starts: list[re.Match[str]] = []
    for pattern in start_patterns:
        starts.extend(re.finditer(pattern, text))
    if not starts:
        return ""
    start = min(starts, key=lambda match: match.start()).start()
    rest = text[start:]
    end_offsets = [
        match.start()
        for pattern in end_patterns
        for match in [re.search(pattern, rest)]
        if match is not None and match.start() > 0
    ]
    end = min(end_offsets) if end_offsets else min(len(rest), 2600)
    return rest[:end]


def cnue_early_result_label_patterns() -> list[tuple[str, str]]:
    return [
        ("교직적·인성인재", r"교직적\s*[·‧ㆍ⸱∙.]\s*인성인재"),
        ("강원교육인재", r"강원교육인재"),
        ("국가보훈대상자", r"국가보훈대상자"),
        ("다문화가정의 자녀", r"다문화가정의\s*자녀"),
        ("농어촌학생", r"농어촌학생"),
        (
            "기초생활수급자 및 차상위계층",
            r"기초\s*(?:생활수급자\s*및\s*차상위계층|/\s*차상위)",
        ),
        ("특수교육대상자", r"특수교육대상자"),
    ]


def cnue_regular_result_label_patterns() -> list[tuple[str, str]]:
    return [
        ("일반학생", r"일반학생(?:전형)?"),
        ("강원교육인재", r"강원교육인재"),
        ("농어촌학생", r"농어촌학생"),
        (
            "기초생활수급자 및 차상위계층",
            r"기초\s*(?:생활수급자\s*및\s*차상위계층|/\s*차상위)",
        ),
        ("특수교육대상자", r"특수교육대상자"),
    ]


def cnue_early_quota_competition(section: str, label_pattern: str) -> dict[str, Any] | None:
    match = re.search(
        rf"{label_pattern}\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d,]+)\s+(\d+(?:\.\d+)?)",
        section,
    )
    if match is not None:
        return cnue_quota_competition_candidate(match.group(1), match.group(4), match.group(5))
    match = re.search(
        rf"{label_pattern}\s+(\d+)\s+([\d,]+)\s+(\d+(?:\.\d+)?)",
        section,
    )
    if match is None:
        return None
    return cnue_quota_competition_candidate(match.group(1), match.group(2), match.group(3))


def cnue_regular_quota_competition(section: str, label_pattern: str) -> dict[str, Any] | None:
    match = re.search(
        rf"{label_pattern}\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+([\d,]+)\s+"
        r"(\d+(?:\.\d+)?)\s*(?::\s*1)?",
        section,
    )
    if match is not None:
        return cnue_quota_competition_candidate(match.group(3), match.group(6), match.group(7))
    match = re.search(
        rf"{label_pattern}\s+(\d+)\s+([\d,]+)\s+(\d+(?:\.\d+)?)",
        section,
    )
    if match is None:
        return None
    return cnue_quota_competition_candidate(match.group(1), match.group(2), match.group(3))


def cnue_quota_competition_candidate(
    quota_raw: str, applicants_raw: str, competition_raw: str
) -> dict[str, Any] | None:
    quota = int_or_none(normalize_text(quota_raw).replace(",", ""))
    applicants = int_or_none(normalize_text(applicants_raw).replace(",", ""))
    competition = number_or_none(competition_raw)
    if quota is None or applicants is None or competition is None:
        return None
    competition_float = float(competition)
    if not is_consistent_office_html_competition(
        quota, applicants, competition_float
    ):
        return None
    return {
        "quota": quota,
        "applicants": applicants,
        "competitionRate": round(competition_float, 2),
        "additionalPass": None,
        "avgScoreCandidate": "",
        "cutScoreCandidate": "",
        "percentileCutCandidate": "",
        "scoreAvailability": "office_quota_competition_candidate",
        "metricCount": 0,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": False,
    }


def cnue_regular_score_metrics(section: str) -> dict[str, tuple[str, str]]:
    metrics: dict[str, tuple[str, str]] = {}
    if not section:
        return metrics
    score = r"(\d{2,4}(?:\.\d+)?)"
    score_values_pattern = (
        rf"{score}\s+{score}\s+{score}\s+{score}\s+{score}\s+{score}"
    )
    for label, label_pattern in cnue_regular_result_label_patterns():
        label_match = re.search(label_pattern, section)
        if label_match is None:
            continue
        values_raw: tuple[str, ...] | None = None
        prefix = section[max(0, label_match.start() - 180) : label_match.start()]
        score_matches = list(re.finditer(rf"표준\s+{score_values_pattern}", prefix))
        if score_matches:
            score_match = score_matches[-1]
            tail = prefix[score_match.end() :]
            if "등급" in tail or any(
                re.search(other_pattern, tail)
                for _other_label, other_pattern in cnue_regular_result_label_patterns()
            ):
                values_raw = None
            else:
                values_raw = score_match.groups()
        if values_raw is None:
            match = re.search(
                rf"{label_pattern}\s+(?:표준\s+)?{score_values_pattern}",
                section,
            )
            if match is None:
                continue
            values_raw = match.groups()
        values = [office_html_score_cell_value(value) for value in values_raw]
        if any(value is None for value in values):
            continue
        score_values = [value for value in values if value is not None]
        if any(value < 300 or value > 600 for value in score_values):
            continue
        metrics[label] = (number_string(score_values[4]), number_string(score_values[5]))
    return metrics


ICCU_REGULAR_SCORE_SPECS_BY_YEAR: dict[int, list[tuple[str, str, str, int, str, str]]] = {
    2021: [
        ("조형예술학과", "na", "정시", 13, "4.04", "79.85"),
        ("융합디자인학과", "na", "정시", 14, "2.83", "90.67"),
        ("문화콘텐츠학과", "da", "정시", 5, "3.13", "89.75"),
        ("간호학과", "da", "정시", 29, "2.92", "84.09"),
    ],
    2022: [
        ("조형예술학과", "na", "정시", 15, "4.38", "73.13"),
        ("융합디자인학과", "na", "정시", 10, "2.75", "90.82"),
        ("문화콘텐츠학과", "da", "정시", 4, "2.06", "94.13"),
        ("간호학과", "da", "정시", 20, "3.11", "80.83"),
    ],
    2023: [
        ("조형예술학과", "na", "정시", 9, "4.79", "68.05"),
        ("융합디자인학과", "na", "정시", 18, "3.03", "89.24"),
        ("문화콘텐츠학과", "da", "정시", 7, "2.13", "94.31"),
        ("간호학과", "da", "정시", 35, "3.17", "81.67"),
    ],
    2024: [
        ("조형예술학과", "na", "정시", 7, "4.27", "68.00"),
        ("융합디자인학과", "na", "정시", 18, "2.93", "86.43"),
        ("문화콘텐츠학과", "da", "정시", 8, "2.29", "91.00"),
        ("간호학과", "da", "정시", 33, "3.18", "80.92"),
    ],
    2025: [
        ("조형예술학과", "na", "정시", 7, "4.77", "58.90"),
        ("융합디자인학과", "na", "정시(실기)", 4, "3.79", "72.33"),
        ("융합디자인학과", "da", "정시(수능)", 0, "3.33", "77.16"),
        ("문화콘텐츠학과", "da", "정시", 1, "3.17", "80.30"),
        ("간호학과", "da", "정시", 20, "3.19", "80.48"),
    ],
    2026: [
        ("조형예술학과", "na", "정시", 1, "3.75", "77.83"),
        ("융합디자인학과", "na", "정시", 4, "3.54", "82.21"),
        ("문화콘텐츠학과", "da", "정시", 2, "2.38", "92.00"),
        ("간호학과", "da", "정시", 32, "3.23", "79.51"),
        ("자유전공", "da", "정시", 4, "3.5", "82.91"),
    ],
}


def is_iccu_result_source(row: dict[str, Any]) -> bool:
    source_labels = join_values(row.get("sourceLabels"))
    if (
        "manual_iccu_2025_result_docs" not in source_labels
        and "manual_iccu_result_docs" not in source_labels
    ):
        return False
    if normalize_text(row.get("unvCd")) != "0000168":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    if "admission_result" not in join_values(row.get("sourceLinkRoles")):
        return False
    text = iccu_result_source_text(row)
    year = iccu_result_admission_year(text)
    if year not in ICCU_REGULAR_SCORE_SPECS_BY_YEAR:
        return False
    return bool(
        f"{year}학년도 인천가톨릭대학교 신입학" in text
        and "정시모집 경쟁률" in text
        and "최종합격자 평균 성적" in text
    )


def parse_iccu_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = iccu_result_source_text(row)
    if not text:
        return []
    year = iccu_result_admission_year(text)
    if year is None:
        return []
    entries: list[dict[str, Any]] = []
    entries.extend(iccu_regular_competition_entries(text, year))
    entries.extend(iccu_regular_score_entries(text, year))
    return entries


def iccu_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is not None:
        return raw_office_text_source(source_path)
    return office_text_candidate_full_text(row)


def iccu_result_admission_year(text: str) -> int | None:
    match = re.search(r"(20\d{2})학년도\s+인천가톨릭대학교\s+신입학", text)
    if not match:
        return None
    return int_or_none(match.group(1))


def iccu_regular_competition_entries(text: str, year: int) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    regular_section = re.split(
        rf"Ⅱ\.\s*{year}학년도\s+인천가톨릭대학교\s+신입학\s+정시모집\s+경쟁률",
        text,
        maxsplit=1,
    )
    if len(regular_section) != 2:
        return entries
    section = normalize_text(regular_section[1])
    if year in {2021, 2022, 2023, 2024}:
        entries.extend(
            iccu_competition_entries_from_match(
                section,
                re.search(
                    r"일반학생\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1",
                    section,
                ),
                [
                    ("조형예술학과", "na"),
                    ("융합디자인학과", "na"),
                    ("문화콘텐츠학과", "da"),
                    ("간호학과", "da"),
                ],
                row_offset=0,
            )
        )
    if year in {2025, 2026}:
        entries.extend(
            iccu_competition_entries_from_match(
                section,
                re.search(
                    r"일반학생\s*\(\s*실기\s*\)\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1",
                    section,
                ),
                [
                    ("조형예술학과", "na"),
                    ("융합디자인학과", "na"),
                ],
                row_offset=0,
            )
        )
        da_units = [
            ("융합디자인학과", "da"),
            ("문화콘텐츠학과", "da"),
            ("간호학과", "da"),
        ]
        if year == 2026:
            da_units = [
                ("문화콘텐츠학과", "da"),
                ("간호학과", "da"),
                ("자유전공", "da"),
            ]
        entries.extend(
            iccu_competition_entries_from_match(
                section,
                re.search(
                    r"일반학생\s*\(\s*수능\s*\)\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1\s+"
                    r"(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*:\s*1",
                    section,
                ),
                da_units,
                row_offset=10,
            )
        )
    return entries


def iccu_competition_entries_from_match(
    section: str,
    match: re.Match[str] | None,
    units: list[tuple[str, str]],
    row_offset: int,
) -> list[dict[str, Any]]:
    if match is None:
        return []
    values = list(match.groups())
    entries: list[dict[str, Any]] = []
    for index, (unit_name, recruitment_group) in enumerate(units):
        quota = int_or_none(values[index * 3])
        applicants = int_or_none(values[index * 3 + 1])
        competition = number_or_none(values[index * 3 + 2])
        if quota is None or applicants is None or competition is None:
            continue
        competition_float = float(competition)
        if not is_consistent_office_html_competition(
            quota, applicants, competition_float
        ):
            continue
        if unit_name not in section:
            continue
        entries.append(
            {
                "unitName": unit_name,
                "canonicalCandidate": canonical_name(unit_name),
                "recruitmentGroup": recruitment_group,
                "rowIndex": row_offset + index,
                "parsed": {
                    "quota": quota,
                    "applicants": applicants,
                    "competitionRate": round(competition_float, 2),
                    "additionalPass": None,
                    "avgScoreCandidate": "",
                    "cutScoreCandidate": "",
                    "percentileCutCandidate": "",
                    "scoreAvailability": "office_quota_competition_candidate",
                    "metricCount": 0,
                    "hasQuotaAndCompetition": True,
                    "hasOutcomeScore": False,
                },
            }
        )
    return entries


def iccu_regular_score_entries(text: str, year: int) -> list[dict[str, Any]]:
    specs = ICCU_REGULAR_SCORE_SPECS_BY_YEAR.get(year, [])
    entries: list[dict[str, Any]] = []
    for index, (unit_name, recruitment_group, track, additional, grade, percentile) in enumerate(specs):
        if not iccu_score_spec_visible(text, unit_name, track, additional, grade, percentile):
            continue
        percentile_value = number_or_none(percentile)
        if percentile_value is None:
            continue
        entries.append(
            {
                "unitName": unit_name,
                "canonicalCandidate": canonical_name(unit_name),
                "recruitmentGroup": recruitment_group,
                "rowIndex": 100 + index,
                "parsed": {
                    "quota": None,
                    "applicants": None,
                    "competitionRate": "",
                    "additionalPass": additional,
                    "avgScoreCandidate": number_string(percentile_value),
                    "cutScoreCandidate": "",
                    "percentileCutCandidate": number_string(percentile_value),
                    "scoreAvailability": "office_percentile_average_score_metric_candidate",
                    "metricCount": 2,
                    "hasQuotaAndCompetition": False,
                    "hasOutcomeScore": True,
                },
            }
        )
    return entries


def iccu_score_spec_visible(
    text: str,
    unit_name: str,
    track: str,
    additional: int,
    grade: str,
    percentile: str,
) -> bool:
    for match in re.finditer(re.escape(grade), text):
        window = text[max(0, match.start() - 900) : match.start() + 900]
        if track not in window or percentile not in window:
            continue
        if not re.search(rf"(?:^|\s){additional}(?:\s|$)", window):
            continue
        if not iccu_score_unit_visible(window, unit_name):
            continue
        return True
    return False


def iccu_score_unit_visible(window: str, unit_name: str) -> bool:
    if unit_name in window:
        return True
    split_aliases = {
        "조형예술학과": ("조형", "예술", "학과"),
        "융합디자인학과": ("융합", "디자인", "학과"),
        "문화콘텐츠학과": ("문화", "콘텐츠", "학과"),
        "간호학과": ("간호", "학과"),
        "자유전공": ("자유", "전공"),
    }
    tokens = split_aliases.get(unit_name)
    if tokens is None:
        return False
    if not all(token in window for token in tokens):
        return False
    return True


def parse_ginue_regular_results_html_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = normalize_text(row.get("sampleText") or row.get("textPreview"))
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    entries.extend(ginue_regular_quota_entries(text))
    entries.extend(ginue_regular_score_entries(text))
    return entries


def ginue_regular_quota_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pattern = re.compile(
        r"수능\s*\(\s*(일반학생전형|저소득층학생전형)\s*\)\s*\|\s*"
        r"정원\s*[내외]\s*\|\s*"
        r"([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)",
        re.I,
    )
    for row_index, match in enumerate(pattern.finditer(text)):
        track_name = normalize_text(match.group(1))
        unit_name = f"수능 / ( {track_name} )"
        quota = int(match.group(2).replace(",", ""))
        applicants = int(match.group(3).replace(",", ""))
        additional_pass = int(match.group(5).replace(",", ""))
        if quota <= 0:
            continue
        competition_rate = round(applicants / quota, 2)
        if not is_consistent_office_html_competition(quota, applicants, competition_rate):
            continue
        entries.append(
            {
                "unitName": unit_name,
                "canonicalCandidate": f"수능({track_name})",
                "recruitmentGroup": "na",
                "rowIndex": row_index,
                "tripleIndex": 0,
                "parsed": {
                    "quota": quota,
                    "applicants": applicants,
                    "competitionRate": competition_rate,
                    "additionalPass": additional_pass,
                    "avgScoreCandidate": "",
                    "cutScoreCandidate": "",
                    "percentileCutCandidate": "",
                    "scoreAvailability": "office_quota_competition_candidate",
                    "metricCount": 0,
                    "hasQuotaAndCompetition": True,
                    "hasOutcomeScore": False,
                },
            }
        )
    return entries


def ginue_regular_score_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    pattern = re.compile(
        r"수능\s*\(\s*(일반학생전형|저소득층학생전형)\s*\).*?"
        r"최종\s*등록자\s*\|\s*"
        r"(\d{2,4}(?:\.\d+)?)\s*\|\s*(\d{2,4}(?:\.\d+)?)\s*\|\s*(\d{2,4}(?:\.\d+)?)",
        re.I,
    )
    for row_index, match in enumerate(pattern.finditer(text)):
        track_name = normalize_text(match.group(1))
        unit_name = f"수능 / ( {track_name} )"
        top_20 = office_html_score_cell_value(match.group(2))
        average = office_html_score_cell_value(match.group(3))
        lower_20 = office_html_score_cell_value(match.group(4))
        if top_20 is None or average is None or lower_20 is None:
            continue
        entries.append(
            {
                "unitName": unit_name,
                "canonicalCandidate": f"수능({track_name})",
                "recruitmentGroup": "na",
                "rowIndex": row_index,
                "tripleIndex": 0,
                "parsed": {
                    "quota": None,
                    "applicants": None,
                    "competitionRate": "",
                    "additionalPass": None,
                    "avgScoreCandidate": number_string(average),
                    "cutScoreCandidate": number_string(lower_20),
                    "percentileCutCandidate": "",
                    "scoreAvailability": "office_score_metric_candidate",
                    "metricCount": 3,
                    "hasQuotaAndCompetition": False,
                    "hasOutcomeScore": True,
                },
            }
        )
    return entries


def office_html_table_grid(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    rowspans: dict[int, tuple[int, str]] = {}
    for row_match in OFFICE_HTML_ROW_PATTERN.finditer(text):
        cells: list[str] = []
        col_index = 0
        for cell_match in OFFICE_HTML_CELL_WITH_ATTR_PATTERN.finditer(row_match.group(1)):
            while col_index in rowspans:
                remaining, value = rowspans[col_index]
                cells.append(value)
                if remaining <= 1:
                    del rowspans[col_index]
                else:
                    rowspans[col_index] = (remaining - 1, value)
                col_index += 1
            attrs = cell_match.group(1) or ""
            value = clean_office_html_cell(cell_match.group(2))
            colspan = max(1, office_html_span_attr(attrs, "colspan"))
            rowspan = max(1, office_html_span_attr(attrs, "rowspan"))
            for offset in range(colspan):
                cells.append(value)
                if rowspan > 1:
                    rowspans[col_index + offset] = (rowspan - 1, value)
            col_index += colspan
        while col_index in rowspans:
            remaining, value = rowspans[col_index]
            cells.append(value)
            if remaining <= 1:
                del rowspans[col_index]
            else:
                rowspans[col_index] = (remaining - 1, value)
            col_index += 1
        rows.append(cells)
    return rows


def office_html_span_attr(attrs: str, name: str) -> int:
    match = re.search(rf'{name}\s*=\s*["\']?(\d+)["\']?', attrs, re.I)
    if not match:
        return 1
    value = int_or_none(match.group(1))
    return value or 1


def office_text_candidate_full_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is not None:
        source_text = normalized_office_text_source(source_path)
        if source_text:
            return source_text
    return office_workbook_row_text(row)


def clean_office_html_cell(value: str) -> str:
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\xa0", " ")
    return normalize_text(text).strip(" /,.:;·ㆍ-[]()")


def office_html_table_unit_cell(cells: list[str]) -> tuple[int | None, str]:
    fallback: tuple[int | None, str] = (None, "")
    for index, cell in enumerate(cells[:6]):
        unit_name = clean_office_html_table_unit_name(cell)
        if unit_name:
            if re.search(r"학과|학부|전공|계열", unit_name):
                return index, unit_name
            if fallback[0] is None:
                fallback = (index, unit_name)
    if fallback[0] is not None:
        return fallback
    for index, cell in enumerate(cells[:4]):
        unit_name = clean_office_html_table_unit_name(cell)
        if unit_name:
            return index, unit_name
    return None, ""


def clean_office_html_table_unit_name(value: str) -> str:
    text = clean_office_admission_unit_name(value)
    if not text:
        return ""
    if text in {"합계", "학계", "총계"}:
        return ""
    if re.search(
        r"모집|지원|정원|전형|학생부|교과|실기|특기자|농어촌|특성화|장애|대상자|"
        r"전체|가\s*[군균]|나\s*[군균]|다\s*[군균]",
        text,
    ):
        return ""
    if OFFICE_UNIT_NOISE_PATTERN.search(text):
        return ""
    if re.fullmatch(r"[가나다]\s*[군균](?:\s*\(?전체\)?)?", text):
        return ""
    if len(text) < 2 or len(text) > 40:
        return ""
    if not re.search(r"[가-힣A-Za-z]", text):
        return ""
    return text


def office_html_table_recruitment_group(cells: list[str]) -> str:
    context = " ".join(cells)
    if re.search(r"가\s*[군균]", context):
        return "ga"
    if re.search(r"나\s*[군균]", context):
        return "na"
    if re.search(r"다\s*[군균]", context):
        return "da"
    return "none"


DGAU_RESULT_IMAGE_UNIT_NAME_BY_CANONICAL = {
    "간흡실대지인": "건축실내디자인",
    "건축실내다자인전공": "건축실내디자인전공",
    "계인,행롯전공": "게임·웹툰전공",
    "계일해보": "게임·웹툰",
    "계인행롯전공": "게임·웹툰전공",
    "공연용확대술전공": "공연융합예술전공",
    "공영예할메숲전공": "공연융합예술전공",
    "디지털용합다자인전공": "디지털융합디자인전공",
    "디지털용합디자인": "디지털융합디자인",
    "디지털용함지자인전공": "디지털융합디자인전공",
    "메슈실리치료": "예술심리치료",
    "복지&센리상업전공": "복지&심리상담전공",
    "복지센리상업전공": "복지&심리상담전공",
    "상담디자인전공": "산업디자인전공",
    "시작디자인전공": "시각디자인전공",
    "실용물액": "실용음악",
    "실용예약전공": "실용음악전공",
    "실용을앞전공": "실용음악전공",
    "아트&이브비선전공": "아트&이노베이션전공",
    "아트&이노베이선전공": "아트&이노베이션전공",
    "아트이브비선전공": "아트&이노베이션전공",
    "아트이노베이선전공": "아트&이노베이션전공",
    "영상/만화매니에이선전공": "영상/만화애니메이션전공",
    "영상/만화메니메이선전공": "영상/만화애니메이션전공",
    "영상/만화에니메이션": "영상/만화애니메이션",
    "영상만화매니에이선전공": "영상/만화애니메이션전공",
    "영상만화메니메이선전공": "영상/만화애니메이션전공",
    "영상만화에니메이션": "영상/만화애니메이션",
    "예술실리치료전공": "예술심리치료전공",
    "올용스포츠상업전공": "융합스포츠산업전공",
    "원투전공": "게임·웹툰전공",
    "자료전공": "자율전공",
    "청작용합대술전공": "창작융합예술전공",
    "청작용합에송": "창작융합예술",
    "패션코스메탁디자인": "패션코스메틱디자인",
    "패션코스메티디자인전공": "패션코스메틱디자인전공",
    "평면용합에송": "공연융합예술",
    "피근아메타버스전공": "피규어메타버스전공",
}


def is_dgau_result_image_ocr_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000087":
        return False
    source_context = " ".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("sourcePaths")),
            join_values(row.get("rawPaths")),
        ]
    )
    return (
        "ipsi.dgau.ac.kr/result/" in source_context
        and "image_ocr" in join_values(row.get("evidenceTypes"))
        and "competition_rate" in join_values(row.get("sourceLinkRoles"))
    )


def office_html_table_display_unit_name(row: dict[str, Any], unit_name: str) -> str:
    if is_dgau_result_image_ocr_source(row):
        return DGAU_RESULT_IMAGE_UNIT_NAME_BY_CANONICAL.get(
            canonical_name(unit_name),
            unit_name,
        )
    if normalize_text(row.get("unvCd")) != "0000073":
        return unit_name
    canonical = canonical_name(unit_name)
    if re.search(r"(?:복|북)지상(?:담|당).+학부", canonical):
        return "복지상담융합학부"
    if canonical in {"올약학부", "음약학부"}:
        return "음악학부"
    if canonical == "유아교육학":
        return "유아교육과"
    if canonical == "한국어교육과":
        return "한국어교육학과"
    if canonical == "신학과" and unit_name != canonical:
        return "신학과"
    return unit_name


def office_html_table_canonical_candidate(row: dict[str, Any], unit_name: str) -> str:
    if normalize_text(row.get("unvCd")) == "0000073":
        text = canonical_name(unit_name)
        if re.search(r"(?:복|북)지상(?:담|당).+학부", text):
            return "복지상담융합학부"
    return canonical_name(unit_name)


def office_html_table_competition_triples(
    cells: list[str],
) -> list[tuple[int, int, int, float]]:
    triples: list[tuple[int, int, int, float]] = []
    index = 0
    while index + 2 < len(cells):
        quota = office_html_integer_cell_value(cells[index])
        applicants = office_html_integer_cell_value(cells[index + 1])
        competition = office_html_competition_cell_value(cells[index + 2])
        if (
            quota is not None
            and applicants is not None
            and competition is not None
            and is_consistent_office_html_competition(quota, applicants, competition)
        ):
            triples.append((index, quota, applicants, competition))
            index += 3
            continue
        index += 1
    return triples


def office_html_table_score_metrics(cells: list[str], full_text: str) -> dict[str, Any] | None:
    if not (
        re.search(r"최종|등록자|상위\s*\d{2}\s*%|백\s*분\s*위|백분위|전형\s*점수", full_text)
        and re.search(r"평균|상위|컷|cut|점수|백분위", full_text, re.I)
    ):
        return None
    values: list[float] = []
    for cell in cells:
        value = office_html_score_cell_value(cell)
        if value is None:
            continue
        values.append(value)
    if len(values) < 3:
        return None
    score_values = values[:3]
    if any(RECENT_YEAR_MIN <= int(value) <= RECENT_YEAR_MAX for value in score_values if value.is_integer()):
        return None
    if not all(40 <= value <= 1000 for value in score_values):
        return None
    percentile_cut = number_string(score_values[2]) if max(score_values) <= 100 else ""
    return {
        "quota": None,
        "applicants": None,
        "competitionRate": "",
        "additionalPass": None,
        "avgScoreCandidate": number_string(score_values[1]),
        "cutScoreCandidate": number_string(score_values[2]),
        "percentileCutCandidate": percentile_cut or number_string(score_values[2]),
        "scoreAvailability": "office_score_metric_candidate",
        "metricCount": len(values),
        "hasQuotaAndCompetition": False,
        "hasOutcomeScore": True,
    }


def office_html_score_cell_value(value: str) -> float | None:
    text = normalize_text(value)
    if re.fullmatch(r"\d{1,4},\d{1,2}", text):
        text = text.replace(",", ".")
    if not re.fullmatch(r"\d{1,4}(?:\.\d{1,3})?", text):
        return None
    number = float(text)
    if number <= 0 or number > 1000:
        return None
    return number


def office_html_integer_cell_value(value: str) -> int | None:
    text = normalize_text(value)
    if not re.fullmatch(r"\d{1,4}", text):
        return None
    number = int(text)
    if number < 0 or number > 10000:
        return None
    return number


def office_html_competition_cell_value(value: str) -> float | None:
    text = normalize_text(value)
    text = re.sub(r"\s*:\s*1\s*$", "", text)
    if re.fullmatch(r"\d{1,3},\d{1,2}", text):
        text = text.replace(",", ".")
    if not re.fullmatch(r"\d{1,3}(?:\.\d{1,2})?", text):
        return None
    number = float(text)
    if number < 0 or number > 300:
        return None
    return number


def is_consistent_office_html_competition(
    quota: int, applicants: int, competition: float
) -> bool:
    if quota <= 0 or quota > 1000 or applicants < 0 or applicants > 10000:
        return False
    computed = applicants / quota
    return abs(computed - competition) <= max(0.08, abs(competition) * 0.04)


def is_office_historical_outcome_source(row: dict[str, Any]) -> bool:
    role = normalize_text(row.get("evidenceRole"))
    target = normalize_text(row.get("evidenceTarget"))
    if target != "HistoricalOutcome" or role not in OFFICE_HISTORICAL_OUTCOME_ROLES:
        return False
    text = office_workbook_row_text(row)
    if bool(
        OFFICE_OUTCOME_STRONG_CONTEXT.search(text)
        and OFFICE_OUTCOME_TABLE_CONTEXT.search(text)
        and OFFICE_OUTCOME_RESULT_CONTEXT.search(text)
    ):
        return True
    return (
        is_score_bearing_office_workbook_outcome_row(row)
        or is_competition_only_office_workbook_outcome_row(row)
        or is_structured_office_workbook_outcome_row(row)
    )


def is_structured_office_workbook_outcome_row(row: dict[str, Any]) -> bool:
    role = normalize_text(row.get("evidenceRole"))
    if role not in {"admission_result_row", "competition_rate_row"}:
        return False
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return False
    if "admission_result" not in join_values(row.get("sourceLinkRoles")):
        return False
    text = office_workbook_row_text(row)
    if "|" not in text or OFFICE_OUTCOME_ROW_NOISE_CONTEXT.search(text):
        return False
    if not office_historical_outcome_years(row):
        return False
    if not office_outcome_unit_matches(text):
        return False
    numeric_values = office_workbook_numeric_values(row)
    if len(numeric_values) < 2:
        return False
    year_values = {
        int(value["value"])
        for value in numeric_values
        if float(value.get("value") or 0).is_integer()
        and RECENT_YEAR_MIN <= int(value["value"]) <= RECENT_YEAR_MAX
    }
    score_context = OFFICE_OUTCOME_SCORE_CONTEXT.search(text) or bool(
        re.search(r"평균|표준편차|50\s*컷|70\s*컷|등록\s*인원|등록인원", text)
    )
    return bool(year_values or score_context)


def is_score_bearing_office_workbook_outcome_row(row: dict[str, Any]) -> bool:
    role = normalize_text(row.get("evidenceRole"))
    if role not in {"admission_result_row", "competition_rate_row"}:
        return False
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return False
    text = office_workbook_row_text(row)
    if "|" not in text or not OFFICE_OUTCOME_SCORE_CONTEXT.search(text):
        return False
    if not office_historical_outcome_years(row):
        return False
    matches = office_outcome_unit_matches(text)
    for index, (_unit_name, _start, end) in enumerate(matches):
        next_start = matches[index + 1][1] if index + 1 < len(matches) else len(text)
        parsed = parse_office_outcome_segment(text[end:next_start], text)
        if parsed is not None and parsed.get("hasOutcomeScore"):
            return True
    return False


def is_competition_only_office_workbook_outcome_row(row: dict[str, Any]) -> bool:
    role = normalize_text(row.get("evidenceRole"))
    if role not in {"admission_result_row", "competition_rate_row"}:
        return False
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return False
    if is_score_bearing_office_workbook_outcome_row(row):
        return False
    text = office_workbook_row_text(row)
    if "|" not in text or OFFICE_OUTCOME_ROW_NOISE_CONTEXT.search(text):
        return False
    if not all(pattern.search(text) for pattern in OFFICE_OUTCOME_COMPETITION_ROW_HEADER_CONTEXTS):
        return False
    if not office_historical_outcome_years(row):
        return False
    matches = office_outcome_unit_matches(text)
    for index, (_unit_name, _start, end) in enumerate(matches):
        next_start = matches[index + 1][1] if index + 1 < len(matches) else len(text)
        parsed = parse_office_outcome_segment(text[end:next_start], text)
        if parsed is not None and not parsed.get("hasOutcomeScore"):
            return True
    return False


def office_workbook_numeric_values(row: dict[str, Any]) -> list[dict[str, Any]]:
    samples = row.get("sourceSpecificSamples") or []
    best_values: list[dict[str, Any]] = []
    for sample in samples:
        numeric_values = sample.get("numericValues") or []
        cleaned: list[dict[str, Any]] = []
        for value in numeric_values:
            number = number_or_none(value.get("value"))
            if number is None:
                continue
            cleaned.append(
                {
                    "raw": normalize_text(value.get("raw")),
                    "value": float(number),
                    "colIndex": int_or_none(value.get("colIndex")) or 0,
                }
            )
        if len(cleaned) > len(best_values):
            best_values = cleaned
    return best_values


def office_workbook_row_text(row: dict[str, Any]) -> str:
    base_text = normalize_text(
        row.get("sampleText") or row.get("textPreview") or row.get("representativeText")
    )
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        snippet_context = office_text_snippet_context(row)
        if snippet_context:
            if base_text and base_text not in snippet_context:
                return f"{snippet_context} {base_text}"
            return snippet_context
    sample = office_workbook_source_sample(row)
    if not sample:
        return base_text
    parts: list[str] = []
    parts.extend(office_workbook_nearby_context_rows(row))
    for header in sample.get("headerContextRows") or []:
        if not isinstance(header, dict):
            continue
        header_text = normalize_text(header.get("rowText") or join_values(header.get("cells")))
        if header_text:
            parts.append(header_text)
    row_cells = sample.get("filledContextCells") or sample.get("cells") or []
    row_cell_texts = [normalize_text(cell) for cell in row_cells]
    row_text = " | ".join(cell_text for cell_text in row_cell_texts if cell_text)
    if row_text:
        parts.append(row_text)
    reconstructed_text = " ".join(unique_preserve_order(parts))
    if reconstructed_text:
        if base_text and base_text not in reconstructed_text:
            return f"{reconstructed_text} {base_text}"
        return reconstructed_text
    return base_text


def office_text_snippet_context(row: dict[str, Any]) -> str:
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return ""
    sample = office_text_source_sample(row)
    if not sample:
        return ""
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return ""
    source_text = raw_office_text_source(source_path)
    if not source_text:
        return ""
    page_number = int_or_none(sample.get("pageNumber"))
    start_line = int_or_none(sample.get("startLine"))
    end_line = int_or_none(sample.get("endLine"))
    if page_number is None or start_line is None or end_line is None:
        return ""
    pages = source_text.split("\f")
    if page_number < 1 or page_number > len(pages):
        return ""
    lines = pages[page_number - 1].splitlines()
    if not lines:
        return ""
    start_index = max(0, start_line - 1)
    end_index = min(len(lines), end_line + 10)
    return normalize_text(" ".join(lines[start_index:end_index]))


def office_text_source_sample(row: dict[str, Any]) -> dict[str, Any]:
    samples = [sample for sample in row.get("sourceSpecificSamples") or [] if isinstance(sample, dict)]
    if not samples:
        return {}
    return max(
        samples,
        key=lambda sample: (
            int_or_none(sample.get("score")) or 0,
            int_or_none(sample.get("endLine")) or 0,
            -(int_or_none(sample.get("startLine")) or 0),
        ),
    )


def first_existing_office_text_source_path(row: dict[str, Any]) -> Path | None:
    source_key = join_values(row.get("sourcePaths"))
    if source_key in OFFICE_TEXT_SOURCE_PATH_CACHE:
        return OFFICE_TEXT_SOURCE_PATH_CACHE[source_key]
    for value in split_joined(row.get("sourcePaths")):
        path = Path(value)
        candidates = [path, Path.cwd() / path]
        repo_root = cached_repo_root()
        if repo_root is not None:
            candidates.append(repo_root / path)
        for candidate in candidates:
            if candidate.exists():
                OFFICE_TEXT_SOURCE_PATH_CACHE[source_key] = candidate
                return candidate
    OFFICE_TEXT_SOURCE_PATH_CACHE[source_key] = None
    return None


def office_workbook_nearby_context_rows(row: dict[str, Any]) -> list[str]:
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return []
    sample = office_workbook_source_sample(row)
    if normalize_text(sample.get("rowType")) != "data_row":
        return []
    row_index = int_or_none(sample.get("rowIndex"))
    if row_index is None:
        return []
    source_path = first_existing_office_workbook_source_path(row)
    if source_path is None:
        return []
    cache_key = (str(source_path), row_index)
    if cache_key in OFFICE_WORKBOOK_CONTEXT_TEXT_CACHE:
        return OFFICE_WORKBOOK_CONTEXT_TEXT_CACHE[cache_key]
    rows = office_workbook_csv_rows(source_path)
    if not rows:
        OFFICE_WORKBOOK_CONTEXT_TEXT_CACHE[cache_key] = []
        return []
    row_offset = max(0, min(row_index - 1, len(rows) - 1))
    lower_bound = max(0, row_offset - 44)
    context_rows: list[str] = []
    for index in range(row_offset - 1, lower_bound - 1, -1):
        row_text = normalize_text(" | ".join(cell for cell in rows[index] if normalize_text(cell)))
        if not row_text:
            continue
        if ADMISSION_YEAR_CONTEXT_PATTERN.search(row_text):
            context_rows.append(row_text)
            break
        if OFFICE_UNIT_NAME_PATTERN.search(row_text) and len(
            OFFICE_OUTCOME_NUMBER_PATTERN.findall(row_text)
        ) >= 2:
            continue
        if not re.search(
            r"학과|전형|모집\s*인원|모집인원|지원자|지원율|지원률|경쟁률|"
            r"등록자|등록률|환산|등급|점수|평균|cut|예비",
            row_text,
            re.I,
        ):
            continue
        if len(OFFICE_OUTCOME_NUMBER_PATTERN.findall(row_text)) > 6:
            continue
        context_rows.append(row_text)
    result = list(reversed(unique_preserve_order(context_rows)))[:8]
    OFFICE_WORKBOOK_CONTEXT_TEXT_CACHE[cache_key] = result
    return result


def first_existing_office_workbook_source_path(row: dict[str, Any]) -> Path | None:
    source_key = join_values(row.get("sourcePaths"))
    if source_key in OFFICE_WORKBOOK_SOURCE_PATH_CACHE:
        return OFFICE_WORKBOOK_SOURCE_PATH_CACHE[source_key]
    for value in split_joined(row.get("sourcePaths")):
        path = Path(value)
        candidates = [path, Path.cwd() / path]
        repo_root = cached_repo_root()
        if repo_root is not None:
            candidates.append(repo_root / path)
        for candidate in candidates:
            if candidate.exists():
                OFFICE_WORKBOOK_SOURCE_PATH_CACHE[source_key] = candidate
                return candidate
    OFFICE_WORKBOOK_SOURCE_PATH_CACHE[source_key] = None
    return None


def office_workbook_csv_rows(path: Path) -> list[list[str]]:
    cache_key = str(path)
    if cache_key not in OFFICE_WORKBOOK_CONTEXT_ROW_CACHE:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            OFFICE_WORKBOOK_CONTEXT_ROW_CACHE[cache_key] = list(csv.reader(handle))
    return OFFICE_WORKBOOK_CONTEXT_ROW_CACHE[cache_key]


def cached_repo_root() -> Path | None:
    global REPO_ROOT_CACHE
    if REPO_ROOT_CACHE is not None:
        return REPO_ROOT_CACHE
    try:
        REPO_ROOT_CACHE = find_repo_root(Path.cwd())
    except RuntimeError:
        return None
    return REPO_ROOT_CACHE


def office_workbook_source_sample(row: dict[str, Any]) -> dict[str, Any]:
    samples = [sample for sample in row.get("sourceSpecificSamples") or [] if isinstance(sample, dict)]
    if not samples:
        return {}
    return max(
        samples,
        key=lambda sample: (
            len(sample.get("numericValues") or []),
            len(sample.get("filledContextCells") or sample.get("cells") or []),
            len(sample.get("headerContextRows") or []),
        ),
    )


def parse_office_score_only_workbook_outcome_row(row: dict[str, Any]) -> dict[str, Any] | None:
    text = office_workbook_row_text(row)
    if re.search(r"등록\s*인원\s*없음|등록인원\s*없음|성적\s*미공개|미공개", text):
        return None
    numeric_values = office_workbook_numeric_values(row)
    if len(numeric_values) < 2:
        return None
    if any(
        value["value"].is_integer() and RECENT_YEAR_MIN <= int(value["value"]) <= RECENT_YEAR_MAX
        for value in numeric_values
    ):
        return None
    values = office_score_only_metric_values(numeric_values, text)
    if not values:
        return None
    return {
        "quota": None,
        "applicants": None,
        "competitionRate": "",
        "additionalPass": None,
        "avgScoreCandidate": values[0],
        "cutScoreCandidate": values[-1],
        "percentileCutCandidate": values[-1],
        "scoreAvailability": "office_score_metric_candidate",
        "metricCount": len(values),
        "hasQuotaAndCompetition": False,
        "hasOutcomeScore": True,
    }


def office_score_only_metric_values(
    numeric_values: list[dict[str, Any]], text: str
) -> list[str]:
    values = [float(value.get("value") or 0) for value in numeric_values]
    has_mean_std_context = bool(re.search(r"평균", text) and re.search(r"표준편차", text))
    if has_mean_std_context:
        values = values[::2]
    elif not values or values[0] < 90:
        return []
    result: list[str] = []
    for value in values:
        if value < 1 or value > 1000:
            continue
        if value.is_integer() and value in {50, 70} and re.search(r"50\s*컷|70\s*컷", text):
            continue
        if value.is_integer() and "." not in number_string(value) and value <= 20:
            continue
        add_score_value(result, value)
        if len(result) >= 8:
            break
    return result


def office_historical_outcome_years(row: dict[str, Any]) -> list[int]:
    locator_year = office_historical_outcome_locator_year(row)
    if locator_year:
        return [locator_year]
    hanil_year = hanil_application_status_collection_year(row)
    if hanil_year:
        return [hanil_year]
    anyang_2022_2024_year = anyang_2022_2024_result_source_year(row)
    if anyang_2022_2024_year:
        return [anyang_2022_2024_year]
    anyang_2025_year = anyang_2025_regular_result_source_year(row)
    if anyang_2025_year:
        return [anyang_2025_year]
    cau_2025_year = cau_2025_regular_result_source_year(row)
    if cau_2025_year:
        return [cau_2025_year]
    kookmin_2026_susi_year = kookmin_2026_susi_result_source_year(row)
    if kookmin_2026_susi_year:
        return [kookmin_2026_susi_year]
    halla_2026_susi_year = halla_2026_susi_result_source_year(row)
    if halla_2026_susi_year:
        return [halla_2026_susi_year]
    jnue_year = jnue_result_source_year(row)
    if jnue_year:
        return [jnue_year]
    cnue_year = cnue_result_source_year(row)
    if cnue_year:
        return [cnue_year]
    wsu_2026_susi_year = wsu_2026_susi_result_source_year(row)
    if wsu_2026_susi_year:
        return [wsu_2026_susi_year]
    hansei_2026_regular_year = hansei_2026_regular_result_source_year(row)
    if hansei_2026_regular_year:
        return [hansei_2026_regular_year]
    chosun_2021_year = chosun_2021_workbook_result_collection_year(row)
    if chosun_2021_year:
        return [chosun_2021_year]
    ysu_2021_year = ysu_2021_official_results_collection_year(row)
    if ysu_2021_year:
        return [ysu_2021_year]
    ysu_2022_year = ysu_2022_official_results_collection_year(row)
    if ysu_2022_year:
        return [ysu_2022_year]
    yewon_2021_year = yewon_2021_legacy_results_collection_year(row)
    if yewon_2021_year:
        return [yewon_2021_year]
    yewon_2022_year = yewon_2022_legacy_results_collection_year(row)
    if yewon_2022_year:
        return [yewon_2022_year]
    seowon_2021_susi_year = seowon_2021_susi_result_source_year(row)
    if seowon_2021_susi_year:
        return [seowon_2021_susi_year]
    kyonggi_2026_susi_guide_year = kyonggi_2026_susi_guide_result_collection_year(row)
    if kyonggi_2026_susi_guide_year:
        return [kyonggi_2026_susi_guide_year]
    kyonggi_2024_year = kyonggi_2024_official_results_collection_year(row)
    if kyonggi_2024_year:
        return [kyonggi_2024_year]
    kyonggi_2022_year = kyonggi_2022_official_score_collection_year(row)
    if kyonggi_2022_year:
        return [kyonggi_2022_year]
    kyonggi_2025_year = kyonggi_2025_official_results_collection_year(row)
    if kyonggi_2025_year:
        return [kyonggi_2025_year]
    joongbu_official_html_year = joongbu_official_html_result_collection_year(row)
    if joongbu_official_html_year:
        return [joongbu_official_html_year]
    ulsan_2021_official_html_year = ulsan_2021_official_results_collection_year(row)
    if ulsan_2021_official_html_year:
        return [ulsan_2021_official_html_year]
    gwnu_2023_region_subject_year = gwnu_2023_region_subject_image_collection_year(row)
    if gwnu_2023_region_subject_year:
        return [gwnu_2023_region_subject_year]
    gwnu_year = gwnu_regular_results_collection_year(row)
    if gwnu_year:
        return [gwnu_year]
    ginue_year = ginue_regular_results_collection_year(row)
    if ginue_year:
        return [ginue_year]
    scnu_admission_result_year = scnu_admission_result_workbook_collection_year(row)
    if scnu_admission_result_year:
        return [scnu_admission_result_year]
    scnu_competition_year = scnu_competition_results_collection_year(row)
    if scnu_competition_year:
        return [scnu_competition_year]
    text = office_workbook_row_text(row)
    contextual = recent_contextual_years(text)
    if contextual:
        return contextual[:1]
    source_context_year = office_historical_outcome_source_context_year(row)
    if source_context_year:
        return [source_context_year]
    for field_name in ("sourceCandidateUrls", "attachmentUrls", "sourceLabels"):
        contextual = recent_contextual_years(join_values(row.get(field_name)))
        if contextual:
            return contextual[:1]
    detected_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("detectedAdmissionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    if len(set(detected_years)) == 1:
        return list(dict.fromkeys(detected_years))
    return []


def gwnu_regular_results_collection_year(row: dict[str, Any]) -> int | None:
    if "manual_gwnu_regular_results_docs" not in join_values(row.get("sourceLabels")):
        return None
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if len(unique_years) == 1 else None


GWNU_2023_REGION_SUBJECT_UNITS = [
    "중어중문학과",
    "사학과",
    "관광경영학과",
    "도시계획·부동산학과",
    "자치행정학과",
    "수학물리학부",
    "데이터사이언스학과",
    "생물학과",
    "대기환경과학과",
    "식품영양학과",
    "해양바이오식품학과",
    "수산생명의학과",
    "식물생명과학과",
    "환경조경학과",
    "전자공학과",
    "세라믹신소재공학과",
    "신소재금속공학과",
    "건설환경공학과",
    "생명화학공학과",
    "패션디자인학과",
    "치의예과",
    "치위생학과",
    "유아교육과",
    "간호학과",
    "다문화학과",
    "컴퓨터공학과",
]


def gwnu_2023_region_subject_image_collection_year(row: dict[str, Any]) -> int | None:
    if normalize_text(row.get("unvCd")) not in {"0003363", "0003364"}:
        return None
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return None
    if normalize_text(row.get("evidenceRole")) != "admission_result_image_ocr":
        return None
    if "image_ocr" not in join_values(row.get("evidenceTypes")):
        return None
    if "admission_result" not in join_values(row.get("sourceLinkRoles")):
        return None
    source_key = " ".join(
        [
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
            join_values(row.get("sourceCandidateUrls")),
        ]
    )
    if "89696/download.do" not in source_key and "a9a4552bab36e453.do" not in source_key:
        return None
    years = [
        year
        for year in (
            int_or_none(value)
            for value in (
                split_joined(row.get("collectionYears"))
                + split_joined(row.get("detectedAdmissionYears"))
            )
        )
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    if 2023 in years:
        return 2023
    text = office_text_candidate_full_text(row)
    if "2023학년도" in text and "지역교과" in text and "최종 등록자" in text:
        return 2023
    return None


def is_gwnu_2023_region_subject_image_ocr_source(row: dict[str, Any]) -> bool:
    return gwnu_2023_region_subject_image_collection_year(row) == 2023


def parse_gwnu_2023_region_subject_image_ocr_entries(
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    year = gwnu_2023_region_subject_image_collection_year(row)
    if year != 2023:
        return []
    text = office_text_candidate_full_text(row)
    if not text:
        return []
    table_rows = office_html_table_grid(text)
    parsed_rows: list[dict[str, Any]] = []
    for row_index, cells in enumerate(table_rows[1:], start=1):
        parsed = parse_gwnu_2023_region_subject_image_cells(cells)
        if parsed is None:
            continue
        parsed_rows.append(
            {
                "rowIndex": row_index,
                "parsed": parsed,
            }
        )
    if len(parsed_rows) != len(GWNU_2023_REGION_SUBJECT_UNITS):
        return []
    entries: list[dict[str, Any]] = []
    for unit_name, parsed_row in zip(GWNU_2023_REGION_SUBJECT_UNITS, parsed_rows):
        entries.append(
            {
                "year": year,
                "unitName": unit_name,
                "canonicalCandidate": unit_name,
                "recruitmentGroup": "none",
                "sectionId": "gwnu_2023_region_subject_image_ocr",
                "tableIndex": "image_attachment_ocr",
                "rowIndex": parsed_row["rowIndex"],
                "parsed": parsed_row["parsed"],
            }
        )
    return entries


def parse_gwnu_2023_region_subject_image_cells(
    cells: list[str],
) -> dict[str, Any] | None:
    normalized_cells = [normalize_text(cell) for cell in cells]
    for index in range(0, max(0, len(normalized_cells) - 7)):
        quota = gwnu_positive_int_cell(normalized_cells[index], max_value=200)
        competition_rate = office_html_competition_cell_value(normalized_cells[index + 1])
        additional_pass = gwnu_nonnegative_int_cell(
            normalized_cells[index + 2], max_value=500
        )
        entrants = gwnu_positive_int_cell(normalized_cells[index + 3], max_value=500)
        avg_grade = gwnu_grade_cell(normalized_cells[index + 4])
        stddev_grade = gwnu_grade_cell(normalized_cells[index + 5], allow_zero=True)
        top_grade = gwnu_grade_cell(normalized_cells[index + 6])
        bottom_grade = gwnu_grade_cell(normalized_cells[index + 7])
        if (
            quota is None
            or competition_rate is None
            or additional_pass is None
            or entrants is None
            or avg_grade is None
            or stddev_grade is None
            or top_grade is None
            or bottom_grade is None
        ):
            continue
        return {
            "quota": quota,
            "competitionRate": competition_rate,
            "additionalPass": additional_pass,
            "entrants": entrants,
            "avgScoreCandidate": number_string(avg_grade),
            "cutScoreCandidate": number_string(bottom_grade),
            "percentileCutCandidate": "",
            "scoreAvailability": "office_score_metric_candidate",
            "metricCount": 4,
            "subjectMetricCount": 4,
        }
    return None


def gwnu_positive_int_cell(value: str, *, max_value: int) -> int | None:
    parsed = int_or_none(value)
    if parsed is None or parsed <= 0 or parsed > max_value:
        return None
    return parsed


def gwnu_nonnegative_int_cell(value: str, *, max_value: int) -> int | None:
    parsed = int_or_none(value)
    if parsed is None or parsed < 0 or parsed > max_value:
        return None
    return parsed


def gwnu_grade_cell(value: str, *, allow_zero: bool = False) -> float | None:
    parsed = number_or_none(value)
    if parsed is None:
        return None
    score = float(parsed)
    if score < 0 or score > 10:
        return None
    if score == 0 and not allow_zero:
        return None
    return score


def is_gwnu_2021_2022_athletics_score_workbook_source(row: dict[str, Any]) -> bool:
    year = gwnu_regular_results_collection_year(row)
    if year not in {2021, 2022}:
        return False
    if normalize_text(row.get("unvCd")) not in {"0003363", "0003364"}:
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_row":
        return False
    if "01_Sheet_01.csv" not in join_values(row.get("sourcePaths")):
        return False
    text = office_workbook_row_text(row)
    return bool(
        "체육학과 입시결과" in text
        and "평균 점수" in text
        and "80% cut" in text
        and "평균 등급" in text
    )


def parse_gwnu_2021_2022_athletics_score_workbook_entries(
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    year = gwnu_regular_results_collection_year(row)
    if year not in {2021, 2022}:
        return []
    sample = office_workbook_source_sample(row)
    if normalize_text(sample.get("rowType")) != "data_row":
        return []
    cells = [normalize_text(cell) for cell in (sample.get("filledContextCells") or [])]
    if len(cells) < 15:
        return []
    unit_label = normalize_text(cells[3])
    if not unit_label.startswith("체육학과-"):
        return []
    entrants = gwnu_athletics_positive_int_cell(cells[4])
    avg_score = gwnu_athletics_score_cell(cells[5], max_value=1000)
    cut_score = gwnu_athletics_score_cell(cells[9], max_value=1000)
    avg_grade = gwnu_athletics_score_cell(cells[10], max_value=10)
    cut_grade = gwnu_athletics_score_cell(cells[14], max_value=10)
    if entrants is None or avg_score is None or cut_score is None:
        return []
    track = unit_label.split("-", 1)[1].strip() or "전형"
    unit_name = f"체육학과 / {track}"
    metric_count = 2 + int(avg_grade is not None) + int(cut_grade is not None)
    return [
        {
            "year": year,
            "unitName": unit_name,
            "canonicalCandidate": f"체육학과({track})",
            "recruitmentGroup": "none",
            "sectionId": "gwnu_athletics_score_workbook",
            "tableIndex": normalize_text(sample.get("sheetName")) or "Sheet_01",
            "rowIndex": int_or_none(sample.get("rowIndex")) or 0,
            "parsed": {
                "avgScoreCandidate": number_string(avg_score),
                "cutScoreCandidate": number_string(cut_score),
                "percentileCutCandidate": (
                    number_string(cut_grade)
                    if cut_grade is not None
                    else number_string(avg_grade)
                    if avg_grade is not None
                    else ""
                ),
                "scoreAvailability": "office_score_metric_candidate",
                "metricCount": metric_count,
                "subjectMetricCount": int(avg_grade is not None)
                + int(cut_grade is not None),
            },
        }
    ]


def gwnu_athletics_positive_int_cell(value: str) -> int | None:
    parsed = int_or_none(value)
    if parsed is None or parsed <= 0 or parsed > 500:
        return None
    return parsed


def gwnu_athletics_score_cell(value: str, *, max_value: float) -> float | None:
    parsed = number_or_none(value)
    if parsed is None:
        return None
    score = float(parsed)
    if score <= 0 or score > max_value:
        return None
    return score


def scnu_competition_results_collection_year(row: dict[str, Any]) -> int | None:
    if normalize_text(row.get("unvCd")) != "0000020":
        return None
    if "js_download_file_docs" not in join_values(row.get("sourceLabels")):
        return None
    if "competition_rate" not in join_values(row.get("sourceLinkRoles")):
        return None
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return None
    attachment_urls = join_values(row.get("attachmentUrls"))
    if not re.search(r"scnu\.ac\.kr/common/nttFileDownload\.do", attachment_urls):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if len(unique_years) == 1 else None


def scnu_admission_result_workbook_collection_year(row: dict[str, Any]) -> int | None:
    if normalize_text(row.get("unvCd")) != "0000020":
        return None
    if "js_download_file_docs" not in join_values(row.get("sourceLabels")):
        return None
    if "admission_result" not in join_values(row.get("sourceLinkRoles")):
        return None
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return None
    attachment_urls = join_values(row.get("attachmentUrls"))
    if not re.search(r"scnu\.ac\.kr/common/nttFileDownload\.do", attachment_urls):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if len(unique_years) == 1 else None


def is_skuniv_2026_official_result_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000121":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_table":
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    source_text = join_values(
        [
            row.get("sourceLabels"),
            row.get("rawPaths"),
            row.get("sourceCandidateUrls"),
            row.get("attachmentUrls"),
        ]
    )
    if "skuniv_2026_official_results_docs" not in source_text and "skuniv_2026" not in source_text:
        return False
    return "2026" in join_values(row.get("collectionYears") or row.get("detectedAdmissionYears"))


SKUNIV_RESULT_NUMBER_TOKEN = re.compile(r"-|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")
SKUNIV_RESULT_HEADER_PATTERN = re.compile(
    r"모집단위|모집\s*단위|지원\s*비율|최종|예비|Cut|백분위|성적\s*현황|"
    r"학생부|교과|수능|전형$|인원$|번호$",
    re.I,
)


def parse_skuniv_2026_official_result_pdf_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    path = first_existing_office_workbook_source_path(row)
    if path is None:
        return []
    text = raw_office_text_source(path)
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    section_id = "skuniv_2026_result_pdf"
    for line_index, raw_line in enumerate(text.splitlines(), start=1):
        line = normalize_text(raw_line)
        if not line:
            continue
        if "2026학년도 정시" in line:
            section_id = "skuniv_2026_regular_result_pdf"
            continue
        if "논술" in line or "실기우수자" in line:
            section_id = "skuniv_2026_susi_essay_practical_result_pdf"
            continue
        if "교과성적 현황" in line:
            section_id = "skuniv_2026_susi_school_record_result_pdf"
            continue
        parsed = parse_skuniv_2026_official_result_line(line, section_id)
        if parsed is None:
            continue
        parsed["rowIndex"] = line_index
        entries.append(parsed)
    return entries


def parse_skuniv_2026_official_result_line(
    line: str,
    section_id: str,
) -> dict[str, Any] | None:
    token_matches = list(SKUNIV_RESULT_NUMBER_TOKEN.finditer(line))
    if len(token_matches) < 4:
        return None
    for token_index in range(len(token_matches) - 3):
        quota = skuniv_integer_token(token_matches[token_index].group(0))
        applicants = skuniv_integer_token(token_matches[token_index + 1].group(0))
        competition = number_or_none(token_matches[token_index + 2].group(0))
        additional_pass = skuniv_integer_token(token_matches[token_index + 3].group(0))
        if (
            quota is None
            or applicants is None
            or competition is None
            or additional_pass is None
        ):
            continue
        competition_value = float(competition)
        if not skuniv_quota_competition_is_consistent(quota, applicants, competition_value):
            continue
        unit_name = clean_skuniv_2026_unit_name(line[: token_matches[token_index].start()])
        if not unit_name:
            continue
        score_values = [
            float(value)
            for value in (
                number_or_none(match.group(0))
                for match in token_matches[token_index + 4 :]
                if match.group(0) != "-"
            )
            if value is not None and not is_year_like_number(value)
        ]
        parsed = skuniv_2026_score_fields(score_values, section_id)
        return {
            "unitName": unit_name,
            "canonicalCandidate": canonical_name(unit_name),
            "recruitmentGroup": "none",
            "sectionId": section_id,
            "tableIndex": "pdf_text",
            "parsed": {
                "quota": quota,
                "applicants": applicants,
                "competitionRate": round(competition_value, 2),
                "additionalPass": additional_pass,
                **parsed,
            },
        }
    return None


def skuniv_integer_token(value: str) -> int | None:
    if value == "-":
        return None
    parsed = number_or_none(value)
    if parsed is None:
        return None
    number = float(parsed)
    if not number.is_integer():
        return None
    return int(number)


def skuniv_quota_competition_is_consistent(
    quota: int,
    applicants: int,
    competition: float,
) -> bool:
    if quota <= 0 or quota > 1000 or applicants < 0 or applicants > 10000:
        return False
    if competition < 0 or competition > 500:
        return False
    computed = applicants / quota
    return abs(computed - competition) <= max(0.08, abs(competition) * 0.04)


def clean_skuniv_2026_unit_name(value: str) -> str:
    unit = normalize_text(value)
    unit = re.sub(r"^[➀➁➂➃①②③④0-9]+\s*", "", unit)
    unit = re.sub(
        r"^(?:교과|우수자|균형|사회|기여자|기회|군사|학과|농어촌|학생|특성화|고교|"
        r"졸업자|서해|5도|고졸|재직자|계약|학과)\s+",
        "",
        unit,
    )
    unit = unit.strip(" /,.:;·ㆍ-[]")
    if not unit or len(unit) < 2 or len(unit) > 50:
        return ""
    if SKUNIV_RESULT_HEADER_PATTERN.search(unit):
        return ""
    if not re.search(r"[가-힣A-Za-z]", unit):
        return ""
    return unit[:60]


def skuniv_2026_score_fields(score_values: list[float], section_id: str) -> dict[str, Any]:
    high_scores = [value for value in score_values if value >= 10]
    grade_values = [value for value in score_values if 0 < value <= 9.99]
    if section_id == "skuniv_2026_regular_result_pdf":
        total_70 = high_scores[0] if high_scores else None
        total_100 = high_scores[4] if len(high_scores) >= 5 else (high_scores[-1] if high_scores else None)
        return {
            "convertedScore50Cut": "",
            "convertedScore70Cut": number_string(total_70),
            "totalScore": number_string(total_70),
            "percentile70Average": number_string(total_70),
            "avgScoreCandidate": number_string(total_70),
            "cutScoreCandidate": number_string(total_100 or total_70),
            "percentileCutCandidate": number_string(total_100 or total_70),
            "scoreAvailability": (
                "office_skuniv_regular_quota_competition_score_candidate"
                if score_values
                else "office_skuniv_regular_quota_competition_candidate"
            ),
            "metricCount": len(score_values),
            "subjectMetricCount": len(grade_values),
            "hasOutcomeScore": bool(score_values),
        }
    converted_50 = high_scores[0] if high_scores else None
    converted_70 = high_scores[1] if len(high_scores) >= 2 else converted_50
    avg_score = grade_values[0] if grade_values else converted_50
    cut_score = grade_values[1] if len(grade_values) >= 2 else converted_70 or avg_score
    return {
        "convertedScore50Cut": number_string(converted_50),
        "convertedScore70Cut": number_string(converted_70),
        "totalScore": "",
        "percentile70Average": "",
        "avgScoreCandidate": number_string(avg_score),
        "cutScoreCandidate": number_string(cut_score),
        "percentileCutCandidate": number_string(cut_score),
        "scoreAvailability": (
            "office_skuniv_susi_quota_competition_score_candidate"
            if score_values
            else "office_skuniv_susi_quota_competition_candidate"
        ),
        "metricCount": len(score_values),
        "subjectMetricCount": len(grade_values),
        "hasOutcomeScore": bool(score_values),
    }


def ysu_2021_official_results_collection_year(row: dict[str, Any]) -> int | None:
    if "gap_ysu_2021_official_results_docs" not in join_values(row.get("sourceLabels")):
        return None
    if normalize_text(row.get("unvCd")) not in {"0003193", "0003194"}:
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if unique_years == [2021] else None


def ysu_2022_official_results_collection_year(row: dict[str, Any]) -> int | None:
    if "gap_ysu_2022_official_results_docs" not in join_values(row.get("sourceLabels")):
        return None
    if normalize_text(row.get("unvCd")) not in {"0003193", "0003194"}:
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if unique_years == [2022] else None


def is_ysu_2021_susi_result_workbook_source(row: dict[str, Any]) -> bool:
    if "gap_ysu_2021_official_results_docs" not in join_values(row.get("sourceLabels")):
        return False
    if normalize_text(row.get("unvCd")) not in {"0003193", "0003194"}:
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return False
    if "01_수시모집.csv" not in join_values(row.get("sourcePaths")):
        return False
    return ysu_2021_official_results_collection_year(row) == 2021


def is_ysu_2022_susi_result_workbook_source(row: dict[str, Any]) -> bool:
    if "gap_ysu_2022_official_results_docs" not in join_values(row.get("sourceLabels")):
        return False
    if normalize_text(row.get("unvCd")) not in {"0003193", "0003194"}:
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if "workbook_row" not in join_values(row.get("evidenceTypes")):
        return False
    if "01_Sheet1.csv" not in join_values(row.get("sourcePaths")):
        return False
    return ysu_2022_official_results_collection_year(row) == 2022


def parse_ysu_2021_susi_result_workbook_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    return parse_ysu_susi_result_workbook_entries(row, first_metric_column=2)


def parse_ysu_2022_susi_result_workbook_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    return parse_ysu_susi_result_workbook_entries(row, first_metric_column=1)


def parse_ysu_susi_result_workbook_entries(
    row: dict[str, Any],
    *,
    first_metric_column: int,
) -> list[dict[str, Any]]:
    sample = office_workbook_source_sample(row)
    if normalize_text(sample.get("rowType")) != "data_row":
        return []
    cells = [normalize_text(cell) for cell in (sample.get("cells") or [])]
    if len(cells) < 5:
        return []
    unit_name = ysu_2021_susi_result_unit_name(cells)
    if not unit_name:
        return []
    header_rows = sample.get("headerContextRows") or []
    if len(header_rows) < 2:
        return []
    track_cells = [normalize_text(cell) for cell in (header_rows[0].get("cells") or [])]
    metric_cells = [normalize_text(cell) for cell in (header_rows[1].get("cells") or [])]
    tracks = ysu_2021_susi_result_track_by_column(track_cells, len(cells))
    entries: list[dict[str, Any]] = []
    row_index = int_or_none(sample.get("rowIndex")) or 0
    for column, metric in enumerate(metric_cells):
        if column < first_metric_column or "평균" not in metric:
            continue
        track = normalize_text(tracks.get(column))
        if not track or track in {"모집단위", "2022 모집단위", "2021(전년도) 모집단위"}:
            continue
        avg_score = (
            ysu_2021_susi_result_score_cell_value(cells[column])
            if column < len(cells)
            else None
        )
        cut_score = (
            ysu_2021_susi_result_score_cell_value(cells[column + 1])
            if column + 1 < len(cells) and "80" in metric_cells[column + 1]
            else None
        )
        competition_rate = (
            office_html_competition_cell_value(cells[column + 2])
            if column + 2 < len(cells) and "경쟁률" in metric_cells[column + 2]
            else None
        )
        if avg_score is None and cut_score is None:
            continue
        metric_count = int(avg_score is not None) + int(cut_score is not None) + int(
            competition_rate is not None
        )
        entries.append(
            {
                "unitName": unit_name,
                "canonicalCandidate": canonical_name(unit_name),
                "track": track,
                "rowIndex": row_index * 100 + column,
                "parsed": {
                    "quota": None,
                    "applicants": None,
                    "competitionRate": (
                        round(float(competition_rate), 2)
                        if competition_rate is not None
                        else ""
                    ),
                    "additionalPass": None,
                    "avgScoreCandidate": (
                        number_string(avg_score) if avg_score is not None else ""
                    ),
                    "cutScoreCandidate": (
                        number_string(cut_score) if cut_score is not None else ""
                    ),
                    "percentileCutCandidate": (
                        number_string(cut_score) if cut_score is not None else ""
                    ),
                    "scoreAvailability": (
                        "office_competition_and_score_metric_candidate"
                        if competition_rate is not None
                        else "office_score_metric_candidate"
                    ),
                    "metricCount": metric_count,
                    "hasQuotaAndCompetition": False,
                    "hasOutcomeScore": True,
                },
            }
        )
    return entries


def ysu_2021_susi_result_track_by_column(
    track_cells: list[str],
    column_count: int,
) -> dict[int, str]:
    tracks: dict[int, str] = {}
    current_track = ""
    for column in range(column_count):
        value = normalize_text(track_cells[column]) if column < len(track_cells) else ""
        if value:
            current_track = value
        tracks[column] = current_track
    return tracks


def ysu_2021_susi_result_score_cell_value(value: str) -> float | None:
    text = normalize_text(value)
    if not re.fullmatch(r"\d{1,2}(?:\.\d+)?", text):
        return None
    number = number_or_none(text)
    if number is None:
        return None
    numeric = float(number)
    if numeric <= 0 or numeric > 10:
        return None
    return numeric


def ysu_2021_susi_result_unit_name(cells: list[str]) -> str:
    previous_unit = normalize_text(cells[1]) if len(cells) > 1 else ""
    current_unit = normalize_text(cells[0]) if cells else ""
    for value in (previous_unit, current_unit):
        if not value or value in {"신설", "모집단위"}:
            continue
        if re.search(r"신설\s*전형|참고|평균|등급|경쟁률", value):
            continue
        if is_useful_office_admission_unit_name(value):
            return value
    return ""


KYONGGI_2025_SECTION_HEADING_PATTERN = re.compile(r"^\s*\d{1,2}(?:-\d{1,2})?[.,]?\s+")
KYONGGI_2025_DETAIL_TITLE_PATTERN = re.compile(r"2025\s*학년도\s*전형\s*결과\s*상세")
KYONGGI_2025_DECIMAL_PATTERN = re.compile(r"\d{1,3}\.\d+")
KYONGGI_2025_NUMBER_PATTERN = re.compile(r"\d{1,3}(?:\.\d+)?")
KYONGGI_2026_SUSI_GUIDE_APPENDIX_PATTERN = re.compile(
    r"\[별첨\]\s*2026\s*학년도\s*전형\s*결과",
    re.I,
)
KYONGGI_2026_SUSI_GUIDE_HEADING_PATTERN = re.compile(r"^\s*\[수시\]\s*(.+)$")
KYONGGI_SUPPORT_NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9가-힣])\d{1,3}(?:,\d{3})*(?:\.\d+)?%?(?![A-Za-z0-9가-힣])"
)


def is_kyonggi_2026_susi_guide_result_source(row: dict[str, Any]) -> bool:
    if "gap_manual_kyonggi_docs" not in join_values(row.get("sourceLabels")):
        return False
    if normalize_text(row.get("unvCd")) not in {"0000056", "0000058"}:
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    detected_years = {
        int_or_none(value) for value in split_joined(row.get("detectedAdmissionYears"))
    }
    if 2026 not in detected_years:
        return False
    text = kyonggi_2025_official_result_source_text(row)
    if not text:
        return False
    normalized = normalize_text(text)
    return bool(
        KYONGGI_2026_SUSI_GUIDE_APPENDIX_PATTERN.search(normalized)
        and "[수시]" in normalized
        and "최종등록자" in normalized
    )


def parse_kyonggi_2026_susi_guide_result_entries(
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    text = kyonggi_2025_official_result_source_text(row)
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    track = ""
    section_index = 0
    pending_prefix = ""
    for line_index, line in enumerate(text.splitlines()):
        normalized = normalize_text(line)
        heading = KYONGGI_2026_SUSI_GUIDE_HEADING_PATTERN.match(normalized)
        if heading:
            track = kyonggi_2026_susi_guide_track_label(normalized)
            section_index += 1
            pending_prefix = ""
            continue
        if not track:
            continue
        parsed = parse_kyonggi_2026_susi_guide_result_line(line, pending_prefix)
        if parsed is not None:
            unit_name = parsed.pop("unitName")
            entries.append(
                {
                    "year": 2026,
                    "unitName": f"{unit_name} / {track}",
                    "canonicalCandidate": f"{unit_name}({track})",
                    "recruitmentGroup": "none",
                    "track": track,
                    "rowIndex": 202600000 + section_index * 10000 + line_index + 1,
                    "sectionId": f"kyonggi_2026_susi_guide:{track}",
                    "parsed": parsed,
                }
            )
            pending_prefix = ""
            continue
        pending_prefix = kyonggi_2025_pending_unit_prefix(line, pending_prefix)
    return entries


def parse_kyonggi_2026_susi_guide_result_line(
    line: str,
    pending_prefix: str,
) -> dict[str, Any] | None:
    matches = list(KYONGGI_SUPPORT_NUMBER_PATTERN.finditer(line))
    if len(matches) < 9:
        return None
    label = line[: matches[0].start()]
    unit_name = clean_kyonggi_2025_result_unit_name(label, pending_prefix)
    if not unit_name:
        return None
    tokens = [match.group(0) for match in matches]
    quota = int_or_none(tokens[0].replace(",", ""))
    applicants = int_or_none(tokens[1].replace(",", ""))
    competition_rate = number_or_none(tokens[2].replace(",", ""))
    additional_pass = None if tokens[3] == "-" else int_or_none(tokens[3].replace(",", ""))
    if quota is None or applicants is None or competition_rate is None:
        return None
    if quota <= 0 or applicants < 0 or competition_rate <= 0 or competition_rate >= 500:
        return None
    calculated = applicants / quota
    if abs(calculated - competition_rate) > 0.12:
        return None
    if additional_pass is not None and additional_pass < 0:
        return None
    score_tokens = [
        token.replace(",", "")
        for token in tokens[5:]
        if not token.endswith("%") and number_or_none(token.replace(",", "")) is not None
    ]
    score_values = [number_or_none(token) for token in score_tokens]
    score_values = [value for value in score_values if value is not None]
    if len(score_values) < 4:
        return None
    cut50, cut70, cut100, final_avg = score_values[-4:]
    if not all(0 < value <= 100 for value in (cut50, cut70, cut100, final_avg)):
        return None
    return {
        "unitName": unit_name,
        "quota": quota,
        "applicants": applicants,
        "competitionRate": number_string(competition_rate),
        "additionalPass": additional_pass,
        "avgScoreCandidate": number_string(final_avg),
        "cutScoreCandidate": number_string(cut100),
        "percentileCutCandidate": number_string(cut70),
        "scoreAvailability": "office_quota_competition_and_score_metric_candidate",
        "metricCount": len(score_values),
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": True,
    }


def kyonggi_2026_susi_guide_track_label(title: str) -> str:
    text = normalize_text(title)
    text = re.sub(r"^\[수시\]\s*", "", text)
    text = text.strip(" /,.:;·ㆍ-")
    return text or "2026학년도 수시 전형결과"


def is_kyonggi_2022_official_score_source(row: dict[str, Any]) -> bool:
    if "gap_kyonggi_2022_official_score_docs" not in join_values(row.get("sourceLabels")):
        return False
    if normalize_text(row.get("unvCd")) != "0000058":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    text = kyonggi_2025_official_result_source_text(row)
    if not text:
        return False
    normalized = normalize_text(text)
    return bool(
        "2022학년도 정시모집 전형결과" in normalized
        and "수능성적 백분위 환산" in normalized
        and "100% Cut" in normalized
    )


def parse_kyonggi_2022_official_score_entries(
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    text = kyonggi_2025_official_result_source_text(row)
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    track = ""
    recruitment_group = "none"
    section_index = 0
    pending_prefix = ""
    for line_index, line in enumerate(text.splitlines()):
        normalized = normalize_text(line)
        if "수능성적 백분위 환산" in normalized or "최초합격자" in normalized:
            continue
        if re.search(r"(?:전형|실기/실적).*[가나다]\s*(?:,?\s*[가나다]\s*)*군", normalized):
            track = kyonggi_2022_score_track_label(normalized)
            recruitment_group = recruitment_group_from_korean_text(normalized)
            section_index += 1
            pending_prefix = ""
            continue
        if not track:
            continue
        parsed = parse_kyonggi_2022_official_score_line(line, pending_prefix)
        if parsed is not None:
            unit_name = parsed.pop("unitName")
            parsed_recruitment_group = parsed.pop("recruitmentGroup", "")
            entry_recruitment_group = (
                parsed_recruitment_group
                if parsed_recruitment_group and parsed_recruitment_group != "none"
                else recruitment_group
            )
            entries.append(
                {
                    "year": 2022,
                    "unitName": f"{unit_name} / {track}",
                    "canonicalCandidate": f"{unit_name}({track})",
                    "recruitmentGroup": entry_recruitment_group,
                    "track": track,
                    "rowIndex": 202200000 + section_index * 10000 + line_index + 1,
                    "sectionId": f"kyonggi_2022_regular_score:{track}",
                    "parsed": parsed,
                }
            )
            pending_prefix = ""
            continue
        pending_prefix = kyonggi_2022_pending_unit_prefix(line, pending_prefix)
    return entries


def parse_kyonggi_2022_official_score_line(
    line: str,
    pending_prefix: str,
) -> dict[str, Any] | None:
    if re.search(r"미선발|미공개|등록\s*인원\s*없음|최종등록자\s*1명", line):
        return None
    first_score = KYONGGI_2025_DECIMAL_PATTERN.search(line)
    if first_score is None:
        return None
    label = line[: first_score.start()]
    unit_name = clean_kyonggi_2022_score_unit_name(label, pending_prefix)
    if not unit_name:
        return None
    values = [
        float(match.group(0))
        for match in KYONGGI_2025_NUMBER_PATTERN.finditer(line[first_score.start() :])
    ]
    if len(values) < 6:
        return None
    final_high, final_avg, final_cut = values[-3:]
    if not all(0 < value <= 100 for value in (final_high, final_avg, final_cut)):
        return None
    return {
        "unitName": unit_name,
        "quota": None,
        "recruitmentGroup": recruitment_group_from_korean_text(label),
        "competitionRate": "",
        "additionalPass": None,
        "avgScoreCandidate": number_string(final_avg),
        "cutScoreCandidate": number_string(final_cut),
        "percentileCutCandidate": number_string(final_cut),
        "scoreAvailability": "office_score_metric_candidate",
        "metricCount": 3,
        "hasOutcomeScore": True,
    }


def clean_kyonggi_2022_score_unit_name(label: str, pending_prefix: str) -> str:
    text = normalize_text(label)
    text = re.sub(r"^(?:수원|서울)\s+", "", text)
    text = re.sub(r"^(?:가군|나군|다군)\s+", "", text)
    text = re.sub(r"^(?:인문|자연|예체능|사범)\s+", "", text)
    if not text and pending_prefix:
        text = pending_prefix
    return clean_kyonggi_2025_result_unit_name(text, "")


def kyonggi_2022_pending_unit_prefix(line: str, previous_prefix: str) -> str:
    text = normalize_text(line)
    if not text or KYONGGI_2025_DECIMAL_PATTERN.search(text):
        return ""
    if re.search(
        r"최고|평균|cut|모집단위|최종등록자|최초합격자|캠퍼스|계열|수능성적|정시모집",
        text,
        re.I,
    ):
        return ""
    cleaned = clean_kyonggi_2022_score_unit_name(text, "")
    if not cleaned:
        return ""
    if cleaned.endswith("학부") or cleaned.endswith("공학부"):
        return cleaned
    if previous_prefix and previous_prefix.endswith(("학부", "공학부")) and cleaned.endswith("전공"):
        return normalize_text(f"{previous_prefix} {cleaned}")
    if previous_prefix and should_merge_kyonggi_2025_pending_prefix(previous_prefix, cleaned):
        return normalize_text(f"{previous_prefix} {cleaned}")
    return cleaned


def kyonggi_2022_score_track_label(title: str) -> str:
    text = normalize_text(title)
    text = re.sub(r"\s+", " ", text).strip(" /,.:;·ㆍ-")
    return text or "2022학년도 정시모집 전형결과"


def is_kyonggi_2025_official_result_source(row: dict[str, Any]) -> bool:
    if "gap_kyonggi_2025_official_results_docs" not in join_values(row.get("sourceLabels")):
        return False
    if normalize_text(row.get("unvCd")) != "0000058":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    text = kyonggi_2025_official_result_source_text(row)
    if not text:
        return False
    normalized = normalize_text(text)
    return bool(
        re.search(r"전형\s*결과\s*안내\s*자료", normalized)
        and KYONGGI_2025_DETAIL_TITLE_PATTERN.search(normalized)
    )


def parse_kyonggi_2025_official_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = kyonggi_2025_official_result_source_text(row)
    if not text:
        return []
    lines = text.splitlines()
    section_starts: list[tuple[int, str, str, str]] = []
    for line_index, line in enumerate(lines):
        normalized = normalize_text(line)
        if not KYONGGI_2025_DETAIL_TITLE_PATTERN.search(normalized):
            continue
        track = kyonggi_2025_result_track_label(normalized)
        recruitment_group = recruitment_group_from_korean_text(normalized)
        section_starts.append((line_index, recruitment_group, track, normalized))
    entries: list[dict[str, Any]] = []
    for index, (start_index, recruitment_group, track, title) in enumerate(section_starts):
        next_start = len(lines)
        for line_index in range(start_index + 1, len(lines)):
            normalized = normalize_text(lines[line_index])
            if line_index > start_index + 4 and KYONGGI_2025_SECTION_HEADING_PATTERN.match(
                normalized
            ):
                next_start = line_index
                break
        pending_prefix = ""
        for line_index in range(start_index + 1, next_start):
            line = lines[line_index]
            parsed = parse_kyonggi_2025_detail_result_line(line, pending_prefix)
            if parsed is not None:
                unit_name = parsed.pop("unitName")
                parsed_recruitment_group = parsed.pop("recruitmentGroup", "")
                entry_recruitment_group = (
                    parsed_recruitment_group
                    if parsed_recruitment_group and parsed_recruitment_group != "none"
                    else recruitment_group
                )
                entries.append(
                    {
                        "unitName": f"{unit_name} / {track}",
                        "canonicalCandidate": f"{unit_name}({track})",
                        "recruitmentGroup": entry_recruitment_group,
                        "track": track,
                        "rowIndex": (index + 1) * 10000 + line_index + 1,
                        "sectionTitle": title,
                        "parsed": parsed,
                    }
                )
                pending_prefix = ""
                continue
            pending_prefix = kyonggi_2025_pending_unit_prefix(line, pending_prefix)
    entries.extend(parse_kyonggi_2023_three_year_result_entries(lines))
    entries.extend(parse_kyonggi_support_result_entries(lines))
    return entries


def parse_kyonggi_2023_three_year_result_entries(
    lines: list[str],
) -> list[dict[str, Any]]:
    section_starts: list[tuple[int, str, str, str]] = []
    for line_index, line in enumerate(lines):
        normalized = normalize_text(line)
        if "3개년 전형결과" not in normalized:
            continue
        if "2023학년도" not in "\n".join(lines[line_index : line_index + 8]):
            continue
        track = kyonggi_three_year_result_track_label(normalized)
        recruitment_group = recruitment_group_from_korean_text(normalized)
        section_starts.append((line_index, recruitment_group, track, normalized))

    entries: list[dict[str, Any]] = []
    for index, (start_index, recruitment_group, track, title) in enumerate(section_starts):
        next_start = len(lines)
        for line_index in range(start_index + 1, len(lines)):
            normalized = normalize_text(lines[line_index])
            if line_index > start_index + 4 and KYONGGI_2025_SECTION_HEADING_PATTERN.match(
                normalized
            ):
                next_start = line_index
                break
        pending_prefix = ""
        for line_index in range(start_index + 1, next_start):
            line = lines[line_index]
            parsed = parse_kyonggi_2023_three_year_result_line(line, pending_prefix)
            if parsed is not None:
                unit_name = parsed.pop("unitName")
                parsed_recruitment_group = parsed.pop("recruitmentGroup", "")
                entry_recruitment_group = (
                    parsed_recruitment_group
                    if parsed_recruitment_group and parsed_recruitment_group != "none"
                    else recruitment_group
                )
                entries.append(
                    {
                        "year": 2023,
                        "unitName": f"{unit_name} / {track}",
                        "canonicalCandidate": f"{unit_name}({track})",
                        "recruitmentGroup": entry_recruitment_group,
                        "track": track,
                        "rowIndex": 202300000 + (index + 1) * 10000 + line_index + 1,
                        "sectionTitle": title,
                        "sectionId": f"kyonggi_2023_three_year:{track}",
                        "sourceConfidence": (
                            "source_preserving_office_kyonggi_2023_three_year_result_pdf_review"
                        ),
                        "parsed": parsed,
                    }
                )
                pending_prefix = ""
                continue
            pending_prefix = kyonggi_2025_pending_unit_prefix(line, pending_prefix)
    return entries


def parse_kyonggi_2023_three_year_result_line(
    line: str,
    pending_prefix: str,
) -> dict[str, Any] | None:
    if re.search(r"미선발|통합선발|미공개|등록\s*인원\s*없음|최종등록자\s*1명", line):
        return None
    first_score = KYONGGI_2025_DECIMAL_PATTERN.search(line)
    if first_score is None:
        return None
    label = line[: first_score.start()]
    values = [
        float(match.group(0))
        for match in KYONGGI_2025_NUMBER_PATTERN.finditer(line[first_score.start() :])
    ]
    if len(values) < 15:
        return None
    line_recruitment_group = recruitment_group_from_korean_text(label)
    unit_name = clean_kyonggi_2025_result_unit_name(label, pending_prefix)
    if not unit_name:
        return None
    final_high, final_avg, cut50, cut70, cut100 = values[-5:]
    final_values = [final_high, final_avg, cut50, cut70, cut100]
    if not all(0 < value <= 100 for value in final_values):
        return None
    return {
        "unitName": unit_name,
        "quota": None,
        "applicants": None,
        "recruitmentGroup": line_recruitment_group,
        "competitionRate": "",
        "additionalPass": None,
        "avgScoreCandidate": number_string(final_avg),
        "cutScoreCandidate": number_string(cut100),
        "percentileCutCandidate": number_string(cut70),
        "scoreAvailability": "office_score_metric_candidate",
        "metricCount": 5,
        "hasQuotaAndCompetition": False,
        "hasOutcomeScore": True,
    }


def parse_kyonggi_support_result_entries(lines: list[str]) -> list[dict[str, Any]]:
    section_starts: list[tuple[int, str, str, str, bool]] = []
    for line_index, line in enumerate(lines):
        normalized = normalize_text(line)
        if "지원결과" not in normalized and "경쟁률 및 등록결과" not in normalized:
            continue
        is_three_year = "3개년 지원결과" in normalized
        is_2025_only = bool(
            re.search(r"2025\s*학년도\s*(?:경쟁률\s*및\s*등록결과|지원결과)", normalized)
        )
        if not is_three_year and not is_2025_only:
            continue
        if is_three_year and "2023학년도" not in "\n".join(lines[line_index : line_index + 8]):
            continue
        track = kyonggi_support_result_track_label(normalized)
        recruitment_group = recruitment_group_from_korean_text(normalized)
        section_starts.append((line_index, recruitment_group, track, normalized, is_three_year))

    entries: list[dict[str, Any]] = []
    for index, (start_index, recruitment_group, track, title, is_three_year) in enumerate(
        section_starts
    ):
        next_start = len(lines)
        for line_index in range(start_index + 1, len(lines)):
            normalized = normalize_text(lines[line_index])
            if line_index > start_index + 4 and KYONGGI_2025_SECTION_HEADING_PATTERN.match(
                normalized
            ):
                next_start = line_index
                break
        pending_prefix = ""
        years = [2025, 2024, 2023] if is_three_year else [2025]
        for line_index in range(start_index + 1, next_start):
            line = lines[line_index]
            parsed = parse_kyonggi_support_result_line(line, pending_prefix, years)
            if parsed:
                unit_name = parsed.pop("unitName")
                parsed_recruitment_group = parsed.pop("recruitmentGroup", "")
                entry_recruitment_group = (
                    parsed_recruitment_group
                    if parsed_recruitment_group and parsed_recruitment_group != "none"
                    else recruitment_group
                )
                for parsed_group in parsed.pop("groups"):
                    year = parsed_group["year"]
                    if year not in {2023, 2025}:
                        continue
                    entries.append(
                        {
                            "year": year,
                            "unitName": f"{unit_name} / {track}",
                            "canonicalCandidate": f"{unit_name}({track})",
                            "recruitmentGroup": entry_recruitment_group,
                            "track": track,
                            "rowIndex": year * 100000
                            + (index + 1) * 10000
                            + line_index
                            + 1,
                            "sectionTitle": title,
                            "sectionId": f"kyonggi_{year}_support_result:{track}",
                            "sourceConfidence": (
                                f"source_preserving_office_kyonggi_{year}_support_result_pdf_review"
                            ),
                            "parsed": {
                                "quota": parsed_group["quota"],
                                "applicants": parsed_group["applicants"],
                                "competitionRate": parsed_group["competitionRate"],
                                "additionalPass": parsed_group.get("additionalPass"),
                                "avgScoreCandidate": None,
                                "cutScoreCandidate": None,
                                "percentileCutCandidate": None,
                                "scoreAvailability": "office_quota_competition_candidate",
                                "metricCount": 0,
                                "hasQuotaAndCompetition": True,
                                "hasOutcomeScore": False,
                            },
                        }
                    )
                pending_prefix = ""
                continue
            pending_prefix = kyonggi_2025_pending_unit_prefix(line, pending_prefix)
    return entries


def parse_kyonggi_support_result_line(
    line: str,
    pending_prefix: str,
    years: list[int],
) -> dict[str, Any] | None:
    matches = list(KYONGGI_SUPPORT_NUMBER_PATTERN.finditer(line))
    if not matches:
        return None
    label = line[: matches[0].start()]
    line_recruitment_group = recruitment_group_from_korean_text(label)
    unit_name = clean_kyonggi_2025_result_unit_name(label, pending_prefix)
    if not unit_name:
        return None
    tokens = [match.group(0) for match in matches]
    groups = parse_kyonggi_support_result_groups(tokens, years)
    if not groups:
        return None
    return {
        "unitName": unit_name,
        "recruitmentGroup": line_recruitment_group,
        "groups": groups,
    }


def parse_kyonggi_support_result_groups(
    tokens: list[str],
    years: list[int],
) -> list[dict[str, Any]]:
    has_csat_min_rate = any(token.endswith("%") for token in tokens)
    group_width = 5 if has_csat_min_rate else 4
    groups: list[dict[str, Any]] = []
    position = 0
    for year in years:
        if position + 4 > len(tokens):
            break
        group_tokens = tokens[position : position + group_width]
        parsed = parse_kyonggi_support_result_group(group_tokens)
        if parsed is not None:
            parsed["year"] = year
            groups.append(parsed)
        position += group_width
    return groups


def parse_kyonggi_support_result_group(tokens: list[str]) -> dict[str, Any] | None:
    if len(tokens) < 4:
        return None
    quota = int_or_none(tokens[0].replace(",", ""))
    applicants = int_or_none(tokens[1].replace(",", ""))
    competition_rate = number_or_none(tokens[2].replace(",", ""))
    additional_pass = None if tokens[3] == "-" else int_or_none(tokens[3].replace(",", ""))
    if quota is None or applicants is None or competition_rate is None:
        return None
    if quota <= 0 or applicants < 0 or competition_rate <= 0 or competition_rate >= 500:
        return None
    if additional_pass is not None and additional_pass < 0:
        return None
    calculated = applicants / quota
    if abs(calculated - competition_rate) > 0.08:
        return None
    return {
        "quota": quota,
        "applicants": applicants,
        "competitionRate": number_string(competition_rate),
        "additionalPass": additional_pass,
    }


def kyonggi_support_result_track_label(title: str) -> str:
    text = normalize_text(title)
    text = re.sub(r"^\d{1,2}(?:-\d{1,2})?[.,]?\s*", "", text)
    text = re.sub(r"^\s*·\s*", "", text)
    text = re.sub(
        r"\s*(?:3개년\s*지원결과|2025\s*학년도\s*(?:경쟁률\s*및\s*등록결과|지원결과)).*$",
        "",
        text,
    )
    text = text.strip(" /,.:;·ㆍ-")
    return text or "지원결과"


def kyonggi_three_year_result_track_label(title: str) -> str:
    text = normalize_text(title)
    text = re.sub(r"^\d{1,2}(?:-\d{1,2})?[.,]?\s*", "", text)
    text = re.sub(r"\s*3개년\s*전형\s*결과.*$", "", text)
    text = text.strip(" /,.:;·ㆍ-")
    return text or "3개년 전형결과"


def parse_kyonggi_2025_detail_result_line(
    line: str,
    pending_prefix: str,
) -> dict[str, Any] | None:
    if re.search(r"미선발|미공개|등록\s*인원\s*없음|최종등록자\s*1명", line):
        return None
    first_score = KYONGGI_2025_DECIMAL_PATTERN.search(line)
    if first_score is None:
        return None
    label = line[: first_score.start()]
    values = [
        float(match.group(0))
        for match in KYONGGI_2025_NUMBER_PATTERN.finditer(line[first_score.start() :])
    ]
    if len(values) < 11:
        return None
    line_recruitment_group = recruitment_group_from_korean_text(label)
    unit_name = clean_kyonggi_2025_result_unit_name(label, pending_prefix)
    if not unit_name:
        return None
    final_high, final_avg, cut50, cut70, cut100 = values[6:11]
    final_values = [final_high, final_avg, cut50, cut70, cut100]
    if not all(0 < value <= 100 for value in final_values):
        return None
    return {
        "unitName": unit_name,
        "quota": None,
        "applicants": None,
        "recruitmentGroup": line_recruitment_group,
        "competitionRate": "",
        "additionalPass": None,
        "avgScoreCandidate": number_string(final_avg),
        "cutScoreCandidate": number_string(cut100),
        "percentileCutCandidate": number_string(cut70),
        "scoreAvailability": "office_score_metric_candidate",
        "metricCount": 5,
        "hasQuotaAndCompetition": False,
        "hasOutcomeScore": True,
    }


def kyonggi_2025_pending_unit_prefix(line: str, previous_prefix: str) -> str:
    text = normalize_text(line)
    if not text or KYONGGI_2025_DECIMAL_PATTERN.search(text):
        return ""
    if re.search(r"최고|평균|cut|모집단위|최종등록자|최초합격자|최종합격자|비고|수능점수", text):
        return ""
    if len(text) > 40:
        return ""
    cleaned = clean_kyonggi_2025_result_unit_name(text, "")
    if not cleaned:
        return ""
    if previous_prefix and cleaned not in previous_prefix:
        return normalize_text(f"{previous_prefix} {cleaned}")
    return cleaned


def clean_kyonggi_2025_result_unit_name(label: str, pending_prefix: str) -> str:
    text = normalize_text(label)
    text = re.sub(r"^(?:가군|나군|다군)\s+", "", text)
    text = re.sub(r"^(?:AI|컴퓨터|공학부)\s+", "", text)
    text = re.sub(r"^(?:[*]\s*)+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" /,.:;·ㆍ-[]")
    if should_merge_kyonggi_2025_pending_prefix(pending_prefix, text):
        text = normalize_text(f"{pending_prefix} {text}")
    text = re.sub(r"\s+", " ", text).strip(" /,.:;·ㆍ-[]")
    if not text:
        return ""
    if not re.search(r"[A-Za-z가-힣]", text):
        return ""
    if re.search(r"최고|평균|cut|모집단위|최종등록자|최초합격자|최종합격자|비고|수능점수", text):
        return ""
    if len(text) > 80:
        return ""
    if not is_useful_office_admission_unit_name(text):
        return ""
    return text


def should_merge_kyonggi_2025_pending_prefix(prefix: str, label: str) -> bool:
    prefix = normalize_text(prefix)
    label = normalize_text(label)
    if not prefix or not label or prefix in label:
        return False
    if "AI컴퓨터공학부" in prefix and re.search(
        r"^(?:컴퓨터공학전공|인공지능전공|SW안전보안전공)$",
        label,
    ):
        return True
    return bool(prefix.endswith("학부") and label.endswith("전공") and len(label) <= 20)


def kyonggi_2025_result_track_label(title: str) -> str:
    text = normalize_text(title)
    text = re.sub(r"^\d{1,2}(?:-\d{1,2})?[.,]?\s*", "", text)
    text = re.sub(r"\s*2025\s*학년도\s*전형\s*결과\s*상세.*$", "", text)
    text = text.strip(" /,.:;·ㆍ-")
    return text or "2025학년도 전형결과 상세"


def kyonggi_2025_official_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return ""
    return raw_office_text_source(source_path)


YEWON_2022_SUSI_RESULT_SPECS: list[dict[str, Any]] = [
    {
        "unitName": "융합조형디자인전공",
        "resultAliases": ("융합조형디자인전공", "융 합 조 형 디 자 인 전 공"),
        "competitionAliases": ("융합조형디자인전공",),
        "quota": 13,
        "applicants": 32,
        "competitionRateText": "2.46",
        "firstBestGrade": "3",
        "firstWorstGrade": "6",
        "avgGrade": "4",
        "finalCutGrade": "6",
        "additionalPass": 13,
    },
    {
        "unitName": "뷰티디자인전공",
        "resultAliases": ("뷰티디자인전공", "뷰 디 디 자 인 전 공"),
        "competitionAliases": ("뷰티디자인전공", "뷰 티 디 자 인 전 공"),
        "quota": 18,
        "applicants": 80,
        "competitionRateText": "4.44",
        "firstBestGrade": "2",
        "firstWorstGrade": "6",
        "avgGrade": "4",
        "finalCutGrade": "6",
        "additionalPass": 50,
    },
    {
        "unitName": "시각디자인전공",
        "resultAliases": (
            "시각디자인전공",
            "시각영상디자인전공",
            "시각〮영상디자인전공",
        ),
        "competitionAliases": ("시각디자인전공", "시 각 디 자 인 전 공"),
        "quota": 14,
        "applicants": 29,
        "competitionRateText": "2.07",
        "firstBestGrade": "1",
        "firstWorstGrade": "6",
        "avgGrade": "4",
        "finalCutGrade": "6",
        "additionalPass": 15,
    },
    {
        "unitName": "애니메이션&웹툰전공",
        "resultAliases": ("애니메이션&웹툰전공",),
        "competitionAliases": ("애니메이션&웹툰전공",),
        "quota": 20,
        "applicants": 110,
        "competitionRateText": "5.50",
        "firstBestGrade": "2",
        "firstWorstGrade": "6",
        "avgGrade": "4",
        "finalCutGrade": "6",
        "additionalPass": 36,
    },
    {
        "unitName": "실용음악전공",
        "resultAliases": ("실용음악전공", "실 용 음 악 전 공"),
        "competitionAliases": ("실용음악전공", "실 용 음 악 전 공"),
        "quota": 14,
        "applicants": 29,
        "competitionRateText": "2.07",
        "firstBestGrade": "3",
        "firstWorstGrade": "7",
        "avgGrade": "5",
        "finalCutGrade": "6",
        "additionalPass": 5,
    },
    {
        "unitName": "공연예술전공",
        "resultAliases": ("공연예술전공", "공 연 예 술 전 공"),
        "competitionAliases": ("공연예술전공", "공 연 예 술 전 공"),
        "quota": 14,
        "applicants": 28,
        "competitionRateText": "2.00",
        "firstBestGrade": "3",
        "firstWorstGrade": "7",
        "avgGrade": "4",
        "finalCutGrade": "7",
        "additionalPass": 6,
    },
    {
        "unitName": "스포츠경호무도학과",
        "resultAliases": ("스포츠경호무도학과", "스포츠과학과"),
        "competitionAliases": ("스포츠경호무도학과",),
        "quota": 23,
        "applicants": 42,
        "competitionRateText": "1.83",
        "firstBestGrade": "4",
        "firstWorstGrade": "8",
        "avgGrade": "5",
        "finalCutGrade": "8",
        "additionalPass": 6,
    },
    {
        "unitName": "만화게임영상전공",
        "resultAliases": ("만화게임영상전공", "만 화 게 임 영 상 전 공"),
        "competitionAliases": ("만화게임영상전공", "만 화 게 임 영 상 전 공"),
        "quota": 19,
        "applicants": 156,
        "competitionRateText": "8.21",
        "firstBestGrade": "3",
        "firstWorstGrade": "6",
        "avgGrade": "4",
        "finalCutGrade": "6",
        "additionalPass": 24,
    },
    {
        "unitName": "연극영화전공",
        "resultAliases": ("연극영화전공", "연 극 영 화 전 공"),
        "competitionAliases": ("연극영화전공", "연 극 영 화 전 공"),
        "quota": 15,
        "applicants": 65,
        "competitionRateText": "4.33",
        "firstBestGrade": "3",
        "firstWorstGrade": "7",
        "avgGrade": "5",
        "finalCutGrade": "7",
        "additionalPass": 21,
    },
    {
        "unitName": "음악전공",
        "resultAliases": ("음악전공", "음 악 전 공"),
        "competitionAliases": ("음악전공", "음 악 전 공"),
        "quota": 7,
        "applicants": 7,
        "competitionRateText": "1.00",
        "firstBestGrade": "5",
        "firstWorstGrade": "8",
        "avgGrade": "6",
        "finalCutGrade": "6",
        "additionalPass": None,
    },
]


def is_yewon_2022_susi_result_pdf_source(row: dict[str, Any]) -> bool:
    if not is_yewon_2022_legacy_results_row(row):
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if "admission_result" not in join_values(row.get("sourceLinkRoles")):
        return False
    if "admission_result_pdf" not in join_values(row.get("detectedDocumentRoles")):
        return False
    return first_existing_office_text_source_path(row) is not None


def parse_yewon_2022_susi_result_pdf_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    result_path = first_existing_office_text_source_path(row)
    if result_path is None:
        return []
    result_text = raw_office_text_source(result_path)
    if "2022학년도 수시모집 입시결과" not in result_text:
        return []
    competition_path = yewon_2022_competition_text_source_path(result_path)
    if competition_path is None:
        return []
    competition_text = raw_office_text_source(competition_path)
    if "2022학년도 수시모집 응시율" not in competition_text:
        return []
    entries: list[dict[str, Any]] = []
    for row_index, spec in enumerate(YEWON_2022_SUSI_RESULT_SPECS, start=1):
        if not yewon_2022_result_spec_visible(result_text, spec):
            continue
        if not yewon_2022_competition_spec_visible(competition_text, spec):
            continue
        competition_rate = number_or_none(spec["competitionRateText"])
        if competition_rate is None:
            continue
        entries.append(
            {
                "unitName": spec["unitName"],
                "canonicalCandidate": canonical_name(spec["unitName"]),
                "track": "일반전형",
                "rowIndex": row_index,
                "parsed": {
                    "quota": spec["quota"],
                    "applicants": spec["applicants"],
                    "competitionRate": round(float(competition_rate), 2),
                    "additionalPass": spec["additionalPass"],
                    "avgScoreCandidate": spec["avgGrade"],
                    "cutScoreCandidate": spec["finalCutGrade"],
                    "percentileCutCandidate": spec["finalCutGrade"],
                    "scoreAvailability": (
                        "office_quota_competition_and_score_metric_candidate"
                    ),
                    "metricCount": 5,
                    "hasQuotaAndCompetition": True,
                    "hasOutcomeScore": True,
                },
            }
        )
    return entries


def yewon_2022_competition_text_source_path(result_path: Path) -> Path | None:
    for parent in result_path.parents:
        if parent.name != "extracted-yewon-2022-legacy-results-20260614":
            continue
        for candidate in parent.glob("pdf-text/2022/**/*.txt"):
            if candidate == result_path:
                continue
            if "2022학년도 수시모집 응시율" in raw_office_text_source(candidate):
                return candidate
    return None


def yewon_2022_result_spec_visible(text: str, spec: dict[str, Any]) -> bool:
    compact_text = yewon_2022_compact_text(text)
    if not yewon_2022_any_alias_visible(compact_text, spec["resultAliases"]):
        return False
    required_tokens = [
        f"{spec['firstBestGrade']}등급",
        f"{spec['firstWorstGrade']}등급",
        f"{spec['avgGrade']}등급",
        f"{spec['finalCutGrade']}등급",
        (
            f"예비{spec['additionalPass']}"
            if spec["additionalPass"] is not None
            else "후보없음"
        ),
    ]
    return all(yewon_2022_compact_text(token) in compact_text for token in required_tokens)


def yewon_2022_competition_spec_visible(text: str, spec: dict[str, Any]) -> bool:
    compact_text = yewon_2022_compact_text(text)
    if not yewon_2022_any_alias_visible(compact_text, spec["competitionAliases"]):
        return False
    required_tokens = [
        str(spec["quota"]),
        str(spec["applicants"]),
        spec["competitionRateText"],
    ]
    return all(yewon_2022_compact_text(token) in compact_text for token in required_tokens)


def yewon_2022_any_alias_visible(compact_text: str, aliases: Any) -> bool:
    return any(yewon_2022_compact_text(alias) in compact_text for alias in aliases)


def yewon_2022_compact_text(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", normalize_text(value))


def yewon_2021_legacy_results_collection_year(row: dict[str, Any]) -> int | None:
    if "gap_yewon_2021_legacy_results_docs" not in join_values(row.get("sourceLabels")):
        return None
    if normalize_text(row.get("unvCd")) != "0000218":
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if unique_years == [2021] else None


def is_yewon_2022_legacy_results_row(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000218":
        return False
    joined_context = join_values(
        [
            row.get("sourceLabels"),
            row.get("sourcePaths"),
            row.get("rawPaths"),
            row.get("attachmentUrls"),
            row.get("sourceCandidateUrls"),
        ]
    )
    return (
        "gap_yewon_2022_legacy_results_docs" in joined_context
        or "extracted-yewon-2022-legacy-results-20260614" in joined_context
        or "filedown.php?menu=294&no=556" in joined_context
        or "filedown.php?menu=294&no=557" in joined_context
    )


def yewon_2022_legacy_results_collection_year(row: dict[str, Any]) -> int | None:
    if not is_yewon_2022_legacy_results_row(row):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if unique_years == [2022] else None


SEOWON_2021_SUSI_RESULT_UNIT_PATTERN = re.compile(
    r"^\s*(?P<unit>[가-힣A-Za-z0-9·ㆍ()\[\]/]+"
    r"(?:교육과|학과|학부|전공|계열)(?:\[교직\])?)"
)
SEOWON_2021_SUSI_RESULT_GRADE_PATTERN = re.compile(
    r"(?<![\d.])\d(?:\.\d)?(?![\d.])"
)


def is_seowon_2021_susi_result_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000128":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_table":
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    source_context = join_values(
        [
            row.get("sourceLabels"),
            row.get("sourcePaths"),
            row.get("rawPaths"),
            row.get("attachmentUrls"),
            row.get("sourceCandidateUrls"),
        ]
    )
    if (
        "seowon_2022_result_detail_files_docs" not in source_context
        and "96b1890478728d6e" not in source_context
        and "/bbs/iphak/602/108348/" not in source_context
    ):
        return False
    text = normalize_text(seowon_2021_susi_result_source_text(row))
    return bool(
        "2022학년도 서원대학교 신입학 전형결과" in text
        and "일반전형(교과)" in text
        and "70% CUT" in text
    )


def seowon_2021_susi_result_source_year(row: dict[str, Any]) -> int | None:
    if not is_seowon_2021_susi_result_source(row):
        return None
    return 2021


def seowon_2021_susi_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return ""
    return raw_office_text_source(source_path)


def parse_seowon_2021_susi_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = seowon_2021_susi_result_source_text(row)
    if not text:
        return []
    entries: list[dict[str, Any]] = []
    for line_index, line in enumerate(text.splitlines(), start=1):
        parsed = parse_seowon_2021_susi_result_line(line)
        if parsed is None:
            continue
        unit_name = parsed["unitName"]
        entries.append(
            {
                "unitName": unit_name,
                "canonicalCandidate": canonical_name(unit_name),
                "year": 2021,
                "sectionId": "seowon_2021_susi_general_subject",
                "rowIndex": line_index,
                "parsed": {
                    "quota": None,
                    "competitionRate": "",
                    "additionalPass": None,
                    "avgScoreCandidate": number_string(parsed["avg2021"]),
                    "cutScoreCandidate": number_string(parsed["cut2021"]),
                    "percentileCutCandidate": "",
                    "scoreAvailability": "office_score_metric_candidate",
                    "metricCount": 2,
                    "hasQuotaAndCompetition": False,
                    "hasOutcomeScore": True,
                },
            }
        )
    return entries


def parse_seowon_2021_susi_result_line(line: str) -> dict[str, Any] | None:
    unit_match = SEOWON_2021_SUSI_RESULT_UNIT_PATTERN.match(line)
    if not unit_match:
        return None
    unit_name = clean_seowon_2021_susi_result_unit_name(unit_match.group("unit"))
    if not unit_name:
        return None
    rest = line[unit_match.end() :]
    first_grade = SEOWON_2021_SUSI_RESULT_GRADE_PATTERN.search(rest)
    if first_grade is None:
        return None
    prefix = rest[: first_grade.start()]
    if "★" in prefix or len(prefix) > 18 or prefix.strip():
        return None
    values = [
        number_or_none(match.group(0))
        for match in SEOWON_2021_SUSI_RESULT_GRADE_PATTERN.finditer(rest)
    ][:4]
    if len(values) < 4 or any(value is None for value in values):
        return None
    avg2021, cut2021, avg2022, cut2022 = [float(value) for value in values]
    if not all(1 <= value <= 9 for value in (avg2021, cut2021, avg2022, cut2022)):
        return None
    if cut2021 + 0.4 < avg2021 or cut2022 + 0.4 < avg2022:
        return None
    return {
        "unitName": unit_name,
        "avg2021": avg2021,
        "cut2021": cut2021,
        "avg2022": avg2022,
        "cut2022": cut2022,
    }


def clean_seowon_2021_susi_result_unit_name(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"\[교직\]", "", text)
    text = text.strip(" /,.:;·ㆍ-[]")
    if not text:
        return ""
    if re.search(r"모집|지원|경쟁|최종|순위|백분위|전형|평균", text):
        return ""
    if not OFFICE_UNIT_SUFFIX_PATTERN.search(text):
        return ""
    if not is_useful_office_admission_unit_name(text):
        return ""
    return text[:60]


SEOWON_2022_REGULAR_RESULT_NUMBER_PATTERN = re.compile(
    r"(?<![\d.])\d{1,3}(?:\.\d+)?(?![\d.])"
)


def is_seowon_2022_regular_result_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("unvCd")) != "0000128":
        return False
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceRole")) != "admission_result_table":
        return False
    if "pdf_snippet" not in join_values(row.get("evidenceTypes")):
        return False
    source_context = join_values(
        [
            row.get("sourceLabels"),
            row.get("sourcePaths"),
            row.get("rawPaths"),
            row.get("attachmentUrls"),
            row.get("sourceCandidateUrls"),
        ]
    )
    if (
        "seowon_2022_result_detail_files_docs" not in source_context
        and "3dff1b4d6b370489" not in source_context
        and "/bbs/iphak/602/110868/" not in source_context
    ):
        return False
    text = normalize_text(seowon_2022_regular_result_source_text(row))
    return bool(
        "2022학년도 서원대학교 정시모집 전형결과" in text
        and "국,수,탐(1)중 2개 백분위 평균" in text
        and "영어등급" in text
    )


def seowon_2022_regular_result_source_year(row: dict[str, Any]) -> int | None:
    if not is_seowon_2022_regular_result_source(row):
        return None
    return 2022


def seowon_2022_regular_result_source_text(row: dict[str, Any]) -> str:
    source_path = first_existing_office_text_source_path(row)
    if source_path is None:
        return ""
    return raw_office_text_source(source_path)


def parse_seowon_2022_regular_result_entries(row: dict[str, Any]) -> list[dict[str, Any]]:
    text = seowon_2022_regular_result_source_text(row)
    if not text:
        return []
    current_group = "ga"
    entries: list[dict[str, Any]] = []
    for line_index, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.replace("\f", " ")
        group_match = re.match(r"^\s*([가나다])\s*군(?:\s+|$)", line)
        if group_match:
            current_group = recruitment_group_from_korean(group_match.group(1))
            line = line[group_match.end() :]
            if not normalize_text(line):
                continue
        parsed = parse_seowon_2022_regular_result_line(line)
        if parsed is None:
            continue
        unit_name = parsed.pop("unitName")
        entries.append(
            {
                "unitName": unit_name,
                "canonicalCandidate": canonical_name(unit_name),
                "recruitmentGroup": current_group,
                "year": 2022,
                "sectionId": f"regular_csat_percentile:{current_group}",
                "rowIndex": line_index,
                "parsed": parsed,
            }
        )
    return entries


def parse_seowon_2022_regular_result_line(line: str) -> dict[str, Any] | None:
    matches = list(SEOWON_2022_REGULAR_RESULT_NUMBER_PATTERN.finditer(line))
    if len(matches) < 11:
        return None
    unit_name = clean_seowon_2022_regular_result_unit_name(line[: matches[0].start()])
    if not unit_name:
        return None
    values = [match.group(0) for match in matches[:11]]
    quota = int_or_none(values[0])
    applicants = int_or_none(values[1])
    competition_rate = number_or_none(values[2])
    additional_pass = int_or_none(values[3])
    percentile_min = number_or_none(values[4])
    percentile_max = number_or_none(values[5])
    percentile_avg = number_or_none(values[6])
    english_min = number_or_none(values[7])
    english_max = number_or_none(values[8])
    english_avg = number_or_none(values[9])
    next_year_quota = int_or_none(values[10])
    if (
        quota is None
        or applicants is None
        or competition_rate is None
        or additional_pass is None
        or percentile_min is None
        or percentile_max is None
        or percentile_avg is None
        or english_min is None
        or english_max is None
        or english_avg is None
        or next_year_quota is None
    ):
        return None
    competition_float = float(competition_rate)
    percentile_min_float = float(percentile_min)
    percentile_max_float = float(percentile_max)
    percentile_avg_float = float(percentile_avg)
    if not (0 < quota <= 1000 and 0 < applicants <= 5000):
        return None
    if not (0 < competition_float <= 300 and 0 <= additional_pass <= 5000):
        return None
    if not (
        0 < percentile_min_float <= 100
        and 0 < percentile_avg_float <= 100
        and 0 < percentile_max_float <= 100
    ):
        return None
    if not (1 <= float(english_min) <= 9 and 1 <= float(english_max) <= 9):
        return None
    return {
        "unitName": unit_name,
        "quota": quota,
        "applicants": applicants,
        "competitionRate": round(competition_float, 2),
        "additionalPass": additional_pass,
        "avgScoreCandidate": number_string(percentile_avg_float),
        "cutScoreCandidate": number_string(percentile_min_float),
        "percentileCutCandidate": number_string(percentile_min_float),
        "scoreAvailability": "office_quota_competition_and_score_metric_candidate",
        "metricCount": 3,
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": True,
    }


def clean_seowon_2022_regular_result_unit_name(value: str) -> str:
    text = normalize_text(value)
    text = re.sub(r"^[가나다]\s*군\s*", "", text)
    text = text.strip(" /,.:;·ㆍ-[]")
    if not text:
        return ""
    if re.search(r"모집|지원|경쟁|최종|순위|백분위|전형", text):
        return ""
    if not OFFICE_UNIT_SUFFIX_PATTERN.search(text):
        return ""
    if not is_useful_office_admission_unit_name(text):
        return ""
    return text[:60]


def kyonggi_2024_official_results_collection_year(row: dict[str, Any]) -> int | None:
    if "gap_kyonggi_2024_official_results_docs" not in join_values(row.get("sourceLabels")):
        return None
    if normalize_text(row.get("unvCd")) != "0000058":
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if unique_years == [2024] else None


def kyonggi_2022_official_score_collection_year(row: dict[str, Any]) -> int | None:
    if "gap_kyonggi_2022_official_score_docs" not in join_values(row.get("sourceLabels")):
        return None
    if normalize_text(row.get("unvCd")) != "0000058":
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if unique_years == [2022] else None


def kyonggi_2025_official_results_collection_year(row: dict[str, Any]) -> int | None:
    if "gap_kyonggi_2025_official_results_docs" not in join_values(row.get("sourceLabels")):
        return None
    if normalize_text(row.get("unvCd")) != "0000058":
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if unique_years == [2025] else None


def kyonggi_2026_susi_guide_result_collection_year(row: dict[str, Any]) -> int | None:
    if "gap_manual_kyonggi_docs" not in join_values(row.get("sourceLabels")):
        return None
    if normalize_text(row.get("unvCd")) not in {"0000056", "0000058"}:
        return None
    source_context = normalize_text(
        " ".join(
            [
                join_values(row.get("sourceCandidateUrls")),
                join_values(row.get("attachmentUrls")),
                join_values(row.get("sourcePaths")),
            ]
        )
    )
    if "1780622763509_0.pdf" not in source_context:
        return None
    detected_years = {
        int_or_none(value) for value in split_joined(row.get("detectedAdmissionYears"))
    }
    if 2026 not in detected_years:
        return None
    return 2026


def ginue_regular_results_collection_year(row: dict[str, Any]) -> int | None:
    if "manual_ginue_regular_results_docs" not in join_values(row.get("sourceLabels")):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if len(unique_years) == 1 else None


def hanil_application_status_collection_year(row: dict[str, Any]) -> int | None:
    if not is_hanil_application_status_html_source(row):
        return None
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    return unique_years[0] if len(unique_years) == 1 else None


def office_historical_outcome_source_context_year(row: dict[str, Any]) -> int | None:
    if "workbook_row" in join_values(row.get("evidenceTypes")):
        return None
    preview = normalize_text(row.get("textPreview") or row.get("sampleText"))
    if len(preview) < 40:
        return None
    if not re.search(r"입시\s*결과|최종\s*결과|경쟁률|전년도", preview):
        return None
    source_path = first_existing_office_workbook_source_path(row)
    if source_path is None:
        return None
    source_text = normalized_office_text_source(source_path)
    if not source_text:
        return None
    needle = preview[: min(160, len(preview))]
    index = source_text.find(needle)
    if index < 0 and len(needle) > 80:
        index = source_text.find(needle[:80])
    if index < 0:
        return None
    context = source_text[max(0, index - 9000) : index + 800]
    preview_context = context[-1600:]
    matches = list(ADMISSION_YEAR_CONTEXT_PATTERN.finditer(context))
    for match in reversed(matches):
        year = int_or_none(match.group(1))
        if year is None or not (RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX):
            continue
        window = context[max(0, match.start() - 260) : match.end() + 260]
        if re.search(r"입시\s*결과|최종\s*결과|경쟁률", window):
            return year
        if re.search(r"모집\s*요강|전형\s*모집\s*요강", window) and re.search(
            r"전년도\s*입시\s*결과", preview_context
        ):
            return year - 1 if year > RECENT_YEAR_MIN else None
    return None


def normalized_office_text_source(path: Path) -> str:
    cache_key = str(path)
    if cache_key not in OFFICE_TEXT_SOURCE_CACHE:
        try:
            OFFICE_TEXT_SOURCE_CACHE[cache_key] = normalize_text(
                path.read_text(encoding="utf-8", errors="ignore")
            )
        except OSError:
            OFFICE_TEXT_SOURCE_CACHE[cache_key] = ""
    return OFFICE_TEXT_SOURCE_CACHE[cache_key]


def raw_office_text_source(path: Path) -> str:
    cache_key = str(path)
    if cache_key not in OFFICE_RAW_TEXT_SOURCE_CACHE:
        try:
            OFFICE_RAW_TEXT_SOURCE_CACHE[cache_key] = path.read_text(
                encoding="utf-8", errors="ignore"
            )
        except OSError:
            OFFICE_RAW_TEXT_SOURCE_CACHE[cache_key] = ""
    return OFFICE_RAW_TEXT_SOURCE_CACHE[cache_key]


def office_historical_outcome_locator_year(row: dict[str, Any]) -> int | None:
    collection_years = [
        year
        for year in (int_or_none(value) for value in split_joined(row.get("collectionYears")))
        if year is not None and RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX
    ]
    unique_years = list(dict.fromkeys(collection_years))
    if len(unique_years) != 1:
        return None
    year = unique_years[0]
    locator_text = join_values(row.get("attachmentUrls"))
    if not locator_text:
        return None
    if re.search(rf"(?<!\d){year}(?:\s*학\s*년\s*도|[_./-]|(?!\d))", locator_text):
        return year
    return None


def office_outcome_unit_matches(text: str) -> list[tuple[str, int, int]]:
    matches: list[tuple[str, int, int]] = []
    seen_at_position: set[tuple[str, int]] = set()
    bracketed_pattern = re.compile(
        r"\[([가-힣A-Za-z0-9·ㆍ&()./+ -]{1,48}(?:학과|교육과|어과|학부|전공|계열))\]"
    )
    for match in bracketed_pattern.finditer(text):
        unit_name = clean_office_admission_unit_name(match.group(1))
        if not is_useful_office_admission_unit_name(unit_name):
            continue
        start = match.start(1)
        end = match.end(1)
        key = (unit_name, start)
        if key in seen_at_position:
            continue
        seen_at_position.add(key)
        matches.append((unit_name, start, end))
    for match in OFFICE_UNIT_NAME_PATTERN.finditer(text):
        unit_name = clean_office_admission_unit_name(match.group(0))
        if not is_useful_office_admission_unit_name(unit_name):
            continue
        unit_offset = match.group(0).rfind(unit_name)
        if unit_offset >= 0:
            start = match.start() + unit_offset
            end = start + len(unit_name)
        else:
            start = match.start()
            end = match.end()
        if start > 0 and re.match(r"[가-힣A-Za-z0-9]", text[start - 1]):
            continue
        key = (unit_name, start)
        if key in seen_at_position:
            continue
        seen_at_position.add(key)
        matches.append((unit_name, start, end))
    if re.search(r"전년도\s*입시\s*결과", text) and re.search(r"지원율|지원률", text):
        bracketed_matches = [
            match for match in matches if match[1] > 0 and text[match[1] - 1] == "["
        ]
        if bracketed_matches:
            return bracketed_matches[:160]
    return matches[:160]


def office_direct_competition_fallback_allowed(row: dict[str, Any]) -> bool:
    role = normalize_text(row.get("evidenceRole"))
    if role in {
        "admission_result_ocr_page",
        "competition_rate_ocr_page",
        "admission_result_image_ocr",
        "competition_rate_image_ocr",
    }:
        return False
    source_locations = "|".join(
        [
            join_values(row.get("sourceCandidateUrls")),
            join_values(row.get("attachmentUrls")),
            join_values(row.get("rawPaths")),
        ]
    )
    return "IE=edge" not in source_locations


def parse_office_outcome_segment(
    segment: str, full_text: str, allow_direct_competition: bool = True
) -> dict[str, Any] | None:
    tokens = office_outcome_number_tokens(segment[:260])
    split_quota_parsed = parse_office_split_quota_competition_segment(tokens, full_text)
    if split_quota_parsed is not None:
        return split_quota_parsed
    for index in range(len(tokens) - 2):
        quota_token = tokens[index]
        applicants_token = tokens[index + 1]
        quota = office_integer_token_value(quota_token)
        applicants = office_integer_token_value(applicants_token)
        if quota is None or applicants is None:
            continue
        if quota <= 0 or quota > 1000 or applicants < 0 or applicants > 10000:
            continue
        for competition_index in (index + 2, index + 3):
            if competition_index >= len(tokens):
                continue
            competition = float(tokens[competition_index]["value"])
            if competition <= 0 or competition > 300:
                continue
            if not is_office_competition_token(tokens[competition_index], quota, applicants):
                continue
            score_values = extract_office_score_values(tokens[competition_index + 1 :], full_text)
            return {
                "quota": quota,
                "applicants": applicants,
                "competitionRate": round(competition, 2),
                "additionalPass": extract_office_additional_pass(
                    segment,
                    full_text,
                    tokens,
                    competition_index,
                    index,
                ),
                "avgScoreCandidate": score_values[0] if score_values else "",
                "cutScoreCandidate": score_values[-1] if score_values else "",
                "percentileCutCandidate": score_values[-1] if score_values else "",
                "scoreAvailability": (
                    "office_quota_competition_and_score_metric_candidate"
                    if score_values
                    else "office_quota_competition_candidate"
                ),
                "metricCount": len(score_values),
                "hasOutcomeScore": bool(score_values),
            }
    if allow_direct_competition:
        direct_competition = parse_office_quota_competition_only_segment(segment, full_text, tokens)
        if direct_competition is not None:
            return direct_competition
    rate_score_result = parse_office_rate_score_result_segment(segment, full_text)
    if rate_score_result is not None:
        return rate_score_result
    return None


def parse_office_rate_score_result_segment(segment: str, full_text: str) -> dict[str, Any] | None:
    context = segment[:1200]
    if "전형" not in context:
        return None
    if not re.search(r"지원율|지원률", context):
        return None
    if not (
        "최고" in context
        and re.search(r"50\s*%", context)
        and re.search(r"70\s*%", context)
        and "최저" in context
    ):
        return None
    if not OFFICE_OUTCOME_SCORE_CONTEXT.search(context):
        return None
    row_pattern = re.compile(
        r"(?:^|\s)"
        r"(?P<label>[가-힣A-Za-z0-9·ㆍ&()./+ -]{0,40}전형(?:\[[^\]]+\])?)"
        r"\s+"
        r"(?P<rate>\d{1,3}(?:\.\d+)?)"
        r"\s+"
        r"(?P<best>\d{1,4}(?:\.\d+)?)"
        r"\s+"
        r"(?P<p50>\d{1,4}(?:\.\d+)?)"
        r"\s+"
        r"(?P<p70>\d{1,4}(?:\.\d+)?)"
        r"\s+"
        r"(?P<low>\d{1,4}(?:\.\d+)?)"
    )
    for match in row_pattern.finditer(context):
        label = normalize_text(match.group("label"))
        if "전형" not in label:
            continue
        rate = number_or_none(match.group("rate"))
        scores = [
            number_or_none(match.group(name))
            for name in ("best", "p50", "p70", "low")
        ]
        if rate is None or any(score is None for score in scores):
            continue
        rate_value = float(rate)
        score_values = [float(score) for score in scores if score is not None]
        if rate_value <= 0 or rate_value > 300:
            continue
        if any(value <= 0 or value > 1000 for value in score_values):
            continue
        if any(value.is_integer() and RECENT_YEAR_MIN <= int(value) <= RECENT_YEAR_MAX for value in score_values):
            continue
        return {
            "quota": None,
            "applicants": None,
            "competitionRate": round(rate_value, 2),
            "additionalPass": None,
            "avgScoreCandidate": number_string(score_values[1]),
            "cutScoreCandidate": number_string(score_values[2]),
            "percentileCutCandidate": number_string(score_values[2]),
            "scoreAvailability": "office_competition_and_score_metric_candidate",
            "metricCount": len(score_values),
            "hasQuotaAndCompetition": False,
            "hasOutcomeScore": True,
        }
    return None


def parse_office_split_quota_competition_segment(
    tokens: list[dict[str, Any]], full_text: str
) -> dict[str, Any] | None:
    if not re.search(r"최초|이월", full_text):
        return None
    for index in range(len(tokens) - 4):
        quota = office_integer_token_value(tokens[index])
        initial_quota = office_integer_token_value(tokens[index + 1])
        carryover_quota = office_integer_token_value(tokens[index + 2])
        applicants = office_integer_token_value(tokens[index + 3])
        if None in {quota, initial_quota, carryover_quota, applicants}:
            continue
        if quota <= 0 or quota > 1000 or applicants < 0 or applicants > 10000:
            continue
        if initial_quota is None or carryover_quota is None or initial_quota + carryover_quota != quota:
            continue
        competition_token = tokens[index + 4]
        competition = float(competition_token.get("value") or 0)
        if competition <= 0 or competition > 300:
            continue
        if not is_office_competition_token(competition_token, quota, applicants):
            continue
        score_values = extract_office_score_values(tokens[index + 5 :], full_text)
        return {
            "quota": quota,
            "applicants": applicants,
            "competitionRate": round(competition, 2),
            "additionalPass": extract_office_additional_pass_after_scores(
                full_text, tokens[index + 5 :]
            ),
            "avgScoreCandidate": score_values[0] if score_values else "",
            "cutScoreCandidate": score_values[-1] if score_values else "",
            "percentileCutCandidate": score_values[-1] if score_values else "",
            "scoreAvailability": (
                "office_quota_competition_and_score_metric_candidate"
                if score_values
                else "office_quota_competition_candidate"
            ),
            "metricCount": len(score_values),
            "hasOutcomeScore": bool(score_values),
        }
    return None


def parse_office_quota_competition_only_segment(
    segment: str, full_text: str, tokens: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if not has_office_quota_context(full_text):
        return None
    if not re.search(r"경쟁률|지원율|지원률", full_text):
        return None
    if not re.search(r"평균|최저|최고|50%\s*cut|70%\s*cut|충원", full_text, re.I):
        return None
    for index in range(len(tokens) - 1):
        quota = office_integer_token_value(tokens[index])
        if quota is None or quota <= 0 or quota > 1000:
            continue
        competition_token = tokens[index + 1]
        competition = float(competition_token.get("value") or 0)
        raw_competition = normalize_text(competition_token.get("raw"))
        if competition <= 0 or competition > 300:
            continue
        if not (
            bool(competition_token.get("isRatio"))
            or "." in raw_competition
            or re.search(rf"\b{re.escape(raw_competition)}\s*:\s*1\b", segment)
        ):
            continue
        score_values = extract_office_score_values(tokens[index + 2 :], full_text)
        return {
            "quota": quota,
            "applicants": None,
            "competitionRate": round(competition, 2),
            "additionalPass": extract_office_additional_pass_for_direct_competition(
                full_text, tokens[index + 2 :]
            ),
            "avgScoreCandidate": score_values[0] if score_values else "",
            "cutScoreCandidate": score_values[-1] if score_values else "",
            "percentileCutCandidate": score_values[-1] if score_values else "",
            "scoreAvailability": (
                "office_quota_competition_and_score_metric_candidate"
                if score_values
                else "office_quota_competition_candidate"
            ),
            "metricCount": len(score_values),
            "hasOutcomeScore": bool(score_values),
        }
    return None


def has_office_quota_context(text: str) -> bool:
    return bool(
        re.search(r"모집\s*인원|모집인원", text)
        or re.search(r"모집\s+등록\s+충원", text)
        or re.search(r"모집\s*단위\s*경쟁률\s*인원", text)
    )


def extract_office_additional_pass_for_direct_competition(
    full_text: str, tokens_after_competition: list[dict[str, Any]]
) -> int | None:
    if not re.search(r"예비|충원", full_text):
        return None
    if re.search(r"등록", full_text):
        score_start_index = first_plausible_office_score_token_index(
            tokens_after_competition, full_text
        )
        candidate_tokens = (
            tokens_after_competition[:score_start_index]
            if score_start_index is not None
            else tokens_after_competition
        )
        integer_values = [
            value
            for value in (office_integer_token_value(token) for token in candidate_tokens)
            if is_plausible_office_additional_pass_value(value)
        ]
        if len(integer_values) >= 2:
            return integer_values[1]
        if integer_values:
            return integer_values[0]
    return extract_office_additional_pass_after_scores(full_text, tokens_after_competition)


def office_outcome_number_tokens(segment: str) -> list[dict[str, Any]]:
    tokens: list[dict[str, Any]] = []
    for match in OFFICE_OUTCOME_NUMBER_PATTERN.finditer(segment):
        value = number_or_none(match.group(1))
        if value is None:
            continue
        tokens.append(
            {
                "raw": match.group(0),
                "value": float(value),
                "start": match.start(),
                "end": match.end(),
                "isRatio": bool(re.search(r":\s*1", match.group(0))),
                "isOrdinalSuffix": bool(re.match(r"\s*번", segment[match.end() :])),
            }
        )
    return tokens


def office_integer_token_value(token: dict[str, Any]) -> int | None:
    value = float(token.get("value") or 0)
    if not value.is_integer():
        return None
    return int(value)


def is_office_competition_token(token: dict[str, Any], quota: int, applicants: int) -> bool:
    competition = float(token.get("value") or 0)
    if competition <= 0:
        return False
    computed = applicants / quota
    close_enough = abs(computed - competition) <= max(0.08, abs(competition) * 0.035)
    return close_enough and (bool(token.get("isRatio")) or "." in str(token.get("raw")) or competition > 1)


def extract_office_additional_pass(
    segment: str,
    full_text: str,
    tokens: list[dict[str, Any]],
    competition_index: int,
    quota_index: int,
) -> int | None:
    explicit = re.search(r"예비\s*(\d{1,4})", segment)
    if explicit:
        return int_or_none(explicit.group(1))
    if not re.search(r"예비|충원", full_text):
        return None
    if competition_index + 1 >= len(tokens):
        return None
    if re.search(r"등록\s*인원|등록인원", full_text) and re.search(
        r"예비\s*순위|예비순위|최종\s*예비|충원", full_text
    ):
        tokens_after_competition = tokens[competition_index + 1 :]
        score_start_index = first_plausible_office_score_token_index(
            tokens_after_competition, full_text
        )
        candidate_tokens = (
            tokens_after_competition[:score_start_index]
            if score_start_index is not None
            else tokens_after_competition
        )
        integer_values = [
            value
            for value in (office_integer_token_value(token) for token in candidate_tokens)
            if is_plausible_office_additional_pass_value(value)
        ]
        if competition_index == quota_index + 2:
            return integer_values[1] if len(integer_values) >= 2 else None
        return integer_values[0] if integer_values else None
    value = office_integer_token_value(tokens[competition_index + 1])
    if is_plausible_office_additional_pass_value(value):
        return value
    return None


def extract_office_additional_pass_after_scores(
    full_text: str, tokens_after_competition: list[dict[str, Any]]
) -> int | None:
    if not re.search(r"예비|충원", full_text):
        return None
    for token in reversed(tokens_after_competition):
        value = office_integer_token_value(token)
        if is_plausible_office_additional_pass_value(value):
            return value
    return None


def is_plausible_office_additional_pass_value(value: int | None) -> bool:
    return bool(
        value is not None
        and 0 <= value <= 5000
        and not (RECENT_YEAR_MIN <= value <= RECENT_YEAR_MAX)
    )


def extract_office_score_values(tokens: list[dict[str, Any]], full_text: str) -> list[str]:
    if not OFFICE_OUTCOME_SCORE_CONTEXT.search(full_text):
        return []
    paired_percentile_total = bool(
        re.search(r"수능\s*백분위|백분위", full_text)
        and re.search(r"전형\s*총점|총점", full_text)
    )
    if paired_percentile_total:
        metric_values: list[float] = []
        score_start_index = first_plausible_office_score_token_index(tokens, full_text)
        if score_start_index is None:
            return []
        for token in tokens[score_start_index:]:
            value = float(token.get("value") or 0)
            if token.get("isOrdinalSuffix"):
                continue
            if value < 1 or value > 1000:
                continue
            if int(value) in range(RECENT_YEAR_MIN, RECENT_YEAR_MAX + 2):
                continue
            metric_values.append(value)
        values: list[str] = []
        for index, value in enumerate(metric_values):
            if index % 2 == 0 and value <= 100:
                add_score_value(values, value)
            if len(values) >= 8:
                break
        return values
    values: list[str] = []
    for token in tokens:
        raw_value = str(token.get("raw") or "")
        value = float(token.get("value") or 0)
        if token.get("isOrdinalSuffix"):
            continue
        if value < 1:
            continue
        if int(value) in range(RECENT_YEAR_MIN, RECENT_YEAR_MAX + 2):
            continue
        if value.is_integer() and "." not in raw_value and value <= 100:
            continue
        if re.search(r"등급", full_text) and 1 <= value <= 9.99:
            add_score_value(values, value)
        elif re.search(r"환산|백분위|표준점수|점수", full_text) and value <= 1000:
            add_score_value(values, value)
        elif "." in raw_value and re.search(r"평균|최저|최고|cut", full_text, re.I) and value <= 1000:
            add_score_value(values, value)
        elif not value.is_integer() and value <= 100:
            add_score_value(values, value)
        if len(values) >= 8:
            break
    return values


def first_plausible_office_score_token_index(
    tokens: list[dict[str, Any]], full_text: str = ""
) -> int | None:
    for index, token in enumerate(tokens):
        value = float(token.get("value") or 0)
        raw_value = normalize_text(token.get("raw"))
        if re.search(r"등급", full_text) and "." in raw_value and 0 < value <= 9.99:
            return index
        if value >= 50:
            return index
    return None


def add_score_value(values: list[str], value: float) -> None:
    text = number_string(value)
    if text not in values:
        values.append(text)


def infer_recruitment_group_near_outcome_unit(text: str, unit_name: str, segment: str) -> str:
    inferred = infer_recruitment_group_near_unit(text, unit_name)
    if inferred != "none":
        return inferred
    group_match = re.search(r"(?:^|\s)([가나다])\s*군?(?=\s|\d|$)", segment[:36])
    if not group_match:
        return "none"
    return {"가": "ga", "나": "na", "다": "da"}.get(group_match.group(1), "none")


def is_year_like_number(value: Any) -> bool:
    numeric = number_or_none(value)
    if numeric is None:
        return False
    number = float(numeric)
    return number.is_integer() and 1900 <= int(number) <= 2100


def is_noisy_adiga_outcome_row(row: dict[str, Any]) -> bool:
    unit_name = normalize_text(row.get("admissionUnitName"))
    if re.search(r"(?:19|20)\d{2}\s*학년도\s*모집", unit_name):
        return True
    for field in ("quota", "competitionRate", "additionalPass"):
        if is_year_like_number(row.get(field)):
            return True
    return False


ADIGA_VISUAL_OUTCOME_OCR_KEYS = {
    ("0000004", 2026),  # 강원대학교: ADIGA image OCR rows left in visual/OCR queue.
    ("0000215", 2026),  # 가톨릭꽃동네대학교: ADIGA image OCR row left in visual/OCR queue.
}


def build_adiga_ocr_historical_outcome_rows(
    adiga_ocr_evidence_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in adiga_ocr_evidence_rows:
        if not is_adiga_visual_outcome_ocr_source(row):
            continue
        ref = first_adiga_ocr_reference(row)
        if not ref:
            continue
        year = int_or_none(ref.get("year") or ref.get("admissionYear"))
        unv_cd = normalize_text(ref.get("unvCd"))
        university_name = normalize_text(ref.get("universityName"))
        if not unv_cd or not university_name or year is None:
            continue
        text = normalize_text(row.get("text") or row.get("textPreview"))
        entries = parse_adiga_visual_outcome_ocr_entries(text)
        for entry in entries:
            unit_name = entry["unitName"]
            parsed = entry["parsed"]
            dedupe_key = (
                unv_cd,
                year,
                canonical_name(unit_name),
                entry["recruitmentGroup"],
                number_string(parsed.get("quota")),
                number_string(parsed.get("competitionRate")),
                number_string(parsed.get("additionalPass")),
                number_string(parsed.get("avgScoreCandidate")),
                number_string(parsed.get("cutScoreCandidate")),
                normalize_text(row.get("evidenceSha256")),
                entry["rowIndex"],
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            rows.append(
                {
                    "unvCd": unv_cd,
                    "universityName": university_name,
                    "year": year,
                    "admissionUnitName": unit_name,
                    "admissionUnitCanonicalCandidate": canonical_name(unit_name),
                    "recruitmentGroup": entry["recruitmentGroup"],
                    "quota": parsed.get("quota"),
                    "competitionRate": parsed.get("competitionRate"),
                    "additionalPass": parsed.get("additionalPass"),
                    "convertedScore50Cut": parsed.get("convertedScore50Cut"),
                    "convertedScore70Cut": parsed.get("convertedScore70Cut"),
                    "totalScore": parsed.get("totalScore"),
                    "avgScoreCandidate": parsed.get("avgScoreCandidate"),
                    "cutScoreCandidate": parsed.get("cutScoreCandidate"),
                    "percentileCutCandidate": parsed.get("percentileCutCandidate"),
                    "scoreAvailability": parsed["scoreAvailability"],
                    "metricCount": parsed["metricCount"],
                    "subjectMetricCount": 0,
                    "hasQuotaAndCompetition": parsed["hasQuotaAndCompetition"],
                    "hasOutcomeScore": parsed["hasOutcomeScore"],
                    "candidateSha256": normalize_text(row.get("evidenceSha256")),
                    "sourceProvider": "adiga",
                    "sourceConfidence": "source_preserving_adiga_image_ocr_visual_outcome_review",
                    "sourceUrl": normalize_text(ref.get("detailSourceUrl")),
                    "rawPath": normalize_text(row.get("rawImagePath")),
                    "sectionId": normalize_text(row.get("evidenceRole")),
                    "tableIndex": normalize_text(row.get("canonicalImageKey")),
                    "rowIndex": entry["rowIndex"],
                    "reviewStatus": normalize_text(row.get("reviewStatus"))
                    or "needs_human_verification",
                }
            )
    return rows


def is_adiga_visual_outcome_ocr_source(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("evidenceTarget")) != "HistoricalOutcome":
        return False
    if normalize_text(row.get("evidenceType")) != "image_ocr":
        return False
    if normalize_text(row.get("evidenceRole")) not in {
        "admission_result_image",
        "score_distribution_image",
    }:
        return False
    ref = first_adiga_ocr_reference(row)
    if not ref:
        return False
    year = int_or_none(ref.get("year") or ref.get("admissionYear"))
    if (normalize_text(ref.get("unvCd")), year) not in ADIGA_VISUAL_OUTCOME_OCR_KEYS:
        return False
    text = normalize_text(row.get("text") or row.get("textPreview"))
    return bool("<tr" in text and "<td" in text and re.search(r"모집|경쟁|환산|cut|등급", text, re.I))


def first_adiga_ocr_reference(row: dict[str, Any]) -> dict[str, Any]:
    refs = row.get("sampleReferences") or []
    return refs[0] if refs and isinstance(refs[0], dict) else {}


def parse_adiga_visual_outcome_ocr_entries(text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    table_rows = office_html_table_grid(repair_incomplete_adiga_ocr_html_table(text))
    for row_index, cells in enumerate(table_rows):
        cells = [cell for cell in cells if cell or cell == "0"]
        if len(cells) < 4:
            continue
        unit_index, unit_name = office_html_table_unit_cell(cells)
        if unit_index is None or not unit_name:
            continue
        parsed = parse_adiga_visual_outcome_ocr_cells(cells[unit_index + 1 :])
        if parsed is None:
            continue
        entries.append(
            {
                "unitName": unit_name,
                "recruitmentGroup": office_html_table_recruitment_group(cells[: unit_index + 1]),
                "rowIndex": row_index,
                "parsed": parsed,
            }
        )
    return entries


def repair_incomplete_adiga_ocr_html_table(text: str) -> str:
    repaired = re.sub(r"<\s*$", "", text)
    if repaired.count("<tr") > repaired.count("</tr>"):
        if repaired.count("<td") + repaired.count("<th") > repaired.count("</td>") + repaired.count("</th>"):
            repaired += "</td>"
        repaired += "</tr>"
    if repaired.count("<tbody") > repaired.count("</tbody>"):
        repaired += "</tbody>"
    if repaired.count("<table") > repaired.count("</table>"):
        repaired += "</table>"
    return repaired


def parse_adiga_visual_outcome_ocr_cells(cells: list[str]) -> dict[str, Any] | None:
    quota_index = first_adiga_visual_quota_index(cells)
    if quota_index is None or quota_index + 1 >= len(cells):
        return None
    quota = office_html_integer_cell_value(cells[quota_index])
    competition = office_html_competition_cell_value(cells[quota_index + 1])
    if quota is None or competition is None:
        return None
    if quota <= 0 or competition <= 0:
        return None
    metric_cells = cells[quota_index + 2 :]
    additional_pass = first_adiga_visual_additional_pass(metric_cells)
    score_cells = metric_cells[1:] if additional_pass is not None else metric_cells
    score_values = [
        value
        for value in (office_html_score_cell_value(cell) for cell in score_cells)
        if value is not None and not is_year_like_number(value)
    ]
    if not score_values and competition is None:
        return None
    total_score = first_total_score_value(score_values)
    score_values_without_total = [
        value for value in score_values if total_score is None or value != total_score
    ]
    converted_score50 = first_score_at_or_above(score_values_without_total, 20)
    converted_score70 = second_score_at_or_above(score_values_without_total, 20)
    grade_values = [value for value in score_values if 0 < value <= 9.99]
    avg_score = grade_values[0] if grade_values else converted_score50
    cut_score = grade_values[1] if len(grade_values) > 1 else converted_score70 or avg_score
    has_outcome_score = bool(score_values)
    return {
        "quota": quota,
        "competitionRate": round(float(competition), 2),
        "additionalPass": additional_pass,
        "convertedScore50Cut": number_string(converted_score50),
        "convertedScore70Cut": number_string(converted_score70),
        "totalScore": number_string(total_score),
        "avgScoreCandidate": number_string(avg_score),
        "cutScoreCandidate": number_string(cut_score),
        "percentileCutCandidate": number_string(cut_score if grade_values else ""),
        "scoreAvailability": (
            "adiga_image_ocr_quota_competition_score_candidate"
            if has_outcome_score
            else "adiga_image_ocr_quota_competition_candidate"
        ),
        "metricCount": len(score_values),
        "hasQuotaAndCompetition": True,
        "hasOutcomeScore": has_outcome_score,
    }


def first_adiga_visual_quota_index(cells: list[str]) -> int | None:
    for index in range(min(len(cells), 4)):
        quota = office_html_integer_cell_value(cells[index])
        competition = (
            office_html_competition_cell_value(cells[index + 1])
            if index + 1 < len(cells)
            else None
        )
        if quota is not None and quota > 0 and competition is not None and competition > 0:
            return index
    return None


def first_adiga_visual_additional_pass(cells: list[str]) -> int | None:
    if not cells:
        return None
    value = office_html_integer_cell_value(cells[0])
    if value is None or is_year_like_number(value):
        return None
    return value


def first_score_at_or_above(values: list[float], minimum: float) -> float | None:
    return next((value for value in values if value >= minimum), None)


def second_score_at_or_above(values: list[float], minimum: float) -> float | None:
    matches = [value for value in values if value >= minimum]
    return matches[1] if len(matches) > 1 else None


def first_total_score_value(values: list[float]) -> float | None:
    for value in values:
        if value in {100, 200, 300, 500, 600, 700, 800, 1000}:
            return value
    return None


def clean_adiga_score_value(value: Any) -> Any:
    numeric = number_or_none(value)
    if numeric is None:
        return value
    if 0 < float(numeric) < 1:
        return None
    return value


def clean_adiga_competition_rate(value: Any) -> Any:
    numeric = number_or_none(value)
    if numeric is None:
        return value
    number = float(numeric)
    if number < 0 or number > 300:
        return ""
    return value


def make_outcome_candidate(unit: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    candidate_sha = normalize_text(row.get("candidateSha256"))
    competition_rate = clean_adiga_competition_rate(row.get("competitionRate"))
    converted_score50_cut = clean_adiga_score_value(row.get("convertedScore50Cut"))
    converted_score70_cut = clean_adiga_score_value(row.get("convertedScore70Cut"))
    total_score = clean_adiga_score_value(row.get("totalScore"))
    percentile70_average = clean_adiga_score_value(row.get("percentile70Average"))
    return {
        "outcomeCandidateId": deterministic_uuid(f"historical-outcome:{candidate_sha}"),
        "unitCandidateId": unit["unitCandidateId"],
        "universityCandidateId": unit["universityCandidateId"],
        "unvCd": unit["unvCd"],
        "universityName": unit["universityName"],
        "year": int_or_none(row.get("year")),
        "admissionUnitName": normalize_text(row.get("admissionUnitName")),
        "admissionUnitCanonicalName": unit["admissionUnitCanonicalName"],
        "recruitmentGroup": unit["recruitmentGroup"],
        "quota": row.get("quota"),
        "competitionRate": competition_rate,
        "additionalPass": int_or_none(row.get("additionalPass")),
        "convertedScore50Cut": converted_score50_cut,
        "convertedScore70Cut": converted_score70_cut,
        "totalScore": total_score,
        "percentile70Average": percentile70_average,
        "avgScoreCandidate": percentile70_average,
        "cutScoreCandidate": converted_score70_cut or converted_score50_cut,
        "percentileCutCandidate": percentile70_average,
        "scoreAvailability": normalize_text(row.get("scoreAvailability")),
        "metricCount": int_or_none(row.get("metricCount")) or 0,
        "subjectMetricCount": int_or_none(row.get("subjectMetricCount")) or 0,
        "hasQuotaAndCompetition": bool(row.get("hasQuotaAndCompetition") and competition_rate != ""),
        "hasOutcomeScore": bool(row.get("hasOutcomeScore")),
        "confidence": confidence_for(row),
        "sourceProvider": "adiga",
        "sourceConfidence": normalize_text(row.get("sourceConfidence")),
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "rawPath": normalize_text(row.get("rawPath")),
        "sectionId": normalize_text(row.get("sectionId")),
        "tableIndex": int_or_none(row.get("tableIndex")),
        "rowIndex": int_or_none(row.get("rowIndex")),
        "sourceCandidateSha256": candidate_sha,
        "reviewStatus": "needs_human_verification",
    }


def make_adiga_ocr_outcome_candidate(unit: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    candidate_sha = normalize_text(row.get("candidateSha256"))
    identity = "|".join(
        [
            candidate_sha,
            unit["unitCandidateId"],
            number_string(row.get("quota")),
            number_string(row.get("competitionRate")),
            normalize_text(row.get("sectionId")),
            normalize_text(row.get("rowIndex")),
        ]
    )
    return {
        "outcomeCandidateId": deterministic_uuid(f"historical-outcome:adiga-ocr:{identity}"),
        "unitCandidateId": unit["unitCandidateId"],
        "universityCandidateId": unit["universityCandidateId"],
        "unvCd": unit["unvCd"],
        "universityName": unit["universityName"],
        "year": int_or_none(row.get("year")),
        "admissionUnitName": normalize_text(row.get("admissionUnitName")),
        "admissionUnitCanonicalName": unit["admissionUnitCanonicalName"],
        "recruitmentGroup": unit["recruitmentGroup"],
        "quota": row.get("quota"),
        "competitionRate": row.get("competitionRate"),
        "additionalPass": int_or_none(row.get("additionalPass")),
        "convertedScore50Cut": normalize_text(row.get("convertedScore50Cut")),
        "convertedScore70Cut": normalize_text(row.get("convertedScore70Cut")),
        "totalScore": normalize_text(row.get("totalScore")),
        "percentile70Average": "",
        "avgScoreCandidate": normalize_text(row.get("avgScoreCandidate")),
        "cutScoreCandidate": normalize_text(row.get("cutScoreCandidate")),
        "percentileCutCandidate": normalize_text(row.get("percentileCutCandidate")),
        "scoreAvailability": normalize_text(row.get("scoreAvailability")),
        "metricCount": int_or_none(row.get("metricCount")) or 0,
        "subjectMetricCount": int_or_none(row.get("subjectMetricCount")) or 0,
        "hasQuotaAndCompetition": bool(row.get("hasQuotaAndCompetition")),
        "hasOutcomeScore": bool(row.get("hasOutcomeScore")),
        "confidence": "limited",
        "sourceProvider": "adiga",
        "sourceConfidence": normalize_text(row.get("sourceConfidence")),
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "rawPath": normalize_text(row.get("rawPath")),
        "sectionId": normalize_text(row.get("sectionId")),
        "tableIndex": normalize_text(row.get("tableIndex")),
        "rowIndex": int_or_none(row.get("rowIndex")),
        "sourceCandidateSha256": candidate_sha,
        "reviewStatus": normalize_text(row.get("reviewStatus")) or "needs_human_verification",
    }


def make_office_outcome_candidate(unit: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    candidate_sha = normalize_text(row.get("candidateSha256"))
    identity = "|".join(
        [
            candidate_sha,
            unit["unitCandidateId"],
            number_string(row.get("quota")),
            number_string(row.get("competitionRate")),
            normalize_text(row.get("sectionId")),
            normalize_text(row.get("rowIndex")),
        ]
    )
    return {
        "outcomeCandidateId": deterministic_uuid(f"historical-outcome:office:{identity}"),
        "unitCandidateId": unit["unitCandidateId"],
        "universityCandidateId": unit["universityCandidateId"],
        "unvCd": unit["unvCd"],
        "universityName": unit["universityName"],
        "year": int_or_none(row.get("year")),
        "admissionUnitName": normalize_text(row.get("admissionUnitName")),
        "admissionUnitCanonicalName": unit["admissionUnitCanonicalName"],
        "recruitmentGroup": unit["recruitmentGroup"],
        "quota": row.get("quota"),
        "competitionRate": row.get("competitionRate"),
        "additionalPass": int_or_none(row.get("additionalPass")),
        "convertedScore50Cut": "",
        "convertedScore70Cut": "",
        "totalScore": "",
        "percentile70Average": "",
        "avgScoreCandidate": normalize_text(row.get("avgScoreCandidate")),
        "cutScoreCandidate": normalize_text(row.get("cutScoreCandidate")),
        "percentileCutCandidate": normalize_text(row.get("percentileCutCandidate")),
        "scoreAvailability": normalize_text(row.get("scoreAvailability")),
        "metricCount": int_or_none(row.get("metricCount")) or 0,
        "subjectMetricCount": int_or_none(row.get("subjectMetricCount")) or 0,
        "hasQuotaAndCompetition": bool(row.get("hasQuotaAndCompetition")),
        "hasOutcomeScore": bool(row.get("hasOutcomeScore")),
        "confidence": "limited",
        "sourceProvider": "university-admission-office",
        "sourceConfidence": normalize_text(row.get("sourceConfidence")),
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "rawPath": normalize_text(row.get("rawPath")),
        "sectionId": normalize_text(row.get("sectionId")),
        "tableIndex": int_or_none(row.get("tableIndex")),
        "rowIndex": int_or_none(row.get("rowIndex")),
        "sourceCandidateSha256": candidate_sha,
        "reviewStatus": normalize_text(row.get("reviewStatus")) or "needs_human_verification",
    }


def make_promotion_link(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "sourceProvider": "university-admission-office",
        "evidenceCandidateSha256": normalize_text(row.get("candidateSha256")),
        "unvCd": normalize_text(row.get("unvCd")),
        "universityName": normalize_text(row.get("universityName")),
        "campus": normalize_text(row.get("campus")),
        "evidenceTarget": normalize_text(row.get("evidenceTarget")),
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "evidenceTypes": join_values(row.get("evidenceTypes")),
        "collectionYears": join_values(row.get("collectionYears")),
        "detectedAdmissionYears": join_values(row.get("detectedAdmissionYears")),
        "evidenceCount": int_or_none(row.get("evidenceCount")) or 0,
        "reviewPriorityScore": int_or_none(row.get("reviewPriorityScore")) or 0,
        "textPreview": normalize_text(row.get("textPreview"))[:500],
        "sourceCandidateUrl": first(row.get("sourceCandidateUrls")),
        "attachmentUrl": first(row.get("attachmentUrls")),
        "rawPath": first(row.get("rawPaths")),
        "sourcePath": first(row.get("sourcePaths")),
        "sourceCandidateUrls": join_values(row.get("sourceCandidateUrls")),
        "attachmentUrls": join_values(row.get("attachmentUrls")),
        "rawPaths": join_values(row.get("rawPaths")),
        "sourcePaths": join_values(row.get("sourcePaths")),
        "sourceDocumentKinds": join_values(row.get("sourceDocumentKinds")),
        "sourceLinkRoles": join_values(row.get("sourceLinkRoles")),
        "sourceLabels": join_values(row.get("sourceLabels")),
        "sourceRowCount": int_or_none(row.get("sourceRowCount")) or 1,
        "duplicateSourceCount": int_or_none(row.get("duplicateSourceCount")) or 0,
        "reviewStatus": normalize_text(row.get("reviewStatus")) or "needs_human_verification",
    }


def build_manual_admission_unit_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, int, str, str]] = set()
    for row in rows:
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        year = int_or_none(row.get("admissionYear") or row.get("year"))
        unit_name = normalize_text(row.get("admissionUnitName"))
        if not unv_cd or not university_name or not year or not unit_name:
            continue
        recruitment_group = recruitment_group_value(row.get("recruitmentGroup"))
        canonical_unit = normalize_text(row.get("admissionUnitCanonicalCandidate")) or canonical_name(
            unit_name
        )
        key = (unv_cd, year, recruitment_group, canonical_unit)
        if key in seen:
            continue
        seen.add(key)
        source_sha = normalize_text(row.get("sourceSha256") or row.get("candidateSha256"))
        identity = "|".join(
            [
                unv_cd,
                str(year),
                recruitment_group,
                canonical_unit,
                source_sha,
                normalize_text(row.get("sourceUrl")),
            ]
        )
        output.append(
            {
                "unvCd": unv_cd,
                "universityName": university_name,
                "year": year,
                "admissionUnitName": unit_name,
                "admissionUnitCanonicalCandidate": canonical_unit,
                "recruitmentGroup": recruitment_group,
                "quota": normalize_text(row.get("quota")),
                "candidateSha256": normalize_text(row.get("candidateSha256"))
                or deterministic_hash(f"manual-admission-unit:{identity}"),
                "sourceProvider": "university-admission-office",
            }
        )
    return output


def build_manual_admission_office_evidence_links(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        unv_cd = normalize_text(row.get("unvCd"))
        university_name = normalize_text(row.get("universityName"))
        detected_years = join_values(
            row.get("detectedAdmissionYears") or row.get("admissionYear") or row.get("year")
        )
        collection_years = join_values(row.get("collectionYears") or detected_years)
        source_url = normalize_text(row.get("sourceUrl"))
        source_label = normalize_text(row.get("sourceLabel")) or "manual_p0_official_source"
        raw_path = normalize_text(row.get("rawPath"))
        if not unv_cd or not university_name or not detected_years or not source_url:
            continue
        identity = "|".join(
            [
                unv_cd,
                detected_years,
                normalize_text(row.get("evidenceTarget")) or "AdmissionRule",
                normalize_text(row.get("evidenceRole")) or "manual_official_source",
                source_url,
                raw_path,
            ]
        )
        evidence_sha = normalize_text(row.get("evidenceCandidateSha256")) or deterministic_hash(
            f"manual-admission-office-evidence:{identity}"
        )
        if evidence_sha in seen:
            continue
        seen.add(evidence_sha)
        output.append(
            {
                "sourceProvider": "university-admission-office",
                "evidenceCandidateSha256": evidence_sha,
                "unvCd": unv_cd,
                "universityName": university_name,
                "campus": normalize_text(row.get("campus")),
                "evidenceTarget": normalize_text(row.get("evidenceTarget")) or "AdmissionRule",
                "evidenceRole": normalize_text(row.get("evidenceRole")) or "manual_official_source",
                "evidenceTypes": normalize_text(row.get("evidenceTypes")) or "manual_source",
                "collectionYears": collection_years,
                "detectedAdmissionYears": detected_years,
                "evidenceCount": int_or_none(row.get("evidenceCount")) or 1,
                "reviewPriorityScore": int_or_none(row.get("reviewPriorityScore")) or 80,
                "textPreview": normalize_text(row.get("textPreview") or row.get("note"))[:500],
                "sourceCandidateUrl": source_url,
                "attachmentUrl": normalize_text(row.get("attachmentUrl") or source_url),
                "rawPath": raw_path,
                "sourcePath": normalize_text(row.get("sourcePath") or raw_path),
                "sourceCandidateUrls": source_url,
                "attachmentUrls": normalize_text(row.get("attachmentUrl") or source_url),
                "rawPaths": raw_path,
                "sourcePaths": normalize_text(row.get("sourcePath") or raw_path),
                "sourceDocumentKinds": normalize_text(row.get("sourceDocumentKinds")) or "manual_pdf",
                "sourceLinkRoles": normalize_text(row.get("sourceLinkRoles")) or "implementation_plan",
                "sourceLabels": source_label,
                "sourceRowCount": int_or_none(row.get("sourceRowCount")) or 1,
                "duplicateSourceCount": int_or_none(row.get("duplicateSourceCount")) or 0,
                "reviewStatus": normalize_text(row.get("reviewStatus")) or "needs_human_verification",
            }
        )
    return output


def build_admission_rule_candidates(
    promotion_rows: list[dict[str, Any]],
    adiga_rule_table_rows: list[dict[str, Any]],
    adiga_ocr_evidence_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in promotion_rows:
        if normalize_text(row.get("evidenceTarget")) == "AdmissionRule":
            candidates.append(make_rule_candidate_from_promotion(row))
    for row in adiga_rule_table_rows:
        if is_adiga_rule_table(row):
            candidates.append(make_rule_candidate_from_adiga_table(row))
    for row in adiga_ocr_evidence_rows:
        if is_adiga_ocr_rule_candidate(row):
            candidates.append(make_rule_candidate_from_adiga_ocr(row))
    return candidates


def is_adiga_ocr_rule_candidate(row: dict[str, Any]) -> bool:
    if normalize_text(row.get("evidenceTarget")) == "AdmissionRule":
        return True
    role = normalize_text(row.get("evidenceRole"))
    if role not in {"admission_result_image", "score_distribution_image"}:
        return False
    text = normalize_text(row.get("text") or row.get("textPreview"))
    if not text:
        return False
    formula_terms = [
        r"\\frac",
        "반영과목",
        "이수단위",
        "석차등급",
        "성취평가",
        "환산",
        "교과점수",
        "교과형수",
        "기본점수",
        "실질반영",
        "산출",
    ]
    return any(term in text for term in formula_terms) or bool(detect_formula_signals(text))


def is_adiga_rule_table(row: dict[str, Any]) -> bool:
    return normalize_text(row.get("tableRole")) in {"csat_rule", "student_rule", "common"}


def make_rule_candidate_from_promotion(row: dict[str, Any]) -> dict[str, Any]:
    text = normalize_text(row.get("sampleText") or row.get("textPreview"))
    evidence_role = normalize_text(row.get("evidenceRole"))
    candidate_id = normalize_text(row.get("candidateSha256"))
    return {
        "ruleCandidateId": deterministic_uuid(f"admission-rule:promotion:{candidate_id}"),
        "sourceProvider": "university-admission-office",
        "artifactType": "foundation_admission_rule_review_candidate",
        "sourceEvidenceId": candidate_id,
        "unvCd": normalize_text(row.get("unvCd")),
        "universityName": normalize_text(row.get("universityName")),
        "campus": normalize_text(row.get("campus")),
        "admissionYears": join_values(row.get("detectedAdmissionYears")),
        "collectionYears": join_values(row.get("collectionYears")),
        "ruleCategory": infer_rule_category(evidence_role, "", text),
        "evidenceRole": evidence_role,
        "evidenceType": join_values(row.get("evidenceTypes")),
        "sourceDocumentKind": join_values(row.get("sourceDocumentKinds")),
        "reviewPriorityScore": int_or_none(row.get("reviewPriorityScore")) or 0,
        "evidenceCount": int_or_none(row.get("evidenceCount")) or 0,
        "detectedSignals": "|".join(detect_rule_signals(text)),
        "percentageValues": "|".join(extract_percentages(text)),
        "weightValues": "|".join(extract_weight_values(text)),
        "scoreMetricSignals": "|".join(detect_score_metric_signals(text)),
        "subjectSignals": "|".join(detect_subject_signals(text)),
        "formulaSignals": "|".join(detect_formula_signals(text)),
        "textPreview": normalize_text(row.get("textPreview") or text)[:500],
        "sourceUrl": first(row.get("sourceCandidateUrls")),
        "attachmentUrl": first(row.get("attachmentUrls")),
        "rawPath": first(row.get("rawPaths")),
        "sourcePath": first(row.get("sourcePaths")),
        "sourceUrls": join_values(row.get("sourceCandidateUrls")),
        "attachmentUrls": join_values(row.get("attachmentUrls")),
        "rawPaths": join_values(row.get("rawPaths")),
        "sourcePaths": join_values(row.get("sourcePaths")),
        "sourceLabels": join_values(row.get("sourceLabels")),
        "sourceRowCount": int_or_none(row.get("sourceRowCount")) or 1,
        "duplicateSourceCount": int_or_none(row.get("duplicateSourceCount")) or 0,
        "tableSha256": "",
        "sectionLabel": "",
        "tableRole": "",
        "tableIndex": "",
        "rows": "",
        "cols": "",
        "reviewStatus": normalize_text(row.get("reviewStatus")) or "needs_human_verification",
    }


def make_rule_candidate_from_adiga_table(row: dict[str, Any]) -> dict[str, Any]:
    text = normalize_text(row.get("textSnippet") or row.get("headerText"))
    table_role = normalize_text(row.get("tableRole"))
    table_sha = normalize_text(row.get("tableSha256"))
    return {
        "ruleCandidateId": deterministic_uuid(f"admission-rule:adiga-table:{table_sha}"),
        "sourceProvider": "adiga",
        "artifactType": "foundation_admission_rule_review_candidate",
        "sourceEvidenceId": table_sha,
        "unvCd": normalize_text(row.get("unvCd")),
        "universityName": normalize_text(row.get("universityName")),
        "campus": "",
        "admissionYears": join_values([row.get("year")]),
        "collectionYears": join_values([row.get("year")]),
        "ruleCategory": infer_rule_category("", table_role, text),
        "evidenceRole": table_role,
        "evidenceType": "html_table",
        "sourceDocumentKind": "adiga_selection_html",
        "reviewPriorityScore": adiga_table_priority(table_role, text),
        "evidenceCount": 1,
        "detectedSignals": "|".join(detect_rule_signals(text)),
        "percentageValues": "|".join(extract_percentages(text)),
        "weightValues": "|".join(extract_weight_values(text)),
        "scoreMetricSignals": "|".join(detect_score_metric_signals(text)),
        "subjectSignals": "|".join(detect_subject_signals(text)),
        "formulaSignals": "|".join(detect_formula_signals(text)),
        "textPreview": text[:500],
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "attachmentUrl": "",
        "rawPath": normalize_text(row.get("rawPath")),
        "sourcePath": "",
        "tableSha256": table_sha,
        "sectionLabel": normalize_text(row.get("sectionLabel")),
        "tableRole": table_role,
        "tableIndex": int_or_none(row.get("tableIndex")),
        "rows": int_or_none(row.get("rows")),
        "cols": int_or_none(row.get("cols")),
        "reviewStatus": "needs_human_verification",
    }


def make_rule_candidate_from_adiga_ocr(row: dict[str, Any]) -> dict[str, Any]:
    text = normalize_text(row.get("text") or row.get("textPreview"))
    first_ref = (row.get("sampleReferences") or [{}])[0]
    evidence_id = normalize_text(row.get("evidenceSha256") or row.get("rawImageSha256"))
    return {
        "ruleCandidateId": deterministic_uuid(f"admission-rule:adiga-ocr:{evidence_id}"),
        "sourceProvider": "adiga",
        "artifactType": "foundation_admission_rule_review_candidate",
        "sourceEvidenceId": evidence_id,
        "unvCd": normalize_text(first_ref.get("unvCd")),
        "universityName": normalize_text(first_ref.get("universityName")),
        "campus": "",
        "admissionYears": join_values(row.get("years")),
        "collectionYears": join_values(row.get("years")),
        "ruleCategory": infer_rule_category(normalize_text(row.get("evidenceRole")), "image_ocr", text),
        "evidenceRole": normalize_text(row.get("evidenceRole")),
        "evidenceType": normalize_text(row.get("evidenceType")) or "image_ocr",
        "sourceDocumentKind": normalize_text(row.get("sourceDocumentKind")) or "adiga_image",
        "reviewPriorityScore": int_or_none(row.get("priorityScore")) or 0,
        "evidenceCount": int_or_none(row.get("sourceReferenceCount")) or 1,
        "detectedSignals": "|".join(detect_rule_signals(text)),
        "percentageValues": "|".join(extract_percentages(text)),
        "weightValues": "|".join(extract_weight_values(text)),
        "scoreMetricSignals": "|".join(detect_score_metric_signals(text)),
        "subjectSignals": "|".join(detect_subject_signals(text)),
        "formulaSignals": "|".join(detect_formula_signals(text)),
        "textPreview": normalize_text(row.get("textPreview") or text)[:500],
        "sourceUrl": normalize_text(first_ref.get("detailSourceUrl")),
        "attachmentUrl": normalize_text((row.get("sourceSpecific") or {}).get("imageUrl")),
        "rawPath": normalize_text(row.get("rawImagePath")),
        "sourcePath": normalize_text(row.get("sourcePath")),
        "tableSha256": "",
        "sectionLabel": "",
        "tableRole": "",
        "tableIndex": "",
        "rows": "",
        "cols": "",
        "reviewStatus": normalize_text(row.get("reviewStatus")) or "needs_human_verification",
    }


def build_academyinfo_summaries(
    rows: list[dict[str, Any]],
    adiga_name_index: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, int, str, str], dict[str, Any]] = {}
    for row in rows:
        university_name = normalize_text(row.get("universityName"))
        survey_year = int_or_none(row.get("surveyYear")) or 0
        relevance_role = normalize_text(row.get("relevanceRole"))
        output_kind = normalize_text(row.get("outputKindLabel"))
        key = (university_name, survey_year, relevance_role, output_kind)
        if key not in groups:
            canonical = canonical_name(university_name)
            matches = adiga_name_index.get(canonical, [])
            groups[key] = {
                "sourceProvider": "academyinfo",
                "summaryCandidateSha256": deterministic_hash(
                    f"academyinfo:{canonical}:{survey_year}:{relevance_role}:{output_kind}"
                ),
                "universityName": university_name,
                "universityNameCanonical": canonical,
                "matchedUnvCd": matches[0]["unvCd"] if len(matches) == 1 else "",
                "matchedUniversityName": matches[0]["universityName"] if len(matches) == 1 else "",
                "matchStatus": "unique_name_match" if len(matches) == 1 else "unmatched_or_ambiguous",
                "surveyYear": survey_year,
                "relevanceRole": relevance_role,
                "outputKind": output_kind,
                "sourceRows": 0,
                "metricValues": 0,
                "candidateSha256Samples": [],
                "sourceZipPaths": [],
                "csvPaths": [],
                "reviewStatus": "auxiliary_evidence_needs_review",
            }
        group = groups[key]
        group["sourceRows"] += 1
        group["metricValues"] += int_or_none(row.get("metricCount")) or 0
        add_limited(group["candidateSha256Samples"], row.get("candidateSha256"), 10)
        add_limited(group["sourceZipPaths"], row.get("sourceZipPath"), 5)
        add_limited(group["csvPaths"], row.get("csvPath"), 5)
    return list(groups.values())


def make_kice_grade_cut_candidate(row: dict[str, Any]) -> dict[str, Any]:
    key = "|".join(
        [
            field(row, "academic_year"),
            field(row, "exam_type"),
            field(row, "file_seq"),
            field(row, "subject_name_normalized"),
            field(row, "grade"),
            field(row, "source_row_number"),
            field(row, "source_column_number"),
        ]
    )
    return {
        "gradeCutCandidateId": deterministic_uuid(f"kice-grade-cut:{key}"),
        "sourceProvider": field(row, "provider") or "kice-suneung",
        "artifactType": field(row, "artifact_type") or "kice_grade_cut_candidate",
        "academicYear": int_or_none(field(row, "academic_year")),
        "examType": field(row, "exam_type"),
        "fileKind": field(row, "file_kind"),
        "scoreMetric": field(row, "score_metric"),
        "subjectArea": field(row, "subject_area"),
        "subjectName": field(row, "subject_name"),
        "subjectNameNormalized": field(row, "subject_name_normalized"),
        "subjectGroup": infer_kice_subject_group(field(row, "subject_name_normalized") or field(row, "subject_name")),
        "grade": int_or_none(field(row, "grade")),
        "cutScoreRaw": field(row, "cut_score_raw"),
        "cutScoreNumeric": number_or_none(field(row, "cut_score_numeric")),
        "cutScoreOperator": field(row, "cut_score_operator"),
        "testTakerCount": int_or_none(field(row, "test_taker_count")),
        "ratioPercent": number_or_none(field(row, "ratio_percent")),
        "valueStatus": field(row, "value_status"),
        "candidateConfidence": kice_candidate_confidence(field(row, "value_status")),
        "sourceAreaReviewFlag": source_area_review_flag(field(row, "subject_area")),
        "boardSeq": field(row, "board_seq"),
        "fileSeq": field(row, "file_seq"),
        "fileTitle": field(row, "file_title"),
        "sheetName": field(row, "sheet_name"),
        "sourceUrl": field(row, "source_url"),
        "viewUrl": field(row, "view_url"),
        "csvPath": field(row, "csv_path"),
        "sourceRowNumber": int_or_none(field(row, "source_row_number")),
        "sourceColumnNumber": int_or_none(field(row, "source_column_number")),
        "reviewStatus": "needs_human_verification",
    }


def make_kice_distribution_candidate(row: dict[str, Any]) -> dict[str, Any]:
    key = "|".join(
        [
            field(row, "academic_year"),
            field(row, "exam_type"),
            field(row, "file_seq"),
            field(row, "subject_name_normalized"),
            field(row, "standard_score"),
            field(row, "source_row_number"),
            field(row, "source_column_number"),
        ]
    )
    return {
        "distributionCandidateId": deterministic_uuid(f"kice-standard-score-distribution:{key}"),
        "sourceProvider": field(row, "provider") or "kice-suneung",
        "artifactType": field(row, "artifact_type") or "kice_standard_score_distribution_candidate",
        "academicYear": int_or_none(field(row, "academic_year")),
        "examType": field(row, "exam_type"),
        "subjectArea": field(row, "subject_area"),
        "subjectName": field(row, "subject_name"),
        "subjectNameNormalized": field(row, "subject_name_normalized"),
        "subjectGroup": infer_kice_subject_group(field(row, "subject_name_normalized") or field(row, "subject_name")),
        "standardScore": int_or_none(field(row, "standard_score")),
        "maleCount": int_or_none(field(row, "male_count")),
        "femaleCount": int_or_none(field(row, "female_count")),
        "totalCount": int_or_none(field(row, "total_count")),
        "cumulativeTotalCount": int_or_none(field(row, "cumulative_total_count")),
        "valueStatus": field(row, "value_status"),
        "candidateConfidence": kice_candidate_confidence(field(row, "value_status")),
        "sourceAreaReviewFlag": source_area_review_flag(field(row, "subject_area")),
        "boardSeq": field(row, "board_seq"),
        "fileSeq": field(row, "file_seq"),
        "fileTitle": field(row, "file_title"),
        "sheetName": field(row, "sheet_name"),
        "sourceUrl": field(row, "source_url"),
        "viewUrl": field(row, "view_url"),
        "csvPath": field(row, "csv_path"),
        "sourceRowNumber": int_or_none(field(row, "source_row_number")),
        "sourceColumnNumber": int_or_none(field(row, "source_column_number")),
        "reviewStatus": "needs_human_verification",
    }


def make_kice_press_evidence_link(row: dict[str, Any]) -> dict[str, Any]:
    snippet_sha = field(row, "snippetSha256")
    return {
        "sourceProvider": "kice-suneung",
        "evidenceCandidateSha256": snippet_sha,
        "academicYear": int_or_none(field(row, "academicYear")),
        "examType": field(row, "examType"),
        "snippetRole": field(row, "snippetRole"),
        "targetEntity": field(row, "targetEntity"),
        "reviewPriorityScore": int_or_none(field(row, "score")) or 0,
        "title": field(row, "title"),
        "fileTitle": field(row, "fileTitle"),
        "startLine": int_or_none(field(row, "startLine")),
        "endLine": int_or_none(field(row, "endLine")),
        "matchedKeywords": field(row, "matchedKeywords"),
        "snippetPreview": field(row, "snippetPreview")[:500],
        "textPath": field(row, "textPath"),
        "rawAttachmentPath": field(row, "rawAttachmentPath"),
        "sourceUrl": field(row, "sourceUrl"),
        "reviewStatus": "needs_human_verification",
    }


def make_kcue_policy_evidence_link(row: dict[str, Any]) -> dict[str, Any]:
    matched_keywords = row.get("matchedKeywords")
    return {
        "sourceProvider": "kcue",
        "evidenceCandidateSha256": normalize_text(row.get("snippetSha256")),
        "academicYear": int_or_none(row.get("academicYear")),
        "postedDate": normalize_text(row.get("postedDate")),
        "postIdx": normalize_text(row.get("idx")),
        "postRole": normalize_text(row.get("postRole")),
        "title": normalize_text(row.get("title")),
        "attachmentRole": normalize_text(row.get("attachmentRole")),
        "documentKind": normalize_text(row.get("documentKind")),
        "snippetRole": normalize_text(row.get("snippetRole")),
        "targetEntity": normalize_text(row.get("evidenceTarget")),
        "reviewPriorityScore": int_or_none(row.get("score")) or 0,
        "pageNumber": int_or_none(row.get("pageNumber")),
        "startLine": int_or_none(row.get("startLine")),
        "endLine": int_or_none(row.get("endLine")),
        "matchedKeywords": join_values(matched_keywords),
        "textPreview": normalize_text(row.get("textPreview"))[:500],
        "textPath": normalize_text(row.get("textPath")),
        "rawAttachmentPath": normalize_text(row.get("rawAttachmentPath")),
        "sourceUrl": normalize_text(row.get("sourceUrl")),
        "viewUrl": normalize_text(row.get("viewUrl")),
        "reviewStatus": normalize_text(row.get("reviewStatus")) or "needs_human_verification",
    }


def build_university_name_index(universities: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    index: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in universities.values():
        index[canonical_name(row.get("universityName"))].append(row)
    return index


def finalize_university(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "universityCandidateId": row["universityCandidateId"],
        "unvCd": row["unvCd"],
        "universityName": row["universityName"],
        "universityNameCanonical": row["universityNameCanonical"],
        "campus": row["campus"],
        "region": row["region"],
        "type": row["type"],
        "sourceProviders": "|".join(sorted(row["sourceProviders"])),
        "years": "|".join(str(v) for v in sorted(x for x in row["years"] if x is not None)),
        "adigaOutcomeRows": row["adigaOutcomeRows"],
        "admissionOfficeEvidenceCandidates": row["admissionOfficeEvidenceCandidates"],
        "admissionRuleReviewCandidates": row["admissionRuleReviewCandidates"],
        "academyinfoSummaryRows": row["academyinfoSummaryRows"],
        "reviewStatus": row["reviewStatus"],
    }


def finalize_unit(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "unitCandidateId": row["unitCandidateId"],
        "universityCandidateId": row["universityCandidateId"],
        "unvCd": row["unvCd"],
        "universityName": row["universityName"],
        "year": row["year"],
        "admissionUnitName": row["admissionUnitName"],
        "admissionUnitCanonicalName": row["admissionUnitCanonicalName"],
        "recruitmentGroup": row["recruitmentGroup"],
        "majorGroup": row["majorGroup"],
        "quotaCandidates": "|".join(sorted(row["quotaCandidates"])),
        "outcomeRows": row["outcomeRows"],
        "sourceProviders": "|".join(sorted(row["sourceProviders"])),
        "sourceCandidateSha256Values": "|".join(row["sourceCandidateSha256Values"]),
        "reviewStatus": row["reviewStatus"],
    }


def summarize(
    universities: list[dict[str, Any]],
    units: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
    promotion_links: list[dict[str, Any]],
    admission_rule_candidates: list[dict[str, Any]],
    academyinfo_summaries: list[dict[str, Any]],
    kice_grade_cuts: list[dict[str, Any]],
    kice_distributions: list[dict[str, Any]],
    kice_press_evidence: list[dict[str, Any]],
    kcue_policy_evidence: list[dict[str, Any]],
    raw_adiga_rows: list[dict[str, Any]],
    raw_promotion_rows: list[dict[str, Any]],
    promotion_source_counts: dict[str, int],
    raw_academyinfo_rows: list[dict[str, Any]],
    raw_adiga_rule_table_rows: list[dict[str, Any]],
    raw_adiga_ocr_evidence_rows: list[dict[str, Any]],
    raw_kice_grade_cut_rows: list[dict[str, Any]],
    raw_kice_distribution_rows: list[dict[str, Any]],
    raw_kice_press_snippet_rows: list[dict[str, Any]],
    raw_kcue_snippet_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_database_candidate_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceRows": {
            "adigaHistoricalOutcomeRows": len(raw_adiga_rows),
            "admissionOfficePromotionRows": len(raw_promotion_rows),
            "admissionOfficePromotionInputRows": promotion_source_counts.get(
                "admissionOfficePromotionInputRows", len(raw_promotion_rows)
            ),
            "admissionOfficePrimaryPromotionRows": promotion_source_counts.get(
                "admissionOfficePrimaryPromotionRows", 0
            ),
            "admissionOfficeGapHomepageFilePromotionRows": promotion_source_counts.get(
                "admissionOfficeGapHomepageFilePromotionRows", 0
            ),
            "admissionOfficeGapHomepageNestedHighValuePromotionRows": promotion_source_counts.get(
                "admissionOfficeGapHomepageNestedHighValuePromotionRows", 0
            ),
            "admissionOfficeGapHomepageRelatedDetailHighValuePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageRelatedDetailHighValuePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapHomepageCurrentFilePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageCurrentFilePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapHomepageCurrentRelatedDetailHighValueOfficialishPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageCurrentRelatedDetailHighValueOfficialishPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapHomepageLinksGoalPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageLinksGoalPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapHomepageLinksGoal2PromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageLinksGoal2PromotionRows",
                    0,
                )
            ),
            "admissionOfficeFailedHomepageRetryCurlFallbackPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeFailedHomepageRetryCurlFallbackPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapHomepageLinksNestedFilteredPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageLinksNestedFilteredPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapRelatedDetailFollowupCorePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapRelatedDetailFollowupCorePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapWorklistFetchedUncoveredPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapWorklistFetchedUncoveredPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapSyuRelatedDetailPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapSyuRelatedDetailPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapManualDcatholicPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualDcatholicPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapManualCalvinPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualCalvinPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapManualYtusPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualYtusPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapManualBpuPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualBpuPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapManualYoungsanPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualYoungsanPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapCrawlerReadyPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapCrawlerReadyPromotionRows", 0
            ),
            "admissionOfficeGapCrawlerDetailFetchPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapCrawlerDetailFetchPromotionRows", 0
            ),
            "admissionOfficeGapCrawlerAttachmentReadyRelatedDetailHighValuePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapCrawlerAttachmentReadyRelatedDetailHighValuePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapCrawlerResidualHiddenDownloadPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapCrawlerResidualHiddenDownloadPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapKwangshinCurrentUndergradHiddenDownloadPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapKwangshinCurrentUndergradHiddenDownloadPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapKwangshinCompetitionInlineOcrPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapKwangshinCompetitionInlineOcrPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapImageAttachmentOcrPromotionRows": (
                promotion_source_counts.get("admissionOfficeGapImageAttachmentOcrPromotionRows", 0)
            ),
            "admissionOfficeGapHomepageManualYewonPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageManualYewonPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapRelatedDetailReadyPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapRelatedDetailReadyPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapLinkReadyManualGnuPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapLinkReadyManualGnuPromotionRows",
                    0,
                )
            ),
            "admissionOfficeManualGnuArchivePromotionRows": (
                promotion_source_counts.get("admissionOfficeManualGnuArchivePromotionRows", 0)
            ),
            "admissionOfficeGapRenderedEuljiPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapRenderedEuljiPromotionRows", 0
            ),
            "admissionOfficeGapManualGjcPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualGjcPromotionRows", 0
            ),
            "admissionOfficeGapManualAnyangPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualAnyangPromotionRows", 0
            ),
            "admissionOfficeGapManualCatholicPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualCatholicPromotionRows", 0
            ),
            "admissionOfficeManualCatholicResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualCatholicResultsPromotionRows", 0
                )
            ),
            "admissionOfficeManualCatholicRegularResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualCatholicRegularResultsPromotionRows", 0
                )
            ),
            "admissionOfficeManualMjuRegularResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualMjuRegularResultsPromotionRows", 0
                )
            ),
            "admissionOfficeManualKonyangRegularResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualKonyangRegularResultsPromotionRows", 0
                )
            ),
            "admissionOfficeManualCauRegularResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualCauRegularResultsPromotionRows", 0
                )
            ),
            "admissionOfficeManualGwnuRegularResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualGwnuRegularResultsPromotionRows", 0
                )
            ),
            "admissionOfficeManualIccu2025ResultPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualIccu2025ResultPromotionRows", 0
                )
            ),
            "admissionOfficeManualIccuResultPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualIccuResultPromotionRows", 0
                )
            ),
            "admissionOfficeGapManualCatholicSongsinPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualCatholicSongsinPromotionRows", 0
                )
            ),
            "admissionOfficeGapManualScuPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualScuPromotionRows", 0
            ),
            "admissionOfficeGapManualJnuePromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualJnuePromotionRows", 0
            ),
            "admissionOfficeGapManualKyonggiPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualKyonggiPromotionRows", 0
            ),
            "admissionOfficeGapManualLtuPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualLtuPromotionRows", 0
            ),
            "admissionOfficeGapManualMokwonPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualMokwonPromotionRows", 0
            ),
            "admissionOfficeGapManualSkhuPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualSkhuPromotionRows", 0
            ),
            "admissionOfficeGapManualDonggukWisePromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualDonggukWisePromotionRows", 0
            ),
            "admissionOfficeGapManualKoreaSejongPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualKoreaSejongPromotionRows", 0
            ),
            "admissionOfficeGapManualKangwonPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualKangwonPromotionRows", 0
            ),
            "admissionOfficeGapManualDgauPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualDgauPromotionRows", 0
            ),
            "admissionOfficeGapManualDgauRecruitmentPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualDgauRecruitmentPromotionRows", 0
                )
            ),
            "admissionOfficeGapManualDgauResultInlineOcrPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualDgauResultInlineOcrPromotionRows", 0
                )
            ),
            "admissionOfficeGapManualKbtusPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualKbtusPromotionRows", 0
            ),
            "admissionOfficeManualHttpsHomepageRetryPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualHttpsHomepageRetryPromotionRows", 0
                )
            ),
            "admissionOfficeGapManualHanilPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualHanilPromotionRows", 0
            ),
            "admissionOfficeGapManualDongdukPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualDongdukPromotionRows", 0
            ),
            "admissionOfficeGapManualDankookPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualDankookPromotionRows", 0
            ),
            "admissionOfficeGapManualShinhanPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualShinhanPromotionRows", 0
            ),
            "admissionOfficeGapManualChosunPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualChosunPromotionRows", 0
            ),
            "admissionOfficeGapManualHsmuPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualHsmuPromotionRows", 0
            ),
            "admissionOfficeGapHomepageHsmuRetryPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapHomepageHsmuRetryPromotionRows", 0
            ),
            "admissionOfficeGapHomepageRetryExpandedFilesPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageRetryExpandedFilesPromotionRows", 0
                )
            ),
            "admissionOfficeGapManualKoreatechPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualKoreatechPromotionRows", 0
            ),
            "admissionOfficeGapManualKangnamPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualKangnamPromotionRows", 0
            ),
            "admissionOfficeGapManualPusanPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualPusanPromotionRows", 0
            ),
            "admissionOfficeGapManualJejunuPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualJejunuPromotionRows", 0
            ),
            "admissionOfficeGapManualDcuPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualDcuPromotionRows", 0
            ),
            "admissionOfficeGapManualCnuePromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualCnuePromotionRows", 0
            ),
            "admissionOfficeGapManualHanseoPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualHanseoPromotionRows", 0
            ),
            "admissionOfficeGapManualMtuPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualMtuPromotionRows", 0
            ),
            "admissionOfficeGapManualCupPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualCupPromotionRows", 0
            ),
            "admissionOfficeGapManualSookmyungPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualSookmyungPromotionRows", 0
            ),
            "admissionOfficeGapManualSunmoonSungkyulPromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualSunmoonSungkyulPromotionRows", 0
            ),
            "admissionOfficeGapManualScheduleP0PromotionRows": promotion_source_counts.get(
                "admissionOfficeGapManualScheduleP0PromotionRows", 0
            ),
            "admissionOfficeHomepageHtmlP0PromotionRows": promotion_source_counts.get(
                "admissionOfficeHomepageHtmlP0PromotionRows", 0
            ),
            "admissionOfficeManualScheduleTopPromotionRows": promotion_source_counts.get(
                "admissionOfficeManualScheduleTopPromotionRows", 0
            ),
            "admissionOfficeManualScheduleTopYearMismatchRows": promotion_source_counts.get(
                "admissionOfficeManualScheduleTopYearMismatchRows", 0
            ),
            "admissionOfficeGapGjcExistingFilePromotionRows": promotion_source_counts.get(
                "admissionOfficeGapGjcExistingFilePromotionRows", 0
            ),
            "admissionOfficeGapCueExistingFilePromotionRows": promotion_source_counts.get(
                "admissionOfficeGapCueExistingFilePromotionRows", 0
            ),
            "admissionOfficeGapSemyungUwayCompetitionPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapSemyungUwayCompetitionPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapCjuExistingFilePromotionRows": promotion_source_counts.get(
                "admissionOfficeGapCjuExistingFilePromotionRows", 0
            ),
            "admissionOfficeGapSmallAdmissionResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapSmallAdmissionResultsPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapSejongAdmissionResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapSejongAdmissionResultsPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapSeowonNestedFileRoutesPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapSeowonNestedFileRoutesPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapCrawlerFetchReadyRemainingPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapCrawlerFetchReadyRemainingPromotionRows",
                    0,
                )
            ),
            "admissionOfficeScriptNavReparsePromotionRows": promotion_source_counts.get(
                "admissionOfficeScriptNavReparsePromotionRows", 0
            ),
            "admissionOfficeScriptNavReparseNestedOfficialPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeScriptNavReparseNestedOfficialPromotionRows",
                    0,
                )
            ),
            "admissionOfficeScriptNavReparseNestedOfficialFilteredRows": (
                promotion_source_counts.get(
                    "admissionOfficeScriptNavReparseNestedOfficialFilteredRows",
                    0,
                )
            ),
            "admissionOfficeGapWorklistHtmlBridgeSecondFilePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapWorklistHtmlBridgeSecondFilePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapWorklistHtmlBridgeThirdFilePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapWorklistHtmlBridgeThirdFilePromotionRows",
                    0,
                )
            ),
            "admissionOfficeManualHomepageSeedFilePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeManualHomepageSeedFilePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapWorklistHtmlBridgePostManualSeedPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapWorklistHtmlBridgePostManualSeedPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapWorklistHtmlBridgePostSecondHtmlPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapWorklistHtmlBridgePostSecondHtmlPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapWorklistHtmlBridgePostDeltaPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapWorklistHtmlBridgePostDeltaPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapManualSehanCurrentApplyPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualSehanCurrentApplyPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapManualSuwonCatholicCurrentPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualSuwonCatholicCurrentPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapManualKayaCurrentPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapManualKayaCurrentPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapHomepageLinksPostManualSeedPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageLinksPostManualSeedPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapHomepageLinksRefinedDirectFilePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapHomepageLinksRefinedDirectFilePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapCollectionLinkCandidatesPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapCollectionLinkCandidatesPromotionRows",
                    0,
                )
            ),
            "admissionOfficeSeowon2022ResultDetailsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeSeowon2022ResultDetailsPromotionRows",
                    0,
                )
            ),
            "admissionOfficeSeowon2022ResultDetailFilesPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeSeowon2022ResultDetailFilesPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapYsu2021OfficialResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapYsu2021OfficialResultsPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapYewon2021LegacyResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapYewon2021LegacyResultsPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapKyonggi2024OfficialResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapKyonggi2024OfficialResultsPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapKyonggi2025OfficialResultsPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapKyonggi2025OfficialResultsPromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapLtu2021OfficialResultImagePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapLtu2021OfficialResultImagePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapWorklistFileHighValuePromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapWorklistFileHighValuePromotionRows",
                    0,
                )
            ),
            "admissionOfficeGapWorklistLinkedUnpromotedPromotionRows": (
                promotion_source_counts.get(
                    "admissionOfficeGapWorklistLinkedUnpromotedPromotionRows",
                    0,
                )
            ),
            "admissionOfficeJsDownloadFilePromotionRows": promotion_source_counts.get(
                "admissionOfficeJsDownloadFilePromotionRows", 0
            ),
            "admissionOfficeZipEntryPromotionRows": promotion_source_counts.get(
                "admissionOfficeZipEntryPromotionRows", 0
            ),
            "admissionOfficePromotionDuplicateRows": promotion_source_counts.get(
                "admissionOfficePromotionDuplicateRows", 0
            ),
            "academyinfoRows": len(raw_academyinfo_rows),
            "adigaRuleTableRows": len(raw_adiga_rule_table_rows),
            "adigaImageOcrEvidenceRows": len(raw_adiga_ocr_evidence_rows),
            "kiceGradeCutRows": len(raw_kice_grade_cut_rows),
            "kiceStandardScoreDistributionRows": len(raw_kice_distribution_rows),
            "kicePressSnippetRows": len(raw_kice_press_snippet_rows),
            "kcueSnippetRows": len(raw_kcue_snippet_rows),
        },
        "candidateRows": {
            "universities": len(universities),
            "admissionUnits": len(units),
            "historicalOutcomes": len(outcomes),
            "admissionOfficeEvidenceLinks": len(promotion_links),
            "admissionRuleReviewCandidates": len(admission_rule_candidates),
            "academyinfoSummaries": len(academyinfo_summaries),
            "kiceGradeCuts": len(kice_grade_cuts),
            "kiceStandardScoreDistributions": len(kice_distributions),
            "kicePressEvidenceLinks": len(kice_press_evidence),
            "kcuePolicyEvidenceLinks": len(kcue_policy_evidence),
        },
        "historicalOutcomesByYear": counter_rows(Counter(str(row.get("year") or "") for row in outcomes)),
        "historicalOutcomesByScoreAvailability": counter_rows(
            Counter(str(row.get("scoreAvailability") or "") for row in outcomes)
        ),
        "historicalOutcomesByConfidence": counter_rows(
            Counter(str(row.get("confidence") or "") for row in outcomes)
        ),
        "historicalOutcomesBySourceProvider": counter_rows(
            Counter(str(row.get("sourceProvider") or "") for row in outcomes)
        ),
        "admissionUnitsByRecruitmentGroup": counter_rows(
            Counter(str(row.get("recruitmentGroup") or "") for row in units)
        ),
        "admissionUnitsBySourceProvider": counter_rows(
            Counter(
                provider
                for row in units
                for provider in split_joined(row.get("sourceProviders"))
            )
        ),
        "admissionOfficeEvidenceByTarget": counter_rows(
            Counter(str(row.get("evidenceTarget") or "") for row in promotion_links)
        ),
        "admissionRuleCandidatesByProvider": counter_rows(
            Counter(str(row.get("sourceProvider") or "") for row in admission_rule_candidates)
        ),
        "admissionRuleCandidatesByCategory": counter_rows(
            Counter(str(row.get("ruleCategory") or "") for row in admission_rule_candidates)
        ),
        "admissionRuleCandidatesByEvidenceRole": counter_rows(
            Counter(str(row.get("evidenceRole") or "") for row in admission_rule_candidates),
            limit=40,
        ),
        "admissionRuleCandidatesByAdmissionYear": counter_rows(
            Counter(
                year
                for row in admission_rule_candidates
                for year in split_joined(row.get("admissionYears"))
            )
        ),
        "academyinfoSummariesByRelevanceRole": counter_rows(
            Counter(str(row.get("relevanceRole") or "") for row in academyinfo_summaries),
            limit=30,
        ),
        "kiceGradeCutsByAcademicYear": counter_rows(
            Counter(str(row.get("academicYear") or "") for row in kice_grade_cuts)
        ),
        "kiceGradeCutsByExamType": counter_rows(
            Counter(str(row.get("examType") or "") for row in kice_grade_cuts)
        ),
        "kiceGradeCutsByScoreMetric": counter_rows(
            Counter(str(row.get("scoreMetric") or "") for row in kice_grade_cuts)
        ),
        "kiceGradeCutsBySubjectGroup": counter_rows(
            Counter(str(row.get("subjectGroup") or "") for row in kice_grade_cuts)
        ),
        "kiceGradeCutsByValueStatus": counter_rows(
            Counter(str(row.get("valueStatus") or "") for row in kice_grade_cuts)
        ),
        "kiceGradeCutsBySourceAreaReviewFlag": counter_rows(
            Counter(str(row.get("sourceAreaReviewFlag") or "") for row in kice_grade_cuts)
        ),
        "kiceDistributionsByAcademicYear": counter_rows(
            Counter(str(row.get("academicYear") or "") for row in kice_distributions)
        ),
        "kiceDistributionsByExamType": counter_rows(
            Counter(str(row.get("examType") or "") for row in kice_distributions)
        ),
        "kiceDistributionsBySubjectGroup": counter_rows(
            Counter(str(row.get("subjectGroup") or "") for row in kice_distributions)
        ),
        "kiceDistributionsByValueStatus": counter_rows(
            Counter(str(row.get("valueStatus") or "") for row in kice_distributions)
        ),
        "kiceDistributionsBySourceAreaReviewFlag": counter_rows(
            Counter(str(row.get("sourceAreaReviewFlag") or "") for row in kice_distributions)
        ),
        "kicePressEvidenceByTarget": counter_rows(
            Counter(str(row.get("targetEntity") or "") for row in kice_press_evidence)
        ),
        "kicePressEvidenceByRole": counter_rows(
            Counter(str(row.get("snippetRole") or "") for row in kice_press_evidence),
            limit=30,
        ),
        "kcuePolicyEvidenceByTarget": counter_rows(
            Counter(str(row.get("targetEntity") or "") for row in kcue_policy_evidence)
        ),
        "kcuePolicyEvidenceByRole": counter_rows(
            Counter(str(row.get("snippetRole") or "") for row in kcue_policy_evidence),
            limit=30,
        ),
        "kcuePolicyEvidenceByAcademicYear": counter_rows(
            Counter(str(row.get("academicYear") or "") for row in kcue_policy_evidence)
        ),
        "kcuePolicyEvidenceByDocumentKind": counter_rows(
            Counter(str(row.get("documentKind") or "") for row in kcue_policy_evidence)
        ),
        "notes": [
            "Foundation candidates are not verified production seed data.",
            "Adiga HistoricalOutcome candidates preserve parsed score fields and original source coordinates.",
            "Admission-office HistoricalOutcome rows are source-preserving review candidates parsed only when quota/applicant/competition values cross-check.",
            "Admission-office evidence links and Academyinfo rows remain review evidence until human source comparison promotes them.",
            "KICE score-reference candidates preserve official workbook coordinates and press-text evidence for calculation-engine reference review.",
            "KCUE policy evidence links preserve national admission policy, schedule, and common-application snippets as review evidence.",
        ],
    }


def write_outputs(output_dir: Path, context: dict[str, Any]) -> None:
    artifacts = [
        (
            "foundation_universities",
            context["universities"],
            [
                "universityCandidateId",
                "unvCd",
                "universityName",
                "universityNameCanonical",
                "campus",
                "region",
                "type",
                "sourceProviders",
                "years",
                "adigaOutcomeRows",
                "admissionOfficeEvidenceCandidates",
                "admissionRuleReviewCandidates",
                "academyinfoSummaryRows",
                "reviewStatus",
            ],
        ),
        (
            "foundation_admission_units",
            context["admissionUnits"],
            [
                "unitCandidateId",
                "universityCandidateId",
                "unvCd",
                "universityName",
                "year",
                "admissionUnitName",
                "admissionUnitCanonicalName",
                "recruitmentGroup",
                "majorGroup",
                "quotaCandidates",
                "outcomeRows",
                "sourceProviders",
                "sourceCandidateSha256Values",
                "reviewStatus",
            ],
        ),
        (
            "foundation_historical_outcomes",
            context["historicalOutcomes"],
            [
                "outcomeCandidateId",
                "unitCandidateId",
                "universityCandidateId",
                "unvCd",
                "universityName",
                "year",
                "admissionUnitName",
                "admissionUnitCanonicalName",
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
                "scoreAvailability",
                "metricCount",
                "subjectMetricCount",
                "hasQuotaAndCompetition",
                "hasOutcomeScore",
                "confidence",
                "sourceProvider",
                "sourceConfidence",
                "sourceUrl",
                "rawPath",
                "sectionId",
                "tableIndex",
                "rowIndex",
                "sourceCandidateSha256",
                "reviewStatus",
            ],
        ),
        (
            "foundation_admission_office_evidence_links",
            context["admissionOfficeEvidenceLinks"],
            [
                "sourceProvider",
                "evidenceCandidateSha256",
                "unvCd",
                "universityName",
                "campus",
                "evidenceTarget",
                "evidenceRole",
                "evidenceTypes",
                "collectionYears",
                "detectedAdmissionYears",
                "evidenceCount",
                "reviewPriorityScore",
                "textPreview",
                "sourceCandidateUrl",
                "attachmentUrl",
                "rawPath",
                "sourcePath",
                "sourceCandidateUrls",
                "attachmentUrls",
                "rawPaths",
                "sourcePaths",
                "sourceDocumentKinds",
                "sourceLinkRoles",
                "sourceLabels",
                "sourceRowCount",
                "duplicateSourceCount",
                "reviewStatus",
            ],
        ),
        (
            "foundation_academyinfo_university_metric_summaries",
            context["academyinfoSummaries"],
            [
                "sourceProvider",
                "summaryCandidateSha256",
                "universityName",
                "universityNameCanonical",
                "matchedUnvCd",
                "matchedUniversityName",
                "matchStatus",
                "surveyYear",
                "relevanceRole",
                "outputKind",
                "sourceRows",
                "metricValues",
                "candidateSha256Samples",
                "sourceZipPaths",
                "csvPaths",
                "reviewStatus",
            ],
        ),
        (
            "foundation_admission_rule_review_candidates",
            context["admissionRuleReviewCandidates"],
            [
                "ruleCandidateId",
                "sourceProvider",
                "artifactType",
                "sourceEvidenceId",
                "unvCd",
                "universityName",
                "campus",
                "admissionYears",
                "collectionYears",
                "ruleCategory",
                "evidenceRole",
                "evidenceType",
                "sourceDocumentKind",
                "reviewPriorityScore",
                "evidenceCount",
                "detectedSignals",
                "percentageValues",
                "weightValues",
                "scoreMetricSignals",
                "subjectSignals",
                "formulaSignals",
                "textPreview",
                "sourceUrl",
                "attachmentUrl",
                "rawPath",
                "sourcePath",
                "sourceUrls",
                "attachmentUrls",
                "rawPaths",
                "sourcePaths",
                "sourceLabels",
                "sourceRowCount",
                "duplicateSourceCount",
                "tableSha256",
                "sectionLabel",
                "tableRole",
                "tableIndex",
                "rows",
                "cols",
                "reviewStatus",
            ],
        ),
        (
            "foundation_kice_grade_cuts",
            context["kiceGradeCuts"],
            [
                "gradeCutCandidateId",
                "sourceProvider",
                "artifactType",
                "academicYear",
                "examType",
                "fileKind",
                "scoreMetric",
                "subjectArea",
                "subjectName",
                "subjectNameNormalized",
                "subjectGroup",
                "grade",
                "cutScoreRaw",
                "cutScoreNumeric",
                "cutScoreOperator",
                "testTakerCount",
                "ratioPercent",
                "valueStatus",
                "candidateConfidence",
                "sourceAreaReviewFlag",
                "boardSeq",
                "fileSeq",
                "fileTitle",
                "sheetName",
                "sourceUrl",
                "viewUrl",
                "csvPath",
                "sourceRowNumber",
                "sourceColumnNumber",
                "reviewStatus",
            ],
        ),
        (
            "foundation_kice_standard_score_distributions",
            context["kiceStandardScoreDistributions"],
            [
                "distributionCandidateId",
                "sourceProvider",
                "artifactType",
                "academicYear",
                "examType",
                "subjectArea",
                "subjectName",
                "subjectNameNormalized",
                "subjectGroup",
                "standardScore",
                "maleCount",
                "femaleCount",
                "totalCount",
                "cumulativeTotalCount",
                "valueStatus",
                "candidateConfidence",
                "sourceAreaReviewFlag",
                "boardSeq",
                "fileSeq",
                "fileTitle",
                "sheetName",
                "sourceUrl",
                "viewUrl",
                "csvPath",
                "sourceRowNumber",
                "sourceColumnNumber",
                "reviewStatus",
            ],
        ),
        (
            "foundation_kice_press_evidence_links",
            context["kicePressEvidenceLinks"],
            [
                "sourceProvider",
                "evidenceCandidateSha256",
                "academicYear",
                "examType",
                "snippetRole",
                "targetEntity",
                "reviewPriorityScore",
                "title",
                "fileTitle",
                "startLine",
                "endLine",
                "matchedKeywords",
                "snippetPreview",
                "textPath",
                "rawAttachmentPath",
                "sourceUrl",
                "reviewStatus",
            ],
        ),
        (
            "foundation_kcue_policy_evidence_links",
            context["kcuePolicyEvidenceLinks"],
            [
                "sourceProvider",
                "evidenceCandidateSha256",
                "academicYear",
                "postedDate",
                "postIdx",
                "postRole",
                "title",
                "attachmentRole",
                "documentKind",
                "snippetRole",
                "targetEntity",
                "reviewPriorityScore",
                "pageNumber",
                "startLine",
                "endLine",
                "matchedKeywords",
                "textPreview",
                "textPath",
                "rawAttachmentPath",
                "sourceUrl",
                "viewUrl",
                "reviewStatus",
            ],
        ),
    ]
    for basename, rows, fields in artifacts:
        write_jsonl(output_dir / f"{basename}.jsonl", rows)
        write_csv(output_dir / f"{basename}.csv", rows, fields)

    (output_dir / "foundation_database_candidate_summary.json").write_text(
        json.dumps(context["summary"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def csv_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def field(row: dict[str, Any], name: str) -> str:
    return normalize_text(row.get(name) if name in row else row.get(f"\ufeff{name}"))


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def deterministic_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_name(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"\s+", "", text)
    return text


def recruitment_group_value(value: Any) -> str:
    text = normalize_text(value)
    return text if text in {"ga", "na", "da"} else "none"


def infer_major_group(name: str) -> str:
    if re.search(r"의예|의학|간호|약학|치의|한의|보건|물리치료|작업치료|방사선|임상", name):
        return "보건의료"
    if re.search(r"공학|컴퓨터|소프트웨어|전자|전기|기계|건축|토목|AI|인공지능|데이터", name, re.I):
        return "공학"
    if re.search(r"경영|경제|무역|회계|관광|호텔|행정|사회복지|미디어|심리", name):
        return "사회경영"
    if re.search(r"국어|영어|문헌|사학|철학|교육|언어|문예|인문", name):
        return "인문교육"
    if re.search(r"디자인|음악|미술|체육|스포츠|연극|영화|무용", name):
        return "예체능"
    if re.search(r"수학|물리|화학|생명|식품|환경|해양|농|동물", name):
        return "자연"
    return ""


def infer_rule_category(evidence_role: str, table_role: str, text: str) -> str:
    role = normalize_text(f"{evidence_role} {table_role}")
    haystack = normalize_text(f"{role} {text}")
    if re.search(r"eligibility", role):
        return "eligibility"
    if re.search(r"school_record|student_record", role):
        return "school_record_reflection"
    if re.search(r"screening_method", role):
        return "screening_method"
    if re.search(r"csat_reflection|csat_rule", role):
        return "csat_reflection"
    if is_recruitment_quota_like_rule_text(text):
        return "recruitment_quota"
    if "csat" in role or re.search(r"수능|표준점수|백분위|영어변환|한국사|탐구.?반영|가산점|활용지표|산출식", haystack):
        return "csat_reflection"
    if re.search(r"전형요소|선발방법|일괄|단계|면접|실기|서류|screening_method", haystack):
        return "screening_method"
    if re.search(r"recruitment_quota", role):
        return "recruitment_quota"
    if re.search(r"지원자격|졸업|농어촌|지역인재|기회균형|특성화고|eligibility", haystack):
        return "eligibility"
    if re.search(r"학생부|교과|내신|출결|봉사|student_rule", haystack):
        return "school_record_reflection"
    if re.search(r"모집인원|모집단위|모집군|정원|recruitment_quota", haystack):
        return "recruitment_quota"
    return "general_rule"


def is_recruitment_quota_like_rule_text(text: str) -> bool:
    if not re.search(r"모집\s*/?\s*인원|모집인원|전형별\s*모집\s*인원", text):
        return False
    return bool(re.search(r"\d+\s*명|미\s*지정|정원\s*(?:내|외)", text))


def adiga_table_priority(table_role: str, text: str) -> int:
    base = {"csat_rule": 82, "student_rule": 58, "common": 42}.get(table_role, 20)
    return base + min(len(detect_rule_signals(text)) * 3, 18)


RULE_SIGNAL_PATTERNS = [
    ("csat", re.compile(r"수능|정시", re.I)),
    ("score_formula", re.compile(r"산출식|환산점수|변환점수|∑|Σ", re.I)),
    ("reflection_ratio", re.compile(r"반영비율|반영.?배점|\d+(?:\.\d+)?\s*%", re.I)),
    ("standard_score", re.compile(r"표준점수", re.I)),
    ("percentile", re.compile(r"백분위", re.I)),
    ("raw_score", re.compile(r"원점수", re.I)),
    ("english_conversion", re.compile(r"영어.?변환|영어.?등급|영어", re.I)),
    ("korean_history", re.compile(r"한국사", re.I)),
    ("exploration_subjects", re.compile(r"탐구|사회탐구|과학탐구|직업탐구", re.I)),
    ("bonus", re.compile(r"가산점", re.I)),
    ("minimum_grade", re.compile(r"수능최저|최저학력|\d+\s*합\s*\d+", re.I)),
    ("screening_method", re.compile(r"전형방법|전형요소|선발방법|일괄|단계", re.I)),
    ("interview_or_practical", re.compile(r"면접|실기", re.I)),
    ("school_record", re.compile(r"학생부|교과|내신", re.I)),
    ("eligibility", re.compile(r"지원자격|졸업|농어촌|지역인재|기회균형|특성화고|기초생활수급자|차상위|한부모", re.I)),
    ("recruitment_group", re.compile(r"가군|나군|다군|모집군", re.I)),
]


def detect_rule_signals(text: str) -> list[str]:
    return [name for name, pattern in RULE_SIGNAL_PATTERNS if pattern.search(text)]


def extract_percentages(text: str, limit: int = 20) -> list[str]:
    values: list[str] = []
    for match in re.finditer(r"(?<!\d)(\d{1,3}(?:\.\d+)?)\s*%", text):
        value = f"{match.group(1)}%"
        if value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def extract_weight_values(text: str, limit: int = 30) -> list[str]:
    if not re.search(r"반영비율|반영.?배점|전형요소|수능영역별|학생부|수능|국어|수학|영어|탐구", text):
        return []
    values: list[str] = []
    for match in re.finditer(r"(?<![\d.])(\d{1,3}(?:\.\d+)?)(?![\d.])", text):
        value = match.group(1)
        number = number_or_none(value)
        if not isinstance(number, (int, float)):
            continue
        if 0 <= float(number) <= 100 and value not in values:
            values.append(value)
        if len(values) >= limit:
            break
    return values


def detect_score_metric_signals(text: str) -> list[str]:
    patterns = [
        ("standard_score", r"표준점수"),
        ("percentile", r"백분위"),
        ("raw_score", r"원점수"),
        ("grade", r"등급"),
        ("converted_score", r"환산점수|변환점수"),
        ("highest_score", r"최고점|만점"),
    ]
    return [name for name, pattern in patterns if re.search(pattern, text)]


def detect_subject_signals(text: str) -> list[str]:
    patterns = [
        ("korean", r"국어"),
        ("math", r"수학|미적분|확률과.?통계|기하"),
        ("english", r"영어"),
        ("exploration", r"탐구"),
        ("social", r"사회탐구|사탐|사회"),
        ("science", r"과학탐구|과탐|과학"),
        ("vocational", r"직업탐구|직탐|직업"),
        ("korean_history", r"한국사"),
        ("second_language", r"제2외국어|한문"),
    ]
    return [name for name, pattern in patterns if re.search(pattern, text)]


def detect_formula_signals(text: str) -> list[str]:
    patterns = [
        ("formula_label", r"산출식"),
        ("summation", r"∑|Σ|합산"),
        ("ratio_weighting", r"반영비율|반영.?배점"),
        ("max_score_normalization", r"최고점|만점"),
        ("division", r"/|÷"),
        ("multiplication", r"×|\*"),
        ("grade_sum_minimum", r"\d+\s*합\s*\d+"),
    ]
    return [name for name, pattern in patterns if re.search(pattern, text)]


def infer_kice_subject_group(name: str) -> str:
    text = normalize_text(name)
    compact = re.sub(r"\s+", "", text)
    if re.search(r"국어|언어|화법|작문|매체", compact):
        return "국어"
    if re.search(r"수학|수리|확률|미적분|기하", compact):
        return "수학"
    if re.search(r"영어|외국어\(영어\)", compact):
        return "영어"
    if "한국사" in compact:
        return "한국사"
    if re.search(r"생활과윤리|윤리와사상|한국지리|세계지리|동아시아사|세계사|경제|정치와법|법과정치|법과사회|사회.?문화|국사|한국근.?현대사|윤리|정치", compact):
        return "사회탐구"
    if re.search(r"물리|화학|생명|생물|지구과학", compact):
        return "과학탐구"
    if re.search(r"직업|농업|공업|상업|수산|해운|인간발달|가사|농생명|기초제도|회계원리|생활서비스산업의이해|해양의이해|디자인일반|식품과영양|정보기술기초|컴퓨터일반|프로그래밍|해사일반|해양일반", compact):
        return "직업탐구"
    if re.search(r"독일어|프랑스어|스페인어|중국어|일본어|러시아어|아랍어|베트남어|한문", compact):
        return "제2외국어/한문"
    return ""


def confidence_for(row: dict[str, Any]) -> str:
    availability = normalize_text(row.get("scoreAvailability"))
    if availability == "converted_and_percentile":
        return "medium"
    if availability in {"converted_score_only", "percentile_only"}:
        return "low"
    return "limited"


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def number_or_none(value: Any) -> int | float | None:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if number.is_integer():
        return int(number)
    return number


def number_string(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return normalize_text(value)
    if number.is_integer():
        return str(int(number))
    return str(number)


def add_limited(values: list[str], value: Any, limit: int) -> None:
    text = normalize_text(value)
    if text and text not in values and len(values) < limit:
        values.append(text)


def unique_values(value: Any) -> list[str]:
    values: list[str] = []
    raw_values = value if isinstance(value, list) else [value]
    for raw_value in raw_values:
        text = normalize_text(raw_value)
        if text and text not in values:
            values.append(text)
    return values


def merge_unique_values(existing: Any, incoming: Any, limit: int = 100) -> list[str]:
    merged = unique_values(existing)
    for value in unique_values(incoming):
        if value not in merged and len(merged) < limit:
            merged.append(value)
    return merged


def merge_count_maps(existing: Any, incoming: Any) -> dict[str, int]:
    merged: dict[str, int] = {}
    for source in (existing, incoming):
        if not isinstance(source, dict):
            continue
        for key, value in source.items():
            text_key = normalize_text(key)
            if not text_key:
                continue
            merged[text_key] = merged.get(text_key, 0) + (int_or_none(value) or 0)
    return merged


def merge_sample_objects(existing: Any, incoming: Any, limit: int = 20) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for source in (existing, incoming):
        if not isinstance(source, list):
            continue
        for item in source:
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key in seen or len(merged) >= limit:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def join_values(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(str(item) for item in value if item is not None and str(item) != "")
    return normalize_text(value)


def split_joined(value: Any) -> list[str]:
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(split_joined(item))
        return parts
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def unique_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def first_int_from_joined(value: Any) -> int | None:
    for part in split_joined(value):
        parsed = int_or_none(part)
        if parsed is not None:
            return parsed
    return None


def first(value: Any) -> str:
    if isinstance(value, list):
        return normalize_text(value[0]) if value else ""
    return normalize_text(value)


def first_for_year(value: Any, year: int) -> str:
    parts = split_joined(value)
    year_pattern = re.compile(rf"(?:^|[/?_=.-]){re.escape(str(year))}(?:$|[/?_=&.-])")
    for part in parts:
        if year_pattern.search(part):
            return normalize_text(part)
    return first(value)


def kice_candidate_confidence(value_status: str) -> str:
    return "high" if value_status == "parsed" else "limited"


def source_area_review_flag(value: Any) -> str:
    text = normalize_text(value)
    return "source_area_numeric_like" if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text) else ""


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": key, "count": value} for key, value in counter.most_common(limit)]


if __name__ == "__main__":
    main()
