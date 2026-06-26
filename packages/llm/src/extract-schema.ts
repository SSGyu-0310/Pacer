import { z } from "zod";

export const EXTRACT_PROMPT_VERSION = "extract-v2";

const byGrade = z.record(z.string().regex(/^\d$/), z.number());
const subjectWeights = z.object({
  korean: z.number().nonnegative(),
  math: z.number().nonnegative(),
  inquiry: z.number().nonnegative(),
});
const calculationMode = z.enum(["weighted_average", "weighted_sum", "normalized_sum"]);
const subjectScoreMetric = z.enum(["standardScore", "percentile"]);
const subjectScoreTypes = z.object({
  korean: subjectScoreMetric.optional(),
  math: subjectScoreMetric.optional(),
  inquiry: subjectScoreMetric.optional(),
});
const scoreMaxes = z.object({
  korean: z.number().positive().optional(),
  math: z.number().positive().optional(),
  inquiry: z.number().positive().optional(),
});
const subjectBaseScores = z.object({
  korean: z.number().nonnegative().optional(),
  math: z.number().nonnegative().optional(),
  inquiry: z.number().nonnegative().optional(),
});
const selectionSubject = z.enum(["korean", "math", "english", "inquiry"]);
const selectionCount = z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4)]);
const adjustedSubject = z.enum(["korean", "math", "inquiry"]);
const externalComponent = z.object({
  kind: z.enum(["student_record", "practical", "interview", "essay", "document", "other"]),
  weight: z.number().nonnegative(),
  label: z.string().min(1).optional(),
  required: z.boolean().optional(),
});
const subjectAdjustment = z
  .object({
    subject: adjustedSubject,
    requiredSelections: z.array(z.string()).min(1).optional(),
    requiredInquiryCategory: z.enum(["science", "social"]).optional(),
    requiredInquiryCategoryCount: z.union([z.literal(1), z.literal(2)]).optional(),
    multiplier: z.number().positive().optional(),
    points: z.number().optional(),
    capAtMax: z.boolean().optional(),
  })
  .refine((adjustment) => adjustment.multiplier !== undefined || adjustment.points !== undefined, {
    message: "subjectAdjustments[] must include multiplier or points",
  })
  .refine(
    (adjustment) =>
      adjustment.requiredInquiryCategoryCount === undefined ||
      adjustment.requiredInquiryCategory !== undefined,
    {
      message: "subjectAdjustments[].requiredInquiryCategoryCount requires requiredInquiryCategory",
    },
  );
const finalAdjustment = z
  .object({
    subject: adjustedSubject,
    requiredSelections: z.array(z.string()).min(1).optional(),
    requiredInquiryCategory: z.enum(["science", "social"]).optional(),
    requiredInquiryCategoryCount: z.union([z.literal(1), z.literal(2)]).optional(),
    pointsFrom: subjectScoreMetric,
    multiplier: z.number().positive(),
    maxPoints: z.number().positive().optional(),
  })
  .refine(
    (adjustment) =>
      adjustment.requiredInquiryCategoryCount === undefined ||
      adjustment.requiredInquiryCategory !== undefined,
    {
      message: "finalAdjustments[].requiredInquiryCategoryCount requires requiredInquiryCategory",
    },
  );
const requiredInput = z.object({
  kind: z.enum(["national_max_standard_score", "conversion_table", "other"]),
  subjects: z.array(adjustedSubject).min(1).max(3).optional(),
  label: z.string().min(1).optional(),
  availability: z.enum(["post_csat", "manual", "unavailable"]).optional(),
});
const selectionGroup = z
  .object({
    count: selectionCount,
    subjects: z.array(selectionSubject).min(1).max(4),
    requiredSubjects: z.array(selectionSubject).min(1).max(4).optional(),
    rankWeights: z.array(z.number().positive()).min(1).max(4),
  })
  .refine((group) => group.rankWeights.length === group.count, {
    message: "selectionPolicy.groups[].rankWeights length must match count",
  })
  .refine((group) => (group.requiredSubjects?.length ?? 0) <= group.count, {
    message: "selectionPolicy.groups[].requiredSubjects length must be <= count",
  })
  .refine((group) => (group.requiredSubjects ?? []).every((subject) => group.subjects.includes(subject)), {
    message: "selectionPolicy.groups[].requiredSubjects must be included in subjects",
  });
const selectionPolicy = z
  .object({
    mode: z.literal("best_n_subjects"),
    count: selectionCount,
    subjects: z.array(selectionSubject).min(1).max(4),
    requiredSubjects: z.array(selectionSubject).min(1).max(4).optional(),
    rankWeights: z.array(z.number().positive()).min(1).max(4).optional(),
    groups: z.array(selectionGroup).min(1).max(4).optional(),
  })
  .refine((policy) => !policy.rankWeights || policy.rankWeights.length === policy.count, {
    message: "selectionPolicy.rankWeights length must match count",
  })
  .refine((policy) => (policy.requiredSubjects?.length ?? 0) <= policy.count, {
    message: "selectionPolicy.requiredSubjects length must be <= count",
  })
  .refine((policy) => (policy.requiredSubjects ?? []).every((subject) => policy.subjects.includes(subject)), {
    message: "selectionPolicy.requiredSubjects must be included in subjects",
  });
