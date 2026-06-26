import { countReviewers, ValidationError } from "@pacer/core";
import type {
  AdmissionRuleData,
  ReviewDecisionRecord,
  ReviewItemDetailRecord,
  ReviewQueueFilter,
  ReviewQueueItem,
  ReviewQueueRepository,
  ReviewRecordInput,
} from "@pacer/core";
import type {
  Confidence,
  ReviewReviewer,
  ReviewDecisionKind,
  ReviewVerdict,
  VerifiedStatus,
} from "@pacer/shared";
import type { Prisma, PrismaClient } from "@prisma/client";
import { mapRule } from "./rule-mapping";

export class PrismaReviewRepository implements ReviewQueueRepository {
  constructor(private readonly db: PrismaClient) {}

  async listQueue(
    filter: ReviewQueueFilter,
  ): Promise<{
    items: ReviewQueueItem[];
    total: number;
    pending: number;
    decided: number;
    reviewerCounts: {
      shin: number;
      kwon: number;
      other: number;
      pending: number;
      total: number;
      decided: number;
    };
  }> {
    const kinds =
      filter.kind === "rule" ? (["rule"] as const) : filter.kind === "outcome" ? (["outcome"] as const) : (["rule", "outcome"] as const);
    const items = (
      await Promise.all(
        kinds.map((kind) =>
          kind === "rule" ? this.ruleItems(filter.coreUniversityIds) : this.outcomeItems(filter.coreUniversityIds),
        ),
      )
    ).flat();
    const reviewerCounts = countReviewers(items);

    const filtered = items.filter((item) => {
      if (filter.status === "pending" && item.latestVerdict) return false;
      if (filter.status === "decided" && !item.latestVerdict) return false;
      if (filter.onlyUncertain && !item.uncertain) return false;
      return true;
    });

    filtered.sort((a, b) => {
      const priority = (b.reviewPriorityScore ?? -1) - (a.reviewPriorityScore ?? -1);
      if (priority !== 0) return priority;
      return (a.universityName ?? "").localeCompare(b.universityName ?? "", "ko");
    });

    return {
      items: filtered,
      total: items.length,
      pending: items.filter((item) => !item.latestVerdict).length,
      decided: items.filter((item) => item.latestVerdict).length,
      reviewerCounts,
    };
  }

  async getItem(
    kind: ReviewDecisionKind,
    id: string,
  ): Promise<ReviewItemDetailRecord | null> {
    if (kind === "rule") return this.getRuleItem(id);
    return this.getOutcomeItem(id);
  }

