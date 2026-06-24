# 6모 브랜치 실행 계획 — 서브에이전트 오케스트레이션

> 버전 v0 · 2026-06-22 · 상위 계획: [`05-6mo-prelaunch-plan.md`](./05-6mo-prelaunch-plan.md) §8(브랜치 분할)의 **실행 절차본**.
> 이 문서는 "무엇을 만드나"(05)가 아니라 **"어떤 순서로·어느 에이전트에게·무엇을 시켜·무엇으로 끝났다 하나"** 를 다룬다.

## 0. 불변 원칙 (모든 브랜치 공통)

1. **데이터 모델은 `AdmissionCycle` 중심, `User`는 nullable** (CLAUDE.md §9). 로그인을 cycle/score 생성의 전제로 만들지 않는다.
2. **무마찰 입구 유지** — 로그인은 "입구"가 아니라 **가치(결과/리포트)를 본 뒤**에만 유도(05 §3).
3. **경계 준수** (`01-architecture.md`): `core`는 Next/Prisma/HTTP를 import하지 않음. 라우트는 thin 어댑터. enum·contract는 `packages/shared`에만.
4. **⛔ 동료 전용 파일은 절대 건드리지 않음** (05 §8): `packages/core/src/services/review.service.ts`, `packages/core/src/ports/index.ts`의 **review* 인터페이스 구역**, `apps/web/app/api/admin/review/*`, `apps/web/app/admin/review/page.tsx`, `apps/web/lib/admin-core.ts`, `apps/web/components/review/*`, `packages/shared/src/contracts.ts`의 reviewer/decision 스키마.
   - 단, `ports/index.ts`에 **새 `UserRepository`를 추가**하는 건 review 구역과 무관 → 허용(파일 끝에 append, review 인터페이스는 미수정).
5. 각 브랜치 종료 게이트: `pnpm typecheck && pnpm lint` 통과 + 해당 브랜치 Acceptance 충족.
6. **🔴 DB 마이그레이션 안전 (절대)**: `DATABASE_URL`은 **공유 운영 Supabase**(215대학·68k입결·동료 검수 데이터 라이브)를 가리킨다. `db` 패키지의 `migrate` 스크립트는 `prisma migrate dev`이고, 이는 drift 감지 시 **DB 리셋(전체 삭제)** 을 실행할 수 있다. 따라서:
   - **공유 DB에 `prisma migrate dev` / `db push` 절대 금지.** 데이터 복구 불가급 사고.
   - 스키마 변경이 필요하면 **`prisma migrate dev --create-only`로 마이그레이션 SQL 파일만 생성**하고, 변경 파일 목록에 포함해 보고만 한다. **실제 적용(apply)은 사람이** 별도 검토/스테이징 DB에서 수행.
   - 에이전트는 `prisma generate`(클라이언트 생성, DB 비접촉)까지만.
7. **핸드오프 스코프**: §1.3 순서대로 **한 번에 한 브랜치만**, (1)부터 진행. 동료 전용 파일(§0.4) 미접촉. worktree 신규 환경이면 `pnpm install` 먼저(vitest는 sandbox shim이라 install로 교체됨). **커밋하지 않는다** — 변경 파일 목록 + typecheck/lint 결과만 보고.

## 1. 서브에이전트 오케스트레이션 모델

### 1.1 브랜치당 1 에이전트 = 1 worktree (격리)
충돌 클러스터(`analysis/page.tsx`, `report/page.tsx`)를 피하려고 **각 브랜치를 별도 git worktree에서 격리 실행**한다. Claude Code에서:

- `Agent(subagent_type: "claude", isolation: "worktree", prompt: <브랜치 작업카드>)` 로 브랜치별 에이전트를 띄운다.
- worktree는 변경 없으면 자동 정리됨. 머지 후 결과만 메인으로 가져온다.
- **동시에 띄우지 말 것** — 같은 퍼널 페이지를 만지는 3개(auth/demand/analytics)는 §2 순서대로 **직렬**. 충돌 없는 게이트/문서 계열만 병렬 허용.

