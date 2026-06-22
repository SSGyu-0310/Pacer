"use client";

import type { AnalyticsEvent } from "@pacer/shared";

type Params = Record<string, string | number | boolean | null | undefined>;

export function track(event: AnalyticsEvent, params: Params = {}) {
  if (typeof window === "undefined") return;
  const posthog = (
    window as typeof window & {
      posthog?: { capture: (event: string, params?: Params) => void };
    }
  ).posthog;
  if (process.env.NEXT_PUBLIC_POSTHOG_KEY && posthog) {
    posthog.capture(event, params);
  }
}
