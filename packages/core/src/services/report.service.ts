import type { Band, ExamType, ReportType, Subject } from "@pacer/shared";
import type {
  AdmissionRuleData,
  AnalysisCandidate,
  CrossAgreement,
  CrossValidationSummary,
  Cycle,
  ExamScore,
  ScoreInput,
  SimulationAdjustment,
  TargetSnapshot,
  TrendAnalysis,
  UnitAnalysis,
} from "../domain/entities";
import type {
  LlmCompetitorComparison,
  LlmReportInput,
  LlmPositionReportData,
  LlmTrendSummary,
  ReportContent,
  StrategyReport,
} from "../domain/report";
import {
  analyzeTrend,
  applyAdjustments,
  bandFavorability,
  crossValidate,
  formatKeyWeight,
  mostFavorableBand,
  normalizeScores,
  validateScores,
} from "../engine";
import { NotFoundError, ValidationError } from "../errors";
import type {
  AnalysisRepository,
  CompetitorSignalRepository,
  CycleRepository,
  LlmReporter,
  ReportRepository,
  ScoreRepository,
  TargetRepository,
  UnitRepository,
} from "../ports";
import { analyzeUnit } from "./analysis.service";

/** 포지션 리포트의 결정론적 보강 데이터(엔진 계산) — keyWeight·what-if */
interface PositionEnrichment {
  keyWeightByUnit: Map<string, string | null>;
  scenarios: LlmPositionReportData["scenarios"];
}

/** report_type ↔ exam_type 정합성 (해당 없는 타입은 제한 없음) */
const REPORT_EXAM: Partial<Record<ReportType, ExamType>> = {
  june_position_report: "june_mock",
  september_change_report: "september_mock",
  csat_final_report: "csat",
};

/**
 * §11 — 엔진의 구조화 출력 → LLM 설명 생성 → 저장.
 * LLM은 계산하지 않는다(§8.1): 여기서 만드는 입력(§11.2)은 이미 계산된
 * 구간 분포·reason code 요약일 뿐, 점수·확률 계산을 위임하지 않는다.
 * 스키마 검증·금지어 필터는 LlmReporter(게이트웨이) 구현이 보장한다.
 */
export class ReportService {
  constructor(
    private readonly cycles: CycleRepository,
    private readonly scores: ScoreRepository,
    private readonly targets: TargetRepository,
    private readonly analyses: AnalysisRepository,
    private readonly llm: LlmReporter,
    private readonly reports: ReportRepository,
    /** P2 교차검증 리포트용 — 수동 입력 신호(§7.7.4) */
    private readonly competitorSignals?: CompetitorSignalRepository,
    /**
     * v2 포지션 리포트 보강용(§3 핵심 반영, §5 what-if) — 후보 규칙 재로드.
     * 미주입 시 keyWeight/시나리오 없이 기존 동작 유지(점진 도입).
     */
    private readonly units?: UnitRepository,
  ) {}

