/**
 * 엔진 캘리브레이션 상수 — 한 곳에 모은다.
 *
 * ★ 아래 수치는 P0 초기 캘리브레이션 값이다. 실데이터(§9.9 HistoricalOutcome)가
 * 쌓이면 이 파일만 조정한다. 함수 본문에 매직 넘버를 두지 않는다.
 */

/** 점수 범위 (§18.1 검증) */
export const SCORE_RANGE = {
  standardScore: { min: 0, max: 200 },
  percentile: { min: 0, max: 100 },
  grade: { min: 1, max: 9 },
  rawScore: { min: 0, max: 100 },
} as const;

/** 정규화: 강·약점 판정 — 백분위 평균 대비 ±델타 */
export const STRENGTH_DELTA = 2;
/** 영어(절대평가): 이 등급 이하면 강점, 이상이면 약점 */
export const ENGLISH_STRENGTH_MAX_GRADE = 1;
export const ENGLISH_WEAKNESS_MIN_GRADE = 4;

/** 과탐 과목 목록(탐구 계열 제한 판정용) */
export const SCIENCE_INQUIRY_SUBJECTS: readonly string[] = [
  "물리학Ⅰ",
  "물리학Ⅱ",
  "화학Ⅰ",
  "화학Ⅱ",
  "생명과학Ⅰ",
  "생명과학Ⅱ",
  "지구과학Ⅰ",
  "지구과학Ⅱ",
];

/** 과목별 기준 만점(basis): 표준점수 / 백분위 */
export const BASIS_MAX = { standard: 200, percentile: 100 } as const;

/** 근사 비교(§8.2)의 만점 — 백분위 합성이므로 100 */
export const APPROX_SCALE = 100;

/** 영어 비율반영(ratio) 시 byGrade 환산점수의 기본 만점 — scoreMax 미지정 시 사용 */
export const ENGLISH_RATIO_DEFAULT_MAX = 100;

/**
 * 구간 분류 기본 임계값 (§8.3) — gap을 만점 100 기준으로 정규화한 값(gapPer100).
 * gapPer100 = score_gap / totalScale * 100 (+ 보정치)
 */
export const BAND_THRESHOLDS_PER100 = {
  stable: 1.5,
  match: -0.5,
  reach: -1.5,
  challenge: -3.0,
} as const;

/** 구간 분류 보정치(만점 100 기준, 음수 = 보수적으로) — §8.3 보정 요소 */
export const BAND_ADJUSTMENTS = {
  /** 모집인원 20% 이상 감소 */
  quotaCut: { threshold: -0.2, adjust: -0.5 },
  /** 모집인원 20% 이상 증가 */
  quotaUp: { threshold: 0.2, adjust: 0.3 },
  /** 충원율 100% 이상(실질 컷 하락 경향) */
  highAdditionalPass: { threshold: 1.0, adjust: 0.5 },
  /** 소수 모집단위 */
  smallQuota: -0.5,
  /** 영어 감점 강한 대학 + 사용자 영어 3등급 이하 */
  englishPenalty: { minGrade: 3, minSpreadPer100: 1.0, adjust: -0.5 },
  /** 탐구 변표 리스크 */
  scienceConversion: -0.3,
  /** 시험 시점(6모/9모는 표본·N수생 유입 차이로 보수적) */
  examTiming: { june_mock: -0.3, september_mock: -0.15, csat: 0 },
  /** 데이터 신뢰도 낮음 */
  lowConfidence: -0.3,
} as const;

/** 소수 모집단위 기준(명) — §8.3 */
export const SMALL_QUOTA_THRESHOLD = 10;

