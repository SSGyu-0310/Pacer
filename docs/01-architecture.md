# Pacer 폴더 아키텍처 (v1)

> 근거: `PRODUCT_SPEC.md` (§8 계산 엔진, §9 데이터 모델, §10 API, §11 AI, §17 기술 아키텍처) + `CLAUDE.md`.
> 스택 결정: **Next.js 풀스택으로 시작**, 단 **내부 구조는 백엔드(FastAPI 등) 분리가 가능한 경계로 설계**. ORM은 **Prisma를 repository 포트 뒤에 격리**.

---

## 1. 설계 원칙 (불변 규칙)

이 9개는 스펙에서 도출한 "깨면 안 되는" 제약이다. 모든 폴더 경계는 이걸 강제하기 위해 존재한다.

1. **AdmissionCycle 중심 스키마(§9).** 모든 데이터는 `User`가 아니라 `AdmissionCycle`에 매달린다. `User`는 nullable, `anon_session_id`가 1급 시민. 익명 세션에서 데이터 생성 → 나중에 가입 전환.
2. **계산 엔진 ≠ LLM, 엄격 분리(§8.1, §11.1).** 엔진이 점수/구간/신뢰도/`reason_code`를 *계산*하고, LLM은 그 구조화 출력을 *설명*만 한다. LLM은 절대 점수·확률을 만들지 않는다.
3. **서버 사이드 전용 계산(§8.1).** 환산식·입결 데이터는 클라이언트로 원문 노출 금지. 클라이언트에는 *결과 + 출처 링크*만.
4. **포트/어댑터 경계 = 백엔드 분리 이음새(seam).** `core`(도메인)는 Next.js·Prisma·HTTP를 import하지 않는다. API 라우트는 얇은 어댑터. → 추후 FastAPI로 분리해도 **API 계약과 프론트는 그대로**, 데이터/엔진 구현만 교체.
5. **ORM 격리.** Prisma는 `packages/db`에만 존재. 서비스·엔진은 Prisma 모델이 아니라 **도메인 엔티티**로 일한다 ("orm 로직 깊이 조정").
6. **구조화 JSON + 스키마 검증(§11.2/11.3, Zod).** API 경계와 LLM 입출력은 전부 Zod로 검증. 검증 스키마는 `packages/shared/contracts` 단일 출처.
7. **컨트롤드 보캐블러리 단일 출처(§8.5, CLAUDE.md).** `exam_type`/`band`/`confidence`/`report_type`/`channel`/`reason_code` enum은 `packages/shared`에서만 정의. 임의 문자열 금지.
8. **다중 채널 알림 우선순위(§5, §17.5).** 1) 카카오 알림톡 → 2) 이메일 → 3) 웹푸시. iOS 미설치 사용자는 웹푸시 도달 불가 → 알림톡/이메일이 커버.
9. **모든 결과 화면·리포트·PDF에 면책(§13.3)·AI 고지(§13.4).** 문구는 스펙 원문 그대로, `packages/shared/disclaimers.ts`에서 단일 관리.

---

## 2. 모노레포 레이아웃

pnpm workspaces + Turborepo. 핵심은 **`apps/web`(전송 계층) ↔ `packages/core`(도메인) ↔ `packages/db`/`llm`/`notifications`(어댑터)** 의 단방향 의존.

