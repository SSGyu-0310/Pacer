/**
 * API 계약 (§10) — 요청/응답 Zod 스키마.
 *
 * 이것이 "백엔드 분리 이음새"다: apps/web 의 라우트 어댑터와 (추후) 외부 백엔드가
 * 공유하는 단일 계약. 라우트는 여기서 parse → 서비스 호출 → 여기로 serialize 만 한다.
 */
import { z } from "zod";
import {
  band,
  channel,
  competitorProvider,
  competitorValueType,
  examType,
  gradeStatus,
  notificationEvent,
  outcomeResult,
  planType,
  platformHint,
  recruitmentGroup,
  reportType,
  coreReviewTier,
  reviewDecisionKind,
  reviewReviewer,
  reviewVerdict,
  riskProfile,
  scoreStatus,
  scoreType,
  snapshotType,
  subject,
  susiJungsiPreference,
  track,
  verifiedStatus,
  confidence,
} from "./enums";
import { reasonCode as reasonCodeUnion } from "./reason-codes";

/** band_distribution: 구간별 모집단위 수 (§10.4) */
export const bandDistribution = z.object({
  stable: z.number().int().nonnegative(),
  match: z.number().int().nonnegative(),
  reach: z.number().int().nonnegative(),
  challenge: z.number().int().nonnegative(),
  risk: z.number().int().nonnegative(),
});
export type BandDistribution = z.infer<typeof bandDistribution>;

/* ── §10.1 입시 사이클 생성 ── */
export const createCycleRequest = z.object({
  admission_year: z.number().int(),
  grade_status: gradeStatus,
  track,
});
export const createCycleResponse = z.object({
  cycle_id: z.string().uuid(),
  status: z.enum(["created", "reused"]),
});
export const currentCycleResponse = z.object({
  cycle_id: z.string().uuid(),
  admission_year: z.number().int(),
  grade_status: gradeStatus,
  track,
});

/* ── §10.2 성적 저장 ── */
export const subjectScoreInput = z.object({
  subject,
  selection: z.string().optional(),
  raw_score: z.number().optional(),
  standard_score: z.number().optional(),
  percentile: z.number().optional(),
  grade: z.number().int().min(1).max(9).optional(),
});
export const saveScoresRequest = z.object({
  exam_type: examType,
  score_status: scoreStatus,
  scores: z.array(subjectScoreInput).min(1),
});
export const saveScoresResponse = z.object({
  exam_score_id: z.string().uuid(),
  validation: z.object({
    valid: z.boolean(),
    warnings: z.array(z.string()),
  }),
});

/* ── §10.3 목표 저장 ── */
export const saveTargetRequest = z.object({
  exam_type: examType,
  target_universities: z.array(z.string()),
  target_major_groups: z.array(z.string()),
  preferred_regions: z.array(z.string()),
  risk_profile: riskProfile,
  susi_jungsi_preference: susiJungsiPreference,
});

/* ── §10.4 분석 실행 ── */
export const runAnalysisRequest = z.object({
  exam_score_id: z.string().uuid(),
  analysis_type: snapshotType,
});
export const runAnalysisResponse = z.object({
  analysis_snapshot_id: z.string().uuid(),
  status: z.enum(["completed", "processing"]),
  band_distribution: bandDistribution,
});

/* ── §10.5 분석 결과 조회 ── */
export const analysisResultItem = z.object({
  unit_id: z.string().uuid(),
  university: z.string(),
  unit_name: z.string(),
  recruitment_group: recruitmentGroup,
  band,
  confidence: z.enum(["high", "medium", "low", "limited"]),
  score_gap: z.number(),
  reason_codes: z.array(reasonCodeUnion),
  warnings: z.array(reasonCodeUnion),
});
export const analysisResultsResponse = z.object({
  snapshot_id: z.string().uuid(),
  results: z.array(analysisResultItem),
  disclaimer: z.string(),
});

