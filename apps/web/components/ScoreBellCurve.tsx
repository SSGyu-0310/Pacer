"use client";

import { useMemo, useState } from "react";

/**
 * 전국 분포(정규분포 가정) 위 내 위치 시각화.
 *
 * 과목별 보기: 성적표의 **백분위 그대로**를 역정규분포(Φ⁻¹)로 변환해 위치를 잡는다.
 * 종합 보기: 과목 백분위 → z점수 → **가중 z평균** → Φ로 다시 백분위화.
 *   - 백분위 단순 평균은 합산 점수의 분포를 왜곡하므로 쓰지 않는다.
 *   - 과목 간 상관계수 1을 가정한 **보수적** 추정 — 전과목이 고르게 상위권인
 *     학생의 실제 종합 순위는 이 표시보다 높을 수 있다(§2.1 단정 금지와 정합).
 *   - 가중치는 통용되는 반영 패턴 3종(균등/인문형/자연형)이며 특정 대학의
 *     환산식이 아니다. 대학별 환산은 서버 엔진 결과(§8.1)를 따른다.
 * 영어·한국사는 절대평가(백분위 없음)라 모든 보기에서 제외한다.
 */

export type SubjectScoreView = {
  subject: string;
  selection: string | null;
  standard_score: number | null;
  percentile: number | null;
  grade: number | null;
};

const CURVE_SUBJECTS: Record<string, string> = {
  korean: "국어",
  math: "수학",
  inquiry1: "탐구1",
  inquiry2: "탐구2",
};

/** 통용 반영 패턴 — 대학별 환산식이 아닌 예시 가중치 (국:수:탐, 탐구는 과목 평균) */
const PRESETS = [
  { id: "balanced", label: "균등", weights: { korean: 1, math: 1, inquiry: 1 } },
  { id: "humanities", label: "인문형", weights: { korean: 4, math: 3, inquiry: 3 } },
  { id: "natural", label: "자연형", weights: { korean: 2.5, math: 4, inquiry: 3.5 } },
] as const;
type PresetId = (typeof PRESETS)[number]["id"];

function defaultPreset(track?: string | null): PresetId {
  if (track === "humanities") return "humanities";
  if (track === "natural" || track === "medical") return "natural";
  return "balanced";
}

/* ── SVG 기하 상수 ── */
const W = 320;
const H = 118;
const BASELINE = 104;
const AMPLITUDE = 86;
const Z_MIN = -3;
const Z_MAX = 3;

const xOf = (z: number) => ((z - Z_MIN) / (Z_MAX - Z_MIN)) * W;
const yOf = (z: number) => BASELINE - Math.exp((-z * z) / 2) * AMPLITUDE;

/** 표준정규 역CDF — Acklam 근사 (|ε| < 1.2e-8, 의존성 없음) */
function inverseNormalCdf(p: number): number {
  const pLow = 0.02425;
  const pHigh = 1 - pLow;
  if (p < pLow) {
    const q = Math.sqrt(-2 * Math.log(p));
    return (
      (((((-7.784894002430293e-3 * q - 3.223964580411365e-1) * q -
        2.400758277161838) *
        q -
        2.549732539343734) *
        q +
        4.374664141464968) *
        q +
        2.938163982698783) /
      ((((7.784695709041462e-3 * q + 3.224671290700398e-1) * q +
        2.445134137142996) *
        q +
        3.754408661907416) *
        q +
        1)
    );
  }
  if (p <= pHigh) {
    const q = p - 0.5;
    const r = q * q;
    return (
      ((((((-3.969683028665376e1 * r + 2.209460984245205e2) * r -
        2.759285104469687e2) *
        r +
        1.38357751867269e2) *
        r -
        3.066479806614716e1) *
        r +
        2.506628277459239) *
        q) /
      (((((-5.447609879822406e1 * r + 1.615858368580409e2) * r -
        1.556989798598866e2) *
        r +
        6.680131188771972e1) *
        r -
        1.328068155288572e1) *
        r +
        1)
    );
  }
  const q = Math.sqrt(-2 * Math.log(1 - p));
  return (
    -(
      ((((-7.784894002430293e-3 * q - 3.223964580411365e-1) * q -
        2.400758277161838) *
        q -
        2.549732539343734) *
        q +
        4.374664141464968) *
        q +
      2.938163982698783
    ) /
    ((((7.784695709041462e-3 * q + 3.224671290700398e-1) * q +
      2.445134137142996) *
      q +
      3.754408661907416) *
      q +
      1)
  );
}

