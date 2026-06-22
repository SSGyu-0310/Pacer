/**
 * 분석 이벤트명 — 단일 진실 공급원 (§16.5).
 * 이 이름 그대로 사용한다. reminder_opt_in / return_from_reminder 는 channel 파라미터 필수.
 */
import { z } from "zod";

export const analyticsEvent = z.enum([
  "landing_view",
  "cta_click",
  "cycle_created",
  "score_input_start",
  "score_submit",
  "target_saved",
  "analysis_run",
  "analysis_success",
  "report_view",
  "report_saved",
  "share_card_created",
  "reminder_opt_in", // channel 파라미터: kakao / email / web_push
  "pwa_install_prompt_shown",
  "pwa_installed",
  "return_from_reminder", // channel 파라미터 포함
  "premium_click",
  "purchase_complete",
  "competitor_signal_added",
  "application_plan_created",
  "final_outcome_submitted",
]);
export type AnalyticsEvent = z.infer<typeof analyticsEvent>;
