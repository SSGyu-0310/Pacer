import type { ExamType } from "@pacer/shared";
import type {
  CompetitorSignal,
  CompetitorSignalInput,
} from "../domain/entities";
import { NotFoundError, ValidationError } from "../errors";
import type { CompetitorSignalRepository, CycleRepository } from "../ports";

/**
 * §7.7.4, §10.7 (P2) — 외부 도구 결과 저장/조회.
 *
 * ★ 수동 입력 전용. 자동 스크래핑·외부 API 연동 금지(§7.7.4) — 이 서비스는
 * 사용자가 직접 보고 옮겨 적은 값만 받는다. 값은 교차검증 리포트에서
 * engine/cross-validate가 보수적 휴리스틱으로 구간 근사할 뿐, 자체 분석을
 * 덮어쓰거나 정확도 우열 판정에 쓰지 않는다(§11.1).
 */
export class CompetitorSignalService {
  constructor(
    private readonly cycles: CycleRepository,
    private readonly signals: CompetitorSignalRepository,
  ) {}

  async create(
    cycleId: string,
    input: CompetitorSignalInput,
  ): Promise<CompetitorSignal> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);

    validateValue(input);
    return this.signals.save(cycleId, input);
  }

  async list(
    cycleId: string,
    examType?: ExamType,
  ): Promise<CompetitorSignal[]> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);
    return this.signals.list(cycleId, examType);
  }
}

/** value_type별 값 검증 — 깨진 값이 교차검증에 조용히 흘러들지 않게 한다 */
function validateValue(input: CompetitorSignalInput): void {
  const value = input.value.trim();
  if (value.length === 0) {
    throw new ValidationError("외부 도구 결과 값이 비어 있습니다");
  }

  switch (input.valueType) {
    case "kansu": {
      const n = Number.parseInt(value, 10);
      if (!Number.isInteger(n) || String(n) !== value || n < 1 || n > 8) {
        throw new ValidationError("진학사 칸수는 1~8 사이 정수여야 합니다");
      }
      return;
    }
    case "probability": {
      const n = Number.parseFloat(value.replace("%", ""));
      if (!Number.isFinite(n) || n < 0 || n > 100) {
        throw new ValidationError("확률 값은 0~100 사이여야 합니다");
      }
      return;
    }
    case "color": {
      if (value.length > 20) {
        throw new ValidationError("색상/구간 표기는 20자 이내여야 합니다");
      }
      return;
    }
    case "memo": {
      if (value.length > 500) {
        throw new ValidationError("메모는 500자 이내여야 합니다");
      }
      return;
    }
  }
}
