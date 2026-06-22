import type { LlmReportInput } from "@pacer/core";

/**
 * 모델 호출 추상화 — Gateway는 어떤 클라이언트든 §11.3 JSON 문자열을 받는다.
 * 검증(스키마·금지어)은 항상 Gateway에서 수행되므로 클라이언트 출력은 신뢰하지 않는다.
 */
export interface LlmClient {
  /** §11.3 구조의 JSON 문자열을 반환해야 한다. */
  complete(args: { prompt: string; input: LlmReportInput }): Promise<string>;
  readonly modelName: string;
}
