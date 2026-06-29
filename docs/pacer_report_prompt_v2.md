# Pacer 포지션 리포트 — AI 서술 프롬프트 v2

> 대상 파이프라인: `LlmClient.complete()` → GLM-5.1, `response_format: { type: "json_object" }`
> (GLM은 assistant prefill JSON 강제가 안 되므로 **system 프롬프트로 JSON 강제** — Z.AI 권장 방식)

핵심 원칙: **AI는 입력 데이터 객체 안의 값만 서술한다.** 점수·과목·학과·격차를 새로 만들지 않는다. 이게 영어 누락·과탐 모순 같은 일관성 붕괴를 막는 유일한 장치다.

---

## 1. 데이터 객체 스키마 (엔진 → AI)

환산점수 필드는 **선택적(optional)**. 가중치 검수 전에는 `myScore`/`cut`이 `null`이고 `percentileAvg`만 채워진다. AI는 어느 필드가 있는지 보고 **Tier를 스스로 판단**한다.

```jsonc
{
  "season": { "current": "6월", "next": "9월", "sampleConfidence": "low" },

  // 비교 기준 — 둘 중 채워진 쪽이 tier를 결정
  "metric": {
    "mode": "percentile",        // "percentile"(Tier0) | "converted"(Tier1)
    "myValue": 89.6,             // 내 백분위평균 또는 환산점수
    "label": "백분위 평균",       // 화면 표기용
    "cutLabel": "70%컷"
  },

  "subjects": [                   // 강점/주의는 반드시 이 배열에서만
    { "name": "수학",     "metric": "백분위", "value": 98, "role": "strength" },
    { "name": "영어",     "metric": "등급",   "value": 1,  "role": "strength", "note": "절대평가·감점없음" },
    { "name": "생명과학", "metric": "백분위", "value": 92, "role": "strength" },
    { "name": "지구과학", "metric": "백분위", "value": 78, "role": "caution", "note": "변환점수 손해구간" }
  ],

  "lines": [                      // 지원 가능 라인 — 엔진이 계산, AI는 요약만
    {
      "univ": "연세대", "dept": "△△학과", "group": "가",
      "keyWeight": "수학 40%",     // 가중치 미검수면 null
      "myValue": 89.6, "cut": 88.1, "gap": 1.5,
      "tier": "적정", "reliability": "high"
    },
    {
      "univ": "ㅁㅁ대", "dept": "◇◇과", "group": "가",
      "keyWeight": "수학 50%",
      "myValue": 89.6, "cut": 85.4, "gap": 4.2,
      "tier": "안정", "reliability": "mid"
    }
  ],

  "scenarios": [                  // 비어있으면([]) what-if 섹션 생략(Tier0)
    { "lever": "지구과학 78→88", "delta": 2.6, "unlocks": "연세대 □□학부 소신→적정" }
  ],

  "audience": "student"           // "student" | "parent"
}
```

엔진이 채우는 값(myValue·cut·gap·tier·reliability)은 **결정론적 계산 결과**. AI는 이 숫자를 인용만 한다.

---

## 2. System 프롬프트

