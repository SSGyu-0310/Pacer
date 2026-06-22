import type { Channel } from "@pacer/shared";
import { CHANNEL_PRIORITY } from "@pacer/shared";
import type { Notifier } from "../ports";

/**
 * §17.5 — 단일 채널 의존 금지. 보유 채널 중 우선순위(1 알림톡 → 2 이메일 → 3 웹푸시)로
 * 발송하고, 먼저 도달한 채널에서 멈춰 중복을 최소화한다.
 */
export class NotificationService {
  constructor(private readonly notifier: Notifier) {}

  async dispatch(
    channels: { channel: Channel; target: string }[],
    message: string,
  ): Promise<{ delivered: boolean; channel: Channel | null }> {
    const ordered = [...channels].sort(
      (a, b) => CHANNEL_PRIORITY[a.channel] - CHANNEL_PRIORITY[b.channel],
    );
    for (const c of ordered) {
      const res = await this.notifier.send(c.channel, c.target, message);
      if (res.delivered) return { delivered: true, channel: c.channel };
    }
    return { delivered: false, channel: null };
  }
}
