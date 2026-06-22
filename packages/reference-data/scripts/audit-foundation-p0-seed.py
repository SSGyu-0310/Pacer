#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SEED_DIR = "packages/reference-data/data/p0-foundation"
DEFAULT_SUMMARY = "foundation_p0_seed_audit_summary.json"


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    seed_dir = resolve(repo_root, args.seed_dir)

    universities = read_csv(seed_dir / "universities.csv")
    units = read_csv(seed_dir / "admission_units.csv")
    rules = read_csv(seed_dir / "admission_rules.csv")
    outcomes = read_csv(seed_dir / "historical_outcomes.csv")

    errors: list[str] = []
    warnings: list[str] = []

    university_ids = collect_unique_ids(universities, "universities", errors)
    unit_ids = collect_unique_ids(units, "admission_units", errors)
    collect_unique_ids(rules, "admission_rules", errors)
    collect_unique_ids(outcomes, "historical_outcomes", errors)

    missing_unit_universities = count_missing_refs(units, "universityId", university_ids)
    missing_rule_units = count_missing_refs(rules, "unitId", unit_ids)
    missing_outcome_units = count_missing_refs(outcomes, "unitId", unit_ids)
    if missing_unit_universities:
        errors.append(f"admission_units has {missing_unit_universities} missing universityId refs")
    if missing_rule_units:
        errors.append(f"admission_rules has {missing_rule_units} missing unitId refs")
    if missing_outcome_units:
        errors.append(f"historical_outcomes has {missing_outcome_units} missing unitId refs")

    future_outcomes = [row for row in outcomes if int_or_none(row.get("year")) and int(row["year"]) >= 2027]
    if future_outcomes:
        errors.append(f"historical_outcomes contains {len(future_outcomes)} 2027+ rows")

    non_2027_rules = [row for row in rules if row.get("year") != "2027"]
    if non_2027_rules:
        errors.append(f"admission_rules contains {len(non_2027_rules)} non-2027 rows")

    non_parsed_rules = [row for row in rules if row.get("verifiedStatus") != "parsed"]
    if non_parsed_rules:
        errors.append(f"admission_rules contains {len(non_parsed_rules)} rows not marked parsed")

    rules_without_review_flag = 0
    invalid_json_fields = Counter()
    for row in rules:
        formula = parse_json(row.get("formulaJson"), "admission_rules.formulaJson", invalid_json_fields)
        if not isinstance(formula, dict) or formula.get("needsHumanVerification") is not True:
            rules_without_review_flag += 1
        for field in ["englishPolicyJson", "historyPolicyJson", "inquiryPolicyJson", "eligibilityJson"]:
            parse_json(row.get(field), f"admission_rules.{field}", invalid_json_fields)
    if rules_without_review_flag:
        errors.append(f"admission_rules contains {rules_without_review_flag} rows without needsHumanVerification=true")
    if invalid_json_fields:
        errors.append(f"invalid JSON fields: {dict(invalid_json_fields)}")

    empty_rule_sources = sum(1 for row in rules if not row.get("sourceUrl"))
    empty_outcome_sources = sum(1 for row in outcomes if not row.get("sourceUrl"))
    if empty_rule_sources:
        errors.append(f"admission_rules contains {empty_rule_sources} empty sourceUrl rows")
    if empty_outcome_sources:
        errors.append(f"historical_outcomes contains {empty_outcome_sources} empty sourceUrl rows")

    unit_years = Counter(row.get("year") for row in units)
    rule_years = Counter(row.get("year") for row in rules)
    outcome_years = Counter(row.get("year") for row in outcomes)
    outcome_confidence = Counter(row.get("confidence") for row in outcomes)
    rule_status = Counter(row.get("verifiedStatus") for row in rules)

    if int(unit_years.get("2027", 0)) != len(rules):
        warnings.append(
            "2027 admission unit count and parsed rule count differ: "
            f"units2027={unit_years.get('2027', 0)} rules={len(rules)}"
        )

    summary = {
        "provider": "pacer-reference-data",
        "artifactType": "foundation_p0_seed_audit_summary",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "seedDir": to_repo_relative(seed_dir, repo_root),
        "status": "ok" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "rows": {
            "universities": len(universities),
            "admissionUnits": len(units),
            "admissionRules": len(rules),
            "historicalOutcomes": len(outcomes),
        },
        "unitRowsByYear": dict(sorted(unit_years.items())),
        "ruleRowsByYear": dict(sorted(rule_years.items())),
        "ruleRowsByVerifiedStatus": dict(sorted(rule_status.items())),
        "outcomeRowsByYear": dict(sorted(outcome_years.items())),
        "outcomeRowsByConfidence": dict(sorted(outcome_confidence.items())),
        "invariants": {
            "unitUniversityRefsMissing": missing_unit_universities,
            "ruleUnitRefsMissing": missing_rule_units,
            "outcomeUnitRefsMissing": missing_outcome_units,
            "historicalOutcome2027PlusRows": len(future_outcomes),
            "admissionRuleNon2027Rows": len(non_2027_rules),
            "admissionRuleNonParsedRows": len(non_parsed_rules),
            "admissionRuleWithoutNeedsHumanVerification": rules_without_review_flag,
            "admissionRuleEmptySourceUrls": empty_rule_sources,
            "historicalOutcomeEmptySourceUrls": empty_outcome_sources,
        },
    }

    output_path = seed_dir / args.output_summary
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "foundation p0 seed audit complete. "
        f"status={summary['status']} universities={len(universities)} units={len(units)} "
        f"rules={len(rules)} historical_outcomes={len(outcomes)}"
    )
    if errors:
        raise SystemExit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-dir", default=DEFAULT_SEED_DIR)
    parser.add_argument("--output-summary", default=DEFAULT_SUMMARY)
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
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def collect_unique_ids(rows: list[dict[str, str]], label: str, errors: list[str]) -> set[str]:
    values = [row.get("id", "") for row in rows]
    empty = sum(1 for value in values if not value)
    if empty:
        errors.append(f"{label} has {empty} empty id rows")
    counts = Counter(value for value in values if value)
    duplicate_count = sum(count - 1 for count in counts.values() if count > 1)
    if duplicate_count:
        errors.append(f"{label} has {duplicate_count} duplicate ids")
    return set(counts)


def count_missing_refs(rows: list[dict[str, str]], field: str, valid_ids: set[str]) -> int:
    return sum(1 for row in rows if row.get(field) not in valid_ids)


def parse_json(value: Any, field: str, invalid_fields: Counter[str]) -> Any:
    try:
        return json.loads(str(value or ""))
    except json.JSONDecodeError:
        invalid_fields[field] += 1
        return None


def int_or_none(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
