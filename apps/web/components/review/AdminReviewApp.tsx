"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Toast } from "@/components/Toast";
import { KeyboardHints } from "./KeyboardHints";
import { OutcomeConfidenceControl } from "./OutcomeConfidenceControl";
import { ProposalFindings } from "./ProposalFindings";
import { ReviewProgressBar } from "./ReviewProgressBar";
import { ReviewSplitCard } from "./ReviewSplitCard";
import {
  RuleFieldEditor,
  emptyRuleEditorValue,
  ruleEditorValueFromDetail,
  ruleValueToCorrectedFields,
  ruleValueUnlocksExact,
  type RuleEditorValue,
} from "./RuleFieldEditor";

type Kind = "rule" | "outcome";
type Verdict = "confirm" | "edit" | "reject" | "flag" | "skip";
type Confidence = "limited" | "low" | "medium" | "high";
type Reviewer = "shin" | "kwon";
type CoreTier = "core" | "must" | "if_time" | "eng_special" | "med_health";

interface ReviewerCounts {
  shin: number;
  kwon: number;
  other: number;
  pending: number;
  total: number;
  decided: number;
}

interface QueueItem {
  kind: Kind;
  id: string;
  university_id: string | null;
  university_name: string | null;
  unit_name: string | null;
  year: number | null;
  verified_status: string | null;
  confidence: Confidence | null;
  review_priority_score: number | null;
  review_strength: string | null;
  has_ai_proposal: boolean;
  uncertain: boolean;
  latest_verdict: Verdict | null;
  latest_reviewer: string | null;
  source_url: string | null;
  text_preview: string | null;
  cluster_size: number;
  core_tier: CoreTier | null;
  core_flag: string | null;
}

interface LatestDecision {
  verdict?: Verdict;
  reviewer?: string;
  reviewed_at?: string;
  reviewed_confidence?: Confidence | null;
}

interface Detail {
  kind: Kind;
  id: string;
  university_name: string | null;
  unit_name: string | null;
  year: number | null;
  source_url: string | null;
  parsed_fields: Record<string, unknown>;
  evidence: Record<string, unknown> | null;
  ai_proposal: { proposal_json: Record<string, unknown> } | null;
  latest_decision: LatestDecision | null;
  would_unlock_exact: boolean | null;
  cluster_size: number;
}

interface QueueResponse {
  items: QueueItem[];
  counts: { total: number; pending: number; decided: number; reviewer_counts: ReviewerCounts };
}

