import { describe, expect, it } from "vitest";
import type { Cycle } from "../../domain/entities";
import type { CycleRepository } from "../../ports";
import { CycleService } from "../cycle.service";

const existing: Cycle = {
  id: "cy-1",
  userId: null,
  anonSessionId: "anon-1",
  admissionYear: 2027,
  gradeStatus: "high3",
  track: "natural",
};

describe("CycleService.getOrCreateCycle", () => {
  it("같은 익명 세션/입학연도는 기존 AdmissionCycle을 재사용한다", async () => {
    let created = false;
    let updated = false;
    const repo: CycleRepository = {
      create: () => {
        created = true;
        return Promise.resolve({ ...existing, id: "cy-new" });
      },
      findByAnonSessionAndYear: () => Promise.resolve(existing),
      updateProfile: (id, input) => {
        updated = true;
        return Promise.resolve({ ...existing, id, ...input });
      },
      findById: () => Promise.resolve(null),
    };

    const result = await new CycleService(repo).getOrCreateCycle({
      userId: null,
      anonSessionId: "anon-1",
      admissionYear: 2027,
      gradeStatus: "repeater",
      track: "medical",
    });

    expect(result.created).toBe(false);
    expect(result.cycle).toMatchObject({
      id: "cy-1",
      gradeStatus: "repeater",
      track: "medical",
    });
    expect(created).toBe(false);
    expect(updated).toBe(true);
  });

  it("기존 AdmissionCycle이 없으면 새로 만든다", async () => {
    const repo: CycleRepository = {
      create: (input) => Promise.resolve({ ...existing, id: "cy-new", ...input }),
      findByAnonSessionAndYear: () => Promise.resolve(null),
      updateProfile: () => Promise.reject(new Error("unused")),
      findById: () => Promise.resolve(null),
    };

    const result = await new CycleService(repo).getOrCreateCycle({
      userId: null,
      anonSessionId: "anon-1",
      admissionYear: 2027,
      gradeStatus: "high3",
      track: "natural",
    });

    expect(result).toMatchObject({ created: true, cycle: { id: "cy-new" } });
  });
});
