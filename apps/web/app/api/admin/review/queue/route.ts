import type { ReviewQueueItem } from "@pacer/core";
import { reviewDecisionKind } from "@pacer/shared";
import { NextResponse, type NextRequest } from "next/server";
import { requireAdminRequest } from "@/lib/admin-auth";
import { getCoreUniversityIds } from "@/lib/admin-core";
import { getReviewService } from "@/lib/container";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const denied = await requireAdminRequest(req);
  if (denied) return denied;
  const url = new URL(req.url);
  const kindRaw = url.searchParams.get("kind");
  const kind = reviewDecisionKind.safeParse(kindRaw).success
    ? reviewDecisionKind.parse(kindRaw)
    : undefined;
  const statusRaw = url.searchParams.get("status");
  const status = statusRaw === "pending" || statusRaw === "decided" ? statusRaw : undefined;
  const onlyUncertain = url.searchParams.get("onlyUncertain") === "1";
  const limitRaw = Number(url.searchParams.get("limit") ?? "500");
  const limit = Number.isFinite(limitRaw)
    ? Math.min(Math.max(Math.trunc(limitRaw), 1), 2000)
    : 500;
  const result = await getReviewService().listQueue({
    kind,
    status,
    onlyUncertain,
    coreUniversityIds: getCoreUniversityIds(),
  });
  return NextResponse.json({
    items: result.items.slice(0, limit).map(serializeQueueItem),
    counts: {
      total: result.total,
      pending: result.pending,
      decided: result.decided,
    },
  });
}

function serializeQueueItem(item: ReviewQueueItem) {
  return {
    kind: item.kind,
    id: item.id,
    university_name: item.universityName,
    unit_name: item.unitName,
    year: item.year,
    verified_status: item.verifiedStatus,
    confidence: item.confidence,
    review_priority_score: item.reviewPriorityScore,
    review_strength: item.reviewStrength,
    has_ai_proposal: item.hasAiProposal,
    uncertain: item.uncertain,
    latest_verdict: item.latestVerdict,
    source_url: item.sourceUrl,
    text_preview: item.textPreview,
    cluster_size: item.clusterSize,
  };
}
