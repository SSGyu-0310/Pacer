import type {
  AdmissionRuleData,
  AnalysisCandidate,
  Cycle,
  UnitRepository,
} from "@pacer/core";
import type { Confidence } from "@pacer/shared";
import type { PrismaClient } from "@prisma/client";
import { mapRule } from "./rule-mapping";

/**
 * §17.3-5 후보 모집단위 로드 — 해당 입시연도의 active 단위 + 최신 규칙 + 최신 입결.
 * ★ 규칙/입결 원문은 서버 전용 (§8.1). 도메인 형태로만 반환한다.
 *
 * 참고: prevQuota(전년 모집인원)는 전년도 AdmissionUnit 행 연결 데이터가 쌓이면
 * 채운다 — 지금은 null(보정요소 미적용)로 보수적으로 둔다.
 * track 필터는 majorGroup 분류 체계가 확정되면 추가한다.
 */
export class PrismaUnitRepository implements UnitRepository {
  constructor(private readonly db: PrismaClient) {}

  async loadCandidates(filter: {
    admissionYear: number;
    track: Cycle["track"];
    preferredRegions?: string[];
    targetUniversities?: string[];
  }): Promise<AnalysisCandidate[]> {
    const rows = await this.db.admissionUnit.findMany({
      where: {
        year: filter.admissionYear,
        active: true,
        university: {
          ...(filter.preferredRegions?.length
            ? { region: { in: filter.preferredRegions } }
            : {}),
          ...(filter.targetUniversities?.length
            ? { name: { in: filter.targetUniversities } }
            : {}),
        },
      },
      include: {
        university: true,
        rules: {
          where: { year: filter.admissionYear },
          orderBy: { updatedAt: "desc" },
          take: 1,
        },
        historicalOutcomes: { orderBy: { year: "desc" }, take: 1 },
      },
    });
    const fallbackHistorical = await this.fallbackHistoricalByName(
      rows.filter((row) => row.historicalOutcomes.length === 0),
      filter.admissionYear,
    );

    return rows.map((row): AnalysisCandidate => {
      const rule = mapRule(row.rules[0] ?? null);
      const directHistorical = row.historicalOutcomes[0];
      const historical =
        historicalCompatibleWithRule(rule, directHistorical)
          ? directHistorical
          : fallbackHistorical.get(row.id);
      return {
        unit: {
          unitId: row.id,
          university: row.university.name,
          unitName: row.name,
          recruitmentGroup: row.recruitmentGroup,
        },
        rule,
        historical: historical
          ? {
              unitId: row.id,
              year: historical.year,
              cutScore: historical.cutScore,
              percentileCut: historical.percentileCut,
              competitionRate: historical.competitionRate,
              additionalPass: historical.additionalPass,
              confidence: historical.confidence as Confidence,
            }
          : null,
        quota: row.quota,
        prevQuota: null,
      };
    });
  }

  private async fallbackHistoricalByName(
    rows: HistoricalFallbackRow[],
    admissionYear: number,
  ) {
    const output = new Map<
      string,
      {
        year: number;
        cutScore: number | null;
        percentileCut: number | null;
        competitionRate: number | null;
        additionalPass: number | null;
        confidence: Confidence;
      }
    >();
    if (rows.length === 0) return output;

    const universityIds = [...new Set(rows.map((row) => row.universityId))];
    const names = [...new Set(rows.map((row) => row.name))];
    const outcomes = await this.db.historicalOutcome.findMany({
      where: {
        year: { lt: admissionYear },
        OR: [{ cutScore: { not: null } }, { percentileCut: { not: null } }],
        unit: {
          universityId: { in: universityIds },
          name: { in: names },
        },
      },
      include: { unit: true },
      orderBy: [{ year: "desc" }],
    });

    const outcomesByUnitName = new Map<string, HistoricalOutcomeForFallback[]>();
    for (const outcome of outcomes) {
      const key = historicalFallbackKey(outcome.unit.universityId, outcome.unit.name);
      const current = outcomesByUnitName.get(key) ?? [];
      current.push(outcome);
      outcomesByUnitName.set(key, current);
    }

    for (const row of rows) {
      const rule = mapRule(row.rules[0] ?? null);
      const key = historicalFallbackKey(row.universityId, row.name);
      const matches = outcomesByUnitName.get(key) ?? [];
      const compatible = matches.find((outcome) =>
        historicalCompatibleWithRule(rule, outcome),
      );
      if (compatible) {
        output.set(row.id, toHistoricalRefLike(compatible));
      }
    }
    return output;
  }
}

interface RuleRowForMapping {
  unitId: string;
  scoreType: string;
  formulaJson: unknown;
  eligibilityJson: unknown;
  englishPolicyJson: unknown;
  historyPolicyJson: unknown;
  inquiryPolicyJson: unknown;
  verifiedStatus: string;
}

interface HistoricalFallbackRow {
  id: string;
  universityId: string;
  name: string;
  rules: RuleRowForMapping[];
}

interface HistoricalOutcomeForFallback {
  year: number;
  cutScore: number | null;
  percentileCut: number | null;
  competitionRate: number | null;
  additionalPass: number | null;
  confidence: Confidence;
  unit: { universityId: string; name: string };
}

function historicalCompatibleWithRule(
  rule: AdmissionRuleData | null,
  historical?: {
    cutScore: number | null;
    percentileCut: number | null;
  } | null,
): boolean {
  if (!rule || !historical) return false;

  const verified =
    rule.verifiedStatus === "verified" || rule.verifiedStatus === "live";
  if (!verified) {
    return isPercentileReference(historical.percentileCut);
  }

  return isScaleCompatible(historical.cutScore, rule.totalScale);
}

function isScaleCompatible(reference: number | null | undefined, scale: number): boolean {
  if (reference === null || reference === undefined || !Number.isFinite(reference)) {
    return false;
  }
  const ratio = reference / scale;
  return ratio >= 0.2 && ratio <= 1.2;
}

function isPercentileReference(reference: number | null | undefined): boolean {
  return (
    reference !== null &&
    reference !== undefined &&
    Number.isFinite(reference) &&
    reference >= 20 &&
    reference <= 100
  );
}

function toHistoricalRefLike(outcome: HistoricalOutcomeForFallback): {
  year: number;
  cutScore: number | null;
  percentileCut: number | null;
  competitionRate: number | null;
  additionalPass: number | null;
  confidence: Confidence;
} {
  return {
    year: outcome.year,
    cutScore: outcome.cutScore,
    percentileCut: outcome.percentileCut,
    competitionRate: outcome.competitionRate,
    additionalPass: outcome.additionalPass,
    confidence: outcome.confidence as Confidence,
  };
}

function historicalFallbackKey(universityId: string, unitName: string): string {
  return `${universityId}\u0000${unitName}`;
}
