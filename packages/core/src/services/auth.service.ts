import type { Cycle, User } from "../domain/entities";
import type { CycleRepository, UserRepository } from "../ports";

export class AuthService {
  constructor(
    private readonly users: UserRepository,
    private readonly cycles: CycleRepository,
  ) {}

  async getOrCreateUserFromSupabase(input: {
    supabaseId: string;
    email: string | null;
    phone: string | null;
    kakaoId: string | null;
  }): Promise<{ user: User; created: boolean }> {
    const existing = await this.users.findBySupabaseId(input.supabaseId);
    if (existing) return { user: existing, created: false };

    return {
      user: await this.users.create(input),
      created: true,
    };
  }

  getUserBySupabaseId(supabaseId: string): Promise<User | null> {
    return this.users.findBySupabaseId(supabaseId);
  }

  /** 익명 세션의 6모 cycle을 로그인 User에 귀속한다. 이미 귀속된 cycle이 있으면 재사용한다. */
  async mergeAnonCycleToUser(input: {
    userId: string;
    anonSessionId: string;
    admissionYear: number;
  }): Promise<Cycle | null> {
    const existing = await this.cycles.findByUserAndYear({
      userId: input.userId,
      admissionYear: input.admissionYear,
    });
    if (existing) return existing;

    return this.cycles.mergeAnonToUser(input);
  }
}
