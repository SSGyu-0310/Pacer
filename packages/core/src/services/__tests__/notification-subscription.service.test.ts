import { describe, expect, it } from "vitest";
import type {
  NotificationSubscription,
  NotificationSubscriptionInput,
} from "../../domain/entities";
import type { NotificationSubscriptionRepository } from "../../ports";
import { NotificationSubscriptionService } from "../notification-subscription.service";

describe("NotificationSubscriptionService (§10.9)", () => {
  it("채널 payload와 eventNames를 repository upsert로 전달한다", async () => {
    let captured: NotificationSubscriptionInput | null = null;
    const repo: NotificationSubscriptionRepository = {
      upsert: (input) => {
        captured = input;
        const saved: NotificationSubscription = {
          id: "11111111-1111-4111-8111-111111111111",
          cycleId: input.cycleId,
          channel: input.channel,
          endpointOrAddress: input.endpointOrAddress,
          eventNames: input.eventNames,
        };
        return Promise.resolve(saved);
      },
    };

    const result = await new NotificationSubscriptionService(repo).subscribe({
      userId: null,
      cycleId: "cy-1",
      channel: "web_push",
      endpointOrAddress: "https://push.example/subscription",
      pushKeys: { p256dh: "p", auth: "a" },
      platformHint: "android",
      eventNames: ["september_mock_open"],
    });

    expect(result.channel).toBe("web_push");
    expect(captured).toEqual({
      userId: null,
      cycleId: "cy-1",
      channel: "web_push",
      endpointOrAddress: "https://push.example/subscription",
      pushKeys: { p256dh: "p", auth: "a" },
      platformHint: "android",
      eventNames: ["september_mock_open"],
    });
  });
});