  async record(
    input: ReviewRecordInput,
  ): Promise<{ decisionId: string; wouldUnlockExact: boolean | null; clusterApplied: number }> {
    if (!input.reviewer) throw new ValidationError("reviewer가 필요합니다");
    const detail = await this.getItem(input.targetKind, input.targetId);
    if (!detail) throw new Error(`review target not found: ${input.targetKind}:${input.targetId}`);

    let wouldUnlockExact: boolean | null = null;
    if (input.targetKind === "rule" && (input.verdict === "confirm" || input.verdict === "edit")) {
      wouldUnlockExact = await this.wouldUnlockExact(input.targetId, input);
      const wouldEnableRelativeComparison =
        input.verdict === "edit"
          ? await this.wouldEnableRelativeComparison(input.targetId, input)
          : false;
      // edit는 공식 원문 기반 corrected_fields를 서비스 분석 경로에 태우는 작업이다.
      // exact가 풀리면 high/medium 분석, requiredInputs 때문에 exact만 닫히면 low confidence 근사 비교를 허용한다.
      // mapRule 불가/custom/비수능 구성요소처럼 분석 경로 자체가 닫히는 경우는 거절한다.
      if (input.verdict === "edit" && !wouldUnlockExact && !wouldEnableRelativeComparison) {
        throw new ValidationError(
          "교정값이 exact/근사 비교 분석을 열지 못합니다 — formula/정책을 엔진 형태로 채워주세요",
        );
      }
    }

    // 클러스터 적용: 같은 대학에서 동일 식을 쓰는 모든 2027 모집단위에 같은 결정을 기록.
    const applyCluster = input.applyToCluster && input.targetKind === "rule";
    const targetIds = applyCluster ? await this.clusterMemberIds(input.targetId) : [input.targetId];
    const scopeKey = applyCluster ? await this.clusterScopeKey(input.targetId) : (input.approvalScopeKey ?? null);
    const snapshot = jsonInput(detail.aiProposal?.proposalJson ?? null);

    const primaryId = await this.db.$transaction(async (tx) => {
      let firstId = "";
      for (const targetId of targetIds) {
        await tx.referenceReviewDecision.updateMany({
          where: { targetKind: input.targetKind, targetId, supersededAt: null },
          data: { supersededAt: new Date() },
        });
        const created = await tx.referenceReviewDecision.create({
          data: {
            targetKind: input.targetKind,
            targetId,
            verdict: input.verdict,
            reviewedVerifiedStatus: input.reviewedVerifiedStatus ?? null,
            reviewedConfidence: input.reviewedConfidence ?? null,
            correctedFields: jsonInput(input.correctedFields),
            aiProposalSnapshot: snapshot,
            evidenceChecked: input.evidenceChecked,
            approvalScopeKey: scopeKey,
            reviewer: input.reviewer,
            reviewNotes: input.reviewNotes ?? null,
          },
        });
        if (targetId === input.targetId) firstId = created.id;
        else if (!firstId) firstId = created.id;
      }
      return firstId;
    });

    return { decisionId: primaryId, wouldUnlockExact, clusterApplied: targetIds.length };
  }

  /** 대표 규칙과 동일 식(대학+정책 바이트 동일)을 쓰는 2027 규칙 id 목록. */
  private async clusterMemberIds(repId: string): Promise<string[]> {
    const rep = await this.db.admissionRule.findUnique({ where: { id: repId }, include: { unit: true } });
    if (!rep) return [repId];
    const siblings = await this.db.admissionRule.findMany({
      where: {
        year: 2027,
        verifiedStatus: { in: ["draft", "parsed"] },
        unit: { universityId: rep.unit.universityId },
      },
      include: { unit: true },
    });
    const decisions = await this.latestDecisions("rule", siblings.map((row) => row.id));
    const repSig = ruleReviewSignature(rep, decisions.get(rep.id));
    const ids = siblings
      .filter((row) => ruleReviewSignature(row, decisions.get(row.id)) === repSig)
      .map((row) => row.id);
    return ids.includes(repId) ? ids : [repId, ...ids];
  }

  private async clusterScopeKey(repId: string): Promise<string | null> {
    const rep = await this.db.admissionRule.findUnique({ where: { id: repId }, include: { unit: true } });
    const decision = rep ? await this.latestDecision("rule", rep.id) : null;
    return rep ? `${rep.unit.universityId}|2027|${hashSignature(ruleReviewSignature(rep, decision ?? undefined))}` : null;
  }

  async bulkConfirm(
    kind: ReviewDecisionKind,
    ids: string[],
    reviewer?: ReviewReviewer,
  ): Promise<{ recorded: number; skipped: number }> {
    if (!reviewer) throw new ValidationError("reviewer가 필요합니다");
    let recorded = 0;
    let skipped = 0;
    for (const id of ids) {
      const detail = await this.getItem(kind, id);
      if (!detail?.aiProposal || detail.latestDecision) {
        skipped += 1;
        continue;
      }
      try {
        await this.record({
          targetKind: kind,
          targetId: id,
          verdict: "confirm",
          reviewedVerifiedStatus: kind === "rule" ? "verified" : undefined,
          reviewedConfidence: kind === "outcome" ? "high" : undefined,
          correctedFields: proposalCorrectedFields(detail.aiProposal.proposalJson),
          evidenceChecked: true,
          applyToCluster: kind === "rule",
          reviewer,
        });
        recorded += 1;
      } catch {
        skipped += 1;
      }
    }
    return { recorded, skipped };
  }

