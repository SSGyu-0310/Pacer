# Reference Data Remaining Work Protocol

이 문서는 다른 에이전트에게 남은 reference-data 작업을 위임하기 위한 실행 프로토콜이다. 기준 snapshot은 `packages/reference-data/data/public/foundation/foundation_reference.sqlite`의 현재 상태이며, 모든 산출 row는 검수 전 `needs_human_verification` 후보로 취급한다.

## 현재 남은 건수

운영 cutoff 기준 최신 snapshot: 2026-06-17 P2/P3 gap collection safe outcome, rule-scope override, 로컬 공식 HTML 직접 연도 evidence 11건, 운영 핵심 coverage 기반 non-operating gap 제외 정책 반영 후. 현재 남은 gap action은 전부 공개대기다.

| 항목 | 현재값 |
| --- | ---: |
| 전체 대학-연도 cell | 1,505 |
| `source_rich_review_ready` | 1,256 |
| `review_ready_partial` | 237 |
| `partial_evidence` | 11 |
| `source_gap` | 1 |
| 2021~2026 과거 입결 review-ready | 자동수집 큐 0, manual/source-scope 판정만 잔존 |
| 2027 전형규칙 후보 | 13,503행, 215개 대학 |
| AdmissionUnit 후보 | 68,072 |
| HistoricalOutcome 후보 | 69,306 |
| score-bearing HistoricalOutcome 후보 | 55,027 |
| quota/competition HistoricalOutcome 후보 | 67,396 |
| AdmissionRule 후보 | 62,383 |
| RecruitmentQuotaDraft 후보 | 1,914 |
| AdmissionOfficeEvidence 후보 | 106,695 |
| ReleaseMonitorTarget | 190 |
| OperationalReviewBatch | 6,636 |
| PromotionQueue p0 | 156,143 |
| P0 foundation parsed seed export | University 215 / AdmissionUnit 68,072 / HistoricalOutcome 68,338 / AdmissionRule 4,868 |
| SQLite import | 42 imported foundation tables / 965,477 imported rows |
| SQLite total | 44 foundation tables incl. metadata / 965,522 foundation rows; 46 total SQLite tables incl. stats / 965,692 total rows / integrity ok |

Operations dashboard:

| tier | stage | rows | 해석 |
| --- | --- | ---: | --- |
| p1 | `wait_for_public_release` | 560 | 2027 입결 등 공개 전에는 완료 불가 |

현재 자동/반자동 큐:

| queue | rows | 해석 |
| --- | ---: | --- |
| `foundation_gap_source_candidates` | 0 | 기존 source-review 후보 없음 |
| `foundation_gap_collection_targets` | 0 | detail/attachment crawl 후보 없음 |
| `foundation_gap_adiga_parser_review_queue` | 0 | ADIGA parser/visual review 후보 없음 |
| `foundation_gap_crawler_worklist` | 0 | crawler worklist 없음 |
| `foundation_gap_visual_review_queue` | 0 | visual review 후보 없음 |
| `foundation_gap_image_source_candidates` | 0 | image source 후보 없음 |
| `foundation_release_monitor_targets` | 190 | 2027 공개대기 대학-연도 모니터링 타깃 |
| `foundation_release_monitor_checklist` | 190 | 공개 확인/claim/status 기록용 체크리스트 |
| `foundation_operational_review_batches` | 6,636 | p0 승격 검수용 작업 배치 |
| `foundation_operational_review_packet_batches` | 48 | 우선 검수 batch packet |
| `foundation_operational_review_packet_rows` | 6,037 | packet별 상세 promotion row |
| `foundation_operational_review_decision_template` | 6,037 | packet row별 검수 decision template |
| `foundation_operational_source_review_bundle` | 5,508 | ready row별 원천 대조용 스니펫 bundle |
| `foundation_operational_review_decision_log` | 5,508 | 검수자가 직접 편집하는 persistent decision log |
| `foundation_reviewed_seed_overlay` | 4,276 | 승인 완료분만 seed 영향 범위로 변환한 overlay |
| `foundation_residual_review_worklist` | 1,232 | 남은 pending row를 원인/처리 프로토콜별로 분해한 위임 큐 |

따라서 신규 수집 관점의 남은 작업은 전부 `wait_for_public_release`다. 560개 gap operation은 190개 대학-연도 release-monitor target으로 압축되어 있다. 다음 에이전트는 자동수집 명령을 반복하지 말고, 2027 최종등록자/입시결과/경쟁률이 실제 공개된 뒤에만 release monitor 목록을 기준으로 수집한다.

수집 대기와 별개로 검수/승격 관점에는 `foundation_residual_review_worklist` 1,232행이 남아 있다. 이 worklist는 자동 승인을 금지한 사유와 다음 처리 프로토콜을 row 단위로 기록한다.

## 운영 seed export

현재 foundation 후보를 기존 P0 seed CSV 형식으로 변환한 parsed seed export가 있다.

```bash
pnpm --filter @pacer/reference-data build:foundation-p0-seed
pnpm --filter @pacer/reference-data audit:foundation-p0-seed
pnpm --filter @pacer/reference-data audit:foundation-data-completeness
pnpm --filter @pacer/reference-data audit:foundation-operational-readiness
pnpm --filter @pacer/reference-data seed:p0 -- packages/reference-data/data/p0-foundation --dry-run
```

산출물:

