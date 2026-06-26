#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_FILLS = "packages/reference-data/data/review/core-rule-fills.jsonl"
DEFAULT_DECISIONS = "packages/reference-data/data/review/review-decisions.jsonl"
DEFAULT_BLOCKERS = "packages/reference-data/data/review/core-rule-blockers.jsonl"
DEFAULT_OUTPUT = "packages/reference-data/data/review/core-rule-review-audit-summary.json"

ALLOWED_BLOCKER_TYPES = {
    "conversion_table_or_formula_gap",
    "engine_formula_gap",
    "official_method_pending",
    "source_or_formula_unverified",
    "unit_mapping_unsafe",
    "scope_or_no_regular_csat_formula",
    "missing_official_grade_table",
    "needs_human_verification",
}

HIGH_RISK_VERIFIED_TERMS = (
    "추정",
    "확인 필요",
    "패턴 기반",
    "패턴기반",
    "미명시",
    "미확인",
)

PARTIAL_EXACT_TERMS = (
    "상위점수",
    "상위 점수",
    "높은 점수 선택",
    "conversionRisk",
    "변환표준점수",
    "자체변환",
    "자체 변환",
    "변환점수",
    "수능 후 공고",
    "가산점은 엔진 미지원",
    "가산점 미반영",
    "가산은 현 엔진 미지원",
    "감점표는 추출 원문",
    "자동승격 필드에서는 제외",
    "현 엔진 미지원",
    "미지원",
    "미반영",
    "별도 track 미분리",
    "별도식",
    "별도 배점",
    "단순화",
    "순수수능 아님",
    "통합",
)

EXACT_STATUSES = {"verified", "live"}


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    fills_path = resolve(repo_root, args.fills)
    decisions_path = resolve(repo_root, args.decisions)
    blockers_path = resolve(repo_root, args.blockers)
    output_path = resolve(repo_root, args.output)

    errors: list[str] = []
    warnings: list[str] = []
    fills = read_jsonl(fills_path, errors)
    decisions = read_jsonl(decisions_path, errors)
    blockers = read_jsonl(blockers_path, errors)

    verified_fills = [row for row in fills if row.get("verified") is True]
    unverified_fills = [row for row in fills if row.get("verified") is not True]
    active_core_decisions = [
        row for row in decisions if row.get("reviewer") == "agent:core-rule-fill"
    ]

    if len(blockers) != len(unverified_fills):
        errors.append(
            f"blocker/unverified fill count mismatch: blockers={len(blockers)} "
            f"unverifiedFills={len(unverified_fills)}"
        )

    risky_verified_fills = [
        row for row in verified_fills if has_high_risk_verified_uncertainty(row)
    ]
    if risky_verified_fills:
        errors.append(
            "verified fills contain high-risk uncertainty terms: "
            + ", ".join(
                f"{row.get('universityName')}({row.get('universityId')})"
                for row in risky_verified_fills[:20]
            )
        )
    partial_exact_fills = [row for row in verified_fills if should_auto_downgrade_to_parsed(row)]

    unverified_keys = Counter(fill_key(row) for row in unverified_fills)
    blocker_keys = Counter(blocker_key(row) for row in blockers)
    if unverified_keys != blocker_keys:
        missing = list((unverified_keys - blocker_keys).elements())
        extra = list((blocker_keys - unverified_keys).elements())
        errors.append(f"blocker keys do not match unverified fills: missing={missing} extra={extra}")

    blocker_types = Counter(str(row.get("blockerType") or "") for row in blockers)
    invalid_blocker_types = sorted(set(blocker_types) - ALLOWED_BLOCKER_TYPES)
    if invalid_blocker_types:
        errors.append(f"invalid blocker types: {invalid_blocker_types}")

    promotion_allowed = [row for row in blockers if row.get("autoPromotionAllowed") is not False]
    if promotion_allowed:
        errors.append(f"{len(promotion_allowed)} blockers allow auto promotion")
    parsed_promotion_blockers = [
        row for row in blockers if row.get("parsedPromotionAllowed") is True
    ]

    blockers_without_raw_evidence = [
        row.get("universityName") for row in blockers if not valid_raw_evidence(row, repo_root)
    ]
    if blockers_without_raw_evidence:
        errors.append(f"blockers missing raw evidence path: {blockers_without_raw_evidence}")

    blocker_universities = {str(row.get("universityId") or "") for row in blockers}
    parsed_allowed_scopes = {
        f"{row.get('universityId')}|{row.get('year')}|core-fill"
        for row in parsed_promotion_blockers
    }
    leaked_decisions = []
    for decision in active_core_decisions:
        scope = str(decision.get("approval_scope_key") or decision.get("approvalScopeKey") or "")
        university_id = scope.split("|", 1)[0]
        if university_id in blocker_universities:
            reviewed_status = decision.get("reviewed_verified_status") or decision.get(
                "reviewedVerifiedStatus"
            )
            if not (scope in parsed_allowed_scopes and reviewed_status == "parsed"):
                leaked_decisions.append(decision.get("target_id") or decision.get("targetId"))
    if leaked_decisions:
        errors.append(f"active decisions exist for blocked universities: {leaked_decisions[:10]}")

    ratio_decisions_missing_weight = []
    bad_inquiry = []
    exact_decisions_for_partial_fills = []
    partial_scope_keys = {
        f"{row.get('universityId')}|{row.get('year')}|core-fill" for row in partial_exact_fills
    }
    for decision in active_core_decisions:
        corrected = decision.get("corrected_fields") or decision.get("correctedFields") or {}
        english = corrected.get("englishPolicyJson") or {}
        inquiry = corrected.get("inquiryPolicyJson") or {}
        reviewed_status = decision.get("reviewed_verified_status") or decision.get(
            "reviewedVerifiedStatus"
        )
        scope_key = decision.get("approval_scope_key") or decision.get("approvalScopeKey")
        if english.get("mode") == "ratio" and not positive_number(english.get("weight")):
            ratio_decisions_missing_weight.append(decision.get("target_id") or decision.get("targetId"))
        if inquiry.get("count") not in (1, 2) or inquiry.get("mode") not in ("average", "best_one", "sum"):
            bad_inquiry.append(decision.get("target_id") or decision.get("targetId"))
        if scope_key in partial_scope_keys and reviewed_status in EXACT_STATUSES:
            exact_decisions_for_partial_fills.append(
                decision.get("target_id") or decision.get("targetId")
            )
    if ratio_decisions_missing_weight:
        errors.append(f"ratio decisions missing positive weight: {ratio_decisions_missing_weight[:10]}")
    if bad_inquiry:
        errors.append(f"decisions with invalid inquiry policy: {bad_inquiry[:10]}")
    if exact_decisions_for_partial_fills:
        errors.append(
            "partial exact fills leaked as verified/live decisions: "
            f"{exact_decisions_for_partial_fills[:10]}"
        )

    if not active_core_decisions and verified_fills:
        warnings.append("verified fills exist but no active core-rule-fill decisions were found")

    summary = {
        "provider": "pacer-reference-data",
        "artifactType": "core_rule_review_audit_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "inputs": {
            "fills": to_repo_relative(fills_path, repo_root),
            "decisions": to_repo_relative(decisions_path, repo_root),
            "blockers": to_repo_relative(blockers_path, repo_root),
        },
        "counts": {
            "fills": len(fills),
            "verifiedFills": len(verified_fills),
            "unverifiedFills": len(unverified_fills),
            "activeCoreRuleFillDecisions": len(active_core_decisions),
            "blockers": len(blockers),
        },
        "blockerTypes": dict(sorted(blocker_types.items())),
        "blockerEvidence": {
            "missingRawEvidencePath": len(blockers_without_raw_evidence),
        },
        "blockerPromotion": {
            "parsedPromotionAllowed": len(parsed_promotion_blockers),
        },
        "fillSafety": {
            "highRiskVerifiedFills": len(risky_verified_fills),
            "autoDowngradedParsedFills": len(partial_exact_fills),
        },
        "decisionChecks": {
            "ratioDecisionsMissingWeight": len(ratio_decisions_missing_weight),
            "invalidInquiryPolicies": len(bad_inquiry),
            "blockedUniversityDecisionLeaks": len(leaked_decisions),
            "partialExactDecisionLeaks": len(exact_decisions_for_partial_fills),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "core rule review audit complete. "
        f"status={summary['status']} fills={len(fills)} verified={len(verified_fills)} "
        f"decisions={len(active_core_decisions)} blockers={len(blockers)}"
    )
    if errors:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fills", default=DEFAULT_FILLS)
    parser.add_argument("--decisions", default=DEFAULT_DECISIONS)
    parser.add_argument("--blockers", default=DEFAULT_BLOCKERS)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
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


