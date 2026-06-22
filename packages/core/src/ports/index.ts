/**
 * 포트(인터페이스)만 — core가 인프라를 향하지 않게 하는 경계.
 * 구현(어댑터)은 packages/db, packages/llm, packages/notifications 에 산다.
 * 런타임 조립은 apps/web 의 composition root 에서.
 */
import type {
  Band,
  Channel,
  Confidence,
  ExamType,
  PlanType,
  ReportType,
  ReviewDecisionKind,
  ReviewVerdict,
  SnapshotType,
  VerifiedStatus,
} from "@pacer/shared";
import type {
  AnalysisCandidate,
  AnalysisSnapshotMeta,
  AnalysisSummary,
  ApplicationPlanCombination,
  CompetitorSignal,
  CompetitorSignalInput,
  Cycle,
  ExamScore,
  FinalOutcome,
  FinalOutcomeInput,
  NotificationSubscription,
  NotificationSubscriptionInput,
  SavedUnit,
  SavedUnitInput,
  ScoreInput,
  TargetSnapshot,
  UnitAnalysis,
} from "../domain/entities";
import type { LlmReportInput, ReportContent, StrategyReport } from "../domain/report";

/** 결정적 테스트를 위한 시계 포트 */
export interface Clock {
  now(): Date;
}

export interface CycleRepository {
  create(input: {
    userId: string | null;
    anonSessionId: string | null;
    admissionYear: number;
    gradeStatus: Cycle["gradeStatus"];
    track: Cycle["track"];
  }): Promise<Cycle>;
  findByAnonSessionAndYear(input: {
    anonSessionId: string;
    admissionYear: number;
  }): Promise<Cycle | null>;
  updateProfile(
    id: string,
    input: { gradeStatus: Cycle["gradeStatus"]; track: Cycle["track"] },
  ): Promise<Cycle>;
  findById(id: string): Promise<Cycle | null>;
}

export interface ScoreRepository {
  save(cycleId: string, input: ScoreInput): Promise<ExamScore>;
  findById(examScoreId: string): Promise<ExamScore | null>;
  /** 시험별 성적 — (cycleId, examType)당 1건(§9.3). P1 trend의 이전 시험 로드용. */
  findByExamType(cycleId: string, examType: ExamType): Promise<ExamScore | null>;
}

export interface TargetRepository {
  save(target: TargetSnapshot): Promise<void>;
  findLatest(cycleId: string, examType: ExamType): Promise<TargetSnapshot | null>;
}

export interface UnitRepository {
  /**
   * 분석 후보 모집단위를 규칙·입결과 함께 로드 (§17.3-5).
   * ★ 규칙/입결 원문은 서버 전용 — 클라이언트로 노출 금지 (§8.1).
   */
  loadCandidates(filter: {
    admissionYear: number;
    track: Cycle["track"];
    preferredRegions?: string[];
    targetUniversities?: string[];
  }): Promise<AnalysisCandidate[]>;
}

export interface AnalysisRepository {
  saveSnapshot(input: {
    cycleId: string;
    examScoreId: string;
    snapshotType: SnapshotType;
    summary: AnalysisSummary;
    bandDistribution: Record<Band, number>;
    results: UnitAnalysis[];
  }): Promise<{ snapshotId: string }>;
  /** 스냅샷 메타가 없으면 null */
  findSnapshotMeta(snapshotId: string): Promise<AnalysisSnapshotMeta | null>;
  /** 스냅샷이 없으면 null */
  findResults(snapshotId: string): Promise<UnitAnalysis[] | null>;
  /**
   * 사이클의 최신 스냅샷 메타 (P1 trend·P2 조합용).
   * snapshotType을 주면 그 타입의 최신, 없으면 전체 중 최신.
   */
  findLatestSnapshotMeta(
    cycleId: string,
    snapshotType?: SnapshotType,
  ): Promise<AnalysisSnapshotMeta | null>;
}

export interface ReportRepository {
  save(input: {
    cycleId: string;
    examScoreId: string;
    reportType: ReportType;
    content: ReportContent;
    modelName: string;
    promptVersion: string;
  }): Promise<{ reportId: string }>;
  findById(reportId: string): Promise<StrategyReport | null>;
  findLatestForCycle(cycleId: string): Promise<StrategyReport | null>;
}

/** LLM Gateway 포트 (§11) — 계산하지 않고 설명만 생성 */
export interface LlmReporter {
  generate(input: LlmReportInput): Promise<{
    content: ReportContent;
    modelName: string;
    promptVersion: string;
  }>;
}

/** §9.14 외부 도구 결과 — 수동 입력 전용(자동 수집 금지 §7.7.4) */
export interface CompetitorSignalRepository {
  save(cycleId: string, input: CompetitorSignalInput): Promise<CompetitorSignal>;
  list(cycleId: string, examType?: ExamType): Promise<CompetitorSignal[]>;
}

