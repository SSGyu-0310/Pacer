import type { Cycle } from "../domain/entities";
import type { CycleRepository } from "../ports";

export class CycleService {
  constructor(private readonly cycles: CycleRepository) {}

  /** §10.1 — 익명 세션 또는 가입 사용자로 사이클 생성 */
  createCycle(input: {
    userId: string | null;
    anonSessionId: string | null;
    admissionYear: number;
    gradeStatus: Cycle["gradeStatus"];
    track: Cycle["track"];
  }): Promise<Cycle> {
    return this.cycles.create(input);
  }

  /** §9.2 — 같은 익명 세션/입학연도는 하나의 AdmissionCycle로 이어간다. */
  async getOrCreateCycle(input: {
    userId: string | null;
    anonSessionId: string | null;
    admissionYear: number;
    gradeStatus: Cycle["gradeStatus"];
    track: Cycle["track"];
  }): Promise<{ cycle: Cycle; created: boolean }> {
    if (input.anonSessionId) {
      const existing = await this.cycles.findByAnonSessionAndYear({
        anonSessionId: input.anonSessionId,
        admissionYear: input.admissionYear,
      });
      if (existing) {
        const cycle = await this.cycles.updateProfile(existing.id, {
          gradeStatus: input.gradeStatus,
          track: input.track,
        });
        return { cycle, created: false };
      }
    }

    return { cycle: await this.cycles.create(input), created: true };
  }

  /** 사이클 조회(소유권 확인용 — 라우트 어댑터가 익명 세션과 대조한다) */
  getCycle(id: string): Promise<Cycle | null> {
    return this.cycles.findById(id);
  }

  getCycleForAnonSession(input: {
    anonSessionId: string;
    admissionYear: number;
  }): Promise<Cycle | null> {
    return this.cycles.findByAnonSessionAndYear(input);
  }
}