  private async ruleItems(coreUniversityIds?: string[]): Promise<ReviewQueueItem[]> {
    const scoped = coreUniversityIds && coreUniversityIds.length > 0;
    const rows = await this.db.admissionRule.findMany({
      where: {
        year: 2027,
        verifiedStatus: { in: ["draft", "parsed"] },
        ...(scoped ? { unit: { universityId: { in: coreUniversityIds } } } : {}),
      },
      include: { unit: { include: { university: true } } },
    });

    const decisions = await this.latestDecisions("rule", rows.map((row) => row.id));

    // 동일 식(대학+환산식+정책 바이트 동일)을 한 클러스터로 접고 대표 1건만 노출.
    // active edit.corrected_fields가 있으면 교정 산식을 기준으로 다시 묶는다. 원본 parser가
    // 자유전공/계열별 산식을 잘못 한 클러스터로 묶은 경우 admin UI에서 숨지 않게 하기 위해서다.
    const clusters = new Map<string, { rep: (typeof rows)[number]; size: number }>();
    for (const row of rows) {
      const key = ruleReviewSignature(row, decisions.get(row.id));
      const existing = clusters.get(key);
      if (!existing) {
        clusters.set(key, { rep: row, size: 1 });
      } else {
        existing.size += 1;
        if (priorityOf(row) > priorityOf(existing.rep)) existing.rep = row;
      }
    }

    const reps = [...clusters.values()];
    const repIds = reps.map((c) => c.rep.id);
    const [evidence, proposals] = await Promise.all([
      this.ruleEvidence(repIds),
      this.proposals("rule", repIds),
    ]);

    return reps.map(({ rep: row, size }) => {
      const ev = evidence.get(row.id);
      const proposal = proposals.get(row.id);
      const decision = decisions.get(row.id);
      return {
        kind: "rule",
        id: row.id,
        universityId: row.unit.universityId,
        universityName: ev?.universityName ?? row.unit.university.name,
        unitName: row.unit.name,
        year: row.year,
        verifiedStatus: row.verifiedStatus as VerifiedStatus,
        confidence: null,
        reviewPriorityScore: ev?.reviewPriorityScore ?? formulaNumber(row.formulaJson, "reviewPriorityScore"),
        reviewStrength: ev?.reviewStrength ?? formulaString(row.formulaJson, "reviewStrength"),
        hasAiProposal: Boolean(proposal),
        uncertain: proposal ? proposalUncertain(proposal.proposalJson) : true,
        latestVerdict: decision?.verdict ?? null,
        latestReviewer: decision?.reviewer ?? null,
        sourceUrl: ev?.sourceUrl ?? row.sourceUrl,
        textPreview: ev?.textPreview ?? null,
        clusterSize: size,
      };
    });
  }

  private async outcomeItems(coreUniversityIds?: string[]): Promise<ReviewQueueItem[]> {
    const scoped = coreUniversityIds && coreUniversityIds.length > 0;
    const rows = await this.db.historicalOutcome.findMany({
      where: {
        confidence: { in: ["low", "limited"] },
        ...(scoped ? { unit: { universityId: { in: coreUniversityIds } } } : {}),
      },
      include: { unit: { include: { university: true } } },
    });
    const ids = rows.map((row) => row.id);
    const [evidence, proposals, decisions] = await Promise.all([
      this.outcomeEvidence(ids),
      this.proposals("outcome", ids),
      this.latestDecisions("outcome", ids),
    ]);

    return rows.map((row) => {
      const ev = evidence.get(row.id);
      const proposal = proposals.get(row.id);
      const decision = decisions.get(row.id);
      return {
        kind: "outcome",
        id: row.id,
        universityId: row.unit.universityId,
        universityName: row.unit.university.name,
        unitName: row.unit.name,
        year: row.year,
        verifiedStatus: null,
        confidence: row.confidence as Confidence,
        reviewPriorityScore: null,
        reviewStrength: null,
        hasAiProposal: Boolean(proposal),
        uncertain: proposal ? proposalUncertain(proposal.proposalJson) : row.confidence !== "high",
        latestVerdict: decision?.verdict ?? null,
        latestReviewer: decision?.reviewer ?? null,
        sourceUrl: ev?.sourceUrl ?? row.sourceUrl,
        textPreview: ev?.rowText ?? null,
        clusterSize: 1,
      };
    });
  }

