# Pacer 구현 계획 (v1)

> 근거: 스펙 §19 로드맵, §20 P0/P1/P2, §18 테스트, §16.5 이벤트. 폴더 구조는 `01-architecture.md` 참조.
> 시점 기준: 오늘 2026-06-06. **2027학년도 입시 사이클**. 6모(6월 모평)가 임박/진행 → **P0 6모 선공개가 최우선 마감**.
> 원칙(§19): *6모에서 만든 것은 9모·수능에서 그대로 재사용*. 6모 전용 throwaway 코드 금지.

---

## Milestone 0 — 스캐폴딩 & 기반 (Phase 0, §19)

> 목표: PWA 골격 + 배포 파이프라인 + 도메인 경계. **코드 작성 전 스택 확정**(완료: Next.js 풀스택 + Prisma, repository 격리).

**워크스트림**
- 모노레포 부트스트랩: pnpm workspaces + Turborepo, `packages/config`(tsconfig/eslint/tailwind), 경계 강제 ESLint 규칙(§01-arch 3절 금지 의존).
- `packages/shared`: enums, reason-codes, `contracts/`(§10 Zod 스키마), `disclaimers.ts`(§13.3/13.4 원문), `analytics-events.ts`(§16.5).
- `packages/db`: `schema.prisma`(§9 전체 모델) + 첫 마이그레이션 + repository 포트 스텁. Supabase/Neon Postgres 연결.
- `packages/core/ports`: repository/LlmReporter/Notifier/Clock 인터페이스 정의.
- `apps/web`: Next.js App Router, Tailwind, `manifest.ts`(standalone, start_url `/dashboard?source=pwa`), Service Worker(앱셸 캐시), 익명 세션(`anon_session_id`) → 가입 전환 토대.
- 인증: 카카오/이메일 로그인 + 익명 세션(§17.2 Auth).
- 관측: PostHog(이벤트), Sentry. 배포: Vercel + Cloudflare, S3 호환 스토리지(OG/PDF용).

**완료 기준(DoD)**
- Lighthouse PWA 체크 통과(설치 가능·오프라인 셸·매니페스트 유효, §17.6/§18.5).
- 익명 세션으로 `POST /api/cycles` 동작(빈 서비스라도 계약·검증 통과).
- `landing_view`/`cta_click` 이벤트 적재 확인.

---

## Milestone 1 — P0: 6모 선공개 (Phase 1, §20 P0) ★최우선

> 목표(§19): 유저 확보 · 데이터 구조 검증 · 기본 분석 가치 검증. **여기서 만든 엔진·모델·리포트 파이프라인이 9모/수능의 토대.**

### 1A. 입력 퍼널 (익명 우선)
- 랜딩(§7.1): SSR + OG 메타, 메인/서브 카피·CTA(§22), 면책 노출.
- 사이클 생성(§7.2, §10.1): 익명 세션 포함. 알림 동의 화면(채널 우선순위 §7.2).
- 성적 입력(§7.3, §10.2): 시험별 입력 모드, 입력 검증/오류 처리, 폼 임시상태 보존(SW). 3분 내 완료 목표.
- 목표 설정(§7.4, §10.3): 지원 성향(risk_profile), 수시/정시 고민 정도.

### 1B. 계산 엔진 (§8) — `packages/core/engine`
- `validate` → `normalize` → `eligibility` → `convert`(정확/근사/불가) → `compare`(score_gap) → `band`(안정~위험) → `confidence`(높음~제한) → `reason-codes`(§8.5).
- 결정적·순수 함수. **단위 테스트가 1급 산출물**(§18.1: 표준점수/백분위/영어감점/한국사/탐구평균·상위1/수학선택제한/모집군/점수차).
- 환산식·입결은 서버 전용. 클라이언트엔 결과 + 출처 링크만(§8.1).

### 1C. 분석 실행 & 결과 (§10.4/10.5, §7.6)
- `analysis.service`로 §17.3 흐름 오케스트레이션 → `AnalysisSnapshot`/`AnalysisResult` 저장.
- 결과 화면(§7.6): 구간 라벨, 신뢰도, 필수 문구(분석불가 시 §8.2 문구). band_distribution 반환.

### 1D. AI 리포트 (§11) — `packages/llm`
- 입력 구조화(§11.2) → LLM 호출 → 출력 구조(§11.3, student_summary + parent_summary 동시) → **금지어 필터(§11.4)** 통과 필수 → `model_name`/`prompt_version` 기록.
- 6모 리포트(`june_position_report`) + 학부모 요약(`parent_summary_report`).
- 부하 대비 비동기 생성 토대(P0는 인라인 허용, 큐는 P1).

### 1E. 저장·공유·재방문·관리자
- 결과 저장(`SavedAdmissionUnit`), 공유 카드 OG 이미지 생성(`/api/og`).
- **9모 알림 신청(§10.9)**: 알림톡 1순위 / 이메일 2순위 / 웹푸시(설치자) 3순위. 웹푸시 권한은 *첫 결과 확인 후*에 요청(§17.4).
- 홈 화면 추가 권유: `beforeinstallprompt` 캡처 후 첫 결과 이후 노출, iOS는 "공유→홈화면 추가" 안내 카드.
- 관리자 데이터 도구(§12): University/AdmissionUnit/AdmissionRule/HistoricalOutcome 입력·검수(`verified_status`).
- 면책(§13.3)·AI 고지(§13.4) 모든 결과/리포트에.

