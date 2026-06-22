import type { Config } from "tailwindcss";

/**
 * 디자인 토큰 — v0 분석 화면(analysis-results-screen)의 band 시맨틱을 이식.
 * 구간 5색: 안정=green, 적정=blue, 소신=amber, 도전=orange, 위험=red (spec §8.3)
 */
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        band: {
          stable: { DEFAULT: "#059669", soft: "#ecfdf5", fg: "#047857" },
          match: { DEFAULT: "#2563eb", soft: "#eff6ff", fg: "#1d4ed8" },
          reach: { DEFAULT: "#f59e0b", soft: "#fffbeb", fg: "#b45309" },
          challenge: { DEFAULT: "#f97316", soft: "#fff7ed", fg: "#c2410c" },
          risk: { DEFAULT: "#ef4444", soft: "#fef2f2", fg: "#b91c1c" },
        },
        warn: { DEFAULT: "#f97316", soft: "#fff7ed", fg: "#c2410c" },
      },
    },
  },
  plugins: [],
};

export default config;
