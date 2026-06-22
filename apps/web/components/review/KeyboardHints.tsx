"use client";

const HINTS = [
  ["Enter", "규칙 저장 / 입결 높음"],
  ["1-4", "입결 신뢰도"],
  ["S", "스킵"],
  ["F", "플래그"],
  ["J/K", "이동"],
  ["A", "AI초안 일괄 확정"],
];

export function KeyboardHints() {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="mb-2 text-xs font-semibold text-slate-700">Keyboard</p>
      <div className="grid grid-cols-2 gap-2">
        {HINTS.map(([key, label]) => (
          <div key={key} className="flex items-center gap-2 text-xs text-slate-600">
            <kbd className="min-w-9 rounded border border-slate-300 bg-white px-1.5 py-0.5 text-center font-mono text-[11px] text-slate-800">
              {key}
            </kbd>
            <span>{label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
