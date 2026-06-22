import { AI_USAGE_NOTICE, DISCLAIMER } from "@pacer/shared";

/** 면책(§13.3) + AI 사용 고지(§13.4). 모든 결과 화면·리포트·PDF 하단에 노출. */
export function Disclaimer() {
  return (
    <footer className="mt-10 space-y-2 border-t border-slate-200 pt-4 text-xs leading-relaxed text-slate-500">
      <p>{DISCLAIMER}</p>
      <p>{AI_USAGE_NOTICE}</p>
    </footer>
  );
}
