import type { Band, Confidence, ExamType, ReasonCode } from "@pacer/shared";
import type {
  AdmissionRuleData,
  ConvertedScore,
  EligibilityResult,
  NormalizedScores,
} from "../domain/entities";
import { ENGLISH_RATIO_DEFAULT_MAX, REASON_THRESHOLDS } from "./constants";

/**
 * 영어 영향 강도 — 1등급과 3등급의 환산점수 차이를 만점 100 기준으로 환산.
 * 구간 보정(§8.3)과 reason code 판정(§8.5)에 공용.
 * - deduction/addition: byGrade가 환산 만점 단위 점수 → totalScale로 정규화.
 * - ratio: 영어가 가중평균의 한 과목 → 등급별 환산점수차에 반영비중(weight/weightSum)을 곱한다.
 */
export function englishPenaltySpreadPer100(rule: AdmissionRuleData): number {
  const policy = rule.englishPolicy;
  const at = (grade: number) => policy.byGrade[grade] ?? 0;

  if (policy.mode === "ratio") {
    const w = policy.weight ?? 0;
    const scoreMax = policy.scoreMax ?? ENGLISH_RATIO_DEFAULT_MAX;
    const weightSum =
      rule.weights.korean + rule.weights.math + rule.weights.inquiry + w;
    if (weightSum <= 0 || scoreMax <= 0) return 0;
    return (w / weightSum) * (Math.abs(at(1) - at(3)) / scoreMax) * 100;
  }

  return (Math.abs(at(1) - at(3)) / rule.totalScale) * 100;
}

/**
 * 8. reason code 생성 (§8.5) — 강점/추천 → reasonCodes, 약점 → warnings.
 * 컨트롤드 보캐블러리(@pacer/shared)만 사용한다. 임의 문자열 금지.
 * 순수·결정적 — 같은 입력이면 같은 코드가 같은 순서로 나온다.
 */
export function generateReasonCodes(args: {
  examType: ExamType;
  normalized: NormalizedScores;
  rule: AdmissionRuleData;
  converted: ConvertedScore;
  band: Band;
  confidence: Confidence;
  eligibility: EligibilityResult;
  /** §8.3 보정 요소 중 코드화 대상 */
  smallQuota?: boolean;
  highVolatility?: boolean;
}): { reasonCodes: ReasonCode[]; warnings: ReasonCode[] } {
  const {
    examType,
    normalized,
    rule,
    band,
    confidence,
    eligibility,
    smallQuota,
    highVolatility,
  } = args;

  const reasonCodes: ReasonCode[] = [];
  const warnings: ReasonCode[] = [];
  const add = (list: ReasonCode[], code: ReasonCode) => {
    if (!list.includes(code)) list.push(code);
  };

  const strengths = new Set(normalized.strengthSubjects);
  const weaknesses = new Set(normalized.weaknessSubjects);
  const englishGrade = normalized.bySubject.get("english")?.grade;
  const spreadPer100 = englishPenaltySpreadPer100(rule);

  // --- 강점 (§8.5) ---
  if (
    strengths.has("math") &&
    rule.weights.math >= REASON_THRESHOLDS.weightAdvantageMin
  ) {
    add(reasonCodes, "math_weight_advantage");
  }
  if (
    strengths.has("korean") &&
    rule.weights.korean >= REASON_THRESHOLDS.weightAdvantageMin
  ) {
    add(reasonCodes, "korean_weight_advantage");
  }
  if (
    englishGrade !== undefined &&
    englishGrade >= 2 &&
    spreadPer100 <= REASON_THRESHOLDS.englishLowSpreadPer100
  ) {
    // 영어 등급이 아쉬운 사용자에게 감점이 약한 대학은 상대적으로 유리
    add(reasonCodes, "english_low_penalty_advantage");
  }
  const inq1 = normalized.bySubject.get("inquiry1")?.percentile;
  const inq2 = normalized.bySubject.get("inquiry2")?.percentile;
  if (
    inq1 !== undefined &&
    inq2 !== undefined &&
    Math.min(inq1, inq2) >= REASON_THRESHOLDS.inquiryStableMinPercentile &&
    Math.abs(inq1 - inq2) <= REASON_THRESHOLDS.inquiryStableMaxDiff
  ) {
    add(reasonCodes, "science_stable");
  }
  if (band === "stable" || band === "match") {
    if (rule.scoreType === "percentile") add(reasonCodes, "percentile_fit");
    else if (rule.scoreType === "standard")
      add(reasonCodes, "standard_score_fit");
  }

  // --- 약점 → warnings (§8.5) ---
  if (
    englishGrade !== undefined &&
    englishGrade >= REASON_THRESHOLDS.englishRiskMinGrade &&
    spreadPer100 >= REASON_THRESHOLDS.englishRiskSpreadPer100
  ) {
    add(warnings, "english_penalty_risk");
  }
  if (rule.inquiryPolicy.conversionRisk) {
    add(warnings, "science_conversion_risk");
  }
  if (eligibility.failures.some((f) => f.code === "math_selection")) {
    add(warnings, "math_requirement_fail");
  }
  if (confidence === "low" || confidence === "limited") {
    add(warnings, "low_data_confidence");
  }
  if (smallQuota) add(warnings, "small_quota_risk");
  if (highVolatility) add(warnings, "high_volatility");

  // --- 추천 (§8.5) — 강·약점에서 파생 ---
  if (reasonCodes.includes("math_weight_advantage")) {
    add(reasonCodes, "explore_math_heavy");
  }
  if (warnings.includes("english_penalty_risk")) {
    add(reasonCodes, "avoid_english_penalty");
  }
  if (weaknesses.has("math")) add(reasonCodes, "simulate_math_up");
  if (weaknesses.has("inquiry1") || weaknesses.has("inquiry2")) {
    add(reasonCodes, "simulate_explore_up");
  }
  if (examType === "csat") add(reasonCodes, "compare_after_jinhak");
  if (band === "reach" || band === "challenge") {
    add(reasonCodes, "build_application_plan");
  }

  return { reasonCodes, warnings };
}
