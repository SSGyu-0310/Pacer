/**
 * AdmissionRule JSON 컬럼(§9.8) → 도메인 AdmissionRuleData 매핑.
 * ★ 서버 전용 — 이 원문은 절대 클라이언트로 내려가지 않는다 (§8.1).
 *
 * JSON이 스키마에 안 맞으면 rule=null 로 매핑되어 해당 모집단위는
 * '분석 불가(unsupported)'로 투명하게 집계된다 — 조용히 잘못 계산하지 않는다.
 */
import type { AdmissionRuleData } from "@pacer/core";
import { scoreType, verifiedStatus } from "@pacer/shared";
import { z } from "zod";

const byGrade = z.record(z.string().regex(/^\d$/), z.number());
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

const finalAdjustment = z
  .object({
    subject: adjustedSubject,
    requiredSelections: z.array(z.string()).min(1).optional(),
    requiredInquiryCategory: z.enum(["science", "social"]).optional(),
    requiredInquiryCategoryCount: z.union([z.literal(1), z.literal(2)]).optional(),
    pointsFrom: z.enum(["standardScore", "percentile"]),
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

const englishPolicyJson = z
  .object({
    mode: z.enum(["deduction", "addition", "ratio"]),
    byGrade,
    // ratio 전용 — 영어 반영비와 환산점수 만점
    weight: z.number().nonnegative().optional(),
    scoreMax: z.number().positive().optional(),
  })
  // ratio면 weight(>0) 필수 — 없으면 가중평균에 합산할 수 없으니 분석 불가 처리
  .refine((p) => p.mode !== "ratio" || (p.weight ?? 0) > 0, {
    message: "ratio 영어 정책은 weight(>0)가 필요합니다",
  });

const historyPolicyJson = z.object({
  mode: z.enum(["deduction", "addition"]).optional(),
  byGrade,
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

const inquiryPolicyJson = z.object({
  count: z.union([z.literal(1), z.literal(2)]),
  mode: z.enum(["average", "best_one", "sum"]),
  conversionTable: inquiryConversionTable.optional(),
  conversionRisk: z.boolean().optional(),
});

const eligibilityJson = z.object({
  requiredMathSelections: z.array(z.string()).optional(),
  requiredInquiryCategory: z.enum(["science", "social"]).optional(),
  maxHistoryGrade: z.number().int().min(1).max(9).optional(),
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
  englishPolicy: englishPolicyJson.optional(),
  historyPolicy: historyPolicyJson.optional(),
  inquiryPolicy: inquiryPolicyJson.optional(),
  eligibility: eligibilityJson.optional(),
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

interface RuleRow {
  unitId: string;
  scoreType: string;
  formulaJson: unknown;
  eligibilityJson: unknown;
  englishPolicyJson: unknown;
  historyPolicyJson: unknown;
  inquiryPolicyJson: unknown;
  verifiedStatus: string;
}

function toNumericGrades(rec: Record<string, number>): Record<number, number> {
  return Object.fromEntries(
    Object.entries(rec).map(([k, v]) => [Number(k), v]),
  );
}

function toEnglishPolicy(
  policy: z.infer<typeof englishPolicyJson>,
): AdmissionRuleData["englishPolicy"] {
  return {
    mode: policy.mode,
    byGrade: toNumericGrades(policy.byGrade),
    ...(policy.weight !== undefined ? { weight: policy.weight } : {}),
    ...(policy.scoreMax !== undefined ? { scoreMax: policy.scoreMax } : {}),
  };
}

function toHistoryPolicy(
  policy: z.infer<typeof historyPolicyJson>,
): AdmissionRuleData["historyPolicy"] {
  return {
    ...(policy.mode !== undefined ? { mode: policy.mode } : {}),
    byGrade: toNumericGrades(policy.byGrade),
  };
}

function toFormulaAlternatives(
  alternatives: z.infer<typeof formulaJson>["alternatives"],
): AdmissionRuleData["formulaAlternatives"] | undefined {
  if (alternatives === undefined) return undefined;
  return alternatives.map((alternative) => ({
    ...(alternative.calculationMode !== undefined
      ? { calculationMode: alternative.calculationMode }
      : {}),
    weights: alternative.weights,
    ...(alternative.totalScale !== undefined
      ? { totalScale: alternative.totalScale }
      : {}),
    ...(alternative.csatWeight !== undefined
      ? { csatWeight: alternative.csatWeight }
      : {}),
    ...(alternative.subjectScoreTypes !== undefined
      ? { subjectScoreTypes: alternative.subjectScoreTypes }
      : {}),
    ...(alternative.scoreMaxes !== undefined
      ? { subjectScoreMaxes: alternative.scoreMaxes }
      : {}),
    ...(alternative.subjectBaseScores !== undefined
      ? { subjectBaseScores: alternative.subjectBaseScores }
      : {}),
    ...(alternative.selectionPolicy !== undefined
      ? { selectionPolicy: alternative.selectionPolicy }
      : {}),
    ...(alternative.subjectAdjustments !== undefined
      ? { subjectAdjustments: alternative.subjectAdjustments }
      : {}),
    ...(alternative.finalAdjustments !== undefined
      ? { finalAdjustments: alternative.finalAdjustments }
      : {}),
    ...(alternative.requiredInputs !== undefined
      ? { requiredInputs: alternative.requiredInputs }
      : {}),
    ...(alternative.externalComponents !== undefined
      ? { externalComponents: alternative.externalComponents }
      : {}),
    ...(alternative.englishPolicy !== undefined
      ? { englishPolicy: toEnglishPolicy(alternative.englishPolicy) }
      : {}),
    ...(alternative.historyPolicy !== undefined
      ? { historyPolicy: toHistoryPolicy(alternative.historyPolicy) }
      : {}),
    ...(alternative.inquiryPolicy !== undefined
      ? { inquiryPolicy: alternative.inquiryPolicy }
      : {}),
    ...(alternative.eligibility !== undefined
      ? { eligibility: alternative.eligibility }
      : {}),
  }));
}

/** 파싱 실패 시 null — 호출부가 '분석 불가'로 처리 */
export function mapRule(row: RuleRow | null | undefined): AdmissionRuleData | null {
  if (!row) return null;

  const st = scoreType.safeParse(row.scoreType);
  const vs = verifiedStatus.safeParse(row.verifiedStatus);
  const formula = formulaJson.safeParse(row.formulaJson);
  const english = englishPolicyJson.safeParse(row.englishPolicyJson);
  const history = historyPolicyJson.safeParse(row.historyPolicyJson);
  const inquiry = inquiryPolicyJson.safeParse(row.inquiryPolicyJson);
  // eligibility는 비어 있어도 됨(제한 없음)
  const eligibility = eligibilityJson.safeParse(row.eligibilityJson ?? {});

  if (
    !st.success ||
    !vs.success ||
    !formula.success ||
    !english.success ||
    !history.success ||
    !inquiry.success ||
    !eligibility.success
  ) {
    return null;
  }

  return {
    unitId: row.unitId,
    scoreType: st.data,
    totalScale: formula.data.totalScale,
    ...(formula.data.csatWeight !== undefined
      ? { csatWeight: formula.data.csatWeight }
      : {}),
    ...(formula.data.calculationMode !== undefined
      ? { calculationMode: formula.data.calculationMode }
      : {}),
    weights: formula.data.weights,
    ...(formula.data.subjectScoreTypes !== undefined
      ? { subjectScoreTypes: formula.data.subjectScoreTypes }
      : {}),
    ...(formula.data.scoreMaxes !== undefined
      ? { subjectScoreMaxes: formula.data.scoreMaxes }
      : {}),
    ...(formula.data.subjectBaseScores !== undefined
      ? { subjectBaseScores: formula.data.subjectBaseScores }
      : {}),
    ...(formula.data.subjectAdjustments !== undefined
      ? { subjectAdjustments: formula.data.subjectAdjustments }
      : {}),
    ...(formula.data.finalAdjustments !== undefined
      ? { finalAdjustments: formula.data.finalAdjustments }
      : {}),
    ...(formula.data.requiredInputs !== undefined
      ? { requiredInputs: formula.data.requiredInputs }
      : {}),
    ...(formula.data.selectionPolicy !== undefined
      ? { selectionPolicy: formula.data.selectionPolicy }
      : {}),
    ...(formula.data.alternatives !== undefined
      ? { formulaAlternatives: toFormulaAlternatives(formula.data.alternatives) }
      : {}),
    ...(formula.data.externalComponents !== undefined
      ? { externalComponents: formula.data.externalComponents }
      : {}),
    englishPolicy: toEnglishPolicy(english.data),
    historyPolicy: toHistoryPolicy(history.data),
    inquiryPolicy: inquiry.data,
    eligibility: eligibility.data,
    verifiedStatus: vs.data,
  };
}
