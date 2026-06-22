import { describe, expect, it } from "vitest";
import { scoreConfidence } from "../confidence";

describe("scoreConfidence (§8.4)", () => {
  it("높음: 공식 환산식 검수 완료 + 입결 있음", () => {
    expect(
      scoreConfidence({
        method: "exact",
        hasApproximations: false,
        hasHistorical: true,
      }),
    ).toBe("high");
  });

  it("중간: 입결 있음 + 일부 근사 계산(예: 탐구 변표 근사)", () => {
    expect(
      scoreConfidence({
        method: "exact",
        hasApproximations: true,
        hasHistorical: true,
      }),
    ).toBe("medium");
  });

  it("낮음: 근사 계산 중심(백분위 합성)", () => {
    expect(
      scoreConfidence({
        method: "approx",
        hasApproximations: true,
        hasHistorical: true,
      }),
    ).toBe("low");
  });

  it("제한: 환산 불가", () => {
    expect(
      scoreConfidence({
        method: "unsupported",
        hasApproximations: false,
        hasHistorical: true,
      }),
    ).toBe("limited");
  });

  it("제한: 입결 없음(비교 기준 부족)", () => {
    expect(
      scoreConfidence({
        method: "exact",
        hasApproximations: false,
        hasHistorical: false,
      }),
    ).toBe("limited");
  });
});
