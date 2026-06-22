import { Disclaimer } from "@/components/Disclaimer";
import { LandingAnalytics, TrackedLandingCta } from "@/components/LandingAnalytics";
import { BAND_META, BAND_ORDER } from "@/lib/labels";

/** 랜딩 페이지 (§7.1). 카피는 §22 — 단정 금지, 해석 우선. SSR로 OG 프리뷰 확보. */
export default function LandingPage() {
  return (
    <main className="pb-8">
      <LandingAnalytics />

      {/* 히어로 */}
      <section className="pb-8 pt-10">
        <p className="text-xs font-semibold text-band-match-fg">
          6모 → 9모 → 수능, 한 사이클
        </p>
        <h1 className="mt-2 text-[26px] font-bold leading-snug text-slate-900">
          6모 성적, 지금
          <br />내 위치부터 확인하자
        </h1>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          전년도 입결 기준으로 구간(안정·적정·소신·도전·위험)을 해석해 드립니다.
          예측이 아니라 해석입니다.
        </p>

        {/* 3스텝 미리보기 — 진입 마찰 낮추기 */}
        <ol className="mt-5 flex items-center gap-2 text-[11px] font-medium text-slate-500">
          <StepPill n="1" label="성적 입력 1분" />
          <StepArrow />
          <StepPill n="2" label="분석 10초" />
          <StepArrow />
          <StepPill n="3" label="AI 리포트" />
        </ol>

        <TrackedLandingCta />
        <p className="mt-2 text-center text-[11px] text-slate-400">
          설치·로그인 없이 익명으로 바로 시작해요
        </p>
      </section>

      {/* 구간 미리보기 */}
      <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <p className="text-xs font-semibold text-slate-500">이렇게 보여드려요</p>
        <div className="mt-3 flex h-2.5 w-full overflow-hidden rounded-full">
          <div className="w-[15%] bg-band-stable" />
          <div className="w-[25%] bg-band-match" />
          <div className="w-[30%] bg-band-reach" />
          <div className="w-[20%] bg-band-challenge" />
          <div className="w-[10%] bg-band-risk" />
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {BAND_ORDER.map((band) => (
            <li key={band} className="flex items-center gap-1.5 text-xs text-slate-600">
              <span className={`size-2 rounded-full ${BAND_META[band].dot}`} />
              {BAND_META[band].label}
            </li>
          ))}
        </ul>
      </section>

      {/* 가치 카드 */}
      <section className="mt-4 space-y-3">
        <ValueCard
          title="단정하지 않습니다"
          description="합격 확률 대신 구간과 근거(reason)를 보여드립니다. 결과는 항상 참고용입니다."
        />
        <ValueCard
          title="근거를 설명합니다"
          description="왜 유리하고 불리한지 과목·반영비 관점에서 풀어 드립니다. 학부모용 쉬운 설명도 함께."
        />
        <ValueCard
          title="사이클로 추적합니다"
          description="한 번 입력하면 6모 → 9모 → 수능까지 같은 기준으로 변화를 따라갑니다."
        />
      </section>

      <Disclaimer />
    </main>
  );
}

function StepPill({ n, label }: { n: string; label: string }) {
  return (
    <li className="flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1.5">
      <span className="flex size-4 items-center justify-center rounded-full bg-slate-900 text-[10px] font-bold text-white">
        {n}
      </span>
      {label}
    </li>
  );
}

function StepArrow() {
  return <li className="text-slate-300">→</li>;
}

function ValueCard({ title, description }: { title: string; description: string }) {
  return (
    <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-bold text-slate-900">{title}</h2>
      <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
    </article>
  );
}