```
pacer/
├─ apps/
│  └─ web/                         # Next.js App Router — PWA 셸 + UI + 얇은 API 라우트
│     ├─ app/
│     │  ├─ (marketing)/
│     │  │  └─ landing/            # SSR 랜딩(§7.1) + OG 메타
│     │  ├─ (app)/
│     │  │  ├─ dashboard/          # 정시 대시보드(§7.5) — 6모/9모/수능 시점 분기
│     │  │  ├─ score/              # 성적 입력(§7.3)
│     │  │  ├─ target/             # 목표 설정(§7.4)
│     │  │  ├─ analysis/           # 분석 결과(§7.6)
│     │  │  ├─ report/             # AI 리포트(§7.7)
│     │  │  ├─ explore/            # 대학/모집단위 탐색(§7.8)
│     │  │  ├─ simulate/           # 점수 시뮬레이션(§7.9, P1)
│     │  │  ├─ plan/               # 가/나/다 조합(§7.10, P2)
│     │  │  └─ outcome/            # 결과 인증(§7.11, P2)
│     │  ├─ admin/                 # 관리자 도구(§12) — 데스크톱 우선
│     │  ├─ api/                   # ★ ROUTE ADAPTERS ONLY — 서비스 호출만, 로직 금지
│     │  │  ├─ cycles/route.ts                              # §10.1
│     │  │  ├─ cycles/[cycleId]/scores/route.ts             # §10.2
│     │  │  ├─ cycles/[cycleId]/targets/route.ts            # §10.3
│     │  │  ├─ cycles/[cycleId]/analysis/run/route.ts       # §10.4
│     │  │  ├─ analysis/[snapshotId]/results/route.ts       # §10.5
│     │  │  ├─ cycles/[cycleId]/reports/route.ts            # §10.6
│     │  │  ├─ cycles/[cycleId]/competitor-signals/route.ts # §10.7
│     │  │  ├─ cycles/[cycleId]/application-plans/route.ts  # §10.8
│     │  │  ├─ cycles/[cycleId]/notifications/subscribe/route.ts # §10.9
│     │  │  ├─ webhooks/                                    # PG 결제, 알림톡 콜백
│     │  │  └─ og/route.tsx                                 # 공유 카드 OG 이미지 생성
│     │  ├─ manifest.ts            # Web App Manifest(§17.4) display:standalone
│     │  └─ layout.tsx
│     ├─ public/icons/             # 마스커블 아이콘 등 PWA 자산
│     ├─ worker/                   # Service Worker(§17.4) — 앱셸 캐시, push, 폼 상태 보존
│     ├─ components/               # 프레젠테이션 UI (engine/db import 금지)
│     ├─ features/                 # 클라이언트 기능 모듈(성적폼, 대시보드 위젯, 설치 권유)
│     └─ lib/                      # api 클라이언트, anon 세션, analytics(§16.5 이벤트명)
│
├─ packages/
│  ├─ shared/                      # ★ 단일 진실 공급원 (도메인 무관 순수 타입/스키마)
│  │  ├─ enums.ts                  # exam_type/score_status/band/confidence/report_type/channel
│  │  ├─ reason-codes.ts           # §8.5 강점/약점/추천 코드 테이블
│  │  ├─ contracts/                # ★ API 계약 = 분리 이음새. 요청/응답 Zod 스키마(§10)
│  │  ├─ disclaimers.ts            # §13.3 면책 + §13.4 AI 고지 (스펙 원문 그대로)
│  │  └─ analytics-events.ts       # §16.5 이벤트명 enum
│  │
│  ├─ core/                        # ★ 도메인 코어 — Next.js·Prisma·fetch import 절대 금지
│  │  ├─ domain/                   # 도메인 엔티티/값객체 (Prisma 모델 아님)
│  │  ├─ engine/                   # 계산 엔진(§8) — 순수 함수, 결정적, 테스트 1급
│  │  │  ├─ validate.ts            # 1. 성적 검증(§8.1, §18.1)
│  │  │  ├─ normalize.ts           # 2. 성적 정규화
│  │  │  ├─ eligibility.ts         # 3. 지원 가능 조건 판정(수학 선택 제한 등)
│  │  │  ├─ convert/               # 4. 대학별 환산: exact(정확)·approx(근사)·unsupported(불가)
│  │  │  ├─ compare.ts             # 5. 전년도 입결 비교 → score_gap
│  │  │  ├─ band.ts                # 6. 구간 분류(§8.3 보정요소)
│  │  │  ├─ confidence.ts          # 7. 신뢰도 산출(§8.4)
│  │  │  ├─ reason-codes.ts        # 8. reason code 생성(§8.5)
│  │  │  ├─ trend.ts               # 9. 시험 간 변화 분석(6모↔9모, P1)
│  │  │  └─ application-plan.ts    # 10. 가/나/다 조합 후보 생성(P2)
│  │  ├─ services/                 # 유스케이스 오케스트레이션 (ports에만 의존)
│  │  │  ├─ cycle.service.ts
│  │  │  ├─ score.service.ts
│  │  │  ├─ analysis.service.ts    # §17.3 분석 처리 흐름 1~14 단계 오케스트레이션
│  │  │  ├─ report.service.ts      # 엔진 출력 → LLM 포트 → 금지어 필터 → 저장
│  │  │  ├─ application-plan.service.ts
│  │  │  ├─ outcome.service.ts
│  │  │  └─ notification.service.ts # 우선순위 발송 오케스트레이션
│  │  └─ ports/                    # ★ 인터페이스만: repositories, LlmReporter, Notifier, Clock
│  │
│  ├─ db/                          # 인프라 어댑터 — Prisma는 여기에만 갇힌다
│  │  ├─ schema.prisma             # §9 전체 데이터 모델
│  │  ├─ migrations/
│  │  ├─ client.ts
│  │  └─ repositories/             # core/ports 구현 (도메인 엔티티 ↔ Prisma 모델 매핑)
│  │
│  ├─ llm/                         # LLM Gateway(§11) — core.ports.LlmReporter 구현
│  │  ├─ gateway.ts                # 모델 호출/캐싱, model_name·prompt_version 기록
│  │  ├─ prompts/                  # report_type별 버전 관리 프롬프트
│  │  ├─ schema.ts                 # §11.2 입력 / §11.3 출력 JSON schema 검증
│  │  └─ banned-words.ts           # §11.4 금지어 필터 (통과 못하면 재생성/차단)
│  │
│  ├─ notifications/               # 다중 채널 어댑터(§17.5) — core.ports.Notifier 구현
│  │  ├─ alimtalk.ts               # 1순위 카카오 알림톡
│  │  ├─ email.ts                  # 2순위 이메일(Resend/SES)
│  │  ├─ web-push.ts               # 3순위 웹푸시(VAPID, iOS 16.4+ 설치자 한정)
│  │  └─ dispatcher.ts             # 보유 채널 중 우선순위 발송(중복 최소화)
│  │
│  ├─ reference-data/              # University/AdmissionUnit/AdmissionRule/HistoricalOutcome
│  │  └─                           #   시드·검수·버저닝 파이프라인(verified_status/confidence)
│  │
│  └─ config/                      # 공유 tsconfig/eslint/tailwind preset
│
├─ workers/                        # 비동기·배치 (선택 Redis 큐) — P1+에서 실체화
│  └─                              #   LLM 리포트 비동기 생성, 알림 배치, 만료 endpoint 정리(§18.4)
│
├─ docs/
│  ├─ 01-architecture.md           # (이 문서)
│  ├─ 02-implementation-plan.md
│  └─ adr/                         # Architecture Decision Records
│
├─ pnpm-workspace.yaml
├─ turbo.json
└─ package.json
```

