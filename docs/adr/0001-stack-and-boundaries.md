# ADR 0001 — 스택 및 경계 결정

- 상태: 채택 (2026-06-06)
- 관련: 스펙 §17.1, `docs/01-architecture.md`

## 맥락
스펙 §17.1은 백엔드를 "Next.js API Routes **또는** FastAPI", ORM을 "Prisma **또는** Drizzle"로 열어두었다. 이 선택이 폴더 구조 전체를 결정한다.

## 결정
1. **Next.js 풀스택으로 시작**하되, 내부 구조는 **백엔드 분리(FastAPI 등)가 가능한 경계**로 설계한다.
   - 도메인 코어(`packages/core`)는 Next.js·Prisma·HTTP를 import하지 않는다.
   - API 라우트(`apps/web/app/api/*`)는 얇은 어댑터: 검증 → 서비스 호출 → 직렬화만.
   - API 계약(`packages/shared/contracts`)을 단일 출처로 둔다 = 분리 이음새.
2. **ORM은 Prisma**, 단 **repository 포트 뒤에 격리**한다.
   - Prisma는 `packages/db`에만 존재. 서비스·엔진은 도메인 엔티티로만 일한다.
   - "추후 FastAPI 분리"를 감안해 ORM 의존을 도메인으로 흘리지 않는다(orm 로직 깊이 조정).
3. 모노레포: **pnpm workspaces + Turborepo**.
4. DB: provider 무관 `DATABASE_URL`(Postgres). 공급자(Supabase/Neon)는 후속 결정.

## 결과
- 장점: 단일 배포로 빠르게 6모 선공개(§19 Phase 0/1). 코드 재사용(§2.2). 분리 시 프론트·계약 무변경.
- 비용: 도메인↔Prisma 매핑 보일러플레이트(의도된 비용).
- 분리 트리거: 수능 시즌 부하·배치(§18.4)가 Vercel 함수 한계를 넘으면 `core`/`workers`를 별도 서비스로 추출.

## 미결정 (다음 ADR 후보)
- DB 공급자(Supabase vs Neon), 인증(카카오/이메일/익명) 구현, LLM 게이트웨이 벤더, ESLint 경계 규칙 도입.
