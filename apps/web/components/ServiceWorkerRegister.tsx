"use client";

import { useEffect } from "react";
import { track } from "@/lib/analytics";

/** SW 등록 (§17.4). 설치 권유(beforeinstallprompt)는 첫 결과 확인 후에 별도로 노출. */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // 등록 실패는 조용히 무시 (PWA는 점진적 향상)
    });
    const onInstalled = () => track("pwa_installed");
    window.addEventListener("appinstalled", onInstalled);
    return () => window.removeEventListener("appinstalled", onInstalled);
  }, []);
  return null;
}