- `packages/reference-data/data/p0-foundation/universities.csv`: 215행
- `packages/reference-data/data/p0-foundation/admission_units.csv`: 68,072행
- `packages/reference-data/data/p0-foundation/historical_outcomes.csv`: 68,338행, 2021~2026만 포함
- `packages/reference-data/data/p0-foundation/admission_rules.csv`: 4,868행, 2027 parsed CSAT rule draft
- `packages/reference-data/data/p0-foundation/foundation_p0_seed_audit_summary.json`: seed invariant audit
- `packages/reference-data/data/public/foundation/foundation_data_completeness_summary.json`: 2021~2026 공개 데이터 completeness audit
- `packages/reference-data/data/public/foundation/foundation_data_completeness_exceptions.csv`: 공개 미게시/비적용 등 scope override 예외 56행
- `packages/reference-data/data/public/foundation/foundation_operational_readiness_summary.json`: collectable-now readiness audit
- `packages/reference-data/data/public/foundation/foundation_release_monitor_checklist.csv`: 2027 release monitor 작업 체크리스트 190행
- `packages/reference-data/data/public/university-admission-sites/university_admission_link_candidates_2027_release_monitor_ready.csv`: 2027 공개 URL 기반 narrow link collector input
- `packages/reference-data/data/public/university-admission-sites/university_admission_attachment_candidates_2027_release_monitor_ready.csv`: 2027 공개 첨부 URL 기반 narrow attachment collector input

주의: 이 export는 `parsed` reference seed 후보이며 human-verified/live seed가 아니다. 2027 입결/HistoricalOutcome은 공개대기이므로 export에서 제외한다. 2027 `AdmissionRule`은 이미 확보된 대학-연도 CSAT rule draft를 unit-level seed shape로 확장한 것이며, `verifiedStatus=parsed`와 `formulaJson.needsHumanVerification=true`를 유지한다. Rule은 `foundation_operational_review_batches.review_lane='rule_schedule_2027'`에서 원문 대조 후 live/verified 승격한다.

`audit:foundation-p0-seed` 통과 조건:

- `AdmissionUnit.universityId` FK missing 0.
- `AdmissionRule.unitId` FK missing 0.
- `HistoricalOutcome.unitId` FK missing 0.
- `HistoricalOutcome` 2027+ row 0.
- `AdmissionRule` non-2027 row 0.
- `AdmissionRule.verifiedStatus != parsed` row 0.
- `AdmissionRule.formulaJson.needsHumanVerification != true` row 0.
- rule/outcome empty `sourceUrl` row 0.

`audit:foundation-data-completeness` 통과 조건:

- SQLite `pragma integrity_check` = `ok`.
- requested public years `2021,2022,2023,2024,2025,2026` 모두 존재.
- 2021~2026 requested-year gap action row 0.
- 즉시 수집/반자동 큐 6종 row 0.
- `source_rich_review_ready`가 아닌 2021~2026 coverage row는 모두 `scope_override_statuses`와 `scope_excluded_missing_flags`를 가진다.
- 이미지/OCR evidence row가 존재한다.

현재 `audit:foundation-data-completeness` 결과:

- `status=ok`
- `requestedPublicYears=2021~2026`
- `requestedYearGapActions=0`
- `nonSourceRichExceptionRows=56`
- `nonSourceRichRowsWithoutScopeOverride=0`
- `admissionOfficeEvidenceRows=106,695`
- `imageOrOcrEvidenceRows=15,432`

`audit:foundation-operational-readiness` 통과 조건:

- SQLite `pragma integrity_check` = `ok`.
- 즉시 수집/반자동 큐 6종 row 0.
- operations dashboard는 `wait_for_public_release`만 존재.
- 남은 missing flag는 `missing_historical_outcomes`, `missing_outcome_scores`, `missing_quota_competition`만 존재.
- release monitor target은 2027만 존재.
- release monitor checklist row 수가 release monitor target row 수와 일치.
- p0-foundation seed audit status `ok`.
- 2027 seed AdmissionUnit 수와 2027 parsed AdmissionRule 수가 일치.

현재 readiness interpretation:

- `collectableNowStatus=closed`
- `remainingCollectionStatus=2027_outcome_public_release_wait`
- `releaseMonitorUnit=foundation_release_monitor_targets`

## 위임 단위 선택: 검수/승격

수집 대기와 별개로, 현재 운영에 바로 도움이 되는 일은 p0 후보 검수/승격이다. 에이전트는 반드시 `foundation_operational_review_batches`에서 작은 단위를 claim한다.

바로 착수할 수 있는 우선 검수 packet도 생성되어 있다.

```bash
pnpm --filter @pacer/reference-data build:foundation-operational-review-packets
pnpm --filter @pacer/reference-data build:foundation-operational-review-decisions
pnpm --filter @pacer/reference-data build:foundation-operational-source-review-bundles
pnpm --filter @pacer/reference-data build:foundation-operational-review-decision-log
pnpm --filter @pacer/reference-data apply:foundation-kice-source-row-review
pnpm --filter @pacer/reference-data apply:foundation-adiga-csat-outcome-review
pnpm --filter @pacer/reference-data apply:foundation-adiga-csat-outcome-carry-forward-review
pnpm --filter @pacer/reference-data apply:foundation-adiga-admission-unit-review
pnpm --filter @pacer/reference-data apply:foundation-office-workbook-outcome-review
pnpm --filter @pacer/reference-data apply:foundation-office-workbook-admission-unit-review
pnpm --filter @pacer/reference-data apply:foundation-decision-sourcepath-admission-unit-review
pnpm --filter @pacer/reference-data apply:foundation-approved-outcome-admission-unit-review
pnpm --filter @pacer/reference-data audit:foundation-review-decision-log
pnpm --filter @pacer/reference-data build:foundation-reviewed-seed-overlay
pnpm --filter @pacer/reference-data build:foundation-residual-review-worklist
```

산출물:

