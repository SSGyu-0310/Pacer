/**
 * 도메인 엔티티/값객체 — Prisma 모델이 아니다 (§01-architecture 원칙 5).
 * 서비스·엔진은 이 타입들로 일한다. 인프라(packages/db)가 ↔ Prisma 매핑을 담당.
 */
import type {
  Band,
  Channel,
  CompetitorProvider,
  CompetitorValueType,
  Confidence,
  ExamType,
  GradeStatus,
  NotificationEvent,
  OutcomeResult,
  PlanType,
  PlatformHint,
  ReasonCode,
  RecruitmentGroup,
  RiskProfile,
  ScoreStatus,
  ScoreType,
  Subject,
  SusiJungsiPreference,
  Track,
  VerifiedStatus,
} from "@pacer/shared";

export interface Cycle {
  id: string;
  userId: string | null;
  anonSessionId: string | null;
  admissionYear: number;
  gradeStatus: GradeStatus;
  track: Track;
}

export interface SubjectScoreValue {
  subject: Subject;
  selection?: string;
  rawScore?: number;
  standardScore?: number;
  percentile?: number;
  grade?: number;
}

export interface ScoreInput {
  examType: ExamType;
  scoreStatus: ScoreStatus;
  scores: SubjectScoreValue[];
}

export interface ExamScore extends ScoreInput {
  id: string;
  cycleId: string;
}

export interface TargetSnapshot {
  cycleId: string;
  examType: ExamType;
  targetUniversities: string[];
  targetUniversityIds: string[];
  targetMajorGroups: string[];
  targetUnitIds: string[];
  preferredRegions: string[];
  riskProfile: RiskProfile;
  susiJungsiPreference: SusiJungsiPreference;
}

/** 분석 후보 모집단위(레퍼런스 데이터에서 로드) */
export interface AdmissionUnitRef {
  unitId: string;
  university: string;
  unitName: string;
  recruitmentGroup: RecruitmentGroup;
}

/** 환산 결과 (§8.2) */
export type ConversionMethod = "exact" | "relative" | "approx" | "unsupported";
export interface ConvertedScore {
  unitId: string;
  convertedScore: number | null;
  method: ConversionMethod;
  /** 환산 만점(구간 분류 시 gap 정규화에 사용). unsupported면 null. */
  scale: number | null;
  /** 근사 처리된 부분(예: 탐구 변표 근사). 신뢰도 산출에 사용. */
  approximations: string[];
}

/** 분석 결과의 비교 지표. converted는 대학 환산점수, percentile은 백분위 평균 기준 비교다. */
export type ComparisonMetricMode = "converted" | "percentile";

// ---------------------------------------------------------------------------
// 레퍼런스 데이터 도메인 표현 (§9.8 AdmissionRule / §9.9 HistoricalOutcome)
// Prisma 모델이 아니라 엔진이 소비하는 형태다. ★ 서버 전용 — 클라이언트 노출 금지(§8.1).
// ---------------------------------------------------------------------------

/**
 * 영어 절대평가 정책 (§9.8 english_policy_json).
 * - deduction/addition: 국·수·탐 가중평균과 분리해 등급별 점수를 감점/가산(환산 만점 단위).
 * - ratio: 영어를 국·수·탐처럼 반영비(weight)를 가진 한 과목으로 가중평균에 합산(대부분 대학).
 *   byGrade는 등급→환산점수, scoreMax는 그 점수의 만점(정규화용, 미지정 시 100).
 */
export interface EnglishPolicy {
  mode: "deduction" | "addition" | "ratio";
  byGrade: Record<number, number>;
  /** ratio 전용: 영어 반영비 (weights와 같은 단위 — 합산 시 weightSum에 포함) */
  weight?: number;
  /** ratio 전용: byGrade 환산점수의 만점 (미지정 시 ENGLISH_RATIO_DEFAULT_MAX) */
  scoreMax?: number;
}

