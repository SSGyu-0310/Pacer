import { describe, expect, it } from "vitest";
import { EXTRACT_PROMPT_VERSION, extractProposalSchema } from "../extract-schema";

const gradeTable = {
  1: 100,
  2: 95,
  3: 90,
  4: 80,
  5: 70,
  6: 60,
  7: 50,
  8: 40,
  9: 0,
};

describe("extractProposalSchema", () => {
  it("accepts rich rule formula proposals used by the admin review editor", () => {
    const parsed = extractProposalSchema.parse({
      proposed: {
        scoreType: "mixed",
        formulaJson: {
          totalScale: 1000,
          calculationMode: "weighted_average",
          weights: { korean: 0, math: 0, inquiry: 0 },
          subjectScoreTypes: { korean: "percentile", math: "percentile", inquiry: "percentile" },
          scoreMaxes: { inquiry: 100 },
          selectionPolicy: {
            mode: "best_n_subjects",
            count: 4,
            subjects: ["korean", "math", "english", "inquiry"],
            groups: [
              { count: 2, subjects: ["korean", "math"], rankWeights: [40, 30] },
              { count: 2, subjects: ["english", "inquiry"], rankWeights: [20, 10] },
            ],
          },
          subjectAdjustments: [
            {
              subject: "math",
              requiredSelections: ["미적분", "기하"],
              multiplier: 1.05,
            },
          ],
          finalAdjustments: [
            {
              subject: "inquiry",
              requiredInquiryCategory: "science",
              pointsFrom: "percentile",
              multiplier: 0.03,
            },
          ],
          requiredInputs: [
            {
              kind: "national_max_standard_score",
              subjects: ["korean", "math", "inquiry"],
              label: "영역별 전국 최고 표준점수",
              availability: "post_csat",
            },
          ],
          alternatives: [
            {
              weights: { korean: 30, math: 40, inquiry: 20 },
              subjectBaseScores: { korean: 40, math: 30, inquiry: 30 },
              calculationMode: "normalized_sum",
            },
          ],
          externalComponents: [{ kind: "practical", weight: 70, label: "실기" }],
        },
        englishPolicyJson: {
          mode: "ratio",
          weight: 20,
          scoreMax: 100,
          byGrade: gradeTable,
        },
        historyPolicyJson: {
          mode: "addition",
          byGrade: gradeTable,
        },
        inquiryPolicyJson: {
          count: 2,
          mode: "sum",
          conversionTable: {
            from: "percentile",
            scoreMax: 200,
            byPercentile: { 100: 200, 99: 198 },
          },
          conversionRisk: true,
        },
        eligibilityJson: {
          requiredMathSelections: ["미적분", "기하"],
          requiredInquiryCategory: "science",
        },
      },
      fieldFindings: [],
      uncertain: [],
      evidenceQuote: "공식 모집요강 표에 따른 추출",
    });

    expect(EXTRACT_PROMPT_VERSION).toBe("extract-v2");
    expect(parsed.proposed.formulaJson?.selectionPolicy?.groups).toHaveLength(2);
    expect(parsed.proposed.formulaJson?.requiredInputs?.[0]?.kind).toBe("national_max_standard_score");
    expect(parsed.proposed.formulaJson?.externalComponents?.[0]?.kind).toBe("practical");
    expect(parsed.proposed.inquiryPolicyJson?.conversionTable?.byPercentile["99"]).toBe(198);
  });

  it("rejects malformed selection group weights instead of silently narrowing the formula", () => {
    expect(() =>
      extractProposalSchema.parse({
        proposed: {
          formulaJson: {
            totalScale: 100,
            weights: { korean: 0, math: 0, inquiry: 0 },
            selectionPolicy: {
              mode: "best_n_subjects",
              count: 2,
              subjects: ["korean", "math"],
              groups: [{ count: 2, subjects: ["korean", "math"], rankWeights: [100] }],
            },
          },
        },
        fieldFindings: [],
        uncertain: [],
        evidenceQuote: "",
      }),
    ).toThrow();
  });

  it("rejects malformed inquiry conversion table percentiles", () => {
    expect(() =>
      extractProposalSchema.parse({
        proposed: {
          inquiryPolicyJson: {
            count: 2,
            mode: "average",
            conversionTable: {
              from: "percentile",
              byPercentile: { 101: 200 },
            },
          },
        },
        fieldFindings: [],
        uncertain: [],
        evidenceQuote: "",
      }),
    ).toThrow();
  });
});