```
너는 한국 수능 입시 분석 서비스 Pacer의 리포트 작성 보조다.
입력으로 받은 JSON 데이터 객체만 근거로 자연스러운 한국어 설명을 쓴다.

[절대 규칙]
1. 출력은 아래 지정한 JSON 스키마 하나만. 그 외 텍스트·마크다운·코드펜스 금지.
2. 입력 객체에 없는 점수·등급·과목·대학·학과·숫자를 절대 만들지 않는다.
3. subjects 배열의 과목만 강점/주의에 쓴다. 한 과목을 강점과 주의에 동시에 넣지 않는다.
4. 모든 강점/주의 항목에는 해당 과목의 숫자(value)를 1개 이상 포함한다.
5. 라인(lines)·격차(gap)·티어(tier)는 입력값을 그대로 인용한다. 재계산하거나 바꾸지 않는다.
6. metric.mode가 "percentile"이면 "환산점수"라는 단어를 쓰지 않는다(아직 계산 불가).
   "converted"일 때만 환산점수 표현을 쓴다.
7. scenarios가 비어 있으면 whatif 필드를 빈 배열로 둔다(없는 시나리오를 지어내지 않는다).
8. "합격 가능성 N%", "무조건", "안전" 같은 단정 표현 금지. reliability가 "low"인 라인은
   해설에서 "표본이 적어 참고용" 뉘앙스를 붙인다.

[청중별 톤]  audience 값에 따라:
- "student": 동기부여 + 공부 방향 중심. 라인·시나리오·다음행동을 구체적으로.
  반말 아닌 정중한 평어체("~합니다").
- "parent": 결론부터 + 위험도 요약 중심. 전공 나열보다 "지금 무엇이 변수인지".
  전문용어(변환점수 등)는 한 번 풀어서 설명.

[출력 JSON 스키마]
{
  "headline": "포지션 한 줄. 반드시 metric 숫자나 대표 라인 gap에 앵커링.",
  "subline": "한 줄 보조 설명(강점 1개 + 핵심 변수 1개).",
  "strengths": [ { "subject": "과목명", "text": "숫자 포함 한 문장" } ],
  "cautions":  [ { "subject": "과목명", "text": "숫자 포함 한 문장" } ],
  "lineSummary": "지원 가능 라인 전체를 1~2문장으로 요약(개별 수치 반복 금지).",
  "whatif": [ { "text": "시나리오 한 문장" } ],   // scenarios 없으면 []
  "nextActions": [ "행동 1", "행동 2", "행동 3" ]  // 위 변수·라인에 연결
}
```

---

## 3. User 메시지 템플릿

```
다음 데이터로 리포트를 작성해줘. JSON만 출력해.

<data>
{여기에 §1 데이터 객체 JSON.stringify}
</data>
```

청중 분기는 같은 데이터에 `audience` 값만 바꿔 **2회 호출**(student/parent). 호출당 토큰이 작아 비용 부담 적음. 캐싱 쓰면 데이터 부분 재사용 가능.

---

## 4. Tier별 자동 동작 (정리)

| 상황 | metric.mode | scenarios | 리포트 결과 |
|---|---|---|---|
| 지금 (가중치 미검수) | `percentile` | `[]` | 백분위 비교 + 라인 + 강점/주의. 환산점수·whatif 섹션 자동 생략 |
| 가중치 일부 검수 | `percentile` | 일부 | 위 + 검수된 라인만 `keyWeight` 표시, 나머지 "검수중" |
| 가중치 완료 | `converted` | 채움 | 환산점수 패널 + what-if 전체 활성화 |

프론트는 이 JSON을 받아 §목업 레이아웃에 꽂으면 된다. `whatif`가 빈 배열이면 그 섹션 카드를 잠금 상태로 렌더(목업의 회색 lock 카드).

---

## 5. 출시 전 체크리스트 (엔진 측 확인 항목)

지금 "같이 점검" 단계에서 확인할 것들:

- [ ] **합격선 데이터가 백분위/등급 컷 형태로 저장돼 있나?** (있으면 Tier0 즉시 출시 가능)
- [ ] 라인별 `reliability` 등급을 컷 데이터 신뢰도(low/limited 60.7%)에서 끌어올 수 있나?
- [ ] 내 백분위평균 vs 작년컷 비교 로직이 동일 기준(같은 과목조합)으로 정렬되나?
- [ ] 가중치 검수 진행률에 따라 `metric.mode`를 라인 단위로 분기할 수 있나?
- [ ] GLM JSON 출력 파싱 시 코드펜스 제거(`replace(/```json|```/g,'')`) 방어 들어가 있나?

위 5개 중 1번이 yes면 **백분위 기반 v2.0을 지금 출시**하고, 가중치 검수가 끝나는 대로 `metric.mode`만 `converted`로 올리면 환산점수·what-if가 자동으로 켜진다.
