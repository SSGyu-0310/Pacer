import type {
  AdmissionRuleData,
  ConvertedScore,
  NormalizedScores,
  SubjectScoreValue,
} from "../../domain/entities";
import {
  APPROX_SCALE,
  BASIS_MAX,
  ENGLISH_RATIO_DEFAULT_MAX,
  SCIENCE_INQUIRY_SUBJECTS,
  round2,
} from "../constants";

/**
 * 4. 대학별 환산점수 계산 (§8.2) — 정확/상대비교/근사/불가.
 * ★ 서버 전용. 환산식·입결 데이터는 클라이언트로 원문 노출 금지 (§8.1).
 *
 * 결정 규칙:
 * - scoreType=custom → 불가(unsupported). P0는 custom formula 해석기를 갖지 않는다.
 * - 규칙이 검수 완료(verified/live) → 정확 환산(exact):
 *   - standard:   국·수·탐 표준점수(만점 200) 가중 평균 → totalScale로 스케일
 *   - percentile: 국·수·탐 백분위(만점 100) 가중 평균 → totalScale로 스케일
 *   - mixed:      국·수/탐구 과목별 점수 기준을 formulaJson.subjectScoreTypes로 지정할 수 있음.
 *                 미지정 legacy mixed 탐구는 백분위×2 근사(변표 근사 — approximations 표기)
 *   탐구는 inquiryPolicy.mode에 따라 평균(average), 상위 1과목(best_one), 합산(sum).
 *   영어: mode=deduction/addition이면 등급별 점수를 가산·감점(§18.1);
 *         mode=ratio이면 국·수·탐처럼 반영비(weight)를 갖는 한 과목으로 가중평균에 합산(대부분 대학).
 *   한국사: mode=deduction/addition이면 등급별 점수를 감점/가산(§18.1). 미지정은 deduction.
 *   수학/탐구 가산: formulaJson.subjectAdjustments로 조건부 배율/고정점 가산을 과목 basis에 적용.
 *   최종점 가산: formulaJson.finalAdjustments로 표준점수/백분위 기반 가산점을 최종 환산점에 더한다.
 *   과목별 만점: formulaJson.scoreMaxes로 공식 표준점수/변환표준점수 최고점을 지정할 수 있다.
 *     requiredInquiryCategoryCount가 있으면 탐구 조합 전체(예: 과탐 2과목)를 먼저 확인한다.
 *   직접 가중합: formulaJson.calculationMode="weighted_sum"이면 basis/만점 정규화 없이
 *     Σ(과목 basis × 계수)로 계산한다. 서강대식 A/B 산식처럼 원문 계수가 점수에 직접 곱해지는 경우다.
 *   기본점수+실질반영점수 합산: formulaJson.calculationMode="normalized_sum"이면
 *     Σ(과목 기본점수 + basis / 과목만점 × 실질반영점수)로 계산한다.
 *   A/B 등 대체 산식: formulaJson.alternatives가 있으면 각 산식을 계산한 뒤 최고점을 반영.
 *   수능 이후 확정되는 전국최고표준점수 등 formulaJson.requiredInputs가 남아 있으면
 *   exact는 닫고, 공개된 반영비 기반 relative 비교로 낮은 신뢰도 분석을 제공한다.
 *   실기·학생부·면접 등 비수능 구성요소가 있으면 전체 전형총점 exact는 닫고,
 *   공개된 수능 반영구조만으로 낮은 신뢰도 relative 비교를 제공한다.
 * - 검수 미완료(draft/parsed/deprecated) → 근사 비교(approx):
 *   백분위 가중 합성(만점 100). ratio 영어는 등급→환산점수를 백분위 환산해 합산(근사 표기);
 *   deduction/addition 영어·한국사 정책은 적용하지 않는다(근사임을 명시).
 * - 필요한 점수가 없으면 불가(unsupported).
 *
 * 순수·결정적: 같은 입력 = 같은 출력 (§18.1).
 */
export function convertScore(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
): ConvertedScore {
  if (rule.scoreType === "custom") {
    return unsupported(rule.unitId);
  }

  const verified =
    rule.verifiedStatus === "verified" || rule.verifiedStatus === "live";

  if (!verified) {
    if (hasExternalComponents(rule)) {
      return approxByExternalComponents(rule, scores);
    }
    return approxByPercentile(rule, scores);
  }

  if (hasExternalComponents(rule)) {
    return relativeResult(approxByExternalComponents(rule, scores));
  }

  if (hasRequiredFormulaInputs(rule)) {
    return relativeResult(approxByRequiredFormula(rule, scores));
  }

  return exactByFormula(rule, scores);
}

function relativeResult(result: ConvertedScore): ConvertedScore {
  return result.method === "approx" ? { ...result, method: "relative" } : result;
}