/** §9.15 원서 조합 저장 */
export interface ApplicationPlanRepository {
  save(input: {
    cycleId: string;
    planType: PlanType;
    gaUnitId: string | null;
    naUnitId: string | null;
    daUnitId: string | null;
    /** summary_json — 엔진이 만든 조합 전체(재현/감사용) */
    combination: ApplicationPlanCombination;
  }): Promise<{ planId: string }>;
}

/** §9.16 합불 결과 수집 — 데이터 해자 */
export interface OutcomeRepository {
  save(cycleId: string, input: FinalOutcomeInput): Promise<FinalOutcome>;
  list(cycleId: string): Promise<FinalOutcome[]>;
}

export interface NotificationSubscriptionRepository {
  upsert(input: NotificationSubscriptionInput): Promise<NotificationSubscription>;
}

export interface SavedUnitRepository {
  save(input: SavedUnitInput): Promise<SavedUnit>;
  list(cycleId: string): Promise<SavedUnit[]>;
}

export interface ReviewQueueItem {
  kind: ReviewDecisionKind;
  id: string;
  universityName: string | null;
  unitName: string | null;
  year: number | null;
  verifiedStatus: VerifiedStatus | null;
  confidence: Confidence | null;
  reviewPriorityScore: number | null;
  reviewStrength: string | null;
  hasAiProposal: boolean;
  uncertain: boolean;
  latestVerdict: ReviewVerdict | null;
  sourceUrl: string | null;
  textPreview: string | null;
  /** 동일 식을 공유하는 모집단위 수(자기 포함). 규칙 클러스터용; 입결은 1. */
  clusterSize: number;
}

export interface ReviewDecisionRecord {
  id: string;
  targetKind: ReviewDecisionKind;
  targetId: string;
  verdict: ReviewVerdict;
  reviewedVerifiedStatus: VerifiedStatus | null;
  reviewedConfidence: Confidence | null;
  correctedFields: Record<string, unknown> | null;
  aiProposalSnapshot: Record<string, unknown> | null;
  evidenceChecked: boolean;
  approvalScopeKey: string | null;
  reviewer: string;
  reviewNotes: string | null;
  reviewedAt: Date;
}

export interface ReviewAiProposalRecord {
  id: string;
  targetKind: ReviewDecisionKind;
  targetId: string;
  promptVersion: string;
  proposalJson: Record<string, unknown>;
  modelName: string;
  createdAt: Date;
}

export interface ReviewItemDetailRecord {
  kind: ReviewDecisionKind;
  id: string;
  universityName: string | null;
  unitName: string | null;
  year: number | null;
  sourceUrl: string | null;
  parsedFields: Record<string, unknown>;
  evidence: Record<string, unknown> | null;
  aiProposal: ReviewAiProposalRecord | null;
  latestDecision: ReviewDecisionRecord | null;
  wouldUnlockExact: boolean | null;
  /** 동일 식을 공유하는 모집단위 수(자기 포함). */
  clusterSize: number;
}

export interface ReviewRecordInput {
  targetKind: ReviewDecisionKind;
  targetId: string;
  verdict: ReviewVerdict;
  reviewedVerifiedStatus?: VerifiedStatus;
  reviewedConfidence?: Confidence;
  correctedFields?: Record<string, unknown>;
  evidenceChecked: boolean;
  approvalScopeKey?: string;
  reviewNotes?: string;
  /** 규칙: 동일 식을 쓰는 같은 대학의 모든 모집단위에 같은 결정을 적용. */
  applyToCluster?: boolean;
}

export interface ReviewQueueFilter {
  kind?: ReviewDecisionKind;
  status?: "pending" | "decided";
  onlyUncertain?: boolean;
  /** 비어 있지 않으면 규칙 큐를 이 대학들로 한정(핵심대 프리셋). */
  coreUniversityIds?: string[];
}

export interface ReviewQueueRepository {
  listQueue(
    filter: ReviewQueueFilter,
  ): Promise<{ items: ReviewQueueItem[]; total: number; pending: number; decided: number }>;
  getItem(kind: ReviewDecisionKind, id: string): Promise<ReviewItemDetailRecord | null>;
  record(
    input: ReviewRecordInput,
  ): Promise<{ decisionId: string; wouldUnlockExact: boolean | null; clusterApplied: number }>;
  bulkConfirm(kind: ReviewDecisionKind, ids: string[]): Promise<{ recorded: number; skipped: number }>;
}

/** 다중 채널 알림 포트 (§17.5) */
export interface Notifier {
  send(channel: Channel, target: string, message: string): Promise<{ delivered: boolean }>;
}
