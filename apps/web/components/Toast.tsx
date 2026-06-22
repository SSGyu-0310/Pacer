"use client";

import { useEffect } from "react";

/**
 * 하단 고정 CTA 위에 뜨는 알림 토스트.
 * 페이지 중간 inline 공지는 CTA 클릭 시 화면 밖이라 보이지 않는 문제를 대체한다.
 */
export function Toast({
  message,
  onDismiss,
  durationMs = 3200,
}: {
  message: string | null;
  onDismiss: () => void;
  durationMs?: number;
}) {
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onDismiss, durationMs);
    return () => clearTimeout(timer);
  }, [message, durationMs, onDismiss]);

  if (!message) return null;

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-36 z-40 flex justify-center px-6">
      <p
        role="status"
        aria-live="polite"
        className="pointer-events-auto max-w-md rounded-xl bg-slate-900/95 px-4 py-2.5 text-center text-xs font-medium text-white shadow-lg backdrop-blur"
      >
        {message}
      </p>
    </div>
  );
}