- `packages/reference-data/data/public/foundation/foundation_operational_review_packet_batches.csv`: 48개 우선 batch
- `packages/reference-data/data/public/foundation/foundation_operational_review_packet_rows.csv`: 6,037개 상세 row
- `packages/reference-data/data/public/foundation/foundation_operational_review_packet_summary.json`: packet summary
- `packages/reference-data/data/public/foundation/foundation_operational_review_decision_template.csv`: row별 decision template
- `packages/reference-data/data/public/foundation/foundation_operational_review_decision_summary.json`: decision summary
- `packages/reference-data/data/public/foundation/foundation_operational_source_review_bundle.csv`: `ready_for_source_review` row 원천 스니펫 bundle
- `packages/reference-data/data/public/foundation/foundation_operational_source_review_bundle_summary.json`: source review bundle summary
- `packages/reference-data/data/public/foundation/foundation_operational_review_decision_log.csv`: 검수자가 직접 편집하는 persistent decision log
- `packages/reference-data/data/public/foundation/foundation_adiga_admission_unit_review_summary.json`: ADIGA AdmissionUnit strict source-row audit summary
- `packages/reference-data/data/public/foundation/foundation_adiga_csat_outcome_carry_forward_review_summary.json`: ADIGA HistoricalOutcome carry-forward group audit summary
- `packages/reference-data/data/public/foundation/foundation_office_workbook_outcome_review_summary.json`: admission-office workbook HistoricalOutcome strict row audit summary
- `packages/reference-data/data/public/foundation/foundation_office_workbook_admission_unit_review_summary.json`: admission-office workbook AdmissionUnit strict row audit summary
- `packages/reference-data/data/public/foundation/foundation_decision_sourcepath_admission_unit_review_summary.json`: decision sourcePath AdmissionUnit strict row audit summary
- `packages/reference-data/data/public/foundation/foundation_approved_outcome_admission_unit_review_summary.json`: approved HistoricalOutcome 기반 AdmissionUnit linked audit summary
- `packages/reference-data/data/public/foundation/foundation_review_decision_log_audit_summary.json`: decision log audit summary
- `packages/reference-data/data/public/foundation/foundation_reviewed_seed_overlay.csv`: 승인 완료분만 seed 영향 범위로 변환한 overlay
- `packages/reference-data/data/public/foundation/foundation_reviewed_seed_overlay_summary.json`: reviewed overlay summary
- `packages/reference-data/data/public/foundation/foundation_residual_review_worklist.csv`: pending row별 남은 처리 프로토콜
- `packages/reference-data/data/public/foundation/foundation_residual_review_worklist_summary.json`: residual worklist summary

현재 packet 구성:

- `historical_outcome_core`: 12 batch / 2,400 detail rows
- `rule_schedule_2027`: 12 batch / 25 detail rows
- `kice_score_reference`: 12 batch / 1,212 detail rows
- `admission_unit_core`: 12 batch / 2,400 detail rows

이 packet은 작업용 검수 목록이지 verified seed가 아니다. `rawPaths`, `sourcePaths`, `sourceUrls`를 열어 원문과 숫자/행/연도를 대조한 뒤에만 verified 승격한다.

현재 decision template 구성:

- `ready_for_source_review`: 5,508행
- `needs_manual_source_year_review`: 529행
- `hold_missing_evidence`: 0행
- `admission_unit_core`: 2,388행 ready, 12행 source-year manual review
- `historical_outcome_core`: 1,894행 ready, 506행 source-year manual review
- `kice_score_reference`: 1,212행 ready
- `rule_schedule_2027`: 25행 중 14행 ready, 11행 source-year manual review

`needs_manual_source_year_review`는 자동 승격 금지다. 특히 2027 rule row에 2021/2022/2025/2026 local artifact가 섞인 경우는 실제 2027 공식 URL/ADIGA evidence와 같은 문서인지 원문을 열어 확인하기 전까지 `parsed` 상태로 둔다. `admission_unit_core`는 `sourceRecordId -> foundation_admission_units.sourceCandidateSha256Values` 및 ADIGA `year/unvCd` raw path를 이용해 source evidence를 보강했으므로, 대부분 원문 대조가 가능하다.

현재 source review bundle 구성:

- bundle row: 5,508행
- snippet 포함: 5,508행
- source record summary 포함: 5,508행
- candidate value summary 포함: 5,508행
- source coordinates 포함: 5,508행
- approval scope key 포함: 5,508행
- `admission_unit_core`: 2,388행 / snippet 2,388행
- `historical_outcome_core`: 1,894행 / snippet 1,894행
- `kice_score_reference`: 1,212행 / snippet 1,212행
- `rule_schedule_2027`: 14행 / snippet 14행
- evidence kind: `source_text` 2,696행, `raw_text` 1,799행, `raw_binary` 693행, `pdf_text_manifest` 320행

`foundation_operational_source_review_bundle.evidenceSnippet`은 원문 대조 진입용 문맥 창일 뿐 verified 근거가 아니다. 검수자는 반드시 `candidateValueSummary`, `sourceCoordinates`, `primaryEvidencePath` 또는 `sourceUrls`를 함께 열어 원문 행/표와 대조한 뒤 decision을 기록한다. `approvalScopeKey`는 원문 대조 후 적용 가능한 승인 단위이지, 그 자체가 승인 상태는 아니다.

현재 decision log / reviewed overlay 구성:

- `foundation_operational_review_decision_log`: 5,508행
- `reviewOutcome=pending`: 1,236행
- `reviewOutcome=approved`: 4,272행
- `kice_score_reference`: 1,212행 approved
- `historical_outcome_core`: 1,507행 approved, 387행 pending
- `admission_unit_core`: 1,553행 approved, 835행 pending
- `rule_schedule_2027`: 14행 pending
- `foundation_reviewed_seed_overlay`: 4,272행
- overlay status: `approved_source_review_only` 1,212행 (`foundation_kice_standard_score_distributions`)
- overlay status: `ready_to_apply` 3,060행 (`foundation_historical_outcomes` 1,507행 + `foundation_admission_units` 1,553행)

남은 pending 1,236행의 성격:

- `admission_unit_core` 835행: ADIGA raw row 473행, 대학 입학처 source text 296행, ADIGA+입학처 mixed 66행. 자동 승인 스크립트 기준으로는 ADIGA outcome sha 없음/정원 불일치/원 row 내 모집군·정원 불명시, 또는 `quotaCandidates` 공란이 남은 상태다.
- `historical_outcome_core` 387행: 대학 입학처 PDF text manifest 320행, 대학 입학처 workbook strict mismatch 67행. PDF snippet은 page-level이라 여러 모집단위가 섞여 row 경계가 약하므로 자동 승격 금지다.
- `rule_schedule_2027` 14행: 2027 요강/rule source text 대조가 필요한 parsed rule draft다. 2027 입결 공개대기와는 별개지만 rule formula 해석이 필요하므로 자동 승인하지 않는다.

