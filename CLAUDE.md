# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

This is a **pnpm + Turborepo monorepo** (Next.js App Router fullstack, Prisma behind repository ports). Implemented so far:

- **P0 (6모)**: calculation engine (`packages/core/src/engine`), analysis/report services, LLM gateway with banned-word filter, Prisma repositories, API routes, notification subscription. See `docs/03-p0-implementation-report.md`.
- **P1/P2 backend foundations (9모·수능)**: trend diff (6모↔9모), score simulation, competitor-signal cross-validation, ga/na/da application plans, outcome collection — engine + services + routes + tests. See `docs/04-p1-p2-foundation.md`. Payments / PDF / workers / new UI pages are **not built yet**.
- **Reference-data review tool (admin)**: localhost-only `/admin/review` (rule/outcome queues, AI-proposal confirm, cluster apply) writing to the shared Supabase. See `docs/reference-data/02-review-guide.md`. Reference data (215 universities, ~68k outcomes, 4,868 rules) is collected (2021–2026; 2027 awaiting public release) and seeded but mostly `parsed`/awaiting review — see `docs/reference-data/01-data-status.md`.
- **Not built**: 카카오/이메일 login (anonymous session only), payments, PDF, notification send adapters (stubbed), P1/P2 UI pages.

Commands: `pnpm typecheck`, `pnpm lint`, `pnpm --filter @pacer/core test`, `pnpm --filter @pacer/llm test`, `pnpm db:generate`. Architecture and folder boundaries: `docs/01-architecture.md` (core imports no Next/Prisma/HTTP; routes are thin adapters; enums/contracts only in `packages/shared`). Note: `node_modules/vitest` is a sandbox shim replaced by real vitest on `pnpm install`.

The spec (`PRODUCT_SPEC.md`) is the source of truth. When implementing, read the relevant spec section first (the document is section-numbered, e.g. §8 계산 엔진, §9 데이터 모델, §10 API). It is long — use Grep to jump to a section rather than re-reading the whole file.

## What the product is

**Pacer** (Korean: 페이서) is a **PWA (mobile-first responsive web app)** that helps Korean students/parents track exam scores across the admission cycle (6모 → 9모 → 수능) and produces AI strategy reports. It is explicitly **not** a one-shot score calculator and **not** a native app at launch. Three positioning rules drive most product decisions:

1. **Interpretation over prediction** (§2.1). Never assert hard admission probabilities. The product explains *reasoning*, cross-validates external tools (진학사/고속성장/텔레그노시스), and surfaces uncertainty. There is a banned-phrase filter (§11.4) — outputs must not contain "합격 보장", "무조건", "100%", "진학사보다 정확", etc.
2. **The whole admission cycle, not one exam** (§2.2). Data and UX are modeled as a continuous timeline, not isolated analyses. The 6모 release is a *pre-launch* of the 수능 main service using the same codebase.
3. **PWA-first, no install gate** (§1.4, §2.6). Entry must be frictionless (link → input → result). Native app is deferred until 추합 real-time-alert ROI is proven.

## Architecture the code must follow

### Data model is `AdmissionCycle`-centric (§9)

The entire schema hangs off `AdmissionCycle`, **not** off `User`. `User` is nullable; anonymous sessions are first-class via `anon_session_id`, because the funnel starts anonymous and converts to signup later. Preserve this — do not require a user to create cycle/score/target data.

Core chain (§23):
```
User (nullable)
 → AdmissionCycle (per admission_year)
   → ExamScore (exam_type: june_mock | september_mock | csat)
     → SubjectScore
   → TargetSnapshot   (one per exam_type — targets change as scores change)
   → AnalysisSnapshot → AnalysisResult (per AdmissionUnit)
   → StrategyReport
   → SavedAdmissionUnit
   → ApplicationPlan (ga/na/da combination)
   → FinalOutcome     (real accept/reject — the data moat)
```
Reference data (`University`, `AdmissionUnit`, `AdmissionRule`, `HistoricalOutcome`) is admin-curated and versioned with `verified_status` / `confidence`. `CompetitorSignal` (외부 도구 결과) is **manual user input only — never auto-scraped** (§7.7.4).

