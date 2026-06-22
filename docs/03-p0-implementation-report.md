# Pacer P0 구현 보고서 — 1B 계산 엔진 · 1C 분석 서비스 · 1D AI 리포트

작성일: 2026-06-06 · 기준 스펙: `PRODUCT_SPEC.md` v1.1 · 마일스톤: P0(6모 선공개)

## 1. 개요

스캐폴딩(모노레포 8개 워크스페이스, 시그니처 수준 스텁)에서 출발해, P0의 핵심 백엔드 파이프라인을 끝까지 구현했다. 이번 작업으로 다음 흐름이 코드로 완성됐다.

```
성적 입력(§10.2) → 목표 저장(§10.3) → 분석 실행(§10.4, §17.3)
  → 결과 조회(§10.5) → AI 리포트 생성(§10.6, §11)
```

검증 결과: **단위 테스트 97/97 통과, 6개 워크스페이스 전체 `tsc --noEmit` 통과.** 계산 엔진과 서비스는 전부 결정적(같은 입력 = 같은 출력)이며, core 패키지는 Next.js/Prisma/HTTP를 일절 import하지 않는다.

## 2. 1B — 계산 엔진 (§8, §18.1)

### 2.1 구현 함수

`packages/core/src/engine/` 의 스텁 9개를 전부 실제 구현으로 교체했다.

| 함수 | 스펙 | 내용 |
| --- | --- | --- |
| `validateScores` | §8.1-1 | 표준점수 0–200 / 백분위 0–100 / 등급 1–9 / 원점수 0–100 범위, 필수과목(국·수·영·한국사), 절대평가 과목 등급 필수, 중복 과목. 차단성 `errors`와 비차단 `warnings`(선택과목 미입력 등) 분리 |
| `normalizeScores` | §8.1-2 | 과목 맵 구성 + 강·약점 도출. 상대평가 과목은 본인 백분위 평균 ±2, 영어는 절대평가 등급 기준(1등급 강점/4등급 이하 약점) |
| `checkEligibility` | §8.1-3 | 수학 선택 제한(§18.1)·탐구 계열 제한·한국사 최저 등급. 판정 불가(선택과목 미입력)는 보수적으로 불충족 처리(§2.1) |
| `convertScore` | §8.2 | 정확/근사/불가 3분기. 아래 2.2 참조 |
| `compareToHistorical` | §8.3 | `score_gap = user_score − historical_cut_score`. 정확 환산은 환산점 컷, 근사는 백분위 컷과 비교. 기준 부재 시 null(분석 불가) |
| `groupByRecruitmentGroup` | §18.1 | 가/나/다군 분류 헬퍼(P2 원서 조합의 기초) |
| `classifyBand` | §8.3 | 구간 5단계 + 보정요소 7종. 아래 2.3 참조 |
| `scoreConfidence` | §8.4 | 높음/중간/낮음/제한 — 아래 2.4 참조 |
| `generateReasonCodes` | §8.5 | 강점·약점·추천 코드 생성. `@pacer/shared` 컨트롤드 보캐블러리만 사용, 결정적 순서 보장 |

`trend`(P1)·`application-plan`(P2)은 로드맵에 따라 스텁으로 남겼다.

### 2.2 환산 방식 (`convertScore`)

- **정확 환산(exact)**: 규칙이 검수 완료(`verified`/`live`)일 때.
  - `standard`: 국·수·탐 표준점수(만점 200) 가중 평균 → `totalScale`로 스케일
  - `percentile`: 백분위(만점 100) 기반 동일 방식
  - `mixed`: 국·수 표준점수 + 탐구는 백분위×2 근사(변표 근사임을 `approximations: ["inquiry_conversion"]`로 표기 → 신뢰도 '중간'으로 강등)
  - 탐구는 `inquiryPolicy.mode`에 따라 평균/상위 1과목(§18.1), 영어·한국사는 등급별 정책 점수 가감(§18.1)
