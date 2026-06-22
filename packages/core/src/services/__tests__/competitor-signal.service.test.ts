import { describe, expect, it } from "vitest";
import type {
  CompetitorSignal,
  CompetitorSignalInput,
  Cycle,
} from "../../domain/entities";
import type { CompetitorSignalRepository, CycleRepository } from "../../ports";
import { CompetitorSignalService } from "../competitor-signal.service";

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

function makeService(store: CompetitorSignal[] = []) {
  const repo: CompetitorSignalRepository = {
    save: (cycleId, input) => {
      const saved: CompetitorSignal = { id: `sig-${store.length + 1}`, cycleId, ...input };
      store.push(saved);
      return Promise.resolve(saved);
    },
    list: (cycleId, examType) =>
      Promise.resolve(
        store.filter(
          (s) => s.cycleId === cycleId && (!examType || s.examType === examType),
        ),
      ),
  };
  return new CompetitorSignalService(cycles, repo);
}

function input(over: Partial<CompetitorSignalInput> = {}): CompetitorSignalInput {
  return {
    examType: "csat",
    provider: "jinhak",
    unitId: "u1",
    valueType: "kansu",
    value: "5",
    ...over,
  };
}

describe("CompetitorSignalService (§10.7, P2 — 수동 입력 전용)", () => {
  it("유효한 칸수 저장", async () => {
    const store: CompetitorSignal[] = [];
    const saved = await makeService(store).create("cy-1", input());
    expect(saved.id).toBe("sig-1");
    expect(store).toHaveLength(1);
  });

  it("값 검증 — 칸수 1~8, 확률 0~100, 빈 값 거부", async () => {
    const s = makeService();
    await expect(s.create("cy-1", input({ value: "9" }))).rejects.toThrow("1~8");
    await expect(s.create("cy-1", input({ value: "0" }))).rejects.toThrow("1~8");
    await expect(s.create("cy-1", input({ value: " " }))).rejects.toThrow("비어");
    await expect(
      s.create("cy-1", input({ valueType: "probability", value: "120" })),
    ).rejects.toThrow("0~100");
    // 정상 케이스는 통과
    await s.create("cy-1", input({ valueType: "probability", value: "85%" }));
    await s.create("cy-1", input({ valueType: "color", value: "빨강" }));
    await s.create("cy-1", input({ valueType: "memo", value: "학원 의견: 적정" }));
  });

  it("exam_type 필터로 조회 — 교차검증 리포트 입력 경로", async () => {
    const store: CompetitorSignal[] = [];
    const s = makeService(store);
    await s.create("cy-1", input({ examType: "csat" }));
    await s.create("cy-1", input({ examType: "september_mock", value: "4" }));
    expect(await s.list("cy-1", "csat")).toHaveLength(1);
    expect(await s.list("cy-1")).toHaveLength(2);
  });

  it("없는 사이클 → NotFoundError", async () => {
    await expect(makeService().create("cy-x", input())).rejects.toThrow(
      "Not found",
    );
  });
});
