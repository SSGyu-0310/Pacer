#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterable


DEFAULT_FOUNDATION_DIR = "packages/reference-data/data/public/foundation"
DEFAULT_P0_SEED_DIR = "packages/reference-data/data/p0-foundation"
DEFAULT_REVIEW_DIR = "packages/reference-data/data/review"

RULE_FIELDS = [
    "ruleId",
    "unvCd",
    "universityName",
    "sourceUrl",
    "attachmentUrl",
    "textPreview",
    "detectedSignals",
    "percentageValues",
    "weightValues",
    "formulaSignals",
    "reviewPriorityScore",
    "reviewStrength",
    "rawPath",
    "sourcePath",
]

OUTCOME_FIELDS = [
    "outcomeId",
    "sourceUrl",
    "rawPath",
    "rowText",
    "metricValuesJson",
]


try:
    csv.field_size_limit(sys.maxsize)
except OverflowError:
    csv.field_size_limit(2**31 - 1)


def main() -> None:
    args = parse_args()
    repo_root = find_repo_root(Path.cwd())
    foundation_dir = resolve(repo_root, args.foundation_dir)
    p0_seed_dir = resolve(repo_root, args.p0_seed_dir)
    review_dir = resolve(repo_root, args.review_dir)
    review_dir.mkdir(parents=True, exist_ok=True)

    core_unv_cds = load_core_unv_cds(review_dir / "core-universities.json")
    rules = build_rule_evidence(foundation_dir, p0_seed_dir, core_unv_cds)
    outcomes = build_outcome_evidence(foundation_dir, p0_seed_dir, core_unv_cds)

    write_csv(p0_seed_dir / "rule_evidence.csv", rules, RULE_FIELDS)
    write_csv(p0_seed_dir / "outcome_evidence.csv", outcomes, OUTCOME_FIELDS)

    summary = {
        "foundationDir": to_repo_relative(foundation_dir, repo_root),
        "p0SeedDir": to_repo_relative(p0_seed_dir, repo_root),
        "coreUniversityFilterCount": len(core_unv_cds),
        "ruleEvidenceRows": len(rules),
        "outcomeEvidenceRows": len(outcomes),
    }
    (p0_seed_dir / "foundation_review_evidence_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        "foundation review evidence complete. "
        f"rules={len(rules)} outcomes={len(outcomes)} output={to_repo_relative(p0_seed_dir, repo_root)}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foundation-dir", default=DEFAULT_FOUNDATION_DIR)
    parser.add_argument("--p0-seed-dir", default=DEFAULT_P0_SEED_DIR)
    parser.add_argument("--review-dir", default=DEFAULT_REVIEW_DIR)
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


def load_core_unv_cds(path: Path) -> set[str]:
    if not path.exists():
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get("unvCds", []) if isinstance(payload, dict) else payload
    return {str(value).zfill(7) for value in values if str(value).strip()}


