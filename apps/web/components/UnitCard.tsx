"use client";

import { useState } from "react";
import { BandBadge, ConfidenceBadge } from "@/components/BandParts";
import { AlertTriangleIcon, BookmarkIcon, CheckIcon } from "@/components/icons";
import {
  GROUP_LABEL,
  reasonLabel,
  type Band,
  type Confidence,
  type RecruitmentGroup,
} from "@/lib/labels";

export type AnalysisUnit = {
  unit_id: string;
  university: string;
  unit_name: string;
  recruitment_group: RecruitmentGroup;
  band: Band;
  confidence: Confidence;
  metric_mode?: "converted" | "percentile";
  metric_label?: string;
  cut_label?: string;
  my_value?: number | null;
  reference_value?: number | null;
  score_gap: number;
  reason_codes: string[];
  warnings: string[];
};

export function UnitCard({
  unit,
  saved,
  saving,
  onSave,
}: {
  unit: AnalysisUnit;
  saved: boolean;
  saving: boolean;
  onSave: () => void;
}) {
  const [showAllReasons, setShowAllReasons] = useState(false);

  const positive = unit.score_gap >= 0;
  const gapText = `${positive ? "+" : ""}${unit.score_gap.toFixed(1)}`;
  const visibleReasons = showAllReasons
    ? unit.reason_codes
    : unit.reason_codes.slice(0, 2);
  const hiddenCount = unit.reason_codes.length - visibleReasons.length;

  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      {/* 헤더: 모집군 + 대학/학과 + 구간 배지 */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="inline-flex items-center rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-600">
              {GROUP_LABEL[unit.recruitment_group]}
            </span>
            <h3 className="truncate text-[15px] font-semibold text-slate-900">
              {unit.university}
            </h3>
          </div>
          <p className="mt-0.5 truncate text-sm text-slate-500">{unit.unit_name}</p>
        </div>
        <BandBadge band={unit.band} />
      </div>

      {/* 점수차 + 신뢰도 */}
      <div className="mt-3 flex items-end justify-between gap-3 border-t border-slate-100 pt-3">
        <div>
          <p className="text-[11px] text-slate-500">
            {unit.cut_label ?? "전년도 컷"} 대비
          </p>
          <p
            className={`mt-0.5 text-lg font-bold tabular-nums ${
              positive ? "text-band-stable-fg" : "text-band-challenge-fg"
            }`}
          >
            {gapText}
            <span className="ml-0.5 text-xs font-normal text-slate-400">점</span>
          </p>
          {unit.my_value !== undefined &&
            unit.my_value !== null &&
            unit.reference_value !== undefined &&
            unit.reference_value !== null && (
              <p className="mt-0.5 text-[11px] text-slate-400">
                내 {unit.metric_label ?? "점수"} {unit.my_value.toFixed(1)} · 기준{" "}
                {unit.reference_value.toFixed(1)}
              </p>
            )}
        </div>
        <ConfidenceBadge confidence={unit.confidence} />
      </div>

      {/* reason codes + warnings */}
      {(unit.reason_codes.length > 0 || unit.warnings.length > 0) && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {visibleReasons.map((code) => (
            <span
              key={code}
              className="inline-flex items-center rounded-md bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-700"
            >
              {reasonLabel(code)}
            </span>
          ))}
          {(hiddenCount > 0 || (showAllReasons && unit.reason_codes.length > 2)) && (
            <button
              type="button"
              onClick={() => setShowAllReasons((v) => !v)}
              className="inline-flex items-center rounded-md px-2 py-1 text-[11px] font-medium text-slate-500 underline-offset-2 hover:underline"
            >
              {showAllReasons ? "접기" : `+${hiddenCount} 더보기`}
            </button>
          )}
          {unit.warnings.map((code) => (
            <span
              key={code}
              className="inline-flex items-center gap-1 rounded-md bg-warn-soft px-2 py-1 text-[11px] font-medium text-warn-fg"
            >
              <AlertTriangleIcon className="size-3" />
              {reasonLabel(code)}
            </span>
          ))}
        </div>
      )}

      {/* 관심 저장 */}
      <button
        type="button"
        onClick={onSave}
        disabled={saving || saved}
        className={`mt-3 flex h-9 w-full items-center justify-center gap-1.5 rounded-xl border text-xs font-semibold transition ${
          saved
            ? "border-band-stable-soft bg-band-stable-soft text-band-stable-fg"
            : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"
        } disabled:cursor-default`}
      >
        {saved ? (
          <>
            <CheckIcon className="size-3.5" /> 저장됨
          </>
        ) : (
          <>
            <BookmarkIcon className="size-3.5" />
            {saving ? "저장 중..." : "관심 모집단위 저장"}
          </>
        )}
      </button>
    </article>
  );
}
