# Pacer (페이서)

6모 → 9모 → 수능, 입시 사이클 전체를 추적하는 **AI 정시 전략 PWA**.

합격 확률을 단정하는 계산기가 아니라, 전년도 입결 기준으로 현재 위치를 **구간(안정·적정·소신·도전·위험)과 근거(reason code)** 로 해석해 주는 서비스다. 시험 한 번의 단발 분석이 아니라 같은 기준으로 시즌 전체의 변화를 추적한다(§2.2). 제품 명세는 `PRODUCT_SPEC.md`(진실의 원천), 설계 문서는 `docs/`.

## 현재 상태

**P0(6모) 내부 데모 동작 + P1(9모)·P2(수능) 백엔드 코어 구축 완료.**

P0 — 성적 입력부터 AI 리포트까지 전체 퍼널이 실제 DB(Supabase Postgres) 위에서 동작한다:

```
랜딩(/) → 성적 입력(/score) → 분석 실행 → 결과(/analysis)
  → 관심 저장 · 9모 알림 신청 · 공유 → AI 리포트(/report, 학생/학부모 탭)
```

- 익명 세션(쿠키) 기반 — 로그인 없이 시작 (§2.6). **카카오/이메일 로그인은 아직 미구현 — 현재는 익명 세션 전용.**
- LLM 리포트는 `ANTHROPIC_API_KEY` 있으면 실모델, 없으면 결정적 스텁 (검증 파이프라인은 동일)

P1/P2 — 9모·수능 시점에 필요한 엔진·서비스·API가 미리 깔려 있다(아래 구현 현황). UI·결제·PDF는 후속.

## 모노레포 구조

```
apps/web                 Next.js (App Router) — PWA 셸 + UI + 얇은 API 라우트(§10)
packages/shared          enum·계약(contract)·면책문구·이벤트명 (단일 진실 공급원)
packages/core            도메인 코어: 계산 엔진(§8) + 서비스(§17.3) + 포트 (Next/Prisma 비의존)
packages/db              Prisma 스키마(§9) + repository 어댑터 (ORM 격리)
packages/llm             LLM Gateway(§11): 프롬프트 버저닝·JSON 스키마 검증·금지어 필터
packages/notifications   다중 채널 알림(§17.5): 알림톡 → 이메일 → 웹푸시
packages/reference-data  대학·모집단위·환산규칙·입결 레퍼런스 데이터 도구
workers                  비동기/배치 (P1+)
docs                     아키텍처 · 구현계획 · 구현보고서 · ADR
```

의존 방향은 단방향(웹 → core → shared, 어댑터들이 core의 포트를 구현)이다. 자세한 경계 규칙과 "FastAPI 분리 이음새"는 `docs/01-architecture.md` 참조.

## 시작하기

요구: Node ≥ 20, pnpm, Supabase(또는 Postgres) 프로젝트.

> ⚠️ **공용 Supabase에 합류하는 경우(협업자):** DB는 이미 시딩된 공용 Supabase다. 전달받은 `DATABASE_URL`만 `.env`에 넣고, **`prisma migrate deploy`·`seed:p0`는 실행하지 마라**(공용 데이터/검수 결과를 덮어쓰거나 egress를 폭증시킴). 아래 ②③은 **DB를 처음부터 새로 세우는 최초 1회·로컬 전용**이다.

```bash
pnpm install
cp .env.example .env                              # ① DATABASE_URL = Supabase Session pooler URI(포트 5432)
pnpm db:generate                                  # Prisma Client 생성 (항상)
pnpm --filter @pacer/db exec prisma migrate deploy # ② [최초 1회·신규 DB만] 마이그레이션 적용
set -a; source .env; set +a
pnpm seed:p0                                      # ③ [최초 1회·신규 DB만] 레퍼런스 데이터 upsert
pnpm dev                                          # http://localhost:3000
```

관리자 검수 도구는 `.env`에 `ADMIN_ENABLED=1` + `ADMIN_TOKEN=<토큰>` 설정 후 `localhost`에서 `/admin/login` → `/admin/review`. 사용법은 [`docs/reference-data/02-review-guide.md`](docs/reference-data/02-review-guide.md).

