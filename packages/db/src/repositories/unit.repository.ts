import type {
  AdmissionRuleData,
  AnalysisCandidate,
  Cycle,
  UnitRepository,
} from "@pacer/core";
import type { Confidence, ReviewVerdict, VerifiedStatus } from "@pacer/shared";
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
    const latestRuleDecisions = await this.latestRuleDecisions(rows);
    const fallbackHistorical = await this.fallbackHistoricalByName(
      rows.filter((row) => row.historicalOutcomes.length === 0),
      filter.admissionYear,
      latestRuleDecisions,
    );

    return rows.map((row): AnalysisCandidate => {
      const rawRule = row.rules[0] ?? null;
      const rule = mapRuleWithDecision(rawRule, latestRuleDecisions.get(rawRule?.id ?? ""));
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
    latestRuleDecisions: Map<string, RuleDecisionOverlay>,
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
      const rawRule = row.rules[0] ?? null;
      const rule = mapRuleWithDecision(rawRule, latestRuleDecisions.get(rawRule?.id ?? ""));
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

  private async latestRuleDecisions(
    rows: { rules: RuleRowForMapping[] }[],
  ): Promise<Map<string, RuleDecisionOverlay>> {
    const ruleIds = rows.flatMap((row) => row.rules.map((rule) => rule.id));
    if (ruleIds.length === 0) return new Map();

    const decisions = await this.db.referenceReviewDecision.findMany({
      where: {
        targetKind: "rule",
        targetId: { in: ruleIds },
        supersededAt: null,
        verdict: { in: ["edit", "confirm", "flag"] },
      },
      orderBy: { reviewedAt: "desc" },
    });

    const output = new Map<string, RuleDecisionOverlay>();
    for (const decision of decisions) {
      if (!output.has(decision.targetId)) {
        output.set(decision.targetId, decision);
      }
    }
    return output;
  }
}

interface RuleRowForMapping {
  id: string;
  unitId: string;
  scoreType: string;
  formulaJson: unknown;
  eligibilityJson: unknown;
  englishPolicyJson: unknown;
  historyPolicyJson: unknown;
  inquiryPolicyJson: unknown;
  verifiedStatus: string;
}

interface RuleDecisionOverlay {
  targetId: string;
  verdict: ReviewVerdict;
  reviewedVerifiedStatus: VerifiedStatus | null;
  correctedFields: unknown;
}

function mapRuleWithDecision(
  row: RuleRowForMapping | null | undefined,
  decision?: RuleDecisionOverlay,
): AdmissionRuleData | null {
  if (!row) return null;
  if (decision?.verdict === "flag") {
    return null;
  }
  const corrected = recordJson(decision?.correctedFields);
  if (!corrected) return mapRule(row);

  return mapRule({
    unitId: row.unitId,
    scoreType: stringField(corrected, "scoreType") ?? row.scoreType,
    formulaJson:
      jsonField(corrected, "formulaJson") ??
      formulaFromCorrected(corrected) ??
      row.formulaJson,
    eligibilityJson:
      jsonField(corrected, "eligibilityJson") ??
      jsonField(corrected, "eligibility") ??
      row.eligibilityJson,
    englishPolicyJson:
      jsonField(corrected, "englishPolicyJson") ??
      jsonField(corrected, "englishPolicy") ??
      row.englishPolicyJson,
    historyPolicyJson:
      jsonField(corrected, "historyPolicyJson") ??
      jsonField(corrected, "historyPolicy") ??
      row.historyPolicyJson,
    inquiryPolicyJson:
      jsonField(corrected, "inquiryPolicyJson") ??
      jsonField(corrected, "inquiryPolicy") ??
      row.inquiryPolicyJson,
    verifiedStatus: decision?.reviewedVerifiedStatus ?? row.verifiedStatus,
  });
}

function recordJson(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringField(record: Record<string, unknown>, key: string): string | null {
  const raw = record[key];
  return typeof raw === "string" ? raw : null;
}

function jsonField(record: Record<string, unknown>, key: string): unknown | null {
  return key in record ? record[key] : null;
}

function formulaFromCorrected(record: Record<string, unknown>): Record<string, unknown> | null {
  const totalScale = record.totalScale;
  const weights = record.weights;
  if (typeof totalScale !== "number" || !recordJson(weights)) return null;
  return { totalScale, weights };
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