- **근사 비교(approx)**: 검수 미완료 규칙은 환산식을 쓰지 않고 백분위 가중 합성(만점 100)으로만 비교. `approximations: ["percentile_composite"]` → 신뢰도 '낮음'
- **분석 불가(unsupported)**: `custom` 환산식(P0 미지원), 필요 점수 누락. 조용히 잘못 계산하는 대신 명시적으로 불가 처리(§8.2)

### 2.3 구간 분류 (`classifyBand`)

gap을 만점 100 기준으로 정규화(`gapPer100 = score_gap / scale × 100`)한 뒤, §8.3 보정요소를 결정적 임계값 시프트로 적용한다: 모집인원 변화(±20%), 충원율(100%↑ 완화), 소수 모집단위, 영어 감점 강도×사용자 등급, 탐구 변표 리스크, 데이터 신뢰도, 시험 시점(6모 −0.3 / 9모 −0.15 / 수능 0).

핵심 안전장치: **신뢰도가 낮음/제한이면 '안정' 단정을 금지하고 최대 '적정'으로 캡** — §2.1(해석 우선, 단정 금지)을 엔진 레벨에서 강제한다.

모든 임계값·보정치는 `engine/constants.ts` 한 곳에 모았다. 실데이터(§9.9)가 쌓이면 이 파일만 캘리브레이션하면 된다.

### 2.4 신뢰도 (§8.4 매핑)

| 신뢰도 | 조건 |
| --- | --- |
| 높음 | 정확 환산 + 근사 부분 없음 + 입결 있음 |
| 중간 | 정확 환산이지만 일부 근사(예: 변표 근사) + 입결 있음 |
| 낮음 | 백분위 합성 근사 중심 |
| 제한 | 환산 불가 또는 입결 부재 |

### 2.5 도메인 타입 확장

`domain/entities.ts`에 §9.8/§9.9를 엔진이 소비하는 형태로 추가: `AdmissionRuleData`(scoreType·반영비·영어/한국사/탐구 정책·지원자격·검수상태), `HistoricalRef`(컷·충원·신뢰도), `BandAdjustmentFactors`, `EligibilityResult`, `AnalysisCandidate`, `AnalysisSummary`.

## 3. 1C — 분석 서비스 배선 (§17.3, §10)

### 3.1 AnalysisService

§17.3 처리 흐름 그대로 오케스트레이션: 검증→정규화→목표 로드→후보 로드→자격 판정→환산→입결 비교→신뢰도→구간→reason code→스냅샷 저장. 모집단위 1건 분석은 레포지토리 접근이 없는 순수 함수로 분리해 결정성을 보장했다.

설계 결정:

- **제외는 투명하게 집계**: 분석 불가/자격 미달/입결 부재 단위는 결과에서 제외하되 `summary`(candidates/analyzed/ineligible/unsupported/insufficientData)로 §9.10 `summary_json`에 기록 — §8.2 "분석하지 않는다"를 숨기지 않고 드러낸다.
- **목표 없이도 분석 가능** — 익명 퍼널(§2.6)의 전제. 목표가 있으면 지역·대학 필터로만 활용.
- `snapshot_type ↔ exam_type` 정합성 검사(june_position ↔ june_mock 등).

### 3.2 Prisma 리포지토리 5종 (`packages/db`)

`PrismaCycleRepository` 패턴(ORM 격리)을 따라 Score/Target/Unit/Analysis/Report를 구현했다.

- **Score**: (cycleId, examType) 단위 upsert + 과목 점수 전체 교체(트랜잭션) — 재제출 시 부분 병합으로 인한 불일치 방지
- **Target**: 시험 시점별 upsert(§9.5 "목표는 성적 따라 바뀐다")
- **Unit**: 입시연도·active·목표 대학/지역 필터로 후보 로드, 최신 규칙·입결 join. **규칙 JSON → 도메인 매핑(`rule-mapping.ts`)은 zod 검증을 거치며, 실패 시 rule=null → 분석 불가로 강등** — 관리자 데이터 오류가 조용한 오계산이 되지 않게 했다
- **Analysis**: 스냅샷+결과 트랜잭션 저장. 조회 시 `reason_codes` 문자열 배열을 컨트롤드 보캐블러리로 방어 파싱
- **Report**: §9.13 — `model_name`/`prompt_version` 필수 저장(재현성)

