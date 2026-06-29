import { describe, expect, it } from "vitest";
import type { CompetitorSignal, UnitAnalysis } from "../../domain/entities";
import { crossValidate, signalToBand } from "../cross-validate";

function unit(unitId: string, band: UnitAnalysis["band"]): UnitAnalysis {
  return {
    unit: { unitId, university: "한양대", unitName: "기계공학", recruitmentGroup: "ga" },
    metricMode: "converted",
    metricLabel: "환산점수",
    cutLabel: "환산점수 컷",
    convertedScore: 500,
    historicalReferenceScore: 495,
    scoreGap: 5,
    band,
    confidence: "high",
    reasonCodes: [],
    warnings: [],
  };
}

function signal(
  unitId: string,
  valueType: CompetitorSignal["valueType"],
  value: string,
  provider: CompetitorSignal["provider"] = "jinhak",
): CompetitorSignal {
  return {
    id: `sig-${unitId}-${valueType}-${value}`,
    cycleId: "cy-1",
    examType: "csat",
    provider,
    unitId,
    valueType,
    value,
  };
}

describe("engine.signalToBand (§7.7.4 휴리스틱 v1)", () => {
  it("진학사 칸수 1~8 매핑, 범위 밖/비정수는 null", () => {
    expect(signalToBand({ valueType: "kansu", value: "8" })).toBe("stable");
    expect(signalToBand({ valueType: "kansu", value: "5" })).toBe("match");
    expect(signalToBand({ valueType: "kansu", value: "4" })).toBe("reach");
    expect(signalToBand({ valueType: "kansu", value: "3" })).toBe("challenge");
    expect(signalToBand({ valueType: "kansu", value: "1" })).toBe("risk");
    expect(signalToBand({ valueType: "kansu", value: "9" })).toBeNull();
    expect(signalToBand({ valueType: "kansu", value: "abc" })).toBeNull();
  });

  it("확률 — % 표기 허용, 0~100 밖은 null", () => {
    expect(signalToBand({ valueType: "probability", value: "90" })).toBe("stable");
    expect(signalToBand({ valueType: "probability", value: "70%" })).toBe("match");
    expect(signalToBand({ valueType: "probability", value: "50" })).toBe("reach");
    expect(signalToBand({ valueType: "probability", value: "30" })).toBe("challenge");
    expect(signalToBand({ valueType: "probability", value: "10" })).toBe("risk");
    expect(signalToBand({ valueType: "probability", value: "120" })).toBeNull();
  });

  it("색상 — 한/영 표기 정규화, 미정의 색은 null", () => {
    expect(signalToBand({ valueType: "color", value: "빨강" })).toBe("stable");
    expect(signalToBand({ valueType: "color", value: "RED" })).toBe("stable");
    expect(signalToBand({ valueType: "color", value: "노랑" })).toBe("reach");
    expect(signalToBand({ valueType: "color", value: "보라" })).toBeNull();
  });

  it("메모는 구간으로 환원하지 않는다", () => {
    expect(signalToBand({ valueType: "memo", value: "학원에서는 안정이라 함" })).toBeNull();
  });
});

describe("engine.crossValidate (§7.7.4, P2)", () => {
  const results = [unit("u1", "match"), unit("u2", "stable")];

  it("agree / near / disagree / uncertain 분류", () => {
    const out = crossValidate(results, [
      signal("u1", "kansu", "5"), // match vs match → agree
      signal("u1", "kansu", "8"), // match vs stable → near
      signal("u2", "kansu", "1"), // stable vs risk → disagree
      signal("u1", "memo", "메모"), // → uncertain
      signal("u9", "kansu", "5"), // 분석 결과 없음 → uncertain
    ]);
    expect(out.totals).toEqual({ agree: 1, near: 1, disagree: 1, uncertain: 2 });

    const missing = out.items.find((i) => i.unitId === "u9")!;
    expect(missing.unit).toBeNull();
    expect(missing.agreement).toBe("uncertain");
  });

  it("자체 분석을 덮어쓰지 않는다 — internalBand는 입력 결과 그대로", () => {
    const out = crossValidate(results, [signal("u1", "kansu", "1")]);
    expect(out.items[0]!.internalBand).toBe("match");
    expect(out.items[0]!.externalBand).toBe("risk");
  });

  it("결정성 — 입력 순서와 무관하게 같은 출력", () => {
    const a = [signal("u1", "kansu", "5"), signal("u2", "kansu", "8")];
    const b = [...a].reverse();
    expect(crossValidate(results, a)).toEqual(crossValidate(results, b));
  });
});
