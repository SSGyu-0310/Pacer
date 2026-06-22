import { bulkConfirmRequest, bulkConfirmResponse } from "@pacer/shared";
import { NextResponse, type NextRequest } from "next/server";
import { requireAdminRequest } from "@/lib/admin-auth";
import { getReviewService } from "@/lib/container";
import { fromDomainError } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const denied = await requireAdminRequest(req);
  if (denied) return denied;
  const parsed = bulkConfirmRequest.safeParse(await req.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ error: parsed.error.message }, { status: 400 });
  }
  try {
    const result = await getReviewService().bulkConfirm(parsed.data.kind, parsed.data.ids);
    return NextResponse.json(bulkConfirmResponse.parse(result));
  } catch (error) {
    return fromDomainError(error);
  }
}
