import type {
  ApplicationPlanCombination,
  ApplicationPlanRepository,
} from "@pacer/core";
import type { PlanType } from "@pacer/shared";
import type { Prisma, PrismaClient } from "@prisma/client";

/** §9.15 — 원서 조합 저장. summary_json에 엔진 조합 전체를 보존한다(재현/감사). */
export class PrismaApplicationPlanRepository
  implements ApplicationPlanRepository
{
  constructor(private readonly db: PrismaClient) {}

  async save(input: {
    cycleId: string;
    planType: PlanType;
    gaUnitId: string | null;
    naUnitId: string | null;
    daUnitId: string | null;
    combination: ApplicationPlanCombination;
  }): Promise<{ planId: string }> {
    const row = await this.db.applicationPlan.create({
      data: {
        cycleId: input.cycleId,
        planType: input.planType,
        gaUnitId: input.gaUnitId,
        naUnitId: input.naUnitId,
        daUnitId: input.daUnitId,
        summaryJson: input.combination as unknown as Prisma.InputJsonValue,
      },
    });
    return { planId: row.id };
  }
}