/** 한국사 정책 (§9.8 history_policy_json) — 등급별 감점/가산(환산 만점 단위 점수) */
export interface HistoryPolicy {
  /** 미지정 시 기존 데이터 호환을 위해 deduction으로 해석한다. */
  mode?: "deduction" | "addition";
  byGrade: Record<number, number>;
}

/** 탐구 반영 정책 (§9.8 inquiry_policy_json) */
export interface InquiryConversionTable {
  /** 현재 지원 범위: 수능 백분위 → 대학 자체 변환표준점수. */
  from: "percentile";
  /** 변환표준점수 만점. 미지정 시 표준점수 만점(200)으로 해석한다. */
  scoreMax?: number;
  /** 백분위 정수값 → 대학 변환표준점수. */
  byPercentile: Record<number, number>;
}

export interface InquiryPolicy {
  /** 반영 과목 수 */
  count: 1 | 2;
  /** 평균 반영 / 상위 1과목 반영 / 합산 반영 (§18.1) */
  mode: "average" | "best_one" | "sum";
  /** 대학 자체 탐구 변환표준점수표. 있으면 탐구 표준점수 대신 표 값을 반영한다. */
  conversionTable?: InquiryConversionTable;
  /** 변환표준점수 리스크(변표 미공개·변동 큼) — §8.3 보정, science_conversion_risk */
  conversionRisk?: boolean;
}

/** 과목 반영비 (합 ≈ 1, 영어는 정책으로 별도 처리) */
export interface SubjectWeights {
  korean: number;
  math: number;
  inquiry: number;
}

export interface SubjectScoreMaxes {
  korean?: number;
  math?: number;
  inquiry?: number;
}

export interface SubjectBaseScores {
  korean?: number;
  math?: number;
  inquiry?: number;
}

export type SubjectScoreMetric = "standardScore" | "percentile";

export interface SubjectScoreTypes {
  korean?: SubjectScoreMetric;
  math?: SubjectScoreMetric;
  inquiry?: SubjectScoreMetric;
}

export interface SubjectAdjustmentPolicy {
  subject: "korean" | "math" | "inquiry";
  /** 적용 조건. 예: 수학 미적분/기하 가산이면 requiredSelections로 제한한다. */
  requiredSelections?: string[];
  /** 탐구 가산 조건. 예: 과탐 응시자 가산. */
  requiredInquiryCategory?: "science" | "social";
  /** 예: 과탐 2과목 모두 응시한 경우에만 탐구 가산 적용. */
  requiredInquiryCategoryCount?: 1 | 2;
  /** 점수 basis 배율. 예: 5% 가산이면 1.05. */
  multiplier?: number;
  /** 점수 basis에 더할 고정점. 예: 과탐 조정점수 +3. */
  points?: number;
  /** true면 조정 후 과목 basis 만점을 넘지 않게 자른다. 기본값은 초과 허용. */
  capAtMax?: boolean;
}

export interface FinalScoreAdjustmentPolicy {
  subject: "korean" | "math" | "inquiry";
  /** 적용 조건. 예: 수학 미적분/기하 표준점수의 7% 가산. */
  requiredSelections?: string[];
  /** 탐구 가산 조건. 예: 사탐/과탐 백분위의 3%를 최종점에 더함. */
  requiredInquiryCategory?: "science" | "social";
  /** 예: 과탐 2과목 모두 응시한 경우에만 가산 적용. */
  requiredInquiryCategoryCount?: 1 | 2;
  /** 최종점에 더할 원점수 출처. */
  pointsFrom: "standardScore" | "percentile";
  /** 최종점 가산 배율. 예: 백분위 83의 3%면 0.03. */
  multiplier: number;
  /** 해당 조정 정책으로 더할 수 있는 최대 점수. */
  maxPoints?: number;
}

export interface FormulaRequiredInputPolicy {
  /**
   * 산식 계산에 필요하지만 현재 사용자 점수/고정 rule만으로는 채울 수 없는 공식 입력값.
   * 예: 전남대식 "영역별 전국 최고 표준점수"는 수능 이후에야 확정된다.
   */
  kind: "national_max_standard_score" | "conversion_table" | "other";
  subjects?: Array<"korean" | "math" | "inquiry">;
  label?: string;
  availability?: "post_csat" | "manual" | "unavailable";
}

