import { describe, expect, it } from "vitest";
import { checkEligibility } from "../eligibility";
import { normalizeScores } from "../normalize";
import { baseScores } from "./fixtures";

const normalized = () => normalizeScores(baseScores());

describe("checkEligibility (§8.1-3, §18.1 수학 선택 제한)", () => {
  it("제한이 없으면 지원 가능", () => {
    expect(checkEligibility({}, normalized()).eligible).toBe(true);
  });

  it("수학 선택 제한 충족(미적분)", () => {
    const r = checkEligibility(
      { requiredMathSelections: ["미적분", "기하"] },
      normalized(),
    );
    expect(r.eligible).toBe(true);
  });

  it("수학 선택 제한 불충족(확률과통계)", () => {
    const input = baseScores();
    input.scores[1]!.selection = "확률과통계";
    const r = checkEligibility(
      { requiredMathSelections: ["미적분", "기하"] },
      normalizeScores(input),
    );
    expect(r.eligible).toBe(false);
    expect(r.failures.map((f) => f.code)).toContain("math_selection");
  });

  it("수학 선택과목 미입력은 보수적으로 불충족", () => {
    const input = baseScores();
    delete input.scores[1]!.selection;
    const r = checkEligibility(
      { requiredMathSelections: ["미적분"] },
      normalizeScores(input),
    );
    expect(r.eligible).toBe(false);
  });

  it("탐구 계열 제한(과탐) 충족", () => {
    const r = checkEligibility(
      { requiredInquiryCategory: "science" },
      normalized(), // 물리학Ⅰ + 지구과학Ⅰ
    );
    expect(r.eligible).toBe(true);
  });

  it("탐구 계열 제한(과탐) 불충족 — 사탐 포함", () => {
    const input = baseScores();
    input.scores[5]!.selection = "생활과윤리";
    const r = checkEligibility(
      { requiredInquiryCategory: "science" },
      normalizeScores(input),
    );
    expect(r.eligible).toBe(false);
    expect(r.failures.map((f) => f.code)).toContain("inquiry_category");
  });

  it("한국사 최저 등급 판정", () => {
    expect(checkEligibility({ maxHistoryGrade: 4 }, normalized()).eligible).toBe(
      true, // 3등급
    );
    const r = checkEligibility({ maxHistoryGrade: 2 }, normalized());
    expect(r.eligible).toBe(false);
    expect(r.failures.map((f) => f.code)).toContain("history_grade");
  });
});
