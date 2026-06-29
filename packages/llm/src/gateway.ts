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

    // §11.4 금지어 필터 — LLM 생성 산문만 검사(positionReport는 엔진 계산 데이터이므로 제외).
    assertNoBannedPhrases(content);

    return {
      content: { ...content, positionReport: input.positionReport },
      modelName: this.client.modelName,
      promptVersion: PROMPT_VERSION,
    };
  }
}

/**
 * 운영 복원력(§11) — 1차 리포터(실모델)가 실패하면 2차(결정론적 스텁)로 폴백한다.
 * 포지션 리포트의 숫자·라인·시나리오는 엔진 계산값이라 어느 쪽이든 동일하고,
 * 폴백은 산문만 템플릿으로 대체한다("데이터가 뼈대, AI는 살" — blueprint).
 * 실모델 지연/검증 실패에도 사용자는 항상 유효한 리포트를 받는다.
 */
export class FallbackLlmReporter implements LlmReporter {
  constructor(
    private readonly primary: LlmReporter,
    private readonly fallback: LlmReporter,
  ) {}

  async generate(input: LlmReportInput): ReturnType<LlmReporter["generate"]> {
    try {
      return await this.primary.generate(input);
    } catch (e) {
      console.warn(
        `[report] 1차 LLM 실패 → 결정론적 폴백 사용: ${
          e instanceof Error ? e.message : String(e)
        }`,
      );
      return this.fallback.generate(input);
    }
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
