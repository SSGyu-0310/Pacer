import { describe, expect, it } from "vitest";
import type { UnitAnalysis } from "../../domain/entities";
import { buildApplicationPlan } from "../application-plan";

function unit(
  unitId: string,
  group: UnitAnalysis["unit"]["recruitmentGroup"],
  band: UnitAnalysis["band"],
  scoreGap = 5,
): UnitAnalysis {
  return {
    unit: {
      unitId,
      university: `${unitId}-대학`,
      unitName: `${unitId}-학과`,
      recruitmentGroup: group,
    },
    metricMode: "converted",
    metricLabel: "환산점수",
    cutLabel: "환산점수 컷",
    convertedScore: 500,
    historicalReferenceScore: 495,
    scoreGap,
    band,
    confidence: "high",
    reasonCodes: [],
    warnings: [],
  };
}

/** §11.4 금지어 일부 — 엔진 요약 문구가 단정 표현을 쓰지 않는지 확인용 */
const BANNED = ["합격 보장", "무조건", "100%", "확실히 붙", "쓰면 붙는다"];

describe("engine.buildApplicationPlan (§7.10, P2)", () => {
  const candidates = [
    unit("ga-stable", "ga", "stable"),
    unit("ga-match", "ga", "match"),
    unit("na-match", "na", "match"),
    unit("na-reach", "na", "reach"),
    unit("da-reach", "da", "reach"),
    unit("da-challenge", "da", "challenge"),
  ];

  it("안정형 — 가안정/나적정/다소신 (§7.10 매트릭스)", () => {
    const plan = buildApplicationPlan({ strategy: "stable", candidates });
    expect(plan.picks.ga.unit!.unitId).toBe("ga-stable");
    expect(plan.picks.na.unit!.unitId).toBe("na-match");
    expect(plan.picks.da.unit!.unitId).toBe("da-reach");
    expect(plan.overallRisk).toBe("low");
  });

  it("균형형 — 가적정/나적정/다소신", () => {
    const plan = buildApplicationPlan({ strategy: "balanced", candidates });
    expect(plan.picks.ga.unit!.unitId).toBe("ga-match");
    expect(plan.picks.na.unit!.unitId).toBe("na-match");
    expect(plan.picks.da.unit!.unitId).toBe("da-reach");
  });

  it("공격형 — 가안정/나소신/다도전, 리스크 상향", () => {
    const plan = buildApplicationPlan({ strategy: "aggressive", candidates });
    expect(plan.picks.ga.unit!.unitId).toBe("ga-stable");
    expect(plan.picks.na.unit!.unitId).toBe("na-reach");
    expect(plan.picks.da.unit!.unitId).toBe("da-challenge");
    expect(plan.riskiestGroup).toBe("da");
    expect(plan.mostStableGroup).toBe("ga");
  });

  it("같은 구간에선 score_gap 큰 순 — 동률은 unitId 사전순", () => {
    const pool = [
      unit("ga-a", "ga", "stable", 3),
      unit("ga-b", "ga", "stable", 7),
      unit("na-1", "na", "match"),
      unit("da-1", "da", "reach"),
    ];
    const plan = buildApplicationPlan({ strategy: "stable", candidates: pool });
    expect(plan.picks.ga.unit!.unitId).toBe("ga-b");
  });

  it("목표 구간에 후보가 없으면 보수적(안정 쪽) 인접 구간으로 대체 + 경고", () => {
    const pool = [
      unit("ga-1", "ga", "stable"),
      unit("na-stable", "na", "stable"), // 나군에 match 없음 → stable로 대체
      unit("da-1", "da", "reach"),
    ];
    const plan = buildApplicationPlan({ strategy: "stable", candidates: pool });
    expect(plan.picks.na.unit!.unitId).toBe("na-stable");
    expect(plan.picks.na.fallback).toBeTruthy();
    expect(plan.warnings.some((w) => w.includes("인접 구간"))).toBeTruthy();
  });

  it("군에 후보가 없으면 pick=null + 경고 — 조용히 만들어내지 않는다", () => {
    const pool = [unit("ga-1", "ga", "stable"), unit("na-1", "na", "match")];
    const plan = buildApplicationPlan({ strategy: "stable", candidates: pool });
    expect(plan.picks.da.unit).toBeNull();
    expect(plan.warnings.some((w) => w.includes("다군"))).toBeTruthy();
  });

  it("custom — 군당 1개 이하 그대로 배치, 2개 이상이면 ValidationError", () => {
    const ok = buildApplicationPlan({
      strategy: "custom",
      candidates: [unit("ga-1", "ga", "reach"), unit("na-1", "na", "match")],
    });
    expect(ok.picks.ga.unit!.unitId).toBe("ga-1");
    expect(ok.picks.da.unit).toBeNull();

    expect(() =>
      buildApplicationPlan({
        strategy: "custom",
        candidates: [unit("ga-1", "ga", "reach"), unit("ga-2", "ga", "match")],
      }),
    ).toThrow("1개만");
  });

  it("후보가 아예 없으면 ValidationError", () => {
    expect(() =>
      buildApplicationPlan({ strategy: "stable", candidates: [] }),
    ).toThrow("후보");
  });

  it("요약 문구 — §7.10 금지 표현 없음 + 참고용 고지 포함", () => {
    const plan = buildApplicationPlan({ strategy: "balanced", candidates });
    for (const banned of BANNED) {
      expect(plan.summary.includes(banned)).toBeFalsy();
    }
    expect(plan.summary).toContain("리스크 분산");
    expect(plan.summary).toContain("참고용");
  });

  it("결정성 — 같은 입력 = 같은 출력", () => {
    expect(buildApplicationPlan({ strategy: "stable", candidates })).toEqual(
      buildApplicationPlan({ strategy: "stable", candidates }),
    );
  });
});