/* ── §10.6 AI 리포트 생성 ── */
export const createReportRequest = z.object({
  exam_score_id: z.string().uuid(),
  report_type: reportType,
  analysis_snapshot_id: z.string().uuid(),
});
export const reportContent = z.object({
  one_line_summary: z.string(),
  student_summary: z.string(),
  parent_summary: z.string(),
  strengths: z.array(
    z.object({ title: z.string(), description: z.string(), reason_code: reasonCodeUnion }),
  ),
  weaknesses: z.array(
    z.object({ title: z.string(), description: z.string(), reason_code: reasonCodeUnion }),
  ),
  recommended_actions: z.array(z.string()),
  warnings: z.array(z.string()),
  next_cta: z.string(),
});
export const createReportResponse = z.object({
  report_id: z.string().uuid(),
  content: reportContent,
  model_name: z.string(),
  prompt_version: z.string(),
  disclaimer: z.string(),
  ai_usage_notice: z.string(),
});

/* ── §7.9 점수 시뮬레이션 (P1) — 가상 점수로 엔진 재실행. 결과만 반환(§8.1) ── */
export const simulationAdjustment = z
  .object({
    subject,
    /** 등급 변화. 음수 = 등급 상승(예: -1 → 한 등급 상승) */
    grade_delta: z.number().int().min(-8).max(8).optional(),
    percentile_delta: z.number().min(-100).max(100).optional(),
    standard_score_delta: z.number().min(-200).max(200).optional(),
    /** 직접 점수 입력(§7.9) — delta 대신 절대값 지정 */
    override: z
      .object({
        standard_score: z.number().min(0).max(200).optional(),
        percentile: z.number().min(0).max(100).optional(),
        grade: z.number().int().min(1).max(9).optional(),
      })
      .optional(),
  })
  .refine(
    (a) =>
      a.grade_delta !== undefined ||
      a.percentile_delta !== undefined ||
      a.standard_score_delta !== undefined ||
      a.override !== undefined,
    { message: "조정값이 최소 하나 필요합니다" },
  );
export const runSimulationRequest = z.object({
  exam_score_id: z.string().uuid(),
  adjustments: z.array(simulationAdjustment).min(1).max(7),
});
const bandOrLimited = z.union([band, z.literal("limited")]);
export const runSimulationResponse = z.object({
  baseline_band_distribution: bandDistribution,
  simulated_band_distribution: bandDistribution,
  /** 적정(match) 이상으로 새로 들어온 모집단위 수 (§7.9 출력) */
  moved_to_match_or_better: z.number().int().nonnegative(),
  band_changes: z.array(
    z.object({
      unit_id: z.string().uuid(),
      university: z.string(),
      unit_name: z.string(),
      from_band: band.nullable(),
      to_band: band.nullable(),
    }),
  ),
  target_approach: z.object({
    baseline: bandOrLimited,
    simulated: bandOrLimited,
  }),
  most_efficient_subject: subject.nullable(),
  caution_subjects: z.array(subject),
  /** §7.9 주의 문구 — 항상 동봉 */
  notice: z.string(),
});

/* ── §10.7 외부 서비스 결과 저장 (수동 입력 전용) ── */
export const createCompetitorSignalRequest = z.object({
  exam_type: examType,
  provider: competitorProvider,
  unit_id: z.string().uuid(),
  value_type: competitorValueType,
  value: z.string().min(1).max(500),
});
export const createCompetitorSignalResponse = z.object({
  signal_id: z.string().uuid(),
  status: z.literal("saved"),
});
export const competitorSignalItem = z.object({
  signal_id: z.string().uuid(),
  exam_type: examType,
  provider: competitorProvider,
  unit_id: z.string().uuid(),
  value_type: competitorValueType,
  value: z.string(),
});
export const listCompetitorSignalsResponse = z.object({
  signals: z.array(competitorSignalItem),
});

/* ── §10.8 원서 조합 생성 ── */
export const createApplicationPlanRequest = z.object({
  plan_type: planType,
  candidate_unit_ids: z.array(z.string().uuid()).min(1),
});
export const applicationPlanResponse = z.object({
  plan_id: z.string().uuid(),
  plans: z.array(
    z.object({
      strategy: planType,
      ga: z.string().uuid().nullable(),
      na: z.string().uuid().nullable(),
      da: z.string().uuid().nullable(),
      summary: z.string(),
    }),
  ),
});