`foundation_residual_review_worklist` 기준 남은 처리 트랙:

| residual category | rows | priority | delegate track | 처리 프로토콜 |
| --- | ---: | --- | --- | --- |
| `adiga_admission_unit_identity_only_missing_quota` | 473 | P1 | `adiga_parser_or_manual_quota` | ADIGA 원표에서 모집단위/모집군/정원 컬럼을 재구성한 뒤 unit exact record 검수 |
| `office_pdf_outcome_column_reconstruction_required` | 320 | P1 | `pdf_table_column_reconstruction` | PDF/OCR 표 컬럼을 복원해 quota/competition/충원/점수 컬럼별 대조 |
| `admission_unit_source_text_missing_source_paths` | 249 | P2 | `html_or_text_extraction` | row-level CSV sourcePath가 생기도록 HTML/PDF/workbook 추출 보강 후 재검수 |
| `admission_unit_source_text_missing_quota` | 108 | P1 | `office_parser_or_manual_quota` | 입학처 원문에서 정원 컬럼을 찾아 quota supplement 또는 parser 보강 |
| `office_workbook_outcome_strict_mismatch` | 67 | P1 | `workbook_table_parser_or_manual` | workbook merged cell/hidden sheet/열 위치를 확인해 targeted parser 또는 수동 검수 |
| `admission_rule_2027_formula_human_review_required` | 14 | P2 | `rule_formula_review` | 2027 요강 rule/schedule 공식 원문 대조. 2027 입결 공개대기와 혼동 금지 |
| `admission_unit_source_text_strict_row_mismatch` | 5 | P2 | `office_table_parser` | row-level sourcePath는 있으나 strict unit/year/group/quota 매칭 실패. table split/merged cell 확인 |

모든 residual row의 `autoApprovalAllowed`는 `no`다. 다른 에이전트가 추가 승인하려면 먼저 해당 category의 `recommendedProtocol`과 `verificationRequirement`를 만족하는 새 parser/manual evidence를 만들어야 한다.

`apply:foundation-kice-source-row-review`는 KICE 표준점수 도수분포 row만 엄격 자동 검수한다. 승인 조건은 source CSV의 `sourceRowNumber`/`sourceColumnNumber`가 `standardScore`, `maleCount`, `femaleCount`, `totalCount`, `cumulativeTotalCount` 5개 값과 정확히 일치하고, 같은 열 위쪽에서 과목명과 `표준점수` 헤더가 확인되는 경우다. 이 절차로 승인된 KICE row는 현 P0 seed shape에 직접 매핑되지 않으므로 `foundation_reviewed_seed_overlay.overlayStatus=approved_source_review_only`로 기록한다.

`apply:foundation-adiga-csat-outcome-review`는 ADIGA 정시 입결 row 중 원 row에 모집군이 직접 표시된 strict subset만 자동 검수한다. 승인 조건은 foundation `HistoricalOutcome` 값이 ADIGA `candidateSha256` row와 일치하고, `adiga_extracted_tables_<year>.jsonl`의 해당 grid row에 모집단위명, 모집군, 모집인원, 경쟁률, 충원, 환산점수, 총점, 백분위 값이 모두 존재하는 경우다.

`apply:foundation-adiga-csat-outcome-carry-forward-review`는 ADIGA 표에서 모집군 셀이 병합되어 대상 row에는 `/`만 있고 위쪽 가까운 row에 `가군/나군/다군`이 명시된 carry-forward HistoricalOutcome만 자동 검수한다. 승인 조건은 foundation 값과 ADIGA `candidateSha256` row가 일치하고, 대상 grid row에 모집단위명 및 모든 핵심 숫자가 있으며, 같은 table에서 위로 스캔했을 때 가장 가까운 명시 모집군이 기대 모집군과 일치하는 경우다. 현재 실행 결과는 106개 pending ADIGA HistoricalOutcome 중 106행 approved다.

`apply:foundation-adiga-admission-unit-review`는 ADIGA 정시 입결 후보와 같은 원문 행에 묶이는 AdmissionUnit strict subset만 자동 검수한다. 승인 조건은 `foundation_admission_units.sourceCandidateSha256Values` 중 하나가 ADIGA `adiga_csat_outcome_row_candidates.candidateSha256`와 일치하고, unit의 `year/unvCd/admissionUnitName 또는 admissionUnitCanonicalName/recruitmentGroup/quotaCandidates`가 ADIGA 후보와 일치하며, `adiga_extracted_tables_<year>.jsonl`의 해당 grid row에 모집단위명, 명시적 모집군, 정원이 직접 보이는 경우다. 현재 실행 결과는 2,388개 pending AdmissionUnit 중 639행 approved, 1,519행 `no_adiga_outcome_sha`, 230행 `no_strict_candidate`다.

`apply:foundation-office-workbook-outcome-review`는 대학 입학처 엑셀 원문에서 추출된 `workbook_row` 기반 HistoricalOutcome strict subset만 자동 검수한다. 승인 조건은 `foundation_historical_outcomes.sourceCandidateSha256`가 `foundation_admission_office_evidence_links.evidenceCandidateSha256`와 일치하고, evidence의 `sourcePaths` 중 해당 연도 workbook CSV를 열었을 때 같은 row에 모집단위명, 명시적 모집군(해당 시), 정원, 경쟁률, 충원/점수 값이 모두 존재하는 경우다. 현재 실행 결과는 1,013개 pending office HistoricalOutcome 중 626행 approved, 67행 strict row mismatch, 320행 `non_workbook_evidence`(PDF snippet 보류)다.

