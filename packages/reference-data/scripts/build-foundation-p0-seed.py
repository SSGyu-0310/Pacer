#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import sys
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_OUTPUT_DIR = "packages/reference-data/data/p0-foundation"


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


UNIVERSITY_FIELDS = ["id", "name", "campus", "region", "type", "displayOrder"]
UNIT_FIELDS = ["id", "universityId", "name", "recruitmentGroup", "majorGroup", "quota", "year", "active"]
RULE_FIELDS = [
    "id",
    "unitId",
    "year",
    "scoreType",
    "formulaJson",
    "totalScale",
    "koreanWeight",
    "mathWeight",
    "inquiryWeight",
    "englishPolicyJson",
    "historyPolicyJson",
    "inquiryPolicyJson",
    "eligibilityJson",
    "sourceUrl",
    "verifiedStatus",
]
OUTCOME_FIELDS = [
    "id",
    "unitId",
    "year",
    "avgScore",
    "cutScore",
    "percentileCut",
    "competitionRate",
    "additionalPass",
    "sourceUrl",
    "confidence",
]


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    output_dir = resolve(repo_root, args.output_dir)
    if output_dir.exists() and args.clean:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    universities = build_universities(foundation_dir)
    units = build_units(foundation_dir)
    outcomes = build_outcomes(foundation_dir, {row["id"] for row in units})
    rules = build_rules(foundation_dir, units)

    write_csv(output_dir / "universities.csv", universities, UNIVERSITY_FIELDS)
    write_csv(output_dir / "admission_units.csv", units, UNIT_FIELDS)
    write_csv(output_dir / "admission_rules.csv", rules, RULE_FIELDS)
    write_csv(output_dir / "historical_outcomes.csv", outcomes, OUTCOME_FIELDS)

    summary = summarize(repo_root, foundation_dir, output_dir, universities, units, rules, outcomes)
    (output_dir / "foundation_p0_seed_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation p0 seed export complete. "
        f"universities={len(universities)} units={len(units)} "
        f"rules={len(rules)} historical_outcomes={len(outcomes)} "
        f"output={to_repo_relative(output_dir, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--clean", action="store_true", default=True)
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