  private async getRuleItem(id: string): Promise<ReviewItemDetailRecord | null> {
    const row = await this.db.admissionRule.findUnique({
      where: { id },
      include: { unit: { include: { university: true } } },
    });
    if (!row) return null;
    const [evidence, proposal, decision] = await Promise.all([
      this.db.ruleEvidence.findUnique({ where: { ruleId: id } }),
      this.latestProposal("rule", id),
      this.latestDecision("rule", id),
    ]);
    const parsedFields = {
      scoreType: row.scoreType,
      formulaJson: row.formulaJson,
      englishPolicyJson: row.englishPolicyJson,
      historyPolicyJson: row.historyPolicyJson,
      inquiryPolicyJson: row.inquiryPolicyJson,
      eligibilityJson: row.eligibilityJson,
    };
    const unlockFields =
      decision?.correctedFields ?? proposalCorrectedFields(proposal?.proposalJson ?? {});
    return {
      kind: "rule",
      id,
      universityName: evidence?.universityName ?? row.unit.university.name,
      unitName: row.unit.name,
      year: row.year,
      sourceUrl: evidence?.sourceUrl ?? row.sourceUrl,
      parsedFields,
      evidence: evidence ? evidenceRecord(evidence, row.year) : null,
      aiProposal: proposal,
      latestDecision: decision,
      wouldUnlockExact: await this.wouldUnlockExact(id, {
        targetKind: "rule",
        targetId: id,
        verdict: "confirm",
        reviewedVerifiedStatus: "verified",
        correctedFields: unlockFields,
        evidenceChecked: true,
      }),
      clusterSize: (await this.clusterMemberIds(id)).length,
    };
  }

  private async getOutcomeItem(id: string): Promise<ReviewItemDetailRecord | null> {
    const row = await this.db.historicalOutcome.findUnique({
      where: { id },
      include: { unit: { include: { university: true } } },
    });
    if (!row) return null;
    const [evidence, proposal, decision] = await Promise.all([
      this.db.outcomeEvidence.findUnique({ where: { outcomeId: id } }),
      this.latestProposal("outcome", id),
      this.latestDecision("outcome", id),
    ]);
    return {
      kind: "outcome",
      id,
      universityName: row.unit.university.name,
      unitName: row.unit.name,
      year: row.year,
      sourceUrl: evidence?.sourceUrl ?? row.sourceUrl,
      parsedFields: {
        avgScore: row.avgScore,
        cutScore: row.cutScore,
        percentileCut: row.percentileCut,
        competitionRate: row.competitionRate,
        additionalPass: row.additionalPass,
      },
      evidence: evidence ? evidenceRecord(evidence, row.year) : null,
      aiProposal: proposal,
      latestDecision: decision,
      wouldUnlockExact: null,
      clusterSize: 1,
    };
  }

  private async wouldUnlockExact(id: string, input: ReviewRecordInput): Promise<boolean> {
    const { mapped, verified } = await this.correctedRuleForReview(id, input);
    return Boolean(
      mapped &&
        verified &&
        mapped.scoreType !== "custom" &&
        !hasExternalComponents(mapped) &&
        !hasRequiredFormulaInputs(mapped) &&
        !hasApproximateInquiryConversion(mapped),
    );
  }