`apply:foundation-office-workbook-admission-unit-review`는 대학 입학처 엑셀 원문에서 추출된 `workbook_row` 기반 AdmissionUnit strict subset만 자동 검수한다. 승인 조건은 `foundation_admission_units.sourceCandidateSha256Values` 중 하나가 office workbook evidence와 연결되고, 해당 연도 workbook CSV row에 모집단위명, 명시적 모집군(해당 시), `quotaCandidates` 중 하나가 직접 보이는 경우다. 현재 실행 결과는 1,276개 pending office/mixed AdmissionUnit 중 857행 approved, 353행 `no_office_workbook_sha`, 66행 strict row mismatch다.

`apply:foundation-decision-sourcepath-admission-unit-review`는 decision bundle의 `primaryEvidencePath/sourcePaths` CSV를 직접 열어 AdmissionUnit strict subset을 자동 검수한다. 승인 조건은 pending AdmissionUnit이 `source_text` evidence를 가지고 있고 `quotaCandidates`가 비어 있지 않으며, 같은 extracted CSV row에 모집단위명, 입학연도, 명시적 모집군(해당 시), `quotaCandidates` 중 하나가 모두 보이는 경우다. 현재 실행 결과는 419개 pending source-text AdmissionUnit 중 57행 approved, 108행 `missing_quota_candidates`, 249행 `missing_source_paths`, 5행 strict row mismatch다.

PDF text manifest HistoricalOutcome 320행은 자동승격 금지다. 한 줄 안에 숫자가 모두 있는 것처럼 보이는 dry-run subset이 일부 있으나, 단국대 PDF에서 `additionalPass`가 후보순위가 아니라 등록인원/등록률 주변 숫자와 충돌하는 패턴이 확인됐다. PDF outcome은 table column reconstruction 또는 사람 검수로만 승격한다.

검수자가 row를 승인하려면 `foundation_operational_review_decision_log.csv`에서 해당 row의 editable field만 수정한다.

- `decisionStatus=reviewed`
- `reviewOutcome=approved`
- `reviewedVerifiedStatus=verified` 또는 `live`
- `reviewer=<검수자 식별자>`
- `reviewedAt=<ISO timestamp>`
- `sourceMatchStatus=matched`
- `valueMatchStatus=matched`
- `reviewNotes=<원문 대조 메모>`

반려는 `reviewOutcome=rejected`, `rejectionReason` 필수다. 추가 확인은 `reviewOutcome=needs_followup`, `followupAction` 필수다. 로그 수정 후에는 반드시 `audit:foundation-review-decision-log`를 먼저 통과시키고, 그 다음 `build:foundation-reviewed-seed-overlay`를 실행한다. `foundation_reviewed_seed_overlay`는 base p0 seed CSV를 직접 mutate하지 않고, 승인된 source review가 어떤 seed row에 영향을 주는지만 기록한다.

권장 단위:

1. `historical_outcome_core` 1개 대학-연도 배치.
2. `rule_schedule_2027` 1개 대학-연도 배치.
3. `kice_score_reference` 1개 과목/시험 배치.
4. `admission_unit_core` 1개 대학-연도 배치.

선택 SQL:

```bash
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite \
  "select review_batch_id,review_lane,target_entity,admission_year,academic_year,exam_type,subject_name,unv_cd,university_name,batch_row_count,review_priority_score_max,operator_next_step
   from foundation_operational_review_batches
   where review_status='needs_human_verification'
   order by case review_lane
     when 'historical_outcome_core' then 0
     when 'rule_schedule_2027' then 1
     when 'kice_score_reference' then 2
     when 'admission_unit_core' then 3
     else 9 end,
     cast(review_priority_score_max as integer) desc,
     university_name,
     admission_year;"
```

선택한 배치의 상세 row 조회:

```bash
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite \
  "select q.*
   from foundation_operational_review_batches b
   join foundation_promotion_queue q
     on instr('|' || b.sample_promotion_queue_ids || '|', '|' || q.promotion_queue_id || '|') > 0
   where b.review_batch_id='REVIEW_BATCH_ID'
   order by cast(q.review_priority_score as integer) desc;"
```

`samplePromotionQueueIds`는 빠른 진입점이다. 전체 배치 row가 20개를 넘으면 `foundation_promotion_queue`에서 같은 `reviewLane` 기준 키(`target_entity`, `admission_year`, `unv_cd`, `academic_year`, `exam_type`, `subject_name`)로 추가 조회한다.

## 위임 단위 선택: 2027 공개 모니터링

2027 입결/최종등록자/경쟁률 공개 여부만 확인할 때 사용한다. 공개 전에는 수집하지 않는다.

```bash
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite \
  "select release_monitor_checklist_id,claim_status,release_evidence_status,unv_cd,university_name,admission_year,missing_flags,gap_operation_count,primary_search_queries,operator_next_step
   from foundation_release_monitor_checklist
   where release_evidence_status in ('not_checked','not_public_yet')
   order by university_name, admission_year;"
```

처리 규칙:

- 공식 입학처/ADIGA에서 2027 입시결과/최종등록자/경쟁률 공개가 확인되기 전에는 `releaseEvidenceStatus=not_public_yet`만 기록한다.
- 공개 확인 시 `officialResultUrl` 또는 `officialAttachmentUrl`을 채우고, 그 URL만 기반으로 좁은 collector input CSV를 만든다.
- broad collector를 checklist 전체에 바로 실행하지 않는다.

URL 입력 후 collector input 생성:

```bash
pnpm --filter @pacer/reference-data build:foundation-release-monitor-collector-inputs
```

산출물:

- `packages/reference-data/data/public/university-admission-sites/university_admission_link_candidates_2027_release_monitor_ready.csv`
- `packages/reference-data/data/public/university-admission-sites/university_admission_attachment_candidates_2027_release_monitor_ready.csv`
- `packages/reference-data/data/public/university-admission-sites/university_admission_release_monitor_collector_inputs_2027_release_monitor_ready_summary.json`