def read_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        errors.append(f"missing input: {path}")
        return rows
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name} line {line_no}: invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"{path.name} line {line_no}: expected object")
            continue
        rows.append(value)
    return rows


def fill_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("universityId") or ""),
        str(row.get("source") or ""),
        str(row.get("year") or ""),
    )


def blocker_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("universityId") or ""),
        str(row.get("source") or ""),
        str(row.get("year") or ""),
    )


def positive_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and value > 0


def has_high_risk_verified_uncertainty(row: dict[str, Any]) -> bool:
    text = " ".join(str(value) for value in row.get("uncertain") or [])
    return any(term in text for term in HIGH_RISK_VERIFIED_TERMS)


def should_auto_downgrade_to_parsed(row: dict[str, Any]) -> bool:
    explicit = row.get("verifiedStatus") or row.get("reviewedVerifiedStatus")
    if explicit == "parsed":
        return True
    if has_external_components(row):
        return True
    text = " ".join(str(value) for value in row.get("uncertain") or [])
    return any(term in text for term in PARTIAL_EXACT_TERMS)


def has_external_components(row: dict[str, Any]) -> bool:
    if non_empty_list(row.get("externalComponents")):
        return True
    if non_empty_list(row.get("formulaAlternatives")):
        for alternative in row["formulaAlternatives"]:
            if isinstance(alternative, dict) and non_empty_list(alternative.get("externalComponents")):
                return True
    for track in row.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        if non_empty_list(track.get("externalComponents")):
            return True
        for alternative in track.get("formulaAlternatives") or track.get("alternatives") or []:
            if isinstance(alternative, dict) and non_empty_list(alternative.get("externalComponents")):
                return True
    return False


def non_empty_list(value: Any) -> bool:
    return isinstance(value, list) and len(value) > 0


def valid_raw_evidence(row: dict[str, Any], repo_root: Path) -> bool:
    if row.get("sourceProvider") == "official_or_manual":
        return isinstance(row.get("source"), str) and bool(row.get("source"))
    raw_path = row.get("rawEvidencePath")
    return isinstance(raw_path, str) and bool(raw_path) and (repo_root / raw_path).exists()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
