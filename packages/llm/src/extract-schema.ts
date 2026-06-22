import { z } from "zod";

export const EXTRACT_PROMPT_VERSION = "extract-v1";

export const extractProposalSchema = z.object({
  proposed: z.object({
    scoreType: z.enum(["standard", "percentile", "mixed", "custom"]).optional(),
    totalScale: z.number().positive().optional(),
    weights: z
      .object({
        korean: z.number().nonnegative(),
        math: z.number().nonnegative(),
        inquiry: z.number().nonnegative(),
      })
      .optional(),
    englishPolicyJson: z
      .object({
        mode: z.enum(["deduction", "addition", "ratio"]),
        byGrade: z.record(z.string().regex(/^\d$/), z.number()),
        // ratio(비율반영) 전용 — 영어 반영비와 환산점수 만점
        weight: z.number().nonnegative().optional(),
        scoreMax: z.number().positive().optional(),
      })
      .optional(),
    historyPolicyJson: z
      .object({
        byGrade: z.record(z.string().regex(/^\d$/), z.number()),
      })
      .optional(),
    inquiryPolicyJson: z
      .object({
        count: z.union([z.literal(1), z.literal(2)]),
        mode: z.enum(["average", "best_one"]),
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
