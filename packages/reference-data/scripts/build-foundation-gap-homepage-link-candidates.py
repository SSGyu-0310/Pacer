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
from urllib.parse import unquote, urlparse, urljoin


DEFAULT_GAP_COLLECTION_TARGETS = (
    "packages/reference-data/data/public/foundation/"
    "foundation_gap_collection_targets.csv"
)
DEFAULT_UNIVERSITY_SITE_DIR = "packages/reference-data/data/public/university-admission-sites"
OUTPUT_JSONL = "university_admission_gap_homepage_link_candidates.jsonl"
OUTPUT_CSV = "university_admission_gap_homepage_link_candidates.csv"
OUTPUT_SUMMARY = "university_admission_gap_homepage_link_candidates_summary.json"

TARGET_ROUTES = {"admission_homepage", "admission_office_deep_link_discovery"}
TARGET_STATUSES = {
    "already_fetched_needs_link_parser_review",
    "homepage_fetch_failed_retry_or_manual",
    "no_matching_link_candidate",
}
DOCUMENT_EXTENSIONS = {"csv", "doc", "docx", "hwp", "hwpx", "pdf", "xls", "xlsx", "zip"}
ASSET_EXTENSIONS = {
    "bmp",
    "css",
    "eot",
    "gif",
    "ico",
    "jpeg",
    "jpg",
    "js",
    "map",
    "mp4",
    "png",
    "svg",
    "ttf",
    "webp",
    "woff",
    "woff2",
}
ADMISSION_HOST_HINTS = {
    "admission",
    "enter",
    "entra",
    "ent",
    "ipsi",
    "iphak",
}
EXCLUDED_HOST_HINTS = {
    "facebook.com",
    "instagram.com",
    "jinhak",
    "jinhakapply",
    "kakao.com",
    "naver.com",
    "nesin",
    "telegr",
    "twitter.com",
    "uway",
    "uwayapply",
    "univapply",
    "x.com",
    "youtube.com",
    "youtu.be",
    "01consulting",
}
KOREAN_KEYWORDS = [
    "정시",
    "모집요강",
    "전형요강",
    "입시결과",
    "입학결과",
    "전형결과",
    "경쟁률",
    "충원",
    "합격",
    "수능",
    "대학입학",
    "입학",
    "모집",
    "전형",
    "공지",
    "자료",
]
ASCII_KEYWORDS = [
    "admission",
    "enter",
    "ipsi",
    "iphak",
    "junsi",
    "jeongsi",
    "regular",
    "result",
    "notice",
    "board",
    "bbs",
    "guide",
    "recruit",
    "apply",
    "uway",
]
ADMISSION_YEAR_MENTION_PATTERN = re.compile(r"(?<!\d)(20\d{2})\s*학\s*년\s*도")
PLAIN_YEAR_PATTERN = re.compile(r"(?<!\d)(20[2-3]\d)(?!\d)")
OUT_OF_SCOPE_PATTERN = re.compile(
    r"재외국민|외국인|편입|대학원|시간제|평생교육|계약학과|산업체|"
    r"선행학습|영향평가|고교연계|체험|설명회|상담|입학자료\s*신청|자료\s*신청|"
    r"서식|양식|참고자료|학사\s*안내|성적\s*산출|성적계산|합격자|등록금|등록\s*안내|등록\s*확인|환불|"
    r"기숙사|생활관|장학|오시는\s*길|캠퍼스|경영정보|등록금심의|채용|학술|연구소|석사|박사|정기간행물|"
    r"이사회|정관|적립금|후원|성폭력|커뮤니티|로그인|회원가입|비밀번호|"
    r"저작권|개인정보|이메일무단수집|선원건강진단서|병역|등록포기|"
    r"tuition|gallery|bo_table=free|webzine|bo_table=account|bo_table=book|bo_table=hyei|"
    r"bo_table=junggwan|bo_table=junglip|bo_table=qa|bo_table=qna|login|register|password|member_|"
    r"privacy|copyright|opt-out|usage-guide|pogi|univregularpass|service\.applyer|pass\.html",
    re.I,
)
STRONG_ADMISSION_DATA_PATTERN = re.compile(
    r"입시\s*결과|입학\s*결과|전형\s*결과|전년도|경쟁률|충원|최종\s*등록|"
    r"정시|수시|모집\s*요강|전형\s*요강|입학\s*전형|전형\s*계획|시행\s*계획|"
    r"주요\s*사항|모집\s*인원|수능\s*반영|학생부\s*반영|모집\s*공지|입시\s*공지",
    re.I,
)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    gap_targets_path = resolve(repo_root, args.gap_collection_targets)
    university_site_dir = resolve(repo_root, args.university_site_dir)
    university_site_dir.mkdir(parents=True, exist_ok=True)

    gap_targets = target_rows(read_csv(gap_targets_path))
    homepage_manifests, homepage_manifest_paths = load_homepage_manifests(university_site_dir)
    existing_link_keys, existing_link_paths = load_existing_link_keys(university_site_dir)

    candidates, extraction_stats = build_candidates(
        repo_root=repo_root,
        gap_targets=gap_targets,
        homepage_manifests=homepage_manifests,
        existing_link_keys=existing_link_keys,
    )
    candidates.sort(
        key=lambda row: (
            -int_or_none(row.get("candidatePriorityScore") or 0),
            str(row.get("universityName") or ""),
            int_or_none(row.get("year")) or 9999,
            str(row.get("linkRole") or ""),
            str(row.get("resolvedUrl") or ""),
        )
    )

    write_jsonl(university_site_dir / OUTPUT_JSONL, candidates)
    write_csv(university_site_dir / OUTPUT_CSV, candidates)
    summary = summarize(
        repo_root=repo_root,
        inputs=[gap_targets_path, *homepage_manifest_paths, *existing_link_paths],
        gap_targets=gap_targets,
        candidates=candidates,
        extraction_stats=extraction_stats,
    )
    (university_site_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation gap homepage link candidates complete. "
        f"targets={len(gap_targets)} candidates={len(candidates)} "
        f"rawPages={summary['homepageTargets']['rawPagesParsed']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gap-collection-targets", default=DEFAULT_GAP_COLLECTION_TARGETS)
    parser.add_argument("--university-site-dir", default=DEFAULT_UNIVERSITY_SITE_DIR)
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


