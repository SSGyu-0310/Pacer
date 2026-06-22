import type { ReportContent, ReportRepository, StrategyReport } from "@pacer/core";
import type { Prisma, PrismaClient } from "@prisma/client";
import { reportType } from "@pacer/shared";

/** §9.13 — 리포트 저장. model_name/prompt_version 필수(재현성). */
export class PrismaReportRepository implements ReportRepository {
  constructor(private readonly db: PrismaClient) {}

  async save(input: {
    cycleId: string;
    examScoreId: string;
    reportType: StrategyReport["reportType"];
    content: ReportContent;
    modelName: string;
    promptVersion: string;
  }): Promise<{ reportId: string }> {
    const row = await this.db.strategyReport.create({
      data: {
        cycleId: input.cycleId,
        examScoreId: input.examScoreId,
        reportType: reportType.parse(input.reportType),
        contentJson: input.content as unknown as Prisma.InputJsonValue,
        modelName: input.modelName,
        promptVersion: input.promptVersion,
      },
    });
    return { reportId: row.id };
  }

  async findById(reportId: string): Promise<StrategyReport | null> {
    const row = await this.db.strategyReport.findUnique({
      where: { id: reportId },
    });
    return row ? toDomain(row) : null;
  }

  async findLatestForCycle(cycleId: string): Promise<StrategyReport | null> {
    const row = await this.db.strategyReport.findFirst({
      where: { cycleId },
      orderBy: { createdAt: "desc" },
    });
    return row ? toDomain(row) : null;
  }
}

function toDomain(row: {
  id: string;
  cycleId: string;
  examScoreId: string;
  reportType: StrategyReport["reportType"];
  contentJson: Prisma.JsonValue;
  modelName: string;
  promptVersion: string;
  createdAt: Date;
}): StrategyReport {
  return {
    id: row.id,
    cycleId: row.cycleId,
    examScoreId: row.examScoreId,
    reportType: row.reportType,
    content: row.contentJson as unknown as ReportContent,
    modelName: row.modelName,
    promptVersion: row.promptVersion,
    createdAt: row.createdAt,
  };
}
