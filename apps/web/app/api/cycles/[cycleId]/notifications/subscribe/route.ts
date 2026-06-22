import { subscribeNotificationRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getNotificationSubscriptionService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** §10.9 알림 구독 등록 (다중 채널) — P0 내부 데모는 저장까지만 수행. */
export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = subscribeNotificationRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  const data = parsed.data;
  const endpointOrAddress =
    data.channel === "web_push"
      ? data.subscription.endpoint
      : data.channel === "email"
        ? data.address
        : data.phone;

  try {
    const saved = await getNotificationSubscriptionService().subscribe({
      userId: cycle.userId,
      cycleId,
      channel: data.channel,
      endpointOrAddress,
      pushKeys: data.channel === "web_push" ? data.subscription.keys : undefined,
      platformHint: data.channel === "web_push" ? data.platform_hint : undefined,
      eventNames: data.events,
    });
    return NextResponse.json(
      { subscription_id: saved.id, status: "subscribed" as const },
      { status: 201 },
    );
  } catch (e) {
    return fromDomainError(e);
  }
}
