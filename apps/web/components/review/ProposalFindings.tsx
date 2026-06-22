"use client";

interface FieldFinding {
  field: string;
  evidenceSupport: "strong" | "partial" | "missing";
  note?: string;
}

const SUPPORT_STYLE: Record<FieldFinding["evidenceSupport"], string> = {
  strong: "bg-emerald-100 text-emerald-800",
  partial: "bg-amber-100 text-amber-800",
  missing: "bg-rose-100 text-rose-800",
};

const SUPPORT_LABEL: Record<FieldFinding["evidenceSupport"], string> = {
  strong: "근거 충분",
  partial: "부분 근거",
  missing: "근거 없음",
};

/** AI 초안의 필드별 evidence 근거와 불확실 플래그를 칩으로 노출 (§231). */
export function ProposalFindings({ proposal }: { proposal: Record<string, unknown> | null }) {
  if (!proposal) return null;
  const findings = parseFindings(proposal.fieldFindings);
  const uncertain = parseUncertain(proposal.uncertain);
  if (findings.length === 0 && uncertain.length === 0) return null;

  return (
    <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
      <p className="mb-2 text-xs font-semibold text-slate-700">AI 근거</p>
      {findings.length > 0 ? (
        <ul className="space-y-1.5">
          {findings.map((finding) => (
            <li key={finding.field} className="flex items-start gap-2 text-[11px]">
              <span className={`rounded px-1.5 py-0.5 font-semibold ${SUPPORT_STYLE[finding.evidenceSupport]}`}>
                {SUPPORT_LABEL[finding.evidenceSupport]}
              </span>
              <span className="min-w-0">
                <span className="font-mono text-slate-800">{finding.field}</span>
                {finding.note ? <span className="text-slate-500"> — {finding.note}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
      {uncertain.length > 0 ? (
        <div className="mt-2 border-t border-slate-200 pt-2">
          <p className="text-[11px] font-semibold text-amber-700">불확실</p>
          <ul className="mt-1 list-inside list-disc text-[11px] text-slate-600">
            {uncertain.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function parseFindings(value: unknown): FieldFinding[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((raw) => {
    if (typeof raw !== "object" || raw === null) return [];
    const finding = raw as Record<string, unknown>;
    const support = finding.evidenceSupport;
    if (support !== "strong" && support !== "partial" && support !== "missing") return [];
    return [
      {
        field: String(finding.field ?? "field"),
        evidenceSupport: support,
        note: typeof finding.note === "string" ? finding.note : undefined,
      },
    ];
  });
}

function parseUncertain(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string");
}
