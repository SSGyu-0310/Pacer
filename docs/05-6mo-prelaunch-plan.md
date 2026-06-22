# 6모 pre-launch 실행 계획

> **버전: v0** · 작성일: 2026-06-22 · 목표: **6모 pre-launch 출시** (전면 무료 체험)
>
> 핵심대 데이터 결정은 [`reference-data/04-core-universities-decision.md`](./reference-data/04-core-universities-decision.md),
> 검수 도구·데이터 상태는 [`reference-data/02-review-guide.md`](./reference-data/02-review-guide.md) 참조.

---

## 1. 결론 한 줄

6모는 **전면 무료 pre-launch 체험**으로 간다. 결제는 6모에서 빼고(사업자·PG 미비), 본질인 *획득(데이터 moat + 9모 알림 리스트)* 에 집중한다. 코드 퍼널은 이미 거의 완성 상태이고, 남은 실질 작업은 **① 핵심대 데이터 검수(5일) → ② 간편로그인/연속성 보강 → ③ 퍼널 검증 → ④ 배포**다.

### 포지셔닝 주의
"전면 무료"는 **영구 무료가 아니라 "출시기념 / pre-launch 무료 체험"** 으로 말한다. 그래야 9모 유료 전환 시 가격결정력이 보존된다. 빗금 정가 앵커링은 9모로 미룬다.

---

## 2. 6모에서 지키는 3가지 (결제 제외)

결제 빌드는 6모에서 제외한다. 대신 아래 3개를 제대로 지킨다.

1. **간편로그인 도입** — 데이터 수집·연속성·재engagement 강화 (§3)
2. **소프트 demand 신호** — 리포트 하단 *"9모엔 더 깊은 유료 분석 준비 중 — 알림 받기"* opt-in 토글 하나. 예약 화면·앵커링 UI 없이 알림 이벤트 1개로 demand만 수집(빌드 거의 0).
3. **사업자등록 + PG 신청 착수** — 무료로 가더라도 9모 결제의 전제. 리드타임(심사 수일~수주) 때문에 **지금** 시작. 코드 아님, 대표 트랙.

---

## 3. 간편로그인 설계

### 왜 6모에 넣나
- 익명세션보다 식별·연속성·연락처 확보가 강해 **데이터 수집에 직접 기여**.
- 아래 §4 연속성 구멍을 자동 해결(로그인 시 기기 무관 사이클 복원).

### 배치 — "입구"가 아니라 "가치 후"
- ❌ 랜딩→점수입력 **앞**에서 로그인 강제 = 무마찰 입구(§1.4, §2.6) 파괴 → 퍼널 즉사.
- ✅ 익명으로 점수 넣고 결과를 본 **뒤**, *저장 · 9모 알림 · 9모 유료예고 알림* 시점에 간편로그인 유도. (web-push를 가치 후에 요청하라는 §5 원칙과 동일)
- 로그인 시 **익명 사이클을 유저에 merge** — 스키마가 `User(nullable) + anon_session_id`로 이미 익명→가입 승계를 염두에 둠(§9).

### Provider 지원 현황 (Supabase Auth 기준)
| Provider | 지원 | 비고 |
|---|---|---|
| 카카오 | ✅ 네이티브 | 한국 1순위, 필수 |
| 구글 | ✅ 네이티브 | 쉬움 |
| 네이버 | ⚠️ 네이티브 미지원 | OAuth2 직접 구현 + Supabase 세션 연결 필요 → 시간 남으면 6모, 아니면 9모 |

→ **6모: 카카오 + 구글 우선. 네이버는 커스텀이라 후순위.** 카카오만으로도 한국 커버리지 대부분 확보. (구현 직전 Supabase provider 지원상태 재확인)

---

## 4. 연속성 구멍 (코드 확인 결과)

- 사이클은 **`anon_session_id` 쿠키**에 묶임(`getCycleForAnonSession`이 쿠키로 조회).
- 분석 결과는 `snapshotId` URL로 재조회 가능(쿠키 없어도 "옛 결과 보기"는 됨).
- **하지만** 쿠키 삭제/기기 변경 시 → 사이클 조회 불가 → 9모 점수를 6모 사이클에 이어붙이는 **연속성이 끊김**. 알림 링크에 사이클 복원 토큰이 없음.
- → **간편로그인이 이 문제를 대체·해결한다**(로그인 = 기기 무관 사이클 소유). 별도 복원 토큰 작업 불필요.

---

## 5. 단계별 계획

### 🔴 Phase 0 — 오늘의 액션 (리드타임)
- **사업자등록 + PG 신청 착수** (대표) ← 9모 결제 전제
- 프리미엄 = 전략 리포트로 확정 (실제 가격/앵커링은 9모에 결정)

### 🟡 Phase 1 — 5일 (병렬, 스파인 = 데이터 검수)
| 워크스트림 | 담당 |
|---|---|
| 핵심대 검수 61개 (대학별 분할) | 둘이 나눠 ← **데드라인 본체** |
| reviewer 사람구분 + 진행도 헤더 | 동료 |
| 간편로그인(카카오/구글) + 익명→유저 merge | 개발 |
| 소프트 demand 신호(리포트 알림 토글) | 개발 |

### 🟢 Phase 2 — 검수 후, 출시 전
- **퍼널 실검증**: 실제 핵심대 점수로 끝까지 — 분석 `exact`/`parsed` → 리포트 → 로그인 저장 → 9모 알림 opt-in → 9모 유료 예고
- **배포 게이트**: Vercel env/시크릿(LLM키 등), OG 공유카드, 면책 문구(§13.3/§13.4)