**DoD (= §18 테스트 + §16.5 이벤트)**
- 계산 테스트 전 항목 통과(§18.1). 리포트 금지어 0 + 동일 입력 일관성 + 면책 포함(§18.2).
- 모바일 3분 내 입력 / 분석 10초 내 표시(§18.3).
- PWA/모바일 테스트(§18.5): 안드 Chrome 웹푸시 딥링크, iOS 미설치 시 알림톡/이메일 대체 도달, OG 리치 프리뷰.
- 이벤트 적재: `cycle_created`→`score_submit`→`analysis_success`→`report_view`→`report_saved`→`reminder_opt_in(channel)`→`share_card_created`→`pwa_installed`.

---

## Milestone 2 — P1: 9모 베타 (Phase 2, §20 P1)

> 목표: 재방문 검증 · 성적 변화 추적 · 유료화 테스트. **재사용 우선**: 6모 코드 위에 diff/시뮬/결제만 얹는다.

- 6모↔9모 비교(`september_change_report`) + 성적 변화 그래프 + 목표 접근도 변화 — `engine/trend.ts`.
- 점수 시뮬레이션(§7.9): 가상 점수 → 엔진 재실행(서버), 환산식 노출 없이 결과만.
- 유료 리포트: **웹 PG(카드/카카오페이/네이버페이)**, 앱스토어 IAP 회피(§14.1). 결제 webhook → 리포트 PDF(S3).
- 수능 알림 신청 + **채널별 재방문 기여 분석**(§16.5 `return_from_reminder` channel 파라미터).
- `workers/` 실체화: LLM 리포트 비동기 큐 + 알림 배치(§18.4 부하 대비).
- 리포트 PDF 생성 파이프라인.

**DoD**: 6모 데이터 보유 유저의 9모 재방문→변화 리포트 생성, 결제 성공/실패 처리, 채널별 도달·전환 측정 대시보드.

---

## Milestone 3 — P2: 수능 메인 (Phase 3, §20 P2)

> 목표: 본격 매출 · 교차검증 차별화 · 원서 조합.

- 정밀 환산 확대(상위권·의치한약수·유료 대상 대학, §8.2).
- 외부 도구 수동 입력(§7.7.4, §10.7): 진학사/고속/텔레그노시스 — **수동 전용, 자동 스크래핑 금지**(`CompetitorSignal`).
- 교차검증 리포트(`cross_validation_report`): 외부 결과와 자사 분석 불일치 해석(§11.1).
- 가/나/다군 조합(§7.10, §10.8): `engine/application-plan.ts` → `ApplicationPlan`(stable/balanced/aggressive).
- 결제 본격화 + 컨설턴트 검수 옵션(데스크톱 우선, §4.4).
- 부하 대비(§18.4): 기본 분석 우선 + LLM 비동기 + 캐시 + 결제 장애 대비 + 알림 대량 배치.

**DoD**: 교차검증 리포트 금지어/단정 0(§11.4 "진학사보다 정확" 등 차단), 조합 화면 금지사항(§7.10) 준수, 수능 시즌 부하 테스트 통과.

---

## Milestone 4 — Phase 4: 수능 이후 (§19) / 데이터 해자

- 실제 지원 대학 저장 + 합불 인증(§7.11, `FinalOutcome`) + 리워드.
- 익명 데이터셋 구축 → 다음 입시연도 예측력 개선. 개인정보 원칙(§13.1, §7.11) 준수.

> Phase 5(네이티브 앱)는 **조건부**(§1.4 트리거 충족 시): 추합 실시간 알림 ROI 입증 + 웹푸시 도달 한계 확인. 기존 PWA 백엔드/모델 재사용.

---

## 횡단 관심사 (모든 마일스톤 공통)

| 관심사 | 규칙 |
|---|---|
| **언어/카피** | 사용자 문구·면책·AI 고지는 한국어, 법무 문구는 스펙 원문 그대로(§13.3/13.4). `packages/shared/disclaimers.ts` 단일 관리. |
| **컨트롤드 보캐블러리** | enum·reason_code는 `packages/shared`에서만. 새 reason_code는 §8.5 테이블 확장(임의 문자열 금지). |
| **분석 이벤트** | §16.5 이름 그대로 사용(`reminder_opt_in`/`return_from_reminder`는 channel 파라미터 필수). |
| **신뢰도/불확실성** | 하드 합격 확률 단정 금지(§2.1). 신뢰도 라벨·근사/불가 문구 항상 노출. |
| **두 목소리** | 모든 리포트 `student_summary` + `parent_summary` 동시 생성(§11.3). |
| **재현성** | 모든 `StrategyReport`에 `model_name`/`prompt_version` 기록. |
| **재사용** | 6모 산출물은 9모·수능에서 그대로 재사용(§19). 시점 분기는 데이터/UX 레이어에서만. |

---

## 권장 진행 순서 (다음 액션)

1. **ADR 작성** — `docs/adr/0001-stack-and-boundaries.md`에 이번 스택/경계 결정 기록.
2. **Milestone 0 스캐폴딩** — 모노레포 + `schema.prisma`(§9) + `packages/shared/contracts`(§10) + PWA 셸. (착수 전 한 번 더 확인 권장: pnpm/Turborepo 채택, Supabase vs Neon.)
3. 그 다음 Milestone 1을 **1B(엔진) → 1C(분석) → 1D(리포트)** 순으로. 엔진+테스트가 먼저여야 리포트가 의미를 가진다.
