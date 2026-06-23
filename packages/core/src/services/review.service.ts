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