/** 정확 환산 (§8.2 정확 환산) */
function exactByFormula(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
): ConvertedScore {
  if (hasExternalComponents(rule)) {
    return unsupported(rule.unitId, ["non_csat_component"]);
  }
  if (hasRequiredFormulaInputs(rule)) {
    return unsupported(rule.unitId, ["formula_required_input"]);
  }
  if (rule.formulaAlternatives?.length) {
    return bestAlternativeScore(rule, scores, exactByFormula);
  }

  const approximations: string[] = [];
  const korean = subjectBasis(rule, "korean", scores);
  const math = subjectBasis(rule, "math", scores);
  const inquiry = inquiryBasis(rule, scores, approximations);
  const english = scores.bySubject.get("english")?.grade;
  const history = scores.bySubject.get("history")?.grade;

  const { weights, englishPolicy } = rule;
  if (rule.selectionPolicy) {
    return exactBySelectionPolicy(rule, scores, approximations);
  }
  if (rule.calculationMode === "normalized_sum") {
    return exactByNormalizedSum(rule, scores, approximations);
  }
  if (rule.calculationMode === "weighted_sum") {
    return exactByWeightedSum(rule, scores, approximations);
  }

  const englishRatio = englishPolicy.mode === "ratio";
  const englishWeight = englishRatio ? (englishPolicy.weight ?? 0) : 0;
  if (
    (weights.korean > 0 && !korean) ||
    (weights.math > 0 && !math) ||
    (weights.inquiry > 0 && !inquiry) ||
    english === undefined ||
    history === undefined
  ) {
    return unsupported(rule.unitId);
  }

  let weightSum = weights.korean + weights.math + weights.inquiry;
  let weightedRatio = 0;
  if (korean) weightedRatio += weights.korean * (korean.value / korean.max);
  if (math) weightedRatio += weights.math * (math.value / math.max);
  if (inquiry) weightedRatio += weights.inquiry * (inquiry.value / inquiry.max);

  // 영어 비율반영(ratio): 국·수·탐과 같은 가중평균에 한 과목으로 합산
  if (englishRatio) {
    const scoreMax = englishPolicy.scoreMax ?? ENGLISH_RATIO_DEFAULT_MAX;
    weightSum += englishWeight;
    weightedRatio +=
      englishWeight * ((englishPolicy.byGrade[english] ?? 0) / scoreMax);
  }

  if (weightSum <= 0) return unsupported(rule.unitId);
  weightedRatio /= weightSum;

  let converted = weightedRatio * rule.totalScale;

  // 영어 가산/감점 정책 (§18.1) — ratio는 위에서 이미 합산했으므로 제외
  if (!englishRatio) {
    const englishPoints = englishPolicy.byGrade[english] ?? 0;
    converted +=
      englishPolicy.mode === "addition" ? englishPoints : -englishPoints;
  }

  const finalPoints = finalAdjustmentPoints(rule, scores);
  if (finalPoints === null) return unsupported(rule.unitId);
  converted += finalPoints;

  converted = applyHistoryPolicy(converted, rule, history);

  return {
    unitId: rule.unitId,
    convertedScore: round2(converted),
    method: "exact",
    scale: rule.totalScale,
    approximations,
  };
}

function exactByWeightedSum(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): ConvertedScore {
  const korean = subjectBasis(rule, "korean", scores);
  const math = subjectBasis(rule, "math", scores);
  const inquiry = inquiryBasis(rule, scores, approximations);
  const english = scores.bySubject.get("english")?.grade;
  const history = scores.bySubject.get("history")?.grade;

  const { weights, englishPolicy } = rule;
  const englishRatio = englishPolicy.mode === "ratio";
  const englishWeight = englishRatio ? (englishPolicy.weight ?? 0) : 0;
  if (
    (weights.korean > 0 && !korean) ||
    (weights.math > 0 && !math) ||
    (weights.inquiry > 0 && !inquiry) ||
    english === undefined ||
    history === undefined
  ) {
    return unsupported(rule.unitId);
  }

  let converted = 0;
  let hasTerm = false;
  if (korean && weights.korean > 0) {
    converted += korean.value * weights.korean;
    hasTerm = true;
  }
  if (math && weights.math > 0) {
    converted += math.value * weights.math;
    hasTerm = true;
  }
  if (inquiry && weights.inquiry > 0) {
    converted += inquiry.value * weights.inquiry;
    hasTerm = true;
  }

  if (englishRatio) {
    converted += (englishPolicy.byGrade[english] ?? 0) * englishWeight;
    hasTerm = hasTerm || englishWeight > 0;
  }

  if (!hasTerm) return unsupported(rule.unitId);

  if (!englishRatio) {
    const englishPoints = englishPolicy.byGrade[english] ?? 0;
    converted +=
      englishPolicy.mode === "addition" ? englishPoints : -englishPoints;
  }

  const finalPoints = finalAdjustmentPoints(rule, scores);
  if (finalPoints === null) return unsupported(rule.unitId);
  converted += finalPoints;

  converted = applyHistoryPolicy(converted, rule, history);

  return {
    unitId: rule.unitId,
    convertedScore: round2(converted),
    method: "exact",
    scale: rule.totalScale,
    approximations,
  };
}

