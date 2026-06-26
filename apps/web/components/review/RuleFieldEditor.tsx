"use client";

import { useState } from "react";

type ScoreType = "standard" | "percentile" | "mixed" | "custom";
type CalculationMode = "weighted_average" | "weighted_sum" | "normalized_sum";
type EnglishMode = "deduction" | "addition" | "ratio";
type HistoryMode = "deduction" | "addition";
type InquiryMode = "average" | "best_one" | "sum";
type SelectionCount = "1" | "2" | "3" | "4";
type SelectionSubject = "korean" | "math" | "english" | "inquiry";
type ExternalComponentKind = "student_record" | "practical" | "interview" | "essay" | "document" | "other";
type ExternalComponentDraft = {
  kind: ExternalComponentKind;
  weight: string;
  label: string;
  required: boolean;
};

export interface RuleEditorValue {
  scoreType: ScoreType;
  totalScale: string;
  csatWeight: string;
  calculationMode: CalculationMode;
  weights: { korean: string; math: string; inquiry: string };
  subjectScoreTypesJson: string;
  scoreMaxesJson: string;
  subjectBaseScoresJson: string;
  selectionEnabled: boolean;
  selectionCount: SelectionCount;
  selectionSubjects: Record<SelectionSubject, boolean>;
  selectionRequiredSubjects: Record<SelectionSubject, boolean>;
  selectionRankWeights: string[];
  selectionGroupsJson: string;
  formulaAlternativesJson: string;
  subjectAdjustmentsJson: string;
  finalAdjustmentsJson: string;
  requiredInputsJson: string;
  externalComponents: ExternalComponentDraft[];
  externalComponentsJson: string;
  englishMode: EnglishMode;
  englishWeight: string;
  englishScoreMax: string;
  englishByGrade: Record<string, string>;
  historyMode: HistoryMode;
  historyByGrade: Record<string, string>;
  inquiryCount: "1" | "2";
  inquiryMode: InquiryMode;
  inquiryConversionTableJson: string;
  inquiryConversionRisk: boolean;
  eligibilityJson: string;
}

const GRADES = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];
const SELECTION_SUBJECTS: { value: SelectionSubject; label: string }[] = [
  { value: "korean", label: "국어" },
  { value: "math", label: "수학" },
  { value: "english", label: "영어" },
  { value: "inquiry", label: "탐구" },
];
const ALL_SELECTION_SUBJECTS: Record<SelectionSubject, boolean> = {
  korean: true,
  math: true,
  english: true,
  inquiry: true,
};
const EMPTY_REQUIRED_SUBJECTS: Record<SelectionSubject, boolean> = {
  korean: false,
  math: false,
  english: false,
  inquiry: false,
};

type SelectionTemplate = {
  label: string;
  count: SelectionCount;
  required?: SelectionSubject[];
  rankWeights?: string[];
  groups?: Record<string, unknown>[];
};

const SELECTION_TEMPLATES: SelectionTemplate[] = [
  {
    label: "국수 40/30 + 영탐 20/10",
    count: "4",
    groups: [
      { count: 2, subjects: ["korean", "math"], rankWeights: [40, 30] },
      { count: 2, subjects: ["english", "inquiry"], rankWeights: [20, 10] },
    ],
  },
  {
    label: "국수 35/25 + 영20 + 탐20",
    count: "4",
    groups: [
      { count: 2, subjects: ["korean", "math"], rankWeights: [35, 25] },
      { count: 1, subjects: ["english"], rankWeights: [20] },
      { count: 1, subjects: ["inquiry"], rankWeights: [20] },
    ],
  },
  {
    label: "우수3 수학필수 45/35/20",
    count: "3",
    required: ["math"],
    rankWeights: ["45", "35", "20"],
  },
  {
    label: "전체 우수4 35/30/20/15",
    count: "4",
    rankWeights: ["35", "30", "20", "15"],
  },
];
const EXTERNAL_COMPONENT_KINDS: { value: ExternalComponentKind; label: string }[] = [
  { value: "practical", label: "실기" },
  { value: "student_record", label: "학생부" },
  { value: "interview", label: "면접" },
  { value: "essay", label: "논술" },
  { value: "document", label: "서류" },
  { value: "other", label: "기타" },
];

/* ── 초기값 / 변환 / 검증 (AdminReviewApp에서 재사용) ── */

export function emptyRuleEditorValue(): RuleEditorValue {
  return {
    scoreType: "custom",
    totalScale: "",
    csatWeight: "",
    calculationMode: "weighted_average",
    weights: { korean: "", math: "", inquiry: "" },
    subjectScoreTypesJson: "",
    scoreMaxesJson: "",
    subjectBaseScoresJson: "",
    selectionEnabled: false,
    selectionCount: "2",
    selectionSubjects: { korean: true, math: true, english: true, inquiry: true },
    selectionRequiredSubjects: { korean: false, math: false, english: false, inquiry: false },
    selectionRankWeights: ["", "", "", ""],
    selectionGroupsJson: "",
    formulaAlternativesJson: "",
    subjectAdjustmentsJson: "",
    finalAdjustmentsJson: "",
    requiredInputsJson: "",
    externalComponents: [],
    externalComponentsJson: "",
    englishMode: "deduction",
    englishWeight: "",
    englishScoreMax: "100",
    englishByGrade: {},
    historyMode: "deduction",
    historyByGrade: {},
    inquiryCount: "2",
    inquiryMode: "average",
    inquiryConversionTableJson: "",
    inquiryConversionRisk: false,
    eligibilityJson: "",
  };
}

