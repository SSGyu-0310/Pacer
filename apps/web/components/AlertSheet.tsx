"use client";

import { useState } from "react";
import { XIcon } from "@/components/icons";

/**
 * 9모 알림 신청 바텀 시트 (§10.9, §17.5).
 * 채널 우선순위: 알림톡(기본) → 이메일 → 웹푸시(iOS는 홈 화면 추가 후 가능).
 */
export function AlertSheet({
  open,
  busy,
  canWebPush,
  onClose,
  onKakao,
  onEmail,
  onWebPush,
}: {
  open: boolean;
  busy: string | null;
  canWebPush: boolean;
  onClose: () => void;
  onKakao: (phone: string) => void;
  onEmail: (address: string) => void;
  onWebPush: () => void;
}) {
  const [channel, setChannel] = useState<"kakao" | "email" | "push">("kakao");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      <button
        type="button"
        aria-label="닫기"
        onClick={onClose}
        className="absolute inset-0 bg-slate-900/40"
      />
      <div className="absolute inset-x-0 bottom-0 mx-auto max-w-md rounded-t-2xl bg-white p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900">9모 알림 신청</h2>
            <p className="mt-1 text-xs leading-5 text-slate-500">
              9월 모의평가 때 같은 기준으로 다시 알려드릴게요.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-slate-400 hover:bg-slate-100"
            aria-label="닫기"
          >
            <XIcon className="size-4" />
          </button>
        </div>

        {/* 채널 선택 */}
        <div className="mt-4 grid grid-cols-3 gap-2">
          {(
            [
              ["kakao", "카카오 알림톡"],
              ["email", "이메일"],
              ["push", "웹 푸시"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              onClick={() => setChannel(value)}
              className={`h-10 rounded-xl border text-xs font-semibold transition ${
                channel === value
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-white text-slate-600"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-3">
          {channel === "kakao" && (
            <>
              <input
                type="tel"
                autoComplete="tel"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                inputMode="tel"
                placeholder="01012345678"
                className="h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
              />
              <button
                type="button"
                onClick={() => onKakao(phone)}
                disabled={!phone.trim() || busy === "subscribe:kakao_alimtalk"}
                className="h-11 w-full rounded-xl bg-slate-900 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-300"
              >
                {busy === "subscribe:kakao_alimtalk" ? "저장 중..." : "알림톡으로 받기"}
              </button>
            </>
          )}
          {channel === "email" && (
            <>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                inputMode="email"
                placeholder="student@example.com"
                className="h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
              />
              <button
                type="button"
                onClick={() => onEmail(email)}
                disabled={!email.trim() || busy === "subscribe:email"}
                className="h-11 w-full rounded-xl bg-slate-900 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-300"
              >
                {busy === "subscribe:email" ? "저장 중..." : "이메일로 받기"}
              </button>
            </>
          )}
          {channel === "push" && (
            <>
              <p className="rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">
                iPhone에서는 Safari 공유 → &lsquo;홈 화면에 추가&rsquo; 후 푸시를 받을 수
                있어요. 설치 전이라면 알림톡이나 이메일을 함께 남겨 주세요.
              </p>
              <button
                type="button"
                onClick={onWebPush}
                disabled={!canWebPush || busy === "subscribe:web_push"}
                className="h-11 w-full rounded-xl bg-slate-900 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-300"
              >
                {busy === "subscribe:web_push"
                  ? "저장 중..."
                  : canWebPush
                    ? "웹 푸시 켜기"
                    : "이 브라우저는 푸시 미지원"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