/* ── §7.11/§9.16 합불 결과 수집 (P2/Phase4 데이터 해자) ── */
export const submitOutcomeRequest = z.object({
  unit_id: z.string().uuid(),
  applied: z.boolean(),
  result: outcomeResult,
  waitlist_number: z.number().int().positive().optional(),
  registered: z.boolean().optional(),
  /** 인증자료는 선택 제출(§7.11) — 업로드 후 URL만 전달 */
  evidence_file_url: z.string().url().optional(),
});
export const submitOutcomeResponse = z.object({
  outcome_id: z.string().uuid(),
  status: z.literal("saved"),
});
export const finalOutcomeItem = z.object({
  outcome_id: z.string().uuid(),
  unit_id: z.string().uuid(),
  applied: z.boolean(),
  result: outcomeResult,
  waitlist_number: z.number().int().nullable(),
  registered: z.boolean().nullable(),
});
export const listOutcomesResponse = z.object({
  outcomes: z.array(finalOutcomeItem),
});

/* ── §10.9 알림 구독 등록 (다중 채널) ── */
export const subscribeNotificationRequest = z.discriminatedUnion("channel", [
  z.object({
    channel: z.literal("web_push"),
    subscription: z.object({
      endpoint: z.string().url(),
      keys: z.object({ p256dh: z.string(), auth: z.string() }),
    }),
    platform_hint: platformHint,
    events: z.array(notificationEvent).min(1),
  }),
  z.object({
    channel: z.literal("kakao_alimtalk"),
    phone: z.string(),
    events: z.array(notificationEvent).min(1),
  }),
  z.object({
    channel: z.literal("email"),
    address: z.string().email(),
    events: z.array(notificationEvent).min(1),
  }),
]);
export const subscribeNotificationResponse = z.object({
  subscription_id: z.string().uuid(),
  status: z.literal("subscribed"),
});

/* ── §9.12 관심 모집단위 저장(P0 내부 데모 최소 API) ── */
export const saveAdmissionUnitRequest = z.object({
  unit_id: z.string().uuid(),
  priority: z.number().int().positive().optional(),
  memo: z.string().max(500).optional(),
});
export const savedAdmissionUnitItem = z.object({
  saved_unit_id: z.string().uuid(),
  unit_id: z.string().uuid(),
  university: z.string(),
  unit_name: z.string(),
  recruitment_group: recruitmentGroup,
  priority: z.number().int().nullable(),
  memo: z.string().nullable(),
});
export const saveAdmissionUnitResponse = z.object({
  status: z.literal("saved"),
  saved_unit: savedAdmissionUnitItem,
});
export const listSavedAdmissionUnitsResponse = z.object({
  saved_units: z.array(savedAdmissionUnitItem),
});

/* ── Admin reference-data review tool ── */
const nullableJsonObject = z.record(z.string(), z.unknown()).nullable();

export const aiProposalContract = z.object({
  id: z.string().uuid(),
  target_kind: reviewDecisionKind,
  target_id: z.string().uuid(),
  prompt_version: z.string(),
  model_name: z.string(),
  proposal_json: z.record(z.string(), z.unknown()),
  created_at: z.string(),
});
export type AiProposalContract = z.infer<typeof aiProposalContract>;

export const reviewQueueItem = z.object({
  kind: reviewDecisionKind,
  id: z.string().uuid(),
  university_id: z.string().uuid().nullable(),
  university_name: z.string().nullable(),
  unit_name: z.string().nullable(),
  year: z.number().int().nullable(),
  verified_status: verifiedStatus.nullable(),
  confidence: confidence.nullable(),
  review_priority_score: z.number().int().nullable(),
  review_strength: z.string().nullable(),
  has_ai_proposal: z.boolean(),
  uncertain: z.boolean(),
  latest_verdict: reviewVerdict.nullable(),
  latest_reviewer: z.string().nullable(),
  source_url: z.string().nullable(),
  text_preview: z.string().nullable(),
  cluster_size: z.number().int().nonnegative(),
  core_tier: coreReviewTier.nullable(),
  core_flag: z.string().nullable(),
});
export type ReviewQueueItem = z.infer<typeof reviewQueueItem>;

