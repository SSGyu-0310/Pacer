# Pacer P1(9모)·P2(수능) 기반 구축 보고서

작성일: 2026-06-12 · 기준: `02-implementation-plan.md` Milestone 2/3, P0 코드베이스(`03-p0-implementation-report.md`)

## 1. 목적과 범위

6모(P0) 파이프라인 위에 **9모·수능 시점에 필요한 백엔드 코어를 미리 깔아두는 것**이 목적이다.
P0의 원칙(§19 "6모 산출물은 9모·수능에서 그대로 재사용")에 따라 새 시점 전용 코드를 만들지 않고,
기존 엔진·서비스·계약 패턴을 확장했다. **엔진·서비스·포트·DB 어댑터·API 라우트·테스트**까지가 이번 범위이고,
결제(web PG)·PDF·workers 큐·UI 페이지는 의도적으로 제외했다(§5 남은 작업).

검증: **단위 테스트 162개 전부 통과**(P0 97개 회귀 포함), shared/core/llm/db/apps-web 전체 `tsc --noEmit` 통과, ESLint 0 경고.

## 2. P1 — 9모 베타 기반

### 2.1 `engine/trend.ts` — 6모↔9모 변화 분석 (§7.7.2)

스텁을 실구현으로 교체. 순수·결정적 함수 `analyzeTrend(prev, curr, targetUniversities)`:

| 출력 | 내용 |
| --- | --- |
| `subjects` | 과목별 변화 — 두 시험 공통 지표 중 **백분위 > 표준점수 > 등급** 우선, 등급은 방향 반전 |
| `transitions` | 모집단위별 구간 전이(unitId 매칭): improved/declined/entered(새 후보)/dropped(빠진 후보) |
| `targetApproach` | 목표 대학 접근도(가장 유리한 구간, §6.4)의 prev/curr/방향 |
| 분포 | prev/curr band distribution + 개선/악화 카운트 |

`mostFavorableBand`·`bandFavorability`(유불리 순서)를 엔진으로 이동해 ReportService의 중복 로직을 제거 — 접근도 판정 기준이 한 곳이 됐다.

### 2.2 `engine/simulate.ts` + `SimulationService` — 점수 시뮬레이션 (§7.9)

- `applyAdjustments`: delta(`percentile/standardScore/grade`)와 직접 입력(override)을 §18.1 범위로 클램프해 적용. 백분위가 바뀐 상대평가 과목은 **9등급제 누적 백분위(`GRADE_PERCENTILE_FLOORS`)로 등급 재산출**(등급 직접 지정 시 사용자 의도 우선). 없는 지표는 만들어내지 않는다.
- `SimulationService.run`: 기준선과 시뮬레이션을 **같은 후보 데이터로 즉석 재계산**(저장 스냅샷과 비교하면 레퍼런스 갱신 시점에 따라 사과/배 비교가 되므로). `AnalysisService.analyzeUnit`을 export로 바꿔 **분석과 동일한 순수 파이프라인을 공유**한다.
- 출력(§7.9): 적정 이상 진입 수, 구간 변화 목록, 접근도 변화, **가장 효율적인 과목**(과목별 단독 적용 재실행 → 구간 개선 수 비교, 동률은 과목 enum 순), **주의할 과목**(시뮬레이션 후에도 남는 약점 reason code 매핑).
- 결과는 **저장하지 않는다**(일회성). 응답에 §7.9 주의 문구(`SIMULATION_NOTICE`, shared/disclaimers) 항상 동봉. 환산식 노출 없음(§8.1).
- 라우트: `POST /api/cycles/{cycleId}/simulations` (§10에 없던 신규 — 계약은 `runSimulationRequest/Response`).

### 2.3 september_change_report 배선 (§7.7.2)

`ReportService`가 9모 변화 리포트 생성 시 6모 성적(`ScoreRepository.findByExamType`)과 6모 스냅샷(`AnalysisRepository.findLatestSnapshotMeta("june_position")`)을 로드해 `analyzeTrend` 결과를 §11.2 입력(`scoreSummary.trend`, 구조화 수치)으로 전달한다. **6모 기록이 없으면 trend=null + 고지 문구 추가**(§5.2 — 9모에 처음 온 유저도 리포트는 받는다). LLM에 계산을 위임하지 않는 원칙은 그대로 — trend도 엔진이 계산한 수치만 넘긴다.

## 3. P2 — 수능 메인 기반

### 3.1 `engine/cross-validate.ts` + CompetitorSignal 경로 (§7.7.4, §10.7)

- `CompetitorSignalService` + `POST/GET /api/cycles/{cycleId}/competitor-signals`: **수동 입력 전용**(자동 스크래핑 금지 명시). value_type별 검증(칸수 1~8 정수, 확률 0~100, 색상 20자, 메모 500자).
- `crossValidate(results, signals)`: 외부 값 → 구간 **보수적 휴리스틱 v1**(`constants.ts`: `KANSU_TO_BAND`, `GOSOK_COLOR_TO_BAND`, `PROBABILITY_BAND_FLOORS`)으로 근사한 뒤 자체 분석과 **agree(동일)/near(인접)/disagree(2구간↑)/uncertain(비교 불가)** 분류. 메모는 구간으로 환원하지 않는다. ★ 매핑은 일치/불일치 분류 전용 — 정확도 우열 판정에 쓰지 않는다(§11.1). 실데이터가 쌓이면 constants만 캘리브레이션.
- `cross_validation_report`: 신호가 없으면 ValidationError(수동 입력 안내). LLM 입력 `competitorComparison`은 **불일치 우선 최대 10건**(프롬프트 비대 방지) + 합계.

