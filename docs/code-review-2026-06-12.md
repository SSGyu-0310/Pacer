# 코드리뷰 & 프론트엔드 개선 기록 — 2026-06-12

범위: `apps/web` + `packages/core` 서비스 인터페이스. **DB/참고데이터 수집(`packages/reference-data`, `packages/db` 데이터)은 병행 작업 중이므로 제외.**

## 1. 프로젝트 현황 (코드 기준)

- 커밋 `11fb356` 로 P0 내부 데모 완성: 계산 엔진(core 3.5k LOC, 테스트 9개 파일) · 분석 파이프라인 · AI 리포트(LLM 게이트웨이 + 스텁 폴백) · 모바일 UI(web 3.2k LOC).
- 모노레포(pnpm + turbo): `apps/web`(Next.js App Router) / `packages/{core,shared,db,llm,notifications,reference-data}`.
- 루트 `CLAUDE.md`는 "pre-code" 상태 설명이라 **현행과 불일치** — 갱신 필요(차기 작업 권장).
- 스펙 핵심 원칙 준수 상태: 엔진/LLM 분리(§8.1) ✅, 환산식 클라이언트 비노출(§8.1) ✅, 익명 세션 퍼스트(§2.6, authz는 anon 쿠키 대조) ✅, 면책 문구 동봉(§13.3) ✅, 분석 이벤트명 §16.5 enum 사용 ✅.

## 2. 이번에 추가한 기능 — 전국 분포 종 그래프

점수 입력 → 분석 결과 화면 최상단에 정규분포 곡선 위 내 위치 시각화.

- `components/ScoreBellCurve.tsx` (신규): 의존성 없는 순수 SVG. 성적표 **백분위를 역정규분포(Φ⁻¹, Acklam 근사)** 로 변환해 곡선 위 위치를 잡는다. 검증: 왕복 오차 < 7e-8, Φ⁻¹(0.93)=1.4758 등 기준값 일치.
- 과목 칩(국어/수학/탐구1/탐구2 — 선택과목명 표기) 전환 + 마커·면적 CSS 트랜지션 애니메이션. 영어·한국사는 절대평가라 제외.
- 수치 요약(표준점수·백분위·상위 %) + 해석용 고지 문구. 단정 표현 없음(§11.4 금지어 준수).
- API: `GET /api/analysis/[snapshotId]/results` 응답에 `subject_scores`(본인 입력 점수)·`track` 추가. 환산식/입결이 아닌 사용자 본인 데이터이므로 §8.1 비노출 원칙과 무관. `core/ScoreService.getById()` 추가(순수 포트 위임).
- **종합(전과목) 보기**: 과목 백분위 → z점수 → 가중 z평균 → Φ로 재백분위화. 백분위 단순 평균의 통계 왜곡 회피, 과목 간 상관 1 가정의 **보수적** 추정(전과목 고른 학생의 실제 종합 순위는 표시보다 높을 수 있음 — 고지 문구 포함). 산출식 프리셋 3종: 균등(국1:수1:탐1 — '국수탐 백분위 합 300' 통용 기준, 합계 수치 병기), 인문형(국4:수3:탐3), 자연형(국2.5:수4:탐3.5). 사이클 계열(track)에 따라 기본 프리셋 자동 선택. 검증: flat50→50.00, flat99→99.00 경계 일치, 샘플(93/96/94/90) 균등 93.92 수기 계산 일치. ※ 검증 중 normalCdf의 erf 인자 √2 스케일 누락 버그를 잡아 수정함.

## 3. 발견·수정한 이슈

