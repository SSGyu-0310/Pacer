import type {
  ConvertedScore,
  HistoricalRef,
  NormalizedScores,
} from "../domain/entities";
import { round2 } from "./constants";

const PERCENTILE_COMPARISON_SUBJECTS = [
  "korean",
  "math",
  "inquiry1",
  "inquiry2",
] as const;

/**
 * 5. 전년도 입결 비교 (§8.3, §18.1 입결 대비 점수차 계산).
 * score_gap = user_score - historical_cut_score
 *
 * - 정확 환산(exact) → 환산점수 컷(cutScore)과 비교
 * - 공식식 기반 상대비교(relative)·근사 비교(approx) → 백분위 컷(percentileCut)과 비교
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

/**
 * no-formula Tier0 비교: 사용자 국·수·탐 백분위 평균을 입결 percentileCut과 직접 비교한다.
 * 환산식이 없으므로 convertedScore가 아니며, scale은 항상 100으로 해석한다.
 */
export function comparePercentileAverageToHistorical(
  normalized: NormalizedScores,
  historical: HistoricalRef | null,
): {
  percentileAverage: number | null;
  historicalReferenceScore: number | null;
  scoreGap: number | null;
} {
  const percentileAverage = percentileAverageForComparison(normalized);
  const reference = historical?.percentileCut;
  if (
    percentileAverage === null ||
    reference === null ||
    reference === undefined
  ) {
    return {
      percentileAverage,
      historicalReferenceScore: null,
      scoreGap: null,
    };
  }

  return {
    percentileAverage,
    historicalReferenceScore: reference,
    scoreGap: round2(percentileAverage - reference),
  };
}

export function percentileAverageForComparison(
  normalized: NormalizedScores,
): number | null {
  const values = PERCENTILE_COMPARISON_SUBJECTS.flatMap((subject) => {
    const percentile = normalized.bySubject.get(subject)?.percentile;
    return percentile === undefined ? [] : [percentile];
  });
  if (values.length < 2) return null;
  return round2(values.reduce((sum, value) => sum + value, 0) / values.length);
}
