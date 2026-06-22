"use client";

import { useState } from "react";

type ScoreType = "standard" | "percentile" | "mixed" | "custom";
type EnglishMode = "deduction" | "addition";
type InquiryMode = "average" | "best_one";

export interface RuleEditorValue {
  scoreType: ScoreType;
  totalScale: string;
  weights: { korean: string; math: string; inquiry: string };
  englishMode: EnglishMode;
  englishByGrade: Record<string, string>;
  historyByGrade: Record<string, string>;
  inquiryCount: "1" | "2";
  inquiryMode: InquiryMode;
  inquiryConversionRisk: boolean;
  eligibilityJson: string;
}

const GRADES = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];

/* ── 초기값 / 변환 / 검증 (AdminReviewApp에서 재사용) ── */

export function emptyRuleEditorValue(): RuleEditorValue {
  return {
    scoreType: "custom",
    totalScale: "",
    weights: { korean: "", math: "", inquiry: "" },
    englishMode: "deduction",
    englishByGrade: {},
    historyByGrade: {},
    inquiryCount: "2",
    inquiryMode: "average",
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
  const st = pickScoreType(proposed.scoreType ?? parsedFields.score_type);
  if (st) base.scoreType = st;

  const formula = asObject(proposed.formulaJson) ?? engineFormula(parsedFields.formula_json);
  if (formula) {
    if (typeof formula.totalScale === "number") base.totalScale = String(formula.totalScale);
    const w = asObject(formula.weights);
    if (w) {
      base.weights = {
        korean: numToStr(w.korean),
        math: numToStr(w.math),
        inquiry: numToStr(w.inquiry),
      };
    }
  }

  const english = asObject(proposed.englishPolicyJson) ?? engineByGradePolicy(parsedFields.english_policy_json);
  if (english) {
    if (english.mode === "deduction" || english.mode === "addition") base.englishMode = english.mode;
    base.englishByGrade = byGradeToStrings(english.byGrade);
  }

  const history = asObject(proposed.historyPolicyJson) ?? engineByGradePolicy(parsedFields.history_policy_json);
  if (history) base.historyByGrade = byGradeToStrings(history.byGrade);

  const inquiry = asObject(proposed.inquiryPolicyJson) ?? engineInquiry(parsedFields.inquiry_policy_json);
  if (inquiry) {
    if (inquiry.count === 1 || inquiry.count === 2) base.inquiryCount = String(inquiry.count) as "1" | "2";
    if (inquiry.mode === "average" || inquiry.mode === "best_one") base.inquiryMode = inquiry.mode;
    base.inquiryConversionRisk = inquiry.conversionRisk === true;
  }

  const eligibility = asObject(proposed.eligibilityJson) ?? engineEligibility(parsedFields.eligibility_json);
  if (eligibility) base.eligibilityJson = JSON.stringify(eligibility, null, 2);

  return base;
}

/** 편집기 값 → corrected_fields (엔진 형태). eligibility JSON이 깨지면 throw. */
export function ruleValueToCorrectedFields(value: RuleEditorValue): Record<string, unknown> {
  return {
    scoreType: value.scoreType,
    formulaJson: {
      totalScale: toNumber(value.totalScale) ?? 0,
      weights: {
        korean: toNumber(value.weights.korean) ?? 0,
        math: toNumber(value.weights.math) ?? 0,
        inquiry: toNumber(value.weights.inquiry) ?? 0,
      },
    },
    englishPolicyJson: { mode: value.englishMode, byGrade: numericByGrade(value.englishByGrade) },
    historyPolicyJson: { byGrade: numericByGrade(value.historyByGrade) },
    inquiryPolicyJson: {
      count: Number(value.inquiryCount),
      mode: value.inquiryMode,
      conversionRisk: value.inquiryConversionRisk,
    },
    eligibilityJson: value.eligibilityJson.trim() === "" ? {} : JSON.parse(value.eligibilityJson),
  };
}

/** mapRule을 미러링해 "지금 값이면 exact가 풀리는가"를 클라이언트에서 즉시 판정. */
export function ruleValueUnlocksExact(value: RuleEditorValue): boolean {
  const totalScale = toNumber(value.totalScale);
  if (totalScale === undefined || totalScale <= 0) return false;
  for (const w of [value.weights.korean, value.weights.math, value.weights.inquiry]) {
    const n = toNumber(w);
    if (n === undefined || n < 0) return false;
  }
  if (!gradesAllNumeric(value.englishByGrade) || !gradesAllNumeric(value.historyByGrade)) return false;
  if (value.eligibilityJson.trim() !== "") {
    try {
      JSON.parse(value.eligibilityJson);
    } catch {
      return false;
    }
  }
  return true;
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

  return (
    <div className="mt-4 space-y-4">
      <div
        className={`rounded-lg border p-3 ${
          unlocksExact ? "border-emerald-300 bg-emerald-50" : "border-rose-200 bg-rose-50"
        }`}
      >
        <p className="text-xs font-semibold text-slate-700">정확 환산(exact) 가능 여부</p>
        <p className={`mt-0.5 text-sm font-bold ${unlocksExact ? "text-emerald-700" : "text-rose-700"}`}>
          {unlocksExact ? "✓ 풀림 — 저장하면 정확 환산이 켜집니다" : "✕ 아직 — 환산총점·가중치를 채우세요"}
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
      </Field>

      <Field label="영어 반영" hint="감점/가산 + 등급별 점수(빈 칸은 무시)">
        <Segmented
          options={[
            { value: "deduction", label: "감점" },
            { value: "addition", label: "가산" },
          ]}
          value={value.englishMode}
          onChange={(v) => set({ englishMode: v as EnglishMode })}
        />
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
        {showAdvanced ? "▾ 고급 항목 숨기기" : "▸ 고급 항목 (한국사·지원자격)"}
      </button>

      {showAdvanced ? (
        <div className="space-y-4 border-t border-slate-200 pt-4">
          <Field label="한국사 등급별 점수" hint="빈 칸은 무시">
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
  return asObject(obj.byGrade) || obj.mode === "deduction" || obj.mode === "addition" ? obj : null;
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

function gradesAllNumeric(value: Record<string, string>): boolean {
  return Object.values(value).every((raw) => raw.trim() === "" || toNumber(raw) !== undefined);
}

function toNumber(value: string): number | undefined {
  if (value.trim() === "") return undefined;
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function numToStr(value: unknown): string {
  return typeof value === "number" ? String(value) : "";
}
