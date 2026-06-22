import { prisma, PrismaReviewRepository } from "@pacer/db";
import {
  AnthropicExtractLlmClient,
  LlmExtractGateway,
  StubExtractLlmClient,
} from "@pacer/llm";
import type { Prisma } from "@prisma/client";

async function main() {
  const args = cliArgs();
  const force = args.includes("--force");
  const kindArg = args.find((arg) => arg.startsWith("--kind="))?.split("=")[1];
  const limitArg = args.find((arg) => arg.startsWith("--limit="))?.split("=")[1];
  const limit = limitArg ? Number(limitArg) : 100;
  const kind = kindArg === "rule" || kindArg === "outcome" ? kindArg : undefined;

  const repo = new PrismaReviewRepository(prisma);
  const apiKey = process.env.ANTHROPIC_API_KEY;
  const gateway = new LlmExtractGateway(
    apiKey
      ? new AnthropicExtractLlmClient(apiKey, process.env.LLM_EXTRACT_MODEL_NAME)
      : new StubExtractLlmClient(),
  );
  const queue = await repo.listQueue({ kind, status: "pending" });

  let extracted = 0;
  let skipped = 0;
  for (const item of queue.items.slice(0, limit)) {
    const existing = await prisma.reviewAiProposal.findUnique({
      where: {
        targetKind_targetId_promptVersion: {
          targetKind: item.kind,
          targetId: item.id,
          promptVersion: "extract-v1",
        },
      },
    });
    if (existing && !force) {
      skipped += 1;
      continue;
    }
    const detail = await repo.getItem(item.kind, item.id);
    if (!detail) {
      skipped += 1;
      continue;
    }
    const result = await gateway.extract({
      targetKind: item.kind,
      targetId: item.id,
      parsedFields: detail.parsedFields,
      evidence: detail.evidence ?? {},
    });
    await prisma.reviewAiProposal.upsert({
      where: {
        targetKind_targetId_promptVersion: {
          targetKind: item.kind,
          targetId: item.id,
          promptVersion: result.promptVersion,
        },
      },
      create: {
        targetKind: item.kind,
        targetId: item.id,
        promptVersion: result.promptVersion,
        proposalJson: result.proposal as unknown as Prisma.InputJsonValue,
        modelName: result.modelName,
      },
      update: {
        proposalJson: result.proposal as unknown as Prisma.InputJsonValue,
        modelName: result.modelName,
        createdAt: new Date(),
      },
    });
    extracted += 1;
  }

  console.log(
    `review extract complete. extracted=${extracted} skipped=${skipped} queued=${queue.items.length}`,
  );
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
