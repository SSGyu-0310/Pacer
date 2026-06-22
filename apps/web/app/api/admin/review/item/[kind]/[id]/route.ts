import type { ReviewAiProposalRecord, ReviewDecisionRecord, ReviewItemDetailRecord } from "@pacer/core";
import { reviewDecisionKind } from "@pacer/shared";
import { NextResponse, type NextRequest } from "next/server";
import { requireAdminRequest } from "@/lib/admin-auth";
import { getReviewService } from "@/lib/container";
import { fromDomainError } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ kind: string; id: string }> },
) {
  const denied = await requireAdminRequest(req);
  if (denied) return denied;
  const { kind: rawKind, id } = await params;
  const kind = reviewDecisionKind.safeParse(rawKind);
  if (!kind.success) return NextResponse.json({ error: "bad_kind" }, { status: 400 });
  try {
    const item = await getReviewService().getItem(kind.data, id);
    return NextResponse.json(serializeItem(item));
  } catch (error) {
    return fromDomainError(error);
  }
}

function serializeItem(item: ReviewItemDetailRecord) {
  return {
    kind: item.kind,
    id: item.id,
    university_name: item.universityName,
    unit_name: item.unitName,
    year: item.year,
    source_url: item.sourceUrl,
    parsed_fields: snakeParsedFields(item.parsedFields),
    evidence: item.evidence,
    ai_proposal: item.aiProposal ? serializeProposal(item.aiProposal) : null,
    latest_decision: item.latestDecision ? serializeDecision(item.latestDecision) : null,
    would_unlock_exact: item.wouldUnlockExact,
    cluster_size: item.clusterSize,
  };
}

function serializeProposal(proposal: ReviewAiProposalRecord) {
  return {
    id: proposal.id,
    target_kind: proposal.targetKind,
    target_id: proposal.targetId,
    prompt_version: proposal.promptVersion,
    proposal_json: proposal.proposalJson,
    model_name: proposal.modelName,
    created_at: proposal.createdAt.toISOString(),
  };
}

function serializeDecision(decision: ReviewDecisionRecord) {
  return {
    id: decision.id,
    target_kind: decision.targetKind,
    target_id: decision.targetId,
    verdict: decision.verdict,
    reviewed_verified_status: decision.reviewedVerifiedStatus,
    reviewed_confidence: decision.reviewedConfidence,
    corrected_fields: decision.correctedFields,
    ai_proposal_snapshot: decision.aiProposalSnapshot,
    evidence_checked: decision.evidenceChecked,
    approval_scope_key: decision.approvalScopeKey,
    reviewer: decision.reviewer,
    review_notes: decision.reviewNotes,
    reviewed_at: decision.reviewedAt.toISOString(),
  };
}

function snakeParsedFields(fields: Record<string, unknown>) {
  return {
    score_type: fields.scoreType,
    formula_json: fields.formulaJson,
    english_policy_json: fields.englishPolicyJson,
    history_policy_json: fields.historyPolicyJson,
    inquiry_policy_json: fields.inquiryPolicyJson,
    eligibility_json: fields.eligibilityJson,
    avg_score: fields.avgScore,
    cut_score: fields.cutScore,
    percentile_cut: fields.percentileCut,
    competition_rate: fields.competitionRate,
    additional_pass: fields.additionalPass,
  };
}
