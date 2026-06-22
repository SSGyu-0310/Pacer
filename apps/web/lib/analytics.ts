"use client";

import type { AnalyticsEvent } from "@pacer/shared";
import posthog from "posthog-js";

type Params = Record<string, string | number | boolean | null | undefined>;

/**
 * §16.5 — PostHog 싱글톤에 직접 capture.
 * PostHogProvider가 init한 같은 인스턴스를 쓴다(window.posthog 전역에 의존하지 않음).
 * 키가 없거나 아직 init 전이면 무해히 no-op.
 */
export function track(event: AnalyticsEvent, params: Params = {}) {
  if (typeof window === "undefined") return;
  if (!process.env.NEXT_PUBLIC_POSTHOG_KEY || !posthog.__loaded) return;
  posthog.capture(event, params);
}
