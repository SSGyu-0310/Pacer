import type { TargetRepository, TargetSnapshot } from "@pacer/core";
import type { ExamType } from "@pacer/shared";
import type { PrismaClient } from "@prisma/client";

/** §9.5 — 목표는 시험 시점(examType)별 1건 upsert(목표는 성적 따라 바뀐다). */
export class PrismaTargetRepository implements TargetRepository {
  constructor(private readonly db: PrismaClient) {}

  async save(target: TargetSnapshot): Promise<void> {
    await this.db.targetSnapshot.upsert({
      where: {
        cycleId_examType: {
          cycleId: target.cycleId,
          examType: target.examType,
        },
      },
      create: {
        cycleId: target.cycleId,
        examType: target.examType,
        targetUniversities: target.targetUniversities,
        targetMajorGroups: target.targetMajorGroups,
        preferredRegions: target.preferredRegions,
        riskProfile: target.riskProfile,
        susiJungsiPreference: target.susiJungsiPreference,
      },
      update: {
        targetUniversities: target.targetUniversities,
        targetMajorGroups: target.targetMajorGroups,
        preferredRegions: target.preferredRegions,
        riskProfile: target.riskProfile,
        susiJungsiPreference: target.susiJungsiPreference,
      },
    });
  }

  async findLatest(
    cycleId: string,
    examType: ExamType,
  ): Promise<TargetSnapshot | null> {
    const row = await this.db.targetSnapshot.findUnique({
      where: { cycleId_examType: { cycleId, examType } },
    });
    if (!row) return null;
    return {
      cycleId: row.cycleId,
      examType: row.examType,
      targetUniversities: row.targetUniversities,
      targetMajorGroups: row.targetMajorGroups,
      preferredRegions: row.preferredRegions,
      riskProfile: row.riskProfile,
      susiJungsiPreference: row.susiJungsiPreference,
    };
  }
}
