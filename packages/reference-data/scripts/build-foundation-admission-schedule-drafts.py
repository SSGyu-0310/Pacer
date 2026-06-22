#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_ADMISSION_OFFICE_EVIDENCE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_admission_office_evidence_links.csv"
)
DEFAULT_KCUE_POLICY_EVIDENCE = (
    "packages/reference-data/data/public/foundation/"
    "foundation_kcue_policy_evidence_links.csv"
)
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/public/foundation"

OUTPUT_JSONL = "foundation_admission_schedule_drafts.jsonl"
OUTPUT_CSV = "foundation_admission_schedule_drafts.csv"
OUTPUT_SUMMARY = "foundation_admission_schedule_drafts_summary.json"

RECENT_YEAR_MIN = 2021
RECENT_YEAR_MAX = 2027

SCHEDULE_SIGNAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("application_period", re.compile(r"원서\s*접수|접수\s*기간|인터넷\s*접수|창구\s*접수|공통\s*원서")),
    ("document_submission", re.compile(r"서류\s*제출|제출\s*서류|등기\s*우편|방문\s*제출")),
    ("interview_exam", re.compile(r"면접\s*고사|면접\s*일|면접")),
    ("practical_exam", re.compile(r"실기\s*고사|실기\s*전형|실기")),
    ("exam_date", re.compile(r"전형\s*일|고사\s*일|논술\s*고사|필기\s*고사|시험\s*일")),
    ("admission_result_announcement", re.compile(r"합격자\s*발표|최초\s*합격|최종\s*합격|발표\s*일")),
    ("registration_period", re.compile(r"등록\s*기간|합격자\s*등록|등록금\s*납부|문서\s*등록|등록\s*확인")),
    ("additional_acceptance", re.compile(r"충원\s*합격|추가\s*합격|미등록\s*충원|충원\s*발표")),
    ("common_application", re.compile(r"공통\s*원서|유웨이어플라이|진학어플라이|통합\s*회원|표준\s*공통원서")),
    ("csat_score_release", re.compile(r"수능\s*성적|성적표|성적\s*통지|대학수학능력시험\s*성적")),
    ("admission_consulting", re.compile(r"대입\s*상담|집중\s*상담|전화\s*상담|온라인\s*상담|상담교사단")),
]

