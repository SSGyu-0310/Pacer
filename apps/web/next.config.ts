import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  // 워크스페이스 TS 패키지를 Next가 트랜스파일 (도메인 코어/어댑터 직접 소비)
  transpilePackages: [
    "@pacer/shared",
    "@pacer/core",
    "@pacer/db",
    "@pacer/llm",
    "@pacer/notifications",
    "@pacer/reference-data",
  ],
};

export default config;