### 3.3 API 라우트 (§10.2–§10.5)

`scores`/`targets`/`analysis/run`/`analysis/{id}/results` 4개 라우트를 501 스텁에서 실제 구현으로 교체했다. 모두 "계약(`@pacer/shared` zod) parse → 서비스 호출 → serialize"만 하는 얇은 어댑터다(백엔드 분리 이음새 유지).

- **소유권**: `authz.ts` — 사이클의 `anon_session_id`와 쿠키 대조. 불일치·부재 모두 404로 응답해 리소스 존재 여부를 노출하지 않는다.
- **오류 매핑**: `ValidationError`→400, `NotFoundError`→404 (`fromDomainError`).
- 결과 응답에 면책 문구(§13.3) 동봉. 환산식·입결 원문은 어떤 응답에도 포함되지 않는다(§8.1).

## 4. 1D — AI 리포트 (§11, §10.6)

### 4.1 LLM Gateway 파이프라인 (`packages/llm`)

```
프롬프트 조립(§11.2) → 모델 호출 → JSON 파싱 → 스키마 검증(§11.3, zod)
  → reason_code 보캐블러리 검증(§8.5) → 면책 문구 보강(§13.3)
  → 금지어 필터(§11.4) → model_name/prompt_version 부착(§9.13)
```

- **클라이언트 추상화**: `LlmClient` 인터페이스에 `AnthropicLlmClient`(fetch 기반, `ANTHROPIC_API_KEY` 있을 때)와 `StubLlmClient`(결정적 템플릿, 개발/테스트/CI)를 구현. **어느 쪽이든 게이트웨이의 동일한 검증을 통과해야 한다** — 스텁이라고 검증을 우회하지 않는다.
- **출력 검증**: JSON 아님/스키마 위반/임의 reason_code/금지어 → 전부 throw(차단). 통과 못한 리포트는 저장되지 않는다.
- **프롬프트**: 6종 리포트 타입별 실제 한국어 템플릿. 공통 규칙에 §11.1 역할 제한(계산 금지·단정 금지), §11.4 금지/§11.5 허용 표현, §11.3 출력 형식을 명시. `PROMPT_VERSION = "v1"`.
- 주의점 하나: §13.4 AI 고지 원문에 금지어("반드시")가 포함되어 있어, AI 고지는 리포트 본문(필터 대상)이 아닌 **라우트 응답의 별도 필드**로 동봉한다. 면책 문구(§13.3)는 금지어가 없으므로 리포트 `warnings`에 직접 포함된다.

### 4.2 ReportService (`packages/core`)

엔진 결과 → §11.2 구조화 입력 조립(순수 함수 `buildLlmInput`): 구간 분포, reason code 빈도 상위 5개(동률은 사전순 — 결정성), 목표 대학 기준 접근도(가장 유리한 구간), 시험 시점별 고지 문구(6모/9모/가채점/실채점). `parent_summary_report`는 role=parent. `report_type ↔ exam_type` 정합성 검사. **LLM에 점수·확률 계산을 위임하는 입력은 없다**(§8.1).

### 4.3 라우트 (§10.6)

`POST /api/cycles/{cycleId}/reports` — 검증된 리포트를 저장 후 §10.6 형태(snake_case)로 반환, `disclaimer`(§13.3)·`ai_usage_notice`(§13.4)·`model_name`·`prompt_version` 동봉.

## 5. 테스트 (§18.1, §18.2)

총 **97개** — 전부 통과.

