import type {
  NotificationSubscription,
  NotificationSubscriptionInput,
} from "../domain/entities";
import type { NotificationSubscriptionRepository } from "../ports";

/** §10.9 — P0 내부 데모는 구독 저장까지만 수행하고 실발송은 하지 않는다. */
export class NotificationSubscriptionService {
  constructor(
    private readonly subscriptions: NotificationSubscriptionRepository,
  ) {}

  subscribe(
    input: NotificationSubscriptionInput,
  ): Promise<NotificationSubscription> {
    return this.subscriptions.upsert(input);
  }
}
