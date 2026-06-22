import type { RecruitmentGroup } from "@pacer/shared";
import type { AdmissionUnitRef } from "../domain/entities";

/**
 * 모집군 분류 (§18.1) — 가/나/다군별 그룹핑.
 * 원서 조합(P2 §7.10)의 기초가 되는 순수 헬퍼.
 */
export function groupByRecruitmentGroup<T extends { unit: AdmissionUnitRef }>(
  results: readonly T[],
): Record<RecruitmentGroup, T[]> {
  const groups: Record<RecruitmentGroup, T[]> = {
    ga: [],
    na: [],
    da: [],
    none: [],
  };
  for (const r of results) {
    groups[r.unit.recruitmentGroup].push(r);
  }
  return groups;
}
