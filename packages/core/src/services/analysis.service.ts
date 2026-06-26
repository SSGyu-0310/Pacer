import type { Band, ExamType, SnapshotType } from "@pacer/shared";
import type {
  AnalysisCandidate,
  AnalysisSnapshotMeta,
  AnalysisSummary,
  BandAdjustmentFactors,
  NormalizedScores,
  UnitAnalysis,
} from "../domain/entities";
import {
  SMALL_QUOTA_THRESHOLD,
  checkEligibility,
  classifyBand,
  compareToHistorical,
  convertScore,
  englishPenaltySpreadPer100,
  generateReasonCodes,
  normalizeScores,
  scoreConfidence,
  validateScores,
} from "../engine";
import { NotFoundError, ValidationError } from "../errors";
import type {
  AnalysisRepository,
  CycleRepository,
  ScoreRepository,
  TargetRepository,
  UnitRepository,
} from "../ports";

/** snapshot_type ↔ exam_type 정합성 (§9.10) */
const SNAPSHOT_EXAM: Record<SnapshotType, ExamType> = {
  june_position: "june_mock",
  september_change: "september_mock",
  csat_final: "csat",
};

const EMPTY_DISTRIBUTION: Record<Band, number> = {
  stable: 0,
  match: 0,
  reach: 0,
  challenge: 0,
  risk: 0,
};

/**
 * §17.3 분석 처리 흐름 오케스트레이션.
 * 2 검증 → 3 정규화 → 4 목표 로드 → 5 후보 로드 → 6 eligibility →
 * 7 convert → 8 compare → 9 band → 10 confidence → 11 reason-codes → 12 스냅샷 저장.
 * (13 LLM 리포트는 ReportService에서 별도/비동기 — 엔진이 계산, LLM은 설명만 §8.1.)
 *
 * 제외 정책(요약에 투명 집계 — §8.2 분석 불가는 숨기지 않는다):
 * - 규칙 없음/custom/점수 부족 → unsupported
 * - 지원 자격 미충족(미확인 포함, 보수적 §2.1) → ineligible
 * - 입결 부재로 비교 불가 → insufficientData
 */
export class AnalysisService {
  constructor(
    private readonly cycles: CycleRepository,
    private readonly scores: ScoreRepository,
    private readonly targets: TargetRepository,
    private readonly units: UnitRepository,
    private readonly analyses: AnalysisRepository,
  ) {}

  async run(
    cycleId: string,
    examScoreId: string,
    type: SnapshotType,
  ): Promise<{
    snapshotId: string;
    bandDistribution: Record<Band, number>;
    summary: AnalysisSummary;
  }> {
    const cycle = await this.cycles.findById(cycleId);
    if (!cycle) throw new NotFoundError(`cycle ${cycleId}`);

    const examScore = await this.scores.findById(examScoreId);
    if (!examScore || examScore.cycleId !== cycleId) {
      throw new NotFoundError(`exam score ${examScoreId}`);
    }
    if (SNAPSHOT_EXAM[type] !== examScore.examType) {
      throw new ValidationError(
        `analysis_type(${type})과 exam_type(${examScore.examType})이 일치하지 않습니다`,
      );
    }

    // 2. 검증
    const validation = validateScores(examScore);
    if (!validation.valid) {
      throw new ValidationError("성적 검증 실패", validation.errors);
    }

    // 3. 정규화
    const normalized = normalizeScores(examScore);

    // 4. 목표 로드(없어도 분석 가능 — 익명 퍼널 §2.6)
    const target = await this.targets.findLatest(cycleId, examScore.examType);

    // 5. 후보 모집단위 로드
    const targetUniversityIds = target?.targetUniversityIds.length
      ? target.targetUniversityIds
      : undefined;
    const targetUnitIds = target?.targetUnitIds.length
      ? target.targetUnitIds
      : undefined;
    const candidates = await this.units.loadCandidates({
      admissionYear: cycle.admissionYear,
      track: cycle.track,
      preferredRegions: target?.preferredRegions.length
        ? target.preferredRegions
        : undefined,
      targetUniversities: !targetUniversityIds && target?.targetUniversities.length
        ? target.targetUniversities
        : undefined,
      targetUniversityIds,
      targetUnitIds,
    });

    // 6–11. 모집단위별 분석 (순수 엔진 함수만 — 결정적)
    const summary: AnalysisSummary = {
      candidates: candidates.length,
      analyzed: 0,
      ineligible: 0,
      unsupported: 0,
      insufficientData: 0,
    };
    const results: UnitAnalysis[] = [];

    for (const candidate of candidates) {
      const r = analyzeUnit(candidate, normalized, examScore.examType);
      if (r.kind === "ok") {
        results.push(r.analysis);
        summary.analyzed++;
      } else {
        summary[r.kind]++;
      }
    }

    const bandDistribution = { ...EMPTY_DISTRIBUTION };
    for (const r of results) bandDistribution[r.band]++;

    // 12. 스냅샷 저장
    const { snapshotId } = await this.analyses.saveSnapshot({
      cycleId,
      examScoreId,
      snapshotType: type,
      summary,
      bandDistribution,
      results,
    });

    return { snapshotId, bandDistribution, summary };
  }