function exactByNormalizedSum(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): ConvertedScore {
  const korean = subjectBasis(rule, "korean", scores);
  const math = subjectBasis(rule, "math", scores);
  const inquiry = inquiryBasis(rule, scores, approximations);
  const english = scores.bySubject.get("english")?.grade;
  const history = scores.bySubject.get("history")?.grade;

  const { weights, englishPolicy } = rule;
  const bases = rule.subjectBaseScores ?? {};
  const englishRatio = englishPolicy.mode === "ratio";
  const englishWeight = englishRatio ? (englishPolicy.weight ?? 0) : 0;
  if (
    (normalizedTermRequired(weights.korean, bases.korean) && !korean) ||
    (normalizedTermRequired(weights.math, bases.math) && !math) ||
    (normalizedTermRequired(weights.inquiry, bases.inquiry) && !inquiry) ||
    english === undefined ||
    history === undefined
  ) {
    return unsupported(rule.unitId);
  }

  let converted = 0;
  let hasTerm = false;
  if (korean && normalizedTermRequired(weights.korean, bases.korean)) {
    converted += normalizedSubjectTerm(korean, weights.korean, bases.korean);
    hasTerm = true;
  }
  if (math && normalizedTermRequired(weights.math, bases.math)) {
    converted += normalizedSubjectTerm(math, weights.math, bases.math);
    hasTerm = true;
  }
  if (inquiry && normalizedTermRequired(weights.inquiry, bases.inquiry)) {
    converted += normalizedSubjectTerm(inquiry, weights.inquiry, bases.inquiry);
    hasTerm = true;
  }

  if (englishRatio) {
    const scoreMax = englishPolicy.scoreMax ?? ENGLISH_RATIO_DEFAULT_MAX;
    converted +=
      englishWeight * ((englishPolicy.byGrade[english] ?? 0) / scoreMax);
    hasTerm = hasTerm || englishWeight > 0;
  }

  if (!hasTerm) return unsupported(rule.unitId);

  if (!englishRatio) {
    const englishPoints = englishPolicy.byGrade[english] ?? 0;
    converted +=
      englishPolicy.mode === "addition" ? englishPoints : -englishPoints;
  }

  const finalPoints = finalAdjustmentPoints(rule, scores);
  if (finalPoints === null) return unsupported(rule.unitId);
  converted += finalPoints;

  converted = applyHistoryPolicy(converted, rule, history);

  return {
    unitId: rule.unitId,
    convertedScore: round2(converted),
    method: "exact",
    scale: rule.totalScale,
    approximations,
  };
}

function normalizedTermRequired(weight: number, baseScore: number | undefined): boolean {
  return weight > 0 || (baseScore ?? 0) > 0;
}

function normalizedSubjectTerm(
  basis: { value: number; max: number },
  weight: number,
  baseScore: number | undefined,
): number {
  return (baseScore ?? 0) + (basis.value / basis.max) * weight;
}

function exactBySelectionPolicy(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): ConvertedScore {
  const selectedScore = selectionPolicyScore(rule, scores, approximations);
  if (selectedScore === null) return unsupported(rule.unitId);

  let converted = (selectedScore / BASIS_MAX.percentile) * rule.totalScale;

  const history = scores.bySubject.get("history")?.grade;
  if (history === undefined) return unsupported(rule.unitId);
  const finalPoints = finalAdjustmentPoints(rule, scores);
  if (finalPoints === null) return unsupported(rule.unitId);
  converted += finalPoints;
  converted = applyHistoryPolicy(converted, rule, history);

  return {
    unitId: rule.unitId,
    convertedScore: round2(converted),
    method: "exact",
    scale: rule.totalScale,
    approximations,
  };
}

/** 탐구 basis — 평균/상위 1과목 (§18.1), mixed는 백분위×2 변표 근사 */
function inquiryBasis(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): { value: number; max: number } | null {
  const values: { value: number; max: number }[] = [];
  const defaultMax =
    rule.scoreType === "percentile"
      ? BASIS_MAX.percentile
      : subjectScoreMax(rule, "inquiry", BASIS_MAX.standard);
  const metric = rule.subjectScoreTypes?.inquiry;

  for (const subject of ["inquiry1", "inquiry2"] as const) {
    const s = scores.bySubject.get(subject);
    if (!s) continue;
    const converted = inquiryConversionTableBasis(rule, s);
    if (converted) {
      const adjusted = applySubjectAdjustments(rule, "inquiry", {
        value: converted.value,
        max: converted.max,
        score: s,
        scores,
      });
      values.push(adjusted);
    } else if (rule.inquiryPolicy.conversionTable) {
      return null;
    } else if (metric === "percentile" || (!metric && rule.scoreType === "percentile")) {
      if (s.percentile !== undefined) {
        const adjusted = applySubjectAdjustments(rule, "inquiry", {
          value: s.percentile,
          max: BASIS_MAX.percentile,
          score: s,
          scores,
        });
        values.push(adjusted);
      }
    } else if (metric === "standardScore" || (!metric && rule.scoreType === "standard")) {
      if (s.standardScore !== undefined) {
        const adjusted = applySubjectAdjustments(rule, "inquiry", {
          value: s.standardScore,
          max: subjectScoreMax(rule, "inquiry", BASIS_MAX.standard),
          score: s,
          scores,
        });
        values.push(adjusted);
      }
    } else if (!metric && rule.scoreType === "mixed") {
      // 변환표준점수 미보유 → 백분위×2 근사 (만점 200 기준)
      if (s.percentile !== undefined) {
        const adjusted = applySubjectAdjustments(rule, "inquiry", {
          value: s.percentile * (defaultMax / BASIS_MAX.percentile),
          max: defaultMax,
          score: s,
          scores,
        });
        values.push(adjusted);
        if (!approximations.includes("inquiry_conversion")) {
          approximations.push("inquiry_conversion");
        }
      }
    }
  }

  if (values.length < rule.inquiryPolicy.count) return null;
  if (rule.inquiryPolicy.mode === "best_one") {
    return values.reduce((best, item) =>
      item.value / item.max > best.value / best.max ? item : best,
    );
  }
  const selected = values.slice(0, rule.inquiryPolicy.count);
  const valueSum = selected.reduce((sum, item) => sum + item.value, 0);
  const maxSum = selected.reduce((sum, item) => sum + item.max, 0);
  if (rule.inquiryPolicy.mode === "sum") {
    return { value: valueSum, max: maxSum };
  }
  return {
    value: valueSum / selected.length,
    max: maxSum / selected.length,
  };
}