DATE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:20\d{2}|['′]\d{2})\s*[.\-년]\s*(?:1[0-2]|0?[1-9])\s*[.\-월]\s*"
        r"(?:[12]\d|3[01]|0?[1-9])(?!\d)\s*(?:[.\-일])?(?:\s*\([^)]{1,8}\))?(?:\s*\d{1,2}:\d{2})?"
    ),
    re.compile(
        r"(?<!\d)(?:1[0-2]|0?[1-9])\s*[.월]\s*"
        r"(?:[12]\d|3[01]|0?[1-9])(?!\d)\s*(?:[.일])?(?:\s*\([^)]{1,8}\))?(?:\s*\d{1,2}:\d{2})?"
    ),
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    admission_office_path = resolve(repo_root, args.admission_office_evidence)
    kcue_policy_path = resolve(repo_root, args.kcue_policy_evidence)
    output_dir = resolve(repo_root, args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    admission_office_rows = [
        row
        for row in read_csv(admission_office_path)
        if row.get("evidenceTarget") == "AdmissionSchedule"
    ]
    kcue_rows = [
        row
        for row in read_csv(kcue_policy_path)
        if row.get("targetEntity") == "AdmissionSchedule"
    ]
    drafts = build_drafts(admission_office_rows, kcue_rows)

    write_jsonl(output_dir / OUTPUT_JSONL, drafts)
    write_csv(output_dir / OUTPUT_CSV, drafts)
    summary = summarize(admission_office_path, kcue_policy_path, repo_root, admission_office_rows, kcue_rows, drafts)
    (output_dir / OUTPUT_SUMMARY).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        "foundation admission schedule drafts complete. "
        f"sourceRows={len(admission_office_rows) + len(kcue_rows)} drafts={len(drafts)} "
        f"universityScope={summary['draftRows']['universityScope']} "
        f"nationalScope={summary['draftRows']['nationalScope']}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission-office-evidence", default=DEFAULT_ADMISSION_OFFICE_EVIDENCE)
    parser.add_argument("--kcue-policy-evidence", default=DEFAULT_KCUE_POLICY_EVIDENCE)
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


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def build_drafts(
    admission_office_rows: list[dict[str, str]],
    kcue_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for row in admission_office_rows:
        years = split_joined(row.get("detectedAdmissionYears"))
        if not years:
            years = ["unknown"]
        for year in years:
            key = (
                "university",
                normalize_text(row.get("unvCd")),
                normalize_text(row.get("universityName")),
                year,
            )
            if key not in groups:
                groups[key] = new_group(key)
            add_admission_office_row(groups[key], row)

    for row in kcue_rows:
        year = normalize_text(row.get("academicYear")) or "unknown"
        key = ("national", "KCUE", "한국대학교육협의회", year)
        if key not in groups:
            groups[key] = new_group(key)
        add_kcue_row(groups[key], row)

    drafts = [finalize_group(group) for group in groups.values()]
    drafts.sort(
        key=lambda row: (
            year_sort_bucket(row.get("admissionYear")),
            -int_or_none(row.get("admissionYear") or 0) if int_or_none(row.get("admissionYear")) else 0,
            str(row.get("scheduleScope") or ""),
            str(row.get("universityName") or ""),
            -int(row.get("reviewPriorityScore") or 0),
        )
    )
    return drafts


def new_group(key: tuple[str, str, str, str]) -> dict[str, Any]:
    scope, unv_cd, university_name, admission_year = key
    return {
        "scheduleScope": scope,
        "unvCd": "" if scope == "national" else unv_cd,
        "universityName": university_name,
        "admissionYear": admission_year,
        "sourceProviders": Counter(),
        "sourceProviderCounts": Counter(),
        "evidenceRoles": Counter(),
        "evidenceTypes": Counter(),
        "documentKinds": Counter(),
        "scheduleSignals": Counter(),
        "dateCandidateValues": [],
        "sourceEvidenceIds": [],
        "sourceUrls": [],
        "attachmentUrls": [],
        "rawPaths": [],
        "sourcePaths": [],
        "viewUrls": [],
        "sampleEvidence": [],
        "maxSourcePriority": 0,
        "sourceRows": 0,
    }


def add_admission_office_row(group: dict[str, Any], row: dict[str, str]) -> None:
    group["sourceRows"] += 1
    provider = normalize_text(row.get("sourceProvider")) or "university-admission-office"
    group["sourceProviders"][provider] += 1
    group["sourceProviderCounts"][provider] += 1
    bump_counter(group["evidenceRoles"], row.get("evidenceRole"))
    for value in split_joined(row.get("evidenceTypes")):
        group["evidenceTypes"][value] += 1
    add_preview_signals(group, row.get("textPreview"))
    priority = int_or_none(row.get("reviewPriorityScore")) or 0
    group["maxSourcePriority"] = max(group["maxSourcePriority"], priority)
    evidence_id = evidence_id_for_row(row)
    add_limited(group["sourceEvidenceIds"], evidence_id, 120)
    add_limited(group["sourceUrls"], row.get("sourceCandidateUrl"), 30)
    add_limited(group["attachmentUrls"], row.get("attachmentUrl"), 30)
    add_limited(group["rawPaths"], row.get("rawPath"), 30)
    add_limited(group["sourcePaths"], row.get("sourcePath"), 30)
    add_sample(
        group,
        row=row,
        priority=priority,
        source_provider=provider,
        evidence_role=normalize_text(row.get("evidenceRole")),
        evidence_id=evidence_id,
        source_url=normalize_text(row.get("sourceCandidateUrl")),
        attachment_url=normalize_text(row.get("attachmentUrl")),
        view_url="",
    )


def add_kcue_row(group: dict[str, Any], row: dict[str, str]) -> None:
    group["sourceRows"] += 1
    provider = normalize_text(row.get("sourceProvider")) or "kcue"
    group["sourceProviders"][provider] += 1
    group["sourceProviderCounts"][provider] += 1
    bump_counter(group["evidenceRoles"], row.get("snippetRole"))
    bump_counter(group["documentKinds"], row.get("documentKind"))
    add_preview_signals(group, row.get("textPreview"))
    priority = int_or_none(row.get("reviewPriorityScore")) or 0
    group["maxSourcePriority"] = max(group["maxSourcePriority"], priority)
    evidence_id = evidence_id_for_row(row)
    add_limited(group["sourceEvidenceIds"], evidence_id, 120)
    add_limited(group["sourceUrls"], row.get("sourceUrl"), 30)
    add_limited(group["attachmentUrls"], row.get("sourceUrl"), 30)
    add_limited(group["rawPaths"], row.get("rawAttachmentPath"), 30)
    add_limited(group["sourcePaths"], row.get("textPath"), 30)
    add_limited(group["viewUrls"], row.get("viewUrl"), 30)
    add_sample(
        group,
        row=row,
        priority=priority,
        source_provider=provider,
        evidence_role=normalize_text(row.get("snippetRole")),
        evidence_id=evidence_id,
        source_url=normalize_text(row.get("sourceUrl")),
        attachment_url=normalize_text(row.get("sourceUrl")),
        view_url=normalize_text(row.get("viewUrl")),
    )


def add_preview_signals(group: dict[str, Any], value: Any) -> None:
    text = normalize_text(value)
    if not text:
        return
    for signal_name, pattern in SCHEDULE_SIGNAL_PATTERNS:
        if pattern.search(text):
            group["scheduleSignals"][signal_name] += 1
    for date_value in extract_date_candidates(text):
        add_limited(group["dateCandidateValues"], date_value, 100)


def extract_date_candidates(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    full_date_spans: list[tuple[int, int]] = []
    for index, pattern in enumerate(DATE_PATTERNS):
        for match in pattern.finditer(text):
            if index > 0 and any(match.start() >= start and match.end() <= end for start, end in full_date_spans):
                continue
            value = normalize_date_candidate(match.group(0))
            if value:
                matches.append((match.start(), value))
                if index == 0:
                    full_date_spans.append(match.span())
    matches.sort(key=lambda item: item[0])
    values: list[str] = []
    for _, value in matches:
        if value not in values:
            values.append(value)
    return values[:80]


def normalize_date_candidate(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" ,;")


def add_sample(
    group: dict[str, Any],
    row: dict[str, str],
    priority: int,
    source_provider: str,
    evidence_role: str,
    evidence_id: str,
    source_url: str,
    attachment_url: str,
    view_url: str,
) -> None:
    preview = normalize_text(row.get("textPreview"))
    if not preview:
        return
    sample = {
        "priority": priority,
        "sourceProvider": source_provider,
        "evidenceRole": evidence_role,
        "sourceEvidenceId": evidence_id,
        "sourceUrl": source_url,
        "attachmentUrl": attachment_url,
        "viewUrl": view_url,
        "dateCandidateValues": extract_date_candidates(preview)[:20],
        "scheduleSignals": detect_schedule_signals(preview),
        "preview": preview[:700],
    }
    samples = group["sampleEvidence"]
    if sample["sourceEvidenceId"] in {item.get("sourceEvidenceId") for item in samples}:
        return
    samples.append(sample)
    samples.sort(
        key=lambda item: (
            -int(item.get("priority") or 0),
            -len(item.get("scheduleSignals") or []),
            -len(item.get("dateCandidateValues") or []),
        )
    )
    del samples[8:]


def detect_schedule_signals(text: str) -> list[str]:
    return [signal_name for signal_name, pattern in SCHEDULE_SIGNAL_PATTERNS if pattern.search(text)]


def finalize_group(group: dict[str, Any]) -> dict[str, Any]:
    year = normalize_text(group["admissionYear"])
    status = "unknown" if year == "unknown" else "detected"
    provider_counts = dict(sorted(group["sourceProviderCounts"].items()))
    signal_names = sorted(group["scheduleSignals"])
    date_values = group["dateCandidateValues"][:80]
    flags = draft_flags(group, signal_names, date_values)
    schedule_json_draft = {
        "status": "review_candidate",
        "scheduleScope": group["scheduleScope"],
        "admissionYearStatus": status,
        "scheduleSignals": signal_names,
        "dateCandidateValues": date_values[:40],
        "sourceEvidenceIds": group["sourceEvidenceIds"][:30],
        "needsHumanVerification": True,
    }
    return {
        "scheduleDraftId": deterministic_uuid(
            f"admission-schedule-draft:{group['scheduleScope']}:{group['unvCd']}:{group['universityName']}:{year}"
        ),
        "artifactType": "foundation_admission_schedule_draft",
        "scheduleScope": group["scheduleScope"],
        "unvCd": group["unvCd"],
        "universityName": group["universityName"],
        "admissionYear": "" if year == "unknown" else int_or_none(year),
        "admissionYearStatus": status,
        "sourceRows": group["sourceRows"],
        "sourceProviders": "|".join(provider_counts),
        "sourceProviderCounts": provider_counts,
        "evidenceRoles": counter_to_rows(group["evidenceRoles"], 20),
        "evidenceTypes": counter_to_rows(group["evidenceTypes"], 20),
        "documentKinds": counter_to_rows(group["documentKinds"], 20),
        "reviewPriorityScore": draft_priority(group, signal_names, date_values, flags),
        "reviewStrength": review_strength(group, signal_names, date_values),
        "draftFlags": "|".join(flags),
        "scheduleSignals": "|".join(signal_names),
        "dateCandidateValues": "|".join(date_values),
        "scheduleJsonDraft": schedule_json_draft,
        "sampleEvidence": group["sampleEvidence"],
        "sourceEvidenceIds": "|".join(group["sourceEvidenceIds"][:120]),
        "sourceUrls": "|".join(group["sourceUrls"]),
        "attachmentUrls": "|".join(group["attachmentUrls"]),
        "rawPaths": "|".join(group["rawPaths"]),
        "sourcePaths": "|".join(group["sourcePaths"]),
        "viewUrls": "|".join(group["viewUrls"]),
        "reviewStatus": "needs_human_verification",
    }


def draft_flags(group: dict[str, Any], signals: list[str], dates: list[str]) -> list[str]:
    flags = []
    if dates:
        flags.append("has_date_candidates")
    if group["sourceRows"] >= 2:
        flags.append("has_multiple_evidence")
    if "application_period" in signals:
        flags.append("has_application_period_signal")
    if "common_application" in signals:
        flags.append("has_common_application_signal")
    if "registration_period" in signals:
        flags.append("has_registration_signal")
    if "additional_acceptance" in signals:
        flags.append("has_additional_acceptance_signal")
    if "admission_result_announcement" in signals:
        flags.append("has_result_announcement_signal")
    if "admission_consulting" in signals:
        flags.append("has_admission_consulting_signal")
    if not dates or not signals:
        flags.append("low_signal_schedule_candidate")
    return flags


def draft_priority(group: dict[str, Any], signals: list[str], dates: list[str], flags: list[str]) -> int:
    evidence_bonus = min(int(group["sourceRows"]), 30)
    signal_bonus = min(len(signals) * 8, 60)
    date_bonus = min(len(dates) * 3, 45)
    scope_bonus = 12 if group["scheduleScope"] == "national" else 0
    quality_penalty = 20 if "low_signal_schedule_candidate" in flags else 0
    return max(0, int(group["maxSourcePriority"]) + evidence_bonus + signal_bonus + date_bonus + scope_bonus - quality_penalty)


def review_strength(group: dict[str, Any], signals: list[str], dates: list[str]) -> str:
    if len(signals) >= 4 and len(dates) >= 2 and group["sourceRows"] >= 2:
        return "high"
    if len(signals) >= 2 and dates:
        return "medium"
    return "low"


def summarize(
    admission_office_path: Path,
    kcue_policy_path: Path,
    repo_root: Path,
    admission_office_rows: list[dict[str, str]],
    kcue_rows: list[dict[str, str]],
    drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_admission_schedule_drafts_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": [
            {"path": to_repo_relative(admission_office_path, repo_root), "sha256": sha256_file(admission_office_path)},
            {"path": to_repo_relative(kcue_policy_path, repo_root), "sha256": sha256_file(kcue_policy_path)},
        ],
        "sourceRows": {
            "admissionOfficeScheduleEvidenceRows": len(admission_office_rows),
            "kcueScheduleEvidenceRows": len(kcue_rows),
            "total": len(admission_office_rows) + len(kcue_rows),
        },
        "draftRows": {
            "total": len(drafts),
            "universityScope": sum(1 for row in drafts if row["scheduleScope"] == "university"),
            "nationalScope": sum(1 for row in drafts if row["scheduleScope"] == "national"),
            "detectedAdmissionYear": sum(1 for row in drafts if row["admissionYearStatus"] == "detected"),
            "unknownAdmissionYear": sum(1 for row in drafts if row["admissionYearStatus"] == "unknown"),
            "recentAdmissionYears2021To2027": sum(
                1
                for row in drafts
                if isinstance(row.get("admissionYear"), int)
                and RECENT_YEAR_MIN <= int(row["admissionYear"]) <= RECENT_YEAR_MAX
            ),
        },
        "byAdmissionYear": counter_rows(Counter(str(row.get("admissionYear") or "unknown") for row in drafts)),
        "byScheduleScope": counter_rows(Counter(str(row.get("scheduleScope") or "") for row in drafts)),
        "byReviewStrength": counter_rows(Counter(str(row.get("reviewStrength") or "") for row in drafts)),
        "byScheduleSignal": counter_rows(
            Counter(signal for row in drafts for signal in split_joined(row.get("scheduleSignals"))),
            limit=30,
        ),
        "byDraftFlag": counter_rows(
            Counter(flag for row in drafts for flag in split_joined(row.get("draftFlags"))),
            limit=30,
        ),
        "bySourceProviders": counter_rows(Counter(str(row.get("sourceProviders") or "") for row in drafts)),
        "notes": [
            "Drafts are grouped by university/admission year for admission-office evidence and by admission year for KCUE national evidence.",
            "dateCandidateValues are raw schedule-like date strings from snippets, not verified AdmissionSchedule rows.",
            "scheduleJsonDraft is a review scaffold and must remain needs_human_verification until source comparison is complete.",
        ],
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "scheduleDraftId",
        "artifactType",
        "scheduleScope",
        "unvCd",
        "universityName",
        "admissionYear",
        "admissionYearStatus",
        "sourceRows",
        "sourceProviders",
        "sourceProviderCounts",
        "evidenceRoles",
        "evidenceTypes",
        "documentKinds",
        "reviewPriorityScore",
        "reviewStrength",
        "draftFlags",
        "scheduleSignals",
        "dateCandidateValues",
        "scheduleJsonDraft",
        "sampleEvidence",
        "sourceEvidenceIds",
        "sourceUrls",
        "attachmentUrls",
        "rawPaths",
        "sourcePaths",
        "viewUrls",
        "reviewStatus",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fields})


def csv_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if value is None:
        return ""
    return value


def bump_counter(counter: Counter[str], value: Any) -> None:
    text = normalize_text(value)
    if text:
        counter[text] += 1


def add_limited(values: list[str], value: Any, limit: int) -> None:
    text = normalize_text(value)
    if text and text not in values and len(values) < limit:
        values.append(text)


def split_joined(value: Any) -> list[str]:
    text = normalize_text(value)
    return [part for part in text.split("|") if part]


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def counter_to_rows(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def counter_rows(counter: Counter[str], limit: int | None = None) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def evidence_id_for_row(row: dict[str, str]) -> str:
    return normalize_text(row.get("sourceEvidenceId") or row.get("evidenceCandidateSha256"))


def deterministic_uuid(value: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"https://pacer.local/reference-data/{value}"))


def int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def year_sort_bucket(value: Any) -> int:
    year = int_or_none(value)
    if year is None:
        return 3
    if RECENT_YEAR_MIN <= year <= RECENT_YEAR_MAX:
        return 0
    if year > RECENT_YEAR_MAX:
        return 1
    return 2


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
