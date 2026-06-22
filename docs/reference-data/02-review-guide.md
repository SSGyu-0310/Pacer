# 레퍼런스 데이터 검수 + 가중치(rule) 입력 온보딩 가이드

새로 합류한 검수 협업자가 **이 문서 하나**로 작업을 시작하기 위한 실무 가이드다. Pacer의 reference-data(대학·모집단위·입결·전형규칙)는 전부 자동 파싱된 `needs_human_verification` 후보 상태이고, 사람이 원문과 대조해 검수·승격해야 운영에 쓰인다.

- 깊은 수집 프로토콜(A~D: manual source discovery, parser repair, detail/attachment crawl, 2027 공개대기)은 이 문서에 옮기지 않는다. 그건 별도 위임용이며 [`03-remaining-work-protocol.md`](./03-remaining-work-protocol.md)에 있다. 여기서는 **검수·rule 입력·승격**만 다룬다.

---

## 1. 시작하기 전

### 무엇을 검수하나
- **rule(전형 규칙 / 환산식)**: 대학별 2027 정시 수능 환산식. 자동 파싱본은 가중치가 비어 있거나 추정치라, 사람이 공식 모집요강과 대조해 채워 넣어야 한다.
- **outcome(입결)**: 과거 HistoricalOutcome 후보. 원문과 대조해 confidence(신뢰도)를 정한다.

### 현재 데이터 상태
- 대학-연도 cell 1,505개 중 `source_rich_review_ready` 1,256, 검수 decision log 5,508행(approved 4,272 / pending 1,236).
- 핵심대 50개 환산식: `verified:true` 42건, blocker 8건(아래 6절).
- 자세한 수치 스냅샷은 동일 폴더의 [`01-data-status.md`](./01-data-status.md)(데이터 상태) / [`03-remaining-work-protocol.md`](./03-remaining-work-protocol.md) "현재 남은 건수"를 참조.

### 절대 규칙
- **공식 출처만.** 대학 입학처 2027 정시 모집요강(PDF/HWP) 또는 ADIGA 공식 페이지. 사설 입시업체·블로그·커뮤니티 금지.
- **추정 금지.** 원문에서 직접 읽은 값만 입력. 못 찾으면 비우고 `uncertain`에 사유를 남긴다.
- **해석이지 예측이 아니다(§2.1).** 합격 확률·"합격 보장"·"무조건"·"100%"·"진학사보다 정확" 등 금지 표현(§11.4)을 산출물 어디에도 넣지 않는다.

---

## 2. 엔진의 2개 레버 — 왜 검수가 중요한가

검수가 운영 결과를 바꾸는 통로는 딱 두 가지다.

1. **rule을 채우면 환산이 풀린다.** 가중치(환산총점·국수탐 비율 등)가 비면 계산엔진은 그 모집단위를 `unsupported`/`approx`로 떨어뜨린다. rule을 유효하게 채워 넣으면 `mapRule`이 인식해 **`exact`(정확 환산)** 로 바뀐다. 검수 도구는 이 판정을 클라이언트에서 미리 미러링해 "exact 풀림 ✓/✕"를 실시간으로 보여준다.
2. **confidence를 낮추면 band가 보수화된다.** 입결 confidence를 낮게 매기면 분석이 더 보수적으로(적정/안정 쪽으로) 처리된다 — 불확실한 데이터로 위험한 단정을 하지 않게 하는 안전장치다.

즉 rule 입력은 "분석이 켜지냐"를, confidence 검수는 "분석이 얼마나 단정적이냐"를 결정한다. 둘 다 **원문 대조 후에만** 손대야 한다.

---

## 3. 검수 도구 사용법 (`/admin/review`)

웹 검수 도구가 빌드되어 있고, 저장이 **공용 Supabase DB에 바로 반영**된다. 즉 여기서 누른 verdict는 실시간으로 운영 decision에 들어간다 — 신중히.

