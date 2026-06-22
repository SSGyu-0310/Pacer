import { describe, expect, it } from "vitest";
import type { EligibilityResult } from "../../domain/entities";
import { convertScore } from "../convert";
import { normalizeScores } from "../normalize";
import {
  englishPenaltySpreadPer100,
  generateReasonCodes,
} from "../reason-codes";
import {
  baseScores,
  percentileRule,
  ratioEnglishRule,
  standardRule,
} from "./fixtures";

const ok: EligibilityResult = { eligible: true, failures: [] };
const normalized = () => normalizeScores(baseScores());

function args(over: Partial<Parameters<typeof generateReasonCodes>[0]> = {}) {
  const rule = standardRule();
  const n = normalized();
  return {
    examType: "june_mock" as const,
    normalized: n,
    rule,
    converted: convertScore(rule, n),
    band: "match" as const,
    confidence: "high" as const,
    eligibility: ok,
    ...over,
  };
}

describe("generateReasonCodes (§8.5)", () => {
  it("강점: 수학 강점 + 수학 반영비 0.4 → math_weight_advantage (+ explore_math_heavy 추천)", () => {
    const r = generateReasonCodes(args());
    expect(r.reasonCodes).toContain("math_weight_advantage");
    expect(r.reasonCodes).toContain("explore_math_heavy");
  });

  it("강점: 탐구 두 과목 백분위 85+ & 차이 5 이내 → science_stable", () => {
    expect(generateReasonCodes(args()).reasonCodes).toContain("science_stable");
  });

  it("적합: 표준점수 반영 + 적정 구간 → standard_score_fit", () => {
    expect(generateReasonCodes(args()).reasonCodes).toContain(
      "standard_score_fit",
    );
    const pct = percentileRule();
    expect(
      generateReasonCodes(args({ rule: pct })).reasonCodes,
    ).toContain("percentile_fit");
  });

  it("약점 과목(탐구) → simulate_explore_up 추천", () => {
    expect(generateReasonCodes(args()).reasonCodes).toContain(
      "simulate_explore_up",
    );
  });

  it("영어 3등급 + 감점 강한 대학 → english_penalty_risk 경고 + avoid_english_penalty 추천", () => {
    const input = baseScores();
    input.scores[2]!.grade = 3;
    const rule = standardRule({
      englishPolicy: { mode: "deduction", byGrade: { 1: 0, 2: 5, 3: 15 } },
    }); // spread 1.5per100
    const r = generateReasonCodes(
      args({ normalized: normalizeScores(input), rule }),
    );
    expect(r.warnings).toContain("english_penalty_risk");
    expect(r.reasonCodes).toContain("avoid_english_penalty");
  });

  it("영어 등급 보유자에게 감점 약한 대학 → english_low_penalty_advantage", () => {
    const rule = standardRule({
      englishPolicy: { mode: "deduction", byGrade: { 1: 0, 2: 2, 3: 4 } },
    }); // spread 0.4per100 ≤ 0.5
    const r = generateReasonCodes(args({ rule }));
    expect(r.reasonCodes).toContain("english_low_penalty_advantage");
  });

  it("탐구 변표 리스크 → science_conversion_risk 경고", () => {
    const rule = standardRule({
      inquiryPolicy: { count: 2, mode: "average", conversionRisk: true },
    });
    expect(generateReasonCodes(args({ rule })).warnings).toContain(
      "science_conversion_risk",
    );
  });

  it("수학 선택 제한 불충족 → math_requirement_fail 경고", () => {
    const fail: EligibilityResult = {
      eligible: false,
      failures: [{ code: "math_selection", message: "" }],
    };
    expect(
      generateReasonCodes(args({ eligibility: fail })).warnings,
    ).toContain("math_requirement_fail");
  });

  it("신뢰도 낮음/제한 → low_data_confidence 경고", () => {
    expect(
      generateReasonCodes(args({ confidence: "low" })).warnings,
    ).toContain("low_data_confidence");
    expect(
      generateReasonCodes(args({ confidence: "high" })).warnings,
    ).not.toContain("low_data_confidence");
  });

  it("소수 모집·변동성 플래그 → small_quota_risk / high_volatility 경고", () => {
    const r = generateReasonCodes(
      args({ smallQuota: true, highVolatility: true }),
    );
    expect(r.warnings).toContain("small_quota_risk");
    expect(r.warnings).toContain("high_volatility");
  });

  it("수능 시점 → compare_after_jinhak, 소신/도전 구간 → build_application_plan", () => {
    const r = generateReasonCodes(args({ examType: "csat", band: "reach" }));
    expect(r.reasonCodes).toContain("compare_after_jinhak");
    expect(r.reasonCodes).toContain("build_application_plan");
  });

  it("결정성: 같은 입력 = 같은 코드, 같은 순서", () => {
    expect(generateReasonCodes(args())).toEqual(generateReasonCodes(args()));
  });
});

describe("englishPenaltySpreadPer100", () => {
  it("deduction: 1↔3등급 차이를 만점 100 기준으로 환산한다", () => {
    expect(
      englishPenaltySpreadPer100(
        standardRule({
          englishPolicy: { mode: "deduction", byGrade: { 1: 0, 2: 2, 3: 6 } },
        }),
      ),
    ).toBe(0.6);
  });

  it("ratio: 반영비중(weight/weightSum)을 곱해 환산한다", () => {
    // 국30+수30+탐20+영20 = weightSum 100, 영어 1↔3등급차 |100−88|=12/100,
    // 반영비중 20/100 → (20/100)·(12/100)·100 = 2.4
    expect(englishPenaltySpreadPer100(ratioEnglishRule())).toBe(2.4);
  });
});
