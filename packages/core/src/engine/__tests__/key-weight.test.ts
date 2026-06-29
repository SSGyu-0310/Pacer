import { describe, expect, it } from "vitest";
import { formatKeyWeight } from "../key-weight";
import { ratioEnglishRule, standardRule } from "./fixtures";

describe("formatKeyWeight (§3 핵심 반영)", () => {
  it("국·수·탐 반영비를 백분율 상위 2과목으로 요약한다", () => {
    // 국30/수40/탐30 → 비중순 수학·국어
    expect(formatKeyWeight(standardRule())).toBe("수학 40%·국어 30%");
  });

  it("maxSubjects로 노출 과목 수를 늘릴 수 있다", () => {
    expect(formatKeyWeight(standardRule(), 3)).toBe(
      "수학 40%·국어 30%·탐구 30%",
    );
  });

  it("영어 ratio 반영비도 합산해 백분율을 낸다", () => {
    // 국30/수30/탐20/영20 (합 100) → 동률은 표기순(국→수) 유지
    expect(formatKeyWeight(ratioEnglishRule())).toBe("국어 30%·수학 30%");
  });

  it("규칙이 없으면 null(=반영비 검수중)", () => {
    expect(formatKeyWeight(null)).toBeNull();
    expect(formatKeyWeight(undefined)).toBeNull();
  });

  it("반영비 합이 0이면 null", () => {
    expect(
      formatKeyWeight(
        standardRule({ weights: { korean: 0, math: 0, inquiry: 0 } }),
      ),
    ).toBeNull();
  });
});