  private async wouldEnableRelativeComparison(id: string, input: ReviewRecordInput): Promise<boolean> {
    const { mapped, verified } = await this.correctedRuleForReview(id, input);
    return Boolean(
      mapped &&
        verified &&
        mapped.scoreType !== "custom" &&
        hasComparableCsatFormula(mapped) &&
        (hasExternalComponents(mapped) || hasRequiredFormulaInputs(mapped) || hasApproximateInquiryConversion(mapped)),
    );
  }

  private async correctedRuleForReview(
    id: string,
    input: ReviewRecordInput,
  ): Promise<{ mapped: AdmissionRuleData | null; verified: boolean }> {
    const row = await this.db.admissionRule.findUnique({ where: { id } });
    if (!row) return { mapped: null, verified: false };
    const corrected = input.correctedFields ?? {};
    const reviewedStatus = input.reviewedVerifiedStatus ?? row.verifiedStatus;
    const mapped = mapRule({
      unitId: row.unitId,
      scoreType: stringField(corrected, "scoreType") ?? row.scoreType,
      formulaJson: jsonField(corrected, "formulaJson") ?? formulaFromCorrected(corrected) ?? row.formulaJson,
      englishPolicyJson:
        jsonField(corrected, "englishPolicyJson") ?? jsonField(corrected, "englishPolicy") ?? row.englishPolicyJson,
      historyPolicyJson:
        jsonField(corrected, "historyPolicyJson") ?? jsonField(corrected, "historyPolicy") ?? row.historyPolicyJson,
      inquiryPolicyJson:
        jsonField(corrected, "inquiryPolicyJson") ?? jsonField(corrected, "inquiryPolicy") ?? row.inquiryPolicyJson,
      eligibilityJson:
        jsonField(corrected, "eligibilityJson") ?? jsonField(corrected, "eligibility") ?? row.eligibilityJson,
      verifiedStatus: reviewedStatus,
    });
    return {
      mapped,
      verified: reviewedStatus === "verified" || reviewedStatus === "live",
    };
  }

  private async ruleEvidence(ids: string[]) {
    const rows = await collectChunks(ids, (chunk) =>
      this.db.ruleEvidence.findMany({ where: { ruleId: { in: chunk } } }),
    );
    return new Map(rows.map((row) => [row.ruleId, row]));
  }

  private async outcomeEvidence(ids: string[]) {
    const rows = await collectChunks(ids, (chunk) =>
      this.db.outcomeEvidence.findMany({ where: { outcomeId: { in: chunk } } }),
    );
    return new Map(rows.map((row) => [row.outcomeId, row]));
  }

  private async proposals(kind: ReviewDecisionKind, ids: string[]) {
    const rows = await collectChunks(ids, (chunk) =>
      this.db.reviewAiProposal.findMany({
        where: { targetKind: kind, targetId: { in: chunk } },
        orderBy: { createdAt: "desc" },
      }),
    );
    const output = new Map<string, NonNullable<Awaited<ReturnType<typeof this.latestProposal>>>>();
    for (const row of rows) if (!output.has(row.targetId)) output.set(row.targetId, proposalRecord(row));
    return output;
  }

  private async latestProposal(kind: ReviewDecisionKind, id: string) {
    const row = await this.db.reviewAiProposal.findFirst({
      where: { targetKind: kind, targetId: id },
      orderBy: { createdAt: "desc" },
    });
    return row ? proposalRecord(row) : null;
  }

  private async latestDecisions(kind: ReviewDecisionKind, ids: string[]) {
    const rows = await collectChunks(ids, (chunk) =>
      this.db.referenceReviewDecision.findMany({
        where: { targetKind: kind, targetId: { in: chunk }, supersededAt: null },
      }),
    );
    return new Map(rows.map((row) => [row.targetId, decisionRecord(row)]));
  }

  private async latestDecision(kind: ReviewDecisionKind, id: string) {
    const row = await this.db.referenceReviewDecision.findFirst({
      where: { targetKind: kind, targetId: id, supersededAt: null },
      orderBy: { reviewedAt: "desc" },
    });
    return row ? decisionRecord(row) : null;
  }
}