### 🚀 Phase 3 — 6모 pre-launch 출시

---

## 6. 의도적 보류 (9모/P1 이후)
- **실결제 PG** (9모, 사업자/PG 준비 후) + 빗금 정가 앵커링
- **PDF** (웹 리포트가 내용 커버, 포맷일 뿐 — 우선순위 낮음)
- 알림 **발송** 어댑터 (실제 발송은 9월 임박해서)
- 네이버 로그인(커스텀) · 풀 회원관리

---

## 7. 5일 작업 분할 (2인)
- 검수는 `/admin/review`(localhost 전용, 공유 Supabase 즉시 반영). 사용법: `reference-data/02-review-guide.md` §3.
- **대학 단위로 나눠 중복 방지.** 우선순위 must → if_time → eng_special → med_health (`04-core-universities-decision.md` §2).
- 영어 ratio 대학은 웹폼이 아니라 JSONL fill 경로(`02-review-guide.md` §4–5).
- reviewer 사람구분이 켜지기 전엔 decision이 `"solo"`로 뭉치니, 분할 검수 전에 연결 권장.

---

## 8. 브랜치 분할 (병렬 작업)

### ⛔ 동료 전용 — 손대지 않음
**승인기록(reviewer 구분) + 진행률 UI**는 동료가 맡는다(`feat/reviewer-progress`). 충돌 방지를 위해 아래 파일은 이 계획의 다른 브랜치에서 **건드리지 않는다**:
- `packages/core/src/services/review.service.ts`, `packages/core/src/ports/index.ts`
- `apps/web/app/api/admin/review/*`, `apps/web/app/admin/review/page.tsx`
- `apps/web/lib/admin-core.ts`, `apps/web/components/review/ReviewProgressBar.tsx`
- `packages/shared/src/contracts.ts`의 **reviewer/decision 스키마 부분** (공유 파일 — 조율 필요)

### 데이터 검수 — 브랜치 아님 (Supabase claim 트랙)
검수는 공유 Supabase에 직접 쓰므로 Git 브랜치가 아니다. **대학 단위 claim**으로 운영하고 같은 대학은 한 명만 잡는다.
- **A 트랙**: must(가천대) + eng_special(항공/공학대) + 가톨릭대(서울)
- **B 트랙**: 서울여대 · 덕성여대 · 동덕여대 · 경기대 (경기대/동덕여대는 단위 많아 후순위로 쪼갬)

### 내 브랜치 (병렬)
| 브랜치 | 작업 | 비고 |
|---|---|---|
| `feat/social-auth-merge` | 카카오/구글 로그인 + 익명 cycle→User merge + 로그인 후 사이클 복원 | **유저 퍼널 baseline — 먼저 머지** |
| `feat/soft-demand-optin` | 리포트 하단 "9모 더 깊은 분석 알림받기" 토글/이벤트 | 결제 UI 없이 신호만. `shared/enums.ts`에 이벤트 추가 |
| `feat/funnel-analytics-hardening` | `cycle_created→score_submit→analysis_success→report_view→reminder_opt_in` 이벤트 누락 점검 + PostHog init/env | 출시 판단용 |
| `fix/prelaunch-mobile-qa` | 모바일 퍼널 QA(입력 3분, 결과/리포트/알림 시트, 면책/AI 고지, iOS/Android PWA 안내) | auth 머지 뒤 최종 1회 |
| `chore/vercel-launch-gate` | Vercel env/시크릿(LLM key·DB URL), **프로덕션 `ADMIN_ENABLED=0` 확인(끄기)**, OG 공유카드 폴리시, Lighthouse/PWA | 코드 적음, 설정 중심 |
| `docs/prelaunch-marketing-copy` | 6모 무료체험 카피 · 커뮤니티 배포글 · 9모 알림 문구 · 예시 리포트 문구 | 코드 무충돌 |

### ⚠️ 충돌 클러스터 (주의)
`social-auth-merge` · `soft-demand-optin` · `funnel-analytics-hardening` · `mobile-qa`는 **같은 유저 퍼널 페이지**(`analysis/page.tsx`, `report/page.tsx`)를 건드린다.
→ **`social-auth-merge`를 먼저 머지해 baseline으로** 깔고, 나머지를 그 위에 얹는다. demand 토글은 페이지 편집 최소화(이벤트는 `enums.ts`에).

### Acceptance 주의
- `social-auth-merge`: "**기기 바꿔/쿠키 지워도 로그인하면 6모 사이클이 복원된다**"가 완료 기준(§4 연속성 구멍 해결 검증).

### 우선순위
1. (동료) `feat/reviewer-progress` — 검수 2인 분할을 깔끔하게. *단, 검수 자체는 수동 분할로 오늘 바로 시작 가능*
2. (나) `feat/social-auth-merge` 먼저 → baseline
3. 동시: `soft-demand-optin` · `funnel-analytics-hardening` (auth 위에서)
4. 마지막 게이트: `fix/prelaunch-mobile-qa` · `chore/vercel-launch-gate`
5. 데이터 검수는 A/B claim 트랙으로 즉시 병렬

### 6모에서 열지 않는 브랜치
결제/PG 구현 · PDF · 알림 발송 어댑터 · 네이버 로그인 · P1/P2 UI — 모두 6모 범위 밖.