### 1.2 작업카드(에이전트 프롬프트) 표준 형식
각 브랜치를 에이전트에 넘길 때 아래를 채워 프롬프트로 준다:
```
[브랜치] feat/xxx  (base: 직전 머지된 baseline 커밋)
[목표] 한 줄
[건드릴 파일] 화이트리스트 (아래 표)
[금지] §0.4 동료 전용 파일 + 다른 브랜치 소유 파일
[구현 단계] 1..n
[Acceptance] 체크 가능한 완료 기준
[검증] 실행할 명령/수동 시나리오
종료 시: typecheck+lint 결과와 변경 파일 목록만 보고. 커밋하지 말 것.
```
> 작업카드를 잘게(파일 화이트리스트 + Acceptance) 줄수록 에이전트가 옆 브랜치 영역을 침범하지 않는다.

### 1.3 머지 순서 (충돌 클러스터 직렬화)
```
(0) 동료: feat/reviewer-progress  ── 독립, 병렬 무관
(1) feat/social-auth-merge        ── baseline. 먼저 머지.
(2) feat/soft-demand-optin        ┐ (1) 위에서. report/page.tsx 편집 최소화.
(3) feat/funnel-analytics-hardening┘ (1) 위에서. (2)와 페이지 충돌나면 (2)→(3) 순차.
(4) fix/prelaunch-mobile-qa        ── (1)(2)(3) 머지 후 최종 1회 QA.
(5) chore/vercel-launch-gate       ── 설정 중심, (4)와 병렬 가능.
   docs/prelaunch-marketing-copy   ── 코드 무충돌, 아무 때나.
```

## 2. 브랜치별 구현 카드

---

### 🟦 (1) `feat/social-auth-merge` — baseline, 먼저 머지

**목표**: 카카오/구글 소셜 로그인 + 익명 cycle→User merge + 로그인 후 사이클 복원. "기기 바꿔/쿠키 지워도 로그인하면 6모 사이클이 복원된다"가 완료 기준(05 §4·§8).

**현재 상태(탐색 결과)**:
- 익명 세션: `apps/web/lib/anon-session.ts`(`ANON_COOKIE="anon_session_id"`, `getOrCreateAnonSessionId`), 쿠키 세팅은 `apps/web/app/api/cycles/route.ts`.
- 소유권 검사: `apps/web/lib/authz.ts` — `authorizeCycle()`가 쿠키 anonId만 대조. **주석에 "가입 사용자 인증(P1)은 여기서 세션 검사로 확장한다"** 명시 → 정확한 확장 지점.
- 스키마: `packages/db/prisma/schema.prisma`의 `User`(nullable, `email String? @unique`, `phone String?`, `kakaoId String?`) + `AdmissionCycle`(`userId String?`, `anonSessionId String?`, `@@index([userId])`). merge에 필요한 `userId`는 이미 있음.
- **🔵 식별자 결정(확정): `User`에 `supabaseId String? @unique` 1개 추가.** provider(카카오/구글/추후 네이버) 무관 단일 안정 키. email/kakaoId 매핑은 불채택 — 카카오 email 누락 흔함 + provider 혼용 시 **중복계정** 위험. 단 이 컬럼 추가는 마이그레이션이므로 **§0.6 준수: `--create-only`로 SQL 파일만 생성, 공유 DB 적용 금지(사람이 별도 적용)**.
- 포트: `packages/core/src/ports/index.ts`에 **`UserRepository` 없음**. `CycleRepository`는 `create/findByAnonSessionAndYear/updateProfile/findById`만.
- Auth 라이브러리: **전무**(Supabase 클라이언트·next-auth 없음). composition root `apps/web/lib/container.ts`에 auth/user 서비스 미주입.

