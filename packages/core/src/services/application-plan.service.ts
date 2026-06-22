import type { PlanType } from "@pacer/shared";
import type { ApplicationPlanCombination } from "../domain/entities";
import { buildApplicationPlan } from "../engine";
import { NotFoundError, ValidationError } from "../errors";
import type {
  AnalysisRepository,
  ApplicationPlanRepository,
  CycleRepository,
} from "../ports";

/**
 * §7.10, §10.8 (P2) — 가/나/다군 조합 생성.
 *
 * 후보 unit_id 목록을 사이클의 최신 분석 스냅샷 결과와 대조해 엔진
 * (buildApplicationPlan)에 넘긴다 — 여기서 점수·구간을 다시 계산하지 않는다.
 * 분석되지 않은 후보(분석 불가·자격 미달 등)는 투명하게 제외 목록으로 남긴다(§8.2).
 *
 * 조합은 ApplicationPlan(§9.15)으로 저장된다. LLM 설명(application_plan_report)은
 * ReportService 경로로 별도 생성 — 엔진/LLM 분리(§8.1).
 */
export class ApplicationPlanService {
  constructor(
    private readonly cycles: CycleRepository,
    private readonly analyses: AnalysisRepository,
    private readonly plans: ApplicationPlanRepository,
  ) {}

  async create(
    cycleId: string,
    planType: PlanType,
    candidateUnitIds: string[],
  ): Promise<{
    planId: string;
    combination: ApplicationPlanCombination;
    /** 최신 분석에 없어 제외된 후보 — 숨기지 않는다(§8.2) */
    skippedUnitIds: string[];
  }> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);

    if (candidateUnitIds.length === 0) {
      throw new ValidationError("후보 모집단위가 최소 하나 필요합니다");
    }

    const snapshot = await this.analyses.findLatestSnapshotMeta(cycleId);
    if (!snapshot) {
      throw new ValidationError(
        "분석 이력이 없습니다 — 성적 분석을 먼저 실행해 주세요",
      );
    }
    const results = await this.analyses.findResults(snapshot.id);
    if (results === null) throw new NotFoundError(`snapshot ${snapshot.id}`);

    const wanted = new Set(candidateUnitIds);
    const candidates = results.filter((r) => wanted.has(r.unit.unitId));
    const foundIds = new Set(candidates.map((r) => r.unit.unitId));
    const skippedUnitIds = candidateUnitIds
      .filter((id) => !foundIds.has(id))
      .sort();

    if (candidates.length === 0) {
      throw new ValidationError(
        "선택한 후보가 최신 분석 결과에 없습니다 — 분석을 다시 실행하거나 후보를 확인해 주세요",
      );
    }

    const combination = buildApplicationPlan({
      strategy: planType,
      candidates,
    });

    const { planId } = await this.plans.save({
      cycleId,
      planType,
      gaUnitId: combination.picks.ga.unit?.unitId ?? null,
      naUnitId: combination.picks.na.unit?.unitId ?? null,
      daUnitId: combination.picks.da.unit?.unitId ?? null,
      combination: skippedUnitIds.length
        ? {
            ...combination,
            warnings: [
              ...combination.warnings,
              `최신 분석에 포함되지 않아 제외된 후보 ${skippedUnitIds.length}건이 있습니다`,
            ],
          }
        : combination,
    });

    return { planId, combination, skippedUnitIds };
  }
}
