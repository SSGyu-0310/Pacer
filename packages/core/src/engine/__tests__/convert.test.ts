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

  it("한국사 가산 방식: addition 정책이면 등급 점수를 더한다", () => {
    const r = convertScore(
      standardRule({
        historyPolicy: { mode: "addition", byGrade: { 1: 10, 2: 8, 3: 5 } },
      }),
      normalized(),
    );
    expect(r.convertedScore).toBe(568.5); // 565.5 - 영어2등급 2 + 한국사3등급 5
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

  it("탐구 변환표준점수표가 있으면 백분위로 표 값을 찾아 exact 반영한다", () => {
    const r = convertScore(
      standardRule({
        inquiryPolicy: {
          count: 1,
          mode: "best_one",
          conversionTable: {
            from: "percentile",
            scoreMax: 200,
            byPercentile: { 94: 68, 90: 66 },
          },
        },
      }),
      normalized(),
    );
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(566.5);
    expect(r.approximations).toEqual([]);
  });

  it("탐구 변환표준점수표에 해당 백분위가 없으면 exact를 닫는다", () => {
    const r = convertScore(
      standardRule({
        inquiryPolicy: {
          count: 1,
          mode: "best_one",
          conversionTable: {
            from: "percentile",
            scoreMax: 200,
            byPercentile: { 90: 66 },
          },
        },
      }),
      normalized(),
    );
    expect(r.method).toBe("unsupported");
    expect(r.convertedScore).toBeNull();
  });

  it("과목별 공식 만점과 최종점 가산을 함께 반영한다: 숭실대식 예시", () => {
    const input = baseScores();
    input.scores = [
      { subject: "korean", standardScore: 134 },
      { subject: "math", selection: "확률과통계", standardScore: 123 },
      { subject: "english", grade: 1 },
      { subject: "history", grade: 4 },
      { subject: "inquiry1", selection: "생활과윤리", percentile: 83 },
      { subject: "inquiry2", selection: "사회문화", percentile: 88 },
    ];
    const r = convertScore(
      standardRule({
        totalScale: 1000,
        weights: { korean: 350, math: 200, inquiry: 250 },
        subjectScoreMaxes: { korean: 147, math: 139 },
        englishPolicy: {
          mode: "ratio",
          weight: 200,
          scoreMax: 200,
          byGrade: { 1: 200, 2: 200, 3: 197, 4: 193, 5: 160, 6: 144, 7: 120, 8: 72, 9: 0 },
        },
        historyPolicy: {
          mode: "deduction",
          byGrade: { 1: 0, 2: 0, 3: 0, 4: 0, 5: 2, 6: 2.5, 7: 3, 8: 3.5, 9: 4 },
        },
        inquiryPolicy: {
          count: 2,
          mode: "average",
          conversionTable: {
            from: "percentile",
            scoreMax: 70.12,
            byPercentile: { 83: 61.38, 88: 63.19 },
          },
        },
        finalAdjustments: [
          {
            subject: "inquiry",
            requiredInquiryCategory: "social",
            pointsFrom: "percentile",
            multiplier: 0.03,
          },
        ],
      }),
      normalizeScores(input),
    );

    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(923.22);
    expect(r.approximations).toEqual([]);
  });

  it("최종점 탐구 가산: requiredInquiryCategory만 있으면 조건에 맞는 탐구 과목만 더한다", () => {
    const input = baseScores();
    input.scores[5]!.selection = "생활과윤리";
    const r = convertScore(
      standardRule({
        finalAdjustments: [
          {
            subject: "inquiry",
            requiredInquiryCategory: "science",
            pointsFrom: "standardScore",
            multiplier: 0.07,
          },
        ],
      }),
      normalizeScores(input),
    );

    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(568.19); // 기본 563.5 + 물리학I 표준점수 67의 7%
  });

  it("혼합 반영(국·수 표준 + 탐구 변표 근사): 740.5, 근사 표기", () => {
    const r = convertScore(mixedRule(), normalized());
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(740.5);
    expect(r.approximations).toContain("inquiry_conversion");
  });

  it("혼합 반영에서 탐구 백분위 기준을 명시하면 근사 표기 없이 exact 계산한다", () => {
    const r = convertScore(
      mixedRule({
        subjectScoreTypes: { inquiry: "percentile" },
      }),
      normalized(),
    );
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(740.5);
    expect(r.approximations).toEqual([]);
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

  it("수학 선택과목 가산: 조건에 맞는 선택이면 basis에 배율을 적용한다", () => {
    const r = convertScore(
      standardRule({
        subjectAdjustments: [
          {
            subject: "math",
            requiredSelections: ["미적분", "기하"],
            multiplier: 1.05,
          },
        ],
      }),
      normalized(),
    );
    // 수학 135 → 141.75, 증가분 6.75/200*0.4*1000 = 13.5
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(577);
  });

  it("수학 선택과목 가산: 조건이 맞지 않으면 적용하지 않는다", () => {
    const r = convertScore(
      standardRule({
        subjectAdjustments: [
          {
            subject: "math",
            requiredSelections: ["기하"],
            multiplier: 1.05,
          },
        ],
      }),
      normalized(),
    );
    expect(r.convertedScore).toBe(563.5);
  });

  it("탐구 계열 가산: 과탐 조건이면 각 탐구 basis에 고정점을 더한다", () => {
    const r = convertScore(
      standardRule({
        subjectAdjustments: [
          {
            subject: "inquiry",
            requiredInquiryCategory: "science",
            points: 3,
          },
        ],
      }),
      normalized(),
    );
    // 탐구 평균 66 → 69, 증가분 3/200*0.3*1000 = 4.5
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(568);
  });

  it("탐구 계열 가산: 과탐 2과목 조건이면 전체 탐구 조합을 확인한 뒤 적용한다", () => {
    const r = convertScore(
      standardRule({
        subjectAdjustments: [
          {
            subject: "inquiry",
            requiredInquiryCategory: "science",
            requiredInquiryCategoryCount: 2,
            multiplier: 1.1,
          },
        ],
      }),
      normalized(),
    );
    // 탐구 평균 66 → 72.6, 증가분 6.6/200*0.3*1000 = 9.9
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(573.4);
  });

  it("탐구 계열 가산: 과탐 2과목 조건에서 한 과목만 과탐이면 적용하지 않는다", () => {
    const input = baseScores();
    input.scores[5]!.selection = "생활과윤리";
    const r = convertScore(
      standardRule({
        subjectAdjustments: [
          {
            subject: "inquiry",
            requiredInquiryCategory: "science",
            requiredInquiryCategoryCount: 2,
            multiplier: 1.1,
          },
        ],
      }),
      normalizeScores(input),
    );
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(563.5);
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

  it("상위 N과목 선택식: verified standard 규칙도 basis를 정규화해 totalScale로 환산한다", () => {
    const r = convertScore(
      standardRule({
        totalScale: 1000,
        weights: { korean: 0, math: 0, inquiry: 0 },
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 2,
          subjects: ["korean", "math", "inquiry"],
          rankWeights: [70, 30],
        },
      }),
      normalized(),
    );
    // 수학 135/200=67.5, 국어 131/200=65.5, 탐구 평균 66/200=33 → 상위2 = 수학/국어
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(669);
  });

  it("상위 N과목 선택식: 우수순 가중치가 있으면 순위별 반영비를 적용한다", () => {
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 100,
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 4,
          subjects: ["korean", "math", "english", "inquiry"],
          rankWeights: [40, 30, 20, 10],
        },
      }),
      normalized(),
    );
    // 수96, 영어95, 국93, 탐구평균92 → 96*40% + 95*30% + 93*20% + 92*10%
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(94.7);
  });

  it("상위 N과목 선택식: 필수 포함 영역은 성적이 낮아도 선택한 뒤 우수순 가중치를 적용한다", () => {
    const input = baseScores();
    input.scores[1] = {
      subject: "math",
      selection: "미적분",
      standardScore: 120,
      percentile: 70,
    };
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 100,
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 3,
          subjects: ["korean", "math", "english", "inquiry"],
          requiredSubjects: ["math"],
          rankWeights: [45, 35, 20],
        },
      }),
      normalizeScores(input),
    );
    // 수학이 상위3 밖이어도 필수 포함: 영어95*45% + 국어93*35% + 수학70*20%
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(89.3);
  });

  it("상위 N과목 선택식: 최우수 1영역도 exact로 계산한다", () => {
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 100,
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 1,
          subjects: ["korean", "math", "english", "inquiry"],
          rankWeights: [100],
        },
      }),
      normalized(),
    );
    // 국93, 수96, 영어95, 탐구평균92 → 최우수 1영역 = 수학96
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(96);
  });

  it("상위 N과목 선택식 exact에도 한국사 가산점을 적용한다", () => {
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 100,
        historyPolicy: { mode: "addition", byGrade: { 1: 10, 2: 9, 3: 8 } },
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 4,
          subjects: ["korean", "math", "english", "inquiry"],
          rankWeights: [40, 30, 20, 10],
        },
      }),
      normalized(),
    );
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(102.7);
  });

  it("상위 N과목 선택식: 그룹별 우수순 반영비를 합산한다", () => {
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 100,
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 4,
          subjects: ["korean", "math", "english", "inquiry"],
          groups: [
            { count: 2, subjects: ["korean", "math"], rankWeights: [40, 30] },
            { count: 2, subjects: ["english", "inquiry"], rankWeights: [20, 10] },
          ],
        },
      }),
      normalized(),
    );
    // 국/수: 수96*40% + 국93*30%, 영/탐: 영어95*20% + 탐구평균92*10%
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(94.5);
  });

  it("상위 N과목 선택식: 국/수 우수순과 영어·탐구 고정 반영을 함께 계산한다", () => {
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 1000,
        weights: { korean: 0, math: 0, inquiry: 0 },
        inquiryPolicy: { count: 1, mode: "best_one" },
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 4,
          subjects: ["korean", "math", "english", "inquiry"],
          groups: [
            { count: 2, subjects: ["korean", "math"], rankWeights: [35, 25] },
            { count: 1, subjects: ["english"], rankWeights: [20] },
            { count: 1, subjects: ["inquiry"], rankWeights: [20] },
          ],
        },
      }),
      normalized(),
    );

    // 국/수: 수96*35% + 국93*25%, 영어95*20%, 탐구상위1 94*20% → 946.5/1000
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(946.5);
  });

  it("상위 N과목 선택식: 그룹별 최우수 1영역 산식을 합산한다", () => {
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 100,
        selectionPolicy: {
          mode: "best_n_subjects",
          count: 2,
          subjects: ["korean", "math", "english", "inquiry"],
          groups: [
            { count: 1, subjects: ["korean", "math"], rankWeights: [70] },
            { count: 1, subjects: ["english", "inquiry"], rankWeights: [30] },
          ],
        },
      }),
      normalized(),
    );
    // 국/수 최우수 수96*70%, 영/탐 최우수 영어95*30%
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(95.7);
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

  it("대체 산식: A/B 유형을 각각 계산한 뒤 높은 점수를 선택한다", () => {
    const r = convertScore(
      ratioEnglishRule({
        totalScale: 1000,
        weights: { korean: 0, math: 0, inquiry: 0 },
        englishPolicy: {
          mode: "ratio",
          weight: 10,
          scoreMax: 100,
          byGrade: { 1: 100, 2: 95, 3: 88, 4: 80 },
        },
        formulaAlternatives: [
          { weights: { korean: 40, math: 30, inquiry: 20 } },
          { weights: { korean: 30, math: 40, inquiry: 20 } },
        ],
      }),
      normalized(),
    );
    // A=939, B=942이므로 B 유형을 선택
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(942);
  });

  it("대체 산식별 영어/한국사/탐구 정책 override를 반영한다", () => {
    const r = convertScore(
      standardRule({
        formulaAlternatives: [
          {
            weights: { korean: 0.3, math: 0.4, inquiry: 0.3 },
            historyPolicy: {
              mode: "addition",
              byGrade: { 1: 20, 2: 20, 3: 20, 4: 15 },
            },
          },
          { weights: { korean: 0.3, math: 0.4, inquiry: 0.3 } },
        ],
      }),
      normalized(),
    );

    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(583.5);
  });

  it("대체 산식별 scale이 다르면 raw 점수가 아니라 scale 대비 우위를 선택한다", () => {
    const r = convertScore(
      standardRule({
        calculationMode: "weighted_sum",
        totalScale: 100,
        weights: { korean: 0, math: 0, inquiry: 0 },
        englishPolicy: { mode: "addition", byGrade: { 1: 0, 2: 0, 3: 0 } },
        historyPolicy: { mode: "addition", byGrade: { 1: 0, 2: 0, 3: 0 } },
        formulaAlternatives: [
          {
            calculationMode: "weighted_sum",
            totalScale: 100,
            weights: { korean: 0.7, math: 0, inquiry: 0 },
          },
          {
            calculationMode: "weighted_sum",
            totalScale: 300,
            weights: { korean: 1.5, math: 0, inquiry: 0 },
          },
        ],
      }),
      normalized(),
    );

    // raw 점수는 두 번째 산식(196.5)이 더 크지만, scale 대비로는 첫 번째(91.7/100)가 우위다.
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(91.7);
    expect(r.scale).toBe(100);
  });

  it("직접 가중합 대체 산식: 탐구 2과목 변표 합산 후 A/B 중 높은 점수를 선택한다", () => {
    const r = convertScore(
      standardRule({
        totalScale: 1000,
        calculationMode: "weighted_sum",
        weights: { korean: 0, math: 0, inquiry: 0 },
        englishPolicy: {
          mode: "addition",
          byGrade: { 1: 12, 2: 10, 3: 8 },
        },
        historyPolicy: {
          mode: "addition",
          byGrade: { 1: 5, 2: 5, 3: 5 },
        },
        inquiryPolicy: {
          count: 2,
          mode: "sum",
          conversionTable: {
            from: "percentile",
            scoreMax: 200,
            byPercentile: { 94: 68, 90: 66 },
          },
        },
        formulaAlternatives: [
          { weights: { korean: 1.1, math: 1.3, inquiry: 0.6 } },
          { weights: { korean: 1.3, math: 1.1, inquiry: 0.6 } },
        ],
      }),
      normalized(),
    );

    // A = 131*1.1 + 135*1.3 + (68+66)*0.6 + 영어10 + 한국사5 = 415
    // B = 131*1.3 + 135*1.1 + (68+66)*0.6 + 영어10 + 한국사5 = 414.2
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(415);
    expect(r.approximations).toEqual([]);
  });

  it("기본점수+실질반영점수 합산식: Σ(기본점수 + 점수/최고점×실질반영점수)를 계산한다", () => {
    const r = convertScore(
      standardRule({
        totalScale: 300,
        calculationMode: "normalized_sum",
        weights: { korean: 90, math: 75, inquiry: 90 },
        subjectBaseScores: { korean: 45, math: 30, inquiry: 30 },
        englishPolicy: {
          mode: "addition",
          byGrade: { 1: 10, 2: 8, 3: 5 },
        },
        historyPolicy: {
          mode: "deduction",
          byGrade: { 1: 0, 2: 0, 3: 0 },
        },
      }),
      normalized(),
    );

    // 국 45+131/200*90, 수 30+135/200*75, 탐 30+66/200*90, 영어 +8
    expect(r.method).toBe("exact");
    expect(r.convertedScore).toBe(252.27);
    expect(r.scale).toBe(300);
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

  it("실기·학생부 등 비수능 구성요소가 있으면 전체 exact는 닫고 수능 파트 상대 비교를 한다", () => {
    const r = convertScore(
      percentileRule({
        csatWeight: 30,
        externalComponents: [{ kind: "practical", weight: 70, label: "실기" }],
      }),
      normalized(),
    );
    expect(r.method).toBe("relative");
    expect(r.convertedScore).toBe(93.9);
    expect(r.scale).toBe(100);
    expect(r.approximations).toContain("percentile_composite");
    expect(r.approximations).toContain("non_csat_component");
  });

  it("수능 이후 확정되는 공식 입력값이 필요하면 exact 대신 공개 반영비 기반 상대 비교를 한다", () => {
    const r = convertScore(
      standardRule({
        requiredInputs: [
          {
            kind: "national_max_standard_score",
            subjects: ["korean", "math", "inquiry"],
            label: "영역별 전국 최고 표준점수",
            availability: "post_csat",
          },
        ],
      }),
      normalized(),
    );
    expect(r.method).toBe("relative");
    expect(r.convertedScore).toBe(93.9);
    expect(r.scale).toBe(100);
    expect(r.approximations).toContain("percentile_composite");
    expect(r.approximations).toContain("formula_required_input");
  });

  it("탐구 변환표만 미확정이면 weighted_sum 공식과 영어/한국사 가산점을 보존해 0~100 상대 비교를 한다", () => {
    const r = convertScore(
      mixedRule({
        totalScale: 1000,
        calculationMode: "weighted_sum",
        weights: { korean: 1.1, math: 1.3, inquiry: 0.6 },
        englishPolicy: {
          mode: "addition",
          byGrade: { 1: 100, 2: 99.5, 3: 98.5, 4: 97, 5: 95, 6: 92.5, 7: 89.5, 8: 86, 9: 82 },
        },
        historyPolicy: {
          mode: "addition",
          byGrade: { 1: 10, 2: 10, 3: 10, 4: 10, 5: 9.5, 6: 9, 7: 8.5, 8: 8, 9: 7 },
        },
        inquiryPolicy: { count: 2, mode: "sum", conversionRisk: true },
        requiredInputs: [
          {
            kind: "conversion_table",
            subjects: ["inquiry"],
            label: "탐구 백분위 환산 자체 변환표준점수",
            availability: "post_csat",
          },
        ],
        formulaAlternatives: [
          {
            calculationMode: "weighted_sum",
            weights: { korean: 1.1, math: 1.3, inquiry: 0.6 },
          },
          {
            calculationMode: "weighted_sum",
            weights: { korean: 1.3, math: 1.1, inquiry: 0.6 },
          },
        ],
      }),
      normalized(),
    );
    expect(r.method).toBe("relative");
    expect(r.convertedScore).toBe(94.52);
    expect(r.scale).toBe(100);
    expect(r.approximations).toContain("formula_required_input");
    expect(r.approximations).toContain("inquiry_conversion");
    expect(r.approximations).toContain("english_addition_approx");
    expect(r.approximations).toContain("history_addition_approx");
  });

  it("대체 산식 중 하나라도 비수능 구성요소가 있으면 exact가 아니라 수능 파트 상대 비교로 처리한다", () => {
    const r = convertScore(
      percentileRule({
        formulaAlternatives: [
          { weights: { korean: 0.3, math: 0.4, inquiry: 0.3 } },
          {
            csatWeight: 30,
            weights: { korean: 0.3, math: 0.4, inquiry: 0.3 },
            externalComponents: [{ kind: "practical", weight: 70, label: "실기" }],
          },
        ],
      }),
      normalized(),
    );
    expect(r.method).toBe("relative");
    expect(r.convertedScore).toBe(93.9);
    expect(r.scale).toBe(100);
    expect(r.approximations).toContain("percentile_composite");
    expect(r.approximations).toContain("non_csat_component");
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
