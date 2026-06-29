/**
 * LLM 출력 JSON 스키마 검증 (§11.3) — LLM 출력은 신뢰하지 않는다.
 * snake_case(모델 출력) → 도메인 ReportContent(camelCase) 매핑까지 담당.
 */
import type { ReportContent } from "@pacer/core";
import { reasonCode } from "@pacer/shared";
import { z } from "zod";

/** §11.3 출력 구조 — reason_code는 컨트롤드 보캐블러리만 허용(§8.5) */
export const llmReportOutput = z.object({
  one_line_summary: z.string().min(1),
  student_summary: z.string().min(1),
  parent_summary: z.string().min(1),
  strengths: z.array(
    z.object({
      title: z.string().min(1),
      description: z.string().min(1),
      reason_code: reasonCode,
    }),
  ),
  weaknesses: z.array(
    z.object({
      title: z.string().min(1),
      description: z.string().min(1),
      reason_code: reasonCode,
    }),
  ),
  recommended_actions: z.array(z.string().min(1)),
  warnings: z.array(z.string()),
  next_cta: z.string().min(1),
});
export type LlmReportOutput = z.infer<typeof llmReportOutput>;

/** LLM 출력이 구조/어휘 규칙을 위반했을 때 (재생성 또는 차단 대상) */
export class LlmOutputError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "LlmOutputError";
  }
}

/** 원시 문자열 → 검증된 도메인 ReportContent */
export function parseReportOutput(raw: string): ReportContent {
  let json: unknown;
  try {
    json = JSON.parse(stripJsonFence(raw));
  } catch {
    throw new LlmOutputError("LLM 출력이 JSON이 아닙니다");
  }
  const parsed = llmReportOutput.safeParse(json);
  if (!parsed.success) {
    throw new LlmOutputError(
      `LLM 출력 스키마 위반(§11.3): ${parsed.error.issues
        .map((i) => i.path.join("."))
        .join(", ")}`,
    );
  }
  const o = parsed.data;
  return {
    oneLineSummary: o.one_line_summary,
    studentSummary: o.student_summary,
    parentSummary: o.parent_summary,
    strengths: o.strengths.map((s) => ({
      title: s.title,
      description: s.description,
      reasonCode: s.reason_code,
    })),
    weaknesses: o.weaknesses.map((w) => ({
      title: w.title,
      description: w.description,
      reasonCode: w.reason_code,
    })),
    recommendedActions: o.recommended_actions,
    warnings: o.warnings,
    nextCta: o.next_cta,
  };
}

function stripJsonFence(raw: string): string {
  return raw
    .trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}
