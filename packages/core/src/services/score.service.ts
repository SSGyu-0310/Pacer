import type { ExamScore, ScoreInput } from "../domain/entities";
import { validateScores } from "../engine";
import { NotFoundError, ValidationError } from "../errors";
import type { ScoreRepository } from "../ports";

export class ScoreService {
  constructor(private readonly scores: ScoreRepository) {}

  /**
   * §10.2 — 검증 후 성적 저장.
   * 차단성 오류(범위 위반·필수 누락)는 저장하지 않고 ValidationError.
   * 경고(선택과목 미입력 등)는 저장하되 응답에 포함한다.
   */
  async saveScores(
    cycleId: string,
    input: ScoreInput,
  ): Promise<{ examScore: ExamScore; warnings: string[] }> {
    const validation = validateScores(input);
    if (!validation.valid) {
      throw new ValidationError("성적 검증 실패", validation.errors);
    }
    const examScore = await this.scores.save(cycleId, input);
    return { examScore, warnings: validation.warnings };
  }

  /**
   * 성적 단건 조회 — 결과 화면에서 본인 입력 점수를 다시 보여줄 때 사용.
   * (사용자 본인 데이터 반환 — 환산식/입결 비노출 원칙 §8.1과 무관)
   */
  async getById(examScoreId: string): Promise<ExamScore> {
    const examScore = await this.scores.findById(examScoreId);
    if (!examScore) throw new NotFoundError(`exam score ${examScoreId}`);
    return examScore;
  }
}
