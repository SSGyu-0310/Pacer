#!/usr/bin/env python3
"""
core-rule-fills.jsonl (에이전트 산출: 대학 × 계열 환산식)
  → review-decisions.jsonl (모집단위별 AdmissionRule.id 결정)

각 대학 fill의 track(계열별 weights)을 해당 대학 2027 모집단위에 majorGroup으로 매칭해
모집단위마다 엔진 형태 corrected_fields를 부여한 'edit' 결정을 만든다.
seed-p0가 review-decisions.jsonl을 읽어 재적용하면 해당 단위가 운영 후보로 풀린다.
검증된 exact rule은 verified로, raw evidence는 있으나 산식/단위/엔진 제약이 남은 rule은
parsed 저신뢰도 결정으로 제한 승격한다.

- 멱등: target_id별 결정 id를 uuid5로 고정. 기존 review-decisions.jsonl의 다른 target은 보존,
  같은 target은 덮어쓴다.
- verified=false라도 parsedPromotionAllowed 조건(raw evidence + 구조화 rule + 안전한 매칭)을
  만족하면 parsed 결정으로 만든다. 그 외 미검증/weights 누락 fill은 blocker로 남긴다.

Usage:
  python3 scripts/build-core-rule-fill-decisions.py
  python3 scripts/build-core-rule-fill-decisions.py --data-dir packages/reference-data/data/p0-foundation
"""
import argparse
import csv
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

NS = uuid.UUID("a1f0c0de-0000-5000-8000-000000000001")  # 고정 네임스페이스(멱등 id용)
HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(PKG))

VERIFIED_STATUSES = {"draft", "parsed", "verified", "live", "deprecated"}
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
    "한국사도 가산점",
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


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"{os.path.basename(path)} line {i}: invalid JSON: {e}")
    return out


def pick(track, fill, *keys, default=None):
    for k in keys:
        if k in track and track[k] is not None:
            return track[k]
    for k in keys:
        if k in fill and fill[k] is not None:
            return fill[k]
    return default


def numeric_by_grade(raw):
    out = {}
    if isinstance(raw, dict):
        for g, v in raw.items():
            if isinstance(v, (int, float)):
                out[str(g)] = v
    return out


def english_policy(eng):
    """영어 정책 — deduction/addition은 byGrade만, ratio는 weight/scoreMax도 보존."""
    mode = eng.get("mode", "deduction")
    out = {"mode": mode, "byGrade": numeric_by_grade(eng.get("byGrade"))}
    if mode == "ratio":
        weight = eng.get("weight")
        if isinstance(weight, (int, float)):
            out["weight"] = weight
        score_max = eng.get("scoreMax")
        if isinstance(score_max, (int, float)):
            out["scoreMax"] = score_max
    return out


def corrected_fields(fill, track):
    weights = pick(track, fill, "weights")
    if not isinstance(weights, dict):
        return None
    total = pick(track, fill, "totalScale", "total_scale")
    if not isinstance(total, (int, float)) or total <= 0:
        return None
    eng = pick(track, fill, "english") or {}
    inq = pick(track, fill, "inquiry") or {}
    hist = pick(track, fill, "history") or {}
    score_type = pick(track, fill, "scoreType", "score_type", default="custom")

    cf = {
        "scoreType": score_type,
        "formulaJson": {
            "totalScale": total,
            "weights": {
                "korean": weights.get("korean", 0),
                "math": weights.get("math", 0),
                "inquiry": weights.get("inquiry", 0),
            },
        },
        "englishPolicyJson": english_policy(eng),
        "historyPolicyJson": {"byGrade": numeric_by_grade(hist.get("byGrade"))},
        "inquiryPolicyJson": {
            "count": int(inq.get("count", 2)),
            "mode": inq.get("mode", "average"),
            "conversionRisk": bool(inq.get("conversionRisk", False)),
        },
        "eligibilityJson": pick(track, fill, "eligibility") or {},
    }
    selection_policy = pick(track, fill, "selectionPolicy")
    if isinstance(selection_policy, dict):
        cf["formulaJson"]["selectionPolicy"] = selection_policy
    return cf


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


def parsed_promotion_allowed(fill):
    if fill.get("verified") is True:
        return True
    text = " ".join(str(value) for value in fill.get("uncertain") or [])
    if not adiga_raw_path(fill):
        return False
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
    if tracks_are_unit_name_scoped(fill) and has_structured_rule(fill):
        return True
    if not any(term in text for term in ("추정", "확인 필요", "패턴 기반", "패턴기반", "미명시", "미확인")):
        return False
    if any(
        term in text
        for term in (
            "분리할 수 없음",
            "majorGroup 매핑",
        )
    ):
        return False
    return has_structured_rule(fill)


def tracks_are_unit_name_scoped(fill):
    tracks = fill.get("tracks")
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


def has_structured_rule(fill):
    tracks = fill.get("tracks")
    if not tracks and not isinstance(fill.get("weights"), dict):
        return False
    english = fill.get("english") or {}
    inquiry = fill.get("inquiry") or {}
    return isinstance(english, dict) and isinstance(inquiry, dict)