### Calculation engine vs. LLM are strictly separated (§8.1, §11.1)

- **The calculation engine computes; the LLM only explains.** The engine does score validation, normalization, eligibility, per-university converted scores, historical comparison, band classification, confidence scoring, and `reason_code` generation. The LLM never computes scores or probabilities — it turns the engine's structured output into prose.
- The engine runs **server-side**. Conversion formulas and 입결 data must **not** be shipped to the PWA client — only results plus source links (§8.1).
- LLM input/output are **structured JSON with schema validation** (§11.2, §11.3), keyed off a controlled vocabulary of `reason_code`s (§8.5). Reports carry `prompt_version` and `model_name`.

### Controlled vocabularies (use these exact enum values)

- `exam_type`: `june_mock` | `september_mock` | `csat`
- `score_status`: `estimated` | `official`
- band (구간): `stable` | `match` | `reach` | `challenge` | `risk` (안정/적정/소신/도전/위험)
- confidence: `high` | `medium` | `low` | `limited`
- `report_type`: `june_position_report` | `september_change_report` | `csat_final_report` | `cross_validation_report` | `parent_summary_report` | `application_plan_report`
- notification `channel`: `kakao_alimtalk` | `email` | `web_push`
- reason codes (strength/weakness/recommendation): defined in §8.5 — extend that table rather than inventing ad-hoc strings.

### Notification = multi-channel by priority (§5, §17.5)

Re-engagement (9모/수능) is the product's spine and must not depend on one channel. Priority order: **1) 카카오 알림톡, 2) email, 3) web push**. Critical constraint: **iOS web push only works on iOS 16.4+ for users who installed the PWA** — un-installed iOS users are unreachable by push, so 알림톡/email must cover them. Web-push permission is requested *after* the user sees value (e.g. at 9모 alert signup), not on signup.

### Two audiences, two voices

Every report produces both a `student_summary` and a `parent_summary` (§11.3). Parent-facing text avoids jargon. The 면책 문구 (disclaimer, §13.3) and AI-usage notice (§13.4) appear on every result screen, report, and PDF.

## Stack (§17.1 — committed: Next.js + Prisma + Supabase Postgres + Anthropic LLM)

Frontend: Next.js (App Router, SSR/SSG for SEO + share previews), TypeScript, Tailwind, React Hook Form, Zod, Service Worker + Web App Manifest, VAPID web push.
Backend: Next.js API routes or FastAPI, PostgreSQL, Prisma or Drizzle, optional Redis + background job queue (for 수능-season load and batch notifications).
Infra: Vercel, Supabase/Neon, Cloudflare, S3-compatible storage (PDFs + OG share cards). AI via an LLM gateway with prompt versioning, JSON-schema validation, banned-word filter, caching.

## Roadmap phasing (§19, §20)

Build is phased to the exam calendar: **P0 = 6모 pre-launch** (anonymous-session cycle, score input, basic analysis engine, 6모 + parent reports, save, 9모 alerts, OG share card, admin data tools, PWA shell), **P1 = 9모 beta** (6모-vs-9모 diff, score simulation, paid reports via web PG, PDF), **P2 = 수능 main** (external-tool cross-validation, ga/na/da combinations, payments, outcome collection). Whatever ships in 6모 must be reusable as-is for 9모 and 수능 — don't build throwaway 6모-only code.

## Notes for working here

- Domain terms, product copy, and spec are in Korean; keep user-facing strings and disclaimers in Korean and match the spec's exact wording for legal/disclaimer text (§13.3, §13.4).
- Payments use **web PG (card/카카오페이/네이버페이)**, deliberately avoiding app-store IAP fees — a reason PWA-first matters commercially (§14.1).
- Analytics event names are enumerated in §16.5 (`landing_view`, `score_submit`, `reminder_opt_in` with channel param, etc.) — use those names.
