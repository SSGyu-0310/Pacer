import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { prisma } from "@pacer/db";
import {
  confidence,
  reviewDecisionKind,
  reviewVerdict,
  verifiedStatus,
} from "@pacer/shared";
import type { Prisma } from "@prisma/client";
import { z } from "zod";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_INPUT = path.resolve(__dirname, "../data/review/review-decisions.jsonl");

const rowSchema = z.object({
  id: z.string().uuid(),
  target_kind: reviewDecisionKind,
  target_id: z.string().uuid(),
  verdict: reviewVerdict,
  reviewed_verified_status: verifiedStatus.nullable(),
  reviewed_confidence: confidence.nullable(),
  corrected_fields: z.record(z.string(), z.unknown()).nullable(),
  ai_proposal_snapshot: z.record(z.string(), z.unknown()).nullable(),
  evidence_checked: z.boolean(),
  approval_scope_key: z.string().nullable(),
  reviewer: z.string(),
  review_notes: z.string().nullable(),
  reviewed_at: z.string(),
});

async function main() {
  const args = cliArgs();
  const input = args[0] ? path.resolve(args[0]) : DEFAULT_INPUT;
  if (!existsSync(input)) throw new Error(`missing input: ${input}`);
  const rows = (await readFile(input, "utf8"))
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const parsed = rowSchema.safeParse(JSON.parse(line));
      if (!parsed.success) throw new Error(`${input} line ${index + 1}: ${parsed.error.message}`);
      return parsed.data;
    });

  for (const row of rows) {
    await prisma.referenceReviewDecision.upsert({
      where: { id: row.id },
      create: {
        id: row.id,
        targetKind: row.target_kind,
        targetId: row.target_id,
        verdict: row.verdict,
        reviewedVerifiedStatus: row.reviewed_verified_status,
        reviewedConfidence: row.reviewed_confidence,
        correctedFields: jsonInput(row.corrected_fields),
        aiProposalSnapshot: jsonInput(row.ai_proposal_snapshot),
        evidenceChecked: row.evidence_checked,
        approvalScopeKey: row.approval_scope_key,
        reviewer: row.reviewer,
        reviewNotes: row.review_notes,
        reviewedAt: new Date(row.reviewed_at),
      },
      update: {
        targetKind: row.target_kind,
        targetId: row.target_id,
        verdict: row.verdict,
        reviewedVerifiedStatus: row.reviewed_verified_status,
        reviewedConfidence: row.reviewed_confidence,
        correctedFields: jsonInput(row.corrected_fields),
        aiProposalSnapshot: jsonInput(row.ai_proposal_snapshot),
        evidenceChecked: row.evidence_checked,
        approvalScopeKey: row.approval_scope_key,
        reviewer: row.reviewer,
        reviewNotes: row.review_notes,
        reviewedAt: new Date(row.reviewed_at),
        supersededAt: null,
      },
    });
  }
  console.log(`review decisions imported. count=${rows.length} input=${input}`);
}

function jsonInput(value: unknown): Prisma.InputJsonValue | undefined {
  if (value === undefined || value === null) return undefined;
  return value as Prisma.InputJsonValue;
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
