import type {
  ScoreInput,
  SubjectScoreValue,
  ValidationResult,
} from "../domain/entities";
import { SCORE_RANGE } from "./constants";

/**
 * 1. 성적 검증 (§8.1, §18.1).
 * - 범위: 표준점수 0–200, 백분위 0–100, 등급 1–9, 원점수 0–100
 * - 영어·한국사(절대평가)는 등급 필수
 * - 국어·수학·탐구는 표준점수 또는 백분위 중 하나 필수
 * - 필수 과목(국어·수학·영어·한국사) 누락 → 오류
 * - 수학/탐구 선택과목 누락, 탐구 미입력 → 경고(저장은 허용)
 *
 * 순수·결정적 함수: 같은 입력 = 같은 출력.
 */
export function validateScores(input: ScoreInput): ValidationResult {
  const errors: string[] = [];
  const warnings: string[] = [];

  // 중복 과목
  const seen = new Set<string>();
  for (const s of input.scores) {
    if (seen.has(s.subject)) errors.push(`중복 입력된 과목: ${s.subject}`);
    seen.add(s.subject);
  }

  // 범위 검증
  for (const s of input.scores) {
    checkRange(s, "standardScore", errors);
    checkRange(s, "percentile", errors);
    checkRange(s, "grade", errors);
    checkRange(s, "rawScore", errors);
  }

  const by = new Map(input.scores.map((s) => [s.subject, s]));

  // 필수 과목
  for (const subject of ["korean", "math", "english", "history"] as const) {
    if (!by.has(subject)) errors.push(`필수 과목 누락: ${subject}`);
  }

  // 절대평가 과목은 등급 필수
  for (const subject of ["english", "history"] as const) {
    const s = by.get(subject);
    if (s && s.grade === undefined) errors.push(`등급 누락: ${subject}`);
  }

  // 상대평가 과목은 표준점수 또는 백분위 필수
  for (const subject of ["korean", "math", "inquiry1", "inquiry2"] as const) {
    const s = by.get(subject);
    if (s && s.standardScore === undefined && s.percentile === undefined) {
      errors.push(`표준점수 또는 백분위 필요: ${subject}`);
    }
  }

  // 경고: 선택과목·탐구
  const math = by.get("math");
  if (math && !math.selection) warnings.push("수학 선택과목 미입력");
  for (const subject of ["inquiry1", "inquiry2"] as const) {
    const s = by.get(subject);
    if (s && !s.selection) warnings.push(`탐구 선택과목 미입력: ${subject}`);
  }
  if (!by.has("inquiry1") && !by.has("inquiry2")) {
    warnings.push("탐구 성적 미입력 — 탐구 반영 대학 분석이 제한됩니다");
  }

  return { valid: errors.length === 0, errors, warnings };
}

function checkRange(
  s: SubjectScoreValue,
  field: keyof typeof SCORE_RANGE,
  errors: string[],
): void {
  const value = s[field];
  if (value === undefined) return;
  const { min, max } = SCORE_RANGE[field];
  if (value < min || value > max) {
    errors.push(`${fieldLabel(field)} 범위 오류(${min}–${max}): ${s.subject}`);
  }
}

function fieldLabel(field: keyof typeof SCORE_RANGE): string {
  switch (field) {
    case "standardScore":
      return "표준점수";
    case "percentile":
      return "백분위";
    case "grade":
      return "등급";
    case "rawScore":
      return "원점수";
  }
}
