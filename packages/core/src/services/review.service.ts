import type { ReviewDecisionKind } from "@pacer/shared";
import { NotFoundError, ValidationError } from "../errors";
import type { ReviewQueueFilter, ReviewQueueRepository, ReviewRecordInput } from "../ports";

export class ReviewService {
  constructor(private readonly reviews: ReviewQueueRepository) {}

  listQueue(filter: ReviewQueueFilter) {
    return this.reviews.listQueue(filter);
  }

  async getItem(kind: ReviewDecisionKind, id: string) {
    const item = await this.reviews.getItem(kind, id);
    if (!item) throw new NotFoundError(`review item ${kind}:${id}`);
    return item;
  }

  async record(input: ReviewRecordInput) {
    if (!input.reviewer) {
      throw new ValidationError("reviewer가 필요합니다");
    }
    if (input.verdict === "edit") {
      // 규칙 교정은 엔진 형태 corrected_fields가 핵심 레버.
      if (input.targetKind === "rule" && !input.correctedFields) {
        throw new ValidationError("rule edit 판정에는 corrected_fields가 필요합니다");
      }
      if (input.targetKind === "rule" && input.correctedFields) {
        assertCompleteRuleGradeTables(input.correctedFields);
      }
      // 입결 교정은 confidence 다이얼이 레버 — corrected_fields가 아니라 reviewed_confidence를 요구한다.
      if (input.targetKind === "outcome" && !input.reviewedConfidence) {
        throw new ValidationError("outcome edit 판정에는 reviewed_confidence가 필요합니다");
      }
    }
    return this.reviews.record(input);
  }

  bulkConfirm(kind: ReviewDecisionKind, ids: string[], reviewer?: ReviewRecordInput["reviewer"]) {
    if (ids.length === 0) throw new ValidationError("ids가 필요합니다");
    if (!reviewer) throw new ValidationError("reviewer가 필요합니다");
    return this.reviews.bulkConfirm(kind, ids, reviewer);
  }
}

const GRADES = ["1", "2", "3", "4", "5", "6", "7", "8", "9"];

function assertCompleteRuleGradeTables(correctedFields: Record<string, unknown>) {
  const english =
    record(correctedFields.englishPolicyJson) ?? record(correctedFields.englishPolicy);
  const history =
    record(correctedFields.historyPolicyJson) ?? record(correctedFields.historyPolicy);

  if (!hasCompleteByGrade(english) || !hasCompleteByGrade(history)) {
    throw new ValidationError("rule edit 판정에는 영어/한국사 1~9등급표가 모두 필요합니다");
  }
}

function hasCompleteByGrade(policy: Record<string, unknown> | null): boolean {
  const byGrade = record(policy?.byGrade);
  if (!byGrade) return false;
  return GRADES.every((grade) => {
    const value = byGrade[grade];
    return typeof value === "number" && Number.isFinite(value);
  });
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}
