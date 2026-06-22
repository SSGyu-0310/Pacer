import type { Notifier } from "@pacer/core";
import type { Channel } from "@pacer/shared";
import { sendAlimtalk, sendEmail, sendWebPush } from "./senders";

/**
 * core.Notifier 어댑터 — 채널별 실제 발송기로 라우팅.
 * 우선순위 발송 로직은 core 의 NotificationService 가 담당한다(§17.5).
 */
export class MultiChannelNotifier implements Notifier {
  async send(
    channel: Channel,
    target: string,
    message: string,
  ): Promise<{ delivered: boolean }> {
    switch (channel) {
      case "kakao_alimtalk":
        return sendAlimtalk(target, message);
      case "email":
        return sendEmail(target, message);
      case "web_push":
        return sendWebPush(target, message);
    }
  }
}
