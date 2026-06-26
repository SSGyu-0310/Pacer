import type { Band, Subject } from "@pacer/shared";
import type {
  AnalysisCandidate,
  AnalysisSummary,
  ScoreInput,
  SimulationAdjustment,
  SimulationResult,
  SimulationUnitChange,
  TargetSnapshot,
  UnitAnalysis,
} from "../domain/entities";
import {
  applyAdjustments,
  mostFavorableBand,
  bandFavorability,
  normalizeScores,
  validateScores,
} from "../engine";
import { NotFoundError, ValidationError } from "../errors";
import type {
  CycleRepository,
  ScoreRepository,
  TargetRepository,
  UnitRepository,
} from "../ports";
import { analyzeUnit } from "./analysis.service";

const EMPTY_DISTRIBUTION: Record<Band, number> = {
  stable: 0,
  match: 0,
  reach: 0,
  challenge: 0,
  risk: 0,
};

/** 약점 reason code → 주의 과목 매핑 (§7.9 "주의할 과목") */
const WEAKNESS_SUBJECTS: Partial<Record<string, Subject[]>> = {
  english_penalty_risk: ["english"],
  science_conversion_risk: ["inquiry1", "inquiry2"],
  math_requirement_fail: ["math"],
};

/** 과목 정렬 순서(결정성) — shared subject enum 순서 */
const SUBJECT_ORDER: readonly Subject[] = [
  "korean",
  "math",
  "english",
  "history",
  "inquiry1",
  "inquiry2",
  "second_language",
];

/**
 * §7.9 점수 시뮬레이션 (P1) — 가상 점수로 엔진을 서버에서 재실행한다.
 *
 * 원칙:
 * - 기준선(baseline)도 같은 후보 데이터로 즉석 재계산한다 — 저장된 스냅샷과
 *   비교하면 레퍼런스 데이터 갱신 시점에 따라 사과/배 비교가 되기 때문.
 * - 결과는 저장하지 않는다(일회성). AnalysisSnapshot을 만들지 않는다.
 * - 클라이언트에는 결과(구간 변화·집계)만 반환 — 환산식·입결 원문 노출 금지(§8.1).
 * - 응답에는 §7.9 주의 문구(SIMULATION_NOTICE)를 항상 동봉한다(라우트에서).
 */
export class SimulationService {
  constructor(
    private readonly cycles: CycleRepository,
    private readonly scores: ScoreRepository,
    private readonly targets: TargetRepository,
    private readonly units: UnitRepository,
  ) {}

  async run(
    cycleId: string,
    examScoreId: string,
    adjustments: SimulationAdjustment[],
  ): Promise<SimulationResult> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);

    const examScore = await this.scores.findById(examScoreId);
    if (!examScore || examScore.cycleId !== cycleId) {
      throw new NotFoundError(`exam score ${examScoreId}`);
    }
    if (adjustments.length === 0) {
      throw new ValidationError("조정 항목이 최소 하나 필요합니다");
    }

    // 가상 점수 적용 + 검증(§8.1-1) — 깨진 가상 점수로 조용히 계산하지 않는다
    const simulatedScore = applyAdjustments(examScore, adjustments);
    const validation = validateScores(simulatedScore);
    if (!validation.valid) {
      throw new ValidationError("시뮬레이션 점수 검증 실패", validation.errors);
    }

    const target = await this.targets.findLatest(cycleId, examScore.examType);
    const targetUniversityIds = target?.targetUniversityIds.length
      ? target.targetUniversityIds
      : undefined;
    const targetUnitIds = target?.targetUnitIds.length
      ? target.targetUnitIds
      : undefined;
    const candidates = await this.units.loadCandidates({
      admissionYear: cycle.admissionYear,
      track: cycle.track,
      preferredRegions: target?.preferredRegions.length
        ? target.preferredRegions
        : undefined,
      targetUniversities: !targetUniversityIds && target?.targetUniversities.length
        ? target.targetUniversities
        : undefined,
      targetUniversityIds,
      targetUnitIds,
    });

    const baseline = runEngine(examScore, candidates);
    const simulated = runEngine(simulatedScore, candidates);

    return buildSimulationResult({
      baseline,
      simulated,
      examScore,
      candidates,
      adjustments,
      target,
    });
  }
}

interface EngineRun {
  results: UnitAnalysis[];
  summary: AnalysisSummary;
}

/** 후보 전체에 순수 엔진 파이프라인 실행(분석 서비스와 동일 — analyzeUnit 공유) */
function runEngine(
  score: ScoreInput,
  candidates: readonly AnalysisCandidate[],
): EngineRun {
  const normalized = normalizeScores(score);
  const summary: AnalysisSummary = {
    candidates: candidates.length,
    analyzed: 0,
    ineligible: 0,
    unsupported: 0,
    insufficientData: 0,
  };
  const results: UnitAnalysis[] = [];
  for (const candidate of candidates) {
    const r = analyzeUnit(candidate, normalized, score.examType);
    if (r.kind === "ok") {
      results.push(r.analysis);
      summary.analyzed++;
    } else {
      summary[r.kind]++;
    }
  }
  return { results, summary };
}