function inquiryConversionTableBasis(
  rule: AdmissionRuleData,
  score: SubjectScoreValue,
): { value: number; max: number } | null {
  const table = rule.inquiryPolicy.conversionTable;
  if (!table) return null;
  if (table.from !== "percentile" || score.percentile === undefined) return null;
  const percentile = Math.round(score.percentile);
  if (Math.abs(score.percentile - percentile) > 0.001) return null;
  const value = table.byPercentile[percentile];
  if (value === undefined) return null;
  return {
    value,
    max: table.scoreMax ?? subjectScoreMax(rule, "inquiry", BASIS_MAX.standard),
  };
}

function subjectBasis(
  rule: AdmissionRuleData,
  subject: "korean" | "math",
  scores: NormalizedScores,
): { value: number; max: number } | null {
  const score = scores.bySubject.get(subject);
  if (!score) return null;

  const metric =
    rule.subjectScoreTypes?.[subject] ??
    (rule.scoreType === "percentile" ? "percentile" : "standardScore");

  if (metric === "percentile") {
    return score.percentile === undefined
      ? null
      : applySubjectAdjustments(rule, subject, {
          value: score.percentile,
          max: BASIS_MAX.percentile,
          score,
          scores,
        });
  }

  // standard | mixed 기본값: 국·수는 표준점수 basis로 계산한다.
  const max = subjectScoreMax(rule, subject, BASIS_MAX.standard);
  return score.standardScore === undefined
    ? null
    : applySubjectAdjustments(rule, subject, {
        value: score.standardScore,
        max,
        score,
        scores,
      });
}

/** 근사 비교 (§8.2 근사 비교) — 백분위 가중 합성, 만점 100. 신뢰도 낮음 표시는 confidence가 담당. */
function approxByRequiredFormula(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  initialApproximations: string[] = [],
): ConvertedScore {
  const approximations = [...new Set([...initialApproximations, "formula_required_input"])];
  if (canApproximateRequiredInputsByFormula(rule)) {
    const result = approxByPercentile(ruleWithoutRequiredInputs(rule), scores, approximations);
    if (result.convertedScore !== null && result.method !== "unsupported") return result;
  }
  return approxByPercentile(rule, scores, approximations);
}

function approxByExternalComponents(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
): ConvertedScore {
  const ruleWithoutExternal = ruleWithoutExternalComponents(rule);
  if (hasRequiredFormulaInputs(ruleWithoutExternal)) {
    return approxByRequiredFormula(ruleWithoutExternal, scores, ["non_csat_component"]);
  }
  return approxByPercentile(ruleWithoutExternal, scores, ["non_csat_component"]);
}

function approxByPercentile(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  initialApproximations: string[] = [],
): ConvertedScore {
  if (hasExternalComponents(rule)) {
    return unsupported(rule.unitId, ["non_csat_component"]);
  }
  if (rule.formulaAlternatives?.length) {
    return bestAlternativeScore(rule, scores, (candidateRule, candidateScores) =>
      approxByPercentile(candidateRule, candidateScores, initialApproximations),
    );
  }

  const { weights, englishPolicy } = rule;
  const approximations = [...new Set(["percentile_composite", ...initialApproximations])];
  if (rule.calculationMode === "weighted_sum") {
    return approxWeightedSumByPercentile(rule, scores, approximations);
  }
  if (rule.selectionPolicy) {
    const selectedScore = selectionPolicyScore(
      { ...rule, scoreType: "percentile" },
      scores,
      [],
    );
    if (selectedScore === null) return unsupported(rule.unitId);
    approximations.push("best_subjects_selection");
    return {
      unitId: rule.unitId,
      convertedScore: round2(selectedScore),
      method: "approx",
      scale: APPROX_SCALE,
      approximations,
    };
  }

  const parts: { weight: number; percentile: number }[] = [];

  const koreanScore = scores.bySubject.get("korean");
  if (weights.korean > 0 && koreanScore?.percentile !== undefined) {
    parts.push({
      weight: weights.korean,
      percentile: applySubjectAdjustments(rule, "korean", {
        value: koreanScore.percentile,
        max: BASIS_MAX.percentile,
        score: koreanScore,
        scores,
      }).value,
    });
  }
  const mathScore = scores.bySubject.get("math");
  if (weights.math > 0 && mathScore?.percentile !== undefined) {
    parts.push({
      weight: weights.math,
      percentile: applySubjectAdjustments(rule, "math", {
        value: mathScore.percentile,
        max: BASIS_MAX.percentile,
        score: mathScore,
        scores,
      }).value,
    });
  }

  const inquiryPercentiles = (["inquiry1", "inquiry2"] as const)
    .map((subject) => {
      const score = scores.bySubject.get(subject);
      if (score?.percentile === undefined) return null;
      return applySubjectAdjustments(rule, "inquiry", {
        value: score.percentile,
        max: BASIS_MAX.percentile,
        score,
        scores,
      }).value;
    })
    .filter((p): p is number => p !== null);
  if (
    weights.inquiry > 0 &&
    inquiryPercentiles.length >= rule.inquiryPolicy.count
  ) {
    const value =
      rule.inquiryPolicy.mode === "best_one"
        ? Math.max(...inquiryPercentiles)
        : inquiryPercentiles.reduce((a, b) => a + b, 0) /
          inquiryPercentiles.length;
    parts.push({ weight: weights.inquiry, percentile: value });
  }

  // 영어 비율반영(ratio): 등급→환산점수를 백분위(만점 100)로 환산해 합산(근사 표기)
  const englishRatioWeight =
    englishPolicy.mode === "ratio" ? (englishPolicy.weight ?? 0) : 0;
  const englishGrade = scores.bySubject.get("english")?.grade;
  if (englishRatioWeight > 0 && englishGrade !== undefined) {
    const scoreMax = englishPolicy.scoreMax ?? ENGLISH_RATIO_DEFAULT_MAX;
    parts.push({
      weight: englishRatioWeight,
      percentile: ((englishPolicy.byGrade[englishGrade] ?? 0) / scoreMax) * 100,
    });
    approximations.push("english_ratio_approx");
  }

  // 반영비 있는 과목의 백분위가 하나도 없거나 일부 누락이면 불가
  const expected =
    (weights.korean > 0 ? 1 : 0) +
    (weights.math > 0 ? 1 : 0) +
    (weights.inquiry > 0 ? 1 : 0) +
    (englishRatioWeight > 0 ? 1 : 0);
  if (parts.length < expected || expected === 0) {
    return unsupported(rule.unitId);
  }

  const weightSum = parts.reduce((a, p) => a + p.weight, 0);
  const converted =
    parts.reduce((a, p) => a + p.weight * p.percentile, 0) / weightSum;

  return {
    unitId: rule.unitId,
    convertedScore: round2(converted),
    method: "approx",
    scale: APPROX_SCALE,
    approximations,
  };
}

