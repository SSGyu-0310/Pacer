import { describe, expect, it } from "vitest";
import type {
  Cycle,
  ExamScore,
  TargetSnapshot,
  UnitAnalysis,
} from "../../domain/entities";
import type { LlmReportInput, ReportContent } from "../../domain/report";
import { baseScores } from "../../engine/__tests__/fixtures";
import type {
  AnalysisRepository,
  CycleRepository,
  LlmReporter,
  ReportRepository,
  ScoreRepository,
  TargetRepository,
} from "../../ports";
import { ReportService, buildLlmInput } from "../report.service";

const cycle: Cycle = {
  id: "cy-1",
  userId: null,
  anonSessionId: "anon-1",
  admissionYear: 2027,
  gradeStatus: "high3",
  track: "natural",
};
const examScore: ExamScore = { ...baseScores(), id: "es-1", cycleId: "cy-1" };

function result(
  unitId: string,
  university: string,
  band: UnitAnalysis["band"],
  codes: UnitAnalysis["reasonCodes"] = [],
  warns: UnitAnalysis["warnings"] = [],
): UnitAnalysis {
  return {
    unit: { unitId, university, unitName: `${unitId}-m`, recruitmentGroup: "ga" },
    convertedScore: 500,
    historicalReferenceScore: 495,
    scoreGap: 5,
    band,
    confidence: "high",
    reasonCodes: codes,
    warnings: warns,
  };
}

const results: UnitAnalysis[] = [
  result("u1", "연세대", "reach", ["math_weight_advantage"], ["english_penalty_risk"]),
  result("u2", "중앙대", "match", ["math_weight_advantage", "standard_score_fit"]),
  result("u3", "한양대", "stable", ["math_weight_advantage"]),
];

const target: TargetSnapshot = {
  cycleId: "cy-1",
  examType: "june_mock",
  targetUniversities: ["연세대", "중앙대"],
  targetMajorGroups: [],
  preferredRegions: [],
  riskProfile: "aggressive",
  susiJungsiPreference: "jungsi",
};

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
  capture: { input?: LlmReportInput; saved?: unknown },
  snapshotMeta = { cycleId: "cy-1", examScoreId: "es-1" },
  reportCycleId = "cy-1",
) {
  const cycles: CycleRepository = {
    create: () => Promise.reject(new Error("unused")),
    findByAnonSessionAndYear: () => Promise.resolve(null),
    findByUserAndYear: () => Promise.resolve(null),
    mergeAnonToUser: () => Promise.resolve(null),
    updateProfile: () => Promise.reject(new Error("unused")),
    findById: (id) => Promise.resolve(id === "cy-1" ? cycle : null),
  };
  const scores: ScoreRepository = {
    save: () => Promise.reject(new Error("unused")),
    findById: (id) => Promise.resolve(id === "es-1" ? examScore : null),
    findByExamType: () => Promise.resolve(null),
  };
  const targets: TargetRepository = {
    save: () => Promise.resolve(),
    findLatest: () => Promise.resolve(target),
  };
  const analyses: AnalysisRepository = {
    saveSnapshot: () => Promise.reject(new Error("unused")),
    findSnapshotMeta: (id) =>
      Promise.resolve(
        id === "snap-1"
          ? {
              id,
              cycleId: snapshotMeta.cycleId,
              examScoreId: snapshotMeta.examScoreId,
              snapshotType: "june_position" as const,
            }
          : null,
      ),
    findResults: (id) => Promise.resolve(id === "snap-1" ? results : null),
    findLatestSnapshotMeta: () => Promise.resolve(null),
  };
  const llm: LlmReporter = {
    generate: (input) => {
      capture.input = input;
      return Promise.resolve({
        content,
        modelName: "stub",
        promptVersion: "v1",
      });
    },
  };
  const reports: ReportRepository = {
    save: (input) => {
      capture.saved = input;
      return Promise.resolve({ reportId: "rep-1" });
    },
    findById: (id) =>
      Promise.resolve(
        id === "rep-1"
          ? {
              id,
              cycleId: reportCycleId,
              examScoreId: "es-1",
              reportType: "june_position_report",
              content,
              modelName: "stub",
              promptVersion: "v1",
              createdAt: new Date("2026-06-06T00:00:00.000Z"),
            }
          : null,
      ),
    findLatestForCycle: (cycleId) =>
      Promise.resolve(
        cycleId === "cy-1"
          ? {
              id: "rep-1",
              cycleId,
              examScoreId: "es-1",
              reportType: "june_position_report",
              content,
              modelName: "stub",
              promptVersion: "v1",
              createdAt: new Date("2026-06-06T00:00:00.000Z"),
            }
          : null,
      ),
  };
  return new ReportService(cycles, scores, targets, analyses, llm, reports);
}

