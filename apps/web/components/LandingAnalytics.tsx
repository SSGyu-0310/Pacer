"use client";

import { useEffect } from "react";
import Link from "next/link";
import { track } from "@/lib/analytics";

export function LandingAnalytics() {
  useEffect(() => {
    track("landing_view");
  }, []);
  return null;
}

export function TrackedLandingCta() {
  return (
    <Link
      href="/score"
      onClick={() => track("cta_click", { target: "score" })}
      className="mt-6 flex h-12 w-full items-center justify-center rounded-xl bg-slate-900 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800"
    >
      내 위치 확인하기
    </Link>
  );
}
