"use client";

import { useState } from "react";
import { XIcon } from "@/components/icons";
import {
  createSupabaseBrowserClient,
  hasSupabaseBrowserConfig,
} from "@/lib/supabase/client";

type Provider = "kakao" | "google";

export function LoginSheet({
  surface,
  nextPath,
}: {
  surface: "analysis" | "report";
  nextPath?: string;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<Provider | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const enabled = hasSupabaseBrowserConfig();

  async function signIn(provider: Provider) {
    if (!enabled) {
      setNotice("Supabase Auth 환경변수 설정 후 로그인할 수 있어요.");
      return;
    }

    setBusy(provider);
    setNotice(null);
    try {
      const supabase = createSupabaseBrowserClient();
      const currentPath = `${window.location.pathname}${window.location.search}`;
      const redirectTo = new URL("/api/auth/callback", window.location.origin);
      redirectTo.searchParams.set("next", nextPath ?? currentPath);

      const { error } = await supabase.auth.signInWithOAuth({
        provider,
        options: { redirectTo: redirectTo.toString() },
      });
      if (error) throw error;
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "로그인을 시작하지 못했습니다.");
      setBusy(null);
    }
  }

  return (
    <section className="mt-4 border-t border-slate-200 pt-4">
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex w-full items-center justify-center rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 transition hover:bg-slate-50"
      >
        {surface === "analysis"
          ? "로그인하고 분석 결과 이어보기"
          : "로그인하고 리포트 저장하기"}
      </button>

      {open ? (
        <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
          <button
            type="button"
            aria-label="닫기"
            onClick={() => setOpen(false)}
            className="absolute inset-0 bg-slate-900/40"
          />
          <div className="absolute inset-x-0 bottom-0 mx-auto max-w-md rounded-t-2xl bg-white p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-base font-bold text-slate-900">간편 로그인</h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  로그인하면 쿠키를 지워도 6모 결과를 다시 불러올 수 있어요.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                className="rounded-md p-1 text-slate-400 hover:bg-slate-100"
                aria-label="닫기"
              >
                <XIcon className="size-4" />
              </button>
            </div>

            <div className="mt-4 grid gap-2">
              <button
                type="button"
                onClick={() => signIn("kakao")}
                disabled={busy !== null}
                className="h-11 rounded-xl bg-[#FEE500] text-sm font-bold text-[#191919] transition hover:bg-[#f6dd00] disabled:opacity-60"
              >
                {busy === "kakao" ? "카카오로 이동 중..." : "카카오로 계속하기"}
              </button>
              <button
                type="button"
                onClick={() => signIn("google")}
                disabled={busy !== null}
                className="h-11 rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:opacity-60"
              >
                {busy === "google" ? "Google로 이동 중..." : "Google로 계속하기"}
              </button>
            </div>

            {notice ? (
              <p className="mt-3 rounded-xl bg-slate-50 p-3 text-xs leading-5 text-slate-500">
                {notice}
              </p>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
