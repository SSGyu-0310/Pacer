import { describe, expect, it } from "vitest";
import { applyAdjustments, percentileToGrade } from "../simulate";
import { baseScores } from "./fixtures";

describe("engine.percentileToGrade (9등급제 누적 백분위)", () => {
  it("등급 경계 — §18.1 검증 범위 내 결정적 매핑", () => {
    expect(percentileToGrade(100)).toBe(1);
    expect(percentileToGrade(96)).toBe(1);
    expect(percentileToGrade(95.9)).toBe(2);
    expect(percentileToGrade(89)).toBe(2);
    expect(percentileToGrade(77)).toBe(3);
    expect(percentileToGrade(4)).toBe(8);
    expect(percentileToGrade(0)).toBe(9);
  });
});

describe("engine.applyAdjustments (§7.9, P1)", () => {
  it("delta 적용 — 원본 불변, 대상 과목만 변경", () => {
    const base = baseScores();
    const out = applyAdjustments(base, [
      { subject: "math", percentileDelta: 2, standardScoreDelta: 3 },
    ]);
    const math = out.scores.find((s) => s.subject === "math")!;
    expect(math.percentile).toBe(98); // 96 + 2
    expect(math.standardScore).toBe(138); // 135 + 3
    // 원본 불변
    expect(base.scores.find((s) => s.subject === "math")!.percentile).toBe(96);
    // 다른 과목 불변
    expect(out.scores.find((s) => s.subject === "korean")!.percentile).toBe(93);
  });

  it("절대평가 등급 상승 — gradeDelta 음수", () => {
    const out = applyAdjustments(baseScores(), [
      { subject: "english", gradeDelta: -1 },
    ]);
    expect(out.scores.find((s) => s.subject === "english")!.grade).toBe(1);
  });

  it("클램프 — 범위(§18.1)를 벗어나지 않는다", () => {
    const out = applyAdjustments(baseScores(), [
      { subject: "math", percentileDelta: 50 },
      { subject: "english", gradeDelta: -5 },
    ]);
    expect(out.scores.find((s) => s.subject === "math")!.percentile).toBe(100);
    expect(out.scores.find((s) => s.subject === "english")!.grade).toBe(1);
  });

  it("override(직접 입력) 후 delta가 누적된다", () => {
    const out = applyAdjustments(baseScores(), [
      {
        subject: "korean",
        override: { percentile: 95 },
        percentileDelta: 1,
      },
    ]);
    expect(out.scores.find((s) => s.subject === "korean")!.percentile).toBe(96);
  });

  it("백분위가 바뀐 과목은 등급을 재산출한다(등급 직접 지정 시 제외)", () => {
    const base = baseScores();
    base.scores = base.scores.map((s) =>
      s.subject === "math" ? { ...s, grade: 2 } : s,
    );
    const out = applyAdjustments(base, [{ subject: "math", percentileDelta: 2 }]);
    const math = out.scores.find((s) => s.subject === "math")!;
    expect(math.percentile).toBe(98);
    expect(math.grade).toBe(1); // 98 ≥ 96 → 1등급 재산출

    const explicit = applyAdjustments(base, [
      { subject: "math", percentileDelta: 2, gradeDelta: 0 },
    ]);
    expect(explicit.scores.find((s) => s.subject === "math")!.grade).toBe(2);
  });

  it("없는 지표는 만들어내지 않는다 — 영어에 percentileDelta를 줘도 무시", () => {
    const out = applyAdjustments(baseScores(), [
      { subject: "english", percentileDelta: 3 },
    ]);
    expect(out.scores.find((s) => s.subject === "english")!.percentile).toBeUndefined();
  });

  it("결정성 — 같은 입력 = 같은 출력", () => {
    const adj = [{ subject: "math" as const, percentileDelta: 2 }];
    expect(applyAdjustments(baseScores(), adj)).toEqual(
      applyAdjustments(baseScores(), adj),
    );
  });
});
