"use client";

import { createBrowserClient } from "@supabase/ssr";
import { getSupabaseBrowserConfig } from "./config";

export function hasSupabaseBrowserConfig(): boolean {
  return getSupabaseBrowserConfig() !== null;
}

export function createSupabaseBrowserClient() {
  const config = getSupabaseBrowserConfig();
  if (!config) {
    throw new Error("Supabase Auth 환경변수가 설정되지 않았습니다.");
  }
  return createBrowserClient(config.url, config.anonKey);
}
