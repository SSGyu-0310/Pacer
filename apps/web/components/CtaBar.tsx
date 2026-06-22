"use client";

import { BellIcon, ShareIcon, SparklesIcon } from "@/components/icons";

/** 분석 결과 하단 고정 CTA 바 — v0 디자인 이식. */
export function CtaBar({
  busy,
  reportDisabled = false,
  onReport,
  onAlert,
  onShare,
}: {
  busy: string | null;
  reportDisabled?: boolean;
  onReport: () => void;
  onAlert: () => void;
  onShare: () => void;
}) {
  return (
    <div className="sticky bottom-0 z-10 -mx-4 border-t border-slate-200 bg-white/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur">
      <div className="mx-auto max-w-md space-y-2">
        <button
          type="button"
          onClick={onReport}
          disabled={busy === "report" || reportDisabled}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-400"
        >
          <SparklesIcon className="size-4" />
          {busy === "report"
            ? "리포트 생성 중..."
            : reportDisabled
              ? "분석 가능한 결과 없음"
              : "AI 리포트 보기"}
        </button>
        <div className="grid grid-cols-2 gap-2">
          <SecondaryButton
            icon={<BellIcon className="size-4" />}
            label="9모 알림"
            onClick={onAlert}
          />
          <SecondaryButton
            icon={<ShareIcon className="size-4" />}
            label="공유"
            onClick={onShare}
          />
        </div>
      </div>
    </div>
  );
}

function SecondaryButton({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center justify-center gap-1.5 rounded-xl border border-slate-200 bg-white py-2.5 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
    >
      <span className="text-slate-400">{icon}</span>
      {label}
    </button>
  );
}
