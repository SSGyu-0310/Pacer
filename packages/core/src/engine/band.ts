import type { Band } from "@pacer/shared";
import type { BandAdjustmentFactors } from "../domain/entities";
import { BAND_ADJUSTMENTS, BAND_THRESHOLDS_PER100 } from "./constants";

/** 보수적 순서(낮음 → 높음) — 신뢰도 캡 적용에 사용 */
const BAND_ORDER: readonly Band[] = [
  "risk",
  "challenge",
  "reach",
  "match",
  "stable",
];

/**
 * 6. 구간 분류 (§8.3) — 안정/적정/소신/도전/위험.
 *
 * gapPer100 = score_gap / scale * 100 에 보정치(§8.3 보정 요소)를 더한 뒤
 * BAND_THRESHOLDS_PER100과 비교한다. 보정 요소:
 * 모집인원 변화 · 충원율 · 소수 모집단위 · 영어 감점 강도 · 탐구 변표 리스크 ·
 * 데이터 신뢰도 · 시험 시점(6모/9모/수능).
 *
 * 데이터 신뢰도가 낮음/제한이면 '안정' 단정을 금지하고 최대 '적정'으로 캡한다(§2.1).
 * 순수·결정적 함수.
 */
export function classifyBand(input: {
  scoreGap: number;
  /** 환산 만점(ConvertedScore.scale) */
  scale: number;
  factors?: BandAdjustmentFactors;
}): Band {
  const { scoreGap, scale, factors } = input;
  const gapPer100 = (scoreGap / scale) * 100;
  const adjusted = gapPer100 + totalAdjustment(factors);

  let band: Band;
  if (adjusted >= BAND_THRESHOLDS_PER100.stable) band = "stable";
  else if (adjusted >= BAND_THRESHOLDS_PER100.match) band = "match";
  else if (adjusted >= BAND_THRESHOLDS_PER100.reach) band = "reach";
  else if (adjusted >= BAND_THRESHOLDS_PER100.challenge) band = "challenge";
  else band = "risk";

  // 데이터 신뢰도 낮음/제한 → '안정' 단정 금지(최대 '적정')
  const confidence = factors?.dataConfidence;
  if (confidence === "low" || confidence === "limited") {
    band = capBand(band, "match");
  }

  return band;
}

function totalAdjustment(factors?: BandAdjustmentFactors): number {
  if (!factors) return 0;
  let adj = 0;

  // 모집인원 변화
  if (factors.quotaChangeRatio !== undefined && factors.quotaChangeRatio !== null) {
    if (factors.quotaChangeRatio <= BAND_ADJUSTMENTS.quotaCut.threshold)
      adj += BAND_ADJUSTMENTS.quotaCut.adjust;
    else if (factors.quotaChangeRatio >= BAND_ADJUSTMENTS.quotaUp.threshold)
      adj += BAND_ADJUSTMENTS.quotaUp.adjust;
  }

  // 충원율
  if (
    factors.additionalPassRate !== undefined &&
    factors.additionalPassRate !== null &&
    factors.additionalPassRate >= BAND_ADJUSTMENTS.highAdditionalPass.threshold
  ) {
    adj += BAND_ADJUSTMENTS.highAdditionalPass.adjust;
  }

  // 소수 모집단위
  if (factors.smallQuota) adj += BAND_ADJUSTMENTS.smallQuota;

  // 영어 감점 강도 × 사용자 영어 등급
  if (
    factors.userEnglishGrade !== undefined &&
    factors.userEnglishGrade >= BAND_ADJUSTMENTS.englishPenalty.minGrade &&
    (factors.englishPenaltySpreadPer100 ?? 0) >=
      BAND_ADJUSTMENTS.englishPenalty.minSpreadPer100
  ) {
    adj += BAND_ADJUSTMENTS.englishPenalty.adjust;
  }

  // 탐구 변표 리스크
  if (factors.scienceConversionRisk) adj += BAND_ADJUSTMENTS.scienceConversion;

  // 시험 시점
  if (factors.examType) adj += BAND_ADJUSTMENTS.examTiming[factors.examType];

  // 데이터 신뢰도 낮음(추가로 보수 보정 — 캡과 별개)
  if (factors.dataConfidence === "low" || factors.dataConfidence === "limited") {
    adj += BAND_ADJUSTMENTS.lowConfidence;
  }

  return adj;
}

function capBand(band: Band, max: Band): Band {
  return BAND_ORDER.indexOf(band) > BAND_ORDER.indexOf(max) ? max : band;
}
