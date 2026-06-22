import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { mapRule, prisma } from "@pacer/db";
import type { Prisma } from "@prisma/client";
import { z } from "zod";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_DECISIONS = path.resolve(__dirname, "../data/review/review-decisions.jsonl");
const DEFAULT_OUTPUT = path.resolve(__dirname, "../data/review/core-rule-db-audit-summary.json");

const decisionRow = z.object({
  id: z.string().uuid(),
  target_id: z.string().uuid(),
  reviewed_verified_status: z.enum(["draft", "parsed", "verified", "live", "deprecated"]).nullable(),
  reviewer: z.string(),
});

async function main() {
  const args = cliArgs();
  const decisionsPath = args[0] ? path.resolve(args[0]) : DEFAULT_DECISIONS;
  const outputPath = args[1] ? path.resolve(args[1]) : DEFAULT_OUTPUT;
  if (!existsSync(decisionsPath)) throw new Error(`missing decisions file: ${decisionsPath}`);

  const localCoreDecisions = await loadLocalCoreDecisionIds(decisionsPath);
  const activeDbCoreDecisions = await prisma.referenceReviewDecision.findMany({
    where: { reviewer: "agent:core-rule-fill", supersededAt: null },
    select: { id: true, targetId: true },
    orderBy: { id: "asc" },
  });
  const supersededCoreCount = await prisma.referenceReviewDecision.count({
    where: { reviewer: "agent:core-rule-fill", supersededAt: { not: null } },
  });
  const activeAllCount = await prisma.referenceReviewDecision.count({
    where: { supersededAt: null },
  });

  const localIds = new Set(localCoreDecisions.map((decision) => decision.id));
  const localByTargetId = new Map(
    localCoreDecisions.map((decision) => [decision.target_id, decision]),
  );
  const dbIds = new Set(activeDbCoreDecisions.map((decision) => decision.id));
  const missingInDb = [...localIds].filter((id) => !dbIds.has(id)).sort();
  const extraInDb = [...dbIds].filter((id) => !localIds.has(id)).sort();

  const targetIds = activeDbCoreDecisions.map((decision) => decision.targetId);
  const rules = await prisma.admissionRule.findMany({
    where: { id: { in: targetIds } },
    select: {
      id: true,
      unitId: true,
      scoreType: true,
      verifiedStatus: true,
      formulaJson: true,
      englishPolicyJson: true,
      historyPolicyJson: true,
      inquiryPolicyJson: true,
      eligibilityJson: true,
    },
  });
  const rulesById = new Map(rules.map((rule) => [rule.id, rule]));
  const missingRules = targetIds.filter((id) => !rulesById.has(id)).sort();
  const statusMismatchRules = rules
    .filter((rule) => {
      const expected = localByTargetId.get(rule.id)?.reviewed_verified_status;
      return expected !== null && expected !== undefined && rule.verifiedStatus !== expected;
    })
    .map((rule) => rule.id)
    .sort();
  const badFormulaRules = rules
    .filter((rule) => !validFormula(rule.formulaJson))
    .map((rule) => rule.id)
    .sort();
  const ratioRulesMissingWeight = rules
    .filter((rule) => ratioMissingWeight(rule.englishPolicyJson))
    .map((rule) => rule.id)
    .sort();
  const invalidInquiryRules = rules
    .filter((rule) => !validInquiry(rule.inquiryPolicyJson))
    .map((rule) => rule.id)
    .sort();
  const mapperNullRules = rules
    .filter((rule) => mapRule(rule) === null)
    .map((rule) => rule.id)
    .sort();

  const errors = [
    ...messageIf(missingInDb.length, `local decisions missing in DB: ${missingInDb.slice(0, 10)}`),
    ...messageIf(extraInDb.length, `extra active DB decisions: ${extraInDb.slice(0, 10)}`),
    ...messageIf(missingRules.length, `active decisions target missing rules: ${missingRules.slice(0, 10)}`),
    ...messageIf(statusMismatchRules.length, `active decision rules with status mismatch: ${statusMismatchRules.slice(0, 10)}`),
    ...messageIf(badFormulaRules.length, `active decision rules with invalid formula: ${badFormulaRules.slice(0, 10)}`),
    ...messageIf(ratioRulesMissingWeight.length, `ratio rules missing weight: ${ratioRulesMissingWeight.slice(0, 10)}`),
    ...messageIf(invalidInquiryRules.length, `active decision rules with invalid inquiry policy: ${invalidInquiryRules.slice(0, 10)}`),
    ...messageIf(mapperNullRules.length, `active decision rules rejected by mapRule: ${mapperNullRules.slice(0, 10)}`),
  ];

  const summary = {
    provider: "pacer-reference-data",
    artifactType: "core_rule_db_audit_summary",
    generatedAt: new Date().toISOString(),
    status: errors.length === 0 ? "ok" : "failed",
    errors,
    inputs: {
      decisions: repoRelative(decisionsPath),
    },
    counts: {
      localCoreRuleFillDecisions: localCoreDecisions.length,
      activeDbCoreRuleFillDecisions: activeDbCoreDecisions.length,
      supersededDbCoreRuleFillDecisions: supersededCoreCount,
      activeDbReviewDecisionsAllReviewers: activeAllCount,
      dbRulesCoveredByActiveDecisions: rules.length,
      localCoreRuleFillDecisionsByStatus: countLocalStatuses(localCoreDecisions),
      dbRulesCoveredByActiveDecisionsByStatus: countRuleStatuses(rules),
    },
    invariants: {
      localDecisionsMissingInDb: missingInDb.length,
      extraActiveDbDecisions: extraInDb.length,
      activeDecisionsTargetMissingRules: missingRules.length,
      activeDecisionRulesWithStatusMismatch: statusMismatchRules.length,
      activeDecisionRulesWithInvalidFormula: badFormulaRules.length,
      ratioRulesMissingWeight: ratioRulesMissingWeight.length,
      activeDecisionRulesWithInvalidInquiryPolicy: invalidInquiryRules.length,
      activeDecisionRulesRejectedByMapRule: mapperNullRules.length,
    },
  };

  await mkdir(path.dirname(outputPath), { recursive: true });
  await writeFile(outputPath, JSON.stringify(summary, null, 2) + "\n", "utf8");
  console.log(
    "core rule DB audit complete. " +
      `status=${summary.status} localDecisions=${localCoreDecisions.length} ` +
      `activeDb=${activeDbCoreDecisions.length} supersededDb=${supersededCoreCount}`,
  );
  if (errors.length) throw new Error(errors.join("; "));
}