function approxWeightedSumByPercentile(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): ConvertedScore {
  const terms: { value: number; max: number }[] = [];

  const korean = weightedSumSubjectApproxTerm(rule, "korean", scores);
  const math = weightedSumSubjectApproxTerm(rule, "math", scores);
  const inquiry = weightedSumInquiryApproxTerm(rule, scores, approximations);
  if (rule.weights.korean > 0 && !korean) return unsupported(rule.unitId);
  if (rule.weights.math > 0 && !math) return unsupported(rule.unitId);
  if (rule.weights.inquiry > 0 && !inquiry) return unsupported(rule.unitId);
  if (korean) terms.push(korean);
  if (math) terms.push(math);
  if (inquiry) terms.push(inquiry);

  const english = scores.bySubject.get("english")?.grade;
  const history = scores.bySubject.get("history")?.grade;
  if (english === undefined || history === undefined) return unsupported(rule.unitId);

  const englishTerm = gradePolicyApproxTerm(rule.englishPolicy, english);
  if (englishTerm) {
    terms.push(englishTerm);
    if (rule.englishPolicy.mode !== "ratio") approximations.push("english_addition_approx");
  }

  const historyTerm = gradePolicyApproxTerm(rule.historyPolicy, history);
  if (historyTerm) {
    terms.push(historyTerm);
    approximations.push("history_addition_approx");
  }

  const value = terms.reduce((sum, term) => sum + term.value, 0);
  const max = terms.reduce((sum, term) => sum + term.max, 0);
  if (max <= 0) return unsupported(rule.unitId);

  return {
    unitId: rule.unitId,
    convertedScore: round2((value / max) * APPROX_SCALE),
    method: "approx",
    scale: APPROX_SCALE,
    approximations: [...new Set(approximations)],
  };
}

function weightedSumSubjectApproxTerm(
  rule: AdmissionRuleData,
  subject: "korean" | "math",
  scores: NormalizedScores,
): { value: number; max: number } | null {
  const score = scores.bySubject.get(subject);
  if (!score || score.percentile === undefined) return null;
  const officialMax =
    rule.subjectScoreTypes?.[subject] === "percentile"
      ? BASIS_MAX.percentile
      : subjectScoreMax(rule, subject, BASIS_MAX.standard);
  const adjusted = applySubjectAdjustments(rule, subject, {
    value: score.percentile,
    max: BASIS_MAX.percentile,
    score,
    scores,
  });
  const weight = rule.weights[subject];
  return {
    value: (adjusted.value / adjusted.max) * officialMax * weight,
    max: officialMax * weight,
  };
}

function weightedSumInquiryApproxTerm(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): { value: number; max: number } | null {
  const officialMax =
    rule.subjectScoreTypes?.inquiry === "percentile"
      ? BASIS_MAX.percentile
      : subjectScoreMax(rule, "inquiry", BASIS_MAX.standard);
  const values = (["inquiry1", "inquiry2"] as const)
    .map((subject) => {
      const score = scores.bySubject.get(subject);
      if (!score || score.percentile === undefined) return null;
      return applySubjectAdjustments(rule, "inquiry", {
        value: score.percentile,
        max: BASIS_MAX.percentile,
        score,
        scores,
      });
    })
    .filter((value): value is { value: number; max: number } => value !== null);

  if (values.length < rule.inquiryPolicy.count) return null;
  if (!approximations.includes("inquiry_conversion")) approximations.push("inquiry_conversion");

  const selected =
    rule.inquiryPolicy.mode === "best_one"
      ? [values.reduce((best, item) => (item.value / item.max > best.value / best.max ? item : best))]
      : values.slice(0, rule.inquiryPolicy.count);
  const ratioSum = selected.reduce((sum, item) => sum + item.value / item.max, 0);
  const divisor = rule.inquiryPolicy.mode === "average" ? selected.length : 1;
  const value = (ratioSum / divisor) * officialMax * rule.weights.inquiry;
  const max =
    (rule.inquiryPolicy.mode === "sum" ? selected.length : 1) *
    officialMax *
    rule.weights.inquiry;
  return { value, max };
}