/** 순수 조립 — 결정적 (시뮬레이션 결과 비교·효율 과목·주의 과목) */
export function buildSimulationResult(args: {
  baseline: EngineRun;
  simulated: EngineRun;
  examScore: ScoreInput;
  candidates: readonly AnalysisCandidate[];
  adjustments: readonly SimulationAdjustment[];
  target: TargetSnapshot | null;
}): SimulationResult {
  const { baseline, simulated, examScore, candidates, adjustments, target } =
    args;
  const targetUniversities = target?.targetUniversities ?? [];

  const baselineByUnit = new Map(
    baseline.results.map((r) => [r.unit.unitId, r]),
  );
  const simulatedByUnit = new Map(
    simulated.results.map((r) => [r.unit.unitId, r]),
  );

  // 구간 변화 목록 — unitId 사전순(결정성)
  const ids = [
    ...new Set([...baselineByUnit.keys(), ...simulatedByUnit.keys()]),
  ].sort();
  const bandChanges: SimulationUnitChange[] = [];
  let movedToMatchOrBetter = 0;
  for (const id of ids) {
    const before = baselineByUnit.get(id) ?? null;
    const after = simulatedByUnit.get(id) ?? null;
    const fromBand = before?.band ?? null;
    const toBand = after?.band ?? null;
    if (fromBand === toBand) continue;
    bandChanges.push({ unit: (after ?? before)!.unit, fromBand, toBand });

    const wasMatchOrBetter =
      fromBand !== null && bandFavorability(fromBand) <= bandFavorability("match");
    const isMatchOrBetter =
      toBand !== null && bandFavorability(toBand) <= bandFavorability("match");
    if (!wasMatchOrBetter && isMatchOrBetter) movedToMatchOrBetter++;
  }

  return {
    baselineDistribution: distribution(baseline.results),
    simulatedDistribution: distribution(simulated.results),
    movedToMatchOrBetter,
    bandChanges,
    targetApproach: {
      baseline: mostFavorableBand(baseline.results, targetUniversities),
      simulated: mostFavorableBand(simulated.results, targetUniversities),
    },
    mostEfficientSubject: mostEfficientSubject(
      examScore,
      candidates,
      adjustments,
      baseline,
    ),
    cautionSubjects: cautionSubjects(simulated.results, examScore),
    summary: simulated.summary,
  };
}

/**
 * §7.9 "가장 효율적인 과목" — 과목별 조정을 단독 적용해 재실행했을 때
 * 구간이 유리해진 모집단위 수가 가장 큰 과목. 동률은 과목 enum 순서(결정성).
 * 조정이 한 과목뿐이면 그 과목(비교 불필요).
 */
function mostEfficientSubject(
  examScore: ScoreInput,
  candidates: readonly AnalysisCandidate[],
  adjustments: readonly SimulationAdjustment[],
  baseline: EngineRun,
): Subject | null {
  const subjects = [...new Set(adjustments.map((a) => a.subject))];
  if (subjects.length === 0) return null;
  if (subjects.length === 1) return subjects[0] ?? null;

  const baselineByUnit = new Map(
    baseline.results.map((r) => [r.unit.unitId, r]),
  );

  let best: Subject | null = null;
  let bestImproved = -1;
  const ordered = [...subjects].sort(
    (a, b) => SUBJECT_ORDER.indexOf(a) - SUBJECT_ORDER.indexOf(b),
  );
  for (const subject of ordered) {
    const only = adjustments.filter((a) => a.subject === subject);
    const run = runEngine(applyAdjustments(examScore, only), candidates);
    let improved = 0;
    for (const r of run.results) {
      const before = baselineByUnit.get(r.unit.unitId);
      if (!before) {
        improved++; // 새로 분석 가능해진 단위도 개선으로 본다
        continue;
      }
      if (bandFavorability(r.band) < bandFavorability(before.band)) improved++;
    }
    if (improved > bestImproved) {
      best = subject;
      bestImproved = improved;
    }
  }
  return best;
}

/** §7.9 "주의할 과목" — 시뮬레이션 후에도 남아있는 약점 reason code의 과목 */
function cautionSubjects(
  simulatedResults: readonly UnitAnalysis[],
  examScore: ScoreInput,
): Subject[] {
  const present = new Set(examScore.scores.map((s) => s.subject));
  const out = new Set<Subject>();
  for (const r of simulatedResults) {
    for (const code of [...r.reasonCodes, ...r.warnings]) {
      for (const subject of WEAKNESS_SUBJECTS[code] ?? []) {
        if (present.has(subject)) out.add(subject);
      }
    }
  }
  return [...out].sort(
    (a, b) => SUBJECT_ORDER.indexOf(a) - SUBJECT_ORDER.indexOf(b),
  );
}

function distribution(results: readonly UnitAnalysis[]): Record<Band, number> {
  const d = { ...EMPTY_DISTRIBUTION };
  for (const r of results) d[r.band]++;
  return d;
}