async function loadLocalCoreDecisionIds(filePath: string) {
  const rows = (await readFile(filePath, "utf8"))
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const parsed = decisionRow.safeParse(JSON.parse(line));
      if (!parsed.success) throw new Error(`${filePath} line ${index + 1}: ${parsed.error.message}`);
      return parsed.data;
    });
  return rows.filter((row) => row.reviewer === "agent:core-rule-fill");
}

function validFormula(value: Prisma.JsonValue | null): boolean {
  if (!isRecord(value)) return false;
  const totalScale = value.totalScale;
  const weights = value.weights;
  const selectionPolicy = value.selectionPolicy;
  return (
    typeof totalScale === "number" &&
    totalScale > 0 &&
    isRecord(weights) &&
    nonNegativeNumber(weights.korean) &&
    nonNegativeNumber(weights.math) &&
    nonNegativeNumber(weights.inquiry) &&
    validSelectionPolicy(selectionPolicy)
  );
}

function validSelectionPolicy(value: unknown): boolean {
  if (value === undefined) return true;
  if (!isRecord(value)) return false;
  if (value.mode !== "best_n_subjects") return false;
  if (value.count !== 2 && value.count !== 3) return false;
  if (!Array.isArray(value.subjects)) return false;
  return (
    value.subjects.length >= 2 &&
    value.subjects.length <= 4 &&
    value.subjects.every((subject) =>
      ["korean", "math", "english", "inquiry"].includes(String(subject)),
    )
  );
}

function ratioMissingWeight(value: Prisma.JsonValue | null): boolean {
  if (!isRecord(value) || value.mode !== "ratio") return false;
  return !positiveNumber(value.weight);
}

function validInquiry(value: Prisma.JsonValue | null): boolean {
  if (!isRecord(value)) return false;
  return (value.count === 1 || value.count === 2) && (value.mode === "average" || value.mode === "best_one");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function positiveNumber(value: unknown): boolean {
  return typeof value === "number" && value > 0;
}

function nonNegativeNumber(value: unknown): boolean {
  return typeof value === "number" && value >= 0;
}

function countLocalStatuses(
  decisions: Array<z.infer<typeof decisionRow>>,
): Record<string, number> {
  return decisions.reduce<Record<string, number>>((counts, decision) => {
    const status = decision.reviewed_verified_status ?? "null";
    counts[status] = (counts[status] ?? 0) + 1;
    return counts;
  }, {});
}

function countRuleStatuses(
  rules: Array<{ verifiedStatus: string }>,
): Record<string, number> {
  return rules.reduce<Record<string, number>>((counts, rule) => {
    counts[rule.verifiedStatus] = (counts[rule.verifiedStatus] ?? 0) + 1;
    return counts;
  }, {});
}

function messageIf(count: number, message: string): string[] {
  return count > 0 ? [message] : [];
}

function repoRelative(filePath: string): string {
  const repoRoot = path.resolve(__dirname, "../../..");
  return path.relative(repoRoot, filePath);
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