/** 파싱된 규칙 + AI 초안에서 편집기 초기값을 만든다. 엔진 형태가 아니면 빈 칸으로 둔다. */
export function ruleEditorValueFromDetail(
  parsedFields: Record<string, unknown>,
  proposed: Record<string, unknown>,
): RuleEditorValue {
  const base = emptyRuleEditorValue();
  const st = pickScoreType(proposed.scoreType ?? proposed.score_type ?? parsedFields.score_type);
  if (st) base.scoreType = st;

  const formula = proposalFormula(proposed) ?? engineFormula(parsedFields.formula_json);
  if (formula) {
    if (typeof formula.totalScale === "number") base.totalScale = String(formula.totalScale);
    if (typeof formula.csatWeight === "number") base.csatWeight = String(formula.csatWeight);
    if (
      formula.calculationMode === "weighted_average" ||
      formula.calculationMode === "weighted_sum" ||
      formula.calculationMode === "normalized_sum"
    ) {
      base.calculationMode = formula.calculationMode;
    }
    const w = asObject(formula.weights);
    if (w) {
      base.weights = {
        korean: numToStr(w.korean),
        math: numToStr(w.math),
        inquiry: numToStr(w.inquiry),
      };
    }
    if (asObject(formula.scoreMaxes)) {
      base.scoreMaxesJson = JSON.stringify(formula.scoreMaxes, null, 2);
    }
    if (asObject(formula.subjectBaseScores)) {
      base.subjectBaseScoresJson = JSON.stringify(formula.subjectBaseScores, null, 2);
    }
    if (asObject(formula.subjectScoreTypes)) {
      base.subjectScoreTypesJson = JSON.stringify(formula.subjectScoreTypes, null, 2);
    }
    const selection = asObject(formula.selectionPolicy);
    if (selection?.mode === "best_n_subjects") {
      const count = selection.count;
      const subjects = Array.isArray(selection.subjects)
        ? selection.subjects.filter(isSelectionSubject)
        : [];
      base.selectionEnabled = true;
      if (count === 1 || count === 2 || count === 3 || count === 4) {
        base.selectionCount = String(count) as SelectionCount;
      }
      if (subjects.length > 0) {
        base.selectionSubjects = {
          korean: subjects.includes("korean"),
          math: subjects.includes("math"),
          english: subjects.includes("english"),
          inquiry: subjects.includes("inquiry"),
        };
      }
      const requiredSubjects = Array.isArray(selection.requiredSubjects)
        ? selection.requiredSubjects.filter(isSelectionSubject)
        : [];
      if (requiredSubjects.length > 0) {
        base.selectionRequiredSubjects = {
          korean: requiredSubjects.includes("korean"),
          math: requiredSubjects.includes("math"),
          english: requiredSubjects.includes("english"),
          inquiry: requiredSubjects.includes("inquiry"),
        };
      }
      const rankWeights = selection.rankWeights;
      if (Array.isArray(rankWeights)) {
        base.selectionRankWeights = [0, 1, 2, 3].map((index) => numToStr(rankWeights[index]));
      }
      if (Array.isArray(selection.groups)) {
        base.selectionGroupsJson = JSON.stringify(selection.groups, null, 2);
      }
    }
    if (Array.isArray(formula.subjectAdjustments)) {
      base.subjectAdjustmentsJson = JSON.stringify(formula.subjectAdjustments, null, 2);
    }
    if (Array.isArray(formula.finalAdjustments)) {
      base.finalAdjustmentsJson = JSON.stringify(formula.finalAdjustments, null, 2);
    }
    if (Array.isArray(formula.requiredInputs)) {
      base.requiredInputsJson = JSON.stringify(formula.requiredInputs, null, 2);
    }
    if (Array.isArray(formula.alternatives)) {
      base.formulaAlternativesJson = JSON.stringify(formula.alternatives, null, 2);
    }
    if (Array.isArray(formula.externalComponents)) {
      const externalComponents = externalComponentDraftsFromUnknown(formula.externalComponents);
      if (externalComponents.length > 0) {
        base.externalComponents = externalComponents;
        base.externalComponentsJson = JSON.stringify(externalComponentObjectsFromDrafts(externalComponents), null, 2);
      } else {
        base.externalComponentsJson = JSON.stringify(formula.externalComponents, null, 2);
      }
    }
  }

  const english =
    asObject(proposed.englishPolicyJson) ??
    asObject(proposed.english_policy_json) ??
    engineByGradePolicy(parsedFields.english_policy_json);
  if (english) {
    if (english.mode === "deduction" || english.mode === "addition" || english.mode === "ratio") {
      base.englishMode = english.mode;
    }
    base.englishWeight = numToStr(english.weight);
    base.englishScoreMax = numToStr(english.scoreMax) || "100";
    base.englishByGrade = byGradeToStrings(english.byGrade);
  }

  const history =
    asObject(proposed.historyPolicyJson) ??
    asObject(proposed.history_policy_json) ??
    engineByGradePolicy(parsedFields.history_policy_json);
  if (history) {
    if (history.mode === "deduction" || history.mode === "addition") {
      base.historyMode = history.mode;
    }
    base.historyByGrade = byGradeToStrings(history.byGrade);
  }

  const inquiry =
    asObject(proposed.inquiryPolicyJson) ??
    asObject(proposed.inquiry_policy_json) ??
    engineInquiry(parsedFields.inquiry_policy_json);
  if (inquiry) {
    if (inquiry.count === 1 || inquiry.count === 2) base.inquiryCount = String(inquiry.count) as "1" | "2";
    if (inquiry.mode === "average" || inquiry.mode === "best_one" || inquiry.mode === "sum") {
      base.inquiryMode = inquiry.mode;
    }
    if (asObject(inquiry.conversionTable)) {
      base.inquiryConversionTableJson = JSON.stringify(inquiry.conversionTable, null, 2);
    }
    base.inquiryConversionRisk = inquiry.conversionRisk === true;
  }

  const eligibility =
    asObject(proposed.eligibilityJson) ??
    asObject(proposed.eligibility_json) ??
    engineEligibility(parsedFields.eligibility_json);
  if (eligibility) base.eligibilityJson = JSON.stringify(eligibility, null, 2);

  return base;
}

function proposalFormula(proposed: Record<string, unknown>): Record<string, unknown> | null {
  const direct = asObject(proposed.formulaJson) ?? asObject(proposed.formula_json);
  if (direct) return direct;

  const formula: Record<string, unknown> = {};
  if (typeof proposed.totalScale === "number") formula.totalScale = proposed.totalScale;
  if (typeof proposed.total_scale === "number") formula.totalScale = proposed.total_scale;
  if (typeof proposed.csatWeight === "number") formula.csatWeight = proposed.csatWeight;
  if (typeof proposed.csat_weight === "number") formula.csatWeight = proposed.csat_weight;
  if (
    proposed.calculationMode === "weighted_average" ||
    proposed.calculationMode === "weighted_sum" ||
    proposed.calculationMode === "normalized_sum"
  ) {
    formula.calculationMode = proposed.calculationMode;
  } else if (
    proposed.calculation_mode === "weighted_average" ||
    proposed.calculation_mode === "weighted_sum" ||
    proposed.calculation_mode === "normalized_sum"
  ) {
    formula.calculationMode = proposed.calculation_mode;
  }
  const weights = asObject(proposed.weights);
  if (weights) formula.weights = weights;
  const scoreMaxes =
    asObject(proposed.scoreMaxes) ??
    asObject(proposed.score_maxes) ??
    asObject(proposed.subjectScoreMaxes) ??
    asObject(proposed.subject_score_maxes);
  if (scoreMaxes) formula.scoreMaxes = scoreMaxes;
  const subjectBaseScores = asObject(proposed.subjectBaseScores) ?? asObject(proposed.subject_base_scores);
  if (subjectBaseScores) formula.subjectBaseScores = subjectBaseScores;
  const subjectScoreTypes = asObject(proposed.subjectScoreTypes) ?? asObject(proposed.subject_score_types);
  if (subjectScoreTypes) formula.subjectScoreTypes = subjectScoreTypes;
  const selectionPolicy = asObject(proposed.selectionPolicy) ?? asObject(proposed.selection_policy);
  if (selectionPolicy) formula.selectionPolicy = selectionPolicy;
  if (Array.isArray(proposed.subjectAdjustments)) formula.subjectAdjustments = proposed.subjectAdjustments;
  else if (Array.isArray(proposed.subject_adjustments)) formula.subjectAdjustments = proposed.subject_adjustments;
  if (Array.isArray(proposed.finalAdjustments)) formula.finalAdjustments = proposed.finalAdjustments;
  else if (Array.isArray(proposed.final_adjustments)) formula.finalAdjustments = proposed.final_adjustments;
  if (Array.isArray(proposed.requiredInputs)) formula.requiredInputs = proposed.requiredInputs;
  else if (Array.isArray(proposed.required_inputs)) formula.requiredInputs = proposed.required_inputs;
  if (Array.isArray(proposed.alternatives)) {
    formula.alternatives = proposed.alternatives;
  } else if (Array.isArray(proposed.formulaAlternatives)) {
    formula.alternatives = proposed.formulaAlternatives;
  } else if (Array.isArray(proposed.formula_alternatives)) {
    formula.alternatives = proposed.formula_alternatives;
  }
  if (Array.isArray(proposed.externalComponents)) formula.externalComponents = proposed.externalComponents;
  else if (Array.isArray(proposed.external_components)) formula.externalComponents = proposed.external_components;

  return Object.keys(formula).length > 0 ? formula : null;
}

/** 편집기 값 → corrected_fields (엔진 형태). eligibility JSON이 깨지면 throw. */
export function ruleValueToCorrectedFields(value: RuleEditorValue): Record<string, unknown> {
  const formulaJson: Record<string, unknown> = {
    totalScale: toNumber(value.totalScale) ?? 0,
    weights: {
      korean: toNumber(value.weights.korean) ?? 0,
      math: toNumber(value.weights.math) ?? 0,
      inquiry: toNumber(value.weights.inquiry) ?? 0,
    },
  };
  if (value.calculationMode !== "weighted_average") {
    formulaJson.calculationMode = value.calculationMode;
  }
  const csatWeight = toNumber(value.csatWeight);
  if (csatWeight !== undefined) {
    formulaJson.csatWeight = csatWeight;
  }
  const selectionPolicy = selectionPolicyJson(value);
  if (selectionPolicy) formulaJson.selectionPolicy = selectionPolicy;
  const subjectScoreTypes = subjectScoreTypesJson(value);
  if (subjectScoreTypes) formulaJson.subjectScoreTypes = subjectScoreTypes;
  const scoreMaxes = scoreMaxesJson(value);
  if (scoreMaxes) formulaJson.scoreMaxes = scoreMaxes;
  const subjectBaseScores = subjectBaseScoresJson(value);
  if (subjectBaseScores) formulaJson.subjectBaseScores = subjectBaseScores;
  const subjectAdjustments = subjectAdjustmentsJson(value);
  if (subjectAdjustments) formulaJson.subjectAdjustments = subjectAdjustments;
  const finalAdjustments = finalAdjustmentsJson(value);
  if (finalAdjustments) formulaJson.finalAdjustments = finalAdjustments;
  const requiredInputs = requiredInputsJson(value);
  if (requiredInputs) formulaJson.requiredInputs = requiredInputs;
  const alternatives = formulaAlternativesJson(value);
  if (alternatives) formulaJson.alternatives = alternatives;
  const externalComponents =
    value.externalComponents.length > 0 ? externalComponentsFromDrafts(value) : externalComponentsJson(value);
  if (externalComponents) formulaJson.externalComponents = externalComponents;

  return {
    scoreType: value.scoreType,
    formulaJson,
    englishPolicyJson: englishPolicyJson(value),
    historyPolicyJson: historyPolicyJson(value),
    inquiryPolicyJson: inquiryPolicyJson(value),
    eligibilityJson: value.eligibilityJson.trim() === "" ? {} : JSON.parse(value.eligibilityJson),
  };
}

