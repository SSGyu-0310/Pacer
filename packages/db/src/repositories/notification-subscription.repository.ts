import type {
  NotificationSubscription,
  NotificationSubscriptionInput,
  NotificationSubscriptionRepository,
} from "@pacer/core";
import type { Prisma, PrismaClient } from "@prisma/client";
import { notificationEvent } from "@pacer/shared";

/** §9.17/§10.9 — 채널별 알림 구독 저장. 실발송은 notifications 패키지 담당. */
export class PrismaNotificationSubscriptionRepository
  implements NotificationSubscriptionRepository
{
  constructor(private readonly db: PrismaClient) {}

  async upsert(
    input: NotificationSubscriptionInput,
  ): Promise<NotificationSubscription> {
    const row = await this.db.notificationSubscription.upsert({
      where: {
        cycleId_channel_endpointOrAddress: {
          cycleId: input.cycleId,
          channel: input.channel,
          endpointOrAddress: input.endpointOrAddress,
        },
      },
      create: {
        userId: input.userId,
        cycleId: input.cycleId,
        channel: input.channel,
        endpointOrAddress: input.endpointOrAddress,
        pushKeys: input.pushKeys
          ? (input.pushKeys as Prisma.InputJsonValue)
          : undefined,
        platformHint: input.platformHint,
        eventNames: input.eventNames,
      },
      update: {
        userId: input.userId,
        pushKeys: input.pushKeys
          ? (input.pushKeys as Prisma.InputJsonValue)
          : undefined,
        platformHint: input.platformHint,
        eventNames: input.eventNames,
        revokedAt: null,
        optedInAt: new Date(),
      },
    });
    return {
      id: row.id,
      cycleId: row.cycleId,
      channel: row.channel,
      endpointOrAddress: row.endpointOrAddress,
      eventNames: notificationEvent.array().parse(row.eventNames),
    };
  }
}