현재 checklist는 `releaseEvidenceStatus=not_checked` 190건이고 공식 URL이 없으므로 ready rows는 0이다. 공개 확인 후에는 해당 row를 `releaseEvidenceStatus=public` 또는 `ready_for_collection`으로 바꾸고 `officialResultUrl`/`officialAttachmentUrl`을 채운 뒤 위 명령을 다시 실행한다. 이 변환기는 ready status가 아닌 URL은 건너뛰므로, 공개 전 URL 메모가 실수로 수집되는 것을 막는다.

공개 URL을 채운 뒤 실제 수집은 반드시 위 narrow CSV만 대상으로 실행한다.

```bash
pnpm --filter @pacer/reference-data collect:university-admission-artifacts -- --year=2027 --link-candidates=packages/reference-data/data/public/university-admission-sites/university_admission_link_candidates_2027_release_monitor_ready.csv --roles=admission_result --output-suffix=release_monitor_ready --timeout-ms=15000 --delay-ms=50

pnpm --filter @pacer/reference-data collect:university-admission-attachments -- --year=2027 --attachment-candidates=packages/reference-data/data/public/university-admission-sites/university_admission_attachment_candidates_2027_release_monitor_ready.csv --roles=admission_result --output-suffix=release_monitor_ready --timeout-ms=15000 --delay-ms=50 --fallback-curl
```

## 공통 금지사항

- `pnpm ... collect:university-admission-artifacts` 또는 `collect:university-admission-attachments`를 입력 CSV 없이 실행하지 않는다. 이 collector들은 `--help`가 없고 기본값으로 실제 수집을 시작할 수 있다.
- 진학사, 유웨이, 고속성장 등 competitor 자료는 자동 수집하지 않는다. Pacer spec상 `CompetitorSignal`은 사용자가 수동 입력하는 데이터다.
- 원문을 보지 않고 `sourceConfidence`를 verified처럼 만들지 않는다. 모든 신규 row는 `needs_human_verification`이다.
- 같은 source가 여러 연도 gap에 붙어 있을 때, 본문 결과 연도와 collection year를 분리한다. 모집요강의 “최근 2개년 입시결과”는 해당 모집요강 연도 결과가 아닐 수 있다.
- PDF text가 저품질이면 Tesseract 숫자를 믿지 않는다. 표 이미지/OCR은 가능하면 GLM OCR 결과를 쓰고, 원본 표와 spot check한다.

## 프로토콜 A: manual source discovery 처리

입력: `foundation_gap_operations_dashboard.next_best_stage='manual_source_discovery'`

절차:

1. `foundation_gap_operations_dashboard`에서 한 대학-연도 또는 같은 `unv_cd` 묶음을 고른다. 현재 P0/P2는 없으므로 우선순위는 `p1` manual 386건, 그 다음 `p3` manual 29건이다.
2. 관련 evidence를 조회한다.

```bash
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite \
  "select source_provider,evidence_role,evidence_types,collection_years,detected_admission_years,source_candidate_url,attachment_url,raw_path,source_path,text_preview
   from foundation_admission_office_evidence_links
   where unv_cd='UNV_CD'
   order by cast(review_priority_score as integer) desc
   limit 80;"
```

3. 공식 입학처/ADIGA/대교협/대학알리미/인터넷 아카이브에서 missing flag를 닫을 수 있는 직접 원문을 새로 찾는다.
4. 원문 표가 실제 결과표나 전형규칙표이면 parser를 `packages/reference-data/scripts/build-foundation-db-candidates.py` 또는 해당 draft builder에 좁게 추가한다.
5. 원문이 navigation, 모집요강, 전년도 참고표, 타 연도 문서라면 자동 승격하지 말고 `admissions_scope_overrides.csv`에 근거와 확인일을 남긴다.
6. 재빌드 후 해당 gap operation이 사라졌는지 확인한다.

완료 기준:

- 처리한 gap이 `foundation_gap_operations_dashboard`에서 사라지거나 공개대기/scope override/blocker로 명확히 이동한다.
- 새 row가 생겼다면 `sourceUrl`, `rawPath`, `sourceConfidence`, `sectionId`, `rowIndex`, `reviewStatus`가 채워져 있다.

## 프로토콜 B: 새 원천 발견 후 parser repair

대상: manual source discovery에서 새 원문 URL 또는 로컬 raw artifact를 확보한 건.

절차:

1. `foundation_gap_public_discovery_queue`에서 같은 대학-연도 row를 찾아 missing flag와 기대 availability를 확인한다.
2. 새 URL은 먼저 별도 후보 CSV로 좁게 만들고, 이미 raw artifact가 있으면 manifest/raw path를 확인한다.
3. HTML이면 링크/표 parser를 보강한다. 파일이면 기존 manifest를 찾아 추출 산출물이 있는지 확인한다.
4. 추출 산출물이 없으면 새 output dir을 만든다.