/** mapRule을 미러링해 "지금 값이면 exact가 풀리는가"를 클라이언트에서 즉시 판정. */
export function ruleValueUnlocksExact(value: RuleEditorValue): boolean {
  if (value.scoreType === "custom") return false;
  const totalScale = toNumber(value.totalScale);
  if (totalScale === undefined || totalScale <= 0) return false;
  for (const w of [value.weights.korean, value.weights.math, value.weights.inquiry]) {
    const n = toNumber(w);
    if (n === undefined || n < 0) return false;
  }
  if (!selectionPolicyValid(value)) return false;
  if (!csatWeightValid(value)) return false;
  if (!subjectScoreTypesValid(value)) return false;
  if (usesLegacyMixedInquiryApproximation(value)) return false;
  if (!scoreMaxesValid(value)) return false;
  if (!subjectBaseScoresValid(value)) return false;
  if (!subjectAdjustmentsValid(value)) return false;
  if (!finalAdjustmentsValid(value)) return false;
  if (!requiredInputsValid(value)) return false;
  if (requiredInputsJson(value)) return false;
  if (!formulaAlternativesValid(value)) return false;
  if (formulaAlternativesHaveRequiredInputs(value)) return false;
  if (!inquiryConversionTableValid(value)) return false;
  if (formulaAlternativesHaveExternalComponents(value)) return false;
  if (!externalComponentsValid(value)) return false;
  if (externalComponentsJson(value)) return false;
  if (!gradesCompleteNumeric(value.englishByGrade) || !gradesCompleteNumeric(value.historyByGrade)) return false;
  if (value.englishMode === "ratio") {
    const weight = toNumber(value.englishWeight);
    const scoreMax = toNumber(value.englishScoreMax);
    if (weight === undefined || weight <= 0 || scoreMax === undefined || scoreMax <= 0) return false;
  }
  if (value.selectionEnabled && selectionUsesEnglish(value) && value.englishMode !== "ratio") return false;
  if (value.eligibilityJson.trim() !== "") {
    try {
      JSON.parse(value.eligibilityJson);
    } catch {
      return false;
    }
  }
  return true;
}

/** exact는 아니어도 공식 반영구조로 서비스의 근사/저신뢰 상대비교를 열 수 있는가. */
export function ruleValueEnablesAnalysis(value: RuleEditorValue): boolean {
  if (ruleValueUnlocksExact(value)) return true;
  if (value.scoreType === "custom") return false;
  const totalScale = toNumber(value.totalScale);
  if (totalScale === undefined || totalScale <= 0) return false;
  for (const w of [value.weights.korean, value.weights.math, value.weights.inquiry]) {
    const n = toNumber(w);
    if (n === undefined || n < 0) return false;
  }
  if (!selectionPolicyValid(value)) return false;
  if (!csatWeightValid(value)) return false;
  if (!subjectScoreTypesValid(value)) return false;
  if (!scoreMaxesValid(value)) return false;
  if (!subjectBaseScoresValid(value)) return false;
  if (!subjectAdjustmentsValid(value)) return false;
  if (!finalAdjustmentsValid(value)) return false;
  if (!requiredInputsValid(value)) return false;
  if (!formulaAlternativesValid(value)) return false;
  if (!inquiryConversionTableValid(value)) return false;
  if (!externalComponentsValid(value)) return false;
  if (!gradesCompleteNumeric(value.englishByGrade) || !gradesCompleteNumeric(value.historyByGrade)) return false;
  if (value.englishMode === "ratio") {
    const weight = toNumber(value.englishWeight);
    const scoreMax = toNumber(value.englishScoreMax);
    if (weight === undefined || weight <= 0 || scoreMax === undefined || scoreMax <= 0) return false;
  }
  if (value.selectionEnabled && selectionUsesEnglish(value) && value.englishMode !== "ratio") return false;
  if (value.eligibilityJson.trim() !== "") {
    try {
      JSON.parse(value.eligibilityJson);
    } catch {
      return false;
    }
  }
  return (
    ruleValueHasCsatComparisonPath(value) &&
    (ruleValueHasExternalComponents(value) || ruleValueHasRequiredInputs(value) || usesLegacyMixedInquiryApproximation(value))
  );
}

export function ruleValueHasExternalComponents(value: RuleEditorValue): boolean {
  const components =
    value.externalComponents.length > 0 ? externalComponentsFromDrafts(value) : externalComponentsJson(value);
  return components !== null || formulaAlternativesHaveExternalComponents(value);
}

export function ruleValueHasRequiredInputs(value: RuleEditorValue): boolean {
  return requiredInputsJson(value) !== null || formulaAlternativesHaveRequiredInputs(value);
}

function ruleValueHasCsatComparisonPath(value: RuleEditorValue): boolean {
  if (value.selectionEnabled) return true;
  const weightSum =
    (toNumber(value.weights.korean) ?? 0) +
    (toNumber(value.weights.math) ?? 0) +
    (toNumber(value.weights.inquiry) ?? 0) +
    (value.englishMode === "ratio" ? (toNumber(value.englishWeight) ?? 0) : 0);
  if (weightSum > 0) return true;
  const alternatives = formulaAlternativesJson(value);
  return alternatives?.some((alternative) => {
    const weights = asObject(alternative.weights);
    if (!weights) return false;
    return (
      numberFromUnknown(weights.korean) > 0 ||
      numberFromUnknown(weights.math) > 0 ||
      numberFromUnknown(weights.inquiry) > 0 ||
      asObject(alternative.selectionPolicy) !== null
    );
  }) ?? false;
}

/* ── 컴포넌트 ── */