def target_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row
        for row in rows
        if normalize_text(row.get("sourceProvider")) == "university-admission-office"
        and normalize_text(row.get("collectionRoute")) in TARGET_ROUTES
        and normalize_text(row.get("existingFetchStatus")) in TARGET_STATUSES
    ]


def load_homepage_manifests(site_dir: Path) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], list[Path]]:
    rows: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    paths = sorted(site_dir.glob("university_admission_homepage_manifest_*.jsonl"))
    for path in paths:
        for row in read_jsonl(path):
            unv_cd = normalize_text(row.get("unvCd"))
            year = normalize_text(row.get("year"))
            if unv_cd and year:
                rows[(unv_cd, year)].append(row)
    return rows, paths


def load_existing_link_keys(site_dir: Path) -> tuple[set[tuple[str, str, str, str]], list[Path]]:
    keys: set[tuple[str, str, str, str]] = set()
    paths = sorted(site_dir.glob("university_admission_link_candidates_*.csv"))
    for path in paths:
        for row in read_csv(path):
            key = link_key(
                row.get("year"),
                row.get("unvCd"),
                row.get("linkRole"),
                row.get("resolvedUrl"),
            )
            if key:
                keys.add(key)
    artifact_paths = sorted(site_dir.glob("university_admission_link_artifact_manifest_*.jsonl"))
    for path in artifact_paths:
        for row in read_jsonl(path):
            for url_field in ["sourceCandidateUrl", "finalUrl"]:
                key = link_key(
                    row.get("year"),
                    row.get("unvCd"),
                    row.get("sourceLinkRole"),
                    row.get(url_field),
                )
                if key:
                    keys.add(key)
    paths.extend(artifact_paths)
    return keys, paths


