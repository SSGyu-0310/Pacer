import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  analyzeUnit,
  normalizeScores,
  type AnalysisCandidate,
  type ExamScore,
} from "@pacer/core";
import { PrismaUnitRepository, prisma } from "@pacer/db";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_OUTPUT = path.resolve(__dirname, "../data/review/core-rule-analysis-smoke-summary.json");

const syntheticScore: ExamScore = {
  id: "core-rule-analysis-smoke-score",
  cycleId: "core-rule-analysis-smoke-cycle",
  examType: "june_mock",
  scoreStatus: "official",
  scores: [
    { subject: "korean", standardScore: 131, percentile: 93 },
    { subject: "math", selection: "미적분", standardScore: 135, percentile: 96 },
    { subject: "english", grade: 2 },
    { subject: "history", grade: 3 },
    { subject: "inquiry1", selection: "물리학Ⅰ", standardScore: 67, percentile: 94 },
    { subject: "inquiry2", selection: "지구과학Ⅰ", standardScore: 65, percentile: 90 },
  ],
};

async function main() {
  const args = cliArgs();
  const outputPath = args[0] ? path.resolve(args[0]) : DEFAULT_OUTPUT;

  const activeDecisions = await prisma.referenceReviewDecision.findMany({
    where: { reviewer: "agent:core-rule-fill", supersededAt: null },
    select: { targetId: true },
  });
  const promotedRules = await prisma.admissionRule.findMany({
    where: { year: 2027, id: { in: activeDecisions.map((decision) => decision.targetId) } },
    select: {
      unitId: true,
      unit: { select: { university: { select: { name: true } } } },
    },
  });
  const promotedUnitIds = new Set(promotedRules.map((rule) => rule.unitId));
  const targetUniversities = [...new Set(promotedRules.map((rule) => rule.unit.university.name))].sort();

  const repository = new PrismaUnitRepository(prisma);
  const candidates = await repository.loadCandidates({
    admissionYear: 2027,
    track: "natural",
    targetUniversities,
  });
  const promotedCandidates = candidates.filter((candidate) =>
    promotedUnitIds.has(candidate.unit.unitId),
  );
  const normalized = normalizeScores(syntheticScore);
  const outcomes = promotedCandidates.map((candidate) => analyzePromoted(candidate, normalized));
  const syntheticHistoricalOutcomes = promotedCandidates.map((candidate) =>
    analyzePromoted(withSyntheticHistorical(candidate), normalized),
  );
  const unsupported = outcomes.filter((outcome) => outcome.kind === "unsupported");
  const ineligible = outcomes.filter((outcome) => outcome.kind === "ineligible");
  const insufficientData = outcomes.filter((outcome) => outcome.kind === "insufficientData");
  const ok = outcomes.filter((outcome) => outcome.kind === "ok");
  const suspiciousScale = ok.filter(hasSuspiciousHistoricalScale);
  const syntheticUnsupported = syntheticHistoricalOutcomes.filter(
    (outcome) => outcome.kind === "unsupported",
  );
  const syntheticOk = syntheticHistoricalOutcomes.filter((outcome) => outcome.kind === "ok");
  const syntheticSuspiciousScale = syntheticOk.filter(hasSuspiciousHistoricalScale);

  const errors = [
    ...messageIf(unsupported.length, `promoted candidates analyzed as unsupported: ${unsupported.slice(0, 10).map((o) => o.unitId)}`),
    ...messageIf(suspiciousScale.length, `promoted candidates have suspicious historical scale: ${suspiciousScale.slice(0, 10).map((o) => o.unitId)}`),
    ...messageIf(syntheticUnsupported.length, `promoted candidates with synthetic historical analyzed as unsupported: ${syntheticUnsupported.slice(0, 10).map((o) => o.unitId)}`),
    ...messageIf(syntheticSuspiciousScale.length, `promoted candidates with synthetic historical have suspicious scale: ${syntheticSuspiciousScale.slice(0, 10).map((o) => o.unitId)}`),
    ...messageIf(
      promotedCandidates.length - syntheticOk.length,
      `synthetic historical pass did not analyze every promoted candidate: ok=${syntheticOk.length} promoted=${promotedCandidates.length}`,
    ),
  ];

  const summary = {
    provider: "pacer-reference-data",
    artifactType: "core_rule_analysis_smoke_summary",
    generatedAt: new Date().toISOString(),
    status: errors.length === 0 ? "ok" : "failed",
    errors,
    syntheticScore: {
      examType: syntheticScore.examType,
      scoreStatus: syntheticScore.scoreStatus,
    },
    counts: {
      promotedRules: activeDecisions.length,
      promotedUnits: promotedUnitIds.size,
      promotedCandidates: promotedCandidates.length,
      ok: ok.length,
      ineligible: ineligible.length,
      insufficientData: insufficientData.length,
      unsupported: unsupported.length,
      suspiciousHistoricalScale: suspiciousScale.length,
      syntheticHistoricalOk: syntheticOk.length,
      syntheticHistoricalUnsupported: syntheticUnsupported.length,
      syntheticHistoricalSuspiciousScale: syntheticSuspiciousScale.length,
    },
    invariants: {
      promotedCandidatesUnsupported: unsupported.length,
      promotedCandidatesSuspiciousHistoricalScale: suspiciousScale.length,
      syntheticHistoricalPromotedCandidatesUnsupported: syntheticUnsupported.length,
      syntheticHistoricalPromotedCandidatesSuspiciousScale: syntheticSuspiciousScale.length,
      syntheticHistoricalPromotedCandidatesNotOk: promotedCandidates.length - syntheticOk.length,
    },
  };

  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, JSON.stringify(summary, null, 2) + "\n", "utf8");
  console.log(
    "core rule analysis smoke complete. " +
      `status=${summary.status} promotedCandidates=${promotedCandidates.length} ` +
      `ok=${ok.length} unsupported=${unsupported.length}`,
  );
  if (errors.length) throw new Error(errors.join("; "));
}

