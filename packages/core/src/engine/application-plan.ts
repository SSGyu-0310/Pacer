import type { Band, PlanType } from "@pacer/shared";
import type {
  ApplicationGroup,
  ApplicationPlanCombination,
  ApplicationPlanPick,
  UnitAnalysis,
} from "../domain/entities";
import { ValidationError } from "../errors";
import { PLAN_RISK_THRESHOLDS, STRATEGY_BAND_MATRIX } from "./constants";
import { groupByRecruitmentGroup } from "./recruitment";
import { BAND_FAVORABLE, bandFavorability } from "./trend";

const GROUPS: readonly ApplicationGroup[] = ["ga", "na", "da"];

const BAND_LABEL: Record<Band, string> = {
  stable: "안정",
  match: "적정",
  reach: "소신",
  challenge: "도전",
  risk: "위험",
};

const STRATEGY_LABEL: Record<PlanType, string> = {
  stable: "안정형",
  balanced: "균형형",
  aggressive: "공격형",
  custom: "직접 선택",
};

const GROUP_LABEL: Record<ApplicationGroup, string> = {
  ga: "가군",
  na: "나군",
  da: "다군",
};

/**
 * 10. 원서 조합 후보 생성 (§7.10, §10.8, P2) — 가/나/다군 조합.
 *
 * 순수·결정적 함수. 입력은 이미 엔진이 계산한 UnitAnalysis(구간·score_gap)뿐 —
 * 여기서 점수를 다시 계산하지 않는다.
 *
 * 전략 매트릭스(§7.10 표): 안정형 가안정/나적정/다소신, 균형형 가적정/나적정/다소신,
 * 공격형 가안정/나소신/다도전. custom은 군당 1개 이하로 사용자가 직접 고른
 * 후보를 그대로 배치한다.
 *
 * 군 내 선택 규칙(결정적): 목표 구간 후보 중 score_gap 최대 → 동률은 unitId 사전순.
 * 목표 구간에 후보가 없으면 보수적 방향(안정 쪽) 인접 구간부터 차례로 대체하고
 * fallback=true + warning을 남긴다. 군에 후보가 아예 없으면 pick=null.
 *
 * 요약 문구는 §7.10 허용 표현만 사용한다 — "이 조합이면 합격" 같은 단정 금지.
 */
export function buildApplicationPlan(input: {
  strategy: PlanType;
  candidates: readonly UnitAnalysis[];
}): ApplicationPlanCombination {
  const { strategy, candidates } = input;

  const grouped = groupByRecruitmentGroup(candidates);
  const warnings: string[] = [];

  if (candidates.length === 0) {
    throw new ValidationError("조합을 만들 분석된 후보 모집단위가 없습니다");
  }

  const picks =
    strategy === "custom"
      ? pickCustom(grouped, warnings)
      : pickByMatrix(strategy, grouped, warnings);

  const picked = GROUPS.map((g) => picks[g]).filter(
    (p): p is ApplicationPlanPick & { band: Band } => p.band !== null,
  );
  if (picked.length === 0) {
    throw new ValidationError("가/나/다군 어디에도 배치 가능한 후보가 없습니다");
  }

  const overallRisk = riskOf(picked.map((p) => p.band));
  const riskiestGroup = extremeGroup(picks, "max");
  const mostStableGroup = extremeGroup(picks, "min");

  return {
    strategy,
    picks,
    overallRisk,
    riskiestGroup,
    mostStableGroup,
    summary: summarize(strategy, picks),
    warnings,
  };
}

/** §7.10 매트릭스 전략 — 군별 목표 구간에 맞춰 선택 */
function pickByMatrix(
  strategy: Exclude<PlanType, "custom">,
  grouped: Record<"ga" | "na" | "da" | "none", UnitAnalysis[]>,
  warnings: string[],
): Record<ApplicationGroup, ApplicationPlanPick> {
  const matrix = STRATEGY_BAND_MATRIX[strategy];
  const picks = {} as Record<ApplicationGroup, ApplicationPlanPick>;

  for (const group of GROUPS) {
    const target = matrix[group];
    const pool = grouped[group];
    if (pool.length === 0) {
      warnings.push(
        `${GROUP_LABEL[group]} 후보가 없습니다 — 후보 저장 목록을 확인해 주세요`,
      );
      picks[group] = emptyPick(group, target);
      continue;
    }
    const { unit, fallback } = selectInGroup(pool, target);
    if (fallback) {
      warnings.push(
        `${GROUP_LABEL[group]}에 ${BAND_LABEL[target]} 구간 후보가 없어 인접 구간으로 대체했습니다`,
      );
    }
    picks[group] = {
      group,
      unit: unit.unit,
      band: unit.band,
      scoreGap: unit.scoreGap,
      targetBand: target,
      fallback,
    };
  }
  return picks;
}

