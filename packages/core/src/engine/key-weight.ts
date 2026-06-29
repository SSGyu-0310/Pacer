import type { AdmissionRuleData } from "../domain/entities";

/**
 * 핵심 반영 라벨 (docs/pacer_report_blueprint.md §3 "핵심 반영").
 * rule.weights(국·수·탐)와 영어 ratio 반영비를 백분율로 환산해
 * 비중이 큰 상위 과목을 "수학 40%·국어 30%" 형태로 요약한다.
 *
 * - 환산식 자체(원문)는 노출하지 않는다(§8.1). 반영비 요약만 보여준다.
 * - 합이 0이거나 의미 있는 반영비가 없으면 null(=화면에서 '반영비 검수중').
 */
export function formatKeyWeight(
  rule: AdmissionRuleData | null | undefined,
  maxSubjects = 2,
): string | null {
  if (!rule) return null;

  const englishRatioWeight =
    rule.englishPolicy?.mode === "ratio" ? (rule.englishPolicy.weight ?? 0) : 0;

  const entries: { label: string; weight: number }[] = [
    { label: "국어", weight: rule.weights.korean },
    { label: "수학", weight: rule.weights.math },
    { label: "탐구", weight: rule.weights.inquiry },
    { label: "영어", weight: englishRatioWeight },
  ];

  const total = entries.reduce((sum, e) => sum + (e.weight > 0 ? e.weight : 0), 0);
  if (total <= 0) return null;

  const ranked = entries
    .filter((e) => e.weight > 0)
    // 비중 내림차순, 동률은 표기 순서 고정(국→수→탐→영)으로 결정성 유지
    .sort((a, b) => b.weight - a.weight)
    .slice(0, Math.max(1, maxSubjects))
    .map((e) => `${e.label} ${Math.round((e.weight / total) * 100)}%`);

  return ranked.length > 0 ? ranked.join("·") : null;
}
