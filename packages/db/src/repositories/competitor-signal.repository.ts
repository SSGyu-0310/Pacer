import type {
  CompetitorSignal,
  CompetitorSignalInput,
  CompetitorSignalRepository,
} from "@pacer/core";
import type { ExamType } from "@pacer/shared";
import type { PrismaClient } from "@prisma/client";

/**
 * §9.14 — 외부 도구 결과. ★ 수동 입력 전용(§7.7.4): 이 저장소에 쓰는 경로는
 * 사용자 입력 API(§10.7)뿐이어야 한다. 자동 수집 잡을 연결하지 않는다.
 */
export class PrismaCompetitorSignalRepository
  implements CompetitorSignalRepository
{
  constructor(private readonly db: PrismaClient) {}

  async save(
    cycleId: string,
    input: CompetitorSignalInput,
  ): Promise<CompetitorSignal> {
    const row = await this.db.competitorSignal.create({
      data: {
        cycleId,
        examType: input.examType,
        provider: input.provider,
        unitId: input.unitId,
        valueType: input.valueType,
        value: input.value,
      },
    });
    return toDomain(row);
  }

  async list(cycleId: string, examType?: ExamType): Promise<CompetitorSignal[]> {
    const rows = await this.db.competitorSignal.findMany({
      where: { cycleId, ...(examType ? { examType } : {}) },
      orderBy: [{ createdAt: "asc" }, { id: "asc" }],
    });
    return rows.map(toDomain);
  }
}

function toDomain(row: {
  id: string;
  cycleId: string;
  examType: CompetitorSignal["examType"];
  provider: CompetitorSignal["provider"];
  unitId: string;
  valueType: CompetitorSignal["valueType"];
  value: string;
}): CompetitorSignal {
  return {
    id: row.id,
    cycleId: row.cycleId,
    examType: row.examType,
    provider: row.provider,
    unitId: row.unitId,
    valueType: row.valueType,
    value: row.value,
  };
}