/** custom — 군당 1개 이하의 사용자 선택을 그대로 배치 */
function pickCustom(
  grouped: Record<"ga" | "na" | "da" | "none", UnitAnalysis[]>,
  warnings: string[],
): Record<ApplicationGroup, ApplicationPlanPick> {
  const picks = {} as Record<ApplicationGroup, ApplicationPlanPick>;
  for (const group of GROUPS) {
    const pool = grouped[group];
    if (pool.length > 1) {
      throw new ValidationError(
        `custom 조합은 ${GROUP_LABEL[group]}에 후보를 1개만 지정할 수 있습니다 (현재 ${pool.length}개)`,
      );
    }
    const unit = pool[0];
    if (!unit) {
      warnings.push(`${GROUP_LABEL[group]}에 선택된 후보가 없습니다`);
      picks[group] = emptyPick(group, "match");
      continue;
    }
    picks[group] = {
      group,
      unit: unit.unit,
      band: unit.band,
      scoreGap: unit.scoreGap,
      targetBand: unit.band,
      fallback: false,
    };
  }
  return picks;
}

/**
 * 군 내 선택: 목표 구간 → (없으면) 안정 쪽 인접 → (없으면) 위험 쪽 인접 순서.
 * 같은 구간에선 score_gap 큰 순, 동률은 unitId 사전순(결정성).
 */
function selectInGroup(
  pool: readonly UnitAnalysis[],
  target: Band,
): { unit: UnitAnalysis; fallback: boolean } {
  const byBand = (band: Band): UnitAnalysis | null => {
    const matches = pool
      .filter((u) => u.band === band)
      .sort(
        (a, b) =>
          b.scoreGap - a.scoreGap || a.unit.unitId.localeCompare(b.unit.unitId),
      );
    return matches[0] ?? null;
  };

  const exact = byBand(target);
  if (exact) return { unit: exact, fallback: false };

  const targetIdx = bandFavorability(target);
  // 보수적 방향(안정 쪽) 우선 — §2.1 단정 금지 원칙과 일관되게 리스크를 낮추는 쪽
  for (let i = targetIdx - 1; i >= 0; i--) {
    const band = BAND_FAVORABLE[i];
    const u = band !== undefined ? byBand(band) : null;
    if (u) return { unit: u, fallback: true };
  }
  for (let i = targetIdx + 1; i < BAND_FAVORABLE.length; i++) {
    const band = BAND_FAVORABLE[i];
    const u = band !== undefined ? byBand(band) : null;
    if (u) return { unit: u, fallback: true };
  }
  // pool이 비어있지 않으면 도달 불가
  throw new ValidationError("군 내 후보 선택에 실패했습니다");
}

function emptyPick(group: ApplicationGroup, target: Band): ApplicationPlanPick {
  return {
    group,
    unit: null,
    band: null,
    scoreGap: null,
    targetBand: target,
    fallback: false,
  };
}

function riskOf(bands: readonly Band[]): "low" | "medium" | "high" {
  const avg =
    bands.reduce((sum, b) => sum + bandFavorability(b), 0) / bands.length;
  if (avg <= PLAN_RISK_THRESHOLDS.low) return "low";
  if (avg <= PLAN_RISK_THRESHOLDS.medium) return "medium";
  return "high";
}

/** 가장 위험/안정 군 — 동률은 가→나→다 순서의 첫 군(결정성) */
function extremeGroup(
  picks: Record<ApplicationGroup, ApplicationPlanPick>,
  mode: "max" | "min",
): ApplicationGroup | null {
  let best: ApplicationGroup | null = null;
  let bestRank: number | null = null;
  for (const group of GROUPS) {
    const band = picks[group].band;
    if (band === null) continue;
    const rank = bandFavorability(band);
    if (
      bestRank === null ||
      (mode === "max" ? rank > bestRank : rank < bestRank)
    ) {
      best = group;
      bestRank = rank;
    }
  }
  return best;
}

/** §7.10 허용 표현 기반 결정적 요약 — 단정 금지(§11.4) */
function summarize(
  strategy: PlanType,
  picks: Record<ApplicationGroup, ApplicationPlanPick>,
): string {
  const parts = GROUPS.map((group) => {
    const p = picks[group];
    if (!p.unit || !p.band) return `${GROUP_LABEL[group]} 미배치`;
    return `${GROUP_LABEL[group]} ${BAND_LABEL[p.band]}권(${p.unit.university} ${p.unit.unitName})`;
  });
  return (
    `리스크 분산 관점에서 ${parts.join(", ")}을 선택하는 ${STRATEGY_LABEL[strategy]} 조합입니다. ` +
    `전년도 입결 기준 참고용이며, 올해 지원 표본에 따라 변동 가능성이 있습니다.`
  );
}
