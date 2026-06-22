import type { FinalOutcome, FinalOutcomeInput } from "../domain/entities";
import { NotFoundError, ValidationError } from "../errors";
import type { CycleRepository, OutcomeRepository } from "../ports";

/**
 * §7.11, §9.16 (P2/Phase4) — 실제 지원/합불 결과 수집(데이터 해자).
 *
 * 개인정보 원칙(§13.1, §7.11): 인증자료는 선택 제출이며 URL만 보관한다.
 * 익명화·통계 활용은 별도 파이프라인(Phase4)에서 처리 — 여기서는 수집만.
 * 리워드 지급(§7.11 리워드 후보)은 reward_status 갱신으로 후속 처리한다.
 */
export class OutcomeService {
  constructor(
    private readonly cycles: CycleRepository,
    private readonly outcomes: OutcomeRepository,
  ) {}

  async submit(
    cycleId: string,
    input: FinalOutcomeInput,
  ): Promise<{ outcomeId: string }> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);

    validateOutcome(input);
    const saved = await this.outcomes.save(cycleId, input);
    return { outcomeId: saved.id };
  }

  async list(cycleId: string): Promise<FinalOutcome[]> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);
    return this.outcomes.list(cycleId);
  }
}

function validateOutcome(input: FinalOutcomeInput): void {
  // 지원하지 않았다면 합불 결과가 있을 수 없다 — 모순 데이터를 막는다
  if (!input.applied && input.result !== "unknown") {
    throw new ValidationError(
      "지원하지 않은 모집단위에는 합불 결과를 기록할 수 없습니다",
    );
  }
  // 예비번호는 예비(waitlisted)일 때만 의미가 있다
  if (input.waitlistNumber != null) {
    if (input.result !== "waitlisted") {
      throw new ValidationError("예비번호는 '예비' 결과에만 입력할 수 있습니다");
    }
    if (!Number.isInteger(input.waitlistNumber) || input.waitlistNumber < 1) {
      throw new ValidationError("예비번호는 1 이상의 정수여야 합니다");
    }
  }
  // 등록 여부는 합격일 때만
  if (input.registered === true && input.result !== "accepted") {
    throw new ValidationError("최종 등록은 '합격' 결과에만 기록할 수 있습니다");
  }
}
