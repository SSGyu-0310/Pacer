import type { Band, ExamType, ReportType } from "@pacer/shared";
import type {
  CrossAgreement,
  CrossValidationSummary,
  ExamScore,
  TargetSnapshot,
  TrendAnalysis,
  UnitAnalysis,
} from "../domain/entities";
import type {
  LlmCompetitorComparison,
  LlmReportInput,
  LlmTrendSummary,
  ReportContent,
  StrategyReport,
} from "../domain/report";
import {
  analyzeTrend,
  crossValidate,
  mostFavorableBand,
  normalizeScores,
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
} from "../ports";

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

    const input = buildLlmInput({
      reportType: args.reportType,
      gradeStatus: cycle.gradeStatus,
      examScore,
      target,
      results,
      trend,
      crossValidation,
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
    competitorComparison: crossValidation
      ? toLlmComparison(crossValidation)
      : null,
    warnings: [...examWarnings(examScore), ...extraWarnings],
  };
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
