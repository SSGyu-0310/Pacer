import type {
  SavedUnit,
  SavedUnitInput,
  SavedUnitRepository,
} from "@pacer/core";
import type { PrismaClient } from "@prisma/client";

/** §9.12 — 관심 모집단위 저장. P0 내부 데모에서는 cycle 단위 저장만 지원한다. */
export class PrismaSavedUnitRepository implements SavedUnitRepository {
  constructor(private readonly db: PrismaClient) {}

  async save(input: SavedUnitInput): Promise<SavedUnit> {
    const row = await this.db.savedAdmissionUnit.upsert({
      where: {
        cycleId_unitId: { cycleId: input.cycleId, unitId: input.unitId },
      },
      create: {
        cycleId: input.cycleId,
        unitId: input.unitId,
        priority: input.priority ?? null,
        memo: input.memo ?? null,
      },
      update: {
        priority: input.priority ?? null,
        memo: input.memo ?? null,
      },
      include: { unit: { include: { university: true } } },
    });
    return toDomain(row);
  }

  async list(cycleId: string): Promise<SavedUnit[]> {
    const rows = await this.db.savedAdmissionUnit.findMany({
      where: { cycleId },
      include: { unit: { include: { university: true } } },
      orderBy: [{ priority: "asc" }, { savedAt: "desc" }],
    });
    return rows.map(toDomain);
  }
}

function toDomain(row: {
  id: string;
  cycleId: string;
  unitId: string;
  priority: number | null;
  memo: string | null;
  unit: {
    name: string;
    recruitmentGroup: SavedUnit["recruitmentGroup"];
    university: { name: string };
  };
}): SavedUnit {
  return {
    id: row.id,
    cycleId: row.cycleId,
    unitId: row.unitId,
    university: row.unit.university.name,
    unitName: row.unit.name,
    recruitmentGroup: row.unit.recruitmentGroup,
    priority: row.priority,
    memo: row.memo,
  };
}