export function AdminReviewApp() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [counts, setCounts] = useState({
    total: 0,
    pending: 0,
    decided: 0,
    reviewer_counts: emptyReviewerCounts(),
  });
  const [kind, setKind] = useState<Kind>("rule");
  const [reviewer, setReviewer] = useState<Reviewer | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [ruleValue, setRuleValue] = useState<RuleEditorValue>(emptyRuleEditorValue());
  const [toast, setToast] = useState<string | null>(null);
  const [queueLoading, setQueueLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const selected = items[selectedIndex] ?? null;
  const liveUnlock = selected?.kind === "rule" ? ruleValueUnlocksExact(ruleValue) : null;
  const hasProposal = Boolean(detail?.ai_proposal && Object.keys(proposalFields(detail)).length > 0);

  useEffect(() => {
    const stored = window.localStorage.getItem("pacer_admin_reviewer");
    if (stored === "shin" || stored === "kwon") setReviewer(stored);
  }, []);

  const loadQueue = useCallback(async () => {
    setQueueLoading(true);
    try {
      const res = await fetch(`/api/admin/review/queue?kind=${kind}`, { cache: "no-store" });
      if (!res.ok) throw new Error("queue load failed");
      const json = (await res.json()) as QueueResponse;
      setItems(json.items);
      setCounts(json.counts);
      setSelectedIndex((index) => Math.min(index, Math.max(0, json.items.length - 1)));
    } finally {
      setQueueLoading(false);
    }
  }, [kind]);

  const loadDetail = useCallback(async (item: QueueItem | null) => {
    if (!item) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    try {
      const res = await fetch(`/api/admin/review/item/${item.kind}/${item.id}`, { cache: "no-store" });
      if (!res.ok) {
        setDetail(null);
        return;
      }
      const json = (await res.json()) as Detail;
      setDetail(json);
      if (json.kind === "rule") {
        setRuleValue(ruleEditorValueFromDetail(json.parsed_fields, proposalFields(json)));
      }
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    loadQueue().catch(() => setToast("큐를 불러오지 못했습니다."));
  }, [loadQueue]);

  useEffect(() => {
    loadDetail(selected).catch(() => setToast("항목을 불러오지 못했습니다."));
  }, [selected, loadDetail]);

  const move = useCallback(
    (delta: number) => {
      setSelectedIndex((index) => Math.min(Math.max(index + delta, 0), Math.max(items.length - 1, 0)));
    },
    [items.length],
  );

  const record = useCallback(
    async (verdict: Verdict, extra: Record<string, unknown> = {}, advance = true) => {
      if (!selected || saving) return;
      if (!reviewer) {
        setToast("검수자를 먼저 선택하세요.");
        return;
      }
      setSaving(true);
      try {
        const res = await fetch("/api/admin/review/decision", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            target_kind: selected.kind,
            target_id: selected.id,
            verdict,
            evidence_checked: true,
            reviewer,
            ...extra,
          }),
        });
        const json = (await res.json().catch(() => ({}))) as {
          error?: string;
          message?: string;
          would_unlock_exact?: boolean;
          cluster_applied?: number;
        };
        if (!res.ok) {
          setToast(json.message ?? json.error ?? "저장에 실패했습니다.");
          return;
        }
        const applied = json.cluster_applied ?? 1;
        setToast(applied > 1 ? `${applied}개 모집단위에 일괄 저장했습니다.` : "저장했습니다.");
        await loadQueue();
        if (advance) move(1);
      } finally {
        setSaving(false);
      }
    },
    [selected, saving, reviewer, loadQueue, move],
  );

  // 규칙: 폼 값을 verified로 저장 (exact가 풀려야 통과).
  const saveRule = useCallback(() => {
    if (!selected || selected.kind !== "rule") return;
    if (!liveUnlock) {
      setToast("환산총점·가중치를 채워 'exact 풀림 ✓'을 만든 뒤 저장하세요.");
      return;
    }
    let correctedFields: Record<string, unknown>;
    try {
      correctedFields = ruleValueToCorrectedFields(ruleValue);
    } catch {
      setToast("지원 자격(JSON) 형식이 올바르지 않습니다.");
      return;
    }
    record("edit", { reviewed_verified_status: "verified", corrected_fields: correctedFields, apply_to_cluster: true });
  }, [liveUnlock, record, ruleValue, selected]);

  const confirmProposal = useCallback(() => {
    if (!detail || !selected || selected.kind !== "rule" || !hasProposal) return;
    record("confirm", {
      reviewed_verified_status: "verified",
      corrected_fields: proposalFields(detail),
      apply_to_cluster: true,
    });
  }, [detail, hasProposal, record, selected]);

  const setConfidence = useCallback(
    (value: Confidence) => record("edit", { reviewed_confidence: value }, false),
    [record],
  );

  const bulkConfirm = useCallback(async () => {
    if (!selected) return;
    if (!reviewer) {
      setToast("검수자를 먼저 선택하세요.");
      return;
    }
    const ids = items
      .filter((item) => item.kind === selected.kind && item.has_ai_proposal && !item.latest_verdict)
      .map((item) => item.id);
    if (ids.length === 0) {
      setToast("일괄 확정할 AI 초안 항목이 없습니다.");
      return;
    }
    if (!window.confirm(`${selected.kind} ${ids.length}건을 AI 초안대로 일괄 확정할까요?`)) return;
    const res = await fetch("/api/admin/review/bulk-confirm", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ kind: selected.kind, ids, reviewer }),
    });
    const json = (await res.json().catch(() => ({}))) as { recorded?: number; skipped?: number };
    if (!res.ok) {
      setToast("일괄 확정에 실패했습니다.");
      return;
    }
    setToast(`일괄 확정 ${json.recorded ?? 0}건, 스킵 ${json.skipped ?? 0}건`);
    await loadQueue();
  }, [items, loadQueue, reviewer, selected]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (
        event.target instanceof HTMLInputElement ||
        event.target instanceof HTMLTextAreaElement ||
        event.target instanceof HTMLSelectElement
      ) {
        return;
      }
      if (!selected) return;
      const key = event.key.toLowerCase();
      if (key === "j" || event.key === "ArrowDown") return run(event, () => move(1));
      if (key === "k" || event.key === "ArrowUp") return run(event, () => move(-1));
      if (event.key === "Enter") return run(event, selected.kind === "rule" ? saveRule : () => setConfidence("high"));
      if (key === "s") return run(event, () => record("skip"));
      if (key === "f") return run(event, () => record("flag"));
      if (key === "a") return run(event, () => void bulkConfirm());
      if (selected.kind === "outcome" && ["1", "2", "3", "4"].includes(event.key)) {
        const values: Confidence[] = ["limited", "low", "medium", "high"];
        const next = values[Number(event.key) - 1];
        if (next) return run(event, () => setConfidence(next));
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [bulkConfirm, move, record, saveRule, setConfidence, selected]);

  const header = useMemo(
    () => [detail?.university_name, detail?.unit_name, detail?.year].filter(Boolean).join(" · "),
    [detail],
  );
  const reviewerCounts = counts.reviewer_counts;
  const recentReview = detail?.latest_decision ? formatRecentReview(detail.latest_decision) : null;

  return (
    <main className="fixed inset-0 z-50 overflow-hidden bg-slate-100 text-slate-950">
      <div className="grid h-full grid-cols-[340px_minmax(0,1fr)]">
        <aside className="flex min-h-0 flex-col border-r border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-4">
            <div className="flex items-center justify-between">
              <h1 className="text-base font-semibold">Reference Review</h1>
              <span className="rounded bg-slate-900 px-2 py-1 text-xs font-semibold text-white">
                {counts.decided}/{counts.total}
              </span>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              전체 {reviewerCounts.decided}/{reviewerCounts.total} · 신 {reviewerCounts.shin} · 권{" "}
              {reviewerCounts.kwon} · 대기 {reviewerCounts.pending}
            </p>
            <ReviewProgressBar decided={counts.decided} total={counts.total} />
            <div className="mt-3">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">검수자</p>
              <div className="inline-flex overflow-hidden rounded border border-slate-300 text-xs font-semibold">
                {(["shin", "kwon"] as const).map((value) => (
                  <button
                    key={value}
                    onClick={() => {
                      setReviewer(value);
                      window.localStorage.setItem("pacer_admin_reviewer", value);
                    }}
                    className={`px-3 py-1.5 ${reviewer === value ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}
                  >
                    {reviewerLabel(value)}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-3 inline-flex overflow-hidden rounded border border-slate-300 text-xs font-semibold">
              {(["rule", "outcome"] as const).map((k) => (
                <button
                  key={k}
                  onClick={() => {
                    setKind(k);
                    setSelectedIndex(0);
                  }}
                  className={`px-3 py-1.5 ${kind === k ? "bg-cyan-500 text-white" : "bg-white text-slate-600"}`}
                >
                  {k === "rule" ? "규칙 (클러스터)" : "입결"}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {queueLoading ? (
              <p className="px-4 py-6 text-sm text-slate-500">큐를 불러오는 중…</p>
            ) : items.length === 0 ? (
              <p className="px-4 py-6 text-sm text-slate-500">검수할 항목이 없습니다.</p>
            ) : (
              items.map((item, index) => (
                <button
                  key={`${item.kind}:${item.id}`}
                  onClick={() => setSelectedIndex(index)}
                  className={`block w-full border-b border-slate-100 px-4 py-3 text-left text-sm ${
                    index === selectedIndex ? "bg-cyan-50" : "bg-white hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate font-medium">{item.university_name ?? "대학 미상"}</span>
                    <span
                      className={`rounded px-1.5 py-0.5 text-[11px] ${
                        item.kind === "rule" ? "bg-blue-100 text-blue-800" : "bg-emerald-100 text-emerald-800"
                      }`}
                    >
                      {item.kind === "rule" ? "규칙" : "입결"}
                    </span>
                  </div>
                  <p className="mt-1 truncate text-xs text-slate-600">
                    {item.unit_name ?? item.id}
                    {item.core_tier ? (
                      <span className={`ml-1 rounded px-1.5 py-0.5 font-semibold ${tierClass(item.core_tier)}`}>
                        {tierLabel(item.core_tier)}
                      </span>
                    ) : null}
                    {item.kind === "rule" && item.cluster_size > 1 ? (
                      <span className="ml-1 font-semibold text-cyan-700"> · {item.cluster_size}개 단위</span>
                    ) : null}
                  </p>
                  <div className="mt-2 flex items-center gap-1 text-[11px] text-slate-500">
                    {item.has_ai_proposal ? <span className="rounded bg-cyan-100 px-1.5 py-0.5 text-cyan-800">AI</span> : null}
                    {item.latest_verdict ? (
                      <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-800">검수완료</span>
                    ) : (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5">대기</span>
                    )}
                    {item.latest_verdict ? (
                      <span className={`rounded px-1.5 py-0.5 ${reviewerClass(item.latest_reviewer)}`}>
                        {reviewerLabel(item.latest_reviewer)}
                      </span>
                    ) : null}
                  </div>
                </button>
              ))
            )}
          </div>
        </aside>

        <section className="flex min-w-0 flex-col">
          <header className="flex min-h-16 items-center justify-between gap-3 border-b border-slate-200 bg-white px-5">
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{header || "검수 항목을 선택하세요"}</p>
              <p className="truncate text-xs text-slate-500">
                {selected?.kind === "rule"
                  ? detail && detail.cluster_size > 1
                    ? `전형 규칙 · 저장 시 ${detail.cluster_size}개 모집단위에 일괄 적용`
                    : "전형 규칙"
                  : selected?.kind === "outcome"
                    ? "입결 데이터"
                    : ""}
                {recentReview ? ` · 최근 검수: ${recentReview}` : ""}
              </p>
              {selected?.core_flag ? (
                <p className="mt-1 truncate text-xs font-semibold text-amber-700">{selected.core_flag}</p>
              ) : null}
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                onClick={() => record("flag")}
                disabled={!selected || saving || !reviewer}
                className="rounded border border-rose-200 px-3 py-2 text-xs font-semibold text-rose-700 disabled:opacity-40"
              >
                플래그 (F)
              </button>
              <button
                onClick={() => record("skip")}
                disabled={!selected || saving || !reviewer}
                className="rounded border border-slate-300 px-3 py-2 text-xs font-semibold text-slate-700 disabled:opacity-40"
              >
                스킵 (S)
              </button>
              {selected?.kind === "rule" && hasProposal ? (
                <button
                  onClick={confirmProposal}
                  disabled={saving || !reviewer}
                  className="rounded border border-cyan-300 px-3 py-2 text-xs font-semibold text-cyan-700 disabled:opacity-40"
                >
                  AI초안 확정
                </button>
              ) : null}
              {selected?.kind === "rule" ? (
                <button
                  onClick={saveRule}
                  disabled={saving || !liveUnlock || !reviewer}
                  title={!reviewer ? "검수자를 먼저 선택하세요" : liveUnlock ? "" : "환산총점·가중치를 채우면 저장할 수 있습니다"}
                  className="rounded bg-cyan-500 px-4 py-2 text-xs font-semibold text-white disabled:opacity-40"
                >
                  {saving ? "저장 중…" : "저장 (Enter)"}
                </button>
              ) : null}
            </div>
          </header>

          <div className="grid min-h-0 flex-1 grid-cols-[1fr_minmax(360px,460px)] gap-0 overflow-hidden">
            <ReviewSplitCard detail={detailLoading ? null : detail} />
            <aside className="overflow-y-auto border-l border-slate-200 bg-white p-4">
              {detail?.kind === "rule" ? (
                <>
                  <RuleFieldEditor value={ruleValue} onChange={setRuleValue} unlocksExact={Boolean(liveUnlock)} />
                  <div className="mt-4">
                    <ProposalFindings proposal={detail.ai_proposal?.proposal_json ?? null} />
                  </div>
                </>
              ) : null}
              {detail?.kind === "outcome" && selected ? (
                <>
                  <p className="text-sm font-semibold text-slate-800">입결 신뢰도 검수</p>
                  <p className="mt-1 text-xs text-slate-500">
                    원문과 대조해 confidence를 정합니다. 낮을수록 분석에서 보수적으로(적정 구간으로) 처리됩니다.
                  </p>
                  <OutcomeConfidenceControl value={currentConfidence(detail, selected)} onChange={setConfidence} />
                  <div className="mt-4">
                    <ProposalFindings proposal={detail.ai_proposal?.proposal_json ?? null} />
                  </div>
                </>
              ) : null}
              <div className="mt-6">
                <KeyboardHints />
              </div>
            </aside>
          </div>
        </section>
      </div>
      <Toast message={toast} onDismiss={() => setToast(null)} />
    </main>
  );
}