function gradePolicyApproxTerm(
  policy:
    | AdmissionRuleData["englishPolicy"]
    | AdmissionRuleData["historyPolicy"],
  grade: number,
): { value: number; max: number } | null {
  const points = policy.byGrade[grade];
  if (points === undefined) return null;
  const values = Object.values(policy.byGrade);
  if (values.length === 0) return null;

  const mode = policy.mode ?? "deduction";
  if (mode === "deduction") {
    const maxDeduction = Math.max(...values);
    if (maxDeduction <= 0) return null;
    return { value: maxDeduction - points, max: maxDeduction };
  }

  const scoreMax =
    "scoreMax" in policy && typeof policy.scoreMax === "number"
      ? policy.scoreMax
      : Math.max(...values);
  const weight =
    "weight" in policy && typeof policy.weight === "number" ? policy.weight : 1;
  if (scoreMax <= 0 || weight <= 0) return null;
  return { value: points * weight, max: scoreMax * weight };
}

function bestAlternativeScore(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  convert: (rule: AdmissionRuleData, scores: NormalizedScores) => ConvertedScore,
): ConvertedScore {
  let best: ConvertedScore | null = null;
  let bestRatio: number | null = null;

  for (const alternative of rule.formulaAlternatives ?? []) {
    const candidate = convert(ruleForAlternative(rule, alternative), scores);
    if (candidate.convertedScore === null) continue;
    const candidateRatio =
      candidate.scale && candidate.scale > 0
        ? candidate.convertedScore / candidate.scale
        : candidate.convertedScore;
    if (!best || bestRatio === null || candidateRatio > bestRatio) {
      best = candidate;
      bestRatio = candidateRatio;
    }
  }

  return best ?? unsupported(rule.unitId);
}

function ruleForAlternative(
  rule: AdmissionRuleData,
  alternative: NonNullable<AdmissionRuleData["formulaAlternatives"]>[number],
): AdmissionRuleData {
  return {
    ...rule,
    totalScale: alternative.totalScale ?? rule.totalScale,
    csatWeight: alternative.csatWeight ?? rule.csatWeight,
    calculationMode: alternative.calculationMode ?? rule.calculationMode,
    weights: alternative.weights,
    subjectScoreTypes:
      alternative.subjectScoreTypes ?? rule.subjectScoreTypes,
    subjectScoreMaxes:
      alternative.subjectScoreMaxes ?? rule.subjectScoreMaxes,
    subjectBaseScores:
      alternative.subjectBaseScores ?? rule.subjectBaseScores,
    subjectAdjustments:
      alternative.subjectAdjustments ?? rule.subjectAdjustments,
    finalAdjustments:
      alternative.finalAdjustments ?? rule.finalAdjustments,
    requiredInputs:
      alternative.requiredInputs ?? rule.requiredInputs,
    selectionPolicy: alternative.selectionPolicy ?? rule.selectionPolicy,
    externalComponents: alternative.externalComponents ?? rule.externalComponents,
    englishPolicy: alternative.englishPolicy ?? rule.englishPolicy,
    historyPolicy: alternative.historyPolicy ?? rule.historyPolicy,
    inquiryPolicy: alternative.inquiryPolicy ?? rule.inquiryPolicy,
    eligibility: alternative.eligibility ?? rule.eligibility,
    formulaAlternatives: undefined,
  };
}

function applyHistoryPolicy(
  converted: number,
  rule: AdmissionRuleData,
  historyGrade: number,
): number {
  const points = rule.historyPolicy.byGrade[historyGrade] ?? 0;
  return rule.historyPolicy.mode === "addition"
    ? converted + points
    : converted - points;
}

function finalAdjustmentPoints(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
): number | null {
  let total = 0;
  for (const adjustment of rule.finalAdjustments ?? []) {
    const points = finalAdjustmentPoint(rule, adjustment, scores);
    if (points === null) return null;
    total += points;
  }
  return total;
}

function finalAdjustmentPoint(
  rule: AdmissionRuleData,
  adjustment: NonNullable<AdmissionRuleData["finalAdjustments"]>[number],
  scores: NormalizedScores,
): number | null {
  if (adjustment.subject === "inquiry") {
    return finalInquiryAdjustmentPoint(rule, adjustment, scores);
  }

  const score = scores.bySubject.get(adjustment.subject);
  if (!score) return null;
  if (!subjectConditionApplies(adjustment, score, scores)) return 0;
  const sourceValue = scoreValueForFinalAdjustment(score, adjustment.pointsFrom);
  if (sourceValue === undefined) return null;
  return capFinalAdjustment(sourceValue * adjustment.multiplier, adjustment.maxPoints);
}

