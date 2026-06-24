"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DeepAnalysisOptIn } from "@/components/DeepAnalysisOptIn";
import { Disclaimer } from "@/components/Disclaimer";
import { LoginSheet } from "@/components/LoginSheet";
import { CheckIcon, SparklesIcon } from "@/components/icons";
import { track } from "@/lib/analytics";
import { ADMISSION_YEAR, readStoredState, writeStoredState } from "@/lib/client";

type ReportResponse = {
  report_id: string;
  content: {
    one_line_summary: string;
    student_summary: string;
    parent_summary: string;
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
    const params = new URLSearchParams(window.location.search);
    if (params.get("source") === "reminder") {
      track("return_from_reminder", {
        channel: params.get("channel") ?? "unknown",
        surface: "report",
      });
    }

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

  return (
    <main className="pb-8">
      <header className="space-y-1.5 pb-4 pt-2">
        <p className="flex items-center gap-1.5 text-xs font-medium text-slate-500">
          6모 포지션 리포트
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
            <SparklesIcon className="size-2.5" /> AI 생성
          </span>
        </p>
        <h1 className="text-xl font-bold leading-snug text-slate-900">
          {content.one_line_summary}
        </h1>
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

      {/* 고지/주의 */}
      <section className="mt-4 space-y-1.5 rounded-2xl bg-slate-100 p-4">
        {content.warnings.map((warning) => (
          <p key={warning} className="text-xs leading-5 text-slate-500">
            {warning}
          </p>
        ))}
      </section>

      {/* next CTA */}
      <p className="mt-4 rounded-2xl border border-band-match-soft bg-band-match-soft/60 p-4 text-sm font-medium leading-6 text-band-match-fg">
        {content.next_cta}
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

      <p className="mt-4 text-[10px] text-slate-400">
        {report.model_name} · prompt {report.prompt_version}
      </p>

      <Disclaimer />
      <DeepAnalysisOptIn />
      <LoginSheet surface="report" />
    </main>
  );
}

async function fetchCurrentCycleId(): Promise<string | null> {
  const res = await fetch(`/api/cycles?admission_year=${ADMISSION_YEAR}`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`입시 사이클 조회 실패(${res.status})`);
  const data = (await res.json()) as { cycle_id: string };
  return data.cycle_id;
}