검증:

```bash
pnpm typecheck                      # 전 워크스페이스
pnpm lint
pnpm --filter @pacer/core test      # 계산 엔진·서비스 (§18.1) — 152 tests
pnpm --filter @pacer/llm test       # 리포트 게이트웨이 (§18.2) — 10 tests
pnpm --filter @pacer/web build
```

## 구현 현황

### P0 — 6모 선공개 (완료)

| 영역 | 상태 | 비고 |
| --- | --- | --- |
| 계산 엔진 (§8) | ✅ | 검증·정규화·자격판정·환산(정확/근사/불가)·입결비교·구간(보정 7종)·신뢰도·reason code. 순수·결정적 |
| 분석 서비스 (§17.3) | ✅ | 검증→정규화→후보로드→…→스냅샷 저장 오케스트레이션. 분석 불가/자격 미달 투명 집계(§8.2) |
| AI 리포트 (§11) | ✅ | LLM Gateway: 스키마(§11.3)·reason code 보캐블러리·금지어(§11.4)·면책(§13.3) 검증. 실모델/스텁 동일 파이프라인 |
| API 라우트 (§10) | ✅ | cycles·scores·targets·analysis·reports·saved-units·notifications/subscribe. 익명 세션 소유권 검사 |
| DB (§9) | ✅ | Prisma 스키마 전체 + 마이그레이션 |
| UI (모바일 퍼스트) | ✅ | 구간 5색 토큰, 칩 선택·자동 포커스 진행, 성적표/가채점 모드, 학생/학부모 탭 리포트 |
| PWA | ✅ | manifest·아이콘·Service Worker·OG 이미지 |
| 알림 발송 | 🚧 | 구독 저장까지 완료. 발송 어댑터(알림톡/이메일/웹푸시)는 스텁 |
| 관리자 데이터 도구 (§12) | ✅ | `/admin/review` 검수 워크플로(규칙·입결 큐, AI초안 확정, 클러스터 일괄). 사용법 `docs/reference-data/02-review-guide.md` |

### P1 — 9모 베타 (백엔드 코어 완료)

| 영역 | 상태 | 비고 |
| --- | --- | --- |
| 6모↔9모 변화 분석 (§7.7.2) | ✅ | `engine/trend.ts` — 과목별 상승/하락(백분위>표준>등급), 구간 전이, 새/빠진 후보, 목표 접근도 변화 |
| 9모 변화 리포트 배선 | ✅ | `september_change_report`가 6모 기록을 자동 로드해 trend를 LLM 입력에 동봉. 6모 미보유 유저도 생성 가능(고지 추가) |
| 점수 시뮬레이션 (§7.9) | ✅ | `POST /simulations` — 가상 점수로 엔진 재실행(저장 없음). 적정 진입 수·효율 과목·주의 과목 + 주의 문구 동봉 |
| 결제(web PG)·PDF·workers 큐 | ⬜ | PG사 선정 후 진행 (§14.1 IAP 회피) |
| 9모 UI (시뮬레이션 화면 등) | ⬜ | |

### P2 — 수능 메인 (백엔드 코어 완료)

| 영역 | 상태 | 비고 |
| --- | --- | --- |
| 외부 도구 수동 입력 (§10.7) | ✅ | `POST/GET /competitor-signals` — 진학사 칸수/고속 색상/텔레그노시스 확률. **수동 입력 전용, 자동 수집 금지(§7.7.4)** |
| 교차검증 (§7.7.4) | ✅ | `engine/cross-validate.ts` — agree/near/disagree/uncertain 분류 → `cross_validation_report`. 정확도 우열 판정 금지(§11.1) |
| 가/나/다군 조합 (§7.10) | ✅ | `engine/application-plan.ts` — 전략 매트릭스(안정/균형/공격/custom), 보수적 fallback, 단정 금지 요약. `POST /application-plans` |
| 합불 수집 (§7.11) | ✅ | `POST/GET /outcomes` — 모순 데이터 차단, 재제출은 갱신. 데이터 해자의 시작점 |
| 정밀 환산 확대·컨설턴트 검수·부하 대비 | ⬜ | |