```bash
OUT=packages/reference-data/data/public/university-admission-sites/extracted-<slug>-<yyyymmdd>
MANIFEST=packages/reference-data/data/public/university-admission-sites/<artifact-manifest>.jsonl

pnpm --filter @pacer/reference-data extract:university-admission:workbooks -- --year=<YYYY> --manifest=$MANIFEST --output-dir=$OUT
pnpm --filter @pacer/reference-data extract:university-admission:workbook-rows -- --year=<YYYY> --workbook-sheets=$OUT/university_admission_workbook_sheets_manifest_<YYYY>.jsonl --output-dir=$OUT
pnpm --filter @pacer/reference-data extract:university-admission:pdfs -- --year=<YYYY> --manifest=$MANIFEST --output-dir=$OUT
pnpm --filter @pacer/reference-data extract:university-admission:pdf-snippets -- --year=<YYYY> --pdf-source-manifest=$OUT/university_admission_pdf_sources_manifest_<YYYY>.jsonl --output-dir=$OUT
pnpm --filter @pacer/reference-data extract:university-admission:hwps -- --year=<YYYY> --manifest=$MANIFEST --output-dir=$OUT
pnpm --filter @pacer/reference-data extract:university-admission:hwp-snippets -- --year=<YYYY> --hwp-source-manifest=$OUT/university_admission_hwp_sources_manifest_<YYYY>.jsonl --output-dir=$OUT
pnpm --filter @pacer/reference-data extract:university-admission:office-docs -- --year=<YYYY> --manifest=$MANIFEST --output-dir=$OUT
pnpm --filter @pacer/reference-data extract:university-admission:office-doc-snippets -- --year=<YYYY> --office-document-source-manifest=$OUT/university_admission_office_document_sources_manifest_<YYYY>.jsonl --output-dir=$OUT
pnpm --filter @pacer/reference-data build:university-admission:evidence-index -- --year=<YYYY> --output-dir=$OUT --pdf-snippets=$OUT/university_admission_pdf_snippets_<YYYY>.jsonl --hwp-snippets=$OUT/university_admission_hwp_snippets_<YYYY>.jsonl --office-document-snippets=$OUT/university_admission_office_document_snippets_<YYYY>.jsonl --workbook-sheets=$OUT/university_admission_workbook_sheets_manifest_<YYYY>.jsonl --workbook-row-candidates=$OUT/university_admission_workbook_row_candidates_<YYYY>.jsonl
pnpm --filter @pacer/reference-data build:university-admission:promotion-queue -- --input-glob "$OUT/university_admission_evidence_index_*.jsonl" --output-dir=$OUT
```

5. promotion queue가 실제 gap을 닫을 수 있으면 `build-foundation-db-candidates.py` 기본 입력에 연결한다. 전용 parser가 필요하면 source label, sourceConfidence, result year guard를 함께 추가한다.

완료 기준:

- `foundation_historical_outcomes.csv`, `foundation_admission_units.csv`, 또는 rule draft CSV에 후보가 증가한다.
- 처리 대학-연도 gap count가 줄거나 blocker로 분리된다.
- parser가 너무 위험하면 자동 승격하지 말고 evidence만 보존한다.

## 프로토콜 C: detail/attachment crawl

대상: manual discovery 과정에서 직접 확인한 공식 링크 후보. 현재 `foundation_gap_collection_targets`와 crawler worklist는 0행이므로 자동 후보 없이 broad crawl을 시작하지 않는다.

절차:

1. 먼저 후보 CSV를 만든다. broad run을 피하려면 `--limit`, `--per-university-limit`, `--min-score`를 사용하고, 결과 CSV를 수동으로 한 번 열어 확인한다.

```bash
python3 packages/reference-data/scripts/build-foundation-gap-collection-link-candidates.py \
  --output-csv packages/reference-data/data/public/university-admission-sites/university_admission_gap_collection_link_candidates_<slug>.csv \
  --output-summary packages/reference-data/data/public/university-admission-sites/university_admission_gap_collection_link_candidates_<slug>_summary.json \
  --limit 80 \
  --per-university-limit 8 \
  --min-score 150
```

2. 연도별로 detail HTML을 fetch한다. 반드시 `--year`, `--link-candidates`, `--output-suffix`를 넣는다.

```bash
pnpm --filter @pacer/reference-data collect:university-admission-artifacts -- \
  --year=<YYYY> \
  --link-candidates=packages/reference-data/data/public/university-admission-sites/university_admission_gap_collection_link_candidates_<slug>.csv \
  --output-suffix=<slug> \
  --timeout-ms=20000 \
  --delay-ms=50
```

3. detail HTML에서 nested attachment 후보를 추출한다.

```bash
pnpm --filter @pacer/reference-data extract:university-admission:related-detail-attachments -- \
  --year=<YYYY> \
  --manifest=packages/reference-data/data/public/university-admission-sites/university_admission_link_artifact_manifest_<YYYY>_<slug>.jsonl \
  --output-suffix=<slug>_related
```

4. 첨부를 fetch한다.

```bash
pnpm --filter @pacer/reference-data collect:university-admission-attachments -- \
  --year=<YYYY> \
  --attachment-candidates=packages/reference-data/data/public/university-admission-sites/university_admission_related_detail_attachment_candidates_<YYYY>_<slug>_related.csv \
  --roles=direct_file,file_download_route \
  --output-suffix=<slug>_files \
  --timeout-ms=20000 \
  --fallback-curl \
  --delay-ms=50
```

5. 프로토콜 B의 문서 추출/승격 절차를 실행한다.

완료 기준:

- fetch summary에서 `fetched`와 file artifact 수가 증가한다.
- HTML 응답 파일을 문서로 오판하지 않는다. MIME/signature와 file kind를 확인한다.
- 새 산출물은 output suffix로 기존 산출물과 분리되어 재현 가능해야 한다.

## 프로토콜 D: 2027 공개대기

대상: P1 `wait_for_public_release` 560건, `foundation_release_monitor_targets` 190건.

처리하지 말아야 할 것:

- 2027 입결이 아직 공개되지 않았는데 2026/2025 결과표를 2027 결과로 승격하지 않는다.
- 모집요강 안의 “전년도 입시결과”를 current-year outcome으로 쓰지 않는다.

처리 방법:

1. `foundation_release_monitor_targets`에서 1개 target을 claim한다.
2. `primary_search_queries`와 `search_queries_json`으로 공식 입학처/ADIGA 공개 여부만 확인한다.
3. 2027 최종등록자/입시결과/경쟁률 공개가 확인되면 공식 URL을 기록하고 프로토콜 C로 수집한다.
4. 공개 전에는 blocker가 아니라 `wait_for_public_release`로 유지한다.
5. 공개 후 수집한 자료만 2027 outcome으로 승격한다. 2026/2025 결과표나 모집요강의 전년도 참고표는 2027 outcome 근거가 아니다.

## Blocker 기록

공식 source가 없거나 해당 대학/연도가 정시/수능위주 모집 대상이 아닌 경우에는 자동 parser를 만들지 말고 blocker 또는 scope override를 남긴다.

사용 파일:

- `packages/reference-data/data/sources/admissions_scope_overrides.csv`
- `packages/reference-data/data/sources/foundation_manual_admission_office_evidence_supplements.csv`
- `packages/reference-data/data/sources/foundation_manual_admission_unit_supplements.csv`

`admissions_scope_overrides.csv`는 다음 컬럼을 사용한다.

```csv
overrideId,unvCd,universityName,startAdmissionYear,endAdmissionYear,scopeStatus,excludedMissingFlags,sourceUrl,sourceLabel,note
```

예시 판정:

- `official_result_not_public`: 공식 입학처/대입정보포털에서 결과 미공개.
- `susi_only_no_regular_csat`: 해당 연도 정시/수능위주 입결 대상 아님.
- `outcome_score_not_published`: 모집/지원/경쟁률은 있으나 성적 점수 미공개.
- `quota_pair_not_published`: 경쟁률만 있고 모집인원·지원인원 pair 없음.

## Rebuild 순서

parser, supplement, override를 바꾼 뒤 반드시 아래 순서로 재생성한다.

```bash
pnpm --filter @pacer/reference-data build:foundation-db-candidates
pnpm --filter @pacer/reference-data build:foundation-csat-rule-drafts
pnpm --filter @pacer/reference-data build:foundation-admission-schedule-drafts
pnpm --filter @pacer/reference-data build:foundation-admission-unit-clusters
pnpm --filter @pacer/reference-data build:foundation-historical-outcome-series
pnpm --filter @pacer/reference-data build:foundation-recruitment-quota-drafts
pnpm --filter @pacer/reference-data build:foundation-screening-method-drafts
pnpm --filter @pacer/reference-data build:foundation-school-record-rule-drafts
pnpm --filter @pacer/reference-data build:foundation-eligibility-rule-drafts
pnpm --filter @pacer/reference-data build:foundation-general-rule-drafts
pnpm --filter @pacer/reference-data build:foundation-promotion-queue
pnpm --filter @pacer/reference-data build:foundation-operational-review-batches
pnpm --filter @pacer/reference-data build:foundation-coverage-audit
pnpm --filter @pacer/reference-data build:foundation-gap-action-queue
pnpm --filter @pacer/reference-data build:foundation-gap-source-candidates
pnpm --filter @pacer/reference-data build:foundation-gap-collection-targets
pnpm --filter @pacer/reference-data build:foundation-gap-image-source-candidates
pnpm --filter @pacer/reference-data build:foundation-gap-adiga-parser-review-queue
pnpm --filter @pacer/reference-data build:foundation-gap-crawler-worklist
pnpm --filter @pacer/reference-data build:foundation-gap-public-discovery-queue
python3 packages/reference-data/scripts/build-foundation-release-monitor-targets.py
pnpm --filter @pacer/reference-data build:foundation-gap-visual-review-queue
pnpm --filter @pacer/reference-data build:foundation-gap-operations-dashboard
pnpm --filter @pacer/reference-data build:foundation-residual-review-worklist
pnpm --filter @pacer/reference-data build:foundation-sqlite-db
```

## 검증 프로토콜

필수 검증:

```bash
python3 -m py_compile packages/reference-data/scripts/build-foundation-db-candidates.py
python3 -m py_compile packages/reference-data/scripts/build-foundation-gap-source-candidates.py
python3 -m py_compile packages/reference-data/scripts/build-foundation-gap-operations-dashboard.py
python3 -m py_compile packages/reference-data/scripts/build-foundation-release-monitor-targets.py
python3 -m py_compile packages/reference-data/scripts/build-foundation-operational-review-batches.py
python3 -m py_compile packages/reference-data/scripts/audit-foundation-p0-seed.py
python3 -m py_compile packages/reference-data/scripts/audit-foundation-operational-readiness.py
python3 -m py_compile packages/reference-data/scripts/build-foundation-sqlite-db.py
python3 -m py_compile packages/reference-data/scripts/build-foundation-residual-review-worklist.py
pnpm --filter @pacer/reference-data typecheck
pnpm --filter @pacer/reference-data build:foundation-residual-review-worklist
pnpm --filter @pacer/reference-data audit:foundation-p0-seed
pnpm --filter @pacer/reference-data audit:foundation-operational-readiness
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite "pragma integrity_check;"
```

Before/after 확인:

```bash
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite \
  "select priority_tier,next_best_stage,target_entity,count(*) as rows
   from foundation_gap_operations_dashboard
   group by priority_tier,next_best_stage,target_entity
   order by priority_tier,next_best_stage,rows desc;"
```

```bash
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite \
  "select coverage_tier,count(*) as cells
   from foundation_university_year_coverage
   group by coverage_tier
   order by cells desc;"
```

```bash
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite \
  "select 'AdmissionUnit' as metric,count(*) as rows from foundation_admission_units
   union all select 'HistoricalOutcome',count(*) from foundation_historical_outcomes
   union all select 'HistoricalOutcome_score_bearing',count(*) from foundation_historical_outcomes where has_outcome_score='True'
   union all select 'HistoricalOutcome_quota_competition_bearing',count(*) from foundation_historical_outcomes where has_quota_and_competition='True'
   union all select 'AdmissionRuleReviewCandidates',count(*) from foundation_admission_rule_review_candidates;"
```

```bash
sqlite3 -header -csv packages/reference-data/data/public/foundation/foundation_reference.sqlite \
  "select residual_category,residual_priority,delegate_track,count(*) as rows
   from foundation_residual_review_worklist
   group by residual_category,residual_priority,delegate_track
   order by rows desc;"
```

에이전트 완료 보고에는 반드시 다음을 포함한다.

- 맡은 `gap_operation_id` 또는 `crawler_worklist_id`.
- 처리 전/후 P0 stage count.
- 새로 생성한 source label, output dir, manifest path.
- 새 row 수와 sourceConfidence.
- blocker 판정이면 공식 URL, 확인 날짜, 왜 자동 수집/승격하지 않았는지.
- 실행한 검증 명령과 결과.