function finalInquiryAdjustmentPoint(
  rule: AdmissionRuleData,
  adjustment: NonNullable<AdmissionRuleData["finalAdjustments"]>[number],
  scores: NormalizedScores,
): number | null {
  const inquiryScores = (["inquiry1", "inquiry2"] as const)
    .map((subject) => scores.bySubject.get(subject))
    .filter((score): score is SubjectScoreValue => score !== undefined);

  if (
    adjustment.requiredInquiryCategory &&
    adjustment.requiredInquiryCategoryCount !== undefined &&
    inquiryCategoryCount(scores, adjustment.requiredInquiryCategory) <
      adjustment.requiredInquiryCategoryCount
  ) {
    return 0;
  }

  const matchingScores = inquiryScores.filter((score) =>
    subjectConditionApplies(adjustment, score, scores),
  );
  if (matchingScores.length === 0) {
    return adjustment.requiredInquiryCategory ? 0 : null;
  }

  const values = matchingScores.map((score) =>
    scoreValueForFinalAdjustment(score, adjustment.pointsFrom),
  );
  if (values.some((value) => value === undefined)) return null;

  const numericValues = values as number[];
  if (
    adjustment.requiredInquiryCategory &&
    adjustment.requiredInquiryCategoryCount === undefined
  ) {
    const categorySelectedValues =
      rule.inquiryPolicy.mode === "best_one"
        ? [Math.max(...numericValues)]
        : numericValues.slice(0, rule.inquiryPolicy.count);
    return capFinalAdjustment(
      categorySelectedValues.reduce(
        (sum, value) => sum + value * adjustment.multiplier,
        0,
      ),
      adjustment.maxPoints,
    );
  }

  const selectedValues =
    rule.inquiryPolicy.mode === "best_one"
      ? [Math.max(...numericValues)]
      : numericValues.slice(0, rule.inquiryPolicy.count);
  if (selectedValues.length < rule.inquiryPolicy.count) return null;

  const points = selectedValues.reduce(
    (sum, value) => sum + value * adjustment.multiplier,
    0,
  );
  return capFinalAdjustment(points, adjustment.maxPoints);
}

function scoreValueForFinalAdjustment(
  score: SubjectScoreValue,
  pointsFrom: NonNullable<AdmissionRuleData["finalAdjustments"]>[number]["pointsFrom"],
): number | undefined {
  return pointsFrom === "standardScore" ? score.standardScore : score.percentile;
}

function capFinalAdjustment(points: number, maxPoints: number | undefined): number {
  return maxPoints === undefined ? points : Math.min(points, maxPoints);
}

function subjectScoreMax(
  rule: AdmissionRuleData,
  subject: keyof NonNullable<AdmissionRuleData["subjectScoreMaxes"]>,
  fallback: number,
): number {
  return rule.subjectScoreMaxes?.[subject] ?? fallback;
}

function selectionPolicyParts(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): { subject: string; percentile: number }[] | null {
  const policy = rule.selectionPolicy;
  if (!policy) return null;
  return selectionSpecParts(rule, scores, policy, approximations);
}

function selectionSpecParts(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  spec: {
    count: number;
    subjects: Array<"korean" | "math" | "english" | "inquiry">;
    requiredSubjects?: Array<"korean" | "math" | "english" | "inquiry">;
  },
  approximations: string[],
): { subject: string; percentile: number }[] | null {
  if (spec.subjects.length < spec.count) return null;
  const requiredSubjects = [...new Set(spec.requiredSubjects ?? [])];
  if (requiredSubjects.length > spec.count) return null;
  if (requiredSubjects.some((subject) => !spec.subjects.includes(subject))) {
    return null;
  }

  const parts: { subject: string; percentile: number }[] = [];
  for (const subject of spec.subjects) {
    if (subject === "english") {
      const grade = scores.bySubject.get("english")?.grade;
      if (grade === undefined || rule.englishPolicy.mode !== "ratio") {
        return null;
      }
      const scoreMax = rule.englishPolicy.scoreMax ?? ENGLISH_RATIO_DEFAULT_MAX;
      parts.push({
        subject,
        percentile: ((rule.englishPolicy.byGrade[grade] ?? 0) / scoreMax) * 100,
      });
      continue;
    }

    if (subject === "inquiry") {
      const basis = inquiryBasis(rule, scores, approximations);
      if (!basis) return null;
      parts.push({
        subject,
        percentile: (basis.value / basis.max) * BASIS_MAX.percentile,
      });
      continue;
    }

    const basis = subjectBasis(rule, subject, scores);
    if (!basis) return null;
    parts.push({
      subject,
      percentile: (basis.value / basis.max) * BASIS_MAX.percentile,
    });
  }

  if (parts.length < spec.count) return null;
  const byScoreDesc = (a: { percentile: number }, b: { percentile: number }) =>
    b.percentile - a.percentile;
  const sorted = [...parts].sort(byScoreDesc);
  if (requiredSubjects.length === 0) return sorted.slice(0, spec.count);

  const requiredSet = new Set<string>(requiredSubjects);
  const requiredParts = parts.filter((part) => requiredSet.has(part.subject));
  if (requiredParts.length !== requiredSubjects.length) return null;

  const remainingSlots = spec.count - requiredParts.length;
  const remainingParts = parts
    .filter((part) => !requiredSet.has(part.subject))
    .sort(byScoreDesc)
    .slice(0, remainingSlots);
  const selected = [...requiredParts, ...remainingParts];
  if (selected.length !== spec.count) return null;
  return selected.sort(byScoreDesc);
}

