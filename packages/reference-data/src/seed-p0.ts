import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import crypto from "node:crypto";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { prisma } from "@pacer/db";
import {
  confidence,
  recruitmentGroup,
  reviewDecisionKind,
  reviewVerdict,
  scoreType,
  verifiedStatus,
} from "@pacer/shared";
import type { Prisma } from "@prisma/client";
import { z } from "zod";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_DIR = path.resolve(__dirname, "../data/p0");
const REVIEW_DIR = path.resolve(__dirname, "../data/review");
const uuid = z.string().uuid();
const bool = z
  .string()
  .transform((v) => v.trim().toLowerCase())
  .pipe(z.enum(["true", "false"]))
  .transform((v) => v === "true");
const optionalNumber = z
  .string()
  .transform((v) => (v.trim() === "" ? null : Number(v)))
  .pipe(z.number().nullable());
const nullableString = z
  .string()
  .transform((v) => (v.trim() === "" ? null : v.trim()));
const jsonValue = z.string().transform((v, ctx) => {
  try {
    return JSON.parse(v) as Prisma.InputJsonValue;
  } catch {
    ctx.addIssue({ code: "custom", message: "invalid JSON" });
    return z.NEVER;
  }
});
const optionalJsonValue = z
  .string()
  .optional()
  .transform((v, ctx) => {
    if (v === undefined || v.trim() === "") return null;
    try {
      return JSON.parse(v) as Prisma.InputJsonValue;
    } catch {
      ctx.addIssue({ code: "custom", message: "invalid JSON" });
      return z.NEVER;
    }
  });
const sourceRef = z.string().min(1);

const universityRow = z.object({
  id: uuid,
  name: z.string().min(1),
  campus: nullableString,
  region: z.string().min(1),
  type: nullableString,
  displayOrder: z.coerce.number().int(),
});

const unitRow = z.object({
  id: uuid,
  universityId: uuid,
  name: z.string().min(1),
  recruitmentGroup,
  majorGroup: nullableString,
  quota: optionalNumber,
  year: z.coerce.number().int(),
  active: bool,
});

const ruleRow = z.object({
  id: uuid,
  unitId: uuid,
  year: z.coerce.number().int(),
  scoreType,
  formulaJson: optionalJsonValue,
  totalScale: optionalNumber,
  koreanWeight: optionalNumber,
  mathWeight: optionalNumber,
  inquiryWeight: optionalNumber,
  englishPolicyJson: jsonValue,
  historyPolicyJson: jsonValue,
  inquiryPolicyJson: jsonValue,
  eligibilityJson: jsonValue,
  sourceUrl: sourceRef,
  verifiedStatus,
});

const outcomeRow = z.object({
  id: uuid,
  unitId: uuid,
  year: z.coerce.number().int(),
  avgScore: optionalNumber,
  cutScore: optionalNumber,
  percentileCut: optionalNumber,
  competitionRate: optionalNumber,
  additionalPass: optionalNumber.transform((v) => (v === null ? null : Math.trunc(v))),
  sourceUrl: sourceRef,
  confidence,
});

const ruleEvidenceRow = z.object({
  ruleId: uuid,
  unvCd: nullableString,
  universityName: nullableString,
  sourceUrl: nullableString,
  attachmentUrl: nullableString,
  textPreview: nullableString,
  detectedSignals: optionalJsonValue,
  percentageValues: optionalJsonValue,
  weightValues: optionalJsonValue,
  formulaSignals: optionalJsonValue,
  reviewPriorityScore: optionalNumber.transform((v) => (v === null ? null : Math.trunc(v))),
  reviewStrength: nullableString,
  rawPath: nullableString,
  sourcePath: nullableString,
});

const outcomeEvidenceRow = z.object({
  outcomeId: uuid,
  sourceUrl: nullableString,
  rawPath: nullableString,
  rowText: nullableString,
  metricValuesJson: optionalJsonValue,
});

