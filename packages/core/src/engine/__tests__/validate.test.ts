import { describe, expect, it } from "vitest";
import { validateScores } from "../validate";
import { baseScores } from "./fixtures";

describe("validateScores (§8.1-1, §18.1)", () => {
  it("정상 입력은 valid", () => {
    const r = validateScores(baseScores());
    expect(r.valid).toBe(true);
    expect(r.errors).toEqual([]);
    expect(r.warnings).toEqual([]);
  });

  it("표준점수 범위(0–200) 위반은 오류", () => {
    const input = baseScores();
    input.scores[0]!.standardScore = 250;
    const r = validateScores(input);
    expect(r.valid).toBe(false);
    expect(r.errors.some((e) => e.includes("표준점수"))).toBe(true);
  });

  it("백분위 범위(0–100) 위반은 오류", () => {
    const input = baseScores();
    input.scores[1]!.percentile = 105;
    expect(validateScores(input).valid).toBe(false);
  });

  it("등급 범위(1–9) 위반은 오류", () => {
    const input = baseScores();
    input.scores[2]!.grade = 0;
    expect(validateScores(input).valid).toBe(false);
  });

  it("영어는 등급 필수", () => {
    const input = baseScores();
    input.scores[2] = { subject: "english" };
    const r = validateScores(input);
    expect(r.valid).toBe(false);
    expect(r.errors.some((e) => e.includes("등급 누락"))).toBe(true);
  });

  it("필수 과목(국어) 누락은 오류", () => {
    const input = baseScores();
    input.scores = input.scores.filter((s) => s.subject !== "korean");
    const r = validateScores(input);
    expect(r.valid).toBe(false);
    expect(r.errors.some((e) => e.includes("필수 과목 누락"))).toBe(true);
  });

  it("국어에 표준점수·백분위 둘 다 없으면 오류", () => {
    const input = baseScores();
    input.scores[0] = { subject: "korean" };
    expect(validateScores(input).valid).toBe(false);
  });

  it("수학 선택과목 미입력은 경고(저장 허용)", () => {
    const input = baseScores();
    delete input.scores[1]!.selection;
    const r = validateScores(input);
    expect(r.valid).toBe(true);
    expect(r.warnings.some((w) => w.includes("수학 선택과목"))).toBe(true);
  });

  it("탐구 미입력은 경고", () => {
    const input = baseScores();
    input.scores = input.scores.filter(
      (s) => s.subject !== "inquiry1" && s.subject !== "inquiry2",
    );
    const r = validateScores(input);
    expect(r.valid).toBe(true);
    expect(r.warnings.some((w) => w.includes("탐구 성적 미입력"))).toBe(true);
  });

  it("중복 과목은 오류", () => {
    const input = baseScores();
    input.scores.push({ subject: "korean", standardScore: 120 });
    expect(validateScores(input).valid).toBe(false);
  });

  it("결정성: 같은 입력 = 같은 출력", () => {
    expect(validateScores(baseScores())).toEqual(validateScores(baseScores()));
  });
});