function selectionPolicyScore(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): number | null {
  const policy = rule.selectionPolicy;
  if (!policy) return null;
  if (policy.groups && policy.groups.length > 0) {
    let weightedSum = 0;
    let weightSum = 0;

    for (const group of policy.groups) {
      const selected = selectionSpecParts(rule, scores, group, approximations);
      if (!selected || group.rankWeights.length !== selected.length) return null;
      const groupWeightSum = group.rankWeights.reduce((sum, weight) => sum + weight, 0);
      if (groupWeightSum <= 0) return null;
      weightedSum += selected.reduce(
        (sum, part, index) => sum + part.percentile * group.rankWeights[index]!,
        0,
      );
      weightSum += groupWeightSum;
    }

    return weightSum > 0 ? weightedSum / weightSum : null;
  }

  const selected = selectionPolicyParts(rule, scores, approximations);
  if (!selected) return null;

  if (!policy.rankWeights) {
    return selected.reduce((sum, part) => sum + part.percentile, 0) / selected.length;
  }

  if (policy.rankWeights.length !== selected.length) return null;
  const weightSum = policy.rankWeights.reduce((sum, weight) => sum + weight, 0);
  if (weightSum <= 0) return null;

  return (
    selected.reduce(
      (sum, part, index) => sum + part.percentile * policy.rankWeights![index]!,
      0,
    ) / weightSum
  );
}

function unsupported(unitId: string, approximations: string[] = []): ConvertedScore {
  return {
    unitId,
    convertedScore: null,
    method: "unsupported",
    scale: null,
    approximations,
  };
}

function hasExternalComponents(rule: AdmissionRuleData): boolean {
  if (rule.externalComponents?.length) return true;
  return (rule.formulaAlternatives ?? []).some((alternative) => Boolean(alternative.externalComponents?.length));
}

function hasRequiredFormulaInputs(rule: AdmissionRuleData): boolean {
  if (rule.requiredInputs?.length) return true;
  return (rule.formulaAlternatives ?? []).some((alternative) => Boolean(alternative.requiredInputs?.length));
}

function canApproximateRequiredInputsByFormula(rule: AdmissionRuleData): boolean {
  const inputs = [
    ...(rule.requiredInputs ?? []),
    ...(rule.formulaAlternatives ?? []).flatMap((alternative) => alternative.requiredInputs ?? []),
  ];
  return (
    inputs.length > 0 &&
    inputs.every(
      (input) =>
        input.kind === "conversion_table" &&
        (!input.subjects?.length || input.subjects.every((subject) => subject === "inquiry")),
    )
  );
}

function ruleWithoutRequiredInputs(rule: AdmissionRuleData): AdmissionRuleData {
  return {
    ...rule,
    requiredInputs: undefined,
    formulaAlternatives: rule.formulaAlternatives?.map((alternative) => ({
      ...alternative,
      requiredInputs: undefined,
    })),
  };
}

function ruleWithoutExternalComponents(rule: AdmissionRuleData): AdmissionRuleData {
  return {
    ...rule,
    externalComponents: undefined,
    formulaAlternatives: rule.formulaAlternatives?.map((alternative) => ({
      ...alternative,
      externalComponents: undefined,
    })),
  };
}

function applySubjectAdjustments(
  rule: AdmissionRuleData,
  subject: "korean" | "math" | "inquiry",
  basis: { value: number; max: number; score: SubjectScoreValue; scores: NormalizedScores },
): { value: number; max: number } {
  let value = basis.value;
  for (const adjustment of rule.subjectAdjustments ?? []) {
    if (adjustment.subject !== subject) continue;
    if (!subjectAdjustmentApplies(adjustment, basis.score, basis.scores)) continue;
    value *= adjustment.multiplier ?? 1;
    value += adjustment.points ?? 0;
    if (adjustment.capAtMax) value = Math.min(value, basis.max);
  }
  return { value, max: basis.max };
}

type SubjectConditionPolicy = {
  subject: "korean" | "math" | "inquiry";
  requiredSelections?: string[];
  requiredInquiryCategory?: "science" | "social";
  requiredInquiryCategoryCount?: 1 | 2;
};

function subjectAdjustmentApplies(
  adjustment: SubjectConditionPolicy,
  score: SubjectScoreValue,
  scores: NormalizedScores,
): boolean {
  return subjectConditionApplies(adjustment, score, scores);
}

function subjectConditionApplies(
  adjustment: SubjectConditionPolicy,
  score: SubjectScoreValue,
  scores: NormalizedScores,
): boolean {
  if (
    adjustment.requiredSelections &&
    (!score.selection || !adjustment.requiredSelections.includes(score.selection))
  ) {
    return false;
  }
  if (adjustment.requiredInquiryCategory) {
    const requiredCount = adjustment.requiredInquiryCategoryCount;
    if (
      requiredCount !== undefined &&
      inquiryCategoryCount(scores, adjustment.requiredInquiryCategory) < requiredCount
    ) {
      return false;
    }
    if (adjustment.subject === "inquiry" || requiredCount === undefined) {
      if (!score.selection) return false;
      if (!selectionMatchesInquiryCategory(score.selection, adjustment.requiredInquiryCategory)) {
        return false;
      }
    }
  }
  return true;
}

function inquiryCategoryCount(
  scores: NormalizedScores,
  category: "science" | "social",
): number {
  return (["inquiry1", "inquiry2"] as const).reduce((count, subject) => {
    const selection = scores.bySubject.get(subject)?.selection;
    return selection && selectionMatchesInquiryCategory(selection, category) ? count + 1 : count;
  }, 0);
}

function selectionMatchesInquiryCategory(
  selection: string,
  category: "science" | "social",
): boolean {
  const isScience = SCIENCE_INQUIRY_SUBJECTS.includes(selection);
  return category === "science" ? isScience : !isScience;
}
