import type {
  ScoreInput,
  SimulationAdjustment,
  SubjectScoreValue,
} from "../domain/entities";
import { GRADE_PERCENTILE_FLOORS, SCORE_RANGE, round2 } from "./constants";

/**
 * 11. 점수 시뮬레이션 — 가상 점수 적용 (§7.9, P1).
 *
 * 순수·결정적 함수: 원본 성적에 조정(delta/override)을 적용한 새 ScoreInput을
 * 반환한다. 원본은 변경하지 않는다. 결과는 저장되지 않는 일회성 계산의 입력일 뿐이며
 * "성적 상승 가능성 예측"이 아니다(§7.9 주의 문구 = shared.SIMULATION_NOTICE).
 *
 * 규칙:
 * - delta와 override가 함께 오면 override를 먼저 적용한 뒤 delta를 더한다.
 * - 값은 §18.1 검증 범위로 클램프한다(표준 0–200, 백분위 0–100, 등급 1–9).
 * - 백분위가 바뀐 상대평가 과목은 등급을 9등급제 누적 백분위로 재산출한다
 *   (등급·백분위 불일치로 인한 검증 경고 방지 — 결정적).
 * - 시뮬레이션에 없는 과목은 그대로 둔다.
 */
export function applyAdjustments(
  base: ScoreInput,
  adjustments: readonly SimulationAdjustment[],
): ScoreInput {
  const bySubject = new Map<string, SimulationAdjustment>();
  for (const adj of adjustments) bySubject.set(adj.subject, adj);

  return {
    ...base,
    scores: base.scores.map((s) => {
      const adj = bySubject.get(s.subject);
      return adj ? adjustSubject(s, adj) : { ...s };
    }),
  };
}

/** 백분위 → 상대평가 9등급 (GRADE_PERCENTILE_FLOORS 기준, 결정적) */
export function percentileToGrade(percentile: number): number {
  for (let i = 0; i < GRADE_PERCENTILE_FLOORS.length; i++) {
    const floor = GRADE_PERCENTILE_FLOORS[i];
    if (floor !== undefined && percentile >= floor) return i + 1;
  }
  return 9;
}

function adjustSubject(
  s: SubjectScoreValue,
  adj: SimulationAdjustment,
): SubjectScoreValue {
  const next: SubjectScoreValue = { ...s };

  // 1) override(직접 점수 입력) 먼저
  if (adj.override?.standardScore !== undefined) {
    next.standardScore = adj.override.standardScore;
  }
  if (adj.override?.percentile !== undefined) {
    next.percentile = adj.override.percentile;
  }
  if (adj.override?.grade !== undefined) {
    next.grade = adj.override.grade;
  }

  // 2) delta 적용 (해당 값이 있는 경우에만 — 없는 지표를 만들어내지 않는다)
  let percentileChanged = adj.override?.percentile !== undefined;
  if (adj.standardScoreDelta !== undefined && next.standardScore !== undefined) {
    next.standardScore = clamp(
      round2(next.standardScore + adj.standardScoreDelta),
      SCORE_RANGE.standardScore.min,
      SCORE_RANGE.standardScore.max,
    );
  }
  if (adj.percentileDelta !== undefined && next.percentile !== undefined) {
    next.percentile = clamp(
      round2(next.percentile + adj.percentileDelta),
      SCORE_RANGE.percentile.min,
      SCORE_RANGE.percentile.max,
    );
    percentileChanged = true;
  }
  if (adj.gradeDelta !== undefined && next.grade !== undefined) {
    next.grade = clamp(
      Math.round(next.grade + adj.gradeDelta),
      SCORE_RANGE.grade.min,
      SCORE_RANGE.grade.max,
    );
  }

  // 3) 백분위가 바뀐 상대평가 과목(등급 보유)은 등급 일관성 재산출.
  //    단, 등급을 직접 지정/조정한 경우는 사용자의 의도를 우선한다.
  const gradeExplicit =
    adj.override?.grade !== undefined || adj.gradeDelta !== undefined;
  if (percentileChanged && !gradeExplicit && next.grade !== undefined) {
    next.grade = percentileToGrade(next.percentile ?? 0);
  }

  // 클램프(override 입력 방어)
  if (next.standardScore !== undefined) {
    next.standardScore = clamp(
      next.standardScore,
      SCORE_RANGE.standardScore.min,
      SCORE_RANGE.standardScore.max,
    );
  }
  if (next.percentile !== undefined) {
    next.percentile = clamp(
      next.percentile,
      SCORE_RANGE.percentile.min,
      SCORE_RANGE.percentile.max,
    );
  }
  if (next.grade !== undefined) {
    next.grade = clamp(next.grade, SCORE_RANGE.grade.min, SCORE_RANGE.grade.max);
  }

  return next;
}

function clamp(n: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, n));
}
