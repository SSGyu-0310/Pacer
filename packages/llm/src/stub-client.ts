/**
 * 결정적 스텁 클라이언트 — API 키가 없는 환경(개발/테스트/CI)에서 사용.
 * 엔진의 구조화 출력(reason code·구간 분포)만으로 §11.3 JSON을 템플릿 생성한다.
 * 같은 입력 = 같은 출력 (§18.2). LLM처럼 '계산'하지 않는다 — 입력을 설명할 뿐.
 */
import type { LlmReportInput } from "@pacer/core";
import {
  recommendationCode,
  strengthCode,
  weaknessCode,
  type ReasonCode,
} from "@pacer/shared";
import type { LlmClient } from "./client";
import { REASON_LABELS } from "./reason-labels";
import type { LlmReportOutput } from "./output-schema";

const EXAM_LABEL: Record<string, string> = {
  june_mock: "6월 모의평가",
  september_mock: "9월 모의평가",
  csat: "수능",
};

const SUBJECT_LABEL: Record<string, string> = {
  korean: "국어",
  math: "수학",
  english: "영어",
  history: "한국사",
  inquiry1: "탐구1",
  inquiry2: "탐구2",
  second_language: "제2외국어",
};

export class StubLlmClient implements LlmClient {
  readonly modelName = "stub-deterministic";

  complete(args: { prompt: string; input: LlmReportInput }): Promise<string> {
    const output = render(args.input);
    return Promise.resolve(JSON.stringify(output));
  }
}

function render(input: LlmReportInput): LlmReportOutput {
  const d = input.analysisSummary.bandDistribution;
  const total = d.stable + d.match + d.reach + d.challenge + d.risk;
  const examLabel = EXAM_LABEL[input.userContext.examType] ?? input.userContext.examType;

  const codes = input.analysisSummary.topReasonCodes.filter(
    (c): c is ReasonCode =>
      strengthCode.safeParse(c).success ||
      weaknessCode.safeParse(c).success ||
      recommendationCode.safeParse(c).success,
  );
  const strengths = codes.filter((c) => strengthCode.safeParse(c).success);
  const weaknesses = codes.filter((c) => weaknessCode.safeParse(c).success);
  const recommendations = codes.filter(
    (c) => recommendationCode.safeParse(c).success,
  );

  const strengthSubjects = input.scoreSummary.strengthSubjects
    .map((s) => SUBJECT_LABEL[s] ?? s)
    .join("·");

  const oneLine = `${examLabel} 성적 기준, 분석한 ${total}개 모집단위 중 안정 ${d.stable}곳 · 적정 ${d.match}곳 · 소신 ${d.reach}곳 · 도전 ${d.challenge}곳 · 위험 ${d.risk}곳으로 나타났습니다.`;

  const studentSummary = [
    oneLine,
    renderTrend(input),
    renderComparison(input),
    strengthSubjects
      ? `강점 과목은 ${strengthSubjects}입니다. 전년도 입결 기준의 참고용 분석이므로, 변동 가능성을 함께 고려해 주세요.`
      : `전년도 입결 기준의 참고용 분석이므로, 변동 가능성을 함께 고려해 주세요.`,
    input.targetSummary.targetUniversities.length
      ? `목표 대학(${input.targetSummary.targetUniversities.join(", ")}) 기준 현재 위치는 '${bandLabel(input.targetSummary.targetDistance)}' 부근입니다.`
      : "",
  ]
    .filter(Boolean)
    .join(" ");

  // 학부모용: 입시 용어(표준점수·백분위·변표 등) 없이 쉬운 문장으로 (§11.1, §18.2)
  const parentSummary = [
    `자녀의 ${examLabel} 성적을 기준으로 ${total}개 학과를 살펴본 결과, 여유 있게 지원할 만한 곳이 ${d.stable}곳, 성적대에 맞는 곳이 ${d.match}곳, 조금 높여 써볼 만한 곳이 ${d.reach}곳입니다.`,
    renderTrendForParent(input),
    `지금 결과는 작년 합격선과 비교한 참고용이며, 남은 기간 성적 변화에 따라 달라질 수 있습니다.`,
  ]
    .filter(Boolean)
    .join(" ");

  return {
    one_line_summary: oneLine,
    student_summary: studentSummary,
    parent_summary: parentSummary,
    strengths: strengths.map((c) => ({
      title: REASON_LABELS[c].title,
      description: REASON_LABELS[c].description,
      reason_code: c,
    })),
    weaknesses: weaknesses.map((c) => ({
      title: REASON_LABELS[c].title,
      description: REASON_LABELS[c].description,
      reason_code: c,
    })),
    recommended_actions: [
      ...recommendations.map((c) => REASON_LABELS[c].description),
      "분석 결과를 저장해 두고, 다음 시험 후 같은 기준으로 변화를 추적해 보세요.",
    ],
    warnings: [...input.warnings],
    next_cta:
      input.userContext.examType === "csat"
        ? "가/나/다군 원서 조합을 구성해 보세요."
        : "9월 모의평가 알림을 신청해 두면 같은 기준으로 변화를 추적할 수 있습니다.",
  };
}