export interface SubjectSelectionGroup {
  count: 1 | 2 | 3 | 4;
  subjects: Array<"korean" | "math" | "english" | "inquiry">;
  /** 후보 중 반드시 포함해야 하는 과목. 예: 수학 필수 포함 우수 3영역. */
  requiredSubjects?: Array<"korean" | "math" | "english" | "inquiry">;
  /** 그룹 안에서 선택된 과목을 성적 내림차순으로 정렬한 뒤 적용할 순위별 반영비 */
  rankWeights: number[];
}

/** 상위 과목 선택식 (§9.8 formula_json.selectionPolicy) */
export interface SubjectSelectionPolicy {
  mode: "best_n_subjects";
  count: 1 | 2 | 3 | 4;
  subjects: Array<"korean" | "math" | "english" | "inquiry">;
  /**
   * 후보 중 반드시 포함해야 하는 과목.
   * 예: "수학 포함 우수 3영역"은 requiredSubjects:["math"] + count:3.
   */
  requiredSubjects?: Array<"korean" | "math" | "english" | "inquiry">;
  /**
   * 선택된 과목을 성적 내림차순으로 정렬한 뒤 적용할 순위별 반영비.
   * 예: 우수 4영역 순 40/30/20/10이면 [40, 30, 20, 10].
   * 없으면 기존 동작처럼 선택 과목 단순 평균을 사용한다.
   */
  rankWeights?: number[];
  /**
   * 서로 다른 후보 과목 묶음을 따로 정렬하는 선택식.
   * 예: 가천대 일반식은 국/수 우수순 40/30 + 영/탐 우수순 20/10.
   */
  groups?: SubjectSelectionGroup[];
}

export interface FormulaAlternativePolicy {
  /** 대체 산식별 결합 방식. 미지정 시 기본 산식 방식을 따른다. */
  calculationMode?: "weighted_average" | "weighted_sum" | "normalized_sum";
  /** 대체 산식의 국어/수학/탐구 반영비. 미지정 정책은 기본 산식을 재사용한다. */
  weights: SubjectWeights;
  /** 대체 산식별 총점이 다른 특수 케이스. 보통은 rule.totalScale을 사용한다. */
  totalScale?: number;
  /** 대체 산식에 비수능 구성요소가 있을 때 전체 전형에서 수능이 차지하는 공식 반영비. */
  csatWeight?: number;
  /** 대체 산식별 과목 점수 기준이 다를 때만 지정한다. */
  subjectScoreTypes?: SubjectScoreTypes;
  /** 대체 산식별 과목 원점수 만점이 다를 때만 지정한다. */
  subjectScoreMaxes?: SubjectScoreMaxes;
  /** 대체 산식별 과목 기본점수가 다를 때만 지정한다. */
  subjectBaseScores?: SubjectBaseScores;
  /** 대체 산식 안에서 우수영역 선택식이 다를 때만 지정한다. */
  selectionPolicy?: SubjectSelectionPolicy;
  /** 대체 산식별 가산 정책이 다를 때만 지정한다. */
  subjectAdjustments?: SubjectAdjustmentPolicy[];
  /** 대체 산식별 최종점 가산 정책이 다를 때만 지정한다. */
  finalAdjustments?: FinalScoreAdjustmentPolicy[];
  /** 대체 산식 계산에 필요한 미확정/외부 공식 입력값. 있으면 exact를 닫는다. */
  requiredInputs?: FormulaRequiredInputPolicy[];
  /** 대체 산식에 실기·학생부 등 수능 외 구성요소가 있으면 전체 exact는 닫고 수능 파트 상대비교만 허용한다. */
  externalComponents?: ExternalComponentPolicy[];
  /** 대체 산식별 영어 등급 정책이 다를 때만 지정한다. */
  englishPolicy?: EnglishPolicy;
  /** 대체 산식별 한국사 등급 정책이 다를 때만 지정한다. */
  historyPolicy?: HistoryPolicy;
  /** 대체 산식별 탐구 선택/집계 정책이 다를 때만 지정한다. */
  inquiryPolicy?: InquiryPolicy;
  /** 대체 산식별 응시 제한이 다를 때만 지정한다. */
  eligibility?: EligibilityRules;
}

