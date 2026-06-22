"use client";

type Confidence = "limited" | "low" | "medium" | "high";

const OPTIONS: { value: Confidence; label: string; key: string }[] = [
  { value: "limited", label: "제한", key: "1" },
  { value: "low", label: "낮음", key: "2" },
  { value: "medium", label: "중간", key: "3" },
  { value: "high", label: "높음", key: "4" },
];

export function OutcomeConfidenceControl({
  value,
  onChange,
}: {
  value: Confidence;
  onChange: (value: Confidence) => void;
}) {
  return (
    <div className="mt-4">
      <p className="mb-2 text-xs font-semibold text-slate-700">입결 confidence</p>
      <div className="grid grid-cols-4 gap-2">
        {OPTIONS.map((option) => (
          <button
            key={option.value}
            onClick={() => onChange(option.value)}
            className={`rounded border px-2 py-3 text-xs font-semibold ${
              option.value === value
                ? "border-cyan-500 bg-cyan-50 text-cyan-800"
                : "border-slate-200 bg-white text-slate-700"
            }`}
          >
            <span className="block text-[10px] text-slate-500">{option.key}</span>
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
