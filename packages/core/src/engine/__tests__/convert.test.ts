import { describe, expect, it } from "vitest";
import { convertScore } from "../convert";
import { normalizeScores } from "../normalize";
import {
  baseScores,
  mixedRule,
  percentileRule,
  ratioEnglishRule,
  standardRule,
} from "./fixtures";

const normalized = () => normalizeScores(baseScores());

describe("convertScore (§8.2, §18.1)", () => {
  it("표준점수 반영 대학: (0.3·131/200 + 0.4·135/200 + 0.3·66/200)·1000 − 영어2등급 2점 = 563.5", () => {
    const r = convertScore(standardRule(), normalized());
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(563.5);
    expect(r.scale).toBe(1000);
    expect(r.approximations).toEqual([]);
  });

  it("백분위 반영 대학: (0.3·93 + 0.4·96 + 0.3·92) − 영어 0.5 − 한국사 0.2 = 93.2", () => {
    const r = convertScore(percentileRule(), normalized());
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(93.2);
    expect(r.scale).toBe(100);
  });

  it("영어 감점 적용: 1등급이면 무감점 → 565.5", () => {
    const input = baseScores();
    input.scores[2]!.grade = 1;
    const r = convertScore(standardRule(), normalizeScores(input));
    expect(r.convertedScore).toBe(565.5);
  });

  it("영어 가산 방식: addition 정책이면 등급 점수를 더한다", () => {
    const rule = standardRule({
      englishPolicy: { mode: "addition", byGrade: { 1: 10, 2: 8, 3: 5 } },
    });
    const r = convertScore(rule, normalized());
    expect(r.convertedScore).toBe(573.5); // 565.5 + 8
  });

  it("한국사 감점 적용: 4등급이면 −2점 → 561.5", () => {
    const input = baseScores();
    input.scores[3]!.grade = 4;
    const r = convertScore(standardRule(), normalizeScores(input));
    expect(r.convertedScore).toBe(561.5);
  });

  it("탐구 평균 반영: (67+65)/2 = 66 basis", () => {
    const r = convertScore(
      standardRule({ inquiryPolicy: { count: 2, mode: "average" } }),
      normalized(),
    );
    expect(r.convertedScore).toBe(563.5);
  });

  it("탐구 2과목 반영 대학에서 1과목만 있으면 분석 불가", () => {
    const input = baseScores();
    input.scores = input.scores.filter((s) => s.subject !== "inquiry2");
    const r = convertScore(
      standardRule({ inquiryPolicy: { count: 2, mode: "average" } }),
      normalizeScores(input),
    );
    expect(r.method).toBe("unsupported");
    expect(r.convertedScore).toBeNull();
  });

  it("탐구 상위 1과목 반영: max(67,65) = 67 basis → 565", () => {
    const r = convertScore(
      standardRule({ inquiryPolicy: { count: 1, mode: "best_one" } }),
      normalized(),
    );
    expect(r.convertedScore).toBe(565);
  });

  it("혼합 반영(국·수 표준 + 탐구 변표 근사): 740.5, 근사 표기", () => {
    const r = convertScore(mixedRule(), normalized());
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(740.5);
    expect(r.approximations).toContain("inquiry_conversion");
  });

  it("영어 비율반영(ratio): 영어를 가중평균에 합산 → (30·93+30·96+20·92+20·95)/100·10 = 941", () => {
    const r = convertScore(ratioEnglishRule(), normalized());
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(941);
    expect(r.scale).toBe(1000);
    // ratio 영어는 가산/감점 후처리를 타지 않는다
    expect(r.approximations).toEqual([]);
  });

  it("영어 비율반영: 영어 1등급이면 환산점수 100 → 951", () => {
    const input = baseScores();
    input.scores[2]!.grade = 1; // 영어 환산점수 95→100
    const r = convertScore(ratioEnglishRule(), normalizeScores(input));
    // 영어 항 19.0→20.0 → numerator 94.1→95.1, /100 ×1000 = 951
    expect(r.convertedScore).toBe(951);
  });

  it("영어 비율반영 + 미검수 규칙은 근사에도 영어 합산: 94.1, english_ratio_approx 표기", () => {
    const r = convertScore(
      ratioEnglishRule({ verifiedStatus: "parsed" }),
      normalized(),
    );
    expect(r.method).toBe("approx");
    expect(r.convertedScore).toBe(94.1);
    expect(r.scale).toBe(100);
    expect(r.approximations).toContain("english_ratio_approx");
  });

  it("상위 N과목 선택식: 국/수/영/탐 중 상위 2개 백분위 평균", () => {
    const r = convertScore(
      ratioEnglishRule({
        verifiedStatus: "parsed",
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 2,
          subjects: ["korean", "math", "english", "inquiry"],
        },
      }),
      normalized(),
    );
    // 국93, 수96, 영어95, 탐구평균92 → 상위2 = 수96 + 영어95
    expect(r.method).toBe("approx");
    expect(r.convertedScore).toBe(95.5);
    expect(r.approximations).toContain("best_subjects_selection");
  });

  it("상위 N과목 선택식: verified percentile 규칙은 totalScale로 환산한다", () => {
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 100,
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 3,
          subjects: ["korean", "math", "english", "inquiry"],
        },
      }),
      normalized(),
    );
    // 상위3 = 수96 + 영어95 + 국93
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(94.67);
  });

  it("상위 N과목 선택식: 후보 과목 점수가 누락되면 계산하지 않는다", () => {
    const input = baseScores();
    input.scores = input.scores.filter((score) => score.subject !== "english");
    const r = convertScore(
      ratioEnglishRule({
        verifiedStatus: "parsed",
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 2,
          subjects: ["korean", "math", "english", "inquiry"],
        },
      }),
      normalizeScores(input),
    );
    expect(r.method).toBe("unsupported");
  });

  it("검수 미완료 규칙은 근사 비교(백분위 합성): 93.9, 만점 100", () => {
    const r = convertScore(
      standardRule({ verifiedStatus: "parsed" }),
      normalized(),
    );
    expect(r.method).toBe("approx");
    expect(r.convertedScore).toBe(93.9);
    expect(r.scale).toBe(100);
    expect(r.approximations).toContain("percentile_composite");
  });

  it("custom 환산식은 분석 불가", () => {
    const r = convertScore(standardRule({ scoreType: "custom" }), normalized());
    expect(r.method).toBe("unsupported");
    expect(r.convertedScore).toBeNull();
    expect(r.scale).toBeNull();
  });

  it("필요 점수 누락(국어 표준점수 없음) → 분석 불가", () => {
    const input = baseScores();
    input.scores[0] = { subject: "korean", percentile: 93 }; // 표준점수 제거
    const r = convertScore(standardRule(), normalizeScores(input));
    expect(r.method).toBe("unsupported");
  });

  it("결정성: 같은 입력 = 같은 출력", () => {
    const a = convertScore(standardRule(), normalized());
    const b = convertScore(standardRule(), normalized());
    expect(a).toEqual(b);
  });
});