- **엔진 60개**: §18.1 필수 케이스 전부(표준점수/백분위 반영, 영어·한국사 감점, 탐구 평균·상위1, 수학 선택 제한, 모집군 분류, score_gap) + 구간 보정 7종 + 신뢰도 표 + reason code 규칙 + 결정성
- **AnalysisService 10개**: 5종 후보(정상/규칙없음/자격미달/입결없음/근사)의 분류·집계, 목표 필터 전달, 타입 정합성, NotFound, 결정성
- **ReportService 6개**: §11.2 입력 조립 정확성, 저장 메타(§9.13), role 분기, 정합성 오류
- **LLM Gateway 10개**: §18.2 전 항목 — 금지어 미포함, reason code 기반 설명, 같은 입력 일관 결과, 학부모용 문체(입시 용어 미사용), 합격 단정 없음, 면책 문구 포함 + 악성 출력(금지어/비JSON/스키마 위반/임의 코드) 차단

## 6. 지킨 원칙 → 코드 매핑

| 원칙 | 강제 지점 |
| --- | --- |
| 엔진이 계산, LLM은 설명만(§8.1) | 엔진은 순수 함수, LLM 입력은 요약뿐. 게이트웨이가 출력 스키마 강제 |
| core의 인프라 비의존 | `grep` 검증: core/llm에 next·prisma·db import 0건. Prisma는 `packages/db`에만 |
| 컨트롤드 보캐블러리(§8.5) | enum·reason code는 `@pacer/shared` 단일 정의. DB 조회·LLM 출력 양쪽에서 zod 방어 파싱 |
| 환산식·입결 서버 전용(§8.1) | 규칙 원문은 `UnitRepository`/`rule-mapping`까지만. API 응답은 결과+구간+코드만 |
| 합격 단정 금지(§2.1, §11.4) | 금지어 필터(위반 시 저장 차단) + 저신뢰 시 '안정' 캡 + 허용 표현 기반 문구 |
| 면책·AI 고지(§13.3/13.4) | 결과·리포트 응답 동봉, 게이트웨이가 리포트 warnings에 면책 자동 보강 |
| 6모 코드의 9모/수능 재사용(§19) | exam_type·snapshot_type 파라미터화 — 동일 코드로 3개 시점 처리 |

## 7. 개발 환경 메모

작업 환경(샌드박스)이 npm 레지스트리를 차단해 vitest를 설치할 수 없었다. 대응:

- vitest는 `@pacer/core`·`@pacer/llm` devDependency와 `test` 스크립트로 **정식 추가**했다. 로컬에서 `pnpm install` 후 `pnpm --filter @pacer/core test`, `pnpm --filter @pacer/llm test`가 그대로 동작한다.
- 샌드박스 검증용으로 `node_modules/vitest`에 호환 심(shim)을 두고 tsc 컴파일 후 실행했다(테스트 코드는 표준 vitest API). `pnpm install` 시 실제 vitest로 대체된다. 같은 이유로 `packages/db`, `packages/llm`의 `node_modules/zod` 심링크를 수동 생성했다 — 역시 `pnpm install`이 정리한다.

## 8. 남은 작업

- **1E (P0 잔여)**: 알림 구독 라우트(§10.9)+`NotificationService`(§17.5 채널 우선순위: 알림톡→이메일→웹푸시), 페이지 UI(점수 입력 폼→분석 결과→리포트), OG 공유 카드, PWA 셸 마무리, 관리자 데이터 도구(§12), 레퍼런스 데이터 시딩
- **P1**: `analyzeTrend`(6모↔9모 diff), 점수 시뮬레이션, 결제(web PG), PDF
- **P2**: 교차검증 리포트 데이터 연동(§7.7.4 수동 입력), `buildApplicationPlan`(가/나/다군), 합불 수집
- **기술 부채**: 캘리브레이션 상수의 실데이터 보정, `prevQuota`(모집인원 변화) 데이터 연결, mixed 변표 근사를 실제 변환표준점수 테이블로 교체, 스냅샷 결과 조회의 사이클 소유권 검사 추가

## 9. 열린 결정

- **DB 공급자(Supabase vs Neon)** — 마이그레이션·인증 방식에 영향. 현재까지의 작업은 DB 없이 검증 가능하나, 시딩·E2E 전에 확정 필요.
- 운영 LLM 모델·비용 정책(현재 기본값 `claude-sonnet-4-6`, 키 없으면 스텁).
