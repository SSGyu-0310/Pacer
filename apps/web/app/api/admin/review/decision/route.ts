import {
  recordReviewDecisionRequest,
  recordReviewDecisionResponse,
} from "@pacer/shared";
import { NextResponse, type NextRequest } from "next/server";
import { requireAdminRequest } from "@/lib/admin-auth";
import { getReviewService } from "@/lib/container";
import { fromDomainError } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const denied = await requireAdminRequest(req);
  if (denied) return denied;
  const parsed = recordReviewDecisionRequest.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }
  try {
    const result = await getReviewService().record({
      targetKind: parsed.data.target_kind,
      targetId: parsed.data.target_id,
      verdict: parsed.data.verdict,
      reviewedVerifiedStatus: parsed.data.reviewed_verified_status,
      reviewedConfidence: parsed.data.reviewed_confidence,
      correctedFields: parsed.data.corrected_fields,
      evidenceChecked: parsed.data.evidence_checked,
      approvalScopeKey: parsed.data.approval_scope_key,
      reviewer: parsed.data.reviewer,
      reviewNotes: parsed.data.review_notes,
      applyToCluster: parsed.data.apply_to_cluster,
    });
    return NextResponse.json(
      recordReviewDecisionResponse.parse({
        decision_id: result.decisionId,
        status: "recorded",
        would_unlock_exact: result.wouldUnlockExact,
        cluster_applied: result.clusterApplied,
      }),
    );
  } catch (error) {
    return fromDomainError(error);
  }
}
