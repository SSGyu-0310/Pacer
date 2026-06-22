/**
 * Composition root — 여기서만 도메인 서비스에 인프라 어댑터를 주입한다.
 * core 는 어떤 어댑터도 import하지 않으므로, 교체 지점은 이 파일이다.
 */
import {
  AnalysisService,
  ApplicationPlanService,
  AuthService,
  CompetitorSignalService,
  CycleService,
  NotificationSubscriptionService,
  OutcomeService,
  ReportService,
  ReviewService,
  SavedUnitService,
  ScoreService,
  SimulationService,
} from "@pacer/core";
import type { TargetRepository } from "@pacer/core";
import {
  PrismaAnalysisRepository,
  PrismaApplicationPlanRepository,
  PrismaCompetitorSignalRepository,
  PrismaCycleRepository,
  PrismaNotificationSubscriptionRepository,
  PrismaOutcomeRepository,
  PrismaReportRepository,
  PrismaReviewRepository,
  PrismaSavedUnitRepository,
  PrismaScoreRepository,
  PrismaTargetRepository,
  PrismaUnitRepository,
  PrismaUserRepository,
  prisma,
} from "@pacer/db";
import {
  AnthropicExtractLlmClient,
  AnthropicLlmClient,
  LlmExtractGateway,
  LlmGateway,
  StubExtractLlmClient,
  StubLlmClient,
} from "@pacer/llm";

export function getCycleService(): CycleService {
  return new CycleService(new PrismaCycleRepository(prisma));
}

export function getAuthService(): AuthService {
  return new AuthService(
    new PrismaUserRepository(prisma),
    new PrismaCycleRepository(prisma),
  );
}

export function getScoreService(): ScoreService {
  return new ScoreService(new PrismaScoreRepository(prisma));
}

export function getTargetRepository(): TargetRepository {
  return new PrismaTargetRepository(prisma);
}

export function getAnalysisService(): AnalysisService {
  return new AnalysisService(
    new PrismaCycleRepository(prisma),
    new PrismaScoreRepository(prisma),
    new PrismaTargetRepository(prisma),
    new PrismaUnitRepository(prisma),
    new PrismaAnalysisRepository(prisma),
  );
}

export function getReportService(): ReportService {
  // API 키가 없으면 결정적 스텁 — 게이트웨이의 스키마·금지어 검증은 동일하게 적용된다.
  const apiKey = process.env.ANTHROPIC_API_KEY;
  const client = apiKey
    ? new AnthropicLlmClient(apiKey, process.env.LLM_MODEL_NAME)
    : new StubLlmClient();
  return new ReportService(
    new PrismaCycleRepository(prisma),
    new PrismaScoreRepository(prisma),
    new PrismaTargetRepository(prisma),
    new PrismaAnalysisRepository(prisma),
    new LlmGateway(client),
    new PrismaReportRepository(prisma),
    new PrismaCompetitorSignalRepository(prisma),
  );
}

/** §7.9 점수 시뮬레이션 (P1) — 저장 없는 일회성 엔진 재실행 */
export function getSimulationService(): SimulationService {
  return new SimulationService(
    new PrismaCycleRepository(prisma),
    new PrismaScoreRepository(prisma),
    new PrismaTargetRepository(prisma),
    new PrismaUnitRepository(prisma),
  );
}

/** §10.7 외부 도구 결과 (P2) — 수동 입력 전용 */
export function getCompetitorSignalService(): CompetitorSignalService {
  return new CompetitorSignalService(
    new PrismaCycleRepository(prisma),
    new PrismaCompetitorSignalRepository(prisma),
  );
}

/** §10.8 가/나/다군 조합 (P2) */
export function getApplicationPlanService(): ApplicationPlanService {
  return new ApplicationPlanService(
    new PrismaCycleRepository(prisma),
    new PrismaAnalysisRepository(prisma),
    new PrismaApplicationPlanRepository(prisma),
  );
}

/** §7.11 합불 결과 수집 (P2/Phase4) */
export function getOutcomeService(): OutcomeService {
  return new OutcomeService(
    new PrismaCycleRepository(prisma),
    new PrismaOutcomeRepository(prisma),
  );
}

export function getNotificationSubscriptionService(): NotificationSubscriptionService {
  return new NotificationSubscriptionService(
    new PrismaNotificationSubscriptionRepository(prisma),
  );
}

export function getSavedUnitService(): SavedUnitService {
  return new SavedUnitService(new PrismaSavedUnitRepository(prisma));
}

export function getReviewService(): ReviewService {
  return new ReviewService(new PrismaReviewRepository(prisma));
}

export function getExtractGateway(): LlmExtractGateway {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  const client = apiKey
    ? new AnthropicExtractLlmClient(apiKey, process.env.LLM_EXTRACT_MODEL_NAME)
    : new StubExtractLlmClient();
  return new LlmExtractGateway(client);
}
