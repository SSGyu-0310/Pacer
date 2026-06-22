import { describe, expect, it } from "vitest";
import type {
  AnalysisCandidate,
  AnalysisSummary,
  Cycle,
  ExamScore,
  TargetSnapshot,
  UnitAnalysis,
} from "../../domain/entities";
import {
  baseScores,
  historicalRef,
  standardRule,
} from "../../engine/__tests__/fixtures";
import type {
  AnalysisRepository,
  CycleRepository,
  ScoreRepository,
  TargetRepository,
  UnitRepository,
} from "../../ports";
import { AnalysisService } from "../analysis.service";

/* ── 인메모리 fakes ── */

const cycle: Cycle = {
  id: "cy-1",
  userId: null,
  anonSessionId: "anon-1",
  admissionYear: 2027,
  gradeStatus: "high3",
  track: "natural",
};

const examScore: ExamScore = { ...baseScores(), id: "es-1", cycleId: "cy-1" };

const fakeCycles: CycleRepository = {
  create: () => Promise.reject(new Error("unused")),
  findByAnonSessionAndYear: () => Promise.resolve(null),
  updateProfile: () => Promise.reject(new Error("unused")),
  findById: (id) => Promise.resolve(id === "cy-1" ? cycle : null),
};

const fakeScores: ScoreRepository = {
  save: () => Promise.reject(new Error("unused")),
  findById: (id) => Promise.resolve(id === "es-1" ? examScore : null),
  findByExamType: () => Promise.resolve(null),
};

function fakeTargets(target: TargetSnapshot | null): TargetRepository {
  return {
    save: () => Promise.resolve(),
    findLatest: () => Promise.resolve(target),
  };
}

function unit(unitId: string, group: "ga" | "na" | "da" = "ga") {
  return {
    unitId,
    university: `${unitId}-univ`,
    unitName: `${unitId}-major`,
    recruitmentGroup: group,
  };
}

/** 5개 후보: 정상 / 규칙없음 / 자격미달 / 입결없음 / 근사(저신뢰) */
function candidates(): AnalysisCandidate[] {
  return [
    {
      unit: unit("u-ok"),
      rule: standardRule({ unitId: "u-ok" }),
      historical: historicalRef({ unitId: "u-ok" }),
      quota: 50,
      prevQuota: 50,
    },
    {
      unit: unit("u-no-rule", "na"),
      rule: null,
      historical: historicalRef({ unitId: "u-no-rule" }),
      quota: 30,
      prevQuota: null,
    },
    {
      unit: unit("u-ineligible", "na"),
      rule: standardRule({
        unitId: "u-ineligible",
        eligibility: { requiredMathSelections: ["기하"] }, // 픽스처는 미적분
      }),
      historical: historicalRef({ unitId: "u-ineligible" }),
      quota: 40,
      prevQuota: 40,
    },
    {
      unit: unit("u-no-historical", "da"),
      rule: standardRule({ unitId: "u-no-historical" }),
      historical: null,
      quota: 25,
      prevQuota: null,
    },
    {
      unit: unit("u-approx", "da"),
      rule: standardRule({ unitId: "u-approx", verifiedStatus: "parsed" }),
      historical: historicalRef({ unitId: "u-approx" }),
      quota: 60,
      prevQuota: 60,
    },
  ];
}

function fakeUnits(
  list: AnalysisCandidate[],
  capture?: { filter?: unknown },
): UnitRepository {
  return {
    loadCandidates: (filter) => {
      if (capture) capture.filter = filter;
      return Promise.resolve(list);
    },
  };
}

class FakeAnalysisRepo implements AnalysisRepository {
  saved: {
    cycleId: string;
    examScoreId: string;
    snapshotType: string;
    summary: AnalysisSummary;
    bandDistribution: Record<string, number>;
    results: UnitAnalysis[];
  } | null = null;

  saveSnapshot(input: {
    cycleId: string;
    examScoreId: string;
    snapshotType: "june_position" | "september_change" | "csat_final";
    summary: AnalysisSummary;
    bandDistribution: Record<"stable" | "match" | "reach" | "challenge" | "risk", number>;
    results: UnitAnalysis[];
  }): Promise<{ snapshotId: string }> {
    this.saved = input;
    return Promise.resolve({ snapshotId: "snap-1" });
  }

  findSnapshotMeta(snapshotId: string) {
    if (snapshotId !== "snap-1" || !this.saved) return Promise.resolve(null);
    return Promise.resolve({
      id: snapshotId,
      cycleId: this.saved.cycleId,
      examScoreId: this.saved.examScoreId,
      snapshotType: this.saved.snapshotType as
        | "june_position"
        | "september_change"
        | "csat_final",
    });
  }

  findLatestSnapshotMeta() {
    return this.findSnapshotMeta("snap-1");
  }

  findResults(snapshotId: string): Promise<UnitAnalysis[] | null> {
    if (snapshotId !== "snap-1" || !this.saved) return Promise.resolve(null);
    return Promise.resolve(this.saved.results);
  }
}

function makeService(
  repo = new FakeAnalysisRepo(),
  target: TargetSnapshot | null = null,
  capture?: { filter?: unknown },
) {
  return {
    service: new AnalysisService(
      fakeCycles,
      fakeScores,
      fakeTargets(target),
      fakeUnits(candidates(), capture),
      repo,
    ),
    repo,
  };
}