function run(event: KeyboardEvent, action: () => void) {
  event.preventDefault();
  action();
}

function proposalFields(detail: Detail): Record<string, unknown> {
  const proposed = detail.ai_proposal?.proposal_json.proposed;
  return typeof proposed === "object" && proposed !== null && !Array.isArray(proposed)
    ? (proposed as Record<string, unknown>)
    : {};
}

function currentConfidence(detail: Detail, selected: QueueItem): Confidence {
  const decided = detail.latest_decision?.reviewed_confidence;
  if (decided === "limited" || decided === "low" || decided === "medium" || decided === "high") return decided;
  return selected.confidence ?? "limited";
}

function emptyReviewerCounts(): ReviewerCounts {
  return { shin: 0, kwon: 0, other: 0, pending: 0, total: 0, decided: 0 };
}

function reviewerLabel(value: string | null | undefined): string {
  if (value === "shin") return "신";
  if (value === "kwon") return "권";
  return "기타";
}

function reviewerClass(value: string | null | undefined): string {
  if (value === "shin") return "bg-sky-100 text-sky-800";
  if (value === "kwon") return "bg-violet-100 text-violet-800";
  return "bg-slate-100 text-slate-600";
}

function tierLabel(value: CoreTier): string {
  return {
    core: "core",
    must: "must",
    if_time: "if_time",
    eng_special: "eng_special",
    med_health: "med_health",
  }[value];
}

function tierClass(value: CoreTier): string {
  return {
    core: "bg-slate-100 text-slate-600",
    must: "bg-rose-100 text-rose-800",
    if_time: "bg-amber-100 text-amber-800",
    eng_special: "bg-indigo-100 text-indigo-800",
    med_health: "bg-emerald-100 text-emerald-800",
  }[value];
}

function formatRecentReview(decision: LatestDecision): string {
  const reviewer = reviewerLabel(decision.reviewer);
  const verdict = decision.verdict ?? "unknown";
  const reviewedAt = typeof decision.reviewed_at === "string" ? decision.reviewed_at.slice(0, 10) : "";
  return [reviewer, verdict, reviewedAt].filter(Boolean).join(" · ");
}
