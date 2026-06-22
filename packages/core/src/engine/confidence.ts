import type { Confidence } from "@pacer/shared";
import type { ConvertedScore } from "../domain/entities";

/**
 * 7. 신뢰도 산출 (§8.4) — 높음/중간/낮음/제한.
 *
 * | 신뢰도 | 조건 (§8.4)                       | 매핑                                  |
 * | 높음   | 공식 환산식 검수 완료 + 입결 있음    | exact + 근사 부분 없음 + 입결         |
 * | 중간   | 입결 있음 + 일부 근사 계산          | exact + 일부 근사(예: 변표) + 입결     |
 * | 낮음   | 근사 계산 중심                     | approx(백분위 합성)                   |
 * | 제한   | 데이터 부족 또는 조건 불확실         | unsupported 또는 입결 없음            |
 */
export function scoreConfidence(input: {
  method: ConvertedScore["method"];
  /** 환산 중 근사 처리된 부분 존재 여부 (ConvertedScore.approximations) */
  hasApproximations: boolean;
  /** 비교 가능한 전년도 입결 존재 여부 */
  hasHistorical: boolean;
}): Confidence {
  const { method, hasApproximations, hasHistorical } = input;
  if (method === "unsupported") return "limited";
  if (!hasHistorical) return "limited";
  if (method === "approx") return "low";
  return hasApproximations ? "medium" : "high";
}