### 3.2 `engine/application-plan.ts` + `ApplicationPlanService` — 가/나/다군 조합 (§7.10, §10.8)

- 전략 매트릭스(§7.10 표 그대로, `STRATEGY_BAND_MATRIX`): 안정형 가안정/나적정/다소신 · 균형형 가적정/나적정/다소신 · 공격형 가안정/나소신/다도전. `custom`은 군당 1개 이하 사용자 선택을 그대로 배치.
- 군 내 선택은 결정적: 목표 구간에서 score_gap 최대(동률 unitId 사전순) → 없으면 **보수적(안정 쪽) 인접 구간 우선 대체** + fallback 표시 + 경고. 군에 후보가 없으면 null + 경고(조용히 만들어내지 않음).
- 요약: 전체 리스크(low/medium/high), 가장 위험/안정 군, §7.10 **허용 표현만 쓰는 결정적 문구**("리스크 분산 관점에서 … 참고용"). 금지 표현 부재를 테스트로 고정.
- 서비스는 **최신 분석 스냅샷 결과를 재사용**(재계산 없음). 분석에 없는 후보는 `skippedUnitIds`로 투명 보고(§8.2). `ApplicationPlan`(§9.15) 저장 시 summary_json에 조합 전체 보존.

### 3.3 `OutcomeService` — 합불 수집 (§7.11, §9.16)

모순 데이터 차단(미지원+합불, 예비번호는 '예비'만, 등록은 '합격'만). `(cycleId, unitId)` 재제출은 **갱신 처리**(데이터셋 오염 방지). 라우트 `POST/GET /api/cycles/{cycleId}/outcomes` (신규). 인증자료는 URL만 보관 — 업로드·익명화 파이프라인은 Phase4.

## 4. 횡단 변경

| 위치 | 내용 |
| --- | --- |
| `shared/contracts.ts` | `runSimulationRequest/Response`, `createCompetitorSignalResponse`+목록, `submitOutcomeRequest/Response`+목록 추가 |
| `shared/disclaimers.ts` | `SIMULATION_NOTICE`(§7.9 주의 문구 원문) |
| `core/domain` | Trend/Simulation/CrossValidation/ApplicationPlan/FinalOutcome 도메인 타입, `LlmReportInput`에 구조화 `trend`·`competitorComparison` |
| `core/ports` | `ScoreRepository.findByExamType`, `AnalysisRepository.findLatestSnapshotMeta`, `CompetitorSignalRepository`/`ApplicationPlanRepository`/`OutcomeRepository` 신설 |
| `packages/db` | 위 포트의 Prisma 구현 3종 신설 + score/analysis 파인더 (스키마 변경 없음 — §9 모델 그대로) |
| `packages/llm` | 스텁 클라이언트가 trend/교차검증 입력을 결정적으로 렌더(금지어 필터 동일 통과) |
| `apps/web` | 라우트 4개(simulations·competitor-signals·application-plans·outcomes) + container 주입. 모두 "계약 parse → 서비스 → serialize" 어댑터 패턴 유지 |
| 테스트 | 엔진 4파일·서비스 5파일 신규(65개). 샌드박스 vitest 심에 `toMatchObject`/`resolves` 보강(로컬 `pnpm install` 시 실제 vitest로 대체 — 영향 없음) |

분석 이벤트(§16.5)는 이미 enum에 있던 `competitor_signal_added`/`application_plan_created`/`final_outcome_submitted`를 클라이언트에서 쏘면 된다(서버 변경 불요).

## 5. 남은 작업 (이번에 의도적으로 제외)

- **결제(web PG)**: PG사 선정(토스/카카오/네이버 등)이 선행 — 결정 후 webhook 라우트 + 유료 리포트 게이팅. §14.1(IAP 회피) 유지.
- **PDF 파이프라인 + S3**: 유료 리포트 산출물. 학부모용 최종 PDF(§3.4)에 면책·AI 고지 필수.
- **workers/ 실체화**: LLM 비동기 큐 + 알림 대량 배치(§18.4 수능 부하). P0 인라인 생성은 P1 트래픽까지는 동작.
- **UI**: simulate(§7.9)·plan(§7.10)·outcome(§7.11) 페이지, 9모 대시보드 분기(§7.5).
- **수능 알림 이벤트**: `notificationEvent` enum이 `september_mock_open`뿐 — 수능 시즌 이벤트(성적표 알림 등) 추가 필요.
- **휴리스틱 캘리브레이션**: 칸수/색상/확률 매핑(v1)과 조합 리스크 임계값을 실데이터로 보정.
- 기존 기술 부채(P0 보고서 §8): mixed 변표 근사 교체, prevQuota 연결 등.

## 6. 원칙 준수 확인

- **엔진이 계산, LLM은 설명만(§8.1)**: trend/교차검증/조합 전부 엔진 산출 → LLM 입력은 수치·분류뿐.
- **환산식·입결 서버 전용(§8.1)**: 시뮬레이션 응답도 결과·구간만.
- **수동 입력 전용(§7.7.4)**: CompetitorSignal 쓰기 경로는 §10.7 사용자 입력 하나.
- **단정 금지(§2.1, §11.4)**: 조합 요약·스텁 렌더 문구 전부 허용 표현 기반, 테스트로 고정.
- **컨트롤드 보캐블러리**: 새 enum 없음(기존 §9 enum 재사용), reason code 테이블 무변경.
- **익명 퍼널(§2.6)**: 새 라우트 전부 기존 `authorizeCycle`(익명 세션) 그대로.
