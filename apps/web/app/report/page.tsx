"use client";

import { DISCLAIMER } from "@pacer/shared";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import { CheckIcon, SparklesIcon } from "@/components/icons";
import { track } from "@/lib/analytics";
import { ADMISSION_YEAR, readStoredState, writeStoredState } from "@/lib/client";
import { BAND_META, type Band } from "@/lib/labels";

type ReportResponse = {
  report_id: string;
  content: {
    one_line_summary: string;
    student_summary: string;
    parent_summary: string;
    position_report?: {
      scope: "exploration" | "targeted";
      season?: {
        current: string;
        next: string | null;
        sampleConfidence: "low" | "medium" | "high";
      };
      metric: {
        mode: "percentile" | "converted";
        myValue: number | null;
        label: string;
        cutLabel: string;
      };
      lines: {
        univ: string;
        dept: string;
        group: string;
        keyWeight: string | null;
        myValue: number | null;
        cut: number | null;
        gap: number;
        tier: string;
        reliability: "high" | "mid" | "low" | "limited";
      }[];
      scenarios: { lever: string; delta: number; unlocks: string }[];
    } | null;
    strengths: { title: string; description: string; reason_code: string }[];
    weaknesses: { title: string; description: string; reason_code: string }[];
    recommended_actions: string[];
    warnings: string[];
    next_cta: string;
  };
  model_name: string;
  prompt_version: string;
  disclaimer: string;
  ai_usage_notice: string;
};

