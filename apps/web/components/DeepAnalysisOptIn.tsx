"use client";

import { useState } from "react";
import { track } from "@/lib/analytics";
import { postJson, readStoredState } from "@/lib/client";

type Channel = "kakao_alimtalk" | "email";
const EVENT = "september_paid_preview" as const;

export function DeepAnalysisOptIn() {
  const [enabled, setEnabled] = useState(false);
  const [channel, setChannel] = useState<Channel>("kakao_alimtalk");
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  async function submit() {
    const cycleId = readStoredState()?.cycleId;
    if (!cycleId) {
      setNotice("이 브라우저에서 생성한 리포트에서만 알림을 신청할 수 있어요.");
      return;
    }
    if (!value.trim()) return;

    setBusy(true);
    setNotice(null);
    const body =
      channel === "email"
        ? { channel, address: value.trim(), events: [EVENT] }
        : { channel, phone: value.trim(), events: [EVENT] };

    try {
      await postJson(`/api/cycles/${cycleId}/notifications/subscribe`, body);
      track("reminder_opt_in", { channel, event: EVENT });
      setNotice("9모 심화 분석 알림을 저장했습니다.");
      setEnabled(false);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "알림 신청을 저장하지 못했습니다.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-bold text-slate-900">9모 심화 분석 알림</h2>
          <p className="mt-1 text-xs leading-5 text-slate-500">
            9모엔 더 깊은 분석을 준비 중이에요. 공개되면 알려드릴게요.
          </p>
        </div>
        <label className="relative inline-flex h-7 w-12 shrink-0 cursor-pointer items-center">
          <input
            type="checkbox"
            checked={enabled}
            onChange={(e) => {
              setEnabled(e.target.checked);
              setNotice(null);
            }}
            className="peer absolute inset-0 z-10 cursor-pointer opacity-0"
            aria-label="9모 심화 분석 알림 신청"
          />
          <span className="absolute inset-0 rounded-full bg-slate-200 transition peer-checked:bg-slate-900" />
          <span className="absolute left-1 size-5 rounded-full bg-white shadow transition peer-checked:translate-x-5" />
        </label>
      </div>

      {enabled ? (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {(
              [
                ["kakao_alimtalk", "카카오 알림톡"],
                ["email", "이메일"],
              ] as const
            ).map(([nextChannel, label]) => (
              <button
                key={nextChannel}
                type="button"
                onClick={() => {
                  setChannel(nextChannel);
                  setValue("");
                }}
                className={`h-10 rounded-xl border text-xs font-semibold transition ${
                  channel === nextChannel
                    ? "border-slate-900 bg-slate-900 text-white"
                    : "border-slate-200 bg-white text-slate-600"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <input
            type={channel === "email" ? "email" : "tel"}
            autoComplete={channel === "email" ? "email" : "tel"}
            inputMode={channel === "email" ? "email" : "tel"}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={channel === "email" ? "student@example.com" : "01012345678"}
            className="h-11 w-full rounded-xl border border-slate-200 px-3 text-sm outline-none transition focus:border-slate-900 focus:ring-2 focus:ring-slate-200"
          />
          <button
            type="button"
            onClick={submit}
            disabled={!value.trim() || busy}
            className="h-11 w-full rounded-xl bg-slate-900 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-300"
          >
            {busy ? "저장 중..." : "알림 받기"}
          </button>
        </div>
      ) : null}

      {notice ? (
        <p className="mt-3 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">
          {notice}
        </p>
      ) : null}
    </section>
  );
}