def track_for(unit_name, major_group, tracks):
    """모집단위 이름 또는 majorGroup에 맞는 track. 단일 전체식은 majorGroups/unitNames를 비워둔 경우만 허용."""
    for t in tracks:
        unit_names = t.get("unitNames") or []
        if unit_name and unit_name in unit_names:
            return t
    for t in tracks:
        groups = t.get("majorGroups") or []
        if major_group and major_group in groups:
            return t
    if (
        len(tracks) == 1
        and not (tracks[0].get("majorGroups") or [])
        and not (tracks[0].get("unitNames") or [])
    ):
        return tracks[0]
    return None


def reviewed_status(fill):
    explicit = fill.get("verifiedStatus") or fill.get("reviewedVerifiedStatus")
    if explicit in VERIFIED_STATUSES:
        return explicit
    text = " ".join(str(value) for value in fill.get("uncertain") or [])
    if any(term in text for term in PARTIAL_EXACT_TERMS):
        return "parsed"
    return "verified"


def reviewed_confidence(status):
    return "low" if status == "parsed" else "high"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=os.path.join(PKG, "data", "p0-foundation"))
    ap.add_argument("--fills", default=os.path.join(PKG, "data", "review", "core-rule-fills.jsonl"))
    ap.add_argument("--out", default=os.path.join(PKG, "data", "review", "review-decisions.jsonl"))
    args = ap.parse_args()

    fills = load_jsonl(args.fills)
    if not fills:
        print(f"no fills at {args.fills} — 에이전트가 먼저 core-rule-fills.jsonl을 산출해야 합니다.")
        return

    units = {r["id"]: r for r in csv.DictReader(open(os.path.join(args.data_dir, "admission_units.csv")))}
    rules = list(csv.DictReader(open(os.path.join(args.data_dir, "admission_rules.csv"))))
    rules_by_uni = {}
    for r in rules:
        u = units.get(r["unitId"])
        if u:
            rules_by_uni.setdefault(u["universityId"], []).append(r)

    now = datetime.now(timezone.utc).isoformat()
    new_decisions = {}  # target_id -> decision dict
    stats = {"universities": 0, "units": 0, "skipped_fill": 0, "unmatched_units": 0}

    for fill in fills:
        uid = fill.get("universityId")
        if not parsed_promotion_allowed(fill):
            stats["skipped_fill"] += 1
            continue
        tracks = fill.get("tracks")
        if not tracks:
            # weights를 fill 최상위에 둔 단일 식도 허용
            if isinstance(fill.get("weights"), dict):
                tracks = [{"majorGroups": [], "weights": fill["weights"]}]
            else:
                stats["skipped_fill"] += 1
                continue

        uni_rules = rules_by_uni.get(uid, [])
        if not uni_rules:
            continue
        stats["universities"] += 1
        scope = f"{uid}|2027|core-fill"
        status = reviewed_status(fill) if fill.get("verified") is True else "parsed"

        for r in uni_rules:
            unit = units.get(r["unitId"]) or {}
            mg = unit.get("majorGroup", "")
            unit_name = unit.get("name", "")
            track = track_for(unit_name, mg, tracks)
            if track is None:
                stats["unmatched_units"] += 1
                continue
            cf = corrected_fields(fill, track)
            if cf is None:
                stats["unmatched_units"] += 1
                continue
            tid = r["id"]
            new_decisions[tid] = {
                "id": str(uuid.uuid5(NS, f"core-rule-fill:{tid}")),
                "target_kind": "rule",
                "target_id": tid,
                "verdict": "edit",
                "reviewed_verified_status": status,
                "reviewed_confidence": reviewed_confidence(status),
                "corrected_fields": cf,
                "evidence_checked": True,
                "approval_scope_key": scope,
                "reviewer": "agent:core-rule-fill",
                "review_notes": fill.get("source", "")[:500],
                "reviewed_at": now,
            }
            stats["units"] += 1

    # 기존 decisions 병합: core-rule-fill 산출물은 stale 방지를 위해 매번 재생성본으로 교체하고,
    # 다른 reviewer/워크플로우가 만든 decision은 보존한다.
    existing = load_jsonl(args.out)
    merged = []
    for d in existing:
        if d.get("reviewer") == "agent:core-rule-fill":
            continue
        tid = d.get("target_id") or d.get("targetId")
        if tid in new_decisions:
            continue
        merged.append(d)
    merged.extend(new_decisions.values())

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for d in merged:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(
        f"wrote {args.out}\n"
        f"  universities applied: {stats['universities']}\n"
        f"  unit decisions: {stats['units']}\n"
        f"  fills skipped (not promotable/no weights): {stats['skipped_fill']}\n"
        f"  units unmatched (no track / bad fields): {stats['unmatched_units']}\n"
        f"  total lines in file: {len(merged)}"
    )


if __name__ == "__main__":
    main()