export default function ReportPage() {
  const [report, setReport] = useState<ReportResponse | null>(null);
  const [tab, setTab] = useState<"student" | "parent">("student");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadReport() {
      const stored = readStoredState();
      const localReport = stored?.report as ReportResponse | undefined;
      const queryReportId = new URLSearchParams(window.location.search).get("reportId");
      const localReportId = localReport?.report_id ?? stored?.reportId;

      if (localReport && (!queryReportId || queryReportId === localReportId)) {
        setReport(localReport);
        setLoading(false);
        track("report_view", { report_type: "june_position_report", source: "local" });
        return;
      }

      try {
        const cycleId = stored?.cycleId ?? (await fetchCurrentCycleId());
        if (!cycleId) {
          if (active) {
            setError("저장된 입시 사이클을 찾을 수 없습니다.");
            setLoading(false);
          }
          return;
        }

        const reportId = queryReportId ?? stored?.reportId;
        const url = reportId
          ? `/api/cycles/${cycleId}/reports?reportId=${reportId}`
          : `/api/cycles/${cycleId}/reports`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`리포트 조회 실패(${res.status})`);
        const nextReport = (await res.json()) as ReportResponse;
        if (!active) return;

        setReport(nextReport);
        setLoading(false);
        writeStoredState({
          ...stored,
          cycleId,
          reportId: nextReport.report_id,
          report: nextReport,
        });
        track("report_view", { report_type: "june_position_report", source: "server" });
      } catch (e) {
        if (!active) return;
        setError(e instanceof Error ? e.message : "리포트를 불러오지 못했습니다.");
        setLoading(false);
      }
    }

    void loadReport();
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <main className="flex flex-col items-center gap-3 py-24 text-sm text-slate-500">
        <span className="size-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
        AI 리포트를 불러오는 중입니다
      </main>
    );
  }

  if (!report) {
    return (
      <main className="space-y-6 py-10">
        <h1 className="text-xl font-bold text-slate-900">AI 전략 리포트</h1>
        <p className="text-sm text-slate-500">
          {error ?? "생성된 리포트를 찾을 수 없습니다."}
        </p>
        <Link
          className="text-sm font-semibold text-slate-900 underline underline-offset-4"
          href="/analysis"
        >
          분석 결과로 이동
        </Link>
      </main>
    );
  }

  const { content } = report;
  const position = content.position_report ?? null;
  const representativeLine = position?.lines[0] ?? null;
  const isExploration = position?.scope === "exploration";
  const representativeBand = representativeLine
    ? bandFromLabel(representativeLine.tier)
    : null;
  // 면책 문구는 하단 Disclaimer에서 1회만 노출. 저장 시점 문구가 상수와 미세하게
  // 달라도(버전 변경 등) 중복되지 않도록 시그니처 문구로 걸러낸다.
  const warnings = content.warnings.filter(
    (w) => w !== DISCLAIMER && !w.includes("합격을 보장하지 않습니다"),
  );

  return (
    <main className="pb-8">
      <header className="space-y-2 pb-4 pt-2">
        <div className="flex items-center gap-1.5">
          <p className="text-xs font-medium text-slate-500">
            {isExploration ? "6모 전체 라인 리포트" : "6모 포지션 리포트"}
          </p>
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
            <SparklesIcon className="size-2.5" /> AI 생성
          </span>
        </div>
        {representativeBand && representativeLine ? (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-bold ${BAND_META[representativeBand].badge}`}
          >
            {BAND_META[representativeBand].label}
            <span className="font-semibold tabular-nums opacity-80">
              {formatSigned(representativeLine.gap)}
            </span>
          </span>
        ) : null}
        <h1 className="text-xl font-bold leading-snug text-slate-900">
          {content.one_line_summary}
        </h1>
        {isExploration ? (
          <p className="text-sm leading-6 text-slate-500">
            지망 학교를 정하기 전, 전체 모집단위와 비교해 먼저 볼 성적대 라인을 정리했습니다.
          </p>
        ) : null}
      </header>

      {/* 학생/학부모 탭 */}
      <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
        {(
          [
            ["student", "학생용"],
            ["parent", "학부모님용"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setTab(value)}
            className={`h-9 rounded-lg text-xs font-medium transition ${
              tab === value
                ? "bg-white font-semibold text-slate-900 shadow-sm"
                : "text-slate-500"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {position && (
        <section className="mt-4 space-y-3">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="text-xs font-bold text-slate-500">핵심 숫자</h2>
            <div className="mt-3 grid grid-cols-3 gap-2 text-center">
              <MetricCell
                label={`내 ${position.metric.label}`}
                value={formatNullable(position.metric.myValue)}
              />
              <MetricCell
                label={position.metric.cutLabel}
                value={formatNullable(representativeLine?.cut ?? null)}
              />
              <MetricCell
                label="격차"
                value={formatSigned(representativeLine?.gap ?? null)}
                emphasis
              />
            </div>
            {representativeLine && representativeLine.cut != null ? (
              <PositionGauge
                gap={representativeLine.gap}
                mode={position.metric.mode}
                band={representativeBand}
              />
            ) : null}
          </div>

          {position.lines.length > 0 && (
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-4 py-3">
                <h2 className="text-xs font-bold text-slate-500">
                  {isExploration ? "성적대 라인" : "지원 가능 라인"}
                </h2>
              </div>
              <div className="divide-y divide-slate-100">
                {position.lines.slice(0, 5).map((line) => (
                  <div
                    key={`${line.univ}-${line.dept}-${line.group}`}
                    className="grid grid-cols-[1fr_auto] gap-3 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {line.univ} {line.dept}
                      </p>
                      <p className="mt-0.5 text-[11px] text-slate-500">
                        {[
                          line.group && line.group !== "-" ? `${line.group}군` : null,
                          line.keyWeight ?? "반영비 검수중",
                          line.cut != null ? `기준 ${formatNullable(line.cut)}` : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                    </div>
                    <div className="text-right">
                      <p
                        className={`text-sm font-bold tabular-nums ${
                          line.gap >= 0 ? "text-band-stable-fg" : "text-band-challenge-fg"
                        }`}
                      >
                        {formatSigned(line.gap)}
                      </p>
                      <p className="mt-0.5 text-[11px] font-semibold text-slate-500">
                        {line.tier}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {position.scenarios.length > 0 && (
            <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-4 py-3">
                <h2 className="text-xs font-bold text-slate-500">
                  What-if · 무엇을 올리면 무엇이 열리나
                </h2>
                <p className="mt-0.5 text-[11px] leading-4 text-slate-400">
                  지금 성적에서 한 과목을 올렸을 때 계산되는 위치 변화입니다. 성적 상승 예측이 아닙니다.
                </p>
              </div>
              <div className="divide-y divide-slate-100">
                {position.scenarios.map((scenario) => (
                  <div
                    key={`${scenario.lever}-${scenario.unlocks}`}
                    className="flex items-center justify-between gap-3 px-4 py-3"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {scenario.lever}
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-band-match-fg">
                        {scenario.unlocks}
                      </p>
                    </div>
                    <span className="shrink-0 rounded-lg bg-band-stable-soft px-2 py-1 text-xs font-bold tabular-nums text-band-stable-fg">
                      {formatSigned(scenario.delta)}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          )}
        </section>
      )}

      {tab === "student" ? (
        <div className="mt-4 space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <p className="text-sm leading-7 text-slate-700">{content.student_summary}</p>
          </section>

          {content.strengths.length > 0 && (
            <section className="space-y-2">
              <h2 className="px-1 text-xs font-bold text-slate-500">강점</h2>
              {content.strengths.map((item) => (
                <article
                  key={`${item.reason_code}-${item.title}`}
                  className="rounded-2xl border border-band-stable-soft bg-band-stable-soft/60 p-4"
                >
                  <h3 className="text-sm font-bold text-band-stable-fg">{item.title}</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-700">
                    {item.description}
                  </p>
                </article>
              ))}
            </section>
          )}

          {content.weaknesses.length > 0 && (
            <section className="space-y-2">
              <h2 className="px-1 text-xs font-bold text-slate-500">주의할 점</h2>
              {content.weaknesses.map((item) => (
                <article
                  key={`${item.reason_code}-${item.title}`}
                  className="rounded-2xl border border-warn-soft bg-warn-soft/60 p-4"
                >
                  <h3 className="text-sm font-bold text-warn-fg">{item.title}</h3>
                  <p className="mt-1 text-sm leading-6 text-slate-700">
                    {item.description}
                  </p>
                </article>
              ))}
            </section>
          )}

          {content.recommended_actions.length > 0 && (
            <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="text-xs font-bold text-slate-500">다음 행동</h2>
              <ul className="mt-2 space-y-2.5">
                {content.recommended_actions.map((action) => (
                  <li key={action} className="flex items-start gap-2 text-sm leading-6 text-slate-700">
                    <CheckIcon className="mt-1 size-3.5 shrink-0 text-band-stable" />
                    {action}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      ) : (
        <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-[17px] leading-8 text-slate-800">{content.parent_summary}</p>
        </section>
      )}

      {/* 타임라인 — 6모는 시즌의 출발점(불안 조성이 아니라 추적 동기) */}
      <SeasonTimeline season={position?.season ?? null} />

      {/* 고지/주의 — 면책 문구는 하단 Disclaimer에서 1회만 노출(중복 제거) */}
      {warnings.length > 0 && (
        <section className="mt-4 space-y-1.5 rounded-2xl bg-slate-100 p-4">
          {warnings.map((warning) => (
            <p key={warning} className="text-xs leading-5 text-slate-500">
              {warning}
            </p>
          ))}
        </section>
      )}

      {/* next CTA */}
      <p className="mt-4 rounded-2xl border border-band-match-soft bg-band-match-soft/60 p-4 text-sm font-medium leading-6 text-band-match-fg">
        {isExploration
          ? "분석 결과에서 관심 모집단위를 저장하면 다음 리포트는 목표 기준으로 더 좁혀 볼 수 있습니다."
          : content.next_cta}
      </p>

      <div className="mt-4 grid grid-cols-2 gap-2">
        <Link
          href="/analysis"
          className="flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
        >
          결과 다시 보기
        </Link>
        <Link
          href="/score"
          className="flex h-11 items-center justify-center rounded-xl bg-slate-900 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          다시 입력
        </Link>
      </div>

      <Disclaimer />
    </main>
  );
}

/** tier 라벨(한국어) → Band enum 역매핑 — 배지 색상에 사용 */
const TIER_LABEL_TO_BAND: Record<string, Band> = Object.entries(BAND_META).reduce(
  (acc, [band, meta]) => {
    acc[meta.label] = band as Band;
    return acc;
  },
  {} as Record<string, Band>,
);

function bandFromLabel(tier: string): Band | null {
  return TIER_LABEL_TO_BAND[tier] ?? null;
}

/**
 * 위치 게이지(§2) — 합격선(컷)=중앙 기준 내 점수가 어디에 있는지 시각화.
 * 지표(환산/백분위)에 따라 시각 범위를 달리해 막대가 항상 꽉 차 보이지 않게 한다.
 */
function PositionGauge({
  gap,
  mode,
  band,
}: {
  gap: number;
  mode: "percentile" | "converted";
  band: Band | null;
}) {
  const range = mode === "converted" ? 15 : 6;
  const clamped = Math.max(-range, Math.min(range, gap));
  const fillPct = (Math.abs(clamped) / range) * 50;
  const positive = gap >= 0;
  const barColor = band ? BAND_META[band].bar : positive ? "bg-band-stable" : "bg-band-challenge";

  return (
    <div className="mt-4">
      <div className="relative h-2 rounded-full bg-slate-100">
        {/* 중앙(합격선) 기준선 */}
        <span className="absolute left-1/2 top-1/2 h-3.5 w-px -translate-x-1/2 -translate-y-1/2 bg-slate-300" />
        {/* 내 위치 막대 — 중앙에서 좌(불리)/우(유리)로 */}
        <span
          className={`absolute top-0 h-2 rounded-full ${barColor}`}
          style={
            positive
              ? { left: "50%", width: `${fillPct}%` }
              : { right: "50%", width: `${fillPct}%` }
          }
        />
      </div>
      <div className="mt-1 flex justify-between text-[10px] font-medium text-slate-400">
        <span>합격선 아래</span>
        <span>합격선</span>
        <span>합격선 위</span>
      </div>
    </div>
  );
}

/** 시즌 타임라인(§7) — 6월 ─●─ 9월 ─ 수능, '지금 여기' 마커 */
function SeasonTimeline({
  season,
}: {
  season: { current: string; next: string | null; sampleConfidence: string } | null;
}) {
  const current = season?.current ?? "6월";
  const stops = ["6월", "9월", "수능"];
  const note =
    current === "6월"
      ? "지금은 6월 표본 기준입니다. 9월 모평 이후 정밀도가 올라가니 같은 기준으로 이어서 확인하세요."
      : current === "9월"
        ? "9월 모평 기준입니다. 수능까지 변화를 이어서 추적하세요."
        : "수능 기준 위치입니다.";

  return (
    <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-xs font-bold text-slate-500">시즌 타임라인</h2>
      <div className="mt-3 flex items-center">
        {stops.map((stop, index) => {
          const active = stop === current;
          return (
            <div key={stop} className="flex flex-1 items-center last:flex-none">
              <div className="flex flex-col items-center gap-1">
                <span
                  className={`size-3 rounded-full ${
                    active ? "bg-slate-900 ring-4 ring-slate-900/10" : "bg-slate-300"
                  }`}
                />
                <span
                  className={`text-[11px] ${
                    active ? "font-bold text-slate-900" : "font-medium text-slate-400"
                  }`}
                >
                  {stop}
                  {active ? " (지금)" : ""}
                </span>
              </div>
              {index < stops.length - 1 ? (
                <span className="mx-1 h-px flex-1 bg-slate-200" />
              ) : null}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500">{note}</p>
    </section>
  );
}

function MetricCell({
  label,
  value,
  emphasis = false,
}: {
  label: string;
  value: string;
  emphasis?: boolean;
}) {
  return (
    <div className="rounded-xl bg-slate-50 px-2 py-3">
      <p className="text-[10px] font-medium text-slate-500">{label}</p>
      <p
        className={`mt-1 text-lg font-bold tabular-nums ${
          emphasis ? "text-slate-950" : "text-slate-800"
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function formatNullable(value: number | null | undefined): string {
  return value === null || value === undefined ? "-" : value.toFixed(1);
}

function formatSigned(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return `${value >= 0 ? "+" : ""}${value.toFixed(1)}`;
}

async function fetchCurrentCycleId(): Promise<string | null> {
  const res = await fetch(`/api/cycles?admission_year=${ADMISSION_YEAR}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`입시 사이클 조회 실패(${res.status})`);
  const data = (await res.json()) as { cycle_id: string };
  return data.cycle_id;
}
