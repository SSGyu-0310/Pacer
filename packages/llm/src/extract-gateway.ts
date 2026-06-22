import { assertNoBannedPhrases } from "./banned-words";
import { extractProposalSchema, type ExtractInput, type ExtractProposal } from "./extract-schema";
import { EXTRACT_SYSTEM_PROMPT } from "./extract-prompts";

export interface ExtractLlmClient {
  readonly modelName: string;
  completeExtract(args: { prompt: string; input: ExtractInput }): Promise<string>;
}

export class StubExtractLlmClient implements ExtractLlmClient {
  readonly modelName = "stub-deterministic-extract";

  completeExtract(args: { prompt: string; input: ExtractInput }): Promise<string> {
    const evidenceText = String(args.input.evidence.textPreview ?? args.input.evidence.rowText ?? "");
    const parsed = args.input.parsedFields;
    const proposal: ExtractProposal = {
      proposed: {
        scoreType:
          parsed.scoreType === "standard" ||
          parsed.scoreType === "percentile" ||
          parsed.scoreType === "mixed" ||
          parsed.scoreType === "custom"
            ? parsed.scoreType
            : undefined,
      },
      fieldFindings: [
        {
          field: "source",
          evidenceSupport: evidenceText ? "partial" : "missing",
          note: evidenceText
            ? "원문 미리보기를 기반으로 사람 검수용 초안을 생성했습니다."
            : "원문 미리보기가 부족합니다.",
        },
      ],
      uncertain: ["stub_extraction_requires_human_review"],
      evidenceQuote: evidenceText.slice(0, 600),
    };
    return Promise.resolve(JSON.stringify(proposal));
  }
}

export class AnthropicExtractLlmClient implements ExtractLlmClient {
  constructor(
    private readonly apiKey: string,
    readonly modelName = "claude-opus-4-8",
  ) {}

  async completeExtract(args: { prompt: string; input: ExtractInput }): Promise<string> {
    const res = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "x-api-key": this.apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: this.modelName,
        max_tokens: 2048,
        system: args.prompt,
        messages: [
          { role: "user", content: JSON.stringify(args.input, null, 2) },
          { role: "assistant", content: "{" },
        ],
      }),
    });
    if (!res.ok) throw new Error(`extract LLM failed: ${res.status} ${await res.text()}`);
    const body = (await res.json()) as { content: { type: string; text?: string }[] };
    const text = body.content
      .filter((part) => part.type === "text")
      .map((part) => part.text ?? "")
      .join("");
    return `{${text}`;
  }
}

export class LlmExtractGateway {
  constructor(private readonly client: ExtractLlmClient) {}

  async extract(input: ExtractInput): Promise<{
    proposal: ExtractProposal;
    modelName: string;
    promptVersion: string;
  }> {
    const raw = await this.client.completeExtract({
      prompt: EXTRACT_SYSTEM_PROMPT,
      input,
    });
    const parsed = extractProposalSchema.parse(JSON.parse(raw));
    // §11.4 금지어 필터 — evidenceQuote/note 등 자유텍스트가 합격보장류 표현을 담지 못하게 한다.
    assertNoBannedPhrases(parsed);
    return {
      proposal: parsed,
      modelName: this.client.modelName,
      promptVersion: "extract-v1",
    };
  }
}
