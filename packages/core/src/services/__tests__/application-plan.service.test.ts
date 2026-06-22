import { describe, expect, it } from "vitest";
import type { Cycle, UnitAnalysis } from "../../domain/entities";
import type {
  AnalysisRepository,
  ApplicationPlanRepository,
  CycleRepository,
} from "../../ports";
import { ApplicationPlanService } from "../application-plan.service";

const cycle: Cycle = {
  id: "cy-1",
  userId: null,
  anonSessionId: "anon-1",
  admissionYear: 2027,
  gradeStatus: "high3",
  track: "natural",
};

function unit(
  unitId: string,
  group: UnitAnalysis["unit"]["recruitmentGroup"],
  band: UnitAnalysis["band"],
): UnitAnalysis {
  return {
    unit: { unitId, university: `${unitId}-대`, unitName: "학과", recruitmentGroup: group },
    convertedScore: 500,
    historicalReferenceScore: 495,
    scoreGap: 5,
    band,
    confidence: "high",
    reasonCodes: [],
    warnings: [],
  };
}

const results = [
  unit("ga-1", "ga", "stable"),
  unit("na-1", "na", "match"),
  unit("da-1", "da", "reach"),
];

function makeService(capture: { saved?: unknown }, hasSnapshot = true) {
  const cycles: CycleRepository = {
    create: () => Promise.reject(new Error("unused")),
    findByAnonSessionAndYear: () => Promise.resolve(null),
    updateProfile: () => Promise.reject(new Error("unused")),
    findById: (id) => Promise.resolve(id === "cy-1" ? cycle : null),
  };
  const analyses: AnalysisRepository = {
    saveSnapshot: () => Promise.reject(new Error("unused")),
    findSnapshotMeta: () => Promise.resolve(null),
    findLatestSnapshotMeta: () =>
      Promise.resolve(
        hasSnapshot
          ? {
              id: "snap-1",
              cycleId: "cy-1",
              examScoreId: "es-1",
              snapshotType: "csat_final" as const,
            }
          : null,
      ),
    findResults: (id) => Promise.resolve(id === "snap-1" ? results : null),
  };
  const plans: ApplicationPlanRepository = {
    save: (input) => {
      capture.saved = input;
      return Promise.resolve({ planId: "plan-1" });
    },
  };
  return new ApplicationPlanService(cycles, analyses, plans);
}

describe("ApplicationPlanService (§10.8, P2)", () => {
  it("최신 분석 결과로 조합 생성·저장 — ga/na/da unit id 기록 (§9.15)", async () => {
    const capture: { saved?: { gaUnitId: string | null } } = {};
    const r = await makeService(capture).create("cy-1", "stable", [
      "ga-1",
      "na-1",
      "da-1",
    ]);
    expect(r.planId).toBe("plan-1");
    expect(r.combination.picks.ga.unit!.unitId).toBe("ga-1");
    expect(capture.saved!.gaUnitId).toBe("ga-1");
    expect(r.skippedUnitIds).toEqual([]);
  });

  it("최신 분석에 없는 후보는 투명하게 skipped로 보고 (§8.2)", async () => {
    const capture: {
      saved?: { combination: { warnings: string[] } };
    } = {};
    const r = await makeService(capture).create("cy-1", "stable", [
      "ga-1",
      "na-1",
      "da-1",
      "u-missing",
    ]);
    expect(r.skippedUnitIds).toEqual(["u-missing"]);
    expect(
      capture.saved!.combination.warnings.some((w) => w.includes("제외된 후보")),
    ).toBeTruthy();
  });

  it("분석 이력 없음 → ValidationError(분석 먼저 실행 안내)", async () => {
    await expect(
      makeService({}, false).create("cy-1", "stable", ["ga-1"]),
    ).rejects.toThrow("분석 이력이 없습니다");
  });

  it("선택 후보가 모두 분석 밖이면 ValidationError", async () => {
    await expect(
      makeService({}).create("cy-1", "stable", ["u-x", "u-y"]),
    ).rejects.toThrow("최신 분석 결과에 없습니다");
  });

  it("빈 후보 목록 → ValidationError", async () => {
    await expect(makeService({}).create("cy-1", "stable", [])).rejects.toThrow(
      "최소 하나",
    );
  });
});