구현 경위: `docs/03-p0-implementation-report.md`(P0), `docs/04-p1-p2-foundation.md`(P1/P2). 테스트는 단위 162개 — 엔진 캘리브레이션 상수와 교차검증 휴리스틱 매핑은 `packages/core/src/engine/constants.ts` 한 곳에 모여 있으며 실데이터 축적 후 보정한다.

## API 표면 (§10)

```
POST /api/cycles                                  사이클 생성(익명 가능)
POST /api/cycles/{id}/scores                      성적 저장 (시험별 upsert)
POST /api/cycles/{id}/targets                     목표 저장
POST /api/cycles/{id}/analysis/run                분석 실행 → 스냅샷
GET  /api/analysis/{snapshotId}/results           결과 조회 (면책 동봉)
POST /api/cycles/{id}/reports                     AI 리포트 생성 (6종 report_type)
POST /api/cycles/{id}/simulations                 점수 시뮬레이션 (P1, 저장 없음)
POST /api/cycles/{id}/competitor-signals          외부 도구 결과 수동 입력 (P2)
POST /api/cycles/{id}/application-plans           가/나/다군 조합 생성 (P2)
POST /api/cycles/{id}/outcomes                    합불 결과 제출 (P2)
POST /api/cycles/{id}/notifications/subscribe     알림 구독 (알림톡→이메일→웹푸시)
POST /api/cycles/{id}/saved-units                 관심 모집단위 저장
```

요청/응답 계약은 전부 `packages/shared/src/contracts.ts`(Zod)에 있다 — 라우트는 "계약 parse → 서비스 호출 → serialize"만 하는 얇은 어댑터다.

## 원칙 (깨면 안 됨)

- **예측이 아니라 해석** — 합격 확률 단정 금지(§2.1). 금지어 필터(§11.4) 미통과 리포트는 저장되지 않는다.
- **계산 엔진 ≠ LLM** — 엔진이 계산하고 LLM은 설명만 한다(§8.1). trend·교차검증·조합도 전부 엔진이 계산한 수치만 LLM에 전달된다.
- **환산식·입결 원문은 서버 전용** — 클라이언트에는 결과(구간·점수차·코드)만 내려간다(§8.1). 시뮬레이션 응답도 동일.
- **외부 도구 데이터는 수동 입력 전용** — 자동 스크래핑 금지(§7.7.4).
- **AdmissionCycle 중심 + 익명 세션 1급**(§9) — User는 nullable. 가입 전환은 나중에.
- **모든 결과/리포트에 면책·AI 고지**(§13.3/13.4) — 문구는 `@pacer/shared` 원문 그대로, 임의 수정 금지.
- **6모 코드 = 9모/수능 코드** — exam_type 파라미터화로 같은 코드가 시즌 전체를 처리한다(§19).

## 문서

- `PRODUCT_SPEC.md` — 제품 명세 (진실의 원천, 섹션 번호로 Grep)
- `docs/00-쉽게-이해하는-Pacer.md` — 비전문가용 그림 설명
- `docs/01-architecture.md` — 폴더 구조·의존 방향·백엔드 분리 이음새
- `docs/02-implementation-plan.md` — P0/P1/P2 단계 계획
- `docs/03-p0-implementation-report.md` — P0 구현 보고서 (엔진→서비스→리포트)
- `docs/04-p1-p2-foundation.md` — P1/P2 백엔드 기반 구축 보고서
- `docs/adr/` — 아키텍처 결정 기록
- `docs/reference-data/` — 레퍼런스 데이터 현황(`01-data-status`)·검수 가이드(`02-review-guide`)·작업 프로토콜(`03-remaining-work-protocol`)
- `packages/reference-data/` — 대학·입결·환산규칙 수집·검수·시드 도구

## 면책

본 서비스의 분석 결과는 공개 입시자료와 사용자가 입력한 성적을 바탕으로 한 참고용 정보입니다. 실제 합격 여부는 수능 본성적, 모집인원, 수시 이월, 지원자 표본, 경쟁률, 대학별 산출 방식 변경 등에 따라 달라질 수 있으며, 본 서비스는 합격을 보장하지 않습니다.