const formulaAlternative = z.object({
  calculationMode: calculationMode.optional(),
  totalScale: z.number().positive().optional(),
  csatWeight: z.number().nonnegative().optional(),
  weights: subjectWeights,
  subjectScoreTypes: subjectScoreTypes.optional(),
  scoreMaxes: scoreMaxes.optional(),
  subjectBaseScores: subjectBaseScores.optional(),
  selectionPolicy: selectionPolicy.optional(),
  subjectAdjustments: z.array(subjectAdjustment).min(1).max(8).optional(),
  finalAdjustments: z.array(finalAdjustment).min(1).max(8).optional(),
  requiredInputs: z.array(requiredInput).min(1).max(8).optional(),
  externalComponents: z.array(externalComponent).min(1).max(8).optional(),
});
const formulaJson = z.object({
  totalScale: z.number().positive(),
  csatWeight: z.number().nonnegative().optional(),
  calculationMode: calculationMode.optional(),
  weights: subjectWeights,
  subjectScoreTypes: subjectScoreTypes.optional(),
  scoreMaxes: scoreMaxes.optional(),
  subjectBaseScores: subjectBaseScores.optional(),
  selectionPolicy: selectionPolicy.optional(),
  subjectAdjustments: z.array(subjectAdjustment).min(1).max(8).optional(),
  finalAdjustments: z.array(finalAdjustment).min(1).max(8).optional(),
  requiredInputs: z.array(requiredInput).min(1).max(8).optional(),
  alternatives: z.array(formulaAlternative).min(1).max(8).optional(),
  externalComponents: z.array(externalComponent).min(1).max(8).optional(),
});
const inquiryConversionTable = z.object({
  from: z.literal("percentile"),
  scoreMax: z.number().positive().optional(),
  byPercentile: z
    .record(z.string().regex(/^\d{1,3}$/), z.number())
    .refine(
      (table) =>
        Object.keys(table).length > 0 &&
        Object.keys(table).every((key) => {
          const percentile = Number(key);
          return Number.isInteger(percentile) && percentile >= 0 && percentile <= 100;
        }),
      {
        message: "conversionTable.byPercentile keys must be integer percentiles 0-100",
      },
    ),
});

export const extractProposalSchema = z.object({
  proposed: z.object({
    scoreType: z.enum(["standard", "percentile", "mixed", "custom"]).optional(),
    formulaJson: formulaJson.optional(),
    totalScale: z.number().positive().optional(),
    csatWeight: z.number().nonnegative().optional(),
    calculationMode: calculationMode.optional(),
    subjectScoreTypes: subjectScoreTypes.optional(),
    scoreMaxes: scoreMaxes.optional(),
    weights: subjectWeights.optional(),
    subjectBaseScores: subjectBaseScores.optional(),
    selectionPolicy: selectionPolicy.optional(),
    subjectAdjustments: z.array(subjectAdjustment).min(1).max(8).optional(),
    finalAdjustments: z.array(finalAdjustment).min(1).max(8).optional(),
    requiredInputs: z.array(requiredInput).min(1).max(8).optional(),
    alternatives: z.array(formulaAlternative).min(1).max(8).optional(),
    formulaAlternatives: z.array(formulaAlternative).min(1).max(8).optional(),
    externalComponents: z.array(externalComponent).min(1).max(8).optional(),
    englishPolicyJson: z
      .object({
        mode: z.enum(["deduction", "addition", "ratio"]),
        byGrade,
        // ratio(비율반영) 전용 — 영어 반영비와 환산점수 만점
        weight: z.number().nonnegative().optional(),
        scoreMax: z.number().positive().optional(),
      })
      .optional(),
    historyPolicyJson: z
      .object({
        mode: z.enum(["deduction", "addition"]).optional(),
        byGrade,
      })
      .optional(),
    inquiryPolicyJson: z
      .object({
        count: z.union([z.literal(1), z.literal(2)]),
        mode: z.enum(["average", "best_one", "sum"]),
        conversionTable: inquiryConversionTable.optional(),
        conversionRisk: z.boolean().optional(),
      })
      .optional(),
    eligibilityJson: z.record(z.string(), z.unknown()).optional(),
  }),
  fieldFindings: z.array(
    z.object({
      field: z.string(),
      evidenceSupport: z.enum(["strong", "partial", "missing"]),
      note: z.string(),
    }),
  ),
  uncertain: z.array(z.string()),
  evidenceQuote: z.string().max(1200),
});

export type ExtractProposal = z.infer<typeof extractProposalSchema>;

export interface ExtractInput {
  targetKind: "rule" | "outcome";
  targetId: string;
  parsedFields: Record<string, unknown>;
  evidence: Record<string, unknown>;
}
