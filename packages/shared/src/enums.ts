/**
 * 컨트롤드 보캐블러리 — 단일 진실 공급원 (spec §8.x, §9, §11, CLAUDE.md).
 *
 * 규칙: 이 enum 값들은 여기에서만 정의한다. 어디서도 임의 문자열을 쓰지 않는다.
 * 새 값이 필요하면 이 파일(과 reason-codes.ts)을 확장한다.
 */
import { z } from "zod";

/** 시험 종류 (§9.3) */
export const examType = z.enum(["june_mock", "september_mock", "csat"]);
export type ExamType = z.infer<typeof examType>;

/** 성적 확정 상태 (§9.3) */
export const scoreStatus = z.enum(["estimated", "official"]);
export type ScoreStatus = z.infer<typeof scoreStatus>;

/** 구간 (§8.3) — 안정/적정/소신/도전/위험 */
export const band = z.enum(["stable", "match", "reach", "challenge", "risk"]);
export type Band = z.infer<typeof band>;

/** 신뢰도 (§8.4) — 높음/중간/낮음/제한 */
export const confidence = z.enum(["high", "medium", "low", "limited"]);
export type Confidence = z.infer<typeof confidence>;

/** 리포트 타입 (§9.13, §7.7) */
export const reportType = z.enum([
  "june_position_report",
  "september_change_report",
  "csat_final_report",
  "cross_validation_report",
  "parent_summary_report",
  "application_plan_report",
]);
export type ReportType = z.infer<typeof reportType>;

/** 알림 채널 (§17.5) — 우선순위 1) 알림톡 2) 이메일 3) 웹푸시 */
export const channel = z.enum(["kakao_alimtalk", "email", "web_push"]);
export type Channel = z.infer<typeof channel>;

/** 알림 구독 이벤트 (§10.9) — P0는 9모 오픈/심화분석 예고 리마인더만 저장한다. */
export const notificationEvent = z.enum([
  "september_mock_open",
  "september_paid_preview",
]);
export type NotificationEvent = z.infer<typeof notificationEvent>;

/** 채널 발송 우선순위 (낮을수록 먼저) — §17.5 */
export const CHANNEL_PRIORITY: Record<Channel, number> = {
  kakao_alimtalk: 1,
  email: 2,
  web_push: 3,
};

/** 학적 상태 (§9.2) */
export const gradeStatus = z.enum(["high3", "repeater", "other"]);
export type GradeStatus = z.infer<typeof gradeStatus>;

/** 계열 (§9.2) */
export const track = z.enum(["humanities", "natural", "medical", "undecided"]);
export type Track = z.infer<typeof track>;

/** 과목 (§9.4) */
export const subject = z.enum([
  "korean",
  "math",
  "english",
  "history",
  "inquiry1",
  "inquiry2",
  "second_language",
]);
export type Subject = z.infer<typeof subject>;

/** 모집군 (§9.7) */
export const recruitmentGroup = z.enum(["ga", "na", "da", "none"]);
export type RecruitmentGroup = z.infer<typeof recruitmentGroup>;

/** 반영식 점수 타입 (§9.8) */
export const scoreType = z.enum(["standard", "percentile", "mixed", "custom"]);
export type ScoreType = z.infer<typeof scoreType>;

/** 레퍼런스 데이터 검수 상태 (§9.8) */
export const verifiedStatus = z.enum([
  "draft",
  "parsed",
  "verified",
  "live",
  "deprecated",
]);
export type VerifiedStatus = z.infer<typeof verifiedStatus>;

/** 분석 스냅샷 타입 (§9.10) */
export const snapshotType = z.enum([
  "june_position",
  "september_change",
  "csat_final",
]);
export type SnapshotType = z.infer<typeof snapshotType>;

/** 외부 도구 제공자 (§9.14) — 수동 입력 전용 */
export const competitorProvider = z.enum([
  "jinhak",
  "gosok",
  "telegnosis",
  "other",
]);
export type CompetitorProvider = z.infer<typeof competitorProvider>;

/** 외부 도구 값 타입 (§9.14) */
export const competitorValueType = z.enum([
  "kansu",
  "color",
  "probability",
  "memo",
]);
export type CompetitorValueType = z.infer<typeof competitorValueType>;

/** 원서 조합 전략 (§9.15) */
export const planType = z.enum(["stable", "balanced", "aggressive", "custom"]);
export type PlanType = z.infer<typeof planType>;

/** 지원 성향 (§7.4, §9.5) */
export const riskProfile = z.enum(["conservative", "balanced", "aggressive"]);
export type RiskProfile = z.infer<typeof riskProfile>;

/** 수시/정시 고민 정도 (§7.4) */
export const susiJungsiPreference = z.enum(["susi", "jungsi", "undecided"]);
export type SusiJungsiPreference = z.infer<typeof susiJungsiPreference>;

/** 사용자 역할 (§9.1) */
export const userRole = z.enum(["student", "parent", "consultant", "admin"]);
export type UserRole = z.infer<typeof userRole>;

/** 합불 결과 (§9.16) */
export const outcomeResult = z.enum([
  "accepted",
  "waitlisted",
  "rejected",
  "unknown",
]);
export type OutcomeResult = z.infer<typeof outcomeResult>;

/** 도달성 판단용 플랫폼 힌트 (§9.17) — iOS 웹푸시 제약 대응 */
export const platformHint = z.enum(["ios", "android", "desktop"]);
export type PlatformHint = z.infer<typeof platformHint>;

/** 레퍼런스 데이터 검수 대상 */
export const reviewDecisionKind = z.enum(["rule", "outcome"]);
export type ReviewDecisionKind = z.infer<typeof reviewDecisionKind>;

/** 레퍼런스 데이터 검수 판정 */
export const reviewVerdict = z.enum(["confirm", "edit", "reject", "flag", "skip"]);
export type ReviewVerdict = z.infer<typeof reviewVerdict>;