def build_candidates(
    repo_root: Path,
    gap_targets: list[dict[str, str]],
    homepage_manifests: dict[tuple[str, str], list[dict[str, Any]]],
    existing_link_keys: set[tuple[str, str, str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "targetsWithoutRawPage": 0,
        "rawPagesParsed": set(),
        "rawPagesMissingOnDisk": set(),
        "existingLinkCandidateDuplicates": 0,
        "discardedAssetOrLowSignalLinks": 0,
        "conflictingAdmissionYearLinks": 0,
        "outOfScopeLinks": 0,
    }
    seen: set[tuple[str, str, str, str]] = set()

    for target in gap_targets:
        manifest = best_homepage_manifest(target, homepage_manifests)
        raw_path = normalize_text((manifest or {}).get("rawPath")) or normalize_text(target.get("rawPath"))
        final_url = normalize_text((manifest or {}).get("finalHomepageUrl")) or normalize_text(target.get("sourceUrl"))
        source_homepage_url = normalize_text((manifest or {}).get("sourceHomepageUrl")) or normalize_text(target.get("sourceUrl"))
        if not raw_path:
            stats["targetsWithoutRawPage"] += 1
            continue
        raw_abs = resolve(repo_root, raw_path)
        if not raw_abs.exists():
            stats["rawPagesMissingOnDisk"].add(raw_path)
            continue

        stats["rawPagesParsed"].add(raw_path)
        html_text = raw_abs.read_text(encoding="utf-8", errors="replace")
        for extracted in extract_candidate_links(html_text, base_url=final_url or source_homepage_url):
            if is_out_of_scope_link(extracted):
                stats["outOfScopeLinks"] += 1
                continue
            if has_conflicting_admission_year(target, extracted):
                stats["conflictingAdmissionYearLinks"] += 1
                continue
            candidate = make_candidate(target, manifest, raw_path, source_homepage_url, final_url, extracted)
            if not candidate:
                stats["discardedAssetOrLowSignalLinks"] += 1
                continue
            key = link_key(candidate.get("year"), candidate.get("unvCd"), candidate.get("linkRole"), candidate.get("resolvedUrl"))
            if not key:
                continue
            if key in existing_link_keys:
                stats["existingLinkCandidateDuplicates"] += 1
                continue
            if key in seen:
                continue
            seen.add(key)
            rows.append(candidate)

    stats["rawPagesParsedCount"] = len(stats["rawPagesParsed"])
    stats["rawPagesMissingOnDiskCount"] = len(stats["rawPagesMissingOnDisk"])
    stats["rawPagesParsed"] = sorted(stats["rawPagesParsed"])
    stats["rawPagesMissingOnDisk"] = sorted(stats["rawPagesMissingOnDisk"])
    return rows, stats


def best_homepage_manifest(
    target: dict[str, str],
    homepage_manifests: dict[tuple[str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    group = (normalize_text(target.get("unvCd")), normalize_text(target.get("admissionYear")))
    source_url = canonical_url(target.get("sourceUrl"))
    candidates = homepage_manifests.get(group, [])
    if source_url:
        matches = [
            row
            for row in candidates
            if source_url in {
                canonical_url(row.get("sourceHomepageUrl")),
                canonical_url(row.get("finalHomepageUrl")),
            }
        ]
        if matches:
            return best_fetched_manifest(matches)
    return best_fetched_manifest(candidates) if candidates else None


def best_fetched_manifest(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        candidates,
        key=lambda row: (
            normalize_text(row.get("status")) == "fetched",
            int_or_none(row.get("bytes")) or 0,
            normalize_text(row.get("fetchedAt")),
        ),
        reverse=True,
    )[0]


def extract_candidate_links(html_text: str, base_url: str) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    candidates.extend(extract_attr_links(html_text, base_url))
    candidates.extend(extract_script_navigation_links(html_text, base_url))
    candidates.extend(extract_absolute_string_links(html_text, base_url))
    candidates.extend(extract_relative_string_links(html_text, base_url))
    return candidates


def extract_attr_links(html_text: str, base_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    tag_pattern = re.compile(r"<(?P<tag>a|area|form|iframe|frame|meta|script)\b(?P<attrs>[\s\S]*?)(?:>|/>)", re.I)
    for match in tag_pattern.finditer(html_text):
        tag = match.group("tag").lower()
        attrs = match.group("attrs")
        attr_names = ["href"] if tag in {"a", "area"} else ["action"] if tag == "form" else ["src"]
        if tag == "meta":
            attr_names = ["content"]
        for attr_name in attr_names:
            raw = extract_attribute(attrs, attr_name)
            if not raw:
                continue
            if tag == "meta":
                raw = meta_url_candidate(attrs, raw)
                if not raw:
                    continue
            label = nearby_anchor_label(html_text, match.start(), match.end()) if tag in {"a", "area"} else tag
            resolved = resolve_candidate_url(raw, base_url)
            if resolved:
                rows.append(
                    {
                        "extractionSource": f"{tag}_{attr_name}",
                        "linkText": label,
                        "hrefRaw": raw,
                        "resolvedUrl": resolved,
                        "context": context_window(html_text, match.start(), match.end()),
                    }
                )
    return rows


def extract_script_navigation_links(html_text: str, base_url: str) -> list[dict[str, str]]:
    patterns = [
        ("document_location_href", r"(?:document\.)?location(?:\.href)?\s*=\s*['\"](?P<url>[^'\"]+)['\"]"),
        ("location_replace", r"location\.replace\(\s*['\"](?P<url>[^'\"]+)['\"]"),
        ("window_open", r"window\.open\(\s*['\"](?P<url>[^'\"]+)['\"]"),
        ("tcontrol_href", r"TControl\.setHref\(\s*['\"](?P<url>[^'\"]+)['\"]"),
        ("script_url_assignment", r"\b(?:url|href|link)\s*[:=]\s*['\"](?P<url>[^'\"]{2,300})['\"]"),
    ]
    rows: list[dict[str, str]] = []
    for source, pattern in patterns:
        for match in re.finditer(pattern, html_text, re.I):
            raw = match.group("url")
            resolved = resolve_candidate_url(raw, base_url)
            if resolved:
                rows.append(
                    {
                        "extractionSource": source,
                        "linkText": source.replace("_", " "),
                        "hrefRaw": raw,
                        "resolvedUrl": resolved,
                        "context": context_window(html_text, match.start(), match.end()),
                    }
                )
    return rows


def extract_absolute_string_links(html_text: str, base_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pattern = re.compile(r"(?P<url>https?://[^'\"<>\s)]+)", re.I)
    for match in pattern.finditer(html_text):
        raw = match.group("url")
        resolved = resolve_candidate_url(raw, base_url)
        if resolved:
            rows.append(
                {
                    "extractionSource": "absolute_url_string",
                    "linkText": "absolute url string",
                    "hrefRaw": raw,
                    "resolvedUrl": resolved,
                    "context": context_window(html_text, match.start(), match.end()),
                }
            )
    return rows


def extract_relative_string_links(html_text: str, base_url: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pattern = re.compile(r"['\"](?P<url>/[^'\"]{2,300})['\"]", re.I)
    for match in pattern.finditer(html_text):
        raw = match.group("url")
        if not has_admission_signal(raw, context_window(html_text, match.start(), match.end())):
            continue
        resolved = resolve_candidate_url(raw, base_url)
        if resolved:
            rows.append(
                {
                    "extractionSource": "relative_url_string",
                    "linkText": "relative url string",
                    "hrefRaw": raw,
                    "resolvedUrl": resolved,
                    "context": context_window(html_text, match.start(), match.end()),
                }
            )
    return rows


def make_candidate(
    target: dict[str, str],
    manifest: dict[str, Any] | None,
    raw_path: str,
    source_homepage_url: str,
    final_homepage_url: str,
    extracted: dict[str, str],
) -> dict[str, Any] | None:
    resolved_url = canonical_url(extracted.get("resolvedUrl"))
    if not resolved_url:
        return None
    if invalid_candidate_url(resolved_url):
        return None
    if resolved_url in {canonical_url(source_homepage_url), canonical_url(final_homepage_url)}:
        return None
    parsed = urlparse(resolved_url)
    if excluded_external_host(parsed.hostname or ""):
        return None
    extension = file_extension_for(resolved_url)
    if extension in ASSET_EXTENSIONS:
        return None
    link_text = normalize_text(extracted.get("linkText")) or normalize_text(extracted.get("extractionSource"))
    context = normalize_text(extracted.get("context"))
    keyword_hits = keyword_hits_for(f"{link_text} {resolved_url} {context}")
    admission_like = is_admission_like_url(resolved_url)
    if not keyword_hits and not admission_like and extension not in DOCUMENT_EXTENSIONS:
        return None
    link_role = classify_link_role(f"{link_text} {resolved_url} {context}", keyword_hits)
    if link_role == "admission_related" and extension not in DOCUMENT_EXTENSIONS:
        if not STRONG_ADMISSION_DATA_PATTERN.search(unquote(f"{link_text} {resolved_url} {context}")):
            return None
    confidence = candidate_confidence(keyword_hits, admission_like, extracted.get("extractionSource"), extension)
    return {
        "provider": "university-admission-office",
        "artifactType": "admission_site_link_candidate",
        "year": int_or_none(target.get("admissionYear")) or normalize_text(target.get("admissionYear")),
        "unvCd": normalize_text(target.get("unvCd")),
        "universityName": normalize_text(target.get("universityName")),
        "campus": normalize_text((manifest or {}).get("campus")),
        "sourceHomepageUrl": source_homepage_url,
        "finalHomepageUrl": final_homepage_url,
        "rawPath": raw_path,
        "linkRole": link_role,
        "linkText": link_text[:240],
        "hrefRaw": normalize_text(extracted.get("hrefRaw"))[:500],
        "resolvedUrl": resolved_url,
        "hostname": parsed.hostname or "",
        "fileExtension": extension,
        "keywordHits": "|".join(keyword_hits),
        "gapHomepageLinkCandidateId": deterministic_uuid(
            "gap-homepage-link:"
            f"{target.get('collectionTargetId')}:{link_role}:{resolved_url}:{extracted.get('extractionSource')}"
        ),
        "collectionTargetId": normalize_text(target.get("collectionTargetId")),
        "collectionRoute": normalize_text(target.get("collectionRoute")),
        "existingFetchStatus": normalize_text(target.get("existingFetchStatus")),
        "gapCount": int_or_none(target.get("gapCount")) or 0,
        "missingFlags": normalize_text(target.get("missingFlags")),
        "targetEntities": normalize_text(target.get("targetEntities")),
        "recommendedActions": normalize_text(target.get("recommendedActions")),
        "extractionSource": normalize_text(extracted.get("extractionSource")),
        "candidateConfidence": confidence,
        "candidatePriorityScore": candidate_priority_score(target, link_role, confidence, keyword_hits, extension),
        "candidateReason": candidate_reason(extracted, keyword_hits, admission_like, extension),
        "operatorNextStep": "Fetch this candidate with university-admission-artifacts, then extract attachment/file routes and refresh gap source candidates.",
    }


def candidate_confidence(
    keyword_hits: list[str],
    admission_like: bool,
    extraction_source: Any,
    extension: str,
) -> str:
    source = normalize_text(extraction_source)
    if extension in DOCUMENT_EXTENSIONS:
        return "high"
    if len(keyword_hits) >= 2:
        return "high"
    if keyword_hits and admission_like:
        return "high"
    if source in {"document_location_href", "location_replace", "window_open", "tcontrol_href"} and admission_like:
        return "medium"
    if keyword_hits or admission_like:
        return "medium"
    return "low"


def candidate_priority_score(
    target: dict[str, str],
    link_role: str,
    confidence: str,
    keyword_hits: list[str],
    extension: str,
) -> int:
    role_bonus = {
        "admission_result": 70,
        "competition_rate": 65,
        "regular_admission_guide": 60,
        "recruitment_notice": 50,
        "admission_related": 25,
    }.get(link_role, 10)
    confidence_bonus = {"high": 40, "medium": 20, "low": 0}.get(confidence, 0)
    file_bonus = 35 if extension in DOCUMENT_EXTENSIONS else 0
    return (
        int_or_none(target.get("collectionPriorityScore")) or 0
    ) + (int_or_none(target.get("gapCount")) or 0) * 2 + role_bonus + confidence_bonus + file_bonus + min(30, len(keyword_hits) * 5)


def candidate_reason(
    extracted: dict[str, str],
    keyword_hits: list[str],
    admission_like: bool,
    extension: str,
) -> str:
    parts = [f"source={normalize_text(extracted.get('extractionSource'))}"]
    if keyword_hits:
        parts.append(f"keywords={','.join(keyword_hits[:8])}")
    if admission_like:
        parts.append("admission_like_url")
    if extension in DOCUMENT_EXTENSIONS:
        parts.append(f"document_extension={extension}")
    return "; ".join(parts)


def classify_link_role(text: str, keyword_hits: list[str]) -> str:
    haystack = compact(text)
    if "입시결과" in haystack or "입학결과" in haystack or "전형결과" in haystack or "result" in haystack:
        return "admission_result"
    if "경쟁률" in haystack or "ratio" in haystack:
        return "competition_rate"
    if "정시" in haystack and ("모집요강" in haystack or "전형요강" in haystack or "요강" in haystack):
        return "regular_admission_guide"
    if "모집요강" in haystack or "전형요강" in haystack or "guide" in haystack:
        return "recruitment_notice"
    return "admission_related"


def keyword_hits_for(value: str) -> list[str]:
    haystack = compact(unquote(value))
    hits = [keyword for keyword in KOREAN_KEYWORDS if keyword in haystack]
    hits.extend(keyword for keyword in ASCII_KEYWORDS if keyword in haystack)
    return hits


def has_admission_signal(raw_url: str, context: str) -> bool:
    value = compact(f"{raw_url} {context}")
    return any(keyword in value for keyword in KOREAN_KEYWORDS) or any(keyword in value for keyword in ASCII_KEYWORDS)


def has_conflicting_admission_year(target: dict[str, str], extracted: dict[str, str]) -> bool:
    target_year = int_or_none(target.get("admissionYear"))
    if target_year is None:
        return False
    direct_years = explicit_admission_years(
        " ".join(
            [
                normalize_text(extracted.get("linkText")),
                normalize_text(extracted.get("hrefRaw")),
                normalize_text(extracted.get("resolvedUrl")),
            ]
        ),
        include_plain_year=True,
    )
    if direct_years:
        return target_year not in direct_years
    context_years = explicit_admission_years(normalize_text(extracted.get("context")))
    return bool(len(context_years) == 1 and target_year not in context_years)


def is_out_of_scope_link(extracted: dict[str, str]) -> bool:
    text = " ".join(
        [
            normalize_text(extracted.get("linkText")),
            normalize_text(extracted.get("hrefRaw")),
            normalize_text(extracted.get("resolvedUrl")),
            normalize_text(extracted.get("context")),
        ]
    )
    return bool(OUT_OF_SCOPE_PATTERN.search(unquote(text)))


def explicit_admission_years(value: str, include_plain_year: bool = False) -> set[int]:
    years = set()
    decoded = unquote(value)
    for match in ADMISSION_YEAR_MENTION_PATTERN.finditer(decoded):
        year = int_or_none(match.group(1))
        if year is not None:
            years.add(year)
    if include_plain_year:
        for match in PLAIN_YEAR_PATTERN.finditer(decoded):
            year = int_or_none(match.group(1))
            if year is not None:
                years.add(year)
    return years


def is_admission_like_url(value: str) -> bool:
    parsed = urlparse(value)
    host_path = compact(f"{parsed.hostname or ''} {parsed.path}")
    return any(hint in host_path for hint in ADMISSION_HOST_HINTS)


def invalid_candidate_url(value: str) -> bool:
    lowered = value.lower()
    invalid_tokens = [
        "<",
        ">",
        "undefined",
        "warning",
        "${",
        "};",
        "`",
        "script-src",
        "unsafe-inline",
        "unsafe-eval",
        "width=device-width",
        "initial-scale",
        "target-densitydpi",
    ]
    if any(token in lowered for token in invalid_tokens):
        return True
    if any(token in value for token in ["'+", "+'", '"+', '+"']):
        return True
    if re.search(r"\s", value):
        return True
    if re.search(r"[?&][A-Za-z0-9_%-]+=$", value):
        return True
    return False


def excluded_external_host(hostname: str) -> bool:
    host = hostname.lower()
    return any(hint in host for hint in EXCLUDED_HOST_HINTS)


def resolve_candidate_url(raw: Any, base_url: str) -> str:
    value = clean_url(raw)
    if not value or value.startswith("#"):
        return ""
    lowered = value.lower()
    if lowered.startswith(("javascript:", "mailto:", "tel:", "data:")):
        return ""
    try:
        resolved = urljoin(base_url, value)
        parsed = urlparse(resolved)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return canonical_url(resolved)
    except ValueError:
        return ""


def clean_url(value: Any) -> str:
    text = html.unescape(normalize_text(value))
    text = text.replace("\\/", "/").replace("\\u0026", "&").replace("&amp;", "&")
    return text.strip().strip("'\"")


def extract_attribute(attrs: str, name: str) -> str:
    pattern = re.compile(
        rf"{name}\s*=\s*(?:\"(?P<double>[^\"]*)\"|'(?P<single>[^']*)'|(?P<bare>[^\s>]+))",
        re.I,
    )
    match = pattern.search(attrs)
    return html.unescape(match.group("double") or match.group("single") or match.group("bare") or "") if match else ""


def meta_url_candidate(attrs: str, content: str) -> str:
    attrs_lower = attrs.lower()
    attrs_compact = compact(strip_tags(html.unescape(attrs)))
    content_text = clean_url(content)
    if "http-equiv=refresh" in attrs_compact or 'http-equiv="refresh"' in attrs_lower or "http-equiv='refresh'" in attrs_lower:
        match = re.search(r"\burl\s*=\s*(?P<url>[^;]+)$", content_text, re.I)
        return clean_url(match.group("url")) if match else ""
    if any(token in attrs_compact for token in ["property=og:url", "name=twitter:url", "itemprop=url"]):
        return content_text if re.match(r"https?://", content_text, re.I) else ""
    return ""


def nearby_anchor_label(html_text: str, start: int, end: int) -> str:
    close = html_text.find("</a>", end)
    if close == -1 or close - end > 500:
        return "anchor"
    return strip_tags(html.unescape(html_text[end:close]))


def context_window(html_text: str, start: int, end: int) -> str:
    return strip_tags(html.unescape(html_text[max(0, start - 160): min(len(html_text), end + 160)]))[:500]


def strip_tags(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", value)).strip()


def file_extension_for(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.lower()
    if "." not in path:
        return ""
    extension = path.rsplit(".", 1)[-1]
    return extension if re.fullmatch(r"[a-z0-9]{1,8}", extension) else ""


def canonical_url(value: Any) -> str:
    url = clean_url(value)
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}{query}"


def link_key(year: Any, unv_cd: Any, link_role: Any, resolved_url: Any) -> tuple[str, str, str, str] | None:
    year_text = normalize_text(year)
    unv_cd_text = normalize_text(unv_cd)
    role_text = normalize_text(link_role)
    url = canonical_url(resolved_url)
    if not year_text or not unv_cd_text or not role_text or not url:
        return None
    return (year_text, unv_cd_text, role_text, url)


def summarize(
    repo_root: Path,
    inputs: list[Path],
    gap_targets: list[dict[str, str]],
    candidates: list[dict[str, Any]],
    extraction_stats: dict[str, Any],
) -> dict[str, Any]:
    return {
        "provider": "university-admission-office",
        "artifactType": "university_admission_gap_homepage_link_candidates_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(path, repo_root), "sha256": sha256_file(path)}
            for path in inputs
            if path.exists()
        ],
        "homepageTargets": {
            "total": len(gap_targets),
            "rawPagesParsed": extraction_stats["rawPagesParsedCount"],
            "targetsWithoutRawPage": extraction_stats["targetsWithoutRawPage"],
            "rawPagesMissingOnDisk": extraction_stats["rawPagesMissingOnDiskCount"],
            "discardedAssetOrLowSignalLinks": extraction_stats["discardedAssetOrLowSignalLinks"],
            "conflictingAdmissionYearLinks": extraction_stats["conflictingAdmissionYearLinks"],
            "outOfScopeLinks": extraction_stats["outOfScopeLinks"],
            "existingLinkCandidateDuplicates": extraction_stats["existingLinkCandidateDuplicates"],
        },
        "candidateRows": {
            "total": len(candidates),
            "highConfidence": sum(1 for row in candidates if row.get("candidateConfidence") == "high"),
            "mediumConfidence": sum(1 for row in candidates if row.get("candidateConfidence") == "medium"),
            "lowConfidence": sum(1 for row in candidates if row.get("candidateConfidence") == "low"),
        },
        "byAdmissionYear": dict(sorted(Counter(str(row.get("year")) for row in candidates).items())),
        "byLinkRole": counter_rows(Counter(str(row.get("linkRole")) for row in candidates), 20),
        "byExtractionSource": counter_rows(Counter(str(row.get("extractionSource")) for row in candidates), 30),
        "byCandidateConfidence": counter_rows(Counter(str(row.get("candidateConfidence")) for row in candidates), 10),
        "topHostnames": counter_rows(Counter(str(row.get("hostname")) for row in candidates), 30),
        "topUniversities": counter_rows(Counter(str(row.get("universityName")) for row in candidates), 30),
        "sampleRawPagesParsed": extraction_stats["rawPagesParsed"][:20],
        "notes": [
            "Candidates are generated from already-fetched homepage HTML for p0 gap targets where static anchor extraction found no relevant link.",
            "The CSV keeps the same leading columns as university_admission_link_candidates_YYYY.csv so it can feed university-admission-artifacts with --link-candidates.",
            "Links with explicit admission-year mentions that conflict with the target admission year are excluded.",
            "External helper or competitor-adjacent hosts such as Uway/Jinhak/Telegr are excluded before crawl candidate generation.",
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "provider",
        "artifactType",
        "year",
        "unvCd",
        "universityName",
        "campus",
        "sourceHomepageUrl",
        "finalHomepageUrl",
        "rawPath",
        "linkRole",
        "linkText",
        "hrefRaw",
        "resolvedUrl",
        "hostname",
        "fileExtension",
        "keywordHits",
        "gapHomepageLinkCandidateId",
        "collectionTargetId",
        "collectionRoute",
        "existingFetchStatus",
        "gapCount",
        "missingFlags",
        "targetEntities",
        "recommendedActions",
        "extractionSource",
        "candidateConfidence",
        "candidatePriorityScore",
        "candidateReason",
        "operatorNextStep",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


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