/* ── tests ── */

describe("AnalysisService.run (§17.3)", () => {
  it("후보를 분석하고 요약·구간분포와 함께 스냅샷을 저장한다", async () => {
    const { service, repo } = makeService();
    const r = await service.run("cy-1", "es-1", "june_position");

    expect(r.snapshotId).toBe("snap-1");
    expect(r.summary).toEqual({
      candidates: 5,
      analyzed: 2,
      ineligible: 1,
      unsupported: 1,
      insufficientData: 1,
    });
    const total = Object.values(r.bandDistribution).reduce((a, b) => a + b, 0);
    expect(total).toBe(2);
    expect(repo.saved!.results.map((x) => x.unit.unitId)).toEqual([
      "u-ok",
      "u-approx",
    ]);
  });

  it("정상 후보(u-ok): 정확 환산 563.5, gap 3.5, 6모 보정 → match, 신뢰도 high", async () => {
    const { service, repo } = makeService();
    await service.run("cy-1", "es-1", "june_position");
    const ok = repo.saved!.results.find((x) => x.unit.unitId === "u-ok")!;
    expect(ok.convertedScore).toBe(563.5);
    expect(ok.historicalReferenceScore).toBe(560);
    expect(ok.scoreGap).toBe(3.5);
    expect(ok.band).toBe("match"); // 0.35per100 − 0.3(6모) = 0.05
    expect(ok.confidence).toBe("high");
  });

  it("근사 후보(u-approx): 백분위 합성, 신뢰도 low + low_data_confidence 경고", async () => {
    const { service, repo } = makeService();
    await service.run("cy-1", "es-1", "june_position");
    const ap = repo.saved!.results.find((x) => x.unit.unitId === "u-approx")!;
    expect(ap.convertedScore).toBe(93.9);
    expect(ap.scoreGap).toBe(1.9); // 92 백분위 컷 대비
    expect(ap.confidence).toBe("low");
    expect(ap.warnings).toContain("low_data_confidence");
    expect(ap.band).toBe("match"); // 1.9 − 0.3(6모) − 0.3(저신뢰) = 1.3 < 1.5
  });

  it("목표가 있으면 후보 로드 필터에 반영된다", async () => {
    const capture: { filter?: unknown } = {};
    const { service } = makeService(new FakeAnalysisRepo(), {
      cycleId: "cy-1",
      examType: "june_mock",
      targetUniversities: ["u-ok-univ"],
      targetMajorGroups: [],
      preferredRegions: ["seoul"],
      riskProfile: "balanced",
      susiJungsiPreference: "jungsi",
    }, capture);
    await service.run("cy-1", "es-1", "june_position");
    expect(capture.filter).toEqual({
      admissionYear: 2027,
      track: "natural",
      preferredRegions: ["seoul"],
      targetUniversities: ["u-ok-univ"],
    });
  });

  it("목표가 없어도 분석 가능(익명 퍼널 §2.6)", async () => {
    const capture: { filter?: unknown } = {};
    const { service } = makeService(new FakeAnalysisRepo(), null, capture);
    await service.run("cy-1", "es-1", "june_position");
    expect(capture.filter).toEqual({
      admissionYear: 2027,
      track: "natural",
      preferredRegions: undefined,
      targetUniversities: undefined,
    });
  });

  it("analysis_type과 exam_type 불일치 → ValidationError", async () => {
    const { service } = makeService();
    await expect(
      service.run("cy-1", "es-1", "september_change"),
    ).rejects.toThrow("일치하지 않습니다");
  });

  it("없는 사이클/성적 → NotFoundError", async () => {
    const { service } = makeService();
    await expect(service.run("cy-x", "es-1", "june_position")).rejects.toThrow(
      "Not found",
    );
    await expect(service.run("cy-1", "es-x", "june_position")).rejects.toThrow(
      "Not found",
    );
  });

  it("결정성: 같은 입력으로 두 번 실행해도 같은 결과", async () => {
    const a = makeService();
    const b = makeService();
    await a.service.run("cy-1", "es-1", "june_position");
    await b.service.run("cy-1", "es-1", "june_position");
    expect(a.repo.saved!.results).toEqual(b.repo.saved!.results);
    expect(a.repo.saved!.bandDistribution).toEqual(b.repo.saved!.bandDistribution);
  });
});

describe("AnalysisService.getResults (§10.5)", () => {
  it("저장된 결과를 반환한다", async () => {
    const { service } = makeService();
    await service.run("cy-1", "es-1", "june_position");
    const results = await service.getResults("snap-1");
    expect(results).toHaveLength(2);
  });

  it("없는 스냅샷 → NotFoundError", async () => {
    const { service } = makeService();
    await expect(service.getResults("snap-x")).rejects.toThrow("Not found");
  });

  it("소유권 확인용 스냅샷 메타를 반환한다", async () => {
    const { service } = makeService();
    await service.run("cy-1", "es-1", "june_position");
    await expect(service.getSnapshotMeta("snap-1")).resolves.toMatchObject({
      cycleId: "cy-1",
      examScoreId: "es-1",
    });
  });
});