const reviewDecisionJson = z.object({
  id: uuid.optional(),
  targetKind: reviewDecisionKind.optional(),
  target_kind: reviewDecisionKind.optional(),
  targetId: uuid.optional(),
  target_id: uuid.optional(),
  verdict: reviewVerdict,
  reviewedVerifiedStatus: verifiedStatus.nullable().optional(),
  reviewed_verified_status: verifiedStatus.nullable().optional(),
  reviewedConfidence: confidence.nullable().optional(),
  reviewed_confidence: confidence.nullable().optional(),
  correctedFields: z.record(z.string(), z.unknown()).nullable().optional(),
  corrected_fields: z.record(z.string(), z.unknown()).nullable().optional(),
  aiProposalSnapshot: z.record(z.string(), z.unknown()).nullable().optional(),
  ai_proposal_snapshot: z.record(z.string(), z.unknown()).nullable().optional(),
  evidenceChecked: z.boolean().optional(),
  evidence_checked: z.boolean().optional(),
  approvalScopeKey: z.string().nullable().optional(),
  approval_scope_key: z.string().nullable().optional(),
  reviewer: z.string().optional(),
  reviewNotes: z.string().nullable().optional(),
  review_notes: z.string().nullable().optional(),
  reviewedAt: z.string().optional(),
  reviewed_at: z.string().optional(),
});

type RuleRow = z.output<typeof ruleRow>;
type OutcomeRow = z.output<typeof outcomeRow>;
type ReviewDecision = {
  id: string;
  targetKind: "rule" | "outcome";
  targetId: string;
  verdict: "confirm" | "edit" | "reject" | "flag" | "skip";
  reviewedVerifiedStatus: z.infer<typeof verifiedStatus> | null;
  reviewedConfidence: z.infer<typeof confidence> | null;
  correctedFields: Record<string, unknown> | null;
  aiProposalSnapshot: Record<string, unknown> | null;
  evidenceChecked: boolean;
  approvalScopeKey: string | null;
  reviewer: string;
  reviewNotes: string | null;
  reviewedAt: Date;
};

