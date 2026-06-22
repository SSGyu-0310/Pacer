-- CreateEnum
CREATE TYPE "Role" AS ENUM ('student', 'parent', 'consultant', 'admin');

-- CreateEnum
CREATE TYPE "GradeStatus" AS ENUM ('high3', 'repeater', 'other');

-- CreateEnum
CREATE TYPE "Track" AS ENUM ('humanities', 'natural', 'medical', 'undecided');

-- CreateEnum
CREATE TYPE "ExamType" AS ENUM ('june_mock', 'september_mock', 'csat');

-- CreateEnum
CREATE TYPE "ScoreStatus" AS ENUM ('estimated', 'official');

-- CreateEnum
CREATE TYPE "Subject" AS ENUM ('korean', 'math', 'english', 'history', 'inquiry1', 'inquiry2', 'second_language');

-- CreateEnum
CREATE TYPE "RecruitmentGroup" AS ENUM ('ga', 'na', 'da', 'none');

-- CreateEnum
CREATE TYPE "ScoreType" AS ENUM ('standard', 'percentile', 'mixed', 'custom');

-- CreateEnum
CREATE TYPE "VerifiedStatus" AS ENUM ('draft', 'parsed', 'verified', 'live', 'deprecated');

-- CreateEnum
CREATE TYPE "SnapshotType" AS ENUM ('june_position', 'september_change', 'csat_final');

-- CreateEnum
CREATE TYPE "Band" AS ENUM ('stable', 'match', 'reach', 'challenge', 'risk');

-- CreateEnum
CREATE TYPE "Confidence" AS ENUM ('high', 'medium', 'low', 'limited');

-- CreateEnum
CREATE TYPE "ReportType" AS ENUM ('june_position_report', 'september_change_report', 'csat_final_report', 'cross_validation_report', 'parent_summary_report', 'application_plan_report');

-- CreateEnum
CREATE TYPE "CompetitorProvider" AS ENUM ('jinhak', 'gosok', 'telegnosis', 'other');

-- CreateEnum
CREATE TYPE "CompetitorValueType" AS ENUM ('kansu', 'color', 'probability', 'memo');

-- CreateEnum
CREATE TYPE "PlanType" AS ENUM ('stable', 'balanced', 'aggressive', 'custom');

-- CreateEnum
CREATE TYPE "RiskProfile" AS ENUM ('conservative', 'balanced', 'aggressive');

-- CreateEnum
CREATE TYPE "SusiJungsiPreference" AS ENUM ('susi', 'jungsi', 'undecided');

-- CreateEnum
CREATE TYPE "OutcomeResult" AS ENUM ('accepted', 'waitlisted', 'rejected', 'unknown');

-- CreateEnum
CREATE TYPE "PlatformHint" AS ENUM ('ios', 'android', 'desktop');

-- CreateEnum
CREATE TYPE "Channel" AS ENUM ('kakao_alimtalk', 'email', 'web_push');

