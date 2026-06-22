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

const formulaJson = z.object({
  totalScale: z.number().positive(),
  weights: z.object({
    korean: z.number().nonnegative(),
    math: z.number().nonnegative(),
    inquiry: z.number().nonnegative(),
  }),
  selectionPolicy: z
    .object({
      mode: z.literal("best_n_subjects"),
      count: z.union([z.literal(2), z.literal(3)]),
      subjects: z
        .array(z.enum(["korean", "math", "english", "inquiry"]))
        .min(2)
        .max(4),
    })
    .optional(),
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

const historyPolicyJson = z.object({ byGrade });

const inquiryPolicyJson = z.object({
  count: z.union([z.literal(1), z.literal(2)]),
  mode: z.enum(["average", "best_one"]),
  conversionRisk: z.boolean().optional(),
});

const eligibilityJson = z.object({
  requiredMathSelections: z.array(z.string()).optional(),
  requiredInquiryCategory: z.enum(["science", "social"]).optional(),
  maxHistoryGrade: z.number().int().min(1).max(9).optional(),
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
    weights: formula.data.weights,
    ...(formula.data.selectionPolicy !== undefined
      ? { selectionPolicy: formula.data.selectionPolicy }
      : {}),
    englishPolicy: {
      mode: english.data.mode,
      byGrade: toNumericGrades(english.data.byGrade),
      ...(english.data.weight !== undefined
        ? { weight: english.data.weight }
        : {}),
      ...(english.data.scoreMax !== undefined
        ? { scoreMax: english.data.scoreMax }
        : {}),
    },
    historyPolicy: { byGrade: toNumericGrades(history.data.byGrade) },
    inquiryPolicy: inquiry.data,
    eligibility: eligibility.data,
    verifiedStatus: vs.data,
  };
}