export const reviewReviewerCounts = z.object({
  shin: z.number().int().nonnegative(),
  kwon: z.number().int().nonnegative(),
  other: z.number().int().nonnegative(),
  pending: z.number().int().nonnegative(),
  total: z.number().int().nonnegative(),
  decided: z.number().int().nonnegative(),
});
export type ReviewReviewerCounts = z.infer<typeof reviewReviewerCounts>;

export const reviewQueueResponse = z.object({
  items: z.array(reviewQueueItem),
  counts: z.object({
    total: z.number().int().nonnegative(),
    pending: z.number().int().nonnegative(),
    decided: z.number().int().nonnegative(),
    reviewer_counts: reviewReviewerCounts,
  }),
});
export type ReviewQueueResponse = z.infer<typeof reviewQueueResponse>;

export const reviewDecisionSnapshot = z.object({
  id: z.string().uuid(),
  target_kind: reviewDecisionKind,
  target_id: z.string().uuid(),
  verdict: reviewVerdict,
  reviewed_verified_status: verifiedStatus.nullable(),
  reviewed_confidence: confidence.nullable(),
  corrected_fields: nullableJsonObject,
  ai_proposal_snapshot: nullableJsonObject,
  evidence_checked: z.boolean(),
  approval_scope_key: z.string().nullable(),
  reviewer: z.string(),
  review_notes: z.string().nullable(),
  reviewed_at: z.string(),
});
export type ReviewDecisionSnapshot = z.infer<typeof reviewDecisionSnapshot>;

export const ruleReviewFields = z.object({
  score_type: scoreType,
  formula_json: z.unknown().nullable(),
  english_policy_json: z.unknown().nullable(),
  history_policy_json: z.unknown().nullable(),
  inquiry_policy_json: z.unknown().nullable(),
  eligibility_json: z.unknown().nullable(),
});

export const outcomeReviewFields = z.object({
  avg_score: z.number().nullable(),
  cut_score: z.number().nullable(),
  percentile_cut: z.number().nullable(),
  competition_rate: z.number().nullable(),
  additional_pass: z.number().int().nullable(),
});

export const reviewItemDetail = z.object({
  kind: reviewDecisionKind,
  id: z.string().uuid(),
  university_name: z.string().nullable(),
  unit_name: z.string().nullable(),
  year: z.number().int().nullable(),
  source_url: z.string().nullable(),
  parsed_fields: z.union([ruleReviewFields, outcomeReviewFields]),
  evidence: z.record(z.string(), z.unknown()).nullable(),
  ai_proposal: aiProposalContract.nullable(),
  latest_decision: reviewDecisionSnapshot.nullable(),
  would_unlock_exact: z.boolean().nullable(),
  cluster_size: z.number().int().nonnegative(),
});
export type ReviewItemDetail = z.infer<typeof reviewItemDetail>;

export const recordReviewDecisionRequest = z.object({
  target_kind: reviewDecisionKind,
  target_id: z.string().uuid(),
  verdict: reviewVerdict,
  reviewed_verified_status: verifiedStatus.optional(),
  reviewed_confidence: confidence.optional(),
  corrected_fields: z.record(z.string(), z.unknown()).optional(),
  evidence_checked: z.boolean().default(false),
  approval_scope_key: z.string().optional(),
  reviewer: reviewReviewer,
  review_notes: z.string().max(2000).optional(),
  apply_to_cluster: z.boolean().default(false),
});
export type RecordReviewDecisionRequest = z.infer<typeof recordReviewDecisionRequest>;

export const recordReviewDecisionResponse = z.object({
  decision_id: z.string().uuid(),
  status: z.literal("recorded"),
  would_unlock_exact: z.boolean().nullable(),
  cluster_applied: z.number().int().nonnegative(),
});
export type RecordReviewDecisionResponse = z.infer<typeof recordReviewDecisionResponse>;

export const bulkConfirmRequest = z.object({
  kind: reviewDecisionKind,
  ids: z.array(z.string().uuid()).min(1).max(200),
  reviewer: reviewReviewer,
});
export type BulkConfirmRequest = z.infer<typeof bulkConfirmRequest>;

export const bulkConfirmResponse = z.object({
  recorded: z.number().int().nonnegative(),
  skipped: z.number().int().nonnegative(),
});
export type BulkConfirmResponse = z.infer<typeof bulkConfirmResponse>;

// 채널 enum 재노출(편의)
export { channel };
