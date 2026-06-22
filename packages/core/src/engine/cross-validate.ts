import type { Band } from "@pacer/shared";
import type {
  CompetitorSignal,
  CrossAgreement,
  CrossValidationItem,
  CrossValidationSummary,
  UnitAnalysis,
} from "../domain/entities";
import {
  GOSOK_COLOR_TO_BAND,
  KANSU_TO_BAND,
  PROBABILITY_BAND_FLOORS,
} from "./constants";
import { bandFavorability } from "./trend";

/**
 * 12. 외부 도구 교차검증 (§7.7.4, P2) — 수동 입력된 CompetitorSignal과
 * 자체 분석 구간의 일치/불일치 분류.
 *
 * 순수·결정적 함수. 외부 값 → 구간 매핑은 보수적 휴리스틱 v1(constants)이며,
 * "어느 쪽이 더 정확한가"는 판정하지 않는다(§11.1) — LLM은 이 분류 결과로
 * '왜 다를 수 있는지'만 설명한다.
 *
 * agreement: 동일 구간 agree / 1구간 차이 near / 2구간 이상 disagree /
 * 매핑 불가(메모 등)·분석 결과 없음 uncertain.
 */
export function crossValidate(
  results: readonly UnitAnalysis[],
  signals: readonly CompetitorSignal[],
): CrossValidationSummary {
  const byUnitId = new Map(results.map((r) => [r.unit.unitId, r]));

  // 결정적 순서: 입력 순서와 무관하게 unitId → provider → value 로 정렬
  const sorted = [...signals].sort(
    (a, b) =>
      a.unitId.localeCompare(b.unitId) ||
      a.provider.localeCompare(b.provider) ||
      a.value.localeCompare(b.value),
  );

  const items: CrossValidationItem[] = sorted.map((signal) => {
    const analysis = byUnitId.get(signal.unitId) ?? null;
    const internalBand = analysis?.band ?? null;
    const externalBand = signalToBand(signal);
    return {
      unitId: signal.unitId,
      unit: analysis?.unit ?? null,
      provider: signal.provider,
      valueType: signal.valueType,
      value: signal.value,
      internalBand,
      externalBand,
      agreement: agreementOf(internalBand, externalBand),
    };
  });

  const totals: Record<CrossAgreement, number> = {
    agree: 0,
    near: 0,
    disagree: 0,
    uncertain: 0,
  };
  for (const item of items) totals[item.agreement]++;

  return { items, totals };
}

/** 외부 도구 값 → 구간 근사. 해석 불가하면 null(uncertain). */
export function signalToBand(signal: {
  valueType: CompetitorSignal["valueType"];
  value: string;
}): Band | null {
  switch (signal.valueType) {
    case "kansu": {
      const n = Number.parseInt(signal.value.trim(), 10);
      return Number.isInteger(n) ? (KANSU_TO_BAND[n] ?? null) : null;
    }
    case "color": {
      const key = signal.value.trim().toLowerCase();
      return GOSOK_COLOR_TO_BAND[key] ?? null;
    }
    case "probability": {
      const n = Number.parseFloat(signal.value.replace("%", "").trim());
      if (!Number.isFinite(n) || n < 0 || n > 100) return null;
      for (const floor of PROBABILITY_BAND_FLOORS) {
        if (n >= floor.min) return floor.band;
      }
      return null;
    }
    case "memo":
      // 자유 메모는 구간으로 환원하지 않는다 — LLM 참고용으로만 전달
      return null;
  }
}

function agreementOf(
  internal: Band | null,
  external: Band | null,
): CrossAgreement {
  if (internal === null || external === null) return "uncertain";
  const distance = Math.abs(bandFavorability(internal) - bandFavorability(external));
  if (distance === 0) return "agree";
  if (distance === 1) return "near";
  return "disagree";
}
