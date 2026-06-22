import { describe, expect, it } from "vitest";
import { normalizeScores } from "../normalize";
import { baseScores } from "./fixtures";

describe("normalizeScores (§8.1-2)", () => {
  it("과목 맵을 구성한다", () => {
    const n = normalizeScores(baseScores());
    expect(n.bySubject.get("korean")?.standardScore).toBe(131);
    expect(n.bySubject.get("math")?.selection).toBe("미적분");
  });

  it("백분위 평균 대비 강·약점을 도출한다 (평균 93.25 → 수학 96 강점, 탐구2 90 약점)", () => {
    const n = normalizeScores(baseScores());
    expect(n.strengthSubjects).toContain("math");
    expect(n.weaknessSubjects).toContain("inquiry2");
    expect(n.strengthSubjects).not.toContain("korean");
  });

  it("영어 1등급은 강점, 4등급 이하는 약점", () => {
    const good = baseScores();
    good.scores[2]!.grade = 1;
    expect(normalizeScores(good).strengthSubjects).toContain("english");

    const bad = baseScores();
    bad.scores[2]!.grade = 4;
    expect(normalizeScores(bad).weaknessSubjects).toContain("english");
  });

  it("영어 2~3등급은 강·약점 어느 쪽도 아니다", () => {
    const n = normalizeScores(baseScores()); // 영어 2등급
    expect(n.strengthSubjects).not.toContain("english");
    expect(n.weaknessSubjects).not.toContain("english");
  });

  it("백분위가 1과목뿐이면 상대 강·약점을 내지 않는다", () => {
    const input = baseScores();
    input.scores = [
      { subject: "korean", percentile: 93 },
      { subject: "english", grade: 2 },
      { subject: "history", grade: 3 },
    ];
    const n = normalizeScores(input);
    expect(n.strengthSubjects).toEqual([]);
    expect(n.weaknessSubjects).toEqual([]);
  });

  it("결정성: 같은 입력 = 같은 출력", () => {
    const a = normalizeScores(baseScores());
    const b = normalizeScores(baseScores());
    expect(a.strengthSubjects).toEqual(b.strengthSubjects);
    expect(a.weaknessSubjects).toEqual(b.weaknessSubjects);
  });
});