/** 표준정규 CDF — Φ(z) = (1+erf(z/√2))/2, erf는 Abramowitz–Stegun 7.1.26 (|ε| < 1.5e-7) */
function normalCdf(z: number): number {
  const x = z / Math.SQRT2;
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const erf =
    1 -
    (((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t -
      0.284496736) *
      t +
      0.254829592) *
      t) *
      Math.exp(-x * x);
  const phi = 0.5 * (1 + (x >= 0 ? erf : -erf));
  return Math.min(Math.max(phi, 0), 1);
}

/** 종 곡선 path (열린 곡선) + 면적 path (베이스라인까지 닫힘) */
function buildPaths(): { curve: string; area: string } {
  const pts: string[] = [];
  for (let z = Z_MIN; z <= Z_MAX + 1e-9; z += 0.1) {
    pts.push(`${xOf(z).toFixed(2)},${yOf(z).toFixed(2)}`);
  }
  const curve = `M${pts.join(" L")}`;
  const area = `${curve} L${W},${BASELINE} L0,${BASELINE} Z`;
  return { curve, area };
}
const PATHS = buildPaths();

function topPercentLabel(percentile: number): string {
  const top = 100 - percentile;
  if (top <= 0.5) return "상위 0.5% 이내";
  const value = top < 10 ? Math.round(top * 10) / 10 : Math.round(top);
  return `상위 ${value}%`;
}

/** 가중 z평균 종합 — 빠진 과목은 가중치 재정규화로 흡수 */
function compositePercentile(
  subjects: SubjectScoreView[],
  presetId: PresetId,
): number | null {
  const preset = PRESETS.find((p) => p.id === presetId) ?? PRESETS[0];
  const inquiries = subjects.filter(
    (s) => s.subject === "inquiry1" || s.subject === "inquiry2",
  );
  let weightSum = 0;
  let zSum = 0;
  for (const s of subjects) {
    if (s.percentile === null) continue;
    let w = 0;
    if (s.subject === "korean") w = preset.weights.korean;
    else if (s.subject === "math") w = preset.weights.math;
    else if (s.subject === "inquiry1" || s.subject === "inquiry2")
      w = preset.weights.inquiry / inquiries.length;
    if (w <= 0) continue;
    const p = Math.min(Math.max(s.percentile, 0.6), 99.4) / 100;
    zSum += w * inverseNormalCdf(p);
    weightSum += w;
  }
  if (weightSum === 0) return null;
  return normalCdf(zSum / weightSum) * 100;
}

/** 통용 '국수탐 백분위 합'(300 만점) — 탐구는 입력된 과목 평균 */
function percentileSum300(subjects: SubjectScoreView[]): number | null {
  const get = (key: string) =>
    subjects.find((s) => s.subject === key)?.percentile ?? null;
  const korean = get("korean");
  const math = get("math");
  const inq = subjects
    .filter(
      (s) =>
        (s.subject === "inquiry1" || s.subject === "inquiry2") &&
        s.percentile !== null,
    )
    .map((s) => s.percentile ?? 0);
  if (korean === null || math === null || inq.length === 0) return null;
  const inqAvg = inq.reduce((a, b) => a + b, 0) / inq.length;
  return korean + math + inqAvg;
}

const EASE = "cubic-bezier(0.22, 1, 0.36, 1)";
const COMPOSITE = "__composite__";