### 접속 (3가지 모두 필요)
1. 환경변수 `ADMIN_ENABLED=1` 와 `ADMIN_TOKEN=<토큰>` 을 설정하고 dev 서버를 띄운다.
2. **localhost(127.0.0.1)에서만** 동작한다. 다른 host면 404/403. (`apps/web/lib/admin-auth.ts`)
3. 브라우저에서 `/admin/login` 에 접속해 `ADMIN_TOKEN` 값을 입력 → 쿠키(`pacer_admin_token`, httpOnly, 상수시간 비교) 발급 → `/admin/review` 로 이동.

토큰/host/`ADMIN_ENABLED` 중 하나라도 안 맞으면 페이지는 `notFound()` 처리되어 존재하지 않는 것처럼 보인다.

### 화면 구성
- 좌측: 큐 리스트. 상단 토글로 **규칙(클러스터) ↔ 입결** 큐를 전환. 각 항목에 `AI`(초안 있음)·`검수완료`/`대기` 배지, rule이면 클러스터 크기(`N개 단위`)가 표시된다.
- 우측: 원문/근거 카드 + 편집 패널(rule이면 `RuleFieldEditor`, outcome이면 confidence 컨트롤). 우측 패널 하단에 키보드 힌트.

### 키보드 단축키
| 키 | 동작 |
|---|---|
| `j` / ↓ | 다음 항목 |
| `k` / ↑ | 이전 항목 |
| `Enter` | rule: 폼 저장(verified). outcome: confidence=`high` |
| `s` | 스킵 |
| `f` | 플래그 |
| `a` | 현재 큐의 AI초안 항목 일괄 확정(확인 prompt) |
| `1`~`4` | (outcome 큐에서만) confidence = 제한/낮음/중간/높음 |

입력 필드(input/textarea/select)에 포커스가 있으면 단축키는 무시된다.

### rule 저장 흐름
1. 우측 `RuleFieldEditor`에서 환산총점·가중치(국/수/탐)·영어·탐구·(고급)한국사/지원자격을 채운다.
2. 패널 상단 배지가 **"✓ 풀림 — 저장하면 정확 환산이 켜집니다"** 가 되어야 저장 버튼이 활성화된다(`exact` 미충족이면 저장 불가).
3. `저장(Enter)` → verdict `edit` + `reviewed_verified_status: "verified"` + `corrected_fields` + `apply_to_cluster: true` 로 DB 기록. 클러스터면 "N개 모집단위에 일괄 저장" 토스트가 뜬다.
4. **AI초안 확정 루프**: AI 초안이 있는 rule은 상단 `AI초안 확정` 버튼(또는 `a`로 일괄)으로 초안 그대로 verified 확정 가능. 초안을 그대로 믿지 말고 원문과 맞을 때만.

> ⚠️ **코드 vs 옛 런북 차이**: 빌드된 `RuleFieldEditor`의 영어 mode는 현재 `deduction`/`addition` 2종만 제공한다. 4절 스키마의 `ratio`(영어 비율반영)는 **JSONL fill 파이프라인(4~5절)** 에서만 표현되고, 웹 폼에는 아직 노출되지 않는다. 영어 ratio 대학은 폼이 아니라 `core-rule-fills.jsonl`로 처리한다.

### outcome 저장 흐름
우측 confidence 컨트롤(제한/낮음/중간/높음 = `1`~`4`)에서 원문과 대조해 신뢰도를 고른다. 선택 즉시 verdict `edit` + `reviewed_confidence` 로 저장된다(항목 이동 없음).

---

## 4. 가중치(rule) 입력 스키마

웹 폼으로 못 푸는 복잡한 환산식(특히 영어 ratio)은 연구용 JSONL fill 파일로 작성한다. 산출 파일은 `packages/reference-data/data/review/core-rule-fills.jsonl` (대학 1개당 1줄). 엔진이 `exact`로 인정하려면 아래가 **모두** 유효해야 한다.