describe("ReportService.generate (§11)", () => {
  const args = {
    cycleId: "cy-1",
    examScoreId: "es-1",
    analysisSnapshotId: "snap-1",
    reportType: "june_position_report" as const,
  };

  it("LLM 입력(§11.2)을 엔진 결과로 조립한다 — 계산 위임 없음", async () => {
    const capture: { input?: LlmReportInput } = {};
    await makeService(capture).generate(args);
    const i = capture.input!;
    expect(i.userContext).toEqual({
      role: "student",
      examType: "june_mock",
      gradeStatus: "high3",
      riskProfile: "aggressive",
    });
    expect(i.analysisSummary.bandDistribution).toEqual({
      stable: 1,
      match: 1,
      reach: 1,
      challenge: 0,
      risk: 0,
    });
    // 빈도순: math_weight_advantage(3) → 나머지 동률 사전순
    expect(i.analysisSummary.topReasonCodes[0]).toBe("math_weight_advantage");
    expect(i.targetSummary.targetUniversities).toEqual(["연세대", "중앙대"]);
    // 목표 대학(연세대 reach, 중앙대 match) 중 가장 유리한 구간
    expect(i.targetSummary.targetDistance).toBe("match");
    expect(i.warnings).toHaveLength(1);
  });

  it("리포트를 model_name/prompt_version과 함께 저장한다 (§9.13)", async () => {
    const capture: { saved?: unknown } = {};
    const r = await makeService(capture).generate(args);
    expect(r.reportId).toBe("rep-1");
    expect(r.content).toEqual(content);
    expect(capture.saved).toEqual({
      cycleId: "cy-1",
      examScoreId: "es-1",
      reportType: "june_position_report",
      content,
      modelName: "stub",
      promptVersion: "v1",
    });
  });

  it("report_type ↔ exam_type 불일치 → ValidationError", async () => {
    await expect(
      makeService({}).generate({ ...args, reportType: "csat_final_report" }),
    ).rejects.toThrow("일치하지 않습니다");
  });

  it("학부모 리포트는 role=parent (§7.9)", async () => {
    const capture: { input?: LlmReportInput } = {};
    await makeService(capture).generate({
      ...args,
      reportType: "parent_summary_report",
    });
    expect(capture.input!.userContext.role).toBe("parent");
  });

  it("없는 스냅샷 → NotFoundError", async () => {
    await expect(
      makeService({}).generate({ ...args, analysisSnapshotId: "snap-x" }),
    ).rejects.toThrow("Not found");
  });

  it("다른 cycle/examScore의 스냅샷이면 NotFoundError", async () => {
    await expect(
      makeService({}, { cycleId: "cy-other", examScoreId: "es-1" }).generate(args),
    ).rejects.toThrow("Not found");
    await expect(
      makeService({}, { cycleId: "cy-1", examScoreId: "es-other" }).generate(args),
    ).rejects.toThrow("Not found");
  });

  it("저장된 리포트 조회도 cycle 불일치면 NotFoundError", async () => {
    await expect(makeService({}).getReport("cy-1", "rep-1")).resolves.toMatchObject({
      id: "rep-1",
      cycleId: "cy-1",
    });
    await expect(
      makeService({}, { cycleId: "cy-1", examScoreId: "es-1" }, "cy-other").getReport(
        "cy-1",
        "rep-1",
      ),
    ).rejects.toThrow("Not found");
  });
});

describe("buildLlmInput 결정성", () => {
  it("같은 입력 = 같은 출력", () => {
    const a = buildLlmInput({
      reportType: "june_position_report",
      gradeStatus: "high3",
      examScore,
      target,
      results,
    });
    const b = buildLlmInput({
      reportType: "june_position_report",
      gradeStatus: "high3",
      examScore,
      target,
      results,
    });
    expect(a).toEqual(b);
  });
});
