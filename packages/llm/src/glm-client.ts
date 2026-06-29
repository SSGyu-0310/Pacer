/**
 * Z.AI GLM 클라이언트 — OpenAI 호환 REST API (ZAI_API_KEY 환경변수).
 * response_format: json_object 로 JSON 강제. 출력 검증은 Gateway가 담당.
 */
import type { LlmReportInput } from "@pacer/core";
import type { LlmClient } from "./client";

const API_URL = "https://api.z.ai/api/paas/v4/chat/completions";

const KOREAN_INSTRUCTION =
  "반드시 한국어로 작성하라. 모든 설명, 요약, 강점/약점/권장사항 텍스트는 자연스러운 한국어 문장으로 출력한다.";

/** 리포트 1건의 LLM 호출 상한(ms). 라우트 maxDuration(60s)보다 짧게 둬 폴백 여지를 남긴다. */
const DEFAULT_TIMEOUT_MS = 50_000;

export class GlmLlmClient implements LlmClient {
  private readonly timeoutMs: number;

  constructor(
    private readonly apiKey: string,
    readonly modelName: string = "glm-5.1",
    timeoutMs = Number(process.env.LLM_TIMEOUT_MS) || DEFAULT_TIMEOUT_MS,
  ) {
    this.timeoutMs = timeoutMs;
  }

  async complete(args: { prompt: string; input: LlmReportInput }): Promise<string> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let res: Response;
    try {
      res = await fetch(API_URL, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${this.apiKey}`,
        },
        signal: controller.signal,
        body: JSON.stringify({
          model: this.modelName,
          max_tokens: 4096,
          temperature: 0.3,
          // 리포트는 엔진 데이터의 '서술'이라 추론이 불필요하다. thinking을 끄면
          // glm-5.1 응답이 수십 초→수 초로 단축돼 라우트 시간 예산을 지킨다(§11.1).
          thinking: { type: "disabled" },
          response_format: { type: "json_object" },
          messages: [
            {
              role: "system",
              content: `${args.prompt}\n\n${KOREAN_INSTRUCTION}`,
            },
            {
              role: "user",
              content: `다음 데이터로 리포트를 작성해줘. JSON만 출력해.\n\n<data>\n${JSON.stringify(args.input, null, 2)}\n</data>`,
            },
          ],
        }),
      });
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") {
        throw new Error(`GLM 호출 시간 초과(${this.timeoutMs}ms)`);
      }
      throw e;
    } finally {
      clearTimeout(timer);
    }

    if (!res.ok) {
      throw new Error(`GLM 호출 실패: ${res.status} ${await res.text()}`);
    }

    const body = (await res.json()) as {
      choices: { message: { content: string } }[];
    };
    const content = body.choices[0]?.message?.content;
    if (!content) throw new Error("GLM 응답이 비어 있습니다");
    return content;
  }
}
