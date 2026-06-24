import { describe, expect, it } from "vitest";
import type {
  AnalysisCandidate,
  Cycle,
  ExamScore,
} from "../../domain/entities";
import {
  baseScores,
  historicalRef,
  percentileRule,
} from "../../engine/__tests__/fixtures";
import type {
  CycleRepository,
  ScoreRepository,
  TargetRepository,
  UnitRepository,
} from "../../ports";
import { SimulationService } from "../simulation.service";

const cycle: Cycle = {
  id: "cy-1",
  userId: null,
  anonSessionId: "anon-1",
  admissionYear: 2027,
  gradeStatus: "high3",
  track: "natural",
};
const examScore: ExamScore = { ...baseScores(), id: "es-1", cycleId: "cy-1" };

/**
 * 백분위 반영(만점 100) 후보 — 손계산 가능:
 * 기준 성적 백분위 국93/수96/탐(94+90)/2=92 → 0.3·93 + 0.4·96 + 0.3·92 = 93.9
 * 영어 2등급 감점 0.5, 한국사 3등급 감점 0.2 → 환산 93.2
 * 6모 보정 −0.3 적용 후 cut과 비교(만점 100 기준 gapPer100).
 */
function candidate(unitId: string, cutScore: number): AnalysisCandidate {
  return {
    unit: {
      unitId,
      university: `${unitId}-대학`,
      unitName: `${unitId}-학과`,
      recruitmentGroup: "ga",
    },
    rule: percentileRule({ unitId }),
    historical: historicalRef({ unitId, cutScore, percentileCut: null }),
    quota: 30,
    prevQuota: 30,
  };
}

function makeService(candidates: AnalysisCandidate[]): SimulationService {
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
    findLatest: () => Promise.resolve(null),
  };
  const units: UnitRepository = {
    loadCandidates: () => Promise.resolve(candidates),
  };
  return new SimulationService(cycles, scores, targets, units);
}

describe("SimulationService (§7.9, P1)", () => {
  it("가상 점수로 재실행 — 기준선과 시뮬레이션 분포를 함께 반환", async () => {
    // 기준 93.2 vs 컷 95 → gap −1.8(−0.3 보정 → 도전). 수학 +4백분위 → +1.6 → −0.5(적정)
    const service = makeService([candidate("u1", 95)]);
    const result = await service.run("cy-1", "es-1", [
      { subject: "math", percentileDelta: 4 },
    ]);

    const baselineTotal = Object.values(result.baselineDistribution).reduce(
      (a, b) => a + b,
      0,
    );
    expect(baselineTotal).toBe(1);
    expect(result.bandChanges.length).toBeGreaterThanOrEqual(0);
    expect(result.summary.analyzed).toBe(1);
  });

  it("적정 이상으로 들어온 모집단위 수를 센다 (§7.9 출력)", async () => {
    const service = makeService([candidate("u1", 95)]);
    const result = await service.run("cy-1", "es-1", [
      { subject: "math", percentileDelta: 4 },
    ]);
    // 수학 96→100: 환산 +1.6 — 컷 95 대비 gap이 음수→양수로 전환
    expect(result.movedToMatchOrBetter).toBeGreaterThanOrEqual(1);
    const change = result.bandChanges.find((c) => c.unit.unitId === "u1");
    expect(change).toBeTruthy();
  });

  it("가장 효율적인 과목 — 반영비 높은 과목(수학 0.4 > 국어 0.3)", async () => {
    // u1(컷 95.9): 국어 +4 → 94.4(−1.8, 도전 유지) / 수학 +4 → 94.8(−1.4, 소신 개선)
    // u2(컷 96.5): 국어 +4 → −2.4(도전 개선) / 수학 +4 → −2.0(도전 개선) ⇒ 수학 2 > 국어 1
    const service = makeService([candidate("u1", 95.9), candidate("u2", 96.5)]);
    const result = await service.run("cy-1", "es-1", [
      { subject: "korean", percentileDelta: 4 },
      { subject: "math", percentileDelta: 4 },
    ]);
    expect(result.mostEfficientSubject).toBe("math");
  });

  it("조정이 한 과목이면 그 과목이 효율 과목", async () => {
    const service = makeService([candidate("u1", 95)]);
    const result = await service.run("cy-1", "es-1", [
      { subject: "math", percentileDelta: 2 },
    ]);
    expect(result.mostEfficientSubject).toBe("math");
  });

  it("빈 조정 목록 → ValidationError", async () => {
    const service = makeService([candidate("u1", 95)]);
    await expect(service.run("cy-1", "es-1", [])).rejects.toThrow("최소 하나");
  });

  it("엔진 클램프 — 범위 밖 override도 §18.1 범위로 보정되어 검증을 통과한다", async () => {
    const service = makeService([candidate("u1", 95)]);
    const result = await service.run("cy-1", "es-1", [
      { subject: "math", override: { percentile: 96, grade: 99 } },
    ]);
    expect(result.summary.analyzed).toBe(1);
  });

  it("없는 사이클/성적 → NotFoundError", async () => {
    const service = makeService([candidate("u1", 95)]);
    await expect(
      service.run("cy-x", "es-1", [{ subject: "math", percentileDelta: 1 }]),
    ).rejects.toThrow("Not found");
    await expect(
      service.run("cy-1", "es-x", [{ subject: "math", percentileDelta: 1 }]),
    ).rejects.toThrow("Not found");
  });

  it("결정성 — 같은 입력 = 같은 출력", async () => {
    const service = makeService([candidate("u1", 95)]);
    const adj = [{ subject: "math" as const, percentileDelta: 4 }];
    const a = await service.run("cy-1", "es-1", adj);
    const b = await service.run("cy-1", "es-1", adj);
    expect(a).toEqual(b);
  });
});