function bandLabel(band: string): string {
  switch (band) {
    case "stable":
      return "안정";
    case "match":
      return "적정";
    case "reach":
      return "소신";
    case "challenge":
      return "도전";
    case "risk":
      return "위험";
    default:
      return "판단 보류";
  }
}

/** P1 — 6모↔9모 변화 요약 (§7.7.2). 입력 trend의 수치만 서술한다(계산 없음). */
function renderTrend(input: LlmReportInput): string {
  const t = input.scoreSummary.trend;
  if (!t) return "";
  const prevLabel = EXAM_LABEL[t.prevExamType] ?? t.prevExamType;
  const up = t.improvedSubjects.map((s) => SUBJECT_LABEL[s] ?? s).join("·");
  const down = t.declinedSubjects.map((s) => SUBJECT_LABEL[s] ?? s).join("·");
  const parts = [
    up ? `${up} 과목이 상승` : "",
    down ? `${down} 과목이 하락` : "",
  ].filter(Boolean);
  const subjectLine = parts.length
    ? `${prevLabel} 대비 ${parts.join(", ")}했습니다.`
    : `${prevLabel} 대비 과목별 위치 변화는 크지 않았습니다.`;
  const bandLine =
    t.bandImprovedCount || t.bandDeclinedCount || t.enteredCount || t.droppedCount
      ? `구간이 유리해진 모집단위 ${t.bandImprovedCount}곳, 불리해진 곳 ${t.bandDeclinedCount}곳, 새로 들어온 후보 ${t.enteredCount}곳, 빠진 후보 ${t.droppedCount}곳입니다.`
      : "";
  const approachLine =
    t.targetApproach.direction === "unchanged"
      ? ""
      : `목표 대학 접근도는 '${bandLabel(t.targetApproach.prev)}'에서 '${bandLabel(t.targetApproach.curr)}'(으)로 ${t.targetApproach.direction === "improved" ? "가까워졌습니다" : "멀어졌습니다"}.`;
  return [subjectLine, bandLine, approachLine].filter(Boolean).join(" ");
}

/** 학부모용 변화 요약 — 입시 용어 없이 */
function renderTrendForParent(input: LlmReportInput): string {
  const t = input.scoreSummary.trend;
  if (!t) return "";
  const prevLabel = EXAM_LABEL[t.prevExamType] ?? t.prevExamType;
  const up = t.improvedSubjects.map((s) => SUBJECT_LABEL[s] ?? s).join("·");
  const down = t.declinedSubjects.map((s) => SUBJECT_LABEL[s] ?? s).join("·");
  if (!up && !down) return `${prevLabel} 때와 비교하면 큰 변화 없이 비슷한 흐름입니다.`;
  return [
    up ? `${prevLabel} 때보다 ${up} 성적이 올랐고` : "",
    down ? `${down}은(는) 다소 내려갔습니다` : "",
  ]
    .filter(Boolean)
    .join(", ")
    .concat(".");
}

/** P2 — 교차검증 요약 (§7.7.4). 일치/불일치 분류만 서술, 정확도 우열 판정 금지(§11.1). */
function renderComparison(input: LlmReportInput): string {
  const c = input.competitorComparison;
  if (!c) return "";
  const n = c.totals.agree + c.totals.near + c.totals.disagree + c.totals.uncertain;
  const head = `직접 입력한 외부 도구 결과 ${n}건 중 자체 분석과 같은 구간 ${c.totals.agree}건, 인접 구간 ${c.totals.near}건, 차이가 큰 경우 ${c.totals.disagree}건, 비교 보류 ${c.totals.uncertain}건입니다.`;
  const tail =
    c.totals.disagree > 0
      ? " 차이가 큰 모집단위는 올해 실지원 표본 유입이나 모집단위 선호도 변화가 반영됐을 가능성이 있어, 단독 판단보다 가/나/다군 조합 안에서 리스크를 분산하는 접근이 필요합니다."
      : " 전반적으로 큰 불일치는 없으나, 표본이 계속 바뀌는 시기이므로 최종 지원 전 재확인이 필요합니다.";
  return head + tail;
}
