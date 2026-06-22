"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertSheet } from "@/components/AlertSheet";
import { BandDistributionBar } from "@/components/BandParts";
import { CtaBar } from "@/components/CtaBar";
import { Disclaimer } from "@/components/Disclaimer";
import { LoginSheet } from "@/components/LoginSheet";
import { ScoreBellCurve, type SubjectScoreView } from "@/components/ScoreBellCurve";
import { Toast } from "@/components/Toast";
import { UnitCard, type AnalysisUnit } from "@/components/UnitCard";
import { track } from "@/lib/analytics";
import {
  postJson,
  readStoredState,
  writeStoredState,
  type StoredState,
} from "@/lib/client";
import type { Band } from "@/lib/labels";

type AnalysisResponse = {
  snapshot_id: string;
  exam_type: string;
  track: string;
  subject_scores: SubjectScoreView[];
  results: AnalysisUnit[];
  disclaimer: string;
};

type ReportResponse = {
  report_id: string;
  content: unknown;
  model_name: string;
  prompt_version: string;
  disclaimer: string;
  ai_usage_notice: string;
};

export default function AnalysisPage() {
  const router = useRouter();
  const [stored, setStored] = useState<StoredState | null>(null);
  const [data, setData] = useState<AnalysisResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState<string | null>(null);
  const [alertOpen, setAlertOpen] = useState(false);
  const dismissNotice = useCallback(() => setNotice(null), []);

  useEffect(() => {
    const state = readStoredState();
    const snapshotId =
      new URLSearchParams(window.location.search).get("snapshotId") ??
      state?.snapshotId;
    if (!snapshotId) {
      setError("분석 스냅샷을 찾을 수 없습니다.");
      return;
    }
    // localStorage가 없어도(다른 탭/저장 삭제) URL의 snapshotId만으로 결과는 조회한다.
    // 저장·리포트 등 사이클 의존 동작은 stored가 있을 때만 활성화.
    if (state) {
      const next = { ...state, snapshotId };
      setStored(next);
      writeStoredState(next);
    }
    fetch(`/api/analysis/${snapshotId}/results`)
      .then(async (res) => {
        if (!res.ok) throw new Error(`결과 조회 실패(${res.status})`);
        return (await res.json()) as AnalysisResponse;
      })
      .then(setData)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "결과를 불러오지 못했습니다."),
      );
  }, []);

  const distribution = useMemo(() => {
    const base: Record<Band, number> = {
      stable: 0,
      match: 0,
      reach: 0,
      challenge: 0,
      risk: 0,
    };
    for (const r of data?.results ?? []) base[r.band]++;
    return base;
  }, [data]);

  async function saveUnit(unit: AnalysisUnit, priority: number) {
    if (!stored?.cycleId) {
      setNotice("이 브라우저에서 입력한 분석에서만 저장할 수 있어요.");
      return;
    }
    setBusy(`save:${unit.unit_id}`);
    setNotice(null);
    try {
      await postJson(`/api/cycles/${stored.cycleId}/saved-units`, {
        unit_id: unit.unit_id,
        priority,
      });
      setSaved((prev) => new Set(prev).add(unit.unit_id));
      setNotice(`${unit.university} ${unit.unit_name} 저장 완료`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "저장하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  async function generateReport() {
    if (!stored?.cycleId || !stored.examScoreId) {
      setNotice("이 브라우저에서 입력한 분석에서만 리포트를 만들 수 있어요.");
      return;
    }
    setBusy("report");
    setNotice(null);
    try {
      const report = await postJson<ReportResponse>(
        `/api/cycles/${stored.cycleId}/reports`,
        {
          exam_score_id: stored.examScoreId,
          report_type: "june_position_report",
          analysis_snapshot_id: stored.snapshotId,
        },
      );
      const next = { ...stored, reportId: report.report_id, report };
      writeStoredState(next);
      track("report_saved", { report_type: "june_position_report" });
      router.push(`/report?reportId=${report.report_id}`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "리포트를 생성하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  async function subscribe(channel: "email" | "kakao_alimtalk", value: string) {
    if (!stored?.cycleId || !value.trim()) {
      if (!stored?.cycleId)
        setNotice("이 브라우저에서 입력한 분석에서만 알림을 신청할 수 있어요.");
      return;
    }
    setBusy(`subscribe:${channel}`);
    setNotice(null);
    const body =
      channel === "email"
        ? { channel, address: value.trim(), events: ["september_mock_open" as const] }
        : { channel, phone: value.trim(), events: ["september_mock_open" as const] };
    try {
      await postJson(`/api/cycles/${stored.cycleId}/notifications/subscribe`, body);
      track("reminder_opt_in", { channel });
      setNotice("9모 알림 신청이 저장되었습니다.");
      setAlertOpen(false);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "알림 신청을 저장하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  async function subscribeWebPush() {
    if (!stored?.cycleId || !process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY) return;
    setBusy("subscribe:web_push");
    setNotice(null);
    try {
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(
          process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY,
        ),
      });
      await postJson(`/api/cycles/${stored.cycleId}/notifications/subscribe`, {
        channel: "web_push",
        subscription: subscription.toJSON(),
        platform_hint: platformHint(),
        events: ["september_mock_open" as const],
      });
      track("reminder_opt_in", { channel: "web_push" });
      setNotice("웹푸시 구독이 저장되었습니다.");
      setAlertOpen(false);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "웹푸시 구독을 저장하지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  async function share() {
    const shareData = {
      title: "Pacer 정시 전략",
      text: "6모부터 수능까지, 현재 위치를 이어서 확인합니다.",
      url: window.location.origin,
    };
    try {
      if (navigator.share) {
        await navigator.share(shareData);
      } else {
        await navigator.clipboard.writeText(shareData.url);
        setNotice("공유 링크를 복사했어요.");
      }
      track("share_card_created", { surface: "analysis" });
    } catch (e) {
      // 사용자가 공유 시트를 닫은 경우(AbortError)는 조용히 무시
      if (e instanceof DOMException && e.name === "AbortError") return;
      try {
        await navigator.clipboard.writeText(shareData.url);
        setNotice("공유 링크를 복사했어요.");
        track("share_card_created", { surface: "analysis" });
      } catch {
        setNotice("공유 링크를 준비하지 못했어요.");
      }
    }
  }

  const canWebPush =
    typeof window !== "undefined" &&
    "Notification" in window &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    Boolean(process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY);

  if (error) {
    return (
      <main className="space-y-6 py-10">
        <h1 className="text-xl font-bold text-slate-900">분석 결과</h1>
        <p className="rounded-xl bg-band-risk-soft p-3 text-sm text-band-risk-fg">
          {error}
        </p>
        <Link
          className="text-sm font-semibold text-slate-900 underline underline-offset-4"
          href="/score"
        >
          성적 다시 입력하기
        </Link>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="flex flex-col items-center gap-3 py-24 text-sm text-slate-500">
        <span className="size-6 animate-spin rounded-full border-2 border-slate-300 border-t-slate-900" />
        분석 결과를 불러오는 중입니다
      </main>
    );
  }

  const total = data.results.length;

  return (
    <main className="pb-4">
      {/* 헤더 */}
      <header className="space-y-1.5 pb-5 pt-2">
        <p className="text-xs font-medium text-slate-500">
          6월 모의평가 기준 · 참고용 분석
        </p>
        <h1 className="text-2xl font-bold leading-tight text-slate-900">
          내 위치를 정리했어요
        </h1>
      </header>

      {/* 전국 분포 위 내 위치 — 점수 입력 직후 가장 먼저 보이는 시각화 */}
      {data.subject_scores.length > 0 ? (
        <div className="mb-4">
          <ScoreBellCurve scores={data.subject_scores} track={data.track} />
        </div>
      ) : null}

      {/* 요약 카드 */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-bold text-slate-900">
          {total > 0 ? `${total}개 모집단위 분석 완료` : "분석 가능한 모집단위가 없습니다"}
        </h2>
        <p className="mt-1 text-xs leading-5 text-slate-500">
          {total > 0
            ? "전년도 입결 기준으로 구간을 나눴어요. 합격 여부가 아닌 상대적 위치 해석입니다."
            : "입력한 과목 조합이나 목표 조건으로는 P0 샘플 데이터에서 신뢰도 있는 비교가 어려워요."}
        </p>
        <div className="mt-4">
          <BandDistributionBar distribution={distribution} />
        </div>
      </section>

      {/* 모집단위 카드 리스트 */}
      {total > 0 ? (
        <section className="mt-4 space-y-3">
          {data.results.map((result, index) => (
            <UnitCard
              key={result.unit_id}
              unit={result}
              saved={saved.has(result.unit_id)}
              saving={busy === `save:${result.unit_id}`}
              onSave={() => saveUnit(result, index + 1)}
            />
          ))}
        </section>
      ) : (
        <section className="mt-4 rounded-xl border border-band-challenge-soft bg-band-challenge-soft/60 p-4">
          <h2 className="text-sm font-bold text-band-challenge-fg">분석 제한 안내</h2>
          <p className="mt-1 text-xs leading-5 text-slate-600">
            입력한 과목 조합·목표 조건과 비교할 수 있는 데이터가 부족했어요. 탐구
            2과목이 모두 입력되었는지, 목표 대학·지역 조건이 너무 좁지 않은지 확인해
            주세요.
          </p>
          <Link
            href="/score"
            className="mt-3 inline-flex text-xs font-semibold text-slate-900 underline underline-offset-4"
          >
            성적 다시 입력하기
          </Link>
        </section>
      )}

      <Disclaimer />
      <LoginSheet surface="analysis" />

      <div className="h-4" />
      <CtaBar
        busy={busy}
        reportDisabled={total === 0}
        onReport={generateReport}
        onAlert={() => setAlertOpen(true)}
        onShare={share}
      />

      <AlertSheet
        open={alertOpen}
        busy={busy}
        canWebPush={canWebPush}
        onClose={() => setAlertOpen(false)}
        onKakao={(phone) => subscribe("kakao_alimtalk", phone)}
        onEmail={(address) => subscribe("email", address)}
        onWebPush={subscribeWebPush}
      />

      <Toast message={notice} onDismiss={dismissNotice} />
    </main>
  );
}

function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4);
  const binary = atob((base64 + padding).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from([...binary].map((char) => char.charCodeAt(0)));
}

function platformHint(): "ios" | "android" | "desktop" {
  const ua = navigator.userAgent.toLowerCase();
  if (/iphone|ipad|ipod/.test(ua)) return "ios";
  if (/android/.test(ua)) return "android";
  return "desktop";
}
