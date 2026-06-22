-- CreateEnum
CREATE TYPE "ReviewDecisionKind" AS ENUM ('rule', 'outcome');

-- CreateEnum
CREATE TYPE "ReviewVerdict" AS ENUM ('confirm', 'edit', 'reject', 'flag', 'skip');

-- CreateTable
CREATE TABLE "reference_review_decisions" (
    "id" TEXT NOT NULL,
    "targetKind" "ReviewDecisionKind" NOT NULL,
    "targetId" TEXT NOT NULL,
    "verdict" "ReviewVerdict" NOT NULL,
    "reviewedVerifiedStatus" "VerifiedStatus",
    "reviewedConfidence" "Confidence",
    "correctedFields" JSONB,
    "aiProposalSnapshot" JSONB,
    "evidenceChecked" BOOLEAN NOT NULL DEFAULT false,
    "approvalScopeKey" TEXT,
    "reviewer" TEXT NOT NULL DEFAULT 'solo',
    "reviewNotes" TEXT,
    "supersededAt" TIMESTAMP(3),
    "reviewedAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "reference_review_decisions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "review_ai_proposals" (
    "id" TEXT NOT NULL,
    "targetKind" "ReviewDecisionKind" NOT NULL,
    "targetId" TEXT NOT NULL,
    "promptVersion" TEXT NOT NULL,
    "proposalJson" JSONB NOT NULL,
    "modelName" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "review_ai_proposals_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "rule_evidence" (
    "ruleId" TEXT NOT NULL,
    "unvCd" TEXT,
    "universityName" TEXT,
    "sourceUrl" TEXT,
    "attachmentUrl" TEXT,
    "textPreview" TEXT,
    "detectedSignals" JSONB,
    "percentageValues" JSONB,
    "weightValues" JSONB,
    "formulaSignals" JSONB,
    "reviewPriorityScore" INTEGER,
    "reviewStrength" TEXT,
    "rawPath" TEXT,
    "sourcePath" TEXT,

    CONSTRAINT "rule_evidence_pkey" PRIMARY KEY ("ruleId")
);

-- CreateTable
CREATE TABLE "outcome_evidence" (
    "outcomeId" TEXT NOT NULL,
    "sourceUrl" TEXT,
    "rawPath" TEXT,
    "rowText" TEXT,
    "metricValuesJson" JSONB,

    CONSTRAINT "outcome_evidence_pkey" PRIMARY KEY ("outcomeId")
);

-- CreateIndex
CREATE INDEX "reference_review_decisions_targetKind_targetId_idx" ON "reference_review_decisions"("targetKind", "targetId");

-- CreateIndex
CREATE INDEX "reference_review_decisions_approvalScopeKey_idx" ON "reference_review_decisions"("approvalScopeKey");

-- CreateIndex
CREATE UNIQUE INDEX "review_ai_proposals_targetKind_targetId_promptVersion_key" ON "review_ai_proposals"("targetKind", "targetId", "promptVersion");