async function main() {
  const args = cliArgs();
  const dryRun = args.includes("--dry-run");
  const dataDirArg = args.find((arg) => arg !== "--dry-run");
  const dataDir = dataDirArg
    ? resolveDataDir(dataDirArg)
    : DEFAULT_DIR;

  const universities = await loadCsv(
    path.join(dataDir, "universities.csv"),
    universityRow,
  );
  const units = await loadCsv(path.join(dataDir, "admission_units.csv"), unitRow);
  const rules = await loadCsv(path.join(dataDir, "admission_rules.csv"), ruleRow);
  const outcomes = await loadCsv(
    path.join(dataDir, "historical_outcomes.csv"),
    outcomeRow,
  );
  const ruleEvidence = await loadOptionalCsv(
    path.join(dataDir, "rule_evidence.csv"),
    ruleEvidenceRow,
  );
  const outcomeEvidence = await loadOptionalCsv(
    path.join(dataDir, "outcome_evidence.csv"),
    outcomeEvidenceRow,
  );
  const decisions = await loadReviewDecisions(path.join(REVIEW_DIR, "review-decisions.jsonl"));
  const activeDecisions = latestEffectiveDecisions(decisions);

  if (dryRun) {
    console.log(
      [
        "P0 reference seed dry-run complete.",
        `universities=${universities.length}`,
        `units=${units.length}`,
        `rules=${rules.length}`,
        `historical_outcomes=${outcomes.length}`,
        `rule_evidence=${ruleEvidence.length}`,
        `outcome_evidence=${outcomeEvidence.length}`,
        `review_decisions=${decisions.length}`,
      ].join(" "),
    );
    return;
  }

  const tx = prisma;
  await processRows("universities", universities, async (u) => {
    await tx.university.upsert({
      where: { id: u.id },
      create: u,
      update: {
        name: u.name,
        campus: u.campus,
        region: u.region,
        type: u.type,
        displayOrder: u.displayOrder,
      },
    });
  });

  await processRows("admission_units", units, async (unit) => {
    await tx.admissionUnit.upsert({
      where: { id: unit.id },
      create: unit,
      update: {
        universityId: unit.universityId,
        name: unit.name,
        recruitmentGroup: unit.recruitmentGroup,
        majorGroup: unit.majorGroup,
        quota: unit.quota,
        year: unit.year,
        active: unit.active,
      },
    });
  });

  await processRows("admission_rules", rules, async (r) => {
    const decision = activeDecisions.get(r.id);
    const reviewed = applyRuleDecision(r, decision);
    await tx.admissionRule.upsert({
      where: { id: r.id },
      create: {
        id: r.id,
        unitId: r.unitId,
        year: r.year,
        scoreType: reviewed.scoreType,
        formulaJson: reviewed.formulaJson,
        englishPolicyJson: reviewed.englishPolicyJson,
        historyPolicyJson: reviewed.historyPolicyJson,
        inquiryPolicyJson: reviewed.inquiryPolicyJson,
        eligibilityJson: reviewed.eligibilityJson,
        sourceUrl: r.sourceUrl,
        verifiedStatus: reviewed.verifiedStatus,
      },
      update: {
        year: r.year,
        scoreType: reviewed.scoreType,
        formulaJson: reviewed.formulaJson,
        englishPolicyJson: reviewed.englishPolicyJson,
        historyPolicyJson: reviewed.historyPolicyJson,
        inquiryPolicyJson: reviewed.inquiryPolicyJson,
        eligibilityJson: reviewed.eligibilityJson,
        sourceUrl: r.sourceUrl,
        verifiedStatus: reviewed.verifiedStatus,
      },
    });
  });

  await processRows("historical_outcomes", outcomes, async (o) => {
    const decision = activeDecisions.get(o.id);
    const reviewedConfidence =
      decision?.targetKind === "outcome" && decision.reviewedConfidence
        ? decision.reviewedConfidence
        : o.confidence;
    await tx.historicalOutcome.upsert({
      where: { id: o.id },
      create: { ...o, confidence: reviewedConfidence },
      update: {
        unitId: o.unitId,
        year: o.year,
        avgScore: o.avgScore,
        cutScore: o.cutScore,
        percentileCut: o.percentileCut,
        competitionRate: o.competitionRate,
        additionalPass: o.additionalPass,
        sourceUrl: o.sourceUrl,
        confidence: reviewedConfidence,
      },
    });
  });

  await processRows("rule_evidence", ruleEvidence, async (evidence) => {
    await tx.ruleEvidence.upsert({
      where: { ruleId: evidence.ruleId },
      create: ruleEvidenceInput(evidence),
      update: {
        unvCd: evidence.unvCd,
        universityName: evidence.universityName,
        sourceUrl: evidence.sourceUrl,
        attachmentUrl: evidence.attachmentUrl,
        textPreview: evidence.textPreview,
        detectedSignals: jsonInput(evidence.detectedSignals),
        percentageValues: jsonInput(evidence.percentageValues),
        weightValues: jsonInput(evidence.weightValues),
        formulaSignals: jsonInput(evidence.formulaSignals),
        reviewPriorityScore: evidence.reviewPriorityScore,
        reviewStrength: evidence.reviewStrength,
        rawPath: evidence.rawPath,
        sourcePath: evidence.sourcePath,
      },
    });
  });

  await processRows("outcome_evidence", outcomeEvidence, async (evidence) => {
    await tx.outcomeEvidence.upsert({
      where: { outcomeId: evidence.outcomeId },
      create: outcomeEvidenceInput(evidence),
      update: {
        sourceUrl: evidence.sourceUrl,
        rawPath: evidence.rawPath,
        rowText: evidence.rowText,
        metricValuesJson: jsonInput(evidence.metricValuesJson),
      },
    });
  });

  await processRows("review_decisions", decisions, async (decision) => {
    await tx.referenceReviewDecision.upsert({
      where: { id: decision.id },
      create: {
        id: decision.id,
        targetKind: decision.targetKind,
        targetId: decision.targetId,
        verdict: decision.verdict,
        reviewedVerifiedStatus: decision.reviewedVerifiedStatus,
        reviewedConfidence: decision.reviewedConfidence,
        correctedFields: jsonInput(decision.correctedFields),
        aiProposalSnapshot: jsonInput(decision.aiProposalSnapshot),
        evidenceChecked: decision.evidenceChecked,
        approvalScopeKey: decision.approvalScopeKey,
        reviewer: decision.reviewer,
        reviewNotes: decision.reviewNotes,
        reviewedAt: decision.reviewedAt,
      },
      update: {
        targetKind: decision.targetKind,
        targetId: decision.targetId,
        verdict: decision.verdict,
        reviewedVerifiedStatus: decision.reviewedVerifiedStatus,
        reviewedConfidence: decision.reviewedConfidence,
        correctedFields: jsonInput(decision.correctedFields),
        aiProposalSnapshot: jsonInput(decision.aiProposalSnapshot),
        evidenceChecked: decision.evidenceChecked,
        approvalScopeKey: decision.approvalScopeKey,
        reviewer: decision.reviewer,
        reviewNotes: decision.reviewNotes,
        reviewedAt: decision.reviewedAt,
        supersededAt: null,
      },
    });
  });
  const activeCoreRuleFillDecisionIds = decisions
    .filter((decision) => decision.reviewer === "agent:core-rule-fill")
    .map((decision) => decision.id);
  if (activeCoreRuleFillDecisionIds.length > 0) {
    await tx.referenceReviewDecision.updateMany({
      where: {
        reviewer: "agent:core-rule-fill",
        id: { notIn: activeCoreRuleFillDecisionIds },
        supersededAt: null,
      },
      data: { supersededAt: new Date() },
    });
  }
  console.log(
    [
      "P0 reference seed complete.",
      `universities=${universities.length}`,
      `units=${units.length}`,
      `rules=${rules.length}`,
      `historical_outcomes=${outcomes.length}`,
      `rule_evidence=${ruleEvidence.length}`,
      `outcome_evidence=${outcomeEvidence.length}`,
      `review_decisions=${decisions.length}`,
      "NOTICE: verify source status before exposing parsed reference rows as live admissions data.",
    ].join(" "),
  );
}