export interface ExternalComponentPolicy {
  kind: "student_record" | "practical" | "interview" | "essay" | "document" | "other";
  /** 공식 반영비. 예: 수능30+실기70이면 practical weight=70. */
  weight: number;
  /** 원문 표기 보존용. 예: "실기", "학생부교과" */
  label?: string;
  /** 해당 점수가 전체 환산에 필수인지. 기본적으로 필수로 해석한다. */
  required?: boolean;
}

/** 지원 가능 조건 (§9.8 eligibility_json) */
export interface EligibilityRules {
  /** 수학 선택 제한(예: ["미적분", "기하"]) — §18.1 */
  requiredMathSelections?: string[];
  /** 탐구 계열 제한 */
  requiredInquiryCategory?: "science" | "social";
  /** 한국사 최저 등급(이 등급 이하만 지원 가능) */
  maxHistoryGrade?: number;
}

/** 엔진이 소비하는 모집단위 환산 규칙 (§9.8) */
export interface AdmissionRuleData {
  unitId: string;
  scoreType: ScoreType;
  /** 환산 만점 (예: 1000, 100) */
  totalScale: number;
  /** 실기·학생부 등 비수능 구성요소가 있을 때 전체 전형에서 수능이 차지하는 공식 반영비. */
  csatWeight?: number;
  /**
   * 과목 결합 방식.
   * - weighted_average(기본): Σ(과목 basis / 과목만점 × 반영비) / 반영비합 × totalScale.
   * - weighted_sum: Σ(과목 basis × 계수) + 영어/한국사/가산점. 서강대식 A/B 직접 가중합에 사용.
   * - normalized_sum: Σ(과목 기본점수 + basis / 과목만점 × 실질반영점수) + 영어/한국사/가산점.
   *   충북대식 "기본점수 + 취득점수 ÷ 최고점 × 실질반영점수" 산식에 사용.
   */
  calculationMode?: "weighted_average" | "weighted_sum" | "normalized_sum";
  weights: SubjectWeights;
  /** 과목별 점수 기준. mixed에서 탐구가 백분위인지 변환표인지 명시할 때 사용한다. */
  subjectScoreTypes?: SubjectScoreTypes;
  /** 국어/수학/탐구 표준점수 또는 변환표준점수의 공식 만점. 미지정 시 기존 200/100 기준. */
  subjectScoreMaxes?: SubjectScoreMaxes;
  /** 국어/수학/탐구 영역별 기본점수. normalized_sum에서만 의미가 있다. */
  subjectBaseScores?: SubjectBaseScores;
  subjectAdjustments?: SubjectAdjustmentPolicy[];
  finalAdjustments?: FinalScoreAdjustmentPolicy[];
  /** 수능 이후 확정되는 전국최고표준점수/변환표 등 미해결 공식 입력값. 있으면 exact를 닫는다. */
  requiredInputs?: FormulaRequiredInputPolicy[];
  selectionPolicy?: SubjectSelectionPolicy;
  formulaAlternatives?: FormulaAlternativePolicy[];
  /**
   * 실기·학생부·면접처럼 현재 사용자 입력(수능 성적)만으로 계산할 수 없는 구성요소.
   * 원문 산식을 잃지 않기 위한 메타데이터이며, 있으면 전체 exact는 닫고
   * 수능 반영구조만으로 low-confidence relative 비교를 허용한다.
   */
  externalComponents?: ExternalComponentPolicy[];
  englishPolicy: EnglishPolicy;
  historyPolicy: HistoryPolicy;
  inquiryPolicy: InquiryPolicy;
  eligibility: EligibilityRules;
  verifiedStatus: VerifiedStatus;
}

