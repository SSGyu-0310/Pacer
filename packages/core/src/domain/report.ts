/** LLM 리포트 입력/출력 도메인 타입 (§11.2 / §11.3). 전송계층 스키마와 별개로 도메인에서 보유. */
import type { Band, Confidence, ReportType } from "@pacer/shared";
import type { CrossAgreement } from "./entities";

export type LlmSubjectRole = "strength" | "caution" | "neutral";

/** docs/pacer_report_prompt_v2.md §1 — 엔진이 AI에 넘기는 포지션 리포트 데이터 객체 */
export interface LlmPositionReportData {
  /** 목표 미설정이면 전체 모집단위 기준 탐색, 목표가 있으면 타깃 기준 리포트 */
  scope: "exploration" | "targeted";
  season: {
    current: string;
    next: string | null;
    sampleConfidence: "low" | "medium" | "high";
  };
  metric: {
    mode: "percentile" | "converted";
    myValue: number | null;
    label: string;
    cutLabel: string;
  };
  subjects: {
    name: string;
    metric: "백분위" | "등급" | "표준점수";
    value: number;
    role: LlmSubjectRole;
    note?: string;
  }[];
  lines: {
    univ: string;
    dept: string;
    group: string;
    keyWeight: string | null;
    myValue: number | null;
    cut: number | null;
    gap: number;
    tier: string;
    reliability: "high" | "mid" | "low" | "limited";
  }[];
  scenarios: {
    lever: string;
    delta: number;
    unlocks: string;
  }[];
}

/**
 * §11.2 trend — 엔진(analyzeTrend)이 계산한 변화 요약.
 * LLM은 이 수치를 설명만 한다(§8.1). 점수·구간 계산을 위임하지 않는다.
 */
export interface LlmTrendSummary {
  prevExamType: string;
  improvedSubjects: string[];
  declinedSubjects: string[];
  subjectDeltas: {
    subject: string;
    metric: string;
    prev: number;
    curr: number;
    delta: number;
  }[];
  enteredCount: number;
  droppedCount: number;
  bandImprovedCount: number;
  bandDeclinedCount: number;
  targetApproach: { prev: string; curr: string; direction: string };
}

/** §11.2 교차검증 입력(§7.7.4) — 엔진(crossValidate)이 계산한 일치도 요약 */
export interface LlmCompetitorComparison {
  totals: Record<CrossAgreement, number>;
  /** 불일치 우선, 최대 10건 — 프롬프트 비대 방지 */
  items: {
    university: string;
    unitName: string;
    provider: string;
    valueType: string;
    value: string;
    internalBand: string | null;
    externalBand: string | null;
    agreement: CrossAgreement;
  }[];
}

/** §11.2 프롬프트 입력 구조 */
export interface LlmReportInput {
  reportType: ReportType;
  userContext: {
    role: string;
    examType: string;
    gradeStatus: string;
    riskProfile: string;
  };
  scoreSummary: {
    strengthSubjects: string[];
    weaknessSubjects: string[];
    /** P1 — 6모↔9모 변화(september_change_report에서 채워짐) */
    trend: LlmTrendSummary | null;
  };
  analysisSummary: {
    bandDistribution: Record<Band, number>;
    topReasonCodes: string[];
  };
  targetSummary: {
    targetUniversities: string[];
    targetDistance: Confidence | Band | string;
  };
  /** v2 포지션 리포트: 숫자·라인·과목 데이터. LLM은 이 객체 밖 값을 만들 수 없다. */
  positionReport: LlmPositionReportData | null;
  /** P2 — 외부 도구 교차검증(cross_validation_report에서 채워짐) */
  competitorComparison?: LlmCompetitorComparison | null;
  warnings: string[];
}

/** §11.3 리포트 출력 구조 */
export interface ReportFinding {
  title: string;
  description: string;
  reasonCode: string;
}
export interface ReportContent {
  oneLineSummary: string;
  studentSummary: string;
  parentSummary: string;
  /** 화면 숫자 패널/지원 라인 렌더링용 결정론적 데이터. LLM 생성물이 아니다. */
  positionReport?: LlmPositionReportData | null;
  strengths: ReportFinding[];
  weaknesses: ReportFinding[];
  recommendedActions: string[];
  warnings: string[];
  nextCta: string;
}

/** §9.13 저장된 전략 리포트 — 재방문/공유 복원용 */
export interface StrategyReport {
  id: string;
  cycleId: string;
  examScoreId: string;
  reportType: ReportType;
  content: ReportContent;
  modelName: string;
  promptVersion: string;
  createdAt: Date;
}