export function RuleFieldEditor({
  value,
  onChange,
  unlocksExact,
}: {
  value: RuleEditorValue;
  onChange: (value: RuleEditorValue) => void;
  unlocksExact: boolean;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const set = (patch: Partial<RuleEditorValue>) => onChange({ ...value, ...patch });
  const hasExternalComponents = ruleValueHasExternalComponents(value);
  const hasRequiredInputs = requiredInputsJson(value) !== null;
  const hasLegacyMixedInquiryApproximation = usesLegacyMixedInquiryApproximation(value);
  const enablesAnalysis = ruleValueEnablesAnalysis(value);
  const relativeComparison = !unlocksExact && enablesAnalysis;
  const updateExternalComponents = (externalComponents: ExternalComponentDraft[]) => {
    const asJson = externalComponentObjectsFromDrafts(externalComponents);
    set({
      externalComponents,
      externalComponentsJson: asJson ? JSON.stringify(asJson, null, 2) : "",
    });
  };
  const addExternalComponent = () => {
    updateExternalComponents([
      ...value.externalComponents,
      { kind: "practical", weight: "", label: "실기", required: true },
    ]);
  };
  const applySelectionTemplate = (template: SelectionTemplate) => {
    const requiredSubjects = { ...EMPTY_REQUIRED_SUBJECTS };
    for (const subject of template.required ?? []) requiredSubjects[subject] = true;
    set({
      selectionEnabled: true,
      selectionCount: template.count,
      selectionSubjects: { ...ALL_SELECTION_SUBJECTS },
      selectionRequiredSubjects: requiredSubjects,
      selectionRankWeights: [0, 1, 2, 3].map((index) => template.rankWeights?.[index] ?? ""),
      selectionGroupsJson: template.groups ? JSON.stringify(template.groups, null, 2) : "",
    });
  };

  return (
    <div className="mt-4 space-y-4">
      <div
        className={`rounded-lg border p-3 ${
          unlocksExact
            ? "border-emerald-300 bg-emerald-50"
            : relativeComparison
              ? "border-amber-300 bg-amber-50"
              : "border-rose-200 bg-rose-50"
        }`}
      >
        <p className="text-xs font-semibold text-slate-700">정확 환산(exact) 가능 여부</p>
        <p
          className={`mt-0.5 text-sm font-bold ${
            unlocksExact ? "text-emerald-700" : relativeComparison ? "text-amber-700" : "text-rose-700"
          }`}
        >
          {unlocksExact
            ? "✓ 풀림 — 저장하면 정확 환산이 켜집니다"
            : relativeComparison
              ? "△ 근사 비교 가능 — exact는 닫고 낮은 신뢰도로 반영됩니다"
            : hasExternalComponents
              ? "✕ 비수능 구성요소 포함 — 현재 제품 입력만으로 전체 exact 환산 불가"
              : hasRequiredInputs
                ? "✕ 공식 입력값 대기 — 수능 이후 확정 상수가 필요합니다"
              : hasLegacyMixedInquiryApproximation
                ? "✕ 아직 — mixed 탐구는 변환표 또는 과목별 점수 기준을 명시하세요"
              : "✕ 아직 — 총점·가중치·영어/한국사 1~9등급을 채우세요"}
        </p>
      </div>

      <Field label="환산 방식 (scoreType)">
        <select
          value={value.scoreType}
          onChange={(e) => set({ scoreType: e.target.value as ScoreType })}
          className="w-full rounded border border-slate-300 px-2 py-2 text-sm"
        >
          <option value="standard">표준점수 (standard)</option>
          <option value="percentile">백분위 (percentile)</option>
          <option value="mixed">혼합 (mixed)</option>
          <option value="custom">대학 자체식 (custom)</option>
        </select>
      </Field>

      <Field label="환산 총점 (totalScale)" hint="예: 1000, 700">
        <NumberInput value={value.totalScale} onChange={(totalScale) => set({ totalScale })} placeholder="총점" />
      </Field>

      <Field label="산식 결합 방식" hint="가중평균 / 직접합 / 기본점수+실질반영점수">
        <Segmented
          options={[
            { value: "weighted_average", label: "가중평균" },
            { value: "weighted_sum", label: "직접합" },
            { value: "normalized_sum", label: "기본+실질" },
          ]}
          value={value.calculationMode}
          onChange={(v) => set({ calculationMode: v as CalculationMode })}
        />
      </Field>

      <Field label="영역 반영 비율 (가중치)" hint="국어·수학·탐구 (퍼센트 또는 비율)">
        <div className="grid grid-cols-3 gap-2">
          <NumberInput
            label="국어"
            value={value.weights.korean}
            onChange={(korean) => set({ weights: { ...value.weights, korean } })}
          />
          <NumberInput
            label="수학"
            value={value.weights.math}
            onChange={(math) => set({ weights: { ...value.weights, math } })}
          />
          <NumberInput
            label="탐구"
            value={value.weights.inquiry}
            onChange={(inquiry) => set({ weights: { ...value.weights, inquiry } })}
          />
        </div>
      </Field>

      <Field label="우수영역 선택식" hint="예: 우수 4영역 순 40/30/20/10">
        <label className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-600">
          <input
            type="checkbox"
            checked={value.selectionEnabled}
            onChange={(e) => set({ selectionEnabled: e.target.checked })}
          />
          우수영역 선택식 사용
        </label>
        {value.selectionEnabled ? (
          <div className="space-y-2 rounded border border-slate-200 p-2">
            <div className="grid grid-cols-2 gap-1">
              {SELECTION_TEMPLATES.map((template) => (
                <button
                  key={template.label}
                  type="button"
                  onClick={() => applySelectionTemplate(template)}
                  className="rounded border border-slate-300 bg-white px-2 py-1.5 text-left text-[11px] font-semibold text-slate-600 hover:border-cyan-400 hover:text-cyan-700"
                >
                  {template.label}
                </button>
              ))}
            </div>
            <Segmented
              options={[
                { value: "1", label: "1영역" },
                { value: "2", label: "2영역" },
                { value: "3", label: "3영역" },
                { value: "4", label: "4영역" },
              ]}
              value={value.selectionCount}
              onChange={(selectionCount) => set({ selectionCount: selectionCount as SelectionCount })}
            />
            <div className="flex flex-wrap gap-2">
              {SELECTION_SUBJECTS.map((subject) => (
                <label key={subject.value} className="flex items-center gap-1 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={value.selectionSubjects[subject.value]}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      set({
                        selectionSubjects: {
                          ...value.selectionSubjects,
                          [subject.value]: checked,
                        },
                        selectionRequiredSubjects: checked
                          ? value.selectionRequiredSubjects
                          : { ...value.selectionRequiredSubjects, [subject.value]: false },
                      });
                    }}
                  />
                  {subject.label}
                </label>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-2">
              <span className="text-xs font-semibold text-slate-500">필수 포함</span>
              {SELECTION_SUBJECTS.map((subject) => (
                <label key={subject.value} className="flex items-center gap-1 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={value.selectionRequiredSubjects[subject.value]}
                    disabled={!value.selectionSubjects[subject.value]}
                    onChange={(e) =>
                      set({
                        selectionRequiredSubjects: {
                          ...value.selectionRequiredSubjects,
                          [subject.value]: e.target.checked,
                        },
                      })
                    }
                  />
                  {subject.label}
                </label>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-2">
              {[0, 1, 2, 3].map((index) => (
                <NumberInput
                  key={index}
                  label={`${index + 1}순위`}
                  value={value.selectionRankWeights[index] ?? ""}
                  onChange={(rankWeight) => {
                    const selectionRankWeights = [...value.selectionRankWeights];
                    selectionRankWeights[index] = rankWeight;
                    set({ selectionRankWeights });
                  }}
                  placeholder={index < Number(value.selectionCount) ? "반영비" : ""}
                />
              ))}
            </div>
            <textarea
              value={value.selectionGroupsJson}
              onChange={(e) => set({ selectionGroupsJson: e.target.value })}
              spellCheck={false}
              placeholder='[{"count":2,"subjects":["korean","math"],"requiredSubjects":["math"],"rankWeights":[40,30]}]'
              className="h-20 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </div>
        ) : null}
      </Field>

      <Field label="탐구 반영">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented
            options={[
              { value: "1", label: "1과목" },
              { value: "2", label: "2과목" },
            ]}
            value={value.inquiryCount}
            onChange={(v) => set({ inquiryCount: v as "1" | "2" })}
          />
          <Segmented
            options={[
              { value: "average", label: "평균" },
              { value: "best_one", label: "우수 1과목" },
              { value: "sum", label: "합산" },
            ]}
            value={value.inquiryMode}
            onChange={(v) => set({ inquiryMode: v as InquiryMode })}
          />
          <label className="flex items-center gap-1 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={value.inquiryConversionRisk}
              onChange={(e) => set({ inquiryConversionRisk: e.target.checked })}
            />
            변환표준 위험
          </label>
        </div>
        <textarea
          value={value.inquiryConversionTableJson}
          onChange={(e) => set({ inquiryConversionTableJson: e.target.value })}
          spellCheck={false}
          placeholder='{"from":"percentile","scoreMax":200,"byPercentile":{"100":200,"99":198,"98":196}}'
          className="mt-2 h-24 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
        />
      </Field>

      <Field label="영어 반영" hint="감점/가산/비율 + 등급별 점수">
        <Segmented
          options={[
            { value: "deduction", label: "감점" },
            { value: "addition", label: "가산" },
            { value: "ratio", label: "비율" },
          ]}
          value={value.englishMode}
          onChange={(v) => set({ englishMode: v as EnglishMode })}
        />
        {value.englishMode === "ratio" ? (
          <div className="mt-2 grid grid-cols-2 gap-2">
            <NumberInput
              label="영어 반영비"
              value={value.englishWeight}
              onChange={(englishWeight) => set({ englishWeight })}
            />
            <NumberInput
              label="영어 만점"
              value={value.englishScoreMax}
              onChange={(englishScoreMax) => set({ englishScoreMax })}
            />
          </div>
        ) : null}
        <GradeRow
          value={value.englishByGrade}
          onChange={(englishByGrade) => set({ englishByGrade })}
        />
      </Field>

      <button
        type="button"
        onClick={() => setShowAdvanced((s) => !s)}
        className="text-xs font-semibold text-cyan-700"
      >
        {showAdvanced ? "▾ 고급 항목 숨기기" : "▸ 고급 항목 (한국사·지원자격·가산)"}
      </button>

      {showAdvanced ? (
        <div className="space-y-4 border-t border-slate-200 pt-4">
          <Field label="한국사 등급별 점수" hint="감점/가산 + 등급별 점수. 빈 칸은 무시">
            <Segmented
              options={[
                { value: "deduction", label: "감점" },
                { value: "addition", label: "가산" },
              ]}
              value={value.historyMode}
              onChange={(v) => set({ historyMode: v as HistoryMode })}
            />
            <GradeRow value={value.historyByGrade} onChange={(historyByGrade) => set({ historyByGrade })} />
          </Field>
          <Field label="지원 자격 (eligibilityJson)" hint="없으면 비워두세요">
            <textarea
              value={value.eligibilityJson}
              onChange={(e) => set({ eligibilityJson: e.target.value })}
              spellCheck={false}
              placeholder='예: {"requiredInquiryCategory":"science"}'
              className="h-24 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </Field>
          <Field label="과목별 점수 기준 (formulaJson.subjectScoreTypes)" hint="mixed에서 탐구 백분위/표준점수 기준을 명시">
            <textarea
              value={value.subjectScoreTypesJson}
              onChange={(e) => set({ subjectScoreTypesJson: e.target.value })}
              spellCheck={false}
              placeholder='{"korean":"standardScore","math":"standardScore","inquiry":"percentile"}'
              className="h-20 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </Field>
          <Field label="과목별 만점 (formulaJson.scoreMaxes)" hint="공식·시험 기준 최고점이 확정됐을 때만">
            <textarea
              value={value.scoreMaxesJson}
              onChange={(e) => set({ scoreMaxesJson: e.target.value })}
              spellCheck={false}
              placeholder='{"korean":147,"math":139,"inquiry":70.12}'
              className="h-20 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </Field>
          <Field label="과목별 기본점수 (formulaJson.subjectBaseScores)" hint="기본점수+실질반영점수 산식에서 사용">
            <textarea
              value={value.subjectBaseScoresJson}
              onChange={(e) => set({ subjectBaseScoresJson: e.target.value })}
              spellCheck={false}
              placeholder='{"korean":40,"math":30,"inquiry":30}'
              className="h-20 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </Field>
          <Field label="과목 가산 정책 (subjectAdjustments)" hint="예: 수학 미적/기하 5%, 과탐 2과목 10%">
            <textarea
              value={value.subjectAdjustmentsJson}
              onChange={(e) => set({ subjectAdjustmentsJson: e.target.value })}
              spellCheck={false}
              placeholder='[{"subject":"math","requiredSelections":["미적분","기하"],"multiplier":1.05},{"subject":"inquiry","requiredInquiryCategory":"science","requiredInquiryCategoryCount":2,"multiplier":1.1}]'
              className="h-24 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </Field>
          <Field label="최종점 가산 정책 (finalAdjustments)" hint="예: 탐구 백분위 3%, 수학 표준점수 7%">
            <textarea
              value={value.finalAdjustmentsJson}
              onChange={(e) => set({ finalAdjustmentsJson: e.target.value })}
              spellCheck={false}
              placeholder='[{"subject":"inquiry","requiredInquiryCategory":"social","pointsFrom":"percentile","multiplier":0.03},{"subject":"math","requiredSelections":["미적분","기하"],"pointsFrom":"standardScore","multiplier":0.07}]'
              className="h-24 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </Field>
          <Field label="추가 공식 입력값 (formulaJson.requiredInputs)" hint="수능 이후 확정되는 전국최고표준점수 등">
            <textarea
              value={value.requiredInputsJson}
              onChange={(e) => set({ requiredInputsJson: e.target.value })}
              spellCheck={false}
              placeholder='[{"kind":"national_max_standard_score","subjects":["korean","math","inquiry"],"label":"영역별 전국 최고 표준점수","availability":"post_csat"}]'
              className="h-24 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </Field>
          <Field label="대체 산식 (formulaJson.alternatives)" hint="예: A/B 유형 중 높은 점수">
            <textarea
              value={value.formulaAlternativesJson}
              onChange={(e) => set({ formulaAlternativesJson: e.target.value })}
              spellCheck={false}
              placeholder='[{"weights":{"korean":40,"math":30,"inquiry":20}},{"weights":{"korean":30,"math":40,"inquiry":20}}]'
              className="h-28 w-full resize-y rounded border border-slate-300 px-2 py-2 font-mono text-xs leading-5"
            />
          </Field>
          <Field label="수능 구성요소 비율 (formulaJson.csatWeight)" hint="수능+실기/학생부 혼합 전형에서만">
            <NumberInput
              value={value.csatWeight}
              onChange={(csatWeight) => set({ csatWeight })}
              placeholder="예: 30"
            />
          </Field>
          <Field label="비수능 구성요소 (externalComponents)" hint="실기·학생부·면접 등 수능 외 반영비">
            <div className="space-y-2 rounded border border-slate-200 p-2">
              {value.externalComponents.length === 0 ? (
                <p className="text-xs text-slate-400">수능 외 구성요소가 없으면 비워두세요.</p>
              ) : null}
              {value.externalComponents.map((component, index) => (
                <div key={index} className="grid grid-cols-[1fr_88px_1.4fr_auto] gap-2">
                  <select
                    value={component.kind}
                    onChange={(e) => {
                      const kind = e.target.value as ExternalComponentKind;
                      updateExternalComponents(
                        value.externalComponents.map((item, itemIndex) =>
                          itemIndex === index
                            ? {
                                ...item,
                                kind,
                                label:
                                  item.label.trim() === "" ||
                                  item.label === externalComponentDefaultLabel(item.kind)
                                    ? externalComponentDefaultLabel(kind)
                                    : item.label,
                              }
                            : item,
                        ),
                      );
                    }}
                    className="rounded border border-slate-300 px-2 py-1.5 text-xs"
                  >
                    {EXTERNAL_COMPONENT_KINDS.map((kind) => (
                      <option key={kind.value} value={kind.value}>
                        {kind.label}
                      </option>
                    ))}
                  </select>
                  <NumberInput
                    value={component.weight}
                    onChange={(weight) =>
                      updateExternalComponents(
                        value.externalComponents.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, weight } : item,
                        ),
                      )
                    }
                    placeholder="반영비"
                  />
                  <input
                    value={component.label}
                    onChange={(e) =>
                      updateExternalComponents(
                        value.externalComponents.map((item, itemIndex) =>
                          itemIndex === index ? { ...item, label: e.target.value } : item,
                        ),
                      )
                    }
                    placeholder="원문 표기"
                    className="rounded border border-slate-300 px-2 py-1.5 text-xs"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      updateExternalComponents(value.externalComponents.filter((_, itemIndex) => itemIndex !== index))
                    }
                    className="rounded border border-slate-300 px-2 py-1.5 text-xs font-semibold text-slate-500 hover:border-rose-300 hover:text-rose-700"
                  >
                    삭제
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addExternalComponent}
                className="rounded border border-cyan-300 px-2 py-1.5 text-xs font-semibold text-cyan-700 hover:bg-cyan-50"
              >
                구성요소 추가
              </button>
              {value.externalComponents.length > 0 && !externalComponentsValid(value) ? (
                <p className="text-xs font-semibold text-rose-600">비수능 구성요소의 반영비를 숫자로 채우세요.</p>
              ) : null}
            </div>
          </Field>
        </div>
      ) : null}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-xs font-semibold text-slate-700">{label}</span>
        {hint ? <span className="text-[11px] text-slate-400">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

function NumberInput({
  value,
  onChange,
  label,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  label?: string;
  placeholder?: string;
}) {
  return (
    <label className="block">
      {label ? <span className="mb-0.5 block text-center text-[11px] text-slate-500">{label}</span> : null}
      <input
        type="number"
        inputMode="decimal"
        value={value}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border border-slate-300 px-2 py-2 text-sm"
      />
    </label>
  );
}

function Segmented({
  options,
  value,
  onChange,
}: {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="inline-flex overflow-hidden rounded border border-slate-300">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          className={`px-3 py-1.5 text-xs font-semibold ${
            value === option.value ? "bg-cyan-500 text-white" : "bg-white text-slate-600"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function GradeRow({
  value,
  onChange,
}: {
  value: Record<string, string>;
  onChange: (value: Record<string, string>) => void;
}) {
  return (
    <div className="mt-2 grid grid-cols-9 gap-1">
      {GRADES.map((grade) => (
        <label key={grade} className="block">
          <span className="block text-center text-[10px] text-slate-400">{grade}등</span>
          <input
            value={value[grade] ?? ""}
            onChange={(e) => onChange({ ...value, [grade]: e.target.value })}
            inputMode="decimal"
            className="w-full rounded border border-slate-300 px-1 py-1 text-center text-[11px]"
          />
        </label>
      ))}
    </div>
  );
}

/* ── helpers ── */

function pickScoreType(value: unknown): ScoreType | null {
  return value === "standard" || value === "percentile" || value === "mixed" || value === "custom" ? value : null;
}

function asObject(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

/** 파싱된 formula_json이 엔진 형태({totalScale,weights})일 때만 채택 (foundation 초안 노이즈는 버림). */
function engineFormula(value: unknown): Record<string, unknown> | null {
  const obj = asObject(value);
  if (!obj) return null;
  return typeof obj.totalScale === "number" && asObject(obj.weights) ? obj : null;
}

function engineByGradePolicy(value: unknown): Record<string, unknown> | null {
  const obj = asObject(value);
  if (!obj) return null;
  return asObject(obj.byGrade) ||
    obj.mode === "deduction" ||
    obj.mode === "addition" ||
    obj.mode === "ratio"
    ? obj
    : null;
}

function engineInquiry(value: unknown): Record<string, unknown> | null {
  const obj = asObject(value);
  if (!obj) return null;
  return obj.count === 1 || obj.count === 2 ? obj : null;
}

function engineEligibility(value: unknown): Record<string, unknown> | null {
  const obj = asObject(value);
  if (!obj) return null;
  return "requiredMathSelections" in obj || "requiredInquiryCategory" in obj || "maxHistoryGrade" in obj ? obj : null;
}

function byGradeToStrings(value: unknown): Record<string, string> {
  const obj = asObject(value);
  if (!obj) return {};
  const output: Record<string, string> = {};
  for (const [grade, score] of Object.entries(obj)) {
    if (/^\d$/.test(grade) && typeof score === "number") output[grade] = String(score);
  }
  return output;
}

function numericByGrade(value: Record<string, string>): Record<string, number> {
  const output: Record<string, number> = {};
  for (const [grade, raw] of Object.entries(value)) {
    const n = toNumber(raw);
    if (n !== undefined) output[grade] = n;
  }
  return output;
}

function englishPolicyJson(value: RuleEditorValue): Record<string, unknown> {
  const policy: Record<string, unknown> = {
    mode: value.englishMode,
    byGrade: numericByGrade(value.englishByGrade),
  };
  if (value.englishMode === "ratio") {
    policy.weight = toNumber(value.englishWeight) ?? 0;
    policy.scoreMax = toNumber(value.englishScoreMax) ?? 100;
  }
  return policy;
}

function historyPolicyJson(value: RuleEditorValue): Record<string, unknown> {
  return {
    mode: value.historyMode,
    byGrade: numericByGrade(value.historyByGrade),
  };
}

function inquiryPolicyJson(value: RuleEditorValue): Record<string, unknown> {
  const policy: Record<string, unknown> = {
    count: Number(value.inquiryCount),
    mode: value.inquiryMode,
    conversionRisk: value.inquiryConversionRisk,
  };
  const conversionTable = inquiryConversionTableJson(value);
  if (conversionTable) policy.conversionTable = conversionTable;
  return policy;
}

function inquiryConversionTableJson(value: RuleEditorValue): Record<string, unknown> | null {
  const raw = value.inquiryConversionTableJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return inquiryConversionTableRecordValid(parsed) ? parsed : null;
}

function inquiryConversionTableValid(value: RuleEditorValue): boolean {
  const raw = value.inquiryConversionTableJson.trim();
  return raw === "" || inquiryConversionTableJson(value) !== null;
}

function inquiryConversionTableRecordValid(value: unknown): value is Record<string, unknown> {
  const table = asObject(value);
  if (!table || table.from !== "percentile") return false;
  if (table.scoreMax !== undefined && !isPositiveNumber(table.scoreMax)) return false;
  const byPercentile = asObject(table.byPercentile);
  if (!byPercentile || Object.keys(byPercentile).length === 0) return false;
  if (Object.keys(byPercentile).length > 101) return false;
  return Object.entries(byPercentile).every(([key, score]) => {
    const percentile = Number(key);
    return (
      Number.isInteger(percentile) &&
      percentile >= 0 &&
      percentile <= 100 &&
      typeof score === "number" &&
      Number.isFinite(score)
    );
  });
}

function selectionPolicyJson(value: RuleEditorValue): Record<string, unknown> | null {
  if (!value.selectionEnabled) return null;
  const count = Number(value.selectionCount);
  const subjects = selectedSubjects(value);
  const policy: Record<string, unknown> = {
    mode: "best_n_subjects",
    count,
    subjects,
  };
  const requiredSubjects = selectedRequiredSubjects(value);
  if (requiredSubjects.length > 0) policy.requiredSubjects = requiredSubjects;
  const weights = value.selectionRankWeights.slice(0, count);
  if (weights.some((weight) => weight.trim() !== "")) {
    policy.rankWeights = weights.map((weight) => toNumber(weight) ?? 0);
  }
  const groups = selectionGroups(value);
  if (groups) policy.groups = groups;
  return policy;
}

function selectionPolicyValid(value: RuleEditorValue): boolean {
  if (!value.selectionEnabled) return true;
  const count = Number(value.selectionCount);
  const subjects = selectedSubjects(value);
  const requiredSubjects = selectedRequiredSubjects(value);
  if (![1, 2, 3, 4].includes(count)) return false;
  if (subjects.length < count) return false;
  if (requiredSubjects.length > count) return false;
  if (requiredSubjects.some((subject) => !subjects.includes(subject))) return false;

  const weights = value.selectionRankWeights.slice(0, count);
  const hasWeights = weights.some((weight) => weight.trim() !== "");
  if (hasWeights) {
    for (const weight of weights) {
      const numeric = toNumber(weight);
      if (numeric === undefined || numeric <= 0) return false;
    }
  }
  if (value.selectionGroupsJson.trim() !== "" && !selectionGroups(value)) return false;
  return true;
}

function csatWeightValid(value: RuleEditorValue): boolean {
  const raw = value.csatWeight.trim();
  if (raw === "") return true;
  const numeric = toNumber(raw);
  return numeric !== undefined && numeric >= 0;
}

function subjectScoreTypesJson(value: RuleEditorValue): Record<string, unknown> | null {
  const raw = value.subjectScoreTypesJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return subjectScoreTypesRecordValid(parsed) ? parsed : null;
}

function subjectScoreTypesValid(value: RuleEditorValue): boolean {
  const raw = value.subjectScoreTypesJson.trim();
  return raw === "" || subjectScoreTypesJson(value) !== null;
}

function subjectScoreTypesRecordValid(value: unknown): value is Record<string, unknown> {
  const obj = asObject(value);
  if (!obj) return false;
  const entries = Object.entries(obj);
  if (entries.length === 0) return false;
  return entries.every(
    ([key, metric]) =>
      (key === "korean" || key === "math" || key === "inquiry") &&
      (metric === "standardScore" || metric === "percentile"),
  );
}

function usesLegacyMixedInquiryApproximation(value: RuleEditorValue): boolean {
  if (value.scoreType !== "mixed") return false;
  if (!ruleUsesInquiry(value)) return false;
  const conversionTable = inquiryConversionTableJson(value);
  if (conversionTable) return false;
  const subjectScoreTypes = subjectScoreTypesJson(value);
  return subjectScoreTypes?.inquiry !== "standardScore" && subjectScoreTypes?.inquiry !== "percentile";
}

function scoreMaxesJson(value: RuleEditorValue): Record<string, unknown> | null {
  const raw = value.scoreMaxesJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return scoreMaxesRecordValid(parsed) ? parsed : null;
}

function scoreMaxesValid(value: RuleEditorValue): boolean {
  const raw = value.scoreMaxesJson.trim();
  return raw === "" || scoreMaxesJson(value) !== null;
}

function scoreMaxesRecordValid(value: unknown): value is Record<string, unknown> {
  const obj = asObject(value);
  if (!obj) return false;
  const entries = Object.entries(obj);
  if (entries.length === 0) return false;
  return entries.every(([key, scoreMax]) =>
    (key === "korean" || key === "math" || key === "inquiry") &&
    isPositiveNumber(scoreMax),
  );
}

function subjectBaseScoresJson(value: RuleEditorValue): Record<string, unknown> | null {
  const raw = value.subjectBaseScoresJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return subjectBaseScoresRecordValid(parsed) ? parsed : null;
}

function subjectBaseScoresValid(value: RuleEditorValue): boolean {
  const raw = value.subjectBaseScoresJson.trim();
  if (raw !== "" && value.calculationMode !== "normalized_sum") return false;
  return raw === "" || subjectBaseScoresJson(value) !== null;
}

function subjectBaseScoresRecordValid(value: unknown): value is Record<string, unknown> {
  const obj = asObject(value);
  if (!obj) return false;
  const entries = Object.entries(obj);
  if (entries.length === 0) return false;
  return entries.every(([key, score]) =>
    (key === "korean" || key === "math" || key === "inquiry") &&
    nonNegativeNumber(score),
  );
}

function subjectAdjustmentsJson(value: RuleEditorValue): Record<string, unknown>[] | null {
  const raw = value.subjectAdjustmentsJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return subjectAdjustmentsValidArray(parsed) ? parsed : null;
}

function subjectAdjustmentsValid(value: RuleEditorValue): boolean {
  const raw = value.subjectAdjustmentsJson.trim();
  return raw === "" || subjectAdjustmentsJson(value) !== null;
}

function subjectAdjustmentsValidArray(value: unknown): value is Record<string, unknown>[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > 8) return false;
  return value.every((item) => {
    const adjustment = asObject(item);
    if (!adjustment) return false;
    if (adjustment.subject !== "korean" && adjustment.subject !== "math" && adjustment.subject !== "inquiry") {
      return false;
    }
    if (adjustment.multiplier === undefined && adjustment.points === undefined) return false;
    if (adjustment.multiplier !== undefined && !isPositiveNumber(adjustment.multiplier)) return false;
    if (adjustment.points !== undefined && typeof adjustment.points !== "number") return false;
    if (
      adjustment.requiredInquiryCategory !== undefined &&
      adjustment.requiredInquiryCategory !== "science" &&
      adjustment.requiredInquiryCategory !== "social"
    ) {
      return false;
    }
    if (
      adjustment.requiredInquiryCategoryCount !== undefined &&
      adjustment.requiredInquiryCategoryCount !== 1 &&
      adjustment.requiredInquiryCategoryCount !== 2
    ) {
      return false;
    }
    if (adjustment.requiredInquiryCategoryCount !== undefined && adjustment.requiredInquiryCategory === undefined) {
      return false;
    }
    if (
      adjustment.requiredSelections !== undefined &&
      (!Array.isArray(adjustment.requiredSelections) ||
        !adjustment.requiredSelections.every(
          (selection) => typeof selection === "string" && selection.trim() !== "",
        ))
    ) {
      return false;
    }
    return adjustment.capAtMax === undefined || typeof adjustment.capAtMax === "boolean";
  });
}

function finalAdjustmentsJson(value: RuleEditorValue): Record<string, unknown>[] | null {
  const raw = value.finalAdjustmentsJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return finalAdjustmentsValidArray(parsed) ? parsed : null;
}

function finalAdjustmentsValid(value: RuleEditorValue): boolean {
  const raw = value.finalAdjustmentsJson.trim();
  return raw === "" || finalAdjustmentsJson(value) !== null;
}

function finalAdjustmentsValidArray(value: unknown): value is Record<string, unknown>[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > 8) return false;
  return value.every((item) => {
    const adjustment = asObject(item);
    if (!adjustment) return false;
    if (adjustment.subject !== "korean" && adjustment.subject !== "math" && adjustment.subject !== "inquiry") {
      return false;
    }
    if (adjustment.pointsFrom !== "standardScore" && adjustment.pointsFrom !== "percentile") return false;
    if (!isPositiveNumber(adjustment.multiplier)) return false;
    if (adjustment.maxPoints !== undefined && !isPositiveNumber(adjustment.maxPoints)) return false;
    if (
      adjustment.requiredInquiryCategory !== undefined &&
      adjustment.requiredInquiryCategory !== "science" &&
      adjustment.requiredInquiryCategory !== "social"
    ) {
      return false;
    }
    if (
      adjustment.requiredInquiryCategoryCount !== undefined &&
      adjustment.requiredInquiryCategoryCount !== 1 &&
      adjustment.requiredInquiryCategoryCount !== 2
    ) {
      return false;
    }
    if (adjustment.requiredInquiryCategoryCount !== undefined && adjustment.requiredInquiryCategory === undefined) {
      return false;
    }
    if (
      adjustment.requiredSelections !== undefined &&
      (!Array.isArray(adjustment.requiredSelections) ||
        !adjustment.requiredSelections.every(
          (selection) => typeof selection === "string" && selection.trim() !== "",
        ))
    ) {
      return false;
    }
    return true;
  });
}

function requiredInputsJson(value: RuleEditorValue): Record<string, unknown>[] | null {
  const raw = value.requiredInputsJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return requiredInputsValidArray(parsed) ? parsed : null;
}

function requiredInputsValid(value: RuleEditorValue): boolean {
  const raw = value.requiredInputsJson.trim();
  return raw === "" || requiredInputsJson(value) !== null;
}

function requiredInputsValidArray(value: unknown): value is Record<string, unknown>[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > 8) return false;
  return value.every((item) => {
    const requiredInput = asObject(item);
    if (!requiredInput) return false;
    if (
      requiredInput.kind !== "national_max_standard_score" &&
      requiredInput.kind !== "conversion_table" &&
      requiredInput.kind !== "other"
    ) {
      return false;
    }
    if (
      requiredInput.subjects !== undefined &&
      (!Array.isArray(requiredInput.subjects) ||
        requiredInput.subjects.length === 0 ||
        requiredInput.subjects.length > 3 ||
        !requiredInput.subjects.every(
          (subject) => subject === "korean" || subject === "math" || subject === "inquiry",
        ))
    ) {
      return false;
    }
    if (requiredInput.label !== undefined && (typeof requiredInput.label !== "string" || requiredInput.label.trim() === "")) {
      return false;
    }
    return (
      requiredInput.availability === undefined ||
      requiredInput.availability === "post_csat" ||
      requiredInput.availability === "manual" ||
      requiredInput.availability === "unavailable"
    );
  });
}

function formulaAlternativesJson(value: RuleEditorValue): Record<string, unknown>[] | null {
  const raw = value.formulaAlternativesJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return formulaAlternativesValidArray(parsed, value.calculationMode) ? parsed : null;
}

function formulaAlternativesValid(value: RuleEditorValue): boolean {
  const raw = value.formulaAlternativesJson.trim();
  return raw === "" || formulaAlternativesJson(value) !== null;
}

function formulaAlternativesHaveExternalComponents(value: RuleEditorValue): boolean {
  return (formulaAlternativesJson(value) ?? []).some((alternative) => {
    const components = alternative.externalComponents;
    return Array.isArray(components) && components.length > 0;
  });
}

function formulaAlternativesHaveRequiredInputs(value: RuleEditorValue): boolean {
  return (formulaAlternativesJson(value) ?? []).some((alternative) => {
    const requiredInputs = alternative.requiredInputs;
    return Array.isArray(requiredInputs) && requiredInputs.length > 0;
  });
}

function externalComponentsJson(value: RuleEditorValue): Record<string, unknown>[] | null {
  if (value.externalComponents.length > 0) return externalComponentsFromDrafts(value);
  const raw = value.externalComponentsJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  return externalComponentsValidArray(parsed) ? parsed : null;
}

function externalComponentsValid(value: RuleEditorValue): boolean {
  if (value.externalComponents.length > 0) return externalComponentsFromDrafts(value) !== null;
  const raw = value.externalComponentsJson.trim();
  return raw === "" || externalComponentsJson(value) !== null;
}

function externalComponentsFromDrafts(value: RuleEditorValue): Record<string, unknown>[] | null {
  return externalComponentObjectsFromDrafts(value.externalComponents);
}

function externalComponentObjectsFromDrafts(
  externalComponents: ExternalComponentDraft[],
): Record<string, unknown>[] | null {
  if (externalComponents.length === 0 || externalComponents.length > 8) return null;
  const output: Record<string, unknown>[] = [];
  for (const component of externalComponents) {
    if (!isExternalComponentKind(component.kind)) return null;
    const weight = toNumber(component.weight);
    if (weight === undefined || weight < 0) return null;
    const label = component.label.trim();
    output.push({
      kind: component.kind,
      weight,
      ...(label !== "" ? { label } : {}),
      ...(component.required === false ? { required: false } : {}),
    });
  }
  return output;
}

function externalComponentDraftsFromUnknown(value: unknown): ExternalComponentDraft[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const component = asObject(item);
      if (!component || !isExternalComponentKind(component.kind) || !nonNegativeNumber(component.weight)) {
        return null;
      }
      const label =
        typeof component.label === "string" && component.label.trim() !== ""
          ? component.label
          : externalComponentDefaultLabel(component.kind);
      return {
        kind: component.kind,
        weight: String(component.weight),
        label,
        required: component.required !== false,
      };
    })
    .filter((component): component is ExternalComponentDraft => component !== null);
}

function externalComponentsValidArray(value: unknown): value is Record<string, unknown>[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > 8) return false;
  return value.every((item) => {
    const component = asObject(item);
    if (!component) return false;
    if (!isExternalComponentKind(component.kind)) return false;
    if (!nonNegativeNumber(component.weight)) return false;
    if (component.label !== undefined && (typeof component.label !== "string" || component.label.trim() === "")) {
      return false;
    }
    return component.required === undefined || typeof component.required === "boolean";
  });
}

function formulaAlternativesValidArray(
  value: unknown,
  defaultCalculationMode: CalculationMode = "weighted_average",
): value is Record<string, unknown>[] {
  if (!Array.isArray(value) || value.length === 0 || value.length > 8) return false;
  return value.every((item) => {
    const alternative = asObject(item);
    if (!alternative) return false;
    if (
      alternative.calculationMode !== undefined &&
      alternative.calculationMode !== "weighted_average" &&
      alternative.calculationMode !== "weighted_sum" &&
      alternative.calculationMode !== "normalized_sum"
    ) {
      return false;
    }
    const weights = asObject(alternative.weights);
    if (
      !weights ||
      !nonNegativeNumber(weights.korean) ||
      !nonNegativeNumber(weights.math) ||
      !nonNegativeNumber(weights.inquiry)
    ) {
      return false;
    }
    if (alternative.totalScale !== undefined && !isPositiveNumber(alternative.totalScale)) return false;
    if (alternative.csatWeight !== undefined && !nonNegativeNumber(alternative.csatWeight)) return false;
    if (
      alternative.subjectScoreTypes !== undefined &&
      !subjectScoreTypesRecordValid(alternative.subjectScoreTypes)
    ) {
      return false;
    }
    if (alternative.scoreMaxes !== undefined && !scoreMaxesRecordValid(alternative.scoreMaxes)) return false;
    if (
      alternative.subjectBaseScores !== undefined &&
      !subjectBaseScoresRecordValid(alternative.subjectBaseScores)
    ) {
      return false;
    }
    if (
      alternative.subjectBaseScores !== undefined &&
      (alternative.calculationMode ?? defaultCalculationMode) !== "normalized_sum"
    ) {
      return false;
    }
    if (alternative.selectionPolicy !== undefined && !selectionPolicyRecordValid(alternative.selectionPolicy)) {
      return false;
    }
    if (
      alternative.subjectAdjustments !== undefined &&
      !subjectAdjustmentsValidArray(alternative.subjectAdjustments)
    ) {
      return false;
    }
    if (
      alternative.finalAdjustments !== undefined &&
      !finalAdjustmentsValidArray(alternative.finalAdjustments)
    ) {
      return false;
    }
    if (
      alternative.requiredInputs !== undefined &&
      !requiredInputsValidArray(alternative.requiredInputs)
    ) {
      return false;
    }
    if (
      alternative.externalComponents !== undefined &&
      !externalComponentsValidArray(alternative.externalComponents)
    ) {
      return false;
    }
    return true;
  });
}

function selectionGroups(value: RuleEditorValue): Record<string, unknown>[] | null {
  const raw = value.selectionGroupsJson.trim();
  if (raw === "") return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!Array.isArray(parsed)) return null;
  const groups: Record<string, unknown>[] = [];
  for (const item of parsed) {
    const group = asObject(item);
    if (!group) return null;
    const count = group.count;
    const subjects = Array.isArray(group.subjects) ? group.subjects.filter(isSelectionSubject) : [];
    const requiredSubjects = Array.isArray(group.requiredSubjects)
      ? group.requiredSubjects.filter(isSelectionSubject)
      : [];
    const rankWeights = Array.isArray(group.rankWeights) ? group.rankWeights : [];
    if (count !== 1 && count !== 2 && count !== 3 && count !== 4) return null;
    if (subjects.length < count) return null;
    if (requiredSubjects.length > count) return null;
    if (requiredSubjects.some((subject) => !subjects.includes(subject))) return null;
    if (rankWeights.length !== count) return null;
    if (!rankWeights.every((weight) => typeof weight === "number" && weight > 0)) return null;
    groups.push({
      count,
      subjects,
      ...(requiredSubjects.length > 0 ? { requiredSubjects } : {}),
      rankWeights,
    });
  }
  return groups.length > 0 ? groups : null;
}

function selectionPolicyRecordValid(value: unknown): boolean {
  const policy = asObject(value);
  if (!policy || policy.mode !== "best_n_subjects") return false;
  const count = policy.count;
  if (count !== 1 && count !== 2 && count !== 3 && count !== 4) return false;
  const subjects = Array.isArray(policy.subjects) ? policy.subjects.filter(isSelectionSubject) : [];
  if (subjects.length < count) return false;
  const requiredSubjects = Array.isArray(policy.requiredSubjects)
    ? policy.requiredSubjects.filter(isSelectionSubject)
    : [];
  if (requiredSubjects.length > count) return false;
  if (requiredSubjects.some((subject) => !subjects.includes(subject))) return false;
  if (policy.rankWeights !== undefined) {
    if (!Array.isArray(policy.rankWeights) || policy.rankWeights.length !== count) return false;
    if (!policy.rankWeights.every(isPositiveNumber)) return false;
  }
  if (policy.groups !== undefined && !selectionGroupsFromRaw(policy.groups)) return false;
  return true;
}

function selectionGroupsFromRaw(value: unknown): Record<string, unknown>[] | null {
  if (!Array.isArray(value)) return null;
  const groups: Record<string, unknown>[] = [];
  for (const item of value) {
    const group = asObject(item);
    if (!group) return null;
    const count = group.count;
    const subjects = Array.isArray(group.subjects) ? group.subjects.filter(isSelectionSubject) : [];
    const requiredSubjects = Array.isArray(group.requiredSubjects)
      ? group.requiredSubjects.filter(isSelectionSubject)
      : [];
    const rankWeights = Array.isArray(group.rankWeights) ? group.rankWeights : [];
    if (count !== 1 && count !== 2 && count !== 3 && count !== 4) return null;
    if (subjects.length < count || rankWeights.length !== count) return null;
    if (requiredSubjects.length > count) return null;
    if (requiredSubjects.some((subject) => !subjects.includes(subject))) return null;
    if (!rankWeights.every(isPositiveNumber)) return null;
    groups.push({
      count,
      subjects,
      ...(requiredSubjects.length > 0 ? { requiredSubjects } : {}),
      rankWeights,
    });
  }
  return groups.length > 0 ? groups : null;
}

function selectedSubjects(value: RuleEditorValue): SelectionSubject[] {
  return SELECTION_SUBJECTS.flatMap((subject) =>
    value.selectionSubjects[subject.value] ? [subject.value] : [],
  );
}

function selectedRequiredSubjects(value: RuleEditorValue): SelectionSubject[] {
  return SELECTION_SUBJECTS.flatMap((subject) =>
    value.selectionRequiredSubjects[subject.value] ? [subject.value] : [],
  );
}

function selectionUsesEnglish(value: RuleEditorValue): boolean {
  if (value.selectionSubjects.english) return true;
  return (selectionGroups(value) ?? []).some((group) => {
    const subjects = group.subjects;
    return Array.isArray(subjects) && subjects.includes("english");
  });
}

function ruleUsesInquiry(value: RuleEditorValue): boolean {
  const inquiryWeight = toNumber(value.weights.inquiry) ?? 0;
  if (inquiryWeight > 0) return true;
  if (value.selectionEnabled && value.selectionSubjects.inquiry) return true;
  if (
    (selectionGroups(value) ?? []).some((group) => {
      const subjects = group.subjects;
      return Array.isArray(subjects) && subjects.includes("inquiry");
    })
  ) {
    return true;
  }
  return [...(subjectAdjustmentsJson(value) ?? []), ...(finalAdjustmentsJson(value) ?? [])].some(
    (adjustment) => adjustment.subject === "inquiry",
  );
}

function gradesCompleteNumeric(value: Record<string, string>): boolean {
  return GRADES.every((grade) => {
    const raw = value[grade] ?? "";
    return raw.trim() !== "" && toNumber(raw) !== undefined;
  });
}

function isSelectionSubject(value: unknown): value is SelectionSubject {
  return value === "korean" || value === "math" || value === "english" || value === "inquiry";
}

function isExternalComponentKind(value: unknown): value is ExternalComponentKind {
  return (
    value === "student_record" ||
    value === "practical" ||
    value === "interview" ||
    value === "essay" ||
    value === "document" ||
    value === "other"
  );
}

function externalComponentDefaultLabel(kind: ExternalComponentKind): string {
  return EXTERNAL_COMPONENT_KINDS.find((option) => option.value === kind)?.label ?? "기타";
}

function isPositiveNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

function nonNegativeNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function toNumber(value: string): number | undefined {
  if (value.trim() === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function numberFromUnknown(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function numToStr(value: unknown): string {
  return typeof value === "number" ? String(value) : "";
}
