/**
 * reason code → 한국어 설명 (§8.5 × §11.5 허용 표현).
 * 스텁 클라이언트와 프롬프트 컨텍스트에 공용. 단정 표현 금지(§11.4):
 * "반드시", "100%", "합격 보장" 등은 여기 어떤 문구에도 쓰지 않는다.
 */
import type { ReasonCode } from "@pacer/shared";

export interface ReasonLabel {
  title: string;
  description: string;
}

export const REASON_LABELS: Record<ReasonCode, ReasonLabel> = {
  // 강점 (§8.5)
  math_weight_advantage: {
    title: "수학 반영비 유리",
    description:
      "수학 성적이 상대적으로 좋아, 수학 반영 비중이 높은 대학에서 유리하게 작용할 수 있습니다.",
  },
  korean_weight_advantage: {
    title: "국어 반영비 유리",
    description:
      "국어 성적이 상대적으로 좋아, 국어 반영 비중이 높은 대학에서 유리하게 작용할 수 있습니다.",
  },
  english_low_penalty_advantage: {
    title: "영어 감점 부담 낮음",
    description:
      "영어 등급별 감점이 작은 대학에서는 현재 영어 등급의 부담이 줄어들 수 있습니다.",
  },
  science_stable: {
    title: "탐구 안정적",
    description: "탐구 두 과목의 성적이 고르게 안정적입니다.",
  },
  percentile_fit: {
    title: "백분위 반영 적합",
    description: "백분위 기준으로 반영하는 대학에서 현재 성적 구조가 적합합니다.",
  },
  standard_score_fit: {
    title: "표준점수 반영 적합",
    description: "표준점수 기준으로 반영하는 대학에서 현재 성적 구조가 적합합니다.",
  },
  target_improved: {
    title: "목표 접근도 상승",
    description: "직전 시험 대비 목표 대학 접근도가 상승했습니다.",
  },
  // 약점 (§8.5)
  english_penalty_risk: {
    title: "영어 감점 위험",
    description:
      "영어 등급에 따른 감점이 큰 대학에서는 불리하게 작용할 수 있습니다. 지원 전 등급별 감점 기준 확인이 필요합니다.",
  },
  science_conversion_risk: {
    title: "탐구 변환표준점수 리스크",
    description:
      "탐구 변환표준점수가 아직 확정되지 않아 결과가 달라질 변동 가능성이 있습니다.",
  },
  math_requirement_fail: {
    title: "수학 선택과목 제한",
    description:
      "일부 모집단위는 수학 선택과목 제한이 있어 지원 자격에 리스크가 있습니다. 모집요강 확인이 필요합니다.",
  },
  low_data_confidence: {
    title: "데이터 신뢰도 낮음",
    description:
      "일부 결과는 근사 계산 기반이라 신뢰도가 낮습니다. 참고용으로 활용하시고 교차검증이 필요합니다.",
  },
  small_quota_risk: {
    title: "소수 모집단위 리스크",
    description:
      "모집인원이 적은 모집단위는 지원자 표본에 따라 결과 변동 가능성이 큽니다.",
  },
  high_volatility: {
    title: "변동성 큼",
    description: "경쟁률·입결 변동 폭이 커서 전년도 기준과 다르게 움직일 수 있습니다.",
  },
  target_declined: {
    title: "목표 접근도 하락",
    description: "직전 시험 대비 목표 대학 접근도가 하락했습니다.",
  },
  // 추천 (§8.5)
  explore_math_heavy: {
    title: "수학 반영비 높은 대학 탐색",
    description: "수학 반영 비중이 높은 대학을 추가로 살펴보면 선택지가 넓어질 수 있습니다.",
  },
  avoid_english_penalty: {
    title: "영어 감점 큰 대학 주의",
    description: "영어 감점이 큰 대학은 지원 전 등급별 감점표를 함께 확인해 주세요.",
  },
  simulate_math_up: {
    title: "수학 상승 시뮬레이션",
    description: "수학 성적이 오르는 경우의 변화를 시뮬레이션해 보는 것을 권장합니다.",
  },
  simulate_explore_up: {
    title: "탐구 상승 시뮬레이션",
    description: "탐구 성적이 오르는 경우의 변화를 시뮬레이션해 보는 것을 권장합니다.",
  },
  compare_after_jinhak: {
    title: "외부 도구 교차검증",
    description:
      "진학사 등 외부 도구 결과가 공개되면 함께 비교해 교차검증하는 것을 권장합니다.",
  },
  build_application_plan: {
    title: "가/나/다군 조합 구성",
    description: "안정·적정·소신을 섞은 가/나/다군 원서 조합 구성이 필요합니다.",
  },
};