-- CreateTable
CREATE TABLE "users" (
    "id" TEXT NOT NULL,
    "email" TEXT,
    "phone" TEXT,
    "kakaoId" TEXT,
    "role" "Role" NOT NULL DEFAULT 'student',
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "deletedAt" TIMESTAMP(3),

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "admission_cycles" (
    "id" TEXT NOT NULL,
    "userId" TEXT,
    "anonSessionId" TEXT,
    "admissionYear" INTEGER NOT NULL,
    "gradeStatus" "GradeStatus" NOT NULL,
    "track" "Track" NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "admission_cycles_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "exam_scores" (
    "id" TEXT NOT NULL,
    "cycleId" TEXT NOT NULL,
    "examType" "ExamType" NOT NULL,
    "scoreStatus" "ScoreStatus" NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "exam_scores_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "subject_scores" (
    "id" TEXT NOT NULL,
    "examScoreId" TEXT NOT NULL,
    "subject" "Subject" NOT NULL,
    "selection" TEXT,
    "rawScore" DOUBLE PRECISION,
    "standardScore" DOUBLE PRECISION,
    "percentile" DOUBLE PRECISION,
    "grade" INTEGER,

    CONSTRAINT "subject_scores_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "target_snapshots" (
    "id" TEXT NOT NULL,
    "cycleId" TEXT NOT NULL,
    "examType" "ExamType" NOT NULL,
    "targetUniversities" TEXT[],
    "targetMajorGroups" TEXT[],
    "preferredRegions" TEXT[],
    "riskProfile" "RiskProfile" NOT NULL,
    "susiJungsiPreference" "SusiJungsiPreference" NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "target_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "universities" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "campus" TEXT,
    "region" TEXT NOT NULL,
    "type" TEXT,
    "displayOrder" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "universities_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "admission_units" (
    "id" TEXT NOT NULL,
    "universityId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "recruitmentGroup" "RecruitmentGroup" NOT NULL,
    "majorGroup" TEXT,
    "quota" INTEGER,
    "year" INTEGER NOT NULL,
    "active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "admission_units_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "admission_rules" (
    "id" TEXT NOT NULL,
    "unitId" TEXT NOT NULL,
    "year" INTEGER NOT NULL,
    "scoreType" "ScoreType" NOT NULL,
    "formulaJson" JSONB,
    "eligibilityJson" JSONB,
    "englishPolicyJson" JSONB,
    "historyPolicyJson" JSONB,
    "inquiryPolicyJson" JSONB,
    "sourceUrl" TEXT,
    "verifiedStatus" "VerifiedStatus" NOT NULL DEFAULT 'draft',
    "updatedAt" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "admission_rules_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "historical_outcomes" (
    "id" TEXT NOT NULL,
    "unitId" TEXT NOT NULL,
    "year" INTEGER NOT NULL,
    "avgScore" DOUBLE PRECISION,
    "cutScore" DOUBLE PRECISION,
    "percentileCut" DOUBLE PRECISION,
    "competitionRate" DOUBLE PRECISION,
    "additionalPass" INTEGER,
    "sourceUrl" TEXT,
    "confidence" "Confidence" NOT NULL DEFAULT 'limited',

    CONSTRAINT "historical_outcomes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "analysis_snapshots" (
    "id" TEXT NOT NULL,
    "cycleId" TEXT NOT NULL,
    "examScoreId" TEXT NOT NULL,
    "snapshotType" "SnapshotType" NOT NULL,
    "summaryJson" JSONB NOT NULL,
    "bandDistributionJson" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "analysis_snapshots_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "analysis_results" (
    "id" TEXT NOT NULL,
    "analysisSnapshotId" TEXT NOT NULL,
    "unitId" TEXT NOT NULL,
    "convertedScore" DOUBLE PRECISION,
    "historicalReferenceScore" DOUBLE PRECISION,
    "scoreGap" DOUBLE PRECISION,
    "band" "Band" NOT NULL,
    "confidence" "Confidence" NOT NULL,
    "reasonCodes" TEXT[],
    "warnings" TEXT[],
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "analysis_results_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "saved_admission_units" (
    "id" TEXT NOT NULL,
    "cycleId" TEXT NOT NULL,
    "unitId" TEXT NOT NULL,
    "priority" INTEGER,
    "memo" TEXT,
    "savedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "saved_admission_units_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "strategy_reports" (
    "id" TEXT NOT NULL,
    "cycleId" TEXT NOT NULL,
    "examScoreId" TEXT NOT NULL,
    "reportType" "ReportType" NOT NULL,
    "contentJson" JSONB NOT NULL,
    "modelName" TEXT NOT NULL,
    "promptVersion" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "strategy_reports_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "competitor_signals" (
    "id" TEXT NOT NULL,
    "cycleId" TEXT NOT NULL,
    "examType" "ExamType" NOT NULL,
    "provider" "CompetitorProvider" NOT NULL,
    "unitId" TEXT NOT NULL,
    "valueType" "CompetitorValueType" NOT NULL,
    "value" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "competitor_signals_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "application_plans" (
    "id" TEXT NOT NULL,
    "cycleId" TEXT NOT NULL,
    "planType" "PlanType" NOT NULL,
    "gaUnitId" TEXT,
    "naUnitId" TEXT,
    "daUnitId" TEXT,
    "summaryJson" JSONB NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "application_plans_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "final_outcomes" (
    "id" TEXT NOT NULL,
    "cycleId" TEXT NOT NULL,
    "unitId" TEXT NOT NULL,
    "applied" BOOLEAN NOT NULL DEFAULT false,
    "result" "OutcomeResult" NOT NULL DEFAULT 'unknown',
    "waitlistNumber" INTEGER,
    "registered" BOOLEAN,
    "evidenceFileUrl" TEXT,
    "rewardStatus" TEXT,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "final_outcomes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "notification_subscriptions" (
    "id" TEXT NOT NULL,
    "userId" TEXT,
    "cycleId" TEXT,
    "channel" "Channel" NOT NULL,
    "endpointOrAddress" TEXT NOT NULL,
    "pushKeys" JSONB,
    "platformHint" "PlatformHint",
    "eventNames" TEXT[] DEFAULT ARRAY[]::TEXT[],
    "optedInAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "revokedAt" TIMESTAMP(3),
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "notification_subscriptions_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE INDEX "admission_cycles_userId_idx" ON "admission_cycles"("userId");

-- CreateIndex
CREATE INDEX "admission_cycles_anonSessionId_idx" ON "admission_cycles"("anonSessionId");

-- CreateIndex
CREATE UNIQUE INDEX "admission_cycles_anonSessionId_admissionYear_key" ON "admission_cycles"("anonSessionId", "admissionYear");

-- CreateIndex
CREATE UNIQUE INDEX "exam_scores_cycleId_examType_key" ON "exam_scores"("cycleId", "examType");

-- CreateIndex
CREATE INDEX "subject_scores_examScoreId_idx" ON "subject_scores"("examScoreId");

-- CreateIndex
CREATE UNIQUE INDEX "target_snapshots_cycleId_examType_key" ON "target_snapshots"("cycleId", "examType");

-- CreateIndex
CREATE INDEX "admission_units_universityId_idx" ON "admission_units"("universityId");

-- CreateIndex
CREATE INDEX "admission_rules_unitId_year_idx" ON "admission_rules"("unitId", "year");

-- CreateIndex
CREATE INDEX "historical_outcomes_unitId_year_idx" ON "historical_outcomes"("unitId", "year");

-- CreateIndex
CREATE INDEX "analysis_snapshots_cycleId_idx" ON "analysis_snapshots"("cycleId");

-- CreateIndex
CREATE INDEX "analysis_results_analysisSnapshotId_idx" ON "analysis_results"("analysisSnapshotId");

-- CreateIndex
CREATE UNIQUE INDEX "saved_admission_units_cycleId_unitId_key" ON "saved_admission_units"("cycleId", "unitId");

-- CreateIndex
CREATE INDEX "strategy_reports_cycleId_idx" ON "strategy_reports"("cycleId");

-- CreateIndex
CREATE INDEX "competitor_signals_cycleId_idx" ON "competitor_signals"("cycleId");

-- CreateIndex
CREATE INDEX "application_plans_cycleId_idx" ON "application_plans"("cycleId");

-- CreateIndex
CREATE INDEX "final_outcomes_cycleId_idx" ON "final_outcomes"("cycleId");

-- CreateIndex
CREATE INDEX "notification_subscriptions_userId_idx" ON "notification_subscriptions"("userId");

-- CreateIndex
CREATE INDEX "notification_subscriptions_cycleId_idx" ON "notification_subscriptions"("cycleId");

-- CreateIndex
CREATE UNIQUE INDEX "notification_subscriptions_cycleId_channel_endpointOrAddres_key" ON "notification_subscriptions"("cycleId", "channel", "endpointOrAddress");

-- AddForeignKey
ALTER TABLE "admission_cycles" ADD CONSTRAINT "admission_cycles_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "exam_scores" ADD CONSTRAINT "exam_scores_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "subject_scores" ADD CONSTRAINT "subject_scores_examScoreId_fkey" FOREIGN KEY ("examScoreId") REFERENCES "exam_scores"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "target_snapshots" ADD CONSTRAINT "target_snapshots_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "admission_units" ADD CONSTRAINT "admission_units_universityId_fkey" FOREIGN KEY ("universityId") REFERENCES "universities"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "admission_rules" ADD CONSTRAINT "admission_rules_unitId_fkey" FOREIGN KEY ("unitId") REFERENCES "admission_units"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "historical_outcomes" ADD CONSTRAINT "historical_outcomes_unitId_fkey" FOREIGN KEY ("unitId") REFERENCES "admission_units"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "analysis_snapshots" ADD CONSTRAINT "analysis_snapshots_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "analysis_snapshots" ADD CONSTRAINT "analysis_snapshots_examScoreId_fkey" FOREIGN KEY ("examScoreId") REFERENCES "exam_scores"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "analysis_results" ADD CONSTRAINT "analysis_results_analysisSnapshotId_fkey" FOREIGN KEY ("analysisSnapshotId") REFERENCES "analysis_snapshots"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "analysis_results" ADD CONSTRAINT "analysis_results_unitId_fkey" FOREIGN KEY ("unitId") REFERENCES "admission_units"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "saved_admission_units" ADD CONSTRAINT "saved_admission_units_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "saved_admission_units" ADD CONSTRAINT "saved_admission_units_unitId_fkey" FOREIGN KEY ("unitId") REFERENCES "admission_units"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "strategy_reports" ADD CONSTRAINT "strategy_reports_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "strategy_reports" ADD CONSTRAINT "strategy_reports_examScoreId_fkey" FOREIGN KEY ("examScoreId") REFERENCES "exam_scores"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "competitor_signals" ADD CONSTRAINT "competitor_signals_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "competitor_signals" ADD CONSTRAINT "competitor_signals_unitId_fkey" FOREIGN KEY ("unitId") REFERENCES "admission_units"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "application_plans" ADD CONSTRAINT "application_plans_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "final_outcomes" ADD CONSTRAINT "final_outcomes_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "final_outcomes" ADD CONSTRAINT "final_outcomes_unitId_fkey" FOREIGN KEY ("unitId") REFERENCES "admission_units"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "notification_subscriptions" ADD CONSTRAINT "notification_subscriptions_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "notification_subscriptions" ADD CONSTRAINT "notification_subscriptions_cycleId_fkey" FOREIGN KEY ("cycleId") REFERENCES "admission_cycles"("id") ON DELETE CASCADE ON UPDATE CASCADE;
