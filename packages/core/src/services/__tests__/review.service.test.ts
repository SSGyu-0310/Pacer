import { describe, expect, it, vi } from "vitest";
import { ValidationError } from "../../errors";
import type { ReviewQueueRepository, ReviewRecordInput } from "../../ports";
import { ReviewService } from "../review.service";

function repoStub(): ReviewQueueRepository {
  return {
    listQueue: vi.fn().mockResolvedValue({ items: [], total: 0, pending: 0, decided: 0 }),
    getItem: vi.fn().mockResolvedValue(null),
    record: vi.fn().mockResolvedValue({ decisionId: "d1", wouldUnlockExact: true, clusterApplied: 1 }),
    bulkConfirm: vi.fn().mockResolvedValue({ recorded: 0, skipped: 0 }),
  };
}

const base: Omit<ReviewRecordInput, "targetKind" | "verdict"> = {
  targetId: "11111111-1111-4111-8111-111111111111",
  evidenceChecked: true,
};

describe("ReviewService.record 검수 가드", () => {
  it("rule edit는 corrected_fields가 없으면 거절한다", async () => {
    const repo = repoStub();
    const service = new ReviewService(repo);
    await expect(service.record({ ...base, targetKind: "rule", verdict: "edit" })).rejects.toBeInstanceOf(
      ValidationError,
    );
    expect(repo.record).not.toHaveBeenCalled();
  });

  it("outcome edit는 corrected_fields 없이 reviewed_confidence만으로 통과한다 (입결 confidence 레버)", async () => {
    const repo = repoStub();
    const service = new ReviewService(repo);
    await service.record({ ...base, targetKind: "outcome", verdict: "edit", reviewedConfidence: "high" });
    expect(repo.record).toHaveBeenCalledOnce();
  });

  it("outcome edit는 reviewed_confidence가 없으면 거절한다", async () => {
    const repo = repoStub();
    const service = new ReviewService(repo);
    await expect(service.record({ ...base, targetKind: "outcome", verdict: "edit" })).rejects.toBeInstanceOf(
      ValidationError,
    );
    expect(repo.record).not.toHaveBeenCalled();
  });

  it("confirm/flag/skip은 corrected_fields 가드를 받지 않는다", async () => {
    const repo = repoStub();
    const service = new ReviewService(repo);
    await service.record({ ...base, targetKind: "rule", verdict: "flag" });
    await service.record({ ...base, targetKind: "outcome", verdict: "skip" });
    expect(repo.record).toHaveBeenCalledTimes(2);
  });
});