def build_rule_evidence(
    foundation_dir: Path,
    p0_seed_dir: Path,
    core_unv_cds: set[str],
) -> list[dict[str, Any]]:
    candidates_by_evidence_id = {
        first(row, "sourceEvidenceId"): row
        for row in read_csv(foundation_dir / "foundation_admission_rule_review_candidates.csv")
        if first(row, "sourceEvidenceId")
    }
    queue_by_source_record = {
        first(row, "sourceRecordId"): row
        for row in read_csv(foundation_dir / "foundation_promotion_queue.csv")
        if first(row, "sourceArtifact") == "foundation_csat_reflection_rule_drafts"
        and first(row, "sourceRecordId")
    }

    output: list[dict[str, Any]] = []
    for rule in read_csv(p0_seed_dir / "admission_rules.csv"):
        if first(rule, "year") != "2027":
            continue
        formula = parse_json(first(rule, "formulaJson"))
        if not isinstance(formula, dict):
            continue
        source_rule_draft_id = str(formula.get("sourceRuleDraftId") or "")
        evidence_ids = [str(v) for v in formula.get("sourceEvidenceIds") or []]
        candidate = next(
            (candidates_by_evidence_id[eid] for eid in evidence_ids if eid in candidates_by_evidence_id),
            {},
        )
        queue = queue_by_source_record.get(source_rule_draft_id, {})
        unv_cd = first(candidate, "unvCd") or first(queue, "unvCd")
        if core_unv_cds and unv_cd not in core_unv_cds:
            continue

        output.append(
            {
                "ruleId": first(rule, "id"),
                "unvCd": unv_cd,
                "universityName": first(candidate, "universityName") or first(queue, "universityName"),
                "sourceUrl": first(candidate, "sourceUrl") or first(rule, "sourceUrl"),
                "attachmentUrl": first(candidate, "attachmentUrl") or first_pipe(queue, "attachmentUrls"),
                "textPreview": first(candidate, "textPreview") or first(queue, "evidenceSummary"),
                "detectedSignals": json_array(first(candidate, "detectedSignals")),
                "percentageValues": json_array(first(candidate, "percentageValues")),
                "weightValues": json_array(first(candidate, "weightValues")),
                "formulaSignals": json_array(first(candidate, "formulaSignals")),
                "reviewPriorityScore": first(candidate, "reviewPriorityScore")
                or first(queue, "reviewPriorityScore")
                or formula.get("reviewPriorityScore")
                or "",
                "reviewStrength": first(queue, "reviewStrength") or formula.get("reviewStrength") or "",
                "rawPath": first(candidate, "rawPath") or first_pipe(queue, "rawPaths"),
                "sourcePath": first(candidate, "sourcePath") or first_pipe(queue, "sourcePaths"),
            }
        )
    return output


def build_outcome_evidence(
    foundation_dir: Path,
    p0_seed_dir: Path,
    core_unv_cds: set[str],
) -> list[dict[str, Any]]:
    foundation_outcomes = list(read_csv(foundation_dir / "foundation_historical_outcomes.csv"))
    by_seed_id = {historical_outcome_seed_id(row): row for row in foundation_outcomes}
    output = []
    for outcome in read_csv(p0_seed_dir / "historical_outcomes.csv"):
        source = by_seed_id.get(first(outcome, "id"), {})
        if core_unv_cds and first(source, "unvCd") not in core_unv_cds:
            continue
        metric_values = {
            key: first(source, key)
            for key in [
                "quota",
                "competitionRate",
                "additionalPass",
                "convertedScore50Cut",
                "convertedScore70Cut",
                "avgScoreCandidate",
                "cutScoreCandidate",
                "percentileCutCandidate",
            ]
            if first(source, key)
        }
        output.append(
            {
                "outcomeId": first(outcome, "id"),
                "sourceUrl": first(source, "sourceUrl") or first(outcome, "sourceUrl"),
                "rawPath": first(source, "rawPath"),
                "rowText": " / ".join(
                    part
                    for part in [
                        first(source, "universityName"),
                        first(source, "admissionUnitName"),
                        f"year={first(source, 'year')}" if first(source, "year") else "",
                        json.dumps(metric_values, ensure_ascii=False) if metric_values else "",
                    ]
                    if part
                ),
                "metricValuesJson": json.dumps(metric_values, ensure_ascii=False) if metric_values else "",
            }
        )
    return output


def historical_outcome_seed_id(row: dict[str, str]) -> str:
    import uuid

    seed = "foundation-historical-outcome-seed:" + "|".join(
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
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def read_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def parse_json(value: str) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def json_array(value: str) -> str:
    if not value:
        return ""
    if value.lstrip().startswith("["):
        return value
    return json.dumps([part for part in value.split("|") if part], ensure_ascii=False)


def first(row: dict[str, Any], key: str) -> str:
    value = row.get(key, "") if row else ""
    return "" if value is None else str(value).strip()


def first_pipe(row: dict[str, Any], key: str) -> str:
    value = first(row, key)
    return value.split("|", 1)[0] if value else ""


def to_repo_relative(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    main()
