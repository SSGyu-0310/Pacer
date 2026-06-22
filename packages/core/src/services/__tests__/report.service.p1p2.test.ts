import { describe, expect, it } from "vitest";
import type {
  CompetitorSignal,
  Cycle,
  ExamScore,
  UnitAnalysis,
} from "../../domain/entities";
import type { LlmReportInput, ReportContent } from "../../domain/report";
import { baseScores } from "../../engine/__tests__/fixtures";
import type {
  AnalysisRepository,
  CompetitorSignalRepository,
  CycleRepository,
  LlmReporter,
  ReportRepository,
  ScoreRepository,
  TargetRepository,
} from "../../ports";
import { ReportService } from "../report.service";

/* ── 공통 픽스처: 6모(es-jun/snap-jun) + 9모(es-sep/snap-sep) ── */

const cycle: Cycle = {
  id: "cy-1",
  userId: null,
  anonSessionId: "anon-1",
  admissionYear: 2027,
  gradeStatus: "high3",
  track: "natural",
};

const juneScore: ExamScore = { ...baseScores(), id: "es-jun", cycleId: "cy-1" };

function septemberScore(): ExamScore {
  const s: ExamScore = {
    ...baseScores(),
    id: "es-sep",
    cycleId: "cy-1",
    examType: "september_mock",
  };
  s.scores = s.scores.map((sc) =>
    sc.subject === "math" ? { ...sc, percentile: 98 } : sc,
  );
  return s;
}

function unit(unitId: string, band: UnitAnalysis["band"]): UnitAnalysis {
  return {
    unit: { unitId, university: "한양대", unitName: `${unitId}-학과`, recruitmentGroup: "ga" },
    convertedScore: 500,
    historicalReferenceScore: 495,
    scoreGap: 5,
    band,
    confidence: "high",
    reasonCodes: [],
    warnings: [],
  };
}

const juneResults = [unit("u1", "reach"), unit("u2", "match")];
const septResults = [unit("u1", "match"), unit("u3", "reach")];

const content: ReportContent = {
  oneLineSummary: "요약",
  studentSummary: "학생 요약",
  parentSummary: "학부모 요약",
  strengths: [],
  weaknesses: [],
  recommendedActions: [],
  warnings: ["면책"],
  nextCta: "다음",
};

function makeService(
  capture: { input?: LlmReportInput },
  opts: { june?: boolean; signals?: CompetitorSignal[] } = {},
): ReportService {
  const { june = true, signals = [] } = opts;

  const cycles: CycleRepository = {
    create: () => Promise.reject(new Error("unused")),
    findByAnonSessionAndYear: () => Promise.resolve(null),
    updateProfile: () => Promise.reject(new Error("unused")),
    findById: (id) => Promise.resolve(id === "cy-1" ? cycle : null),
  };
  const scores: ScoreRepository = {
    save: () => Promise.reject(new Error("unused")),
    findById: (id) => {
      if (id === "es-sep") return Promise.resolve(septemberScore());
      if (id === "es-jun") return Promise.resolve(juneScore);
      return Promise.resolve(null);
    },
    findByExamType: (_cycleId, examType) =>
      Promise.resolve(june && examType === "june_mock" ? juneScore : null),
  };
  const targets: TargetRepository = {
    save: () => Promise.resolve(),
    findLatest: () => Promise.resolve(null),
  };
  const analyses: AnalysisRepository = {
    saveSnapshot: () => Promise.reject(new Error("unused")),
    findSnapshotMeta: (id) => {
      if (id === "snap-sep") {
        return Promise.resolve({
          id,
          cycleId: "cy-1",
          examScoreId: "es-sep",
          snapshotType: "september_change" as const,
        });
      }
      return Promise.resolve(null);
    },
    findLatestSnapshotMeta: (_cycleId, snapshotType) =>
      Promise.resolve(
        june && snapshotType === "june_position"
          ? {
              id: "snap-jun",
              cycleId: "cy-1",
              examScoreId: "es-jun",
              snapshotType: "june_position" as const,
            }
          : null,
      ),
    findResults: (id) => {
      if (id === "snap-sep") return Promise.resolve(septResults);
      if (id === "snap-jun") return Promise.resolve(june ? juneResults : null);
      return Promise.resolve(null);
    },
  };
  const llm: LlmReporter = {
    generate: (input) => {
      capture.input = input;
      return Promise.resolve({ content, modelName: "stub", promptVersion: "v1" });
    },
  };
  const reports: ReportRepository = {
    save: () => Promise.resolve({ reportId: "rep-1" }),
    findById: () => Promise.resolve(null),
    findLatestForCycle: () => Promise.resolve(null),
  };
  const competitorSignals: CompetitorSignalRepository = {
    save: () => Promise.reject(new Error("unused")),
    list: () => Promise.resolve(signals),
  };
  return new ReportService(
    cycles,
    scores,
    targets,
    analyses,
    llm,
    reports,
    competitorSignals,
  );
}

const sepArgs = {
  cycleId: "cy-1",
  examScoreId: "es-sep",
  analysisSnapshotId: "snap-sep",
  reportType: "september_change_report" as const,
};

describe("ReportService — september_change_report (§7.7.2, P1)", () => {
  it("6모 기록이 있으면 trend를 LLM 입력에 채운다 — 수치만, 계산 위임 없음", async () => {
    const capture: { input?: LlmReportInput } = {};
    await makeService(capture).generate(sepArgs);

    const trend = capture.input!.scoreSummary.trend!;
    expect(trend.prevExamType).toBe("june_mock");
    expect(trend.improvedSubjects).toContain("math"); // 96 → 98
    expect(trend.enteredCount).toBe(1); // u3
    expect(trend.droppedCount).toBe(1); // u2
    expect(trend.bandImprovedCount).toBe(1); // u1 reach→match
    expect(trend.targetApproach.direction).toBe("unchanged"); // 최유리 match 유지
  });

  it("6모 기록이 없으면 trend=null + 고지 warning 추가 (§5.2 신규 유저)", async () => {
    const capture: { input?: LlmReportInput } = {};
    await makeService(capture, { june: false }).generate(sepArgs);

    expect(capture.input!.scoreSummary.trend).toBeNull();
    expect(
      capture.input!.warnings.some((w) => w.includes("6월 모의평가 기록이 없어")),
    ).toBeTruthy();
  });
});

describe("ReportService — cross_validation_report (§7.7.4, P2)", () => {
  const crossArgs = { ...sepArgs, reportType: "cross_validation_report" as const };

  const signal: CompetitorSignal = {
    id: "sig-1",
    cycleId: "cy-1",
    examType: "september_mock",
    provider: "jinhak",
    unitId: "u1",
    valueType: "kansu",
    value: "5",
  };

  it("입력 신호가 있으면 competitorComparison을 채운다", async () => {
    const capture: { input?: LlmReportInput } = {};
    await makeService(capture, { signals: [signal] }).generate(crossArgs);

    const c = capture.input!.competitorComparison!;
    expect(c.totals.agree).toBe(1); // u1 match vs 칸수5(match)
    expect(c.items[0]!.provider).toBe("jinhak");
    expect(c.items[0]!.internalBand).toBe("match");
  });

  it("입력 신호가 없으면 ValidationError — 수동 입력 안내 (§7.7.4)", async () => {
    await expect(makeService({}).generate(crossArgs)).rejects.toThrow(
      "외부 도구 결과가 없습니다",
    );
  });
});