/** 전년도 입결 도메인 표현 (§9.9) */
export interface HistoricalRef {
  unitId: string;
  year: number;
  /** 환산점수 기준 컷(정확 환산 비교용) */
  cutScore: number | null;
  /** 백분위 기준 컷(relative/근사 비교용) */
  percentileCut: number | null;
  competitionRate: number | null;
  /** 추가합격 인원 */
  additionalPass: number | null;
  confidence: Confidence;
}

/** 지원 자격 판정 결과 (§8.1-3) */
export type EligibilityFailureCode =
  | "math_selection"
  | "inquiry_category"
  | "history_grade";
export interface EligibilityResult {
  eligible: boolean;
  failures: { code: EligibilityFailureCode; message: string }[];
}

/** 구간 분류 보정 요소 (§8.3) — 서비스가 데이터로부터 계산해 전달한다. */
export interface BandAdjustmentFactors {
  /** 시험 시점(6모/9모는 보수적으로) */
  examType?: ExamType;
  /** 모집인원 변화율 (올해-전년)/전년 */
  quotaChangeRatio?: number | null;
  /** 충원율 = 추가합격 / 모집인원 */
  additionalPassRate?: number | null;
  /** 소수 모집단위 여부 */
  smallQuota?: boolean;
  /** 영어 감점 강도(1↔3등급 차이, 만점 100 기준 환산치) */
  englishPenaltySpreadPer100?: number;
  /** 사용자 영어 등급 */
  userEnglishGrade?: number;
  /** 탐구 변표 리스크 */
  scienceConversionRisk?: boolean;
  /** 데이터 신뢰도(낮으면 '안정' 단정 금지 — §2.1) */
  dataConfidence?: Confidence;
}

/** 정규화 결과 */
export interface NormalizedScores {
  bySubject: Map<Subject, SubjectScoreValue>;
  strengthSubjects: Subject[];
  weaknessSubjects: Subject[];
}

export interface ValidationResult {
  valid: boolean;
  /** 저장/분석을 막아야 하는 오류 */
  errors: string[];
  /** 저장은 가능하나 사용자에게 알릴 사항 */
  warnings: string[];
}

/** 분석 후보 묶음 — UnitRepository가 레퍼런스 데이터에서 로드해 전달 (§17.3-5) */
export interface AnalysisCandidate {
  unit: AdmissionUnitRef;
  /** 검수 상태 무관 최신 규칙. 없으면 분석 불가. */
  rule: AdmissionRuleData | null;
  /** 최신 입결. 없으면 신뢰도 '제한'. */
  historical: HistoricalRef | null;
  /** 올해 모집인원 (§9.7) — 보정요소 계산용 */
  quota: number | null;
  /** 전년 모집인원 — 모집인원 변화율 계산용(데이터 없으면 null) */
  prevQuota: number | null;
}

/** 분석 스냅샷 요약 (§9.10 summary_json) — 분석 불가/자격 미달도 투명하게 집계 */
export interface AnalysisSummary {
  candidates: number;
  analyzed: number;
  /** 지원 자격 미충족으로 제외 */
  ineligible: number;
  /** 환산 불가(규칙 없음·custom·점수 부족) */
  unsupported: number;
  /** 입결 부재 등으로 비교 불가 */
  insufficientData: number;
}

/** 모집단위별 분석 결과 (§9.11) */
export interface UnitAnalysis {
  unit: AdmissionUnitRef;
  /** UI/리포트가 환산점수와 백분위 비교를 혼동하지 않도록 저장하는 지표 메타. */
  metricMode: ComparisonMetricMode;
  metricLabel: string;
  cutLabel: string;
  convertedScore: number | null;
  historicalReferenceScore: number | null;
  scoreGap: number;
  band: Band;
  confidence: Confidence;
  reasonCodes: ReasonCode[];
  warnings: ReasonCode[];
}

