import {
  BAND_META,
  BAND_ORDER,
  CONFIDENCE_META,
  type Band,
  type Confidence,
} from "@/lib/labels";
import { InfoIcon } from "@/components/icons";

export function BandBadge({ band }: { band: Band }) {
  const meta = BAND_META[band];
  return (
    <span
      className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${meta.badge}`}
    >
      {meta.label}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const meta = CONFIDENCE_META[confidence];
  return (
    <span
      title={meta.note}
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
        meta.muted ? "bg-slate-100 text-slate-500" : "bg-slate-900 text-white"
      }`}
    >
      {meta.label}
      {meta.note ? <InfoIcon className="size-3 opacity-70" /> : null}
    </span>
  );
}

/** 구간 분포 누적 바 + 범례 (개수 0인 구간도 라벨은 읽히게) */
export function BandDistributionBar({
  distribution,
}: {
  distribution: Record<Band, number>;
}) {
  const total = BAND_ORDER.reduce((sum, b) => sum + distribution[b], 0);

  return (
    <div className="space-y-3">
      <div
        className="flex h-2.5 w-full overflow-hidden rounded-full bg-slate-100"
        role="img"
        aria-label="구간 분포"
      >
        {total > 0
          ? BAND_ORDER.map((band) => {
              const count = distribution[band];
              if (count === 0) return null;
              return (
                <div
                  key={band}
                  className={BAND_META[band].bar}
                  style={{ width: `${(count / total) * 100}%` }}
                  aria-hidden="true"
                />
              );
            })
          : null}
      </div>

      <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
        {BAND_ORDER.map((band) => {
          const count = distribution[band];
          const dim = count === 0;
          return (
            <li key={band} className="flex items-center gap-1.5 text-xs text-slate-700">
              <span
                className={`size-2 rounded-full ${BAND_META[band].dot} ${dim ? "opacity-40" : ""}`}
              />
              <span className={dim ? "text-slate-400" : ""}>{BAND_META[band].label}</span>
              <span
                className={`font-medium tabular-nums ${dim ? "text-slate-400" : "text-slate-500"}`}
              >
                {count}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
