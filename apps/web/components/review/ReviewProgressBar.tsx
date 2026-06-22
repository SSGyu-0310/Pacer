"use client";

export function ReviewProgressBar({ decided, total }: { decided: number; total: number }) {
  const pct = total > 0 ? Math.round((decided / total) * 100) : 0;
  return (
    <div className="mt-3">
      <div className="h-2 overflow-hidden rounded bg-slate-200">
        <div className="h-full bg-cyan-500" style={{ width: `${pct}%` }} />
      </div>
      <p className="mt-1 text-[11px] text-slate-500">{pct}% reviewed</p>
    </div>
  );
}
