import { describe, expect, it } from "vitest";
import { classifyBand } from "../band";

describe("classifyBand (§8.3)", () => {
  it("기본 임계값: 만점 1000 기준 gap → 구간", () => {
    expect(classifyBand({ scoreGap: 20, scale: 1000 })).toBe("stable"); // +2.0
    expect(classifyBand({ scoreGap: 5, scale: 1000 })).toBe("match"); // +0.5
    expect(classifyBand({ scoreGap: -8, scale: 1000 })).toBe("reach"); // -0.8
    expect(classifyBand({ scoreGap: -25, scale: 1000 })).toBe("challenge"); // -2.5
    expect(classifyBand({ scoreGap: -40, scale: 1000 })).toBe("risk"); // -4.0
  });

  it("만점이 달라도 비율로 정규화된다 (백분위 만점 100)", () => {
    expect(classifyBand({ scoreGap: 2, scale: 100 })).toBe("stable"); // +2.0
    expect(classifyBand({ scoreGap: -1, scale: 100 })).toBe("reach"); // -1.0
  });

  it("시험 시점 보정: 6모는 보수적 (gap 17 → 수능 stable, 6모 match)", () => {
    expect(
      classifyBand({ scoreGap: 17, scale: 1000, factors: { examType: "csat" } }),
    ).toBe("stable");
    expect(
      classifyBand({
        scoreGap: 17,
        scale: 1000,
        factors: { examType: "june_mock" },
      }),
    ).toBe("match");
  });

  it("모집인원 20% 이상 감소 → 보수적", () => {
    expect(
      classifyBand({
        scoreGap: 16,
        scale: 1000,
        factors: { quotaChangeRatio: -0.25 },
      }),
    ).toBe("match"); // 1.6 - 0.5 = 1.1
  });

  it("충원율 100% 이상 → 완화 (reach → match)", () => {
    expect(
      classifyBand({
        scoreGap: -8,
        scale: 1000,
        factors: { additionalPassRate: 1.2 },
      }),
    ).toBe("match"); // -0.8 + 0.5 = -0.3
  });

  it("소수 모집단위 → 보수적 (match → reach)", () => {
    expect(
      classifyBand({ scoreGap: -1, scale: 1000, factors: { smallQuota: true } }),
    ).toBe("reach"); // -0.1 - 0.5 = -0.6
  });

  it("영어 감점 강한 대학 + 영어 3등급 → 보수적", () => {
    expect(
      classifyBand({
        scoreGap: -1,
        scale: 1000,
        factors: { userEnglishGrade: 3, englishPenaltySpreadPer100: 1.2 },
      }),
    ).toBe("reach"); // -0.1 - 0.5 = -0.6
    // 영어 1등급이면 보정 없음
    expect(
      classifyBand({
        scoreGap: -1,
        scale: 1000,
        factors: { userEnglishGrade: 1, englishPenaltySpreadPer100: 1.2 },
      }),
    ).toBe("match");
  });

  it("탐구 변표 리스크 → 보수적 (reach → challenge)", () => {
    expect(
      classifyBand({
        scoreGap: -13,
        scale: 1000,
        factors: { scienceConversionRisk: true },
      }),
    ).toBe("challenge"); // -1.3 - 0.3 = -1.6
  });

  it("데이터 신뢰도 낮음 → '안정' 단정 금지(최대 '적정') §2.1", () => {
    expect(
      classifyBand({
        scoreGap: 30,
        scale: 1000,
        factors: { dataConfidence: "low" },
      }),
    ).toBe("match"); // 3.0 - 0.3 = 2.7 → stable이지만 캡
    expect(
      classifyBand({
        scoreGap: 30,
        scale: 1000,
        factors: { dataConfidence: "high" },
      }),
    ).toBe("stable");
  });

  it("결정성: 같은 입력 = 같은 출력", () => {
    const input = {
      scoreGap: -8,
      scale: 1000,
      factors: { examType: "june_mock" as const, smallQuota: true },
    };
    expect(classifyBand(input)).toBe(classifyBand(input));
  });
});
