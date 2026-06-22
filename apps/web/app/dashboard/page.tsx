"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Disclaimer } from "@/components/Disclaimer";
import {
  ADMISSION_YEAR,
  readStoredState,
  writeStoredState,
  type StoredState,
} from "@/lib/client";

export default function DashboardPage() {
  const [state, setState] = useState<{
    cycleId?: string;
    examScoreId?: string;
    snapshotId?: string;
    reportId?: string;
  } | null>(null);

  useEffect(() => {
    let active = true;

    async function loadState() {
      const stored = readStoredState();
      let next: StoredState | null = stored;

      try {
        const cycleId = stored?.cycleId ?? (await fetchCurrentCycleId());
        if (cycleId) {
          const report = await fetchLatestReport(cycleId);
          next = {
            ...stored,
            cycleId,
            reportId: report?.report_id ?? stored?.reportId,
            report: report ?? stored?.report,
          };
          writeStoredState(next);
        }
      } catch {
        next = stored;
      }

      if (active) {
        setState({
          cycleId: next?.cycleId,
          examScoreId: next?.examScoreId,
          snapshotId: next?.snapshotId,
          reportId: next?.reportId,
        });
      }
    }

    void loadState();
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="space-y-8 pb-12">
      <header className="space-y-3 border-b border-slate-200 pb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
          Pacer
        </p>
        <h1 className="text-2xl font-bold leading-tight">정시 대시보드</h1>
        <p className="text-sm leading-6 text-slate-600">
          6모 내부 데모 데이터로 입력, 분석, 리포트, 알림 신청 상태를 이어서 확인합니다.
        </p>
      </header>

      <section className="space-y-3">
        <StatusLine
          label="성적 입력"
          done={Boolean(state?.examScoreId ?? state?.snapshotId)}
        />
        <StatusLine label="분석 결과" done={Boolean(state?.snapshotId)} />
        <StatusLine label="AI 리포트" done={Boolean(state?.reportId)} />
      </section>

      <div className="grid gap-3">
        <Link
          href="/score"
          className="flex h-12 items-center justify-center rounded-xl bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          성적 입력
        </Link>
        {state?.snapshotId ? (
          <Link
            href={`/analysis?snapshotId=${state.snapshotId}`}
            className="flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            분석 결과
          </Link>
        ) : null}
        {state?.reportId ? (
          <Link
            href={`/report?reportId=${state.reportId}`}
            className="flex h-11 items-center justify-center rounded-xl border border-slate-200 bg-white px-4 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
          >
            리포트
          </Link>
        ) : null}
      </div>

      <Disclaimer />
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

async function fetchLatestReport(cycleId: string): Promise<{ report_id: string } | null> {
  const res = await fetch(`/api/cycles/${cycleId}/reports`);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`리포트 조회 실패(${res.status})`);
  return (await res.json()) as { report_id: string };
}

function StatusLine({ label, done }: { label: string; done: boolean }) {
  return (
    <div className="flex items-center justify-between border-t border-slate-200 py-3">
      <span className="text-sm font-medium">{label}</span>
      <span className={`text-xs font-semibold ${done ? "text-slate-900" : "text-slate-400"}`}>
        {done ? "완료" : "대기"}
      </span>
    </div>
  );
}
