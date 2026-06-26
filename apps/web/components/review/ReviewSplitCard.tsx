"use client";

import type React from "react";

interface Detail {
  kind: "rule" | "outcome";
  source_url: string | null;
  parsed_fields: Record<string, unknown>;
  evidence: Record<string, unknown> | null;
  ai_proposal: { proposal_json: Record<string, unknown> } | null;
}

export function ReviewSplitCard({ detail }: { detail: Detail | null }) {
  if (!detail) {
    return <div className="flex h-full items-center justify-center p-5 text-sm text-slate-400">불러오는 중…</div>;
  }
  const quote = String(detail.ai_proposal?.proposal_json.evidenceQuote ?? "");
  const textPreview = String(detail.evidence?.textPreview ?? detail.evidence?.rowText ?? "");
  const rawPath = String(detail.evidence?.rawPath ?? "");
  const attachmentUrl = String(detail.evidence?.attachmentUrl ?? "");
  const sourceWarnings = warningList(detail.evidence?.sourceWarnings);
  const lines = splitSignals(textPreview);

  return (
    <div className="h-full overflow-y-auto p-5">
      {/* 원문 근거 */}
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-sm font-semibold">원문 근거</h2>
        <div className="flex items-center gap-3 text-xs font-semibold">
          {detail.source_url ? (
            <a href={detail.source_url} target="_blank" rel="noreferrer" className="text-cyan-700">
              원문 페이지 ↗
            </a>
          ) : null}
          {attachmentUrl ? (
            <a href={attachmentUrl} target="_blank" rel="noreferrer" className="text-cyan-700">
              첨부 ↗
            </a>
          ) : null}
          {rawPath ? (
            <a
              href={`/api/admin/review/evidence/file?path=${encodeURIComponent(rawPath)}`}
              target="_blank"
              rel="noreferrer"
              className="text-cyan-700"
            >
              수집 원문 ↗
            </a>
          ) : null}
        </div>
      </div>

      {sourceWarnings.length > 0 ? (
        <div className="mb-3 space-y-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-900">
          {sourceWarnings.map((warning) => (
            <p key={warning}>{warning}</p>
          ))}
        </div>
      ) : null}

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        {lines.length > 0 ? (
          <dl className="space-y-1.5 text-sm">
            {lines.map(([key, val]) => (
              <div key={key} className="flex gap-2">
                <dt className="shrink-0 font-mono text-xs text-slate-400">{key}</dt>
                <dd className="min-w-0 break-words text-slate-800">{highlightQuote(val, quote)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="whitespace-pre-wrap text-sm leading-6 text-slate-800">
            {highlightQuote(textPreview, quote) || "원문 미리보기가 없습니다."}
          </p>
        )}
      </div>

      {/* AI 초안 / 원시값 — 기본 접힘 */}
      <div className="mt-4 space-y-2">
        <RawSection title="AI 초안 (raw)" empty="AI 초안이 아직 없습니다. 오른쪽에서 직접 입력하세요.">
          {detail.ai_proposal && Object.keys(detail.ai_proposal.proposal_json).length > 0
            ? JSON.stringify(detail.ai_proposal.proposal_json, null, 2)
            : null}
        </RawSection>
        <RawSection title="파싱된 원시 필드 (raw)">
          {JSON.stringify(detail.parsed_fields, null, 2)}
        </RawSection>
      </div>
    </div>
  );
}

function RawSection({
  title,
  empty,
  children,
}: {
  title: string;
  empty?: string;
  children: React.ReactNode;
}) {
  if (!children) {
    return empty ? (
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-400">{empty}</div>
    ) : null;
  }
  return (
    <details className="rounded-lg border border-slate-200 bg-slate-50">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-semibold text-slate-600">{title}</summary>
      <pre className="max-h-72 overflow-auto border-t border-slate-200 bg-slate-950 p-3 text-[11px] leading-5 text-slate-100">
        {children}
      </pre>
    </details>
  );
}

function warningList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

/** "a=1;b=2" 형태 시그널 문자열을 [key, value] 목록으로. 형태가 아니면 빈 배열. */
function splitSignals(text: string): [string, string][] {
  if (!text || !text.includes("=") || !text.includes(";")) return [];
  return text
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const idx = part.indexOf("=");
      return idx === -1 ? (["", part] as [string, string]) : ([part.slice(0, idx), part.slice(idx + 1)] as [string, string]);
    });
}

function highlightQuote(text: string, quote: string): React.ReactNode {
  if (!text) return "";
  if (!quote || !text.includes(quote)) return text;
  const [before, after] = text.split(quote, 2);
  return (
    <>
      {before}
      <mark className="bg-amber-200 px-1 text-slate-950">{quote}</mark>
      {after}
    </>
  );
}
