import { describe, expect, it } from "vitest";
import type { ConvertedScore } from "../../domain/entities";
import { compareToHistorical } from "../compare";
import { groupByRecruitmentGroup } from "../recruitment";
import { historicalRef } from "./fixtures";

const exact = (score: number): ConvertedScore => ({
  unitId: "unit-std",
  convertedScore: score,
  method: "exact",
  scale: 1000,
  approximations: [],
});

const approx = (score: number): ConvertedScore => ({
  unitId: "unit-std",
  convertedScore: score,
  method: "approx",
  scale: 100,
  approximations: ["percentile_composite"],
});

describe("compareToHistorical (§8.3, §18.1 입결 대비 점수차)", () => {
  it("정확 환산은 환산점수 컷과 비교: 563.5 − 560 = 3.5", () => {
    const r = compareToHistorical(exact(563.5), historicalRef());
    expect(r.historicalReferenceScore).toBe(560);
    expect(r.scoreGap).toBe(3.5);
  });

  it("근사 비교는 백분위 컷과 비교: 93.9 − 92 = 1.9", () => {
    const r = compareToHistorical(approx(93.9), historicalRef());
    expect(r.historicalReferenceScore).toBe(92);
    expect(r.scoreGap).toBe(1.9);
  });

  it("음수 gap도 그대로 계산한다", () => {
    const r = compareToHistorical(exact(555), historicalRef());
    expect(r.scoreGap).toBe(-5);
  });

  it("입결이 없으면 gap = null", () => {
    const r = compareToHistorical(exact(563.5), null);
    expect(r.scoreGap).toBeNull();
    expect(r.historicalReferenceScore).toBeNull();
  });

  it("기준 컷이 없으면 gap = null (정확 환산인데 cutScore 없음)", () => {
    const r = compareToHistorical(
      exact(563.5),
      historicalRef({ cutScore: null }),
    );
    expect(r.scoreGap).toBeNull();
  });

  it("환산 불가면 gap = null", () => {
    const r = compareToHistorical(
      {
        unitId: "u",
        convertedScore: null,
        method: "unsupported",
        scale: null,
        approximations: [],
      },
      historicalRef(),
    );
    expect(r.scoreGap).toBeNull();
  });
});

describe("groupByRecruitmentGroup (§18.1 모집군 분류)", () => {
  it("가/나/다군별로 그룹핑한다", () => {
    const unit = (id: string, group: "ga" | "na" | "da" | "none") => ({
      unit: {
        unitId: id,
        university: "U",
        unitName: id,
        recruitmentGroup: group,
      },
    });
    const groups = groupByRecruitmentGroup([
      unit("a1", "ga"),
      unit("b1", "na"),
      unit("a2", "ga"),
      unit("c1", "da"),
    ]);
    expect(groups.ga.map((x) => x.unit.unitId)).toEqual(["a1", "a2"]);
    expect(groups.na).toHaveLength(1);
    expect(groups.da).toHaveLength(1);
    expect(groups.none).toEqual([]);
  });
});
