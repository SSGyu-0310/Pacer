import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { prisma } from "@pacer/db";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_OUTPUT = path.resolve(__dirname, "../data/review/review-decisions.jsonl");

async function main() {
  const args = cliArgs();
  const output = args[0] ? path.resolve(args[0]) : DEFAULT_OUTPUT;
  const decisions = await prisma.referenceReviewDecision.findMany({
    where: { supersededAt: null },
    orderBy: [{ targetKind: "asc" }, { targetId: "asc" }, { reviewedAt: "asc" }],
  });
  const lines = decisions.map((decision) =>
    JSON.stringify({
      id: decision.id,
      target_kind: decision.targetKind,
      target_id: decision.targetId,
      verdict: decision.verdict,
      reviewed_verified_status: decision.reviewedVerifiedStatus,
      reviewed_confidence: decision.reviewedConfidence,
      corrected_fields: decision.correctedFields,
      ai_proposal_snapshot: decision.aiProposalSnapshot,
      evidence_checked: decision.evidenceChecked,
      approval_scope_key: decision.approvalScopeKey,
      reviewer: decision.reviewer,
      review_notes: decision.reviewNotes,
      reviewed_at: decision.reviewedAt.toISOString(),
    }),
  );
  await mkdir(path.dirname(output), { recursive: true });
  await writeFile(output, lines.join("\n") + (lines.length ? "\n" : ""), "utf8");
  console.log(`review decisions exported. count=${lines.length} output=${output}`);
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
