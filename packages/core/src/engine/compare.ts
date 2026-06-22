import type { ConvertedScore, HistoricalRef } from "../domain/entities";
import { round2 } from "./constants";

/**
 * 5. 전년도 입결 비교 (§8.3, §18.1 입결 대비 점수차 계산).
 * score_gap = user_score - historical_cut_score
 *
 * - 정확 환산(exact) → 환산점수 컷(cutScore)과 비교
 * - 근사 비교(approx) → 백분위 컷(percentileCut)과 비교
 * - 비교 기준이 없으면 gap = null (분석 불가 — §8.2)
 */
export function compareToHistorical(
  converted: ConvertedScore,
  historical: HistoricalRef | null,
): { historicalReferenceScore: number | null; scoreGap: number | null } {
  if (converted.convertedScore === null || historical === null) {
    return { historicalReferenceScore: null, scoreGap: null };
  }

  const reference =
    converted.method === "exact"
      ? historical.cutScore
      : historical.percentileCut;

  if (reference === null || reference === undefined) {
    return { historicalReferenceScore: null, scoreGap: null };
  }

  return {
    historicalReferenceScore: reference,
    scoreGap: round2(converted.convertedScore - reference),
  };
}
