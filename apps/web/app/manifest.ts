import type { MetadataRoute } from "next";

/** Web App Manifest (§17.4). display: standalone, start_url 은 PWA 진입 추적 파라미터 포함. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Pacer 정시 전략",
    short_name: "Pacer",
    description: "6모부터 수능까지, 내 정시 위치를 추적하세요.",
    start_url: "/dashboard?source=pwa",
    scope: "/",
    display: "standalone",
    theme_color: "#0f172a",
    background_color: "#ffffff",
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
