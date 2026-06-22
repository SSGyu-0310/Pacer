import type { Cycle, CycleRepository } from "@pacer/core";
import type { PrismaClient } from "@prisma/client";

/**
 * Prisma ↔ 도메인 매핑은 여기(인프라)에만 존재한다.
 * 서비스/엔진은 Prisma 모델을 모른 채 도메인 Cycle 로만 일한다 (ORM 격리).
 * → 추후 백엔드 분리 시 이 계층만 교체하면 된다.
 */
export class PrismaCycleRepository implements CycleRepository {
  constructor(private readonly db: PrismaClient) {}

  async create(input: {
    userId: string | null;
    anonSessionId: string | null;
    admissionYear: number;
    gradeStatus: Cycle["gradeStatus"];
    track: Cycle["track"];
  }): Promise<Cycle> {
    const row = await this.db.admissionCycle.create({
      data: {
        userId: input.userId,
        anonSessionId: input.anonSessionId,
        admissionYear: input.admissionYear,
        gradeStatus: input.gradeStatus,
        track: input.track,
      },
    });
    return toDomain(row);
  }

  async findByAnonSessionAndYear(input: {
    anonSessionId: string;
    admissionYear: number;
  }): Promise<Cycle | null> {
    const row = await this.db.admissionCycle.findFirst({
      where: {
        anonSessionId: input.anonSessionId,
        admissionYear: input.admissionYear,
      },
    });
    return row ? toDomain(row) : null;
  }

  async updateProfile(
    id: string,
    input: { gradeStatus: Cycle["gradeStatus"]; track: Cycle["track"] },
  ): Promise<Cycle> {
    const row = await this.db.admissionCycle.update({
      where: { id },
      data: {
        gradeStatus: input.gradeStatus,
        track: input.track,
      },
    });
    return toDomain(row);
  }

  async findById(id: string): Promise<Cycle | null> {
    const row = await this.db.admissionCycle.findUnique({ where: { id } });
    return row ? toDomain(row) : null;
  }
}

function toDomain(row: {
  id: string;
  userId: string | null;
  anonSessionId: string | null;
  admissionYear: number;
  gradeStatus: Cycle["gradeStatus"];
  track: Cycle["track"];
}): Cycle {
  return {
    id: row.id,
    userId: row.userId,
    anonSessionId: row.anonSessionId,
    admissionYear: row.admissionYear,
    gradeStatus: row.gradeStatus,
    track: row.track,
  };
}
