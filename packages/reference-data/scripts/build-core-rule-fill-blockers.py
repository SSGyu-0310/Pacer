#!/usr/bin/env python3
"""
core-rule-fills.jsonl의 verified=false 항목을 운영 blocker 산출물로 분리한다.

이 파일은 AdmissionRule 승격 결정이 아니며, 시제품 운영/다음 검수자가
"왜 50개 중 일부가 review-decisions로 승격되지 않았는지"를 추적하기 위한
비파괴적 진단 산출물이다.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PKG))


def load_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"{os.path.basename(path)} line {line_no}: invalid JSON: {e}")
    return rows


def classify(row):
    text = " ".join(row.get("uncertain") or [])
    university = row.get("universityName", "")
    if "포항공과" in university or "POSTECH" in text:
        return "scope_or_no_regular_csat_formula"
    if "미확정" in text or "추후" in text:
        return "official_method_pending"
    if "majorGroup" in text or "매핑" in text or "분리할 수 없음" in text:
        return "unit_mapping_unsafe"
    if any(term in text for term in ("추정", "확인 필요", "패턴 기반", "패턴기반", "미명시", "미확인")):
        return "source_or_formula_unverified"
    if "전국 최고" in text or "표준점수 최고점" in text or "기본점수" in text:
        return "engine_formula_gap"
    if "변환표준점수" in text or "변환백분위" in text:
        return "conversion_table_or_formula_gap"
    if "영어" in text and ("없음" in text or "누락" in text):
        return "missing_official_grade_table"
    return "needs_human_verification"


def next_action(blocker_type):
    return {
        "scope_or_no_regular_csat_formula": "수시-only/scope override 여부를 확인하고 정시 수능 환산식 자동승격 대상에서 제외한다.",
        "official_method_pending": "대학 입학처의 2027 정시 모집요강 확정본 또는 변환표준점수 공지를 기다린 뒤 재검수한다.",
        "source_or_formula_unverified": "공식 원문에서 환산 총점·반영지표·등급표를 직접 확인한 뒤에만 verified로 전환한다.",
        "unit_mapping_unsafe": "공식 원문 기준 적용 단위를 unitName으로 분리한 뒤에만 verified로 전환한다.",
        "engine_formula_gap": "전국 최고 표준점수·기본점수·실질반영점수 산식을 엔진이 지원할 때까지 exact 승격하지 않는다.",
        "conversion_table_or_formula_gap": "대학 자체 변환표준점수/변환백분위 표와 적용 단위를 원문에서 대조한 뒤 승격한다.",
        "missing_official_grade_table": "공식 영어 등급별 변환점수표를 확보한 뒤 ratio/addition/deduction 값을 확정한다.",
    }.get(blocker_type, "공식 원문 대조와 사람 검수 후에만 verified로 전환한다.")


def parsed_promotion_allowed(row, blocker_type, raw_path):
    if not raw_path:
        return False
    text = " ".join(row.get("uncertain") or [])
    if any(
        term in text
        for term in (
            "미확정",
            "추후",
            "전국 최고",
            "전국최고",
            "기본점수",
            "불일치",
        )
    ):
        return False
    if tracks_are_unit_name_scoped(row) and blocker_type in {
        "conversion_table_or_formula_gap",
        "unit_mapping_unsafe",
        "engine_formula_gap",
        "needs_human_verification",
    }:
        return tracks_are_unit_name_scoped(row) and has_structured_rule(row)
    if blocker_type != "source_or_formula_unverified":
        return False
    if "분리할 수 없음" in text or "majorGroup 매핑" in text:
        return False
    return has_structured_rule(row)


def tracks_are_unit_name_scoped(row):
    tracks = row.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        return False
    for track in tracks:
        if not isinstance(track, dict):
            return False
        if track.get("majorGroups"):
            return False
        unit_names = track.get("unitNames")
        if not isinstance(unit_names, list) or not unit_names:
            return False
    return True


def has_structured_rule(row):
    if not row.get("tracks") and not isinstance(row.get("weights"), dict):
        return False
    return isinstance(row.get("english"), dict) and isinstance(row.get("inquiry"), dict)


def adiga_raw_path(row):
    source = row.get("source") or ""
    year = str(row.get("year") or "")
    parsed = urlparse(source)
    query = parse_qs(parsed.query)
    unv_cd = (query.get("unvCd") or [""])[0]
    search_year = (query.get("searchSyr") or [year])[0]
    if not unv_cd or not search_year:
        return None
    rel = os.path.join(".reference-data", "raw", "adiga", search_year, unv_cd, "selection.html")
    return rel if os.path.exists(os.path.join(REPO, rel)) else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fills", default=os.path.join(PKG, "data", "review", "core-rule-fills.jsonl"))
    parser.add_argument("--out", default=os.path.join(PKG, "data", "review", "core-rule-blockers.jsonl"))
    args = parser.parse_args()

    rows = load_jsonl(args.fills)
    now = datetime.now(timezone.utc).isoformat()
    blockers = []
    for row in rows:
        if row.get("verified") is True:
            continue
        blocker_type = classify(row)
        raw_path = adiga_raw_path(row)
        allow_parsed = parsed_promotion_allowed(row, blocker_type, raw_path)
        blockers.append(
            {
                "universityId": row.get("universityId"),
                "universityName": row.get("universityName"),
                "year": row.get("year"),
                "source": row.get("source"),
                "sourceProvider": "adiga" if raw_path else "official_or_manual",
                "rawEvidencePath": raw_path,
                "scoreType": row.get("scoreType"),
                "blockerType": blocker_type,
                "autoPromotionAllowed": False,
                "parsedPromotionAllowed": allow_parsed,
                "uncertain": row.get("uncertain") or [],
                "nextAction": next_action(blocker_type),
                "generatedAt": now,
            }
        )

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for blocker in blockers:
            f.write(json.dumps(blocker, ensure_ascii=False) + "\n")

    print(f"wrote {args.out}")
    print(f"  blockers: {len(blockers)}")
    for blocker in blockers:
        print(f"  - {blocker['universityName']}: {blocker['blockerType']}")


if __name__ == "__main__":
    main()
