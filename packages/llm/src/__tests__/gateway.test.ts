import type { LlmReportInput } from "@pacer/core";
import { DISCLAIMER } from "@pacer/shared";
import { describe, expect, it } from "vitest";
import { findBannedPhrase } from "../banned-words";
import type { LlmClient } from "../client";
import { LlmGateway } from "../gateway";
import { PROMPT_VERSION } from "../prompts";
import { StubLlmClient } from "../stub-client";

/** §11.2 형태의 대표 입력 */
function input(over: Partial<LlmReportInput> = {}): LlmReportInput {
  return {
    reportType: "june_position_report",
    userContext: {
      role: "student",
      examType: "june_mock",
      gradeStatus: "high3",
      riskProfile: "balanced",
    },
    scoreSummary: {
      strengthSubjects: ["math"],
      weaknessSubjects: ["inquiry2"],
      trend: null,
    },
    analysisSummary: {
      bandDistribution: { stable: 8, match: 17, reach: 24, challenge: 31, risk: 48 },
      topReasonCodes: [
        "math_weight_advantage",
        "english_penalty_risk",
        "low_data_confidence",
        "explore_math_heavy",
      ],
    },
    targetSummary: {
      targetUniversities: ["연세대", "중앙대"],
      targetDistance: "reach",
    },
    warnings: ["본 결과는 6월 모의평가 기준이며, 실제 수능 결과와 다를 수 있습니다."],
    ...over,
  };
}

const gateway = () => new LlmGateway(new StubLlmClient());

describe("LlmGateway + StubLlmClient (§11, §18.2)", () => {
  it("§11.3 구조의 리포트를 생성한다 (학생용·학부모용 동시)", async () => {
    const r = await gateway().generate(input());
    expect(r.content.oneLineSummary.length).toBeGreaterThan(0);
    expect(r.content.studentSummary.length).toBeGreaterThan(0);
    expect(r.content.parentSummary.length).toBeGreaterThan(0);
    expect(r.content.nextCta.length).toBeGreaterThan(0);
    expect(r.modelName).toBe("stub-deterministic");
    expect(r.promptVersion).toBe(PROMPT_VERSION);
  });

  it("금지어 미포함 (§18.2): 모든 텍스트가 §11.4 필터를 통과한다", async () => {
    const r = await gateway().generate(input());
    const all = JSON.stringify(r.content);
    expect(findBannedPhrase(all)).toBeNull();
  });

  it("reason code 기반 설명 (§18.2): 강점/약점이 입력 코드에서만 나온다", async () => {
    const r = await gateway().generate(input());
    const inputCodes = input().analysisSummary.topReasonCodes;
    expect(r.content.strengths.map((s) => s.reasonCode)).toEqual([
      "math_weight_advantage",
    ]);
    expect(r.content.weaknesses.map((w) => w.reasonCode)).toEqual([
      "english_penalty_risk",
      "low_data_confidence",
    ]);
    for (const s of [...r.content.strengths, ...r.content.weaknesses]) {
      expect(inputCodes).toContain(s.reasonCode);
    }
  });

  it("같은 입력 = 일관된 결과 (§18.2)", async () => {
    const a = await gateway().generate(input());
    const b = await gateway().generate(input());
    expect(a).toEqual(b);
  });

  it("학부모용 문체 쉬움 (§18.2): 입시 용어 미사용", async () => {
    const r = await gateway().generate(input());
    for (const term of ["표준점수", "백분위", "변환표준점수", "반영비", "변표"]) {
      expect(r.content.parentSummary).not.toContain(term);
    }
  });

  it("합격 단정 없음 (§18.2): 단정 표현 미포함", async () => {
    const r = await gateway().generate(input());
    const all = JSON.stringify(r.content);
    for (const phrase of ["합격 보장", "무조건", "100%", "확실히 붙음"]) {
      expect(all).not.toContain(phrase);
    }
  });

  it("면책 문구 포함 (§18.2): warnings에 §13.3 면책이 동봉된다", async () => {
    const r = await gateway().generate(input());
    expect(r.content.warnings).toContain(DISCLAIMER);
    // 입력 warnings도 보존
    expect(r.content.warnings).toContain(
      "본 결과는 6월 모의평가 기준이며, 실제 수능 결과와 다를 수 있습니다.",
    );
  });

  it("금지어를 뱉는 클라이언트는 차단된다 (§11.4)", async () => {
    const bad: LlmClient = {
      modelName: "bad-model",
      complete: async () => {
        const r = await new StubLlmClient().complete({
          prompt: "",
          input: input(),
        });
        const obj = JSON.parse(r) as { one_line_summary: string };
        obj.one_line_summary = "이 조합이면 합격 보장입니다.";
        return JSON.stringify(obj);
      },
    };
    await expect(new LlmGateway(bad).generate(input())).rejects.toThrow(
      "금지 표현",
    );
  });

  it("JSON이 아니거나 스키마 위반이면 차단된다 (§11.3)", async () => {
    const notJson: LlmClient = {
      modelName: "bad",
      complete: () => Promise.resolve("죄송합니다, JSON을 만들 수 없어요"),
    };
    await expect(new LlmGateway(notJson).generate(input())).rejects.toThrow(
      "JSON",
    );

    const wrongSchema: LlmClient = {
      modelName: "bad",
      complete: () => Promise.resolve('{"one_line_summary": "x"}'),
    };
    await expect(new LlmGateway(wrongSchema).generate(input())).rejects.toThrow(
      "스키마",
    );
  });

  it("임의 reason_code는 스키마에서 거부된다 (§8.5 컨트롤드 보캐블러리)", async () => {
    const madeUpCode: LlmClient = {
      modelName: "bad",
      complete: async () => {
        const r = await new StubLlmClient().complete({
          prompt: "",
          input: input(),
        });
        const obj = JSON.parse(r) as {
          strengths: { title: string; description: string; reason_code: string }[];
        };
        obj.strengths.push({
          title: "x",
          description: "y",
          reason_code: "totally_made_up_code",
        });
        return JSON.stringify(obj);
      },
    };
    await expect(new LlmGateway(madeUpCode).generate(input())).rejects.toThrow(
      "스키마",
    );
  });

  it("입력 topReasonCodes에 없는 허용 reason_code도 차단된다 (§11.1)", async () => {
    const outOfInputCode: LlmClient = {
      modelName: "bad",
      complete: async () => {
        const r = await new StubLlmClient().complete({
          prompt: "",
          input: input(),
        });
        const obj = JSON.parse(r) as {
          strengths: { title: string; description: string; reason_code: string }[];
        };
        obj.strengths.push({
          title: "x",
          description: "y",
          reason_code: "korean_weight_advantage",
        });
        return JSON.stringify(obj);
      },
    };
    await expect(new LlmGateway(outOfInputCode).generate(input())).rejects.toThrow(
      "입력에 없는 reason_code",
    );
  });
});
