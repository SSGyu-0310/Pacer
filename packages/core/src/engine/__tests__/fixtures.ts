/** 엔진 테스트 공용 픽스처 — 손계산 가능한 값으로 고정. */
import type {
  AdmissionRuleData,
  HistoricalRef,
  ScoreInput,
} from "../../domain/entities";

/**
 * 기준 성적:
 * 국어 표준 131 / 백분위 93, 수학(미적분) 표준 135 / 백분위 96,
 * 영어 2등급, 한국사 3등급,
 * 탐구1 물리학Ⅰ 표준 67 / 백분위 94, 탐구2 지구과학Ⅰ 표준 65 / 백분위 90
 */
export function baseScores(): ScoreInput {
  return {
    examType: "june_mock",
    scoreStatus: "official",
    scores: [
      { subject: "korean", standardScore: 131, percentile: 93 },
      {
        subject: "math",
        selection: "미적분",
        standardScore: 135,
        percentile: 96,
      },
      { subject: "english", grade: 2 },
      { subject: "history", grade: 3 },
      {
        subject: "inquiry1",
        selection: "물리학Ⅰ",
        standardScore: 67,
        percentile: 94,
      },
      {
        subject: "inquiry2",
        selection: "지구과학Ⅰ",
        standardScore: 65,
        percentile: 90,
      },
    ],
  };
}

/** 표준점수 반영 대학 — 만점 1000, 국30/수40/탐30, 영어 감점(2등급 −2), 한국사 3등급까지 무감점 */
export function standardRule(
  over: Partial<AdmissionRuleData> = {},
): AdmissionRuleData {
  return {
    unitId: "unit-std",
    scoreType: "standard",
    totalScale: 1000,
    weights: { korean: 0.3, math: 0.4, inquiry: 0.3 },
    englishPolicy: {
      mode: "deduction",
      byGrade: { 1: 0, 2: 2, 3: 6, 4: 12, 5: 20 },
    },
    historyPolicy: { byGrade: { 1: 0, 2: 0, 3: 0, 4: 2, 5: 4 } },
    inquiryPolicy: { count: 2, mode: "average" },
    eligibility: {},
    verifiedStatus: "verified",
    ...over,
  };
}

/** 백분위 반영 대학 — 만점 100, 영어 감점(2등급 −0.5), 한국사 3등급 −0.2 */
export function percentileRule(
  over: Partial<AdmissionRuleData> = {},
): AdmissionRuleData {
  return {
    unitId: "unit-pct",
    scoreType: "percentile",
    totalScale: 100,
    weights: { korean: 0.3, math: 0.4, inquiry: 0.3 },
    englishPolicy: {
      mode: "deduction",
      byGrade: { 1: 0, 2: 0.5, 3: 1.5, 4: 3 },
    },
    historyPolicy: { byGrade: { 1: 0, 2: 0, 3: 0.2, 4: 0.5 } },
    inquiryPolicy: { count: 2, mode: "average" },
    eligibility: {},
    verifiedStatus: "verified",
    ...over,
  };
}

/**
 * 영어 비율반영 대학 — 만점 1000, 국30/수30/탐20 + 영어 반영비20(등급→환산점수, 만점 100),
 * 한국사 무감점. 백분위 기준이라 손계산이 쉽다.
 */
export function ratioEnglishRule(
  over: Partial<AdmissionRuleData> = {},
): AdmissionRuleData {
  return {
    unitId: "unit-ratio-eng",
    scoreType: "percentile",
    totalScale: 1000,
    weights: { korean: 30, math: 30, inquiry: 20 },
    englishPolicy: {
      mode: "ratio",
      weight: 20,
      scoreMax: 100,
      byGrade: { 1: 100, 2: 95, 3: 88, 4: 80 },
    },
    historyPolicy: { byGrade: { 1: 0, 2: 0, 3: 0 } },
    inquiryPolicy: { count: 2, mode: "average" },
    eligibility: {},
    verifiedStatus: "verified",
    ...over,
  };
}

/** 혼합 반영 대학 — 국·수 표준 + 탐구 변표(백분위×2 근사) */
export function mixedRule(
  over: Partial<AdmissionRuleData> = {},
): AdmissionRuleData {
  return standardRule({
    unitId: "unit-mixed",
    scoreType: "mixed",
    ...over,
  });
}

export function historicalRef(
  over: Partial<HistoricalRef> = {},
): HistoricalRef {
  return {
    unitId: "unit-std",
    year: 2025,
    cutScore: 560,
    percentileCut: 92,
    competitionRate: 5.2,
    additionalPass: 12,
    confidence: "high",
    ...over,
  };
}
