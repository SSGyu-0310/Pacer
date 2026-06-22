import type { Band, ExamType, Subject } from "@pacer/shared";
import type {
  AdmissionUnitRef,
  BandTransitionKind,
  ExamScore,
  SubjectScoreValue,
  SubjectTrendEntry,
  TargetApproach,
  TrendAnalysis,
  TrendDirection,
  TrendMetric,
  UnitAnalysis,
  UnitBandTransition,
} from "../domain/entities";
import { round2 } from "./constants";

/** 유리한 순(안정 → 위험). 접근도·전이 판정의 단일 기준. */
export const BAND_FAVORABLE: readonly Band[] = [
  "stable",
  "match",
  "reach",
  "challenge",
  "risk",
];

/** 구간 유불리 인덱스(0 = 가장 유리). */
export function bandFavorability(band: Band): number {
  return BAND_FAVORABLE.indexOf(band);
}

/**
 * 목표 대학 결과 중 가장 유리한 구간 (§6.4 목표 접근도).
 * 목표 대학 결과가 없으면 전체 결과 기준, 그것도 없으면 "limited".
 */
export function mostFavorableBand(
  results: readonly UnitAnalysis[],
  targetUniversities: readonly string[],
): TargetApproach {
  const pool = targetUniversities.length
    ? results.filter((r) => targetUniversities.includes(r.unit.university))
    : results;
  const source = pool.length ? pool : results;
  for (const band of BAND_FAVORABLE) {
    if (source.some((r) => r.band === band)) return band;
  }
  return "limited";
}

/** analyzeTrend 입력 — 한 시험의 성적 + 그 시험의 분석 결과 스냅샷 */
export interface TrendInput {
  examScore: ExamScore;
  results: readonly UnitAnalysis[];
}

/**
 * 9. 시험 간 변화 분석 (§7.7.2, P1) — 6모↔9모 점수/구간/접근도 변화.
 *
 * 순수·결정적 함수. 과목 비교 지표는 두 시험이 공통으로 가진 것 중
 * 백분위 > 표준점수 > 등급 우선(상대 위치 비교가 목적 — §2.2 누적 타임라인).
 * 등급은 낮을수록 좋으므로 direction 판정이 반대다.
 */
export function analyzeTrend(
  prev: TrendInput,
  curr: TrendInput,
  targetUniversities: readonly string[] = [],
): TrendAnalysis {
  const subjects = compareSubjects(prev.examScore, curr.examScore);
  const transitions = compareBands(prev.results, curr.results);

  const enteredUnits = transitions
    .filter((t) => t.kind === "entered")
    .map((t) => t.unit);
  const droppedUnits = transitions
    .filter((t) => t.kind === "dropped")
    .map((t) => t.unit);

  const prevApproach = mostFavorableBand(prev.results, targetUniversities);
  const currApproach = mostFavorableBand(curr.results, targetUniversities);

  return {
    prevExamType: prev.examScore.examType,
    currExamType: curr.examScore.examType,
    subjects,
    improvedSubjects: subjects
      .filter((s) => s.direction === "improved")
      .map((s) => s.subject),
    declinedSubjects: subjects
      .filter((s) => s.direction === "declined")
      .map((s) => s.subject),
    transitions,
    enteredUnits,
    droppedUnits,
    bandImprovedCount: transitions.filter((t) => t.kind === "improved").length,
    bandDeclinedCount: transitions.filter((t) => t.kind === "declined").length,
    prevBandDistribution: distribution(prev.results),
    currBandDistribution: distribution(curr.results),
    targetApproach: {
      prev: prevApproach,
      curr: currApproach,
      direction: approachDirection(prevApproach, currApproach),
    },
  };
}

/** 과목별 변화 — 과목 enum 순서대로(결정성) */
function compareSubjects(prev: ExamScore, curr: ExamScore): SubjectTrendEntry[] {
  const prevBySubject = new Map(prev.scores.map((s) => [s.subject, s]));
  const entries: SubjectTrendEntry[] = [];

  for (const score of curr.scores) {
    const before = prevBySubject.get(score.subject);
    if (!before) continue;
    const picked = pickMetric(before, score);
    if (!picked) continue;

    const { metric, prevValue, currValue } = picked;
    const delta = round2(currValue - prevValue);
    entries.push({
      subject: score.subject,
      metric,
      prev: prevValue,
      curr: currValue,
      delta,
      direction: subjectDirection(metric, delta),
    });
  }
  return entries;
}

function pickMetric(
  a: SubjectScoreValue,
  b: SubjectScoreValue,
): { metric: TrendMetric; prevValue: number; currValue: number } | null {
  if (a.percentile !== undefined && b.percentile !== undefined) {
    return { metric: "percentile", prevValue: a.percentile, currValue: b.percentile };
  }
  if (a.standardScore !== undefined && b.standardScore !== undefined) {
    return {
      metric: "standard_score",
      prevValue: a.standardScore,
      currValue: b.standardScore,
    };
  }
  if (a.grade !== undefined && b.grade !== undefined) {
    return { metric: "grade", prevValue: a.grade, currValue: b.grade };
  }
  return null;
}

function subjectDirection(metric: TrendMetric, delta: number): TrendDirection {
  if (delta === 0) return "unchanged";
  // 등급은 낮을수록 좋다
  const improved = metric === "grade" ? delta < 0 : delta > 0;
  return improved ? "improved" : "declined";
}

/** 모집단위별 구간 전이 — unitId 기준 매칭, unitId 사전순(결정성) */
function compareBands(
  prev: readonly UnitAnalysis[],
  curr: readonly UnitAnalysis[],
): UnitBandTransition[] {
  const prevById = new Map(prev.map((r) => [r.unit.unitId, r]));
  const currById = new Map(curr.map((r) => [r.unit.unitId, r]));
  const ids = [...new Set([...prevById.keys(), ...currById.keys()])].sort();

  return ids.map((id) => {
    const before = prevById.get(id) ?? null;
    const after = currById.get(id) ?? null;
    const unit: AdmissionUnitRef = (after ?? before)!.unit;
    return {
      unit,
      prevBand: before?.band ?? null,
      currBand: after?.band ?? null,
      kind: transitionKind(before?.band ?? null, after?.band ?? null),
    };
  });
}

function transitionKind(prev: Band | null, curr: Band | null): BandTransitionKind {
  if (prev === null && curr !== null) return "entered";
  if (prev !== null && curr === null) return "dropped";
  if (prev === null || curr === null) return "unchanged"; // 도달 불가(둘 다 null이면 항목 자체가 없다)
  const diff = bandFavorability(curr) - bandFavorability(prev);
  if (diff < 0) return "improved";
  if (diff > 0) return "declined";
  return "unchanged";
}

function approachDirection(
  prev: TargetApproach,
  curr: TargetApproach,
): TrendDirection {
  const rank = (a: TargetApproach): number =>
    a === "limited" ? BAND_FAVORABLE.length : bandFavorability(a);
  const diff = rank(curr) - rank(prev);
  if (diff < 0) return "improved";
  if (diff > 0) return "declined";
  return "unchanged";
}

function distribution(results: readonly UnitAnalysis[]): Record<Band, number> {
  const d: Record<Band, number> = {
    stable: 0,
    match: 0,
    reach: 0,
    challenge: 0,
    risk: 0,
  };
  for (const r of results) d[r.band]++;
  return d;
}
