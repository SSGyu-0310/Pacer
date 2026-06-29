import type {
  AnalysisSnapshotMeta,
  AnalysisRepository,
  AnalysisSummary,
  UnitAnalysis,
} from "@pacer/core";
import type { Band, SnapshotType } from "@pacer/shared";
import { reasonCode } from "@pacer/shared";
import type { Prisma, PrismaClient } from "@prisma/client";

/** §9.10/§9.11 — 스냅샷 + 모집단위별 결과 저장/조회. */
export class PrismaAnalysisRepository implements AnalysisRepository {
  constructor(private readonly db: PrismaClient) {}

  async saveSnapshot(input: {
    cycleId: string;
    examScoreId: string;
    snapshotType: SnapshotType;
    summary: AnalysisSummary;
    bandDistribution: Record<Band, number>;
    results: UnitAnalysis[];
  }): Promise<{ snapshotId: string }> {
    const snapshot = await this.db.$transaction(async (tx) => {
      const created = await tx.analysisSnapshot.create({
        data: {
          cycleId: input.cycleId,
          examScoreId: input.examScoreId,
          snapshotType: input.snapshotType,
          summaryJson: input.summary as unknown as Prisma.InputJsonValue,
          bandDistributionJson:
            input.bandDistribution as unknown as Prisma.InputJsonValue,
        },
      });
      if (input.results.length > 0) {
        await tx.analysisResult.createMany({
          data: input.results.map((r) => ({
            analysisSnapshotId: created.id,
            unitId: r.unit.unitId,
            metricMode: r.metricMode,
            metricLabel: r.metricLabel,
            cutLabel: r.cutLabel,
            convertedScore: r.convertedScore,
            historicalReferenceScore: r.historicalReferenceScore,
            scoreGap: r.scoreGap,
            band: r.band,
            confidence: r.confidence,
            reasonCodes: r.reasonCodes,
            warnings: r.warnings,
          })),
        });
      }
      return created;
    });
    return { snapshotId: snapshot.id };
  }

  async findSnapshotMeta(
    snapshotId: string,
  ): Promise<AnalysisSnapshotMeta | null> {
    const row = await this.db.analysisSnapshot.findUnique({
      where: { id: snapshotId },
      select: {
        id: true,
        cycleId: true,
        examScoreId: true,
        snapshotType: true,
      },
    });
    return row;
  }

  /** 사이클 최신 스냅샷(타입 지정 가능) — 생성순 desc, 동시각은 id desc(결정성) */
  async findLatestSnapshotMeta(
    cycleId: string,
    snapshotType?: SnapshotType,
  ): Promise<AnalysisSnapshotMeta | null> {
    const row = await this.db.analysisSnapshot.findFirst({
      where: { cycleId, ...(snapshotType ? { snapshotType } : {}) },
      orderBy: [{ createdAt: "desc" }, { id: "desc" }],
      select: {
        id: true,
        cycleId: true,
        examScoreId: true,
        snapshotType: true,
      },
    });
    return row;
  }

  async findResults(snapshotId: string): Promise<UnitAnalysis[] | null> {
    const snapshot = await this.db.analysisSnapshot.findUnique({
      where: { id: snapshotId },
      include: {
        results: {
          include: { unit: { include: { university: true } } },
          orderBy: { scoreGap: "desc" },
        },
      },
    });
    if (!snapshot) return null;

    return snapshot.results.map((r) => ({
      unit: {
        unitId: r.unitId,
        university: r.unit.university.name,
        unitName: r.unit.name,
        recruitmentGroup: r.unit.recruitmentGroup,
      },
      convertedScore: r.convertedScore,
      historicalReferenceScore: r.historicalReferenceScore,
      metricMode: r.metricMode === "percentile" ? "percentile" : "converted",
      metricLabel: r.metricLabel,
      cutLabel: r.cutLabel,
      scoreGap: r.scoreGap ?? 0,
      band: r.band,
      confidence: r.confidence,
      // String[] 컬럼 → 컨트롤드 보캐블러리만 통과(임의 문자열 방어)
      reasonCodes: r.reasonCodes
        .map((c) => reasonCode.safeParse(c))
        .filter((p) => p.success)
        .map((p) => p.data),
      warnings: r.warnings
        .map((c) => reasonCode.safeParse(c))
        .filter((p) => p.success)
        .map((p) => p.data),
    }));
  }
}