function hasExternalComponents(rule: AdmissionRuleData): boolean {
  if (rule.externalComponents?.length) return true;
  return (rule.formulaAlternatives ?? []).some((alternative) => Boolean(alternative.externalComponents?.length));
}

function hasRequiredFormulaInputs(rule: AdmissionRuleData): boolean {
  if (rule.requiredInputs?.length) return true;
  return (rule.formulaAlternatives ?? []).some((alternative) => Boolean(alternative.requiredInputs?.length));
}

function hasApproximateInquiryConversion(rule: AdmissionRuleData): boolean {
  if (rule.formulaAlternatives?.length) {
    return rule.formulaAlternatives.some((alternative) =>
      hasApproximateInquiryConversion({
        ...rule,
        totalScale: alternative.totalScale ?? rule.totalScale,
        calculationMode: alternative.calculationMode ?? rule.calculationMode,
        weights: alternative.weights,
        subjectScoreTypes: alternative.subjectScoreTypes ?? rule.subjectScoreTypes,
        subjectScoreMaxes: alternative.subjectScoreMaxes ?? rule.subjectScoreMaxes,
        subjectBaseScores: alternative.subjectBaseScores ?? rule.subjectBaseScores,
        subjectAdjustments: alternative.subjectAdjustments ?? rule.subjectAdjustments,
        finalAdjustments: alternative.finalAdjustments ?? rule.finalAdjustments,
        requiredInputs: alternative.requiredInputs ?? rule.requiredInputs,
        selectionPolicy: alternative.selectionPolicy ?? rule.selectionPolicy,
        externalComponents: alternative.externalComponents ?? rule.externalComponents,
        formulaAlternatives: undefined,
      }),
    );
  }
  if (rule.scoreType !== "mixed") return false;
  if (!ruleUsesInquiry(rule)) return false;
  if (rule.inquiryPolicy.conversionTable) return false;
  return rule.subjectScoreTypes?.inquiry === undefined;
}

function ruleUsesInquiry(rule: AdmissionRuleData): boolean {
  if (rule.weights.inquiry > 0) return true;
  if (rule.selectionPolicy?.subjects.includes("inquiry")) return true;
  if (rule.selectionPolicy?.groups?.some((group) => group.subjects.includes("inquiry"))) return true;
  if (rule.subjectAdjustments?.some((adjustment) => adjustment.subject === "inquiry")) return true;
  return rule.finalAdjustments?.some((adjustment) => adjustment.subject === "inquiry") ?? false;
}

function hasComparableCsatFormula(rule: AdmissionRuleData): boolean {
  if (rule.selectionPolicy) return true;
  if (rule.weights.korean > 0 || rule.weights.math > 0 || rule.weights.inquiry > 0) return true;
  if (rule.englishPolicy.mode === "ratio" && (rule.englishPolicy.weight ?? 0) > 0) return true;
  return (
    rule.formulaAlternatives?.some((alternative) => {
      if (alternative.selectionPolicy ?? rule.selectionPolicy) return true;
      const weights = alternative.weights;
      return weights.korean > 0 || weights.math > 0 || weights.inquiry > 0;
    }) ?? false
  );
}

