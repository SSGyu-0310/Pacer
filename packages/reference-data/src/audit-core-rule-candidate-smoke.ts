import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PrismaUnitRepository, prisma } from "@pacer/db";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_OUTPUT = path.resolve(__dirname, "../data/review/core-rule-candidate-smoke-summary.json");

async function main() {
  const args = cliArgs();
  const outputPath = args[0] ? path.resolve(args[0]) : DEFAULT_OUTPUT;

  const promotedRules = await prisma.admissionRule.findMany({
    where: {
      year: 2027,
      id: {
        in: (
          await prisma.referenceReviewDecision.findMany({
            where: { reviewer: "agent:core-rule-fill", supersededAt: null },
            select: { targetId: true },
          })
        ).map((decision) => decision.targetId),
      },
    },
    select: {
      id: true,
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
  const candidateByUnit = new Map(candidates.map((candidate) => [candidate.unit.unitId, candidate]));
  const missingCandidates = [...promotedUnitIds].filter((unitId) => !candidateByUnit.has(unitId)).sort();
  const candidatesWithoutRule = [...promotedUnitIds]
    .filter((unitId) => candidateByUnit.get(unitId)?.rule == null)
    .sort();

  const errors = [
    ...messageIf(missingCandidates.length, `promoted units missing from loadCandidates: ${missingCandidates.slice(0, 10)}`),
    ...messageIf(candidatesWithoutRule.length, `promoted units loaded without rule: ${candidatesWithoutRule.slice(0, 10)}`),
  ];

  const summary = {
    provider: "pacer-reference-data",
    artifactType: "core_rule_candidate_smoke_summary",
    generatedAt: new Date().toISOString(),
    status: errors.length === 0 ? "ok" : "failed",
    errors,
    counts: {
      promotedRules: promotedRules.length,
      promotedUnits: promotedUnitIds.size,
      targetUniversities: targetUniversities.length,
      loadedCandidates: candidates.length,
    },
    invariants: {
      promotedUnitsMissingFromLoadCandidates: missingCandidates.length,
      promotedUnitsLoadedWithoutRule: candidatesWithoutRule.length,
    },
  };

  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, JSON.stringify(summary, null, 2) + "\n", "utf8");
  console.log(
    "core rule candidate smoke complete. " +
      `status=${summary.status} promotedRules=${promotedRules.length} ` +
      `loadedCandidates=${candidates.length}`,
  );
  if (errors.length) throw new Error(errors.join("; "));
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
