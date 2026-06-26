import type { TargetRepository, TargetSnapshot } from "@pacer/core";
import { ValidationError } from "@pacer/core";
import type { ExamType } from "@pacer/shared";
import { randomUUID } from "node:crypto";
import type { PrismaClient } from "@prisma/client";

/** §9.5 — 목표는 시험 시점(examType)별 1건 upsert(목표는 성적 따라 바뀐다). */
export class PrismaTargetRepository implements TargetRepository {
  private targetIdColumnState: Promise<TargetIdColumnState> | null = null;
  private warnedLegacyFallback = false;

  constructor(private readonly db: PrismaClient) {}

  async save(target: TargetSnapshot): Promise<void> {
    try {
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
          targetUniversityIds: target.targetUniversityIds,
          targetMajorGroups: target.targetMajorGroups,
          targetUnitIds: target.targetUnitIds,
          preferredRegions: target.preferredRegions,
          riskProfile: target.riskProfile,
          susiJungsiPreference: target.susiJungsiPreference,
        },
        update: {
          targetUniversities: target.targetUniversities,
          targetUniversityIds: target.targetUniversityIds,
          targetMajorGroups: target.targetMajorGroups,
          targetUnitIds: target.targetUnitIds,
          preferredRegions: target.preferredRegions,
          riskProfile: target.riskProfile,
          susiJungsiPreference: target.susiJungsiPreference,
        },
      });
    } catch (e) {
      if (!(await this.canUseLegacyFallback(e))) throw e;
      await this.saveLegacyTarget(target);
    }
  }

  async findLatest(
    cycleId: string,
    examType: ExamType,
  ): Promise<TargetSnapshot | null> {
    try {
      const row = await this.db.targetSnapshot.findUnique({
        where: { cycleId_examType: { cycleId, examType } },
      });
      if (!row) return null;
      return {
        cycleId: row.cycleId,
        examType: row.examType,
        targetUniversities: row.targetUniversities,
        targetUniversityIds: row.targetUniversityIds,
        targetMajorGroups: row.targetMajorGroups,
        targetUnitIds: row.targetUnitIds,
        preferredRegions: row.preferredRegions,
        riskProfile: row.riskProfile,
        susiJungsiPreference: row.susiJungsiPreference,
      };
    } catch (e) {
      if (!(await this.canUseLegacyFallback(e))) throw e;
      return this.findLatestLegacyTarget(cycleId, examType);
    }
  }

  private async canUseLegacyFallback(e: unknown): Promise<boolean> {
    if (!isTargetIdSchemaDrift(e)) return false;
    const state = await this.getTargetIdColumnState();
    return !state.targetUniversityIds && !state.targetUnitIds;
  }

  private getTargetIdColumnState(): Promise<TargetIdColumnState> {
    this.targetIdColumnState ??= this.readTargetIdColumnState();
    return this.targetIdColumnState;
  }

  private async readTargetIdColumnState(): Promise<TargetIdColumnState> {
    const rows = await this.db.$queryRaw<Array<{ column_name: string }>>`
      SELECT column_name
      FROM information_schema.columns
      WHERE table_schema = 'public'
        AND table_name = 'target_snapshots'
        AND column_name IN ('targetUniversityIds', 'targetUnitIds')
    `;
    const names = new Set(rows.map((row) => row.column_name));
    return {
      targetUniversityIds: names.has("targetUniversityIds"),
      targetUnitIds: names.has("targetUnitIds"),
    };
  }

  private async saveLegacyTarget(target: TargetSnapshot): Promise<void> {
    if (target.targetUniversityIds.length > 0 || target.targetUnitIds.length > 0) {
      throw new ValidationError(
        "ID 기반 목표 저장을 위해 DB 마이그레이션이 필요합니다",
      );
    }
    this.warnLegacyFallback();
    await this.db.$executeRaw`
      INSERT INTO "target_snapshots" (
        "id",
        "cycleId",
        "examType",
        "targetUniversities",
        "targetMajorGroups",
        "preferredRegions",
        "riskProfile",
        "susiJungsiPreference"
      )
      VALUES (
        ${randomUUID()},
        ${target.cycleId},
        ${target.examType}::"ExamType",
        ${target.targetUniversities}::TEXT[],
        ${target.targetMajorGroups}::TEXT[],
        ${target.preferredRegions}::TEXT[],
        ${target.riskProfile}::"RiskProfile",
        ${target.susiJungsiPreference}::"SusiJungsiPreference"
      )
      ON CONFLICT ("cycleId", "examType") DO UPDATE SET
        "targetUniversities" = EXCLUDED."targetUniversities",
        "targetMajorGroups" = EXCLUDED."targetMajorGroups",
        "preferredRegions" = EXCLUDED."preferredRegions",
        "riskProfile" = EXCLUDED."riskProfile",
        "susiJungsiPreference" = EXCLUDED."susiJungsiPreference"
    `;
  }

  private async findLatestLegacyTarget(
    cycleId: string,
    examType: ExamType,
  ): Promise<TargetSnapshot | null> {
    this.warnLegacyFallback();
    const rows = await this.db.$queryRaw<LegacyTargetSnapshotRow[]>`
      SELECT
        "cycleId",
        "examType",
        "targetUniversities",
        "targetMajorGroups",
        "preferredRegions",
        "riskProfile",
        "susiJungsiPreference"
      FROM "target_snapshots"
      WHERE "cycleId" = ${cycleId}
        AND "examType" = ${examType}::"ExamType"
      LIMIT 1
    `;
    const row = rows[0];
    if (!row) return null;
    return {
      cycleId: row.cycleId,
      examType: row.examType,
      targetUniversities: row.targetUniversities,
      targetUniversityIds: [],
      targetMajorGroups: row.targetMajorGroups,
      targetUnitIds: [],
      preferredRegions: row.preferredRegions,
      riskProfile: row.riskProfile,
      susiJungsiPreference: row.susiJungsiPreference,
    };
  }

  private warnLegacyFallback(): void {
    if (this.warnedLegacyFallback) return;
    this.warnedLegacyFallback = true;
    console.warn(
      "TargetSnapshot ID columns are missing; using legacy target fallback. Apply migration 20260626000000_target_snapshot_reference_ids.",
    );
  }
}

interface LegacyTargetSnapshotRow {
  cycleId: string;
  examType: TargetSnapshot["examType"];
  targetUniversities: string[];
  targetMajorGroups: string[];
  preferredRegions: string[];
  riskProfile: TargetSnapshot["riskProfile"];
  susiJungsiPreference: TargetSnapshot["susiJungsiPreference"];
}

interface TargetIdColumnState {
  targetUniversityIds: boolean;
  targetUnitIds: boolean;
}

function isTargetIdSchemaDrift(e: unknown): boolean {
  if (typeof e !== "object" || e === null) return false;
  const code = "code" in e ? (e as { code?: unknown }).code : undefined;
  if (code !== "P2022") return false;
  const message = "message" in e ? String((e as { message?: unknown }).message) : "";
  const meta =
    "meta" in e && typeof (e as { meta?: unknown }).meta === "object"
      ? JSON.stringify((e as { meta?: unknown }).meta)
      : "";
  return (
    message.includes("targetUniversityIds") ||
    message.includes("targetUnitIds") ||
    meta.includes("targetUniversityIds") ||
    meta.includes("targetUnitIds")
  );
}