def build_universities(foundation_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for index, row in enumerate(read_csv(foundation_dir / "foundation_universities.csv"), start=1):
        name = first(row, "universityNameCanonical", "universityName")
        if not name:
            continue
        rows.append(
            {
                "id": first(row, "universityCandidateId"),
                "name": name,
                "campus": first(row, "campus"),
                "region": first(row, "region") or "unknown",
                "type": first(row, "type"),
                "displayOrder": index,
            }
        )
    return rows


def build_units(foundation_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for row in read_csv(foundation_dir / "foundation_admission_units.csv"):
        unit_id = first(row, "unitCandidateId")
        university_id = first(row, "universityCandidateId")
        name = first(row, "admissionUnitCanonicalName", "admissionUnitName")
        year = int_or_none(first(row, "year"))
        if not unit_id or not university_id or not name or year is None:
            continue
        rows.append(
            {
                "id": unit_id,
                "universityId": university_id,
                "_unvCd": first(row, "unvCd"),
                "name": name,
                "recruitmentGroup": normalize_recruitment_group(first(row, "recruitmentGroup")),
                "majorGroup": first(row, "majorGroup"),
                "quota": first_numeric(first(row, "quotaCandidates")),
                "year": year,
                "active": "true",
            }
        )
    return rows


def build_outcomes(foundation_dir: Path, unit_ids: set[str]) -> list[dict[str, Any]]:
    rows = []
    seen_ids: set[str] = set()
    for row in read_csv(foundation_dir / "foundation_historical_outcomes.csv"):
        outcome_id = deterministic_uuid(
            "foundation-historical-outcome-seed:"
            + "|".join(
                [
                    first(row, "unitCandidateId"),
                    first(row, "year"),
                    first(row, "sourceCandidateSha256"),
                    first(row, "sectionId"),
                    first(row, "tableIndex"),
                    first(row, "rowIndex"),
                    first(row, "sourceUrl"),
                    first(row, "quota"),
                    first(row, "competitionRate"),
                    first(row, "convertedScore70Cut"),
                    first(row, "cutScoreCandidate"),
                    first(row, "avgScoreCandidate"),
                ]
            )
        )
        unit_id = first(row, "unitCandidateId")
        year = int_or_none(first(row, "year"))
        if not outcome_id or unit_id not in unit_ids or year is None:
            continue
        if year >= 2027:
            continue
        if not truthy(first(row, "hasOutcomeScore")) and not truthy(first(row, "hasQuotaAndCompetition")):
            continue
        if outcome_id in seen_ids:
            continue
        seen_ids.add(outcome_id)
        rows.append(
            {
                "id": outcome_id,
                "unitId": unit_id,
                "year": year,
                "avgScore": first_number(
                    first(row, "avgScoreCandidate"),
                    first(row, "convertedScore70Cut"),
                    first(row, "convertedScore50Cut"),
                ),
                "cutScore": first_number(
                    first(row, "cutScoreCandidate"),
                    first(row, "convertedScore70Cut"),
                    first(row, "convertedScore50Cut"),
                ),
                "percentileCut": first_number(
                    first(row, "percentileCutCandidate"),
                    first(row, "percentile70Average"),
                ),
                "competitionRate": first_number(first(row, "competitionRate")),
                "additionalPass": int_number(first(row, "additionalPass")),
                "sourceUrl": first(row, "sourceUrl") or "foundation://missing-source-url",
                "confidence": normalize_confidence(first(row, "confidence")),
            }
        )
    return rows


def build_rules(foundation_dir: Path, units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    draft_by_unv: dict[str, dict[str, str]] = {}
    for row in read_csv(foundation_dir / "foundation_csat_reflection_rule_drafts.csv"):
        if first(row, "admissionYear") != "2027":
            continue
        if first(row, "reviewStrength") not in {"high", "medium"}:
            continue
        unv_cd = first(row, "unvCd")
        if not unv_cd:
            continue
        current = draft_by_unv.get(unv_cd)
        current_score = int_or_none(first(current, "reviewPriorityScore")) if current else None
        row_score = int_or_none(first(row, "reviewPriorityScore")) or 0
        if current is None or row_score > (current_score or 0):
            draft_by_unv[unv_cd] = row

    rows = []
    for unit in units:
        if str(unit.get("year")) != "2027":
            continue
        unv_cd = str(unit.get("_unvCd") or "")
        draft = draft_by_unv.get(unv_cd)
        if draft is None:
            continue
        draft_id = first(draft, "csatRuleDraftId")
        formula_json = parsed_json(first(draft, "formulaJsonDraft")) or {}
        formula_json.update(
            {
                "source": "foundation_csat_reflection_rule_draft",
                "sourceRuleDraftId": draft_id,
                "appliesTo": "university_year_2027_all_units_pending_unit_level_review",
                "needsHumanVerification": True,
                "reviewStrength": first(draft, "reviewStrength"),
                "reviewPriorityScore": int_or_none(first(draft, "reviewPriorityScore")),
            }
        )
        rows.append(
            {
                "id": deterministic_uuid(f"foundation-admission-rule:{draft_id}:{unit['id']}"),
                "unitId": unit["id"],
                "year": 2027,
                "scoreType": normalize_score_type(first(draft, "scoreTypeCandidates")),
                "formulaJson": json.dumps(formula_json, ensure_ascii=False, sort_keys=True),
                "totalScale": "",
                "koreanWeight": "",
                "mathWeight": "",
                "inquiryWeight": "",
                "englishPolicyJson": valid_json_or_default(
                    first(draft, "englishPolicyJsonDraft"),
                    {"policyType": "english", "status": "review_candidate"},
                ),
                "historyPolicyJson": valid_json_or_default(
                    first(draft, "historyPolicyJsonDraft"),
                    {"policyType": "korean_history", "status": "review_candidate"},
                ),
                "inquiryPolicyJson": valid_json_or_default(
                    first(draft, "inquiryPolicyJsonDraft"),
                    {"policyType": "inquiry", "status": "review_candidate"},
                ),
                "eligibilityJson": json.dumps(
                    {
                        "status": "review_candidate",
                        "source": "foundation_csat_reflection_rule_draft",
                        "sourceRuleDraftId": draft_id,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "sourceUrl": first_split(first(draft, "sourceUrls")) or "foundation://missing-source-url",
                "verifiedStatus": "parsed",
            }
        )
    return rows


def summarize(
    repo_root: Path,
    foundation_dir: Path,
    output_dir: Path,
    universities: list[dict[str, Any]],
    units: list[dict[str, Any]],
    rules: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_p0_seed_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "foundationDir": to_repo_relative(foundation_dir, repo_root),
        },
        "outputs": {
            "outputDir": to_repo_relative(output_dir, repo_root),
            "universities": to_repo_relative(output_dir / "universities.csv", repo_root),
            "admissionUnits": to_repo_relative(output_dir / "admission_units.csv", repo_root),
            "admissionRules": to_repo_relative(output_dir / "admission_rules.csv", repo_root),
            "historicalOutcomes": to_repo_relative(output_dir / "historical_outcomes.csv", repo_root),
        },
        "rows": {
            "universities": len(universities),
            "admissionUnits": len(units),
            "admissionRules": len(rules),
            "historicalOutcomes": len(outcomes),
        },
        "unitRowsByYear": dict(sorted(Counter(str(row["year"]) for row in units).items())),
        "outcomeRowsByYear": dict(sorted(Counter(str(row["year"]) for row in outcomes).items())),
        "outcomeRowsByConfidence": dict(sorted(Counter(str(row["confidence"]) for row in outcomes).items())),
        "notes": [
            "This export maps foundation candidates into the current P0 seed CSV shape.",
            "Rows remain parsed/reference seed candidates, not human-verified live data.",
            "HistoricalOutcome rows exclude 2027 because those results remain wait_for_public_release.",
            "AdmissionRule rows are 2027 parsed CSAT rule drafts expanded to current unit-level seed shape with needsHumanVerification=true.",
        ],
    }


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: csv_value(row.get(field)) for field in fieldnames})


def csv_value(value: Any) -> Any:
    return "" if value is None else value


def first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = normalize_text(row.get(key))
        if value:
            return value
    return ""


def first_numeric(value: str) -> str:
    text = normalize_text(value)
    for part in re.split(r"[|,;/\s]+", text):
        number = first_number(part)
        if number != "":
            return str(int(float(number))) if float(number).is_integer() else str(number)
    return ""


def first_number(*values: str) -> str:
    for value in values:
        text = normalize_text(value)
        if not text:
            continue
        try:
            return str(float(text.replace(",", "")))
        except ValueError:
            match = re.search(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
            if match:
                return str(float(match.group(0)))
    return ""


def int_number(value: str) -> str:
    number = first_number(value)
    if number == "":
        return ""
    return str(int(float(number)))


def int_or_none(value: str) -> int | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def normalize_recruitment_group(value: str) -> str:
    text = normalize_text(value).lower()
    return text if text in {"ga", "na", "da", "none"} else "none"


def normalize_confidence(value: str) -> str:
    text = normalize_text(value).lower()
    return text if text in {"high", "medium", "low", "limited"} else "limited"


def normalize_score_type(value: str) -> str:
    text = normalize_text(value).lower()
    if "mixed" in text:
        return "mixed"
    if "standard" in text or "표준" in text:
        return "standard"
    if "percentile" in text or "백분위" in text:
        return "percentile"
    return "custom"


def parsed_json(value: str) -> dict[str, Any] | None:
    text = normalize_text(value)
    if not text:
        return None
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def valid_json_or_default(value: str, default: dict[str, Any]) -> str:
    parsed = parsed_json(value)
    return json.dumps(parsed if parsed is not None else default, ensure_ascii=False, sort_keys=True)


def first_split(value: str) -> str:
    return next((part for part in normalize_text(value).split("|") if part), "")


def deterministic_uuid(seed: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def truthy(value: Any) -> bool:
    return normalize_text(value).lower() in {"1", "true", "t", "yes", "y"}


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
