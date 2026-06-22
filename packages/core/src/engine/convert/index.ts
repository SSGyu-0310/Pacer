import type {
  AdmissionRuleData,
  ConvertedScore,
  NormalizedScores,
} from "../../domain/entities";
import {
  APPROX_SCALE,
  BASIS_MAX,
  ENGLISH_RATIO_DEFAULT_MAX,
  round2,
} from "../constants";

/**
 * 4. 대학별 환산점수 계산 (§8.2) — 정확/근사/불가.
 * ★ 서버 전용. 환산식·입결 데이터는 클라이언트로 원문 노출 금지 (§8.1).
 *
 * 결정 규칙:
 * - scoreType=custom → 불가(unsupported). P0는 custom formula 해석기를 갖지 않는다.
 * - 규칙이 검수 완료(verified/live) → 정확 환산(exact):
 *   - standard:   국·수·탐 표준점수(만점 200) 가중 평균 → totalScale로 스케일
 *   - percentile: 국·수·탐 백분위(만점 100) 가중 평균 → totalScale로 스케일
 *   - mixed:      국·수 표준점수 + 탐구는 백분위×2 근사(변표 근사 — approximations 표기)
 *   탐구는 inquiryPolicy.mode에 따라 평균(average) 또는 상위 1과목(best_one).
 *   영어: mode=deduction/addition이면 등급별 점수를 가산·감점(§18.1);
 *         mode=ratio이면 국·수·탐처럼 반영비(weight)를 갖는 한 과목으로 가중평균에 합산(대부분 대학).
 *   한국사는 등급별 점수를 감점(§18.1).
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
    return approxByPercentile(rule, scores);
  }

  return exactByFormula(rule, scores);
}

/** 정확 환산 (§8.2 정확 환산) */
function exactByFormula(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
): ConvertedScore {
  const approximations: string[] = [];
  const basisFor = (
    subject: "korean" | "math",
  ): { value: number; max: number } | null => {
    const s = scores.bySubject.get(subject);
    if (!s) return null;
    if (rule.scoreType === "percentile") {
      return s.percentile === undefined
        ? null
        : { value: s.percentile, max: BASIS_MAX.percentile };
    }
    // standard | mixed: 국·수는 표준점수
    return s.standardScore === undefined
      ? null
      : { value: s.standardScore, max: BASIS_MAX.standard };
  };

  const korean = basisFor("korean");
  const math = basisFor("math");
  const inquiry = inquiryBasis(rule, scores, approximations);
  const english = scores.bySubject.get("english")?.grade;
  const history = scores.bySubject.get("history")?.grade;

  const { weights, englishPolicy } = rule;
  if (rule.selectionPolicy) {
    return exactBySelectionPolicy(rule, scores, approximations);
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

  // 한국사 정책 (§18.1 한국사 감점 적용) — 감점만
  converted -= rule.historyPolicy.byGrade[history] ?? 0;

  return {
    unitId: rule.unitId,
    convertedScore: round2(converted),
    method: "exact",
    scale: rule.totalScale,
    approximations,
  };
}

function exactBySelectionPolicy(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
  approximations: string[],
): ConvertedScore {
  if (rule.scoreType !== "percentile") return unsupported(rule.unitId);

  const selected = selectionPolicyParts(rule, scores);
  if (!selected) return unsupported(rule.unitId);

  let converted =
    (selected.reduce((sum, part) => sum + part.percentile, 0) /
      selected.length /
      BASIS_MAX.percentile) *
    rule.totalScale;

  const history = scores.bySubject.get("history")?.grade;
  if (history === undefined) return unsupported(rule.unitId);
  converted -= rule.historyPolicy.byGrade[history] ?? 0;

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
  const values: number[] = [];
  let max: number = BASIS_MAX.standard;

  for (const subject of ["inquiry1", "inquiry2"] as const) {
    const s = scores.bySubject.get(subject);
    if (!s) continue;
    if (rule.scoreType === "percentile") {
      if (s.percentile !== undefined) {
        values.push(s.percentile);
        max = BASIS_MAX.percentile;
      }
    } else if (rule.scoreType === "mixed") {
      // 변환표준점수 미보유 → 백분위×2 근사 (만점 200 기준)
      if (s.percentile !== undefined) {
        values.push(s.percentile * 2);
        max = BASIS_MAX.standard;
        if (!approximations.includes("inquiry_conversion")) {
          approximations.push("inquiry_conversion");
        }
      }
    } else if (s.standardScore !== undefined) {
      values.push(s.standardScore);
      max = BASIS_MAX.standard;
    }
  }

  if (values.length < rule.inquiryPolicy.count) return null;
  const value =
    rule.inquiryPolicy.mode === "best_one"
      ? Math.max(...values)
      : values.reduce((a, b) => a + b, 0) / values.length;
  return { value, max };
}

/** 근사 비교 (§8.2 근사 비교) — 백분위 가중 합성, 만점 100. 신뢰도 낮음 표시는 confidence가 담당. */
function approxByPercentile(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
): ConvertedScore {
  const { weights, englishPolicy } = rule;
  const approximations = ["percentile_composite"];
  const selected = selectionPolicyParts(rule, scores);
  if (selected) {
    approximations.push("best_subjects_selection");
    return {
      unitId: rule.unitId,
      convertedScore: round2(
        selected.reduce((sum, part) => sum + part.percentile, 0) /
          selected.length,
      ),
      method: "approx",
      scale: APPROX_SCALE,
      approximations,
    };
  }

  const parts: { weight: number; percentile: number }[] = [];

  const korean = scores.bySubject.get("korean")?.percentile;
  if (weights.korean > 0 && korean !== undefined)
    parts.push({ weight: weights.korean, percentile: korean });
  const math = scores.bySubject.get("math")?.percentile;
  if (weights.math > 0 && math !== undefined)
    parts.push({ weight: weights.math, percentile: math });

  const inquiryPercentiles = (["inquiry1", "inquiry2"] as const)
    .map((s) => scores.bySubject.get(s)?.percentile)
    .filter((p): p is number => p !== undefined);
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

function selectionPolicyParts(
  rule: AdmissionRuleData,
  scores: NormalizedScores,
): { subject: string; percentile: number }[] | null {
  const policy = rule.selectionPolicy;
  if (!policy) return null;

  const parts: { subject: string; percentile: number }[] = [];
  for (const subject of policy.subjects) {
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
      const values = (["inquiry1", "inquiry2"] as const)
        .map((s) => scores.bySubject.get(s)?.percentile)
        .filter((value): value is number => value !== undefined);
      if (values.length < rule.inquiryPolicy.count) return null;
      const percentile =
        rule.inquiryPolicy.mode === "best_one"
          ? Math.max(...values)
          : values.reduce((sum, value) => sum + value, 0) / values.length;
      parts.push({ subject, percentile });
      continue;
    }

    const percentile = scores.bySubject.get(subject)?.percentile;
    if (percentile === undefined) return null;
    parts.push({ subject, percentile });
  }

  if (parts.length < policy.count) return null;
  return parts
    .sort((a, b) => b.percentile - a.percentile)
    .slice(0, policy.count);
}

function unsupported(unitId: string): ConvertedScore {
  return {
    unitId,
    convertedScore: null,
    method: "unsupported",
    scale: null,
    approximations: [],
  };
}
