import { describe, expect, it } from "vitest";
import type { ExamScore, UnitAnalysis } from "../../domain/entities";
import { analyzeTrend, mostFavorableBand } from "../trend";
import { baseScores } from "./fixtures";

function exam(over: Partial<ExamScore> = {}): ExamScore {
  return { ...baseScores(), id: "es", cycleId: "cy", ...over };
}

function unit(
  unitId: string,
  band: UnitAnalysis["band"],
  university = "한양대",
): UnitAnalysis {
  return {
    unit: { unitId, university, unitName: `${unitId}-학과`, recruitmentGroup: "ga" },
    convertedScore: 500,
    historicalReferenceScore: 495,
    scoreGap: 5,
    band,
    confidence: "high",
    reasonCodes: [],
    warnings: [],
  };
}

/** 9모 성적: 수학 백분위 96→98 상승, 영어 2→3등급 하락 */
function septScores(): ExamScore {
  const s = exam({ examType: "september_mock" });
  s.scores = s.scores.map((sc) => {
    if (sc.subject === "math") return { ...sc, percentile: 98 };
    if (sc.subject === "english") return { ...sc, grade: 3 };
    return sc;
  });
  return s;
}

describe("engine.analyzeTrend (§7.7.2, P1)", () => {
  const prev = { examScore: exam(), results: [unit("u1", "reach"), unit("u2", "match")] };
  const curr = {
    examScore: septScores(),
    results: [unit("u1", "match"), unit("u3", "reach")],
  };

  it("과목별 상승/하락 — 백분위 우선, 등급은 방향 반전", () => {
    const t = analyzeTrend(prev, curr);
    const math = t.subjects.find((s) => s.subject === "math")!;
    expect(math.metric).toBe("percentile");
    expect(math.delta).toBe(2);
    expect(math.direction).toBe("improved");

    const english = t.subjects.find((s) => s.subject === "english")!;
    expect(english.metric).toBe("grade");
    expect(english.delta).toBe(1); // 2 → 3등급
    expect(english.direction).toBe("declined");

    expect(t.improvedSubjects).toContain("math");
    expect(t.declinedSubjects).toContain("english");
  });

  it("구간 전이 — 개선/새 후보/빠진 후보를 구분한다", () => {
    const t = analyzeTrend(prev, curr);
    const u1 = t.transitions.find((x) => x.unit.unitId === "u1")!;
    expect(u1.kind).toBe("improved"); // reach → match
    expect(t.enteredUnits.map((u) => u.unitId)).toEqual(["u3"]);
    expect(t.droppedUnits.map((u) => u.unitId)).toEqual(["u2"]);
    expect(t.bandImprovedCount).toBe(1);
    expect(t.bandDeclinedCount).toBe(0);
  });

  it("목표 접근도 변화 — 가장 유리한 구간 비교", () => {
    const t = analyzeTrend(prev, curr);
    // prev 최유리 match, curr 최유리 match → unchanged
    expect(t.targetApproach.direction).toBe("unchanged");

    const t2 = analyzeTrend(
      { ...prev, results: [unit("u1", "reach")] },
      { ...curr, results: [unit("u1", "match")] },
    );
    expect(t2.targetApproach.prev).toBe("reach");
    expect(t2.targetApproach.curr).toBe("match");
    expect(t2.targetApproach.direction).toBe("improved");
  });

  it("결과 없음 → 접근도 limited", () => {
    const t = analyzeTrend({ ...prev, results: [] }, { ...curr, results: [] });
    expect(t.targetApproach.prev).toBe("limited");
    expect(t.targetApproach.curr).toBe("limited");
  });

  it("결정성 — 같은 입력 = 같은 출력", () => {
    expect(analyzeTrend(prev, curr)).toEqual(analyzeTrend(prev, curr));
  });
});

describe("engine.mostFavorableBand", () => {
  it("목표 대학이 있으면 그 안에서, 없으면 전체에서 가장 유리한 구간", () => {
    const results = [unit("u1", "stable", "한양대"), unit("u2", "reach", "연세대")];
    expect(mostFavorableBand(results, ["연세대"])).toBe("reach");
    expect(mostFavorableBand(results, [])).toBe("stable");
    expect(mostFavorableBand([], [])).toBe("limited");
  });
});