/** reason code 판정 기준 (§8.5) */
export const REASON_THRESHOLDS = {
  /** 이 비율 이상 반영하면 '반영비 유리/탐색' 대상 */
  weightAdvantageMin: 0.35,
  /** 탐구 안정: 두 과목 모두 이 백분위 이상 */
  inquiryStableMinPercentile: 85,
  /** 탐구 안정: 두 과목 백분위 차이 허용치 */
  inquiryStableMaxDiff: 5,
  /** 영어 감점이 '낮다'고 보는 1↔3등급 차이(만점 100 기준) */
  englishLowSpreadPer100: 0.5,
  /** 영어 감점 위험으로 보는 1↔3등급 차이(만점 100 기준) */
  englishRiskSpreadPer100: 1.0,
  /** 영어 감점 위험을 경고할 사용자 최소 등급 */
  englishRiskMinGrade: 3,
} as const;

/** 소수점 반올림(결정성 보장) */
export function round2(n: number): number {
  return Math.round(n * 100) / 100;
}

// ---------------------------------------------------------------------------
// P1 — 시뮬레이션 (§7.9)
// ---------------------------------------------------------------------------

/**
 * 상대평가 9등급제 누적 백분위 하한 (1~8등급; 9등급은 나머지).
 * 1등급 상위 4% → 백분위 ≥96, 2등급 상위 11% → ≥89, …
 * 백분위 조정 시 등급을 결정적으로 재산출하는 데 쓴다.
 */
export const GRADE_PERCENTILE_FLOORS: readonly number[] = [
  96, 89, 77, 60, 40, 23, 11, 4,
];

// ---------------------------------------------------------------------------
// P2 — 외부 도구 교차검증 (§7.7.4) 휴리스틱 v1
// ★ 외부 도구 등급 체계의 보수적 근사일 뿐 정밀 매핑이 아니다. 실데이터가
//   쌓이면 이 테이블만 캘리브레이션한다. "어느 쪽이 더 정확"하다는 판정에
//   쓰지 않는다(§11.1) — 일치/불일치 분류에만 쓴다.
// ---------------------------------------------------------------------------

/** 진학사 칸수(1~8) → 구간 근사 */
export const KANSU_TO_BAND: Record<number, "stable" | "match" | "reach" | "challenge" | "risk"> = {
  8: "stable",
  7: "stable",
  6: "match",
  5: "match",
  4: "reach",
  3: "challenge",
  2: "risk",
  1: "risk",
};

/** 고속성장 색상 표기(사용자 자유 입력 정규화) → 구간 근사 */
export const GOSOK_COLOR_TO_BAND: Record<string, "stable" | "match" | "reach" | "challenge" | "risk"> = {
  빨강: "stable",
  빨간색: "stable",
  red: "stable",
  주황: "match",
  주황색: "match",
  orange: "match",
  노랑: "reach",
  노란색: "reach",
  yellow: "reach",
  초록: "challenge",
  초록색: "challenge",
  green: "challenge",
  파랑: "risk",
  파란색: "risk",
  blue: "risk",
};

/** 텔레그노시스 확률(%) → 구간 근사 하한 */
export const PROBABILITY_BAND_FLOORS: readonly {
  min: number;
  band: "stable" | "match" | "reach" | "challenge" | "risk";
}[] = [
  { min: 85, band: "stable" },
  { min: 65, band: "match" },
  { min: 45, band: "reach" },
  { min: 25, band: "challenge" },
  { min: 0, band: "risk" },
];

// ---------------------------------------------------------------------------
// P2 — 가/나/다군 조합 전략 매트릭스 (§7.10)
// ---------------------------------------------------------------------------

/** 전략별 군당 목표 구간 (§7.10 표 그대로) */
export const STRATEGY_BAND_MATRIX = {
  stable: { ga: "stable", na: "match", da: "reach" },
  balanced: { ga: "match", na: "match", da: "reach" },
  aggressive: { ga: "stable", na: "reach", da: "challenge" },
} as const;

/** 조합 전체 리스크 판정: 군별 구간 인덱스(안정0~위험4) 평균 임계 */
export const PLAN_RISK_THRESHOLDS = { low: 1.0, medium: 2.0 } as const;
