"use client";

import posthog from "posthog-js";
import type { ReactNode } from "react";
import { useEffect } from "react";

export function PostHogProvider({ children }: { children: ReactNode }) {
  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_POSTHOG_KEY;
    if (!key || posthog.__loaded) return;

    posthog.init(key, {
      api_host: process.env.NEXT_PUBLIC_POSTHOG_HOST ?? "https://app.posthog.com",
      capture_pageview: true,
      loaded: (client) => {
        if (process.env.NODE_ENV === "development") client.debug(false);
      },
    });
  }, []);

  return <>{children}</>;
}
