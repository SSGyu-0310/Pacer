import { describe, expect, it } from "vitest";
import type { Cycle, FinalOutcome, FinalOutcomeInput } from "../../domain/entities";
import type { CycleRepository, OutcomeRepository } from "../../ports";
import { OutcomeService } from "../outcome.service";

const cycle: Cycle = {
  id: "cy-1",
  userId: null,
  anonSessionId: "anon-1",
  admissionYear: 2027,
  gradeStatus: "high3",
  track: "natural",
};

const cycles: CycleRepository = {
  create: () => Promise.reject(new Error("unused")),
  findByAnonSessionAndYear: () => Promise.resolve(null),
  updateProfile: () => Promise.reject(new Error("unused")),
  findById: (id) => Promise.resolve(id === "cy-1" ? cycle : null),
};

function makeService(store: FinalOutcome[] = []) {
  const repo: OutcomeRepository = {
    save: (cycleId, input) => {
      const saved: FinalOutcome = {
        id: `out-${store.length + 1}`,
        cycleId,
        unitId: input.unitId,
        applied: input.applied,
        result: input.result,
        waitlistNumber: input.waitlistNumber ?? null,
        registered: input.registered ?? null,
        evidenceFileUrl: input.evidenceFileUrl ?? null,
        rewardStatus: null,
      };
      store.push(saved);
      return Promise.resolve(saved);
    },
    list: (cycleId) => Promise.resolve(store.filter((o) => o.cycleId === cycleId)),
  };
  return new OutcomeService(cycles, repo);
}

function input(over: Partial<FinalOutcomeInput> = {}): FinalOutcomeInput {
  return { unitId: "u1", applied: true, result: "accepted", ...over };
}

describe("OutcomeService (§7.11, P2/Phase4 — 데이터 해자)", () => {
  it("합불 결과 저장", async () => {
    const store: FinalOutcome[] = [];
    const r = await makeService(store).submit("cy-1", input());
    expect(r.outcomeId).toBe("out-1");
    expect(await makeService(store).list("cy-1")).toHaveLength(1);
  });

  it("모순 데이터 차단 — 미지원인데 합불 결과", async () => {
    await expect(
      makeService().submit("cy-1", input({ applied: false, result: "accepted" })),
    ).rejects.toThrow("지원하지 않은");
  });

  it("예비번호는 '예비'에만, 1 이상의 정수", async () => {
    const s = makeService();
    await expect(
      s.submit("cy-1", input({ result: "accepted", waitlistNumber: 3 })),
    ).rejects.toThrow("예비");
    await expect(
      s.submit("cy-1", input({ result: "waitlisted", waitlistNumber: 0 })),
    ).rejects.toThrow("1 이상");
    await s.submit("cy-1", input({ result: "waitlisted", waitlistNumber: 5 }));
  });

  it("최종 등록은 합격에만", async () => {
    await expect(
      makeService().submit(
        "cy-1",
        input({ result: "rejected", registered: true }),
      ),
    ).rejects.toThrow("합격");
  });

  it("없는 사이클 → NotFoundError", async () => {
    await expect(makeService().submit("cy-x", input())).rejects.toThrow(
      "Not found",
    );
  });
});