```jsonc
{
  "universityId": "…",            // 워크리스트의 universityId 그대로
  "universityName": "건국대학교",
  "year": 2027,
  "source": "https://…",          // 실제로 본 공식 출처 URL
  "scoreType": "percentile",       // standard | percentile | mixed | custom
  "totalScale": 1000,              // 환산 총점(>0)

  // ── 영역 반영비율: 계열별로 다르면 tracks를 나눈다 ──
  "tracks": [
    {
      "majorGroups": ["인문교육", "사회경영"],   // 이 비율이 적용되는 계열들
      "weights": { "korean": 30, "math": 25, "inquiry": 20 }  // 국/수/탐 (출처 표기 그대로)
    },
    {
      "majorGroups": ["공학", "자연", "보건의료"],
      "weights": { "korean": 20, "math": 35, "inquiry": 20 }
    }
  ],

  // ── 아래는 보통 대학 단위로 동일(계열별로 다르면 track 안에 같은 키로 override) ──
  "english": {                     // 영어 반영 방식 3종
    "mode": "deduction",           // deduction(등급별 감점) | addition(등급별 가산점) | ratio(반영비로 합산)
    "byGrade": { "1": 0, "2": 2, "3": 5, "4": 9, "5": 14 }, // 등급→점수. 일부 등급만 적어도 됨
    // ── mode가 "ratio"일 때만(대부분 대학): 영어가 국수탐처럼 가중 합산됨 ──
    "weight": 20,                  // 영어 반영비(국수탐 weights와 같은 단위)
    "scoreMax": 100               // byGrade 환산점수의 만점(예: 100). 생략 시 100
    // ratio면 byGrade는 등급→'환산점수'(감점 아님). 예: {"1":100,"2":98,"3":94}
  },
  "history": {                     // 한국사
    "byGrade": { "1": 10, "2": 10, "3": 10, "4": 9.8 }
  },
  "inquiry": {
    "count": 2,                    // 반영 과목 수: 1 또는 2
    "mode": "average",             // average(평균) | best_one(상위 1과목)
    "conversionRisk": false        // 변환표준점수 사용 등 주의 필요 시 true
  },

  "eligibility": {},               // 지원자격 제한 없으면 {} (선택)
  "verified": true,                // 출처에서 확실히 확인했으면 true
  "uncertain": []                  // 불확실/누락 항목 사유 문자열 배열
}
```

### exact가 풀리는 검증 기준
- `totalScale` > 0
- 각 track의 `weights.korean / math / inquiry` 가 모두 숫자(≥0)
- `english.mode` ∈ {deduction, addition, ratio} — **ratio면 `english.weight`(>0) 필수** (없으면 `mapRule`이 null 반환 → '분석 불가')
- `inquiry.count` ∈ {1,2}, `inquiry.mode` ∈ {average, best_one}
- `history.byGrade`, `english.byGrade` 값은 모두 숫자(빈 객체 `{}`도 허용 — 등급표 못 찾으면 비우고 `uncertain`에 적어라, exact 자체는 풀린다)

### 자주 틀리는 포인트
- ratio의 `byGrade`는 **감점/가산이 아니라 환산점수 그 자체**(예: 1등급 100, 2등급 95).
- 영어가 ratio인데 `weight`를 빠뜨리면 그 단위는 분석 불가가 된다.
- `majorGroup` 7종: `공학 / 자연 / 보건의료 / 인문교육 / 사회경영 / 예체능 / (빈값)`. 반영비율은 보통 계열별로 다르므로 산출 단위는 **대학 × 계열**.
- 한계(모집군별 상이식, 제2외국어 대체, A/B 상위점수 선택 등)에 걸리면 억지로 끼우지 말고 `verified:false` + `uncertain`으로 남긴다.

---

## 5. 승격 워크플로 + 명령어 (사람이 실행)

`core-rule-fills.jsonl`을 갱신한 뒤 fill → DB decision으로 반영하는 절차다. (변환·반영은 사람이 직접 돌린다.)

표준 시퀀스:

```bash
pnpm --filter @pacer/reference-data review:core-rule:prepare      # decisions/blockers 재생성 + 파일 감사
pnpm --filter @pacer/reference-data seed:p0 -- packages/reference-data/data/p0-foundation --dry-run
SEED_CONCURRENCY=2 pnpm --filter @pacer/reference-data seed:p0 -- packages/reference-data/data/p0-foundation
pnpm --filter @pacer/reference-data review:core-rule:verify       # 파일/DB/foundation 감사
```