function analyzePromoted(
  candidate: AnalysisCandidate,
  normalized: ReturnType<typeof normalizeScores>,
) {
  const result = analyzeUnit(candidate, normalized, "june_mock");
  if (result.kind !== "ok") {
    return { kind: result.kind, unitId: candidate.unit.unitId };
  }
  return {
    kind: "ok" as const,
    unitId: candidate.unit.unitId,
    historicalReferenceScore: result.analysis.historicalReferenceScore,
    historicalReferenceScale: referenceScale(candidate),
  };
}

function withSyntheticHistorical(candidate: AnalysisCandidate): AnalysisCandidate {
  return {
    ...candidate,
    historical: {
      unitId: candidate.unit.unitId,
      year: 2026,
      cutScore: syntheticCutScore(candidate.rule?.totalScale ?? 1000),
      percentileCut: 70,
      competitionRate: 5,
      additionalPass: 10,
      confidence: "medium",
    },
  };
}

function syntheticCutScore(totalScale: number): number {
  return Math.max(1, totalScale * 0.7);
}

function referenceScale(candidate: AnalysisCandidate): number | null {
  if (!candidate.rule) return null;
  return candidate.rule.verifiedStatus === "verified" ||
    candidate.rule.verifiedStatus === "live"
    ? candidate.rule.totalScale
    : 100;
}

function hasSuspiciousHistoricalScale(outcome: {
  historicalReferenceScore?: number | null;
  historicalReferenceScale?: number | null;
}): boolean {
  const reference = outcome.historicalReferenceScore;
  const scale = outcome.historicalReferenceScale;
  if (
    reference === null ||
    reference === undefined ||
    scale === null ||
    scale === undefined ||
    !Number.isFinite(reference) ||
    !Number.isFinite(scale) ||
    scale <= 0
  ) {
    return true;
  }
  const ratio = reference / scale;
  return ratio < 0.2 || ratio > 1.2;
}

function messageIf(count: number, message: string): string[] {
  return count > 0 ? [message] : [];
}

function cliArgs(): string[] {
  const args = process.argv.slice(2);
  return args[0] === "--" ? args.slice(1) : args;
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