/** active edit가 있으면 교정 산식까지 반영한 규칙 클러스터 서명. */
function ruleReviewSignature(
  row: {
    scoreType: string;
    formulaJson: unknown;
    englishPolicyJson: unknown;
    historyPolicyJson: unknown;
    inquiryPolicyJson: unknown;
    eligibilityJson: unknown;
    unit?: { universityId: string };
  },
  decision?: ReviewDecisionRecord | null,
): string {
  const corrected = decision?.verdict === "edit" ? (decision.correctedFields ?? {}) : {};
  return ruleSignature({
    unit: row.unit,
    scoreType: stringField(corrected, "scoreType") ?? row.scoreType,
    formulaJson: jsonField(corrected, "formulaJson") ?? formulaFromCorrected(corrected) ?? row.formulaJson,
    englishPolicyJson:
      jsonField(corrected, "englishPolicyJson") ?? jsonField(corrected, "englishPolicy") ?? row.englishPolicyJson,
    historyPolicyJson:
      jsonField(corrected, "historyPolicyJson") ?? jsonField(corrected, "historyPolicy") ?? row.historyPolicyJson,
    inquiryPolicyJson:
      jsonField(corrected, "inquiryPolicyJson") ?? jsonField(corrected, "inquiryPolicy") ?? row.inquiryPolicyJson,
    eligibilityJson:
      jsonField(corrected, "eligibilityJson") ?? jsonField(corrected, "eligibility") ?? row.eligibilityJson,
  });
}

/** 규칙 클러스터 서명: 대학+환산식+정책이 바이트 동일하면 같은 식으로 본다. */
function ruleSignature(row: {
  scoreType: string;
  formulaJson: unknown;
  englishPolicyJson: unknown;
  historyPolicyJson: unknown;
  inquiryPolicyJson: unknown;
  eligibilityJson: unknown;
  unit?: { universityId: string };
}): string {
  return [
    row.unit?.universityId ?? "",
    row.scoreType,
    stableJson(row.formulaJson),
    stableJson(row.englishPolicyJson),
    stableJson(row.historyPolicyJson),
    stableJson(row.inquiryPolicyJson),
    stableJson(row.eligibilityJson),
  ].join("\u0000");
}

/** 키 정렬된 JSON 직렬화 — 키 순서 차이로 클러스터가 갈라지지 않게. */
function stableJson(value: unknown): string {
  const seen = (v: unknown): unknown => {
    if (Array.isArray(v)) return v.map(seen);
    if (v && typeof v === "object") {
      return Object.fromEntries(
        Object.entries(v as Record<string, unknown>)
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([k, val]) => [k, seen(val)]),
      );
    }
    return v;
  };
  return JSON.stringify(seen(value));
}

function hashSignature(signature: string): string {
  let hash = 0;
  for (let i = 0; i < signature.length; i += 1) {
    hash = (hash * 31 + signature.charCodeAt(i)) | 0;
  }
  return (hash >>> 0).toString(16);
}

function priorityOf(row: { formulaJson: Prisma.JsonValue }): number {
  return formulaNumber(row.formulaJson, "reviewPriorityScore") ?? 0;
}

function proposalRecord(row: {
  id: string;
  targetKind: ReviewDecisionKind;
  targetId: string;
  promptVersion: string;
  proposalJson: Prisma.JsonValue;
  modelName: string;
  createdAt: Date;
}): {
  id: string;
  targetKind: ReviewDecisionKind;
  targetId: string;
  promptVersion: string;
  proposalJson: Record<string, unknown>;
  modelName: string;
  createdAt: Date;
} {
  return {
    id: row.id,
    targetKind: row.targetKind,
    targetId: row.targetId,
    promptVersion: row.promptVersion,
    proposalJson: recordJson(row.proposalJson) ?? {},
    modelName: row.modelName,
    createdAt: row.createdAt,
  };
}

function decisionRecord(row: {
  id: string;
  targetKind: ReviewDecisionKind;
  targetId: string;
  verdict: ReviewVerdict;
  reviewedVerifiedStatus: VerifiedStatus | null;
  reviewedConfidence: Confidence | null;
  correctedFields: Prisma.JsonValue | null;
  aiProposalSnapshot: Prisma.JsonValue | null;
  evidenceChecked: boolean;
  approvalScopeKey: string | null;
  reviewer: string;
  reviewNotes: string | null;
  reviewedAt: Date;
}): ReviewDecisionRecord {
  return {
    id: row.id,
    targetKind: row.targetKind,
    targetId: row.targetId,
    verdict: row.verdict,
    reviewedVerifiedStatus: row.reviewedVerifiedStatus,
    reviewedConfidence: row.reviewedConfidence,
    correctedFields: recordJson(row.correctedFields),
    aiProposalSnapshot: recordJson(row.aiProposalSnapshot),
    evidenceChecked: row.evidenceChecked,
    approvalScopeKey: row.approvalScopeKey,
    reviewer: row.reviewer,
    reviewNotes: row.reviewNotes,
    reviewedAt: row.reviewedAt,
  };
}