  /** 결과 조회 (§10.5) */
  async getResults(snapshotId: string): Promise<UnitAnalysis[]> {
    const results = await this.analyses.findResults(snapshotId);
    if (results === null) throw new NotFoundError(`snapshot ${snapshotId}`);
    return results;
  }

  /** 결과 조회 전 소유권 확인용 메타 (§10.5) */
  async getSnapshotMeta(snapshotId: string): Promise<AnalysisSnapshotMeta> {
    const meta = await this.analyses.findSnapshotMeta(snapshotId);
    if (meta === null) throw new NotFoundError(`snapshot ${snapshotId}`);
    return meta;
  }
}

/**
 * 모집단위 1개 분석 — 순수 함수(레포지토리 접근 없음).
 * AnalysisService와 SimulationService(§7.9)가 같은 파이프라인을 공유한다.
 */
export function analyzeUnit(
  candidate: AnalysisCandidate,
  normalized: NormalizedScores,
  examType: ExamType,
):
  | { kind: "ok"; analysis: UnitAnalysis }
  | { kind: "ineligible" | "unsupported" | "insufficientData" } {
  const { unit, rule, historical, quota, prevQuota } = candidate;

  if (!rule) return { kind: "unsupported" };

  // 6. 지원 조건 판정 — 미충족은 제외 (§8.1-3)
  const eligibility = checkEligibility(rule.eligibility, normalized);
  if (!eligibility.eligible) return { kind: "ineligible" };

  // 7. 환산점수
  const converted = convertScore(rule, normalized);
  if (converted.method === "unsupported" || converted.convertedScore === null) {
    return { kind: "unsupported" };
  }

  // 8. 입결 비교
  const compared = compareToHistorical(converted, historical);
  if (compared.scoreGap === null) return { kind: "insufficientData" };

  // 10. 신뢰도 (band 보정 입력이므로 먼저 산출)
  const confidence = scoreConfidence({
    method: converted.method,
    hasApproximations: converted.approximations.length > 0,
    hasHistorical: historical !== null,
  });

  // 9. 구간 분류 (§8.3 보정 요소)
  const smallQuota = quota !== null && quota < SMALL_QUOTA_THRESHOLD;
  const factors: BandAdjustmentFactors = {
    examType,
    quotaChangeRatio:
      quota !== null && prevQuota !== null && prevQuota > 0
        ? (quota - prevQuota) / prevQuota
        : null,
    additionalPassRate:
      historical?.additionalPass != null && quota !== null && quota > 0
        ? historical.additionalPass / quota
        : null,
    smallQuota,
    englishPenaltySpreadPer100: englishPenaltySpreadPer100(rule),
    userEnglishGrade: normalized.bySubject.get("english")?.grade,
    scienceConversionRisk: rule.inquiryPolicy.conversionRisk ?? false,
    dataConfidence: confidence,
  };
  const band = classifyBand({
    scoreGap: compared.scoreGap,
    scale: converted.scale ?? rule.totalScale,
    factors,
  });

  // 11. reason codes (§8.5)
  const { reasonCodes, warnings } = generateReasonCodes({
    examType,
    normalized,
    rule,
    converted,
    band,
    confidence,
    eligibility,
    smallQuota,
  });

  return {
    kind: "ok",
    analysis: {
      unit,
      convertedScore: converted.convertedScore,
      historicalReferenceScore: compared.historicalReferenceScore,
      scoreGap: compared.scoreGap,
      band,
      confidence,
      reasonCodes,
      warnings,
    },
  };
}