/** 분석 스냅샷 메타 — 결과 조회/리포트 생성 소유권 검증용 */
export interface AnalysisSnapshotMeta {
  id: string;
  cycleId: string;
  examScoreId: string;
  snapshotType: "june_position" | "september_change" | "csat_final";
}

/** 알림 구독 저장 입력 (§10.9). 실발송 payload가 아니라 옵트인 기록이다. */
export interface NotificationSubscriptionInput {
  userId: string | null;
  cycleId: string;
  channel: Channel;
  endpointOrAddress: string;
  pushKeys?: { p256dh: string; auth: string };
  platformHint?: PlatformHint;
  eventNames: NotificationEvent[];
}

export interface NotificationSubscription {
  id: string;
  cycleId: string | null;
  channel: Channel;
  endpointOrAddress: string;
  eventNames: NotificationEvent[];
}

// ---------------------------------------------------------------------------
// P1 — 시험 간 변화 분석 (§7.7.2, engine/trend.ts)
// ---------------------------------------------------------------------------

/** 과목별 변화 비교에 쓴 지표 — 두 시험 모두 가진 지표 중 우선순위(백분위 > 표준점수 > 등급) */
export type TrendMetric = "percentile" | "standard_score" | "grade";
export type TrendDirection = "improved" | "declined" | "unchanged";

export interface SubjectTrendEntry {
  subject: Subject;
  metric: TrendMetric;
  prev: number;
  curr: number;
  /** curr − prev (등급은 낮을수록 좋으므로 direction으로 해석) */
  delta: number;
  direction: TrendDirection;
}

export type BandTransitionKind =
  | "entered" // 새로 들어온 후보군 (curr에만 존재)
  | "dropped" // 빠진 후보군 (prev에만 존재)
  | "improved" // 구간이 유리해짐 (예: 소신 → 적정)
  | "declined" // 구간이 불리해짐
  | "unchanged";

export interface UnitBandTransition {
  unit: AdmissionUnitRef;
  prevBand: Band | null;
  currBand: Band | null;
  kind: BandTransitionKind;
}

/** 목표 대학 접근도 — 목표 대학 결과 중 가장 유리한 구간 (§6.4) */
export type TargetApproach = Band | "limited";

export interface TrendAnalysis {
  prevExamType: ExamType;
  currExamType: ExamType;
  subjects: SubjectTrendEntry[];
  improvedSubjects: Subject[];
  declinedSubjects: Subject[];
  transitions: UnitBandTransition[];
  enteredUnits: AdmissionUnitRef[];
  droppedUnits: AdmissionUnitRef[];
  bandImprovedCount: number;
  bandDeclinedCount: number;
  prevBandDistribution: Record<Band, number>;
  currBandDistribution: Record<Band, number>;
  targetApproach: {
    prev: TargetApproach;
    curr: TargetApproach;
    direction: TrendDirection;
  };
}

// ---------------------------------------------------------------------------
// P1 — 점수 시뮬레이션 (§7.9, engine/simulate.ts)
// 가상 점수 → 엔진 재실행. 저장하지 않는 일회성 계산이며 환산식은 노출하지 않는다(§8.1).
// ---------------------------------------------------------------------------

export interface SimulationAdjustment {
  subject: Subject;
  /** 등급 변화. 음수 = 등급 상승(1등급이 최고) */
  gradeDelta?: number;
  percentileDelta?: number;
  standardScoreDelta?: number;
  /** 직접 점수 입력(§7.9) */
  override?: { standardScore?: number; percentile?: number; grade?: number };
}

export interface SimulationUnitChange {
  unit: AdmissionUnitRef;
  fromBand: Band | null;
  toBand: Band | null;
}

export interface SimulationResult {
  baselineDistribution: Record<Band, number>;
  simulatedDistribution: Record<Band, number>;
  /** 적정(match) 이상으로 새로 들어온 모집단위 수 (§7.9 출력) */
  movedToMatchOrBetter: number;
  bandChanges: SimulationUnitChange[];
  targetApproach: { baseline: TargetApproach; simulated: TargetApproach };
  /** 단일 과목 조정만 적용했을 때 구간 개선이 가장 큰 과목 (§7.9 "가장 효율적인 과목") */
  mostEfficientSubject: Subject | null;
  /** 시뮬레이션 후에도 약점 reason code가 남는 과목 (§7.9 "주의할 과목") */
  cautionSubjects: Subject[];
  /** 시뮬레이션 분석 집계(분석 불가/자격 미달 투명 노출 §8.2) */
  summary: AnalysisSummary;
}