---

## 3. 의존성 방향 (단방향, 안쪽으로만)

```
apps/web  ──▶  packages/shared
   │             ▲
   │             │
   ▼             │
packages/core ───┘        (core는 shared만 의존)
   ▲   ▲   ▲
   │   │   │   (어댑터들이 core의 ports를 "구현"하며 안쪽을 향함)
   db  llm  notifications
```

- `core`는 **어떤 어댑터도 import하지 않는다.** 런타임에 `apps/web`의 조립 지점(composition root)에서 어댑터를 주입한다.
- 금지 의존(ESLint 규칙으로 강제 권장):
  - `core` → `next`, `@prisma/client`, `fetch`/HTTP, `apps/web` **금지**
  - `components` → `core/engine`, `db` **금지** (UI는 결과 DTO만 본다)
  - 환산식/입결 타입을 클라이언트 번들로 새지 않게 `convert/`·`reference-data`는 서버 전용 경계 유지(§8.1)

---

## 4. FastAPI 분리 이음새 (지금 안 쪼개되, 쪼갤 수 있게)

추후 백엔드를 별도 서비스(FastAPI 등)로 분리할 때 **건드리지 않아도 되는 것**과 **교체되는 것**을 지금 경계로 못 박는다.

| 구성요소 | 분리 시 |
|---|---|
| `packages/shared/contracts` (API 계약, Zod/JSON-schema) | **유지** — 양쪽의 단일 계약 |
| `apps/web` UI + `lib/api-client` | **유지** — base URL만 외부 서비스로 변경 |
| `apps/web/app/api/*` 라우트 어댑터 | 얇으므로 제거/프록시화 비용 작음 |
| `packages/core/services` + `engine` | 별도 서비스로 이전(Node 추출) **또는** Python 재구현 |
| `packages/db` (Prisma) | 새 서비스 쪽으로 이동/재구현 — **서비스가 Prisma에 의존 안 하므로 파급 없음** |

> 핵심: **로직은 라우트가 아니라 서비스에**, **DB 접근은 ORM이 아니라 repository 포트 뒤에.** 이 두 규칙이 분리 비용을 결정한다.

---

## 5. 핵심 데이터 모델 매핑 (§9 → schema.prisma)

체인(§23): `User?` → `AdmissionCycle` → `ExamScore` → `SubjectScore`, `TargetSnapshot`, `AnalysisSnapshot` → `AnalysisResult`, `StrategyReport`, `SavedAdmissionUnit`, `ApplicationPlan`, `FinalOutcome`.
레퍼런스(admin-curated, 버저닝): `University`, `AdmissionUnit`, `AdmissionRule`, `HistoricalOutcome`. 교차검증: `CompetitorSignal`(수동 입력 전용, 자동수집 금지 §7.7.4). 알림: `NotificationSubscription`(다중 채널).

제약:
- `AdmissionCycle.user_id` nullable + `anon_session_id` nullable (둘 중 하나로 데이터 소유).
- `AdmissionRule.verified_status`: draft/parsed/verified/live/deprecated, `HistoricalOutcome.confidence` — 신뢰도 라벨(§8.4) 입력값.
- `StrategyReport`는 `model_name`·`prompt_version` 필수 기록(§11, 재현성).

---

## 6. 분석 1회 처리 흐름 (§17.3 → analysis.service.ts)

```
성적 입력(client) → [validate → normalize] → 목표 로드 → 후보 모집단위 로드
→ eligibility → convert(환산) → compare(입결) → band(구간) → confidence → reason-codes
→ AnalysisSnapshot 저장 → (LLM 리포트 생성 = 별도/비동기) → 결과 표시
```
- **기본 분석 우선 제공 + LLM 리포트 비동기**(§17.6, §18.4): 수능 시즌 부하 대비. P0는 인라인 허용, P1+는 `workers/` 큐.
- 성능 목표: 입력 3분 내, 분석 표시 10초 내(§18.3).