function evidenceRecord(row: Record<string, unknown>, targetYear: number | null): Record<string, unknown> {
  const record = Object.fromEntries(Object.entries(row).filter(([key]) => key !== "ruleId" && key !== "outcomeId"));
  const sourceWarnings = evidenceSourceWarnings(record, targetYear);
  if (sourceWarnings.length > 0) record.sourceWarnings = sourceWarnings;
  return record;
}

function evidenceSourceWarnings(record: Record<string, unknown>, targetYear: number | null): string[] {
  const warnings: string[] = [];
  const documentYearStatus = stringField(record, "documentYearStatus");
  const primaryYear = numberField(record, "documentPrimaryAdmissionYear");

  if (documentYearStatus && documentYearStatus !== "primary_year_matched") {
    warnings.push(`문서 연도 상태가 ${documentYearStatus}입니다. 최신 검수 메모의 공식 원문을 기준으로 재확인하세요.`);
  }
  if (record.promotionSafeSourceYear === false) {
    warnings.push("이 문서는 추출 대상 연도와 1차 문서 연도가 달라 자동 승격 근거로 쓰면 안 됩니다.");
  }
  if (targetYear && primaryYear && primaryYear !== targetYear) {
    warnings.push(`문서 제목 기준 학년도 ${primaryYear}와 검수 대상 ${targetYear}학년도가 다릅니다.`);
  }

  const sourcePath = stringField(record, "sourcePath");
  const sourceYear = sourcePath?.match(/(?:^|\/)hwp-text\/(20[1-3][0-9])(?:\/|$)/)?.[1];
  if (targetYear && sourceYear && Number(sourceYear) !== targetYear) {
    warnings.push(`수집 evidence 경로가 hwp-text/${sourceYear}입니다. ${targetYear}학년도 근거인지 별도 확인이 필요합니다.`);
  }

  return [...new Set(warnings)];
}

function recordJson(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function jsonInput(value: unknown): Prisma.InputJsonValue | undefined {
  if (value === undefined || value === null) return undefined;
  return value as Prisma.InputJsonValue;
}

function proposalCorrectedFields(proposal: Record<string, unknown>): Record<string, unknown> {
  const proposed = proposal.proposed;
  return recordJson(proposed) ?? {};
}

function proposalUncertain(proposal: Record<string, unknown>): boolean {
  const uncertain = proposal.uncertain;
  return Array.isArray(uncertain) && uncertain.length > 0;
}

function formulaNumber(value: unknown, key: string): number | null {
  const record = recordJson(value);
  const raw = record?.[key];
  return typeof raw === "number" ? raw : null;
}

function formulaString(value: unknown, key: string): string | null {
  const record = recordJson(value);
  const raw = record?.[key];
  return typeof raw === "string" ? raw : null;
}

function stringField(record: Record<string, unknown>, key: string): string | null {
  const raw = record[key];
  return typeof raw === "string" ? raw : null;
}

function numberField(record: Record<string, unknown>, key: string): number | null {
  const raw = record[key];
  return typeof raw === "number" ? raw : null;
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

function chunks<T>(items: T[], size = 5000): T[][] {
  const output: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    output.push(items.slice(index, index + size));
  }
  return output;
}

async function collectChunks<T, R>(
  items: T[],
  worker: (chunk: T[]) => Promise<R[]>,
): Promise<R[]> {
  const output: R[] = [];
  for (const chunk of chunks(items)) {
    output.push(...(await worker(chunk)));
  }
  return output;
}
