/**
 * UI 라벨/스타일 메타 — 컨트롤드 보캐블러리(@pacer/shared §8.5)의 한국어 표현.
 * 클래스 문자열은 Tailwind 퍼지를 위해 리터럴로 유지한다.
 */

export type Band = "stable" | "match" | "reach" | "challenge" | "risk";
export type Confidence = "high" | "medium" | "low" | "limited";
export type RecruitmentGroup = "ga" | "na" | "da" | "none";

export const BAND_ORDER: readonly Band[] = [
  "stable",
  "match",
  "reach",
  "challenge",
  "risk",
];

export const BAND_META: Record<
  Band,
  { label: string; badge: string; bar: string; dot: string }
> = {
  stable: {
    label: "안정",
    badge: "bg-band-stable-soft text-band-stable-fg",
    bar: "bg-band-stable",
    dot: "bg-band-stable",
  },
  match: {
    label: "적정",
    badge: "bg-band-match-soft text-band-match-fg",
    bar: "bg-band-match",
    dot: "bg-band-match",
  },
  reach: {
    label: "소신",
    badge: "bg-band-reach-soft text-band-reach-fg",
    bar: "bg-band-reach",
    dot: "bg-band-reach",
  },
  challenge: {
    label: "도전",
    badge: "bg-band-challenge-soft text-band-challenge-fg",
    bar: "bg-band-challenge",
    dot: "bg-band-challenge",
  },
  risk: {
    label: "위험",
    badge: "bg-band-risk-soft text-band-risk-fg",
    bar: "bg-band-risk",
    dot: "bg-band-risk",
  },
};

export const CONFIDENCE_META: Record<
  Confidence,
  { label: string; muted: boolean; note?: string }
> = {
  high: { label: "신뢰도 높음", muted: false },
  medium: { label: "신뢰도 중간", muted: false },
  low: { label: "신뢰도 낮음", muted: true, note: "근사 계산 기반 결과입니다" },
  limited: { label: "신뢰도 제한", muted: true, note: "데이터가 부족합니다" },
};

export const GROUP_LABEL: Record<RecruitmentGroup, string> = {
  ga: "가군",
  na: "나군",
  da: "다군",
  none: "군외",
};

const REASON_LABELS: Record<string, string> = {
  // 강점 (§8.5)
  math_weight_advantage: "수학 반영비 유리",
  korean_weight_advantage: "국어 반영비 유리",
  english_low_penalty_advantage: "영어 감점 부담 낮음",
  science_stable: "탐구 안정적",
  percentile_fit: "백분위 반영 적합",
  standard_score_fit: "표준점수 반영 적합",
  target_improved: "목표 접근도 상승",
  // 약점
  english_penalty_risk: "영어 감점 위험",
  science_conversion_risk: "탐구 변표 리스크",
  math_requirement_fail: "수학 선택과목 제한",
  low_data_confidence: "데이터 신뢰도 낮음",
  small_quota_risk: "소수 모집 리스크",
  high_volatility: "변동성 큼",
  target_declined: "목표 접근도 하락",
  // 추천
  explore_math_heavy: "수학 반영비 대학 탐색",
  avoid_english_penalty: "영어 감점 큰 대학 주의",
  simulate_math_up: "수학 상승 시뮬레이션",
  simulate_explore_up: "탐구 상승 시뮬레이션",
  compare_after_jinhak: "외부 도구 교차검증",
  build_application_plan: "원서 조합 필요",
};

export function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code;
}
