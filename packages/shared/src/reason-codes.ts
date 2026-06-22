/**
 * Reason Code 컨트롤드 보캐블러리 (§8.5).
 *
 * AI 리포트는 reason code 기반으로만 작성된다. 새 코드가 필요하면 이 테이블을 확장한다.
 * 임의 문자열 금지.
 */
import { z } from "zod";

/** 강점 코드 (§8.5) */
export const strengthCode = z.enum([
  "math_weight_advantage", // 수학 반영비 대학에서 유리
  "korean_weight_advantage", // 국어 반영비 대학에서 유리
  "english_low_penalty_advantage", // 영어 감점이 낮은 대학에서 유리
  "science_stable", // 탐구가 안정적
  "percentile_fit", // 백분위 반영 대학에 적합
  "standard_score_fit", // 표준점수 반영 대학에 적합
  "target_improved", // 목표 대학 접근도 상승
]);
export type StrengthCode = z.infer<typeof strengthCode>;

/** 약점 코드 (§8.5) */
export const weaknessCode = z.enum([
  "english_penalty_risk", // 영어 감점 위험
  "science_conversion_risk", // 탐구 변표 위험
  "math_requirement_fail", // 수학 선택 제한 위험
  "low_data_confidence", // 데이터 신뢰도 낮음
  "small_quota_risk", // 소수 모집단위 리스크
  "high_volatility", // 변동성 큼
  "target_declined", // 목표 대학 접근도 하락
]);
export type WeaknessCode = z.infer<typeof weaknessCode>;

/** 추천 코드 (§8.5) */
export const recommendationCode = z.enum([
  "explore_math_heavy", // 수학 반영비 높은 대학 탐색
  "avoid_english_penalty", // 영어 감점 큰 대학 주의
  "simulate_math_up", // 수학 상승 시뮬레이션 권장
  "simulate_explore_up", // 탐구 상승 시뮬레이션 권장
  "compare_after_jinhak", // 진학사 공개 후 교차검증 권장
  "build_application_plan", // 가/나/다군 조합 필요
]);
export type RecommendationCode = z.infer<typeof recommendationCode>;

/** 분석 결과의 reason_codes(강점/추천)와 warnings(약점)에 쓰이는 합집합 */
export const reasonCode = z.union([
  strengthCode,
  weaknessCode,
  recommendationCode,
]);
export type ReasonCode = z.infer<typeof reasonCode>;
