import { NotImplementedError } from "@pacer/core";

export interface SendResult {
  delivered: boolean;
}

/** 1순위: 카카오 알림톡 (OS 무관, 도달률 높음) — §17.5 */
export function sendAlimtalk(_phone: string, _message: string): Promise<SendResult> {
  throw new NotImplementedError("sendAlimtalk");
}

/** 2순위: 트랜잭션 이메일 (Resend/SES) */
export function sendEmail(_address: string, _message: string): Promise<SendResult> {
  throw new NotImplementedError("sendEmail");
}

/**
 * 3순위: 웹푸시 (VAPID) — iOS는 16.4+ & PWA 설치자 한정 도달.
 * 미설치 iOS는 알림톡/이메일이 커버한다.
 */
export function sendWebPush(_endpoint: string, _message: string): Promise<SendResult> {
  throw new NotImplementedError("sendWebPush");
}
