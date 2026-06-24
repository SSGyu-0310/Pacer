import { describe, expect, it } from "vitest";
import type { Cycle, User } from "../../domain/entities";
import type { CycleRepository, UserRepository } from "../../ports";
import { AuthService } from "../auth.service";

const user: User = {
  id: "user-1",
  supabaseId: "supabase-1",
  email: "student@example.com",
  phone: null,
  kakaoId: null,
  role: "student",
};

const anonCycle: Cycle = {
  id: "cy-1",
  userId: null,
  anonSessionId: "anon-1",
  admissionYear: 2027,
  gradeStatus: "high3",
  track: "natural",
};

function users(existing: User | null = user): UserRepository {
  return {
    findBySupabaseId: () => Promise.resolve(existing),
    findById: (id) => Promise.resolve(id === user.id ? user : null),
    create: (input) => Promise.resolve({ ...user, ...input, id: "user-new" }),
  };
}

describe("AuthService", () => {
  it("Supabase id 기준으로 User를 재사용하거나 생성한다", async () => {
    await expect(
      new AuthService(users(user), cycles()).getOrCreateUserFromSupabase({
        supabaseId: "supabase-1",
        email: "student@example.com",
        phone: null,
        kakaoId: null,
      }),
    ).resolves.toMatchObject({ created: false, user: { id: "user-1" } });

    await expect(
      new AuthService(users(null), cycles()).getOrCreateUserFromSupabase({
        supabaseId: "supabase-new",
        email: null,
        phone: null,
        kakaoId: "kakao-1",
      }),
    ).resolves.toMatchObject({
      created: true,
      user: { id: "user-new", supabaseId: "supabase-new", kakaoId: "kakao-1" },
    });
  });

  it("익명 cycle에 userId를 채워 로그인 사용자에게 귀속한다", async () => {
    let merged = false;
    const service = new AuthService(
      users(),
      cycles({
        mergeAnonToUser: (input) => {
          merged = true;
          return Promise.resolve({ ...anonCycle, userId: input.userId });
        },
      }),
    );

    const result = await service.mergeAnonCycleToUser({
      userId: "user-1",
      anonSessionId: "anon-1",
      admissionYear: 2027,
    });

    expect(result).toMatchObject({ id: "cy-1", userId: "user-1" });
    expect(merged).toBe(true);
  });

  it("이미 같은 연도 User cycle이 있으면 중복 merge를 만들지 않고 재사용한다", async () => {
    let merged = false;
    const existingUserCycle: Cycle = { ...anonCycle, userId: "user-1" };
    const service = new AuthService(
      users(),
      cycles({
        findByUserAndYear: () => Promise.resolve(existingUserCycle),
        mergeAnonToUser: () => {
          merged = true;
          return Promise.resolve(null);
        },
      }),
    );

    const result = await service.mergeAnonCycleToUser({
      userId: "user-1",
      anonSessionId: "anon-1",
      admissionYear: 2027,
    });

    expect(result).toBe(existingUserCycle);
    expect(merged).toBe(false);
  });
});

function cycles(
  overrides: Partial<CycleRepository> = {},
): CycleRepository {
  return {
    create: () => Promise.reject(new Error("unused")),
    findByAnonSessionAndYear: () => Promise.resolve(null),
    findByUserAndYear: () => Promise.resolve(null),
    mergeAnonToUser: (input) =>
      Promise.resolve({ ...anonCycle, userId: input.userId }),
    updateProfile: () => Promise.reject(new Error("unused")),
    findById: (id) => Promise.resolve(id === anonCycle.id ? anonCycle : null),
    ...overrides,
  };
}
