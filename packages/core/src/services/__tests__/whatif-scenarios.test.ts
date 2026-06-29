import { describe, expect, it } from "vitest";
import type { AnalysisCandidate, ExamScore } from "../../domain/entities";
import { baseScores, historicalRef } from "../../engine/__tests__/fixtures";
import { buildWhatIfScenarios } from "../report.service";

const examScore: ExamScore = { ...baseScores(), id: "es-1", cycleId: "cy-1" };

/**
 * 규칙 없는(백분위 평균) 후보 — 손계산이 쉽다.
 * 기준 백분위 평균 = (국93+수96+탐194+탐290)/4 = 93.25.
 * 컷 94 → gap −0.75, 6모 보정 −0.3 → −1.05 = 소신(reach).
 * 탐구2 90→99 상향 시 평균 95.5 → gap 1.5, 보정 후 1.2 = 적정(match).
 */
function reachCandidate(): AnalysisCandidate {
  return {
    unit: {
      unitId: "u-flip",
      university: "테스트대",
      unitName: "샘플과",
      recruitmentGroup: "ga",
    },
    rule: null,
    historical: historicalRef({ unitId: "u-flip", percentileCut: 94 }),
    quota: 50,
    prevQuota: null,
  };
}

describe("buildWhatIfScenarios (§5 what-if)", () => {
  it("후보가 없으면 빈 배열", () => {
    expect(
      buildWhatIfScenarios({
        examScore,
        candidates: [],
        weaknessSubjects: ["inquiry2"],
      }),
    ).toEqual([]);
  });

  it("약점 과목을 올리면 구간이 열리는 라인을 시나리오로 만든다", () => {
    const scenarios = buildWhatIfScenarios({
      examScore,
      candidates: [reachCandidate()],
      weaknessSubjects: ["inquiry2"],
    });

    expect(scenarios).toHaveLength(1);
    const [s] = scenarios;
    expect(s?.lever).toBe("탐구2 백분위 90→99");
    expect(s?.unlocks).toBe("테스트대 샘플과 소신→적정");
    expect(s?.delta).toBeGreaterThan(0);
  });

  it("구간 변화가 없으면 시나리오를 만들지 않는다", () => {
    // 이미 안정권(컷 80)이면 상향해도 더 유리한 구간으로 갈 곳이 없다.
    const scenarios = buildWhatIfScenarios({
      examScore,
      candidates: [
        {
          ...reachCandidate(),
          historical: historicalRef({ unitId: "u-flip", percentileCut: 80 }),
        },
      ],
      weaknessSubjects: ["inquiry2"],
    });
    expect(scenarios).toEqual([]);
  });

  it("결정적이다 — 같은 입력은 같은 출력", () => {
    const args = {
      examScore,
      candidates: [reachCandidate()],
      weaknessSubjects: ["inquiry2" as const],
    };
    expect(buildWhatIfScenarios(args)).toEqual(buildWhatIfScenarios(args));
  });
});