| # | 위치 | 문제 | 수정 |
|---|------|------|------|
| 1 | `analysis/page.tsx` | localStorage 없으면 URL `snapshotId`가 있어도 에러 — 같은 브라우저 새 탭/저장소 삭제 시 결과 못 봄 | URL만으로 조회 허용, 사이클 의존 동작(저장/리포트/알림)은 안내 토스트로 가드 |
| 2 | `analysis/page.tsx` `share()` | 공유 시트 취소(AbortError) 시 unhandled rejection | try/catch + AbortError 무시 + 클립보드 폴백 |
| 3 | `analysis/page.tsx` | 작업 결과 공지가 페이지 중간 inline — 하단 CTA 클릭 시 화면 밖이라 안 보임 | `Toast` 컴포넌트 신규(CTA 위 고정, aria-live, 자동 소멸) |
| 4 | `score/page.tsx` | 필수 점수 비우면 zod 영문 에러("Expected number, received nan") 노출 | `requiredScore()` 헬퍼로 한국어 메시지 통일 |
| 5 | `score/page.tsx` | 표준점수/백분위 입력은 에러 시 테두리 강조 누락(원점수만 있음), 라벨-입력 미연결 | 전 숫자 필드 error 전달 + `Field as="label"`(단일 입력만 — 칩 그룹은 div 유지, label이면 라벨 탭이 첫 버튼을 오클릭) |
| 6 | `layout.tsx` | `maximumScale: 1` — 저시력 사용자 핀치줌 차단(WCAG 1.4.4) | 제한 제거 |
| 7 | `dashboard/page.tsx` | `pt-3` 수직정렬 핵(폰트 변경 시 깨짐), "성적 입력" 완료 판정이 snapshotId 의존 | flex 정렬 + 버튼 스타일 타 페이지와 통일, `examScoreId` 기준 판정 |
| 8 | 4개 페이지 공통 | `STORAGE_KEY`/`ADMISSION_YEAR`/`postJson`/`readStoredState` 중복 정의(에러 처리 품질도 제각각) | `lib/client.ts` 로 통합 — 서버 메시지 우선 노출 버전으로 단일화 |
| 9 | `UnitCard.tsx` | reason "+N 더보기" 펼친 뒤 접기 불가 | 토글로 변경 |
| 10 | `AlertSheet.tsx` | 전화/이메일 input에 `type` 누락 — 자동완성·키보드·기본 검증 미작동 | `type="tel/email"` + `autoComplete` |
| 11 | `analysis/page.tsx` | 분석 0건 안내문이 탐구 케이스만 언급 | 원인 일반화(과목 조합·목표 조건) |

## 4. 수정하지 않고 남긴 관찰 (제안)

- **데모 기본값**: 점수 폼이 샘플 점수로 프리필 — 내부 데모용 의도로 보이나, 베타 공개 전 빈 값 + placeholder 전환 필요.
- **`numberField` 자동 진행**: 3자리 도달 시 다음 필드 이동 — 121→131 수정 같은 재편집 시 커서 튐 가능. 베타 전 사용성 테스트 권장.
- **탐구 표준점수 max 200 허용**: 실제 탐구 표준점수 상한(~80대)보다 느슨. 엔진 검증(§18.1)과 별개로 폼 단계 소프트 경고 고려.
- **`CLAUDE.md` 갱신**: pre-code 설명 → 현행 모노레포/명령어 반영.
- **공유 링크**: 현재 origin만 공유(스냅샷 링크는 anon 쿠키 때문에 타인이 못 열음 — 올바른 보안 동작). P1에서 OG 카드 공유 전용 공개 뷰 필요할 것.

## 5. 검증

- `tsc --noEmit`: `apps/web` ✅ / `packages/core` ✅
- `eslint --max-warnings=0` (변경 파일 전체) ✅
- Φ⁻¹ 수치 검증 ✅ (위 §2)
- `vitest`/`next build`는 이 환경에서 네이티브 바이너리(macOS용 rollup/swc) 문제로 실행 불가 — 로컬에서 `pnpm --filter @pacer/core test && pnpm build` 1회 확인 권장.
- 커밋하지 않음 — 참고데이터 수집 작업트리와 섞이지 않도록 워킹트리에만 반영.