function cliArgs(): string[] {
  const args = process.argv.slice(2);
  return args[0] === "--" ? args.slice(1) : args;
}

function resolveDataDir(value: string): string {
  if (path.isAbsolute(value)) return value;
  const cwdRelative = path.resolve(value);
  if (existsSync(cwdRelative)) return cwdRelative;
  const repoRelative = path.resolve(__dirname, "../../..", value);
  if (existsSync(repoRelative)) return repoRelative;
  return cwdRelative;
}

async function processRows<T>(
  label: string,
  rows: T[],
  worker: (row: T) => Promise<void>,
): Promise<void> {
  const concurrency = Number(process.env.SEED_CONCURRENCY ?? "8");
  let nextIndex = 0;
  let completed = 0;
  const startedAt = Date.now();

  async function runWorker() {
    while (true) {
      const index = nextIndex;
      nextIndex += 1;
      const row = rows[index];
      if (row === undefined) return;
      await worker(row);
      completed += 1;
      if (completed % 1000 === 0 || completed === rows.length) {
        const elapsedSec = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
        console.log(`${label}: ${completed}/${rows.length} (${elapsedSec}s)`);
      }
    }
  }

  await Promise.all(
    Array.from({ length: Math.min(concurrency, rows.length) }, () => runWorker()),
  );
}

function ruleFormulaJson(row: RuleRow): Prisma.InputJsonValue {
  if (row.formulaJson !== null) return row.formulaJson;
  return {
    totalScale: row.totalScale,
    weights: {
      korean: row.koreanWeight,
      math: row.mathWeight,
      inquiry: row.inquiryWeight,
    },
  };
}

