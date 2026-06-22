import type {
  FinalOutcome,
  FinalOutcomeInput,
  OutcomeRepository,
} from "@pacer/core";
import type { PrismaClient } from "@prisma/client";

/**
 * §9.16 — 합불 결과(데이터 해자). (cycleId, unitId) 재제출은 갱신으로 처리한다 —
 * 같은 모집단위의 모순된 결과가 데이터셋을 오염시키지 않게.
 */
export class PrismaOutcomeRepository implements OutcomeRepository {
  constructor(private readonly db: PrismaClient) {}

  async save(cycleId: string, input: FinalOutcomeInput): Promise<FinalOutcome> {
    const row = await this.db.$transaction(async (tx) => {
      const existing = await tx.finalOutcome.findFirst({
        where: { cycleId, unitId: input.unitId },
        orderBy: [{ createdAt: "desc" }, { id: "desc" }],
      });
      const data = {
        applied: input.applied,
        result: input.result,
        waitlistNumber: input.waitlistNumber ?? null,
        registered: input.registered ?? null,
        evidenceFileUrl: input.evidenceFileUrl ?? null,
      };
      if (existing) {
        return tx.finalOutcome.update({ where: { id: existing.id }, data });
      }
      return tx.finalOutcome.create({
        data: { cycleId, unitId: input.unitId, ...data },
      });
    });
    return toDomain(row);
  }

  async list(cycleId: string): Promise<FinalOutcome[]> {
    const rows = await this.db.finalOutcome.findMany({
      where: { cycleId },
      orderBy: [{ createdAt: "asc" }, { id: "asc" }],
    });
    return rows.map(toDomain);
  }
}

function toDomain(row: {
  id: string;
  cycleId: string;
  unitId: string;
  applied: boolean;
  result: FinalOutcome["result"];
  waitlistNumber: number | null;
  registered: boolean | null;
  evidenceFileUrl: string | null;
  rewardStatus: string | null;
}): FinalOutcome {
  return {
    id: row.id,
    cycleId: row.cycleId,
    unitId: row.unitId,
    applied: row.applied,
    result: row.result,
    waitlistNumber: row.waitlistNumber,
    registered: row.registered,
    evidenceFileUrl: row.evidenceFileUrl,
    rewardStatus: row.rewardStatus,
  };
}