짧은 명령:

```bash
pnpm --filter @pacer/reference-data review:core-rule:verify       # 실제 seed 없이 현재 상태 검증
pnpm --filter @pacer/reference-data review:core-rule:apply-db     # 실제 DB seed + DB 감사
```

세부 명령(개별 감사):

```bash
pnpm --filter @pacer/reference-data review:build-fill-decisions
pnpm --filter @pacer/reference-data review:build-fill-blockers
pnpm --filter @pacer/reference-data audit:core-rule-review-state      # fills/decisions/blockers 정합성
pnpm --filter @pacer/reference-data audit:core-rule-db-state          # 로컬 decision vs DB active + mapRule 로딩
pnpm --filter @pacer/reference-data audit:core-rule-candidate-smoke   # loadCandidates에서 rule:null 아닌지
pnpm --filter @pacer/reference-data audit:core-rule-analysis-smoke    # 승격 후보가 unsupported로 안 떨어지는지
pnpm --filter @pacer/reference-data audit:foundation-p0-seed
pnpm --filter @pacer/reference-data audit:foundation-operational-readiness
pnpm --filter @pacer/core test                                       # ratio 환산 동작 확인
pnpm --filter @pacer/db typecheck
pnpm --filter @pacer/reference-data typecheck
```

핵심 동작:
- `prepare`는 각 대학 track을 `majorGroup`/`unitNames`로 모집단위에 매칭해 `review-decisions.jsonl`을 만들고, `verified:false` fill은 `core-rule-blockers.jsonl`로 분리한다. 감사는 `verified:true` row에 `추정`·`확인 필요`·`패턴 기반`·`미명시`·`미확인` 같은 고위험 문구가 남아 있으면 **실패**한다.
- exact 계산 가능한 rule만 `verified`로, 변환표준점수 후공개·가산점·상위점수 선택 등 제약이 남은 rule은 `parsed` 저신뢰도로 자동 강등/제한 승격된다(현재 운영 decision 820건: verified 12, parsed 808).
- 2027 unit에 직접 입결이 없으면 `PrismaUnitRepository`가 같은 대학+같은 모집단위명의 score-bearing 과거 HistoricalOutcome을 서버 내부 fallback으로 붙인다(스케일 호환 시에만; 운영 row를 새로 만들지 않음).

승격이 끝나면 해당 모집단위 분석이 `method:"exact"`(또는 `parsed`)로 나오는지 확인한다.

> 웹 도구(3절)는 단건/클러스터 검수를 DB에 바로 쓰고, JSONL 파이프라인(4~5절)은 핵심대 환산식 fill을 일괄 반영한다. 두 경로 모두 동일한 reference decision으로 수렴한다.

---

## 6. 현재 rule-fill 현황 (핵심대 50개, 2026-06-20 기준)

- `verified:true` 42건, blocker 8건. 남은 blocker 중 `parsedPromotionAllowed:true`는 0건(전부 자동승격 완전 금지).
- 영어 ratio 구조화 완료: 강원대·건국대·경북대·광운대·국민대·단국대·동국대·부산대·세종대·숭실대·연세대·이화여대·인하대·한양대·홍익대.
- 원문 직접 검수로 verified 전환된 대표 대학: 서울대·고려대(본교/세종)·연세대(본교/미래)·경희대·서울시립대·서울과기대·국민대·숭실대·인하대·이화여대·명지대·경상국립대 등(다수는 변환표준점수/가산점 때문에 exact가 아닌 `parsed` 제한 승격).

### 남은 8개 blocker