  async generate(args: {
    cycleId: string;
    examScoreId: string;
    analysisSnapshotId: string;
    reportType: ReportType;
  }): Promise<{
    reportId: string;
    content: ReportContent;
    modelName: string;
    promptVersion: string;
  }> {
    const cycle = await this.cycles.findById(args.cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${args.cycleId}`);

    const examScore = await this.scores.findById(args.examScoreId);
    if (!examScore || examScore.cycleId !== args.cycleId) {
      throw new NotFoundError(`exam score ${args.examScoreId}`);
    }

    const expected = REPORT_EXAM[args.reportType];
    if (expected && expected !== examScore.examType) {
      throw new ValidationError(
        `report_type(${args.reportType})과 exam_type(${examScore.examType})이 일치하지 않습니다`,
      );
    }

    const snapshot = await this.analyses.findSnapshotMeta(args.analysisSnapshotId);
    if (!snapshot) {
      throw new NotFoundError(`snapshot ${args.analysisSnapshotId}`);
    }
    if (
      snapshot.cycleId !== args.cycleId ||
      snapshot.examScoreId !== args.examScoreId
    ) {
      throw new NotFoundError(`snapshot ${args.analysisSnapshotId}`);
    }

    const results = await this.analyses.findResults(args.analysisSnapshotId);
    if (results === null) {
      throw new NotFoundError(`snapshot ${args.analysisSnapshotId}`);
    }

    const target = await this.targets.findLatest(
      args.cycleId,
      examScore.examType,
    );

    // P1 — 9모 변화 리포트: 6모 성적·분석이 있으면 trend를 계산한다(§7.7.2).
    // 6모 기록이 없는 신규 유저도 리포트는 받을 수 있다(§5.2) — trend 없이 생성.
    let trend: TrendAnalysis | null = null;
    let trendMissingNotice: string | null = null;
    if (args.reportType === "september_change_report") {
      trend = await this.loadJuneTrend(args.cycleId, examScore, results, target);
      if (!trend) {
        trendMissingNotice =
          "6월 모의평가 기록이 없어 변화 비교 없이 현재 위치 기준으로 작성되었습니다.";
      }
    }

    // P2 — 교차검증 리포트: 수동 입력된 외부 도구 결과가 필수다(§7.7.4).
    let crossValidation: CrossValidationSummary | null = null;
    if (args.reportType === "cross_validation_report") {
      if (!this.competitorSignals) {
        throw new ValidationError("교차검증 리포트가 아직 활성화되지 않았습니다");
      }
      const signals = await this.competitorSignals.list(
        args.cycleId,
        examScore.examType,
      );
      if (signals.length === 0) {
        throw new ValidationError(
          "입력된 외부 도구 결과가 없습니다 — 진학사/고속성장/텔레그노시스 결과를 직접 입력한 뒤 생성할 수 있습니다",
        );
      }
      crossValidation = crossValidate(results, signals);
    }

    // v2 — 핵심 반영비·what-if는 후보 규칙이 있어야 계산 가능(§3, §5).
    // UnitRepository가 주입된 경우에만, 화면에 노출되는 라인 + 구간이 열릴
    // 여지가 있는 라인으로 후보를 좁혀 재로드한다(전체 재분석 회피).
    const enrichment = await this.buildEnrichment(cycle, examScore, results);

    const input = buildLlmInput({
      reportType: args.reportType,
      gradeStatus: cycle.gradeStatus,
      examScore,
      target,
      results,
      trend,
      crossValidation,
      enrichment,
      extraWarnings: trendMissingNotice ? [trendMissingNotice] : [],
    });

    // LLM 게이트웨이: 스키마(§11.3)·금지어(§11.4)·면책(§13.3) 검증 포함
    const generated = await this.llm.generate(input);

    const { reportId } = await this.reports.save({
      cycleId: args.cycleId,
      examScoreId: args.examScoreId,
      reportType: args.reportType,
      content: generated.content,
      modelName: generated.modelName,
      promptVersion: generated.promptVersion,
    });

    return { reportId, ...generated };
  }

  async getReport(cycleId: string, reportId: string): Promise<StrategyReport> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);

    const report = await this.reports.findById(reportId);
    if (!report || report.cycleId !== cycleId) {
      throw new NotFoundError(`report ${reportId}`);
    }
    return report;
  }

  async getLatestReport(cycleId: string): Promise<StrategyReport> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);

    const report = await this.reports.findLatestForCycle(cycleId);
    if (!report) throw new NotFoundError(`report for cycle ${cycleId}`);
    return report;
  }

  /** 6모 성적 + 6모 분석 스냅샷이 모두 있어야 trend를 만든다(부분 데이터로 비교하지 않는다) */
  private async loadJuneTrend(
    cycleId: string,
    currExamScore: ExamScore,
    currResults: UnitAnalysis[],
    target: TargetSnapshot | null,
  ): Promise<TrendAnalysis | null> {
    const prevScore = await this.scores.findByExamType(cycleId, "june_mock");
    if (!prevScore) return null;

    const prevSnapshot = await this.analyses.findLatestSnapshotMeta(
      cycleId,
      "june_position",
    );
    if (!prevSnapshot || prevSnapshot.examScoreId !== prevScore.id) return null;

    const prevResults = await this.analyses.findResults(prevSnapshot.id);
    if (prevResults === null) return null;

    return analyzeTrend(
      { examScore: prevScore, results: prevResults },
      { examScore: currExamScore, results: currResults },
      target?.targetUniversities ?? [],
    );
  }

  /**
   * 핵심 반영비(§3)와 what-if(§5)는 후보 규칙으로 재계산해야 한다.
   * 분석 스냅샷에는 규칙 원문이 없으므로 UnitRepository로 후보를 다시 로드한다.
   * 전체(수천 개)를 재분석하지 않고, 화면에 노출되는 상위 라인 + 구간이 한 단계
   * 위로 열릴 여지가 있는(=stable이 아닌) 상위 라인만 unitId로 좁혀 로드한다.
   * units 미주입 또는 결과 없음 시 보강 없이 null.
   */
  private async buildEnrichment(
    cycle: Cycle,
    examScore: ExamScore,
    results: UnitAnalysis[],
  ): Promise<PositionEnrichment | null> {
    if (!this.units || results.length === 0) return null;

    // findResults는 scoreGap 내림차순 정렬. 노출 라인 후보 윈도우(품질 정렬용) +
    // 구간 상향 여지가 있는 라인을 합쳐 로드한다.
    const lineWindowIds = results
      .slice(0, LINE_SELECTION_WINDOW)
      .map((r) => r.unit.unitId);
    const scenarioScanIds = results
      .filter((r) => r.band !== "stable")
      .slice(0, SCENARIO_SCAN_LIMIT)
      .map((r) => r.unit.unitId);
    const wantedIds = [...new Set([...lineWindowIds, ...scenarioScanIds])];
    if (wantedIds.length === 0) return null;

    const candidates = await this.units.loadCandidates({
      admissionYear: cycle.admissionYear,
      track: cycle.track,
      targetUnitIds: wantedIds,
    });
    if (candidates.length === 0) return null;

    const keyWeightByUnit = new Map<string, string | null>();
    for (const candidate of candidates) {
      keyWeightByUnit.set(candidate.unit.unitId, formatKeyWeight(candidate.rule));
    }

    const normalized = normalizeScores(examScore);
    const scenarios = buildWhatIfScenarios({
      examScore,
      candidates,
      weaknessSubjects: normalized.weaknessSubjects,
    });

    return { keyWeightByUnit, scenarios };
  }
}

/** 포지션 리포트에 노출하는 라인 수(§3) — buildPositionReportData와 일치시킨다. */
const POSITION_LINE_COUNT = 8;
/** 라인 품질 정렬(반영비 검수 미완 라인 후순위) 대상 윈도우. */
const LINE_SELECTION_WINDOW = 150;
/** what-if 스캔 상한 — 구간 상향 여지가 큰 상위 라인만 재계산(성능 가드). */
const SCENARIO_SCAN_LIMIT = 60;

/**
 * 반영비가 영어 단일로만 잡힌 라인(=국·수·탐 반영비 미수집, 검수 대기 데이터)을 식별한다.
 * 이런 라인은 환산 비교가 왜곡돼 격차가 비현실적으로 커지므로 노출 후순위로 둔다(숨기진 않음 §8.2).
 */
const ENGLISH_ONLY_KEYWEIGHT = /^영어 \d+%$/;
function lineQualityRank(
  unitId: string,
  enrichment: PositionEnrichment | null,
): number {
  const keyWeight = enrichment?.keyWeightByUnit.get(unitId);
  return keyWeight && ENGLISH_ONLY_KEYWEIGHT.test(keyWeight) ? 1 : 0;
}

/** §11.2 프롬프트 입력 조립 — 순수 함수(결정적) */
export function buildLlmInput(args: {
  reportType: ReportType;
  gradeStatus: string;
  examScore: ExamScore;
  target: TargetSnapshot | null;
  results: UnitAnalysis[];
  /** P1 — 9모 변화 리포트의 6모↔9모 diff(analyzeTrend 결과) */
  trend?: TrendAnalysis | null;
  /** P2 — 교차검증 리포트의 일치도(crossValidate 결과) */
  crossValidation?: CrossValidationSummary | null;
  /** v2 — 핵심 반영비·what-if 보강(후보 규칙 재로드 결과) */
  enrichment?: PositionEnrichment | null;
  extraWarnings?: string[];
}): LlmReportInput {
  const {
    reportType,
    gradeStatus,
    examScore,
    target,
    results,
    trend = null,
    crossValidation = null,
    enrichment = null,
    extraWarnings = [],
  } = args;

  const normalized = normalizeScores(examScore);

  const bandDistribution: Record<Band, number> = {
    stable: 0,
    match: 0,
    reach: 0,
    challenge: 0,
    risk: 0,
  };
  for (const r of results) bandDistribution[r.band]++;

  // reason code 빈도 상위 5개(동률은 코드 사전순 — 결정성)
  const counts = new Map<string, number>();
  for (const r of results) {
    for (const c of [...r.reasonCodes, ...r.warnings]) {
      counts.set(c, (counts.get(c) ?? 0) + 1);
    }
  }
  const topReasonCodes = [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 5)
    .map(([code]) => code);

  return {
    reportType,
    userContext: {
      role: reportType === "parent_summary_report" ? "parent" : "student",
      examType: examScore.examType,
      gradeStatus,
      riskProfile: target?.riskProfile ?? "balanced",
    },
    scoreSummary: {
      strengthSubjects: normalized.strengthSubjects,
      weaknessSubjects: normalized.weaknessSubjects,
      trend: trend ? toLlmTrend(trend) : null,
    },
    analysisSummary: { bandDistribution, topReasonCodes },
    targetSummary: {
      targetUniversities: target?.targetUniversities ?? [],
      targetDistance: mostFavorableBand(
        results,
        target?.targetUniversities ?? [],
      ),
    },
    positionReport: buildPositionReportData(
      examScore,
      results,
      normalized,
      target,
      enrichment,
    ),
    competitorComparison: crossValidation
      ? toLlmComparison(crossValidation)
      : null,
    warnings: [...examWarnings(examScore), ...extraWarnings],
  };
}

function buildPositionReportData(
  examScore: ExamScore,
  results: UnitAnalysis[],
  normalized: ReturnType<typeof normalizeScores>,
  target: TargetSnapshot | null,
  enrichment: PositionEnrichment | null,
): LlmPositionReportData | null {
  const representative = results[0] ?? null;
  if (!representative) return null;

  return {
    scope: hasExplicitTarget(target) ? "targeted" : "exploration",
    season: seasonForExam(examScore.examType),
    metric: {
      mode: representative.metricMode,
      myValue: representative.convertedScore,
      label: representative.metricLabel,
      cutLabel: representative.cutLabel,
    },
    subjects: examScore.scores.flatMap((score) => {
      const metric =
        score.percentile !== undefined
          ? "백분위"
          : score.grade !== undefined
            ? "등급"
            : score.standardScore !== undefined
              ? "표준점수"
              : null;
      const value = score.percentile ?? score.grade ?? score.standardScore;
      if (!metric || value === undefined) return [];
      return [
        {
          name: subjectLabel(score.subject),
          metric,
          value,
          role: normalized.strengthSubjects.includes(score.subject)
            ? "strength"
            : normalized.weaknessSubjects.includes(score.subject)
              ? "caution"
              : "neutral",
          ...(score.subject === "english" && score.grade === 1
            ? { note: "절대평가·감점없음" }
            : {}),
        },
      ];
    }),
    lines: rankLinesForDisplay(results, enrichment)
      .slice(0, POSITION_LINE_COUNT)
      .map((result) => ({
      univ: result.unit.university,
      dept: result.unit.unitName,
      group: recruitmentGroupLabel(result.unit.recruitmentGroup),
      keyWeight: enrichment?.keyWeightByUnit.get(result.unit.unitId) ?? null,
      myValue: result.convertedScore,
      cut: result.historicalReferenceScore,
      gap: result.scoreGap,
      tier: bandLabel(result.band),
      reliability: reliabilityLabel(result.confidence),
    })),
    // What-if(§5): 약점 과목을 끌어올렸을 때 구간이 열리는 라인만 결정론적으로 노출.
    scenarios: enrichment?.scenarios ?? [],
  };
}

/**
 * 노출 라인 정렬 — 격차순(scoreGap desc, findResults 정렬)은 유지하되, 반영비가
 * 검수 미완(영어 단일)인 라인만 안정적으로 후순위로 민다. enrichment 없으면 원순서.
 */
function rankLinesForDisplay(
  results: UnitAnalysis[],
  enrichment: PositionEnrichment | null,
): UnitAnalysis[] {
  if (!enrichment) return results;
  return [...results].sort(
    (a, b) =>
      lineQualityRank(a.unit.unitId, enrichment) -
      lineQualityRank(b.unit.unitId, enrichment),
  );
}

function hasExplicitTarget(target: TargetSnapshot | null): boolean {
  return Boolean(
    target &&
      (target.targetUniversityIds.length > 0 ||
        target.targetUnitIds.length > 0 ||
        target.targetUniversities.length > 0 ||
        target.targetMajorGroups.length > 0 ||
        target.preferredRegions.length > 0),
  );
}

function seasonForExam(examType: ExamType): LlmPositionReportData["season"] {
  switch (examType) {
    case "june_mock":
      return { current: "6월", next: "9월", sampleConfidence: "low" };
    case "september_mock":
      return { current: "9월", next: "수능", sampleConfidence: "medium" };
    case "csat":
      return { current: "수능", next: null, sampleConfidence: "high" };
  }
}

// ---------------------------------------------------------------------------
// What-if 시나리오 (§5) — 약점 과목을 올렸을 때 어떤 라인이 열리는지 결정론적 재계산.
// SimulationService와 동일하게 후보 전체에 analyzeUnit을 재실행한다(저장 없음).
// LLM은 이 결과를 만들지 않는다 — 엔진 계산값만 화면/프롬프트에 인용된다(§8.1).
// ---------------------------------------------------------------------------

/** 레버로 고려할 과목 우선순위(결정성) — 반영 비중이 큰 순서 */
const WHATIF_LEVER_ORDER: readonly Subject[] = [
  "math",
  "korean",
  "inquiry1",
  "inquiry2",
  "english",
];

export function buildWhatIfScenarios(args: {
  examScore: ExamScore;
  candidates: readonly AnalysisCandidate[];
  weaknessSubjects: Subject[];
  maxScenarios?: number;
}): LlmPositionReportData["scenarios"] {
  const { examScore, candidates } = args;
  const maxScenarios = args.maxScenarios ?? 3;
  if (candidates.length === 0) return [];

  const baseline = runScenarioEngine(examScore, candidates);
  if (baseline.size === 0) return [];

  const scenarios: LlmPositionReportData["scenarios"] = [];
  const usedUnits = new Set<string>();

  for (const subject of pickLeverSubjects(examScore, args.weaknessSubjects)) {
    if (scenarios.length >= maxScenarios) break;

    const lever = buildImprovementAdjustment(examScore, subject);
    if (!lever) continue;

    const simulatedScore = applyAdjustments(examScore, [lever.adjustment]);
    if (!validateScores(simulatedScore).valid) continue;
    const simulated = runScenarioEngine(simulatedScore, candidates);

    const flip = pickBestFlip(baseline, simulated, usedUnits);
    if (!flip) continue;
    usedUnits.add(flip.unitId);

    scenarios.push({
      lever: lever.label,
      delta: round1(flip.gapDelta),
      unlocks: `${flip.unit.university} ${flip.unit.unitName} ${bandLabel(
        flip.fromBand,
      )}→${bandLabel(flip.toBand)}`,
    });
  }

  return scenarios;
}

/** 후보 전체에 엔진 파이프라인 실행 → unitId별 분석 결과 맵(분석 가능 건만) */
function runScenarioEngine(
  score: ScoreInput,
  candidates: readonly AnalysisCandidate[],
): Map<string, UnitAnalysis> {
  const normalized = normalizeScores(score);
  const byUnit = new Map<string, UnitAnalysis>();
  for (const candidate of candidates) {
    const r = analyzeUnit(candidate, normalized, score.examType);
    if (r.kind === "ok") byUnit.set(r.analysis.unit.unitId, r.analysis);
  }
  return byUnit;
}

/** 레버 후보: 약점 과목 우선, 없으면 반영 과목 중 백분위 최저 1개 */
function pickLeverSubjects(
  examScore: ExamScore,
  weaknessSubjects: Subject[],
): Subject[] {
  const weak = WHATIF_LEVER_ORDER.filter((s) => weaknessSubjects.includes(s));
  if (weak.length > 0) return weak;

  let lowest: { subject: Subject; percentile: number } | null = null;
  for (const score of examScore.scores) {
    if (
      !WHATIF_LEVER_ORDER.includes(score.subject) ||
      score.percentile === undefined
    ) {
      continue;
    }
    if (!lowest || score.percentile < lowest.percentile) {
      lowest = { subject: score.subject, percentile: score.percentile };
    }
  }
  return lowest ? [lowest.subject] : [];
}

/** 과목별 현실적인 상향 조정 1개 + 사람이 읽을 라벨 */
function buildImprovementAdjustment(
  examScore: ExamScore,
  subject: Subject,
): { adjustment: SimulationAdjustment; label: string } | null {
  const score = examScore.scores.find((s) => s.subject === subject);
  if (!score) return null;
  const name = subjectLabel(subject);

  // 백분위 보유 과목: +10p(최대 99) 상향
  if (score.percentile !== undefined && score.percentile < 99) {
    const next = Math.min(99, score.percentile + 10);
    if (next <= score.percentile) return null;
    return {
      adjustment: { subject, override: { percentile: next } },
      label: `${name} 백분위 ${score.percentile}→${next}`,
    };
  }
  // 등급만 보유(영어 등 절대평가): 1등급 상향
  if (score.grade !== undefined && score.grade > 1) {
    const next = score.grade - 1;
    return {
      adjustment: { subject, override: { grade: next } },
      label: `${name} ${score.grade}→${next}등급`,
    };
  }
  return null;
}

/** baseline 대비 구간이 더 유리해진 모집단위 중 대표 1건 선정(결정적) */
function pickBestFlip(
  baseline: Map<string, UnitAnalysis>,
  simulated: Map<string, UnitAnalysis>,
  usedUnits: Set<string>,
): {
  unitId: string;
  unit: UnitAnalysis["unit"];
  fromBand: Band;
  toBand: Band;
  gapDelta: number;
} | null {
  let best: {
    unitId: string;
    unit: UnitAnalysis["unit"];
    fromBand: Band;
    toBand: Band;
    gapDelta: number;
    improvement: number;
  } | null = null;

  for (const unitId of [...baseline.keys()].sort()) {
    if (usedUnits.has(unitId)) continue;
    const before = baseline.get(unitId);
    const after = simulated.get(unitId);
    if (!before || !after) continue;

    const improvement =
      bandFavorability(before.band) - bandFavorability(after.band);
    if (improvement <= 0) continue;

    const candidate = {
      unitId,
      unit: after.unit,
      fromBand: before.band,
      toBand: after.band,
      gapDelta: after.scoreGap - before.scoreGap,
      improvement,
    };
    // 우선순위: 구간 개선폭↑ → 도달 구간이 더 안정적 → gap 개선↑ (동률은 unitId 오름차순 유지)
    if (
      !best ||
      candidate.improvement > best.improvement ||
      (candidate.improvement === best.improvement &&
        bandFavorability(candidate.toBand) < bandFavorability(best.toBand)) ||
      (candidate.improvement === best.improvement &&
        bandFavorability(candidate.toBand) === bandFavorability(best.toBand) &&
        candidate.gapDelta > best.gapDelta)
    ) {
      best = candidate;
    }
  }

  if (!best) return null;
  const { improvement: _improvement, ...flip } = best;
  return flip;
}

function round1(value: number): number {
  return Math.round(value * 10) / 10;
}

function subjectLabel(subject: string): string {
  switch (subject) {
    case "korean":
      return "국어";
    case "math":
      return "수학";
    case "english":
      return "영어";
    case "history":
      return "한국사";
    case "inquiry1":
      return "탐구1";
    case "inquiry2":
      return "탐구2";
    case "second_language":
      return "제2외국어";
    default:
      return subject;
  }
}

function recruitmentGroupLabel(group: UnitAnalysis["unit"]["recruitmentGroup"]): string {
  switch (group) {
    case "ga":
      return "가";
    case "na":
      return "나";
    case "da":
      return "다";
    case "none":
      return "-";
  }
}

function bandLabel(band: Band): string {
  switch (band) {
    case "stable":
      return "안정";
    case "match":
      return "적정";
    case "reach":
      return "소신";
    case "challenge":
      return "도전";
    case "risk":
      return "위험";
  }
}

function reliabilityLabel(
  confidence: UnitAnalysis["confidence"],
): LlmPositionReportData["lines"][number]["reliability"] {
  switch (confidence) {
    case "high":
      return "high";
    case "medium":
      return "mid";
    case "low":
      return "low";
    case "limited":
      return "limited";
  }
}

/** TrendAnalysis → §11.2 trend 요약 — 숫자만 전달, 해석은 LLM의 몫(§8.1) */
function toLlmTrend(trend: TrendAnalysis): LlmTrendSummary {
  return {
    prevExamType: trend.prevExamType,
    improvedSubjects: trend.improvedSubjects,
    declinedSubjects: trend.declinedSubjects,
    subjectDeltas: trend.subjects.map((s) => ({
      subject: s.subject,
      metric: s.metric,
      prev: s.prev,
      curr: s.curr,
      delta: s.delta,
    })),
    enteredCount: trend.enteredUnits.length,
    droppedCount: trend.droppedUnits.length,
    bandImprovedCount: trend.bandImprovedCount,
    bandDeclinedCount: trend.bandDeclinedCount,
    targetApproach: {
      prev: trend.targetApproach.prev,
      curr: trend.targetApproach.curr,
      direction: trend.targetApproach.direction,
    },
  };
}

/**
 * CrossValidationSummary → §11.2 교차검증 요약.
 * 불일치(disagree) → near → agree → uncertain 순으로 최대 10건만 — 프롬프트 비대 방지.
 * 동순위는 대학명·학과명 사전순(결정성).
 */
const AGREEMENT_PRIORITY: Record<CrossAgreement, number> = {
  disagree: 0,
  near: 1,
  agree: 2,
  uncertain: 3,
};

function toLlmComparison(
  summary: CrossValidationSummary,
): LlmCompetitorComparison {
  const items = [...summary.items]
    .sort(
      (a, b) =>
        AGREEMENT_PRIORITY[a.agreement] - AGREEMENT_PRIORITY[b.agreement] ||
        (a.unit?.university ?? "").localeCompare(b.unit?.university ?? "") ||
        (a.unit?.unitName ?? "").localeCompare(b.unit?.unitName ?? ""),
    )
    .slice(0, 10)
    .map((item) => ({
      university: item.unit?.university ?? "(분석 결과 없음)",
      unitName: item.unit?.unitName ?? "",
      provider: item.provider,
      valueType: item.valueType,
      value: item.value,
      internalBand: item.internalBand,
      externalBand: item.externalBand,
      agreement: item.agreement,
    }));
  return { totals: summary.totals, items };
}

/** 시험 시점·확정 상태에 따른 고지 (§11.2 warnings) — 단정 금지 표현만 사용 */
function examWarnings(examScore: ExamScore): string[] {
  switch (examScore.examType) {
    case "june_mock":
      return ["본 결과는 6월 모의평가 기준이며, 실제 수능 결과와 다를 수 있습니다."];
    case "september_mock":
      return ["본 결과는 9월 모의평가 기준이며, 실제 수능 결과와 다를 수 있습니다."];
    case "csat":
      return examScore.scoreStatus === "estimated"
        ? ["가채점 기준 분석으로, 실채점 결과에 따라 달라질 수 있습니다."]
        : ["전년도 입결 기준 분석으로, 올해 지원 표본에 따라 변동 가능성이 있습니다."];
  }
}