function applyRuleDecision(row: RuleRow, decision: ReviewDecision | undefined) {
  const corrected =
    decision?.targetKind === "rule" &&
    (decision.verdict === "confirm" || decision.verdict === "edit")
      ? decision.correctedFields
      : null;

  return {
    scoreType: readCorrectedScoreType(corrected) ?? row.scoreType,
    formulaJson: readCorrectedFormula(corrected) ?? ruleFormulaJson(row),
    englishPolicyJson:
      jsonInput(readCorrected(corrected, "englishPolicyJson", "englishPolicy")) ??
      row.englishPolicyJson,
    historyPolicyJson:
      jsonInput(readCorrected(corrected, "historyPolicyJson", "historyPolicy")) ??
      row.historyPolicyJson,
    inquiryPolicyJson:
      jsonInput(readCorrected(corrected, "inquiryPolicyJson", "inquiryPolicy")) ??
      row.inquiryPolicyJson,
    eligibilityJson:
      jsonInput(readCorrected(corrected, "eligibilityJson", "eligibility")) ??
      row.eligibilityJson,
    verifiedStatus:
      decision?.targetKind === "rule" && decision.reviewedVerifiedStatus
        ? decision.reviewedVerifiedStatus
        : row.verifiedStatus,
  };
}

function readCorrectedScoreType(
  corrected: Record<string, unknown> | null,
): z.infer<typeof scoreType> | null {
  const raw = readCorrected(corrected, "scoreType", "score_type");
  const parsed = scoreType.safeParse(raw);
  return parsed.success ? parsed.data : null;
}

function readCorrectedFormula(
  corrected: Record<string, unknown> | null,
): Prisma.InputJsonValue | null {
  const explicit = jsonInput(readCorrected(corrected, "formulaJson", "formula_json"));
  if (explicit) return explicit;
  const totalScale = readCorrected(corrected, "totalScale", "total_scale");
  const weights = readCorrected(corrected, "weights");
  if (typeof totalScale !== "number" || !isPlainRecord(weights)) return null;
  return { totalScale, weights } as Prisma.InputJsonValue;
}

function readCorrected(
  corrected: Record<string, unknown> | null,
  ...keys: string[]
): unknown {
  if (!corrected) return undefined;
  for (const key of keys) {
    if (key in corrected) return corrected[key];
  }
  return undefined;
}

function jsonInput(value: unknown): Prisma.InputJsonValue | undefined {
  if (value === null || value === undefined) return undefined;
  return value as Prisma.InputJsonValue;
}

function ruleEvidenceInput(
  evidence: z.output<typeof ruleEvidenceRow>,
): Prisma.RuleEvidenceUncheckedCreateInput {
  return {
    ruleId: evidence.ruleId,
    unvCd: evidence.unvCd,
    universityName: evidence.universityName,
    sourceUrl: evidence.sourceUrl,
    attachmentUrl: evidence.attachmentUrl,
    textPreview: evidence.textPreview,
    detectedSignals: jsonInput(evidence.detectedSignals),
    percentageValues: jsonInput(evidence.percentageValues),
    weightValues: jsonInput(evidence.weightValues),
    formulaSignals: jsonInput(evidence.formulaSignals),
    reviewPriorityScore: evidence.reviewPriorityScore,
    reviewStrength: evidence.reviewStrength,
    rawPath: evidence.rawPath,
    sourcePath: evidence.sourcePath,
  };
}