| 대학 | 상태 | 자동승격 금지 사유 |
|---|---|---|
| 서강대학교 | `verified:false` | A형(국1.1/수1.3)·B형(국1.3/수1.1) 산출점수 중 상위 점수 최종 반영 + 탐구 수능 발표 후 공지 변환표준점수. 고정 가중치 엔진 범위 밖. |
| 성균관대학교 | `verified:false` | 자체 변환표준점수/변환백분위 + A/B 유형 상위 성적. 영어 등급별 세부 변환점수표가 fill 근거에 없어 ratio skeleton만 보존. |
| 건국대학교(f2f8c9ff) | `verified:false` | 의예과 제외 전 단위가 국·수·영·탐 중 우수 2과목 50/50 선택식. 현 p0 후보가 골프산업·스포츠건강 예체능/실기형뿐이라 제외. |
| 중앙대학교(5cc63e2f) | `verified:false` | ADIGA 2027 원문에 정시 수능 환산방법 미확정 명시. 기존 verified row의 totalScale 800도 추정치. |
| 중앙대학교 | `verified:false` | 정시 환산방법 미확정. 탐구 변환표준점수 추후 공지, 한국사 가산점·예체능/안성 단위 복잡도. |
| 홍익대학교(6d6dd9ce) | `verified:false` | 영어 환산표/한국사 감점은 정정했으나 exact 검증 전. 예술경영학부는 수능우수자 산식 직접 적용 모집단위로 안전 확인 불가. |
| 홍익대학교(76436861) | `verified:false` | 캠퍼스자율전공처럼 인문/자연 분리 필요한 단위 제외. 예술경영학부 동일 사유. |
| 포항공과대학교 | `verified:false` | 공식 scope override상 정시/수능위주 gap 아님(수시 중심). ADIGA 2027 selection raw에 일반 수능 환산식 없음. |

추가 보류 근거(최신성 재확인): 중앙대·성균관대는 공식 입학처에 2027 정시 확정 산출표가 아직 없고(2026 정시요강만 노출), 2026 표를 2027로 전용하지 않는다. POSTECH은 서류·면접 중심 + 수능최저 케이스라 일반 환산식 scope 밖. 전남대·충북대는 전국최고 표준점수/기본점수 구조라 exact 금지, 2027 p0 unitName으로 좁힌 일반 단위만 `parsed` 제한 승격됨.

---

## 7. 2027 공개 모니터링

신규 수집 관점의 남은 작업은 전부 `wait_for_public_release`다(P1 560건 → 190개 release-monitor target으로 압축). 2027 입결/최종등록자/경쟁률은 **공식 입학처/ADIGA에 실제 공개되기 전에는 수집하지 않는다.** 공개 여부만 `foundation_release_monitor_checklist`로 확인하고, 공개 전에는 `releaseEvidenceStatus=not_public_yet`만 기록한다. 2026/2025 결과표나 모집요강의 "전년도 참고표"를 2027 outcome으로 승격하면 안 된다. 공개 확인 후 narrow collector input을 만드는 절차는 [`03-remaining-work-protocol.md`](./03-remaining-work-protocol.md) "위임 단위 선택: 2027 공개 모니터링" 단락에 있다.

---

## 8. 금지사항

- **CompetitorSignal 자동 수집 금지.** 진학사·유웨이·고속성장·텔레그노시스 등 경쟁 도구 자료는 절대 자동 스크래핑하지 않는다 — spec상 `CompetitorSignal`은 사용자 수동 입력 데이터다(§7.7.4).
- **출처 없는 verified 금지.** 원문을 직접 보지 않고 `sourceConfidence`/`verified`를 만들지 않는다. 모든 신규 row는 `needs_human_verification`이 기본. fill의 `verified:true`는 공식 출처 직접 확인 시에만.
- **추정 금지·예측 금지.** 합격 확률/단정 표현, 금지 표현(§11.4)을 산출물에 넣지 않는다.
- **연도 혼동 금지.** 같은 source가 여러 연도 gap에 붙어 있으면 본문 결과 연도와 collection year를 분리한다. 모집요강의 "최근 입시결과"는 그 요강 연도 결과가 아닐 수 있다.
- **저품질 OCR 신뢰 금지.** PDF text가 저품질이면 숫자를 그대로 믿지 말고 원본 표와 spot check. PDF text manifest 기반 outcome은 자동 승격 금지(컬럼 복원/사람 검수만).
- **input CSV 없이 collector 실행 금지.** `collect:university-admission-artifacts` / `collect:university-admission-attachments`는 `--help`가 없고 기본값으로 실제 수집을 시작할 수 있다 — 반드시 narrow input CSV를 지정한다.