export function ScoreBellCurve({
  scores,
  track,
}: {
  scores: SubjectScoreView[];
  track?: string | null;
}) {
  const subjects = useMemo(
    () =>
      scores.filter(
        (s) =>
          s.subject in CURVE_SUBJECTS &&
          s.percentile !== null &&
          Number.isFinite(s.percentile),
      ),
    [scores],
  );
  const [selected, setSelected] = useState<string>(COMPOSITE);
  const [presetId, setPresetId] = useState<PresetId>(() => defaultPreset(track));

  const fallback = subjects[0];
  if (!fallback) return null;

  const isComposite = selected === COMPOSITE && subjects.length >= 2;
  const currentSubject = isComposite
    ? null
    : (subjects.find((s) => s.subject === selected) ?? fallback);

  const compositeP = isComposite ? compositePercentile(subjects, presetId) : null;
  const percentile = isComposite
    ? (compositeP ?? 50)
    : (currentSubject?.percentile ?? 50);
  const sum300 = isComposite ? percentileSum300(subjects) : null;
  const preset = PRESETS.find((p) => p.id === presetId) ?? PRESETS[0];

  // 마커가 화면 밖으로 나가지 않도록 시각 위치만 클램프 (수치는 원본 표기)
  const z = inverseNormalCdf(Math.min(Math.max(percentile, 0.6), 99.4) / 100);
  const markerX = xOf(z);
  const markerY = yOf(z);
  const topLabel = topPercentLabel(percentile);
  const pillLeft = Math.min(Math.max((markerX / W) * 100, 12), 88);

  const subjectLabel = (s: SubjectScoreView) => {
    const base = CURVE_SUBJECTS[s.subject] ?? s.subject;
    return s.selection ? `${base} · ${s.selection}` : base;
  };
  const currentLabel = isComposite
    ? `종합(${preset.label})`
    : subjectLabel(currentSubject ?? fallback);

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-baseline justify-between gap-2">
        <h2 className="text-sm font-bold text-slate-900">전국 분포에서 내 위치</h2>
        <p className="text-[11px] text-slate-400">백분위 기준 · 정규분포 가정</p>
      </div>

      {/* 보기 전환 칩: 종합 + 과목별 */}
      <div className="mt-3 flex gap-1.5 overflow-x-auto pb-0.5" role="tablist">
        {subjects.length >= 2 ? (
          <Chip
            active={isComposite}
            onClick={() => setSelected(COMPOSITE)}
            label="종합"
          />
        ) : null}
        {subjects.map((s) => (
          <Chip
            key={s.subject}
            active={!isComposite && currentSubject?.subject === s.subject}
            onClick={() => setSelected(s.subject)}
            label={subjectLabel(s)}
          />
        ))}
      </div>

      {/* 종합 모드: 산출식 프리셋 — 통용 반영 패턴이며 대학별 환산식이 아님 */}
      {isComposite ? (
        <div className="mt-2 flex items-center gap-1.5">
          <div className="grid flex-1 grid-cols-3 gap-1 rounded-lg bg-slate-100 p-0.5">
            {PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => setPresetId(p.id)}
                className={`h-7 rounded-md text-[11px] font-medium transition ${
                  presetId === p.id
                    ? "bg-white font-semibold text-slate-900 shadow-sm"
                    : "text-slate-500"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <span className="shrink-0 text-[10px] tabular-nums text-slate-400">
            국{preset.weights.korean}:수{preset.weights.math}:탐
            {preset.weights.inquiry}
          </span>
        </div>
      ) : null}

      {/* 곡선 */}
      <div className="relative mt-2">
        <div
          className="pointer-events-none absolute top-0 z-10 -translate-x-1/2"
          style={{ left: `${pillLeft}%`, transition: `left 0.45s ${EASE}` }}
        >
          <span className="inline-flex items-center gap-1 whitespace-nowrap rounded-full bg-band-match px-2 py-0.5 text-[11px] font-semibold text-white shadow-sm">
            내 위치 · {topLabel}
          </span>
        </div>

        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="block w-full"
          role="img"
          aria-label={`${currentLabel} 백분위 ${Math.round(percentile * 10) / 10} — ${topLabel}`}
        >
          <defs>
            <linearGradient id="bellFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#2563eb" stopOpacity="0.28" />
              <stop offset="100%" stopColor="#2563eb" stopOpacity="0.04" />
            </linearGradient>
            <clipPath id="bellClip">
              <rect
                x="0"
                y="0"
                height={H}
                width={markerX}
                style={{ transition: `width 0.45s ${EASE}` }}
              />
            </clipPath>
          </defs>

          <line
            x1={W / 2}
            y1={yOf(0) - 4}
            x2={W / 2}
            y2={BASELINE}
            stroke="#e2e8f0"
            strokeWidth="1"
            strokeDasharray="3 3"
          />

          <path d={PATHS.area} fill="url(#bellFill)" clipPath="url(#bellClip)" />
          <path
            d={PATHS.curve}
            fill="none"
            stroke="#cbd5e1"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <line x1="0" y1={BASELINE} x2={W} y2={BASELINE} stroke="#e2e8f0" />

          <rect
            x={markerX - 0.75}
            y={markerY}
            width="1.5"
            height={BASELINE - markerY}
            rx="0.75"
            fill="#2563eb"
            style={{
              transition: `x 0.45s ${EASE}, y 0.45s ${EASE}, height 0.45s ${EASE}`,
            }}
          />
          <circle
            cx={markerX}
            cy={markerY}
            r="4.5"
            fill="#2563eb"
            stroke="#fff"
            strokeWidth="2"
            style={{ transition: `cx 0.45s ${EASE}, cy 0.45s ${EASE}` }}
          />
        </svg>

        <div className="flex justify-between text-[10px] text-slate-400">
          <span>← 하위</span>
          <span>평균 (백분위 50)</span>
          <span>상위 →</span>
        </div>
      </div>

      {/* 수치 요약 */}
      <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3">
        {isComposite ? (
          <>
            <Stat
              label="백분위 합 (300)"
              value={sum300 !== null ? `${Math.round(sum300 * 10) / 10}` : "—"}
            />
            <Stat
              label={`종합 백분위 (${preset.label})`}
              value={Math.round(percentile * 10) / 10}
            />
            <Stat label="전국 위치" value={topLabel.replace("상위 ", "")} accent />
          </>
        ) : (
          <>
            <Stat label="표준점수" value={currentSubject?.standard_score ?? "—"} />
            <Stat label="백분위" value={percentile} />
            <Stat label="전국 위치" value={topLabel.replace("상위 ", "")} accent />
          </>
        )}
      </dl>

      <p className="mt-3 text-[11px] leading-4 text-slate-400">
        {isComposite
          ? "종합 위치는 통용 반영 패턴 기준의 보수적 추정으로, 실제 누적 분포·대학별 환산 결과와 다를 수 있습니다. 합격 예측이 아닙니다."
          : "성적표의 백분위(전국 비율)를 위치로 옮긴 해석용 그래프입니다. 실제 분포 모양은 시험마다 다를 수 있으며, 합격 예측이 아닙니다."}
      </p>
    </section>
  );
}

function Chip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`h-8 shrink-0 whitespace-nowrap rounded-lg border px-2.5 text-xs font-medium transition ${
        active
          ? "border-slate-900 bg-slate-900 font-semibold text-white"
          : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"
      }`}
    >
      {label}
    </button>
  );
}

function Stat({
  label,
  value,
  accent = false,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <div>
      <dt className="truncate text-[11px] text-slate-500">{label}</dt>
      <dd
        className={`mt-0.5 text-base font-bold tabular-nums ${
          accent ? "text-band-match-fg" : "text-slate-900"
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