function outcomeEvidenceInput(
  evidence: z.output<typeof outcomeEvidenceRow>,
): Prisma.OutcomeEvidenceUncheckedCreateInput {
  return {
    outcomeId: evidence.outcomeId,
    sourceUrl: evidence.sourceUrl,
    rawPath: evidence.rawPath,
    rowText: evidence.rowText,
    metricValuesJson: jsonInput(evidence.metricValuesJson),
  };
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function loadOptionalCsv<T extends z.ZodTypeAny>(
  filePath: string,
  schema: T,
): Promise<z.output<T>[]> {
  if (!existsSync(filePath)) return [];
  return loadCsv(filePath, schema);
}

async function loadReviewDecisions(filePath: string): Promise<ReviewDecision[]> {
  if (!existsSync(filePath)) return [];
  const lines = (await readFile(filePath, "utf8"))
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.map((line, index) => {
    const parsed = reviewDecisionJson.safeParse(JSON.parse(line));
    if (!parsed.success) {
      throw new Error(
        `${path.basename(filePath)} line ${index + 1}: ${parsed.error.message}`,
      );
    }
    const data = parsed.data;
    const targetKind = data.targetKind ?? data.target_kind;
    const targetId = data.targetId ?? data.target_id;
    if (!targetKind || !targetId) {
      throw new Error(`${path.basename(filePath)} line ${index + 1}: target is required`);
    }
    return {
      id: data.id ?? deterministicUuid(`review-decision:${targetKind}:${targetId}:${index}`),
      targetKind,
      targetId,
      verdict: data.verdict,
      reviewedVerifiedStatus:
        data.reviewedVerifiedStatus ?? data.reviewed_verified_status ?? null,
      reviewedConfidence: data.reviewedConfidence ?? data.reviewed_confidence ?? null,
      correctedFields: data.correctedFields ?? data.corrected_fields ?? null,
      aiProposalSnapshot: data.aiProposalSnapshot ?? data.ai_proposal_snapshot ?? null,
      evidenceChecked: data.evidenceChecked ?? data.evidence_checked ?? false,
      approvalScopeKey: data.approvalScopeKey ?? data.approval_scope_key ?? null,
      reviewer: data.reviewer ?? "solo",
      reviewNotes: data.reviewNotes ?? data.review_notes ?? null,
      reviewedAt: new Date(data.reviewedAt ?? data.reviewed_at ?? 0),
    };
  });
}

function latestEffectiveDecisions(decisions: ReviewDecision[]): Map<string, ReviewDecision> {
  const output = new Map<string, ReviewDecision>();
  for (const decision of decisions) {
    if (decision.verdict !== "confirm" && decision.verdict !== "edit") continue;
    const previous = output.get(decision.targetId);
    if (!previous || previous.reviewedAt.getTime() <= decision.reviewedAt.getTime()) {
      output.set(decision.targetId, decision);
    }
  }
  return output;
}

function deterministicUuid(seed: string): string {
  const bytes = crypto.createHash("sha1").update(seed).digest();
  bytes[6] = (bytes[6]! & 0x0f) | 0x50;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = bytes.subarray(0, 16).toString("hex");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function loadCsv<T extends z.ZodTypeAny>(
  filePath: string,
  schema: T,
): Promise<z.output<T>[]> {
  const rows = parseCsv(await readFile(filePath, "utf8"));
  return rows.map((row, index) => {
    const parsed = schema.safeParse(row);
    if (!parsed.success) {
      throw new Error(
        `${path.basename(filePath)} row ${index + 2}: ${parsed.error.message}`,
      );
    }
    return parsed.data;
  });
}

function parseCsv(input: string): Record<string, string>[] {
  const records: string[][] = [];
  let field = "";
  let record: string[] = [];
  let inQuotes = false;

  for (let i = 0; i < input.length; i++) {
    const ch = input[i];
    const next = input[i + 1];
    if (ch === '"' && inQuotes && next === '"') {
      field += '"';
      i++;
    } else if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === "," && !inQuotes) {
      record.push(field);
      field = "";
    } else if ((ch === "\n" || ch === "\r") && !inQuotes) {
      if (ch === "\r" && next === "\n") i++;
      record.push(field);
      if (record.some((v) => v.trim() !== "")) records.push(record);
      field = "";
      record = [];
    } else {
      field += ch;
    }
  }
  if (field.length > 0 || record.length > 0) {
    record.push(field);
    if (record.some((v) => v.trim() !== "")) records.push(record);
  }

  const [headers, ...rows] = records;
  if (!headers) return [];
  return rows.map((row) =>
    Object.fromEntries(headers.map((header, i) => [header, row[i] ?? ""])),
  );
}

main()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
