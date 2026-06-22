import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import { ServiceWorkerRegister } from "@/components/ServiceWorkerRegister";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: "Pacer — 6모부터 수능까지, 내 정시 위치를 추적하세요",
  description:
    "6모 → 9모 → 수능, 입시 사이클 전체를 함께 보는 AI 정시 전략 플랫폼. 예측이 아니라 해석입니다.",
  // SSR/OG 공유 프리뷰 (§7.1) — 상세 OG 카드는 /api/og 에서 동적 생성
  openGraph: {
    title: "6모부터 수능까지, 내 정시 위치를 추적하세요",
    description: "예측이 아니라 해석. 입시 사이클 전체를 함께 보는 AI 정시 전략 플랫폼.",
    type: "website",
    images: [{ url: "/opengraph-image", width: 1200, height: 630 }],
  },
};

// maximumScale 제한 없음 — 저시력 사용자의 핀치줌을 막지 않는다 (WCAG 1.4.4)
export const viewport: Viewport = {
  themeColor: "#0f172a",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko" suppressHydrationWarning>
      <body suppressHydrationWarning className="mx-auto min-h-dvh max-w-md bg-slate-50 px-4 py-4">
        {children}
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
