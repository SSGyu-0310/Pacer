import type {
  ExamScore,
  ScoreInput,
  ScoreRepository,
  SubjectScoreValue,
} from "@pacer/core";
import type { PrismaClient } from "@prisma/client";

/**
 * §9.3/§9.4 — 시험별 성적은 (cycleId, examType) 당 1건 upsert.
 * 재제출 시 과목 점수를 통째로 교체한다(부분 병합으로 인한 불일치 방지).
 */
export class PrismaScoreRepository implements ScoreRepository {
  constructor(private readonly db: PrismaClient) {}

  async save(cycleId: string, input: ScoreInput): Promise<ExamScore> {
    const row = await this.db.$transaction(async (tx) => {
      const examScore = await tx.examScore.upsert({
        where: {
          cycleId_examType: { cycleId, examType: input.examType },
        },
        create: {
          cycleId,
          examType: input.examType,
          scoreStatus: input.scoreStatus,
        },
        update: { scoreStatus: input.scoreStatus },
      });
      await tx.subjectScore.deleteMany({ where: { examScoreId: examScore.id } });
      await tx.subjectScore.createMany({
        data: input.scores.map((s) => ({
          examScoreId: examScore.id,
          subject: s.subject,
          selection: s.selection ?? null,
          rawScore: s.rawScore ?? null,
          standardScore: s.standardScore ?? null,
          percentile: s.percentile ?? null,
          grade: s.grade ?? null,
        })),
      });
      return tx.examScore.findUniqueOrThrow({
        where: { id: examScore.id },
        include: { subjectScores: true },
      });
    });
    return toDomain(row);
  }

  async findById(examScoreId: string): Promise<ExamScore | null> {
    const row = await this.db.examScore.findUnique({
      where: { id: examScoreId },
      include: { subjectScores: true },
    });
    return row ? toDomain(row) : null;
  }

  /** (cycleId, examType)당 1건(§9.3) — P1 trend의 이전 시험 로드용 */
  async findByExamType(
    cycleId: string,
    examType: ExamScore["examType"],
  ): Promise<ExamScore | null> {
    const row = await this.db.examScore.findUnique({
      where: { cycleId_examType: { cycleId, examType } },
      include: { subjectScores: true },
    });
    return row ? toDomain(row) : null;
  }
}

function toDomain(row: {
  id: string;
  cycleId: string;
  examType: ExamScore["examType"];
  scoreStatus: ExamScore["scoreStatus"];
  subjectScores: {
    subject: SubjectScoreValue["subject"];
    selection: string | null;
    rawScore: number | null;
    standardScore: number | null;
    percentile: number | null;
    grade: number | null;
  }[];
}): ExamScore {
  return {
    id: row.id,
    cycleId: row.cycleId,
    examType: row.examType,
    scoreStatus: row.scoreStatus,
    scores: row.subjectScores.map((s) => ({
      subject: s.subject,
      selection: s.selection ?? undefined,
      rawScore: s.rawScore ?? undefined,
      standardScore: s.standardScore ?? undefined,
      percentile: s.percentile ?? undefined,
      grade: s.grade ?? undefined,
    })),
  };
}
