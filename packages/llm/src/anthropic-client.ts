/**
 * Anthropic Messages API 클라이언트 (SDK 없이 fetch).
 * ANTHROPIC_API_KEY 가 있는 운영 환경에서 사용 — 없으면 composition root가
 * StubLlmClient 를 주입한다. 출력 검증은 Gateway가 담당하므로 여기서는 호출만.
 */
import type { LlmReportInput } from "@pacer/core";
import type { LlmClient } from "./client";

const API_URL = "https://api.anthropic.com/v1/messages";
const API_VERSION = "2023-06-01";

export class AnthropicLlmClient implements LlmClient {
  constructor(
    private readonly apiKey: string,
    readonly modelName: string = "claude-sonnet-4-6",
  ) {}

  async complete(args: { prompt: string; input: LlmReportInput }): Promise<string> {
    const res = await fetch(API_URL, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": this.apiKey,
        "anthropic-version": API_VERSION,
      },
      body: JSON.stringify({
        model: this.modelName,
        max_tokens: 2048,
        system: args.prompt,
        messages: [
          {
            role: "user",
            content: JSON.stringify(args.input, null, 2),
          },
          // §11.3 JSON 형식을 강제하기 위한 프리필
          { role: "assistant", content: "{" },
        ],
      }),
    });

    if (!res.ok) {
      throw new Error(`LLM 호출 실패: ${res.status} ${await res.text()}`);
    }

    const body = (await res.json()) as {
      content: { type: string; text?: string }[];
    };
    const text = body.content
      .filter((b) => b.type === "text")
      .map((b) => b.text ?? "")
      .join("");
    return `{${text}`;
  }
}