// ---------------------------------------------------------------------------
// P2 — 외부 도구 교차검증 (§7.7.4, §9.14) — 수동 입력 전용, 자동 수집 금지
// ---------------------------------------------------------------------------

export interface CompetitorSignalInput {
  examType: ExamType;
  provider: CompetitorProvider;
  unitId: string;
  valueType: CompetitorValueType;
  value: string;
}

export interface CompetitorSignal extends CompetitorSignalInput {
  id: string;
  cycleId: string;
}

/**
 * 외부 도구 결과와 자체 분석의 일치도.
 * agree = 동일 구간, near = 인접 구간, disagree = 2구간 이상 차이,
 * uncertain = 비교 불가(메모/매핑 불가/해당 모집단위 분석 없음).
 */
export type CrossAgreement = "agree" | "near" | "disagree" | "uncertain";

export interface CrossValidationItem {
  unitId: string;
  /** 자체 분석 결과에 있으면 채워진다 */
  unit: AdmissionUnitRef | null;
  provider: CompetitorProvider;
  valueType: CompetitorValueType;
  value: string;
  /** 자체 분석 구간 */
  internalBand: Band | null;
  /** 외부 도구 값의 보수적 구간 근사(휴리스틱 v1 — engine/constants.ts) */
  externalBand: Band | null;
  agreement: CrossAgreement;
}

export interface CrossValidationSummary {
  items: CrossValidationItem[];
  totals: Record<CrossAgreement, number>;
}

// ---------------------------------------------------------------------------
// P2 — 가/나/다군 원서 조합 (§7.10, §9.15, engine/application-plan.ts)
// ---------------------------------------------------------------------------

export type ApplicationGroup = "ga" | "na" | "da";

export interface ApplicationPlanPick {
  group: ApplicationGroup;
  /** 군 내 후보가 없으면 null */
  unit: AdmissionUnitRef | null;
  band: Band | null;
  scoreGap: number | null;
  /** 전략 매트릭스(§7.10)가 요구한 목표 구간 */
  targetBand: Band;
  /** 목표 구간에 후보가 없어 인접 구간으로 대체했는지 */
  fallback: boolean;
}

export interface ApplicationPlanCombination {
  strategy: PlanType;
  picks: Record<ApplicationGroup, ApplicationPlanPick>;
  overallRisk: "low" | "medium" | "high";
  riskiestGroup: ApplicationGroup | null;
  mostStableGroup: ApplicationGroup | null;
  /** 결정적 요약 — §7.10 허용 표현만 사용(단정 금지) */
  summary: string;
  warnings: string[];
}

// ---------------------------------------------------------------------------
// P2/Phase4 — 합불 결과 수집 (§7.11, §9.16) — 데이터 해자
// ---------------------------------------------------------------------------

export interface FinalOutcomeInput {
  unitId: string;
  applied: boolean;
  result: OutcomeResult;
  waitlistNumber?: number | null;
  registered?: boolean | null;
  evidenceFileUrl?: string | null;
}

export interface FinalOutcome extends FinalOutcomeInput {
  id: string;
  cycleId: string;
  waitlistNumber: number | null;
  registered: boolean | null;
  evidenceFileUrl: string | null;
  rewardStatus: string | null;
}

export interface SavedUnitInput {
  cycleId: string;
  unitId: string;
  priority?: number | null;
  memo?: string | null;
}

export interface SavedUnit {
  id: string;
  cycleId: string;
  unitId: string;
  university: string;
  unitName: string;
  recruitmentGroup: RecruitmentGroup;
  priority: number | null;
  memo: string | null;
}
