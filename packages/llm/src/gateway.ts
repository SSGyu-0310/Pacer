import type { LlmReportInput, LlmReporter, ReportContent } from "@pacer/core";
import { DISCLAIMER } from "@pacer/shared";
import { assertNoBannedPhrases } from "./banned-words";
import type { LlmClient } from "./client";
import { LlmOutputError, parseReportOutput } from "./output-schema";
import { PROMPT_TEMPLATES, PROMPT_VERSION } from "./prompts";

/**
 * LLM Gateway (§11.1) — 계산하지 않고 "설명"만 생성한다.
 * 흐름: 프롬프트 조립(§11.2) → 모델 호출 → JSON schema 검증(§11.3) →
 *       면책 문구 보강(§13.3, §18.2) → 금지어 필터(§11.4) →
 *       model_name/prompt_version 부착(§9.13 재현성).
 *
 * 클라이언트 출력은 신뢰하지 않는다 — 스텁이든 실모델이든 같은 검증을 통과해야 한다.
 */
export class LlmGateway implements LlmReporter {
  constructor(private readonly client: LlmClient) {}

  async generate(input: LlmReportInput): Promise<{
    content: ReportContent;
    modelName: string;
    promptVersion: string;
  }> {
    const prompt = PROMPT_TEMPLATES[input.reportType];

    const raw = await this.client.complete({ prompt, input });

    // §11.3 스키마 + reason code 보캐블러리 검증
    const parsed = parseReportOutput(raw);
    assertReasonCodesFromInput(parsed, input);

    // §18.2 면책 문구 포함 — 모든 리포트 warnings 에 동봉(§13.3)
    const content: ReportContent = parsed.warnings.includes(DISCLAIMER)
      ? parsed
      : { ...parsed, warnings: [...parsed.warnings, DISCLAIMER] };

    // §11.4 금지어 필터 — 위반 시 throw(차단). 통과 못한 리포트는 저장되지 않는다.
    assertNoBannedPhrases(content);

    return {
      content,
      modelName: this.client.modelName,
      promptVersion: PROMPT_VERSION,
    };
  }
}

function assertReasonCodesFromInput(
  content: ReportContent,
  input: LlmReportInput,
): void {
  const allowed = new Set(input.analysisSummary.topReasonCodes);
  for (const item of [...content.strengths, ...content.weaknesses]) {
    if (!allowed.has(item.reasonCode)) {
      throw new LlmOutputError(
        `입력에 없는 reason_code 사용: ${item.reasonCode}`,
      );
    }
  }
}