**기술 결정**: Supabase Auth(카카오+구글 네이티브 provider) 사용. 네이버는 6모 제외(05 §3). **구현 직전 Supabase provider 지원상태 재확인**.

**건드릴 파일 (화이트리스트)**:
| 레이어 | 파일 | 작업 |
|---|---|---|
| 포트 | `packages/core/src/ports/index.ts` | 파일 끝에 `UserRepository`(`findBySupabaseId`/`findById`/`create`) + `CycleRepository`에 `findByUserAndYear`·`mergeAnonToUser` **append**(review 구역 미수정) |
| 도메인 | `packages/core/src/domain/entities.ts` | `User` 엔티티(없으면) |
| 서비스 | `packages/core/src/services/auth.service.ts`(신규) 또는 `cycle.service.ts`에 `mergeAnonCycleToUser(userId, anonSessionId, admissionYear)` | merge = anon cycle의 `userId` 채우기 (트랜잭션) |
| 어댑터 | `packages/db/src/repositories/user.repository.ts`(신규) + `cycle.repository.ts`에 merge 구현 | Prisma↔도메인 매핑 |
| 조립 | `apps/web/lib/container.ts` | `getAuthService()`/`getUserService()` 추가 |
| Auth 인프라 | `apps/web/lib/supabase/*`(신규: server/client helper), `apps/web/middleware.ts`(세션 갱신) | Supabase Auth 세션 |
| 라우트 | `apps/web/app/api/auth/callback/route.ts`(신규: OAuth 콜백→User upsert→merge 호출) | |
| 인가 확장 | `apps/web/lib/authz.ts` | `authorizeCycle`을 **userId 세션 OR anonId 쿠키**로 확장(주석 지시대로) |
| 복원 | `apps/web/app/dashboard/page.tsx` | 로그인 시 `findByUserAndYear`로 사이클 복원 경로 |
| 로그인 UI | `apps/web/components/LoginSheet.tsx`(신규) + `report`/`analysis`에서 "가치 후" 1개 CTA로 호출 | 페이지 편집 **최소** |
| 의존성 | `apps/web/package.json` | `@supabase/ssr` 등 |
| env | `.env.example` | `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, (서버) provider 시크릿 |

**구현 단계**:
0. `schema.prisma`에 `User.supabaseId String? @unique` 추가 → **`prisma migrate dev --create-only`로 SQL 파일만 생성**(§0.6, 공유 DB 적용 금지) → `prisma generate`.
1. 포트·도메인·repo(User) + `mergeAnonCycleToUser` 서비스/어댑터 추가, core 단위테스트(merge가 anon cycle의 userId를 채우고 동일 anon의 중복 생성 안 함).
2. Supabase server/client helper + middleware 세션.
3. `/api/auth/callback`: 콜백→`User` upsert(supabaseId/kakaoId/email)→현재 anon 쿠키의 cycle을 user에 merge.
4. `authz.ts` 확장: 세션 userId가 cycle.userId와 일치해도 통과.
5. `LoginSheet` + report/analysis "가치 후" CTA 1개 + dashboard 복원.

**Acceptance — ✅ 에이전트가 검증 (키 불필요)**:
- [ ] 익명으로 점수→분석→리포트까지 **로그인 없이** 그대로 동작(무마찰 입구 보존).
- [ ] `mergeAnonCycleToUser` core 단위테스트 green(userId 채움 + 중복 생성 안 함).
- [ ] `authorizeCycle`이 userId 세션 경로로도 통과(테스트로).
- [ ] `LoginSheet`·콜백·복원 경로 **골격 빌드**(키 없으면 OAuth 호출 직전까지) + typecheck·lint green.
- [ ] supabaseId 마이그레이션은 **파일만 생성**(미적용), 변경 파일 목록에 포함.

**Acceptance — 👤 OAuth 키 받은 뒤 사람이 검증 (에이전트 done 아님)**:
- [ ] Supabase에 카카오/구글 provider 등록 + 키 주입 후, 리포트 본 뒤 로그인 → User 생성 + 6모 cycle 귀속.
- [ ] **다른 브라우저(쿠키 없음)에서 같은 계정 로그인 → dashboard에 6모 cycle 복원**(05 §4 핵심).
- [ ] supabaseId 마이그레이션을 스테이징/검토 후 실제 적용.

**검증**: `pnpm --filter @pacer/core test`, `pnpm typecheck && pnpm lint`. (라이브 로그인·크로스기기 복원은 키 주입 후 수동.)

---

### 🟩 (2) `feat/soft-demand-optin` — 리포트 하단 알림 토글 (이벤트+DB 저장)

**목표**: 리포트 하단 *"9모엔 더 깊은 유료 분석 준비 중 — 알림 받기"* opt-in 토글 1개. 결제/예약/앵커링 UI 없음. **클릭 시 analytics 이벤트 emit + 구독을 DB 저장**해 9모 때 재연락 가능한 리스트 확보(05 §2.2 "획득").

**현재 상태(탐색 결과)**:
- 리포트 페이지 `apps/web/app/report/page.tsx`: `<Disclaimer />`(≈L249) **뒤**, 푸터 버튼 그리드(≈L230–242) 앞이 삽입 위치.
- 재사용 가능: 알림 구독 컴포넌트 `apps/web/components/AlertSheet.tsx`(카카오/이메일/웹푸시 탭) + API `apps/web/app/api/cycles/[cycleId]/notifications/subscribe/route.ts`(`subscribeNotificationRequest` Zod, `NotificationSubscriptionService` 위임). 9모 알림은 `analysis/page.tsx`에서 이 경로 이미 사용.
- enum: `packages/shared/src/enums.ts:41` `notificationEvent = z.enum(["september_mock_open"])` — **현재 값 1개뿐**.
- analytics: `packages/shared/src/analytics-events.ts`에 `reminder_opt_in`(channel 파라미터) 이미 존재.

**건드릴 파일 (화이트리스트)**:
| 파일 | 작업 |
|---|---|
| `packages/shared/src/enums.ts` | `notificationEvent`에 `"september_paid_preview"`(가칭) 1개 **추가** |
| `apps/web/components/DeepAnalysisOptIn.tsx`(신규) | 토글/카드 1개. AlertSheet 스타일 재사용. 켜면 채널 입력→subscribe 호출 |
| `apps/web/app/report/page.tsx` | `<Disclaimer/>` **뒤**에 `<DeepAnalysisOptIn/>` 한 줄 삽입 (편집 최소 — 충돌 클러스터) |
| `apps/web/app/api/cycles/[cycleId]/notifications/subscribe/route.ts` | `eventNames`에 새 이벤트 허용(기존 `september_mock_open` 유지) |
| (이벤트) | 토글 ON 시 `track("reminder_opt_in", { channel, event:"september_paid_preview" })` |

**구현 단계**:
1. `enums.ts`에 이벤트 값 추가(shared 빌드 영향 확인). 2. `DeepAnalysisOptIn` 컴포넌트(채널 1개 입력→기존 subscribe API에 새 event로 저장). 3. report 페이지에 1줄 삽입. 4. `track` emit.

**Acceptance**:
- [ ] 리포트 하단에 토글 노출(결제/가격 UI 없음).
- [ ] 켜면 `notifications/subscribe`에 새 event로 **DB 저장**(재연락 리스트).
- [ ] `reminder_opt_in` 이벤트 emit.
- [ ] `report/page.tsx` diff가 삽입 1줄 수준(충돌 최소).
- [ ] typecheck·lint green.

**검증**: 리포트에서 토글 ON→DB row 생성 확인(로컬 Supabase/Prisma studio), PostHog 이벤트 확인.

---

### 🟨 (3) `feat/funnel-analytics-hardening` — 퍼널 이벤트 누락 점검 + PostHog init

**목표**: `cycle_created → score_submit → analysis_success → report_view → reminder_opt_in` 전 구간 이벤트가 실제로 발화하도록 누락 배선 + PostHog 초기화. 출시 판단(드롭오프) 가시화.

**현재 상태(탐색 결과)**:
- 이벤트 이름은 `packages/shared/src/analytics-events.ts`에 **이미 enum화**(§16.5와 일치).
- track 헬퍼 `apps/web/lib/analytics.ts`: `window.posthog?.capture` 호출만. **PostHog 라이브러리 init이 없음**(`posthog-js` import·provider 없음) → 외부 주입 가정. `NEXT_PUBLIC_POSTHOG_KEY` 가드는 있음.
- 이미 발화: `cycle_created/score_submit/analysis_success`(score), `report_view`(report), `reminder_opt_in/share_card_created`(analysis), `landing_view/cta_click`, `pwa_installed`.
- **누락**: `score_input_start`(/score 진입), `analysis_run`(분석 API 호출 시), `return_from_reminder`(알림 링크 복귀). (이외 premium/purchase 등은 6모 범위 밖.)

**건드릴 파일 (화이트리스트)**:
| 파일 | 작업 |
|---|---|
| `apps/web/components/PostHogProvider.tsx`(신규) + `app/layout.tsx`에 마운트 | `posthog-js` 명시적 init(키 있을 때만), `apps/web/package.json`에 `posthog-js` |
| `apps/web/app/score/page.tsx` | `score_input_start` emit (진입 시) |
| 분석 실행 지점(`score/page.tsx` 또는 분석 트리거) | `analysis_run` emit (성공 전) |
| 알림 복귀 진입점(dashboard/report, `?source=reminder`) | `return_from_reminder` emit |
| `.env.example` | `NEXT_PUBLIC_POSTHOG_KEY/HOST` 코멘트 정리(이미 존재) |

> ⚠️ `score/page.tsx`·`report/page.tsx`는 (1)(2)와 겹침 → **(2) 머지 후 그 위에서** 작업. emit 추가는 한 줄짜리라 충돌 최소.

**Acceptance**:
- [ ] 키 설정 시 PostHog가 명시적으로 init되고 페이지뷰/이벤트 전송.
- [ ] 5개 핵심 퍼널 이벤트가 실제 클릭 흐름에서 순서대로 발화(개발자도구/PostHog 라이브 확인).
- [ ] 키 없으면 무해히 no-op(기존 가드 유지).
- [ ] typecheck·lint green.

**검증**: 키 넣고 랜딩→점수→분석→리포트→알림 끝까지 → PostHog Live events에서 5개 확인.

---

### 🟧 (4) `fix/prelaunch-mobile-qa` — 모바일 퍼널 최종 QA (auth 머지 후 1회)

**목표**: 코드 변경 최소, (1)(2)(3) 머지 후 모바일 퍼널 통검.

**QA 대상 경로**: `/`(`app/page.tsx`) → `/score` → `/analysis?snapshotId=` → `/report?reportId=` → `/dashboard` + 알림 시트(`AlertSheet`)/소셜 로그인 시트.

**체크리스트**:
- [ ] 입력 3분 내(§7.3) — 모바일 폼(수학/탐구 선택, 목표대) 사용성.
- [ ] **면책/AI 고지가 모든 결과·리포트 화면에 노출**: `components/Disclaimer.tsx` 텍스트가 `packages/shared/src/disclaimers.ts`(§13.3/§13.4)와 **정확히 일치**(문구 수정 금지) — landing/analysis/report/dashboard.
- [ ] iOS/Android PWA 안내 + 웹푸시 제약(iOS 16.4+ 설치 PWA only) 고지(`AlertSheet`에 이미 있음) 확인.
- [ ] 결과/리포트/알림 바텀시트 모바일 레이아웃(`max-w-md`), 터치 타깃, 명도대비.
- [ ] 새로 들어온 로그인 CTA·demand 토글이 모바일에서 깨지지 않음.

**Acceptance**: 위 전부 OK + 실데이터(핵심대 점수) 1세트로 끝까지 통과. 코드 수정 발생 시 해당 파일만 최소 패치.

---

### ⚙️ (5) `chore/vercel-launch-gate` — 배포 게이트 (설정 중심)

**목표**: Vercel env/시크릿·프로덕션 admin off·OG·PWA 점검. 코드 적음.

**현재 상태(탐색 결과)**:
- env 소스: `.env.example`(`DATABASE_URL`, `ANTHROPIC_API_KEY`, `LLM_MODEL_NAME`, `VAPID_*`, `ADMIN_ENABLED`, `ADMIN_TOKEN`, `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_POSTHOG_*`, (신규) Supabase 키).
- admin 게이팅: `apps/web/lib/admin-auth.ts` — `ADMIN_ENABLED!=="1"`이면 404 + localhost 체크 + 상수시간 토큰. **프로덕션 `ADMIN_ENABLED=0`이면 `/admin/*` 전부 404**.
- PWA: `app/manifest.ts`(standalone, start_url `/dashboard?source=pwa`, 192/512 아이콘), `public/sw.js`(navigation network-first + push), `components/ServiceWorkerRegister.tsx`.
- OG: `app/opengraph-image.tsx`(edge, 1200×630 정적 카드), `app/layout.tsx` metadata(`metadataBase`←`NEXT_PUBLIC_SITE_URL`).

**체크리스트(대부분 코드 아님, Vercel 설정)**:
- [ ] 서버 시크릿(Vercel env): `DATABASE_URL`, `ANTHROPIC_API_KEY`, `VAPID_PRIVATE_KEY`, (auth) Supabase service/provider 시크릿, `ADMIN_TOKEN`.
- [ ] 클라이언트: `NEXT_PUBLIC_SITE_URL`(실도메인), `NEXT_PUBLIC_VAPID_PUBLIC_KEY`, `NEXT_PUBLIC_POSTHOG_KEY/HOST`, `NEXT_PUBLIC_SUPABASE_*`.
- [ ] **프로덕션 `ADMIN_ENABLED=0` 확인** → 배포본에서 `/admin/review` 404 확인(실측).
- [ ] OG 공유카드(카카오/인스타 미리보기) + `metadataBase` 실도메인 반영.
- [ ] Lighthouse/PWA: manifest 유효·SW 등록·설치 가능·아이콘 사이즈. 스테이징 1회 측정.

**Acceptance**: 배포본에서 admin 404 + 퍼널 정상 + OG 미리보기 정상 + Lighthouse PWA 통과. 필요한 코드 패치는 설정/메타 한정.

---

## 3. 참조만 (이 문서에서 상세화 안 함)

- **동료 `feat/reviewer-progress`** — review.service/ports review구역/admin/review/* 소유. §0.4 절대 미접촉.
- **데이터 검수** — Git 브랜치 아님. 공유 Supabase 직접 쓰기 → 대학단위 claim(05 §8 A/B 트랙).
- **`docs/prelaunch-marketing-copy`** — 코드 무충돌, 카피만.
- **6모에서 안 여는 것**: 실결제 PG·PDF·알림 발송 어댑터·네이버 로그인·P1/P2 UI(05 §6).

## 4. 실행 순서 요약(체크리스트)
1. [ ] (동료) reviewer-progress 병렬 진행(독립).
2. [ ] **(1) social-auth-merge** worktree 에이전트 → Acceptance → 메인 머지(baseline).
3. [ ] **(2) soft-demand-optin** → (3) **funnel-analytics-hardening** (baseline 위, report/score 충돌 시 순차).
4. [ ] **(4) mobile-qa** 최종 1회.
5. [ ] **(5) vercel-launch-gate**(병렬 가능) → 배포.
6. [ ] 데이터 검수 A/B claim 즉시 병렬.
