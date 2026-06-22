# AGENTS.md

이 저장소의 에이전트 가이드는 **[`CLAUDE.md`](CLAUDE.md) 하나로 통일**한다. Codex 등 모든 AI 에이전트는 `CLAUDE.md`를 따른다 — 제품 포지셔닝, 아키텍처 규칙(코어는 Next/Prisma/HTTP 비의존, 라우트는 얇은 어댑터, enum·계약은 `packages/shared`), 통제 어휘(`exam_type`/band/confidence/`report_type`/reason code), 로드맵 단계가 모두 거기 있다.

제품 명세(요구사항의 진실의 원천)는 [`PRODUCT_SPEC.md`](PRODUCT_SPEC.md) — 섹션 번호(§8 계산 엔진, §9 데이터 모델, §10 API)로 Grep해 해당 부분만 읽는다.

> 과거 이 파일은 별도 사본이었다가 "pre-code"라는 오래된 내용으로 드리프트했다. 중복을 없애려 `CLAUDE.md` 포인터로 대체했다 — 가이드 변경은 `CLAUDE.md`에서만 한다.
