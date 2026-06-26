"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import type { ReferenceUnitItem, ReferenceUniversityItem } from "@pacer/shared";
import { useRouter } from "next/navigation";
import type { KeyboardEvent, ReactNode } from "react";
import { useEffect, useState } from "react";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { z } from "zod";
import { track } from "@/lib/analytics";
import { ADMISSION_YEAR, postJson, writeStoredState } from "@/lib/client";

const MATH_SELECTIONS = ["미적분", "기하", "확률과통계"] as const;
const INQUIRY_SELECTIONS = [
  "물리학Ⅰ",
  "화학Ⅰ",
  "생명과학Ⅰ",
  "지구과학Ⅰ",
  "물리학Ⅱ",
  "화학Ⅱ",
  "생명과학Ⅱ",
  "지구과학Ⅱ",
  "생활과윤리",
  "사회문화",
  "윤리와사상",
  "한국지리",
] as const;
const UNIVERSITY_INITIAL_GROUPS = ["ㄱ", "ㄴ-ㅂ", "ㅅ", "ㅇ-ㅈ", "ㅊ-ㅎ"] as const;

const optionalScore = (max: number) =>
  z.preprocess(
    (v) => (v === "" || v === null || Number.isNaN(v) ? undefined : v),
    z.coerce
      .number({ invalid_type_error: "숫자만 입력해 주세요" })
      .min(0, "0 이상이어야 해요")
      .max(max, `${max} 이하여야 해요`)
      .optional(),
  );

/** 필수 숫자 — 비우면 NaN이 되므로 한국어 안내로 통일 */
const requiredScore = (max: number, label: string) =>
  z.coerce
    .number({ invalid_type_error: `${label}를 입력해 주세요` })
    .min(0, "0 이상이어야 해요")
    .max(max, `${max} 이하여야 해요`);

const formSchema = z.object({
  grade_status: z.enum(["high3", "repeater", "other"]),
  track: z.enum(["humanities", "natural", "medical", "undecided"]),
  risk_profile: z.enum(["conservative", "balanced", "aggressive"]),
  susi_jungsi_preference: z.enum(["susi", "jungsi", "undecided"]),
  korean_raw: optionalScore(100),
  korean_standard: requiredScore(200, "표준점수"),
  korean_percentile: requiredScore(100, "백분위"),
  math_raw: optionalScore(100),
  math_standard: requiredScore(200, "표준점수"),
  math_percentile: requiredScore(100, "백분위"),
  math_selection: z.string().min(1, "선택과목을 골라 주세요"),
  english_grade: z.coerce
    .number({ invalid_type_error: "등급을 선택해 주세요" })
    .int()
    .min(1)
    .max(9),
  history_grade: z.coerce
    .number({ invalid_type_error: "등급을 선택해 주세요" })
    .int()
    .min(1)
    .max(9),
  inquiry1_raw: optionalScore(50),
  inquiry1_standard: requiredScore(200, "표준점수"),
  inquiry1_percentile: requiredScore(100, "백분위"),
  inquiry1_selection: z.string().min(1, "선택과목을 골라 주세요"),
  inquiry2_raw: optionalScore(50),
  inquiry2_standard: requiredScore(200, "표준점수"),
  inquiry2_percentile: requiredScore(100, "백분위"),
  inquiry2_selection: z.string().min(1, "선택과목을 골라 주세요"),
});

type FormValues = z.infer<typeof formSchema>;
type FieldName = keyof FormValues;

const defaults: FormValues = {
  grade_status: "high3",
  track: "natural",
  risk_profile: "balanced",
  susi_jungsi_preference: "jungsi",
  korean_raw: undefined,
  korean_standard: 131,
  korean_percentile: 93,
  math_raw: undefined,
  math_standard: 135,
  math_percentile: 96,
  math_selection: "미적분",
  english_grade: 2,
  history_grade: 2,
  inquiry1_raw: undefined,
  inquiry1_standard: 67,
  inquiry1_percentile: 94,
  inquiry1_selection: "물리학Ⅰ",
  inquiry2_raw: undefined,
  inquiry2_standard: 65,
  inquiry2_percentile: 90,
  inquiry2_selection: "지구과학Ⅰ",
};

type ScoreMode = "official" | "estimated";

export default function ScorePage() {
  const router = useRouter();
  const [mode, setMode] = useState<ScoreMode>("official");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [universityQuery, setUniversityQuery] = useState("");
  const [universityInitialGroup, setUniversityInitialGroup] =
    useState<(typeof UNIVERSITY_INITIAL_GROUPS)[number]>("ㄱ");
  const [browseUniversityOptions, setBrowseUniversityOptions] = useState<
    ReferenceUniversityItem[]
  >([]);
  const [browseUniversityLoading, setBrowseUniversityLoading] = useState(false);
  const [searchUniversityOptions, setSearchUniversityOptions] = useState<
    ReferenceUniversityItem[]
  >([]);
  const [searchUniversityLoading, setSearchUniversityLoading] = useState(false);
  const [selectedUniversities, setSelectedUniversities] = useState<
    ReferenceUniversityItem[]
  >([]);
  const [activeUniversityId, setActiveUniversityId] = useState<string | null>(null);
  const [unitQuery, setUnitQuery] = useState("");
  const [unitOptions, setUnitOptions] = useState<ReferenceUnitItem[]>([]);
  const [unitLoading, setUnitLoading] = useState(false);
  const [selectedUnits, setSelectedUnits] = useState<ReferenceUnitItem[]>([]);
  const {
    register,
    handleSubmit,
    setValue,
    setFocus,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: defaults,
  });
  const activeUniversity =
    selectedUniversities.find((university) => university.id === activeUniversityId) ??
    selectedUniversities[0] ??
    null;

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setBrowseUniversityLoading(true);
      try {
        const qs = new URLSearchParams({
          initial_group: universityInitialGroup,
          limit: "24",
        });
        const data = await fetchJson<{ universities: ReferenceUniversityItem[] }>(
          `/api/reference/universities?${qs.toString()}`,
          controller.signal,
        );
        setBrowseUniversityOptions(data.universities);
      } catch (e) {
        if (!isAbortError(e)) setBrowseUniversityOptions([]);
      } finally {
        if (!controller.signal.aborted) setBrowseUniversityLoading(false);
      }
    }, 180);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [universityInitialGroup]);

  useEffect(() => {
    const q = universityQuery.trim();
    if (!q) {
      setSearchUniversityOptions([]);
      setSearchUniversityLoading(false);
      return;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setSearchUniversityLoading(true);
      try {
        const qs = new URLSearchParams({
          q,
          limit: "12",
        });
        const data = await fetchJson<{ universities: ReferenceUniversityItem[] }>(
          `/api/reference/universities?${qs.toString()}`,
          controller.signal,
        );
        setSearchUniversityOptions(data.universities);
      } catch (e) {
        if (!isAbortError(e)) setSearchUniversityOptions([]);
      } finally {
        if (!controller.signal.aborted) setSearchUniversityLoading(false);
      }
    }, 180);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [universityQuery]);

  useEffect(() => {
    if (!activeUniversity) {
      setUnitOptions([]);
      setUnitLoading(false);
      return;
    }

    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      setUnitLoading(true);
      try {
        const qs = new URLSearchParams({
          university_id: activeUniversity.id,
          q: unitQuery,
          limit: "16",
        });
        const data = await fetchJson<{ units: ReferenceUnitItem[] }>(
          `/api/reference/units?${qs.toString()}`,
          controller.signal,
        );
        setUnitOptions(data.units);
      } catch (e) {
        if (!isAbortError(e)) setUnitOptions([]);
      } finally {
        if (!controller.signal.aborted) setUnitLoading(false);
      }
    }, 180);
    return () => {
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, [activeUniversity, unitQuery]);

  /* ── 자동 진행: 칩 선택/입력 완료 시 다음 입력으로 ── */
  function advance(target: string) {
    if (target.startsWith("#")) {
      document
        .querySelector(target)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setFocus(target as FieldName);
  }

  function selectChip(name: FieldName, value: string | number, next?: string) {
    setValue(name, value as never, { shouldValidate: true });
    if (next) setTimeout(() => advance(next), 120);
  }

  /** 숫자 입력이 기대 자릿수에 도달하면 다음 필드로 */
  function numberField(name: FieldName, next: string, fullLen: number) {
    const reg = register(name, {
      valueAsNumber: true,
      onChange: (e: { target: { value: string } }) => {
        if (String(e.target.value).length >= fullLen) advance(next);
      },
    });
    const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        advance(next);
      }
    };
    return { ...reg, onKeyDown };
  }

  function selectUniversity(university: ReferenceUniversityItem) {
    const relatedIds = new Set(university.related_ids);
    if (
      !selectedUniversities.some(
        (item) => item.id === university.id || item.related_ids.some((id) => relatedIds.has(id)),
      )
    ) {
      setSelectedUniversities([...selectedUniversities, university]);
    }
    setActiveUniversityId(university.id);
    setUniversityQuery("");
  }

  function removeUniversity(id: string) {
    const target = selectedUniversities.find((university) => university.id === id);
    const relatedIds = new Set(target?.related_ids ?? [id]);
    const nextUniversities = selectedUniversities.filter(
      (university) => !university.related_ids.some((relatedId) => relatedIds.has(relatedId)),
    );
    setSelectedUniversities(nextUniversities);
    setSelectedUnits(
      selectedUnits.filter((unit) => !relatedIds.has(unit.university_id)),
    );
    if (activeUniversityId !== null && relatedIds.has(activeUniversityId)) {
      setActiveUniversityId(nextUniversities[0]?.id ?? null);
    }
  }

  function selectUnit(unit: ReferenceUnitItem) {
    if (!selectedUnits.some((item) => item.id === unit.id)) {
      setSelectedUnits([...selectedUnits, unit]);
    }
    setUnitQuery("");
  }

  function removeUnit(id: string) {
    setSelectedUnits(selectedUnits.filter((unit) => unit.id !== id));
  }

  async function onSubmit(values: FormValues) {
    setError(null);
    setStatus("입시 사이클 생성 중");
    try {
      const cycle = await postJson<{ cycle_id: string }>("/api/cycles", {
        admission_year: ADMISSION_YEAR,
        grade_status: values.grade_status,
        track: values.track,
      });
      track("cycle_created", { admission_year: ADMISSION_YEAR });

      setStatus("성적 저장 중");
      const score = await postJson<{ exam_score_id: string }>(
        `/api/cycles/${cycle.cycle_id}/scores`,
        {
          exam_type: "june_mock",
          score_status: mode,
          scores: [
            {
              subject: "korean",
              ...(values.korean_raw !== undefined && { raw_score: values.korean_raw }),
              standard_score: values.korean_standard,
              percentile: values.korean_percentile,
            },
            {
              subject: "math",
              selection: values.math_selection,
              ...(values.math_raw !== undefined && { raw_score: values.math_raw }),
              standard_score: values.math_standard,
              percentile: values.math_percentile,
            },
            { subject: "english", grade: values.english_grade },
            { subject: "history", grade: values.history_grade },
            {
              subject: "inquiry1",
              selection: values.inquiry1_selection,
              ...(values.inquiry1_raw !== undefined && {
                raw_score: values.inquiry1_raw,
              }),
              standard_score: values.inquiry1_standard,
              percentile: values.inquiry1_percentile,
            },
            {
              subject: "inquiry2",
              selection: values.inquiry2_selection,
              ...(values.inquiry2_raw !== undefined && {
                raw_score: values.inquiry2_raw,
              }),
              standard_score: values.inquiry2_standard,
              percentile: values.inquiry2_percentile,
            },
          ],
        },
      );
      track("score_submit", { exam_type: "june_mock" });

      setStatus("목표 저장 중");
      const targetUniversityIds = uniqueStrings(
        selectedUniversities.flatMap((university) => university.related_ids),
      );
      const targetUnitIds = selectedUnits.map((unit) => unit.id);
      await postJson(`/api/cycles/${cycle.cycle_id}/targets`, {
        exam_type: "june_mock",
        target_universities: selectedUniversities.map((university) => university.name),
        target_university_ids: targetUniversityIds,
        target_major_groups: uniqueStrings(
          selectedUnits
            .map((unit) => unit.major_group)
            .filter((majorGroup): majorGroup is string => Boolean(majorGroup)),
        ),
        target_unit_ids: targetUnitIds,
        preferred_regions: [],
        risk_profile: values.risk_profile,
        susi_jungsi_preference: values.susi_jungsi_preference,
      });

      setStatus("분석 실행 중");
      const analysis = await postJson<{ analysis_snapshot_id: string }>(
        `/api/cycles/${cycle.cycle_id}/analysis/run`,
        {
          exam_score_id: score.exam_score_id,
          analysis_type: "june_position",
        },
      );
      track("analysis_success", { exam_type: "june_mock" });

      writeStoredState({
        cycleId: cycle.cycle_id,
        examScoreId: score.exam_score_id,
        snapshotId: analysis.analysis_snapshot_id,
      });
      router.push(`/analysis?snapshotId=${analysis.analysis_snapshot_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "분석을 시작하지 못했습니다.");
      setStatus(null);
    }
  }

  const showRaw = mode === "estimated";

  return (
    <main className="pb-8">
      <header className="space-y-1.5 pb-4 pt-2">
        <p className="text-xs font-medium text-slate-500">
          6월 모의평가 · 내부 데모(샘플 데이터)
        </p>
        <h1 className="text-2xl font-bold leading-tight text-slate-900">
          성적표 그대로 옮겨 적기만 하면 돼요
        </h1>
      </header>

      {/* 입력 모드 토글 */}
      <div className="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1">
        {(
          [
            ["official", "성적표 보고 입력"],
            ["estimated", "가채점 입력"],
          ] as const
        ).map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setMode(value)}
            className={`h-9 rounded-lg text-xs font-medium transition ${
              mode === value
                ? "bg-white font-semibold text-slate-900 shadow-sm"
                : "text-slate-500"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {showRaw ? (
        <p className="mt-2 rounded-xl bg-warn-soft p-3 text-xs leading-5 text-warn-fg">
          가채점 단계에서는 원점수와 함께 <b>예상 백분위·표준점수</b>를 입력해
          주세요. 회차별 변환표가 공개되기 전이라 자동 변환은 제공하지 않아요 —
          성적표가 나오면 실제 값으로 다시 분석할 수 있습니다.
        </p>
      ) : null}

      <form className="mt-4 space-y-4" onSubmit={handleSubmit(onSubmit)}>
        {/* 1. 기본 정보 */}
        <Card id="card-basic" step="1" title="기본 정보">
          <Field label="학적">
            <ChipGroup
              cols={3}
              value={watch("grade_status")}
              options={[
                ["high3", "고3"],
                ["repeater", "N수"],
                ["other", "기타"],
              ]}
              onSelect={(v) => selectChip("grade_status", v, "#chips-track")}
            />
          </Field>
          <Field label="계열">
            <div id="chips-track">
              <ChipGroup
                cols={4}
                value={watch("track")}
                options={[
                  ["natural", "자연"],
                  ["humanities", "인문"],
                  ["medical", "의약학"],
                  ["undecided", "미정"],
                ]}
                onSelect={(v) =>
                  selectChip("track", v, showRaw ? "korean_raw" : "korean_standard")
                }
              />
            </div>
          </Field>
        </Card>

        {/* 2. 과목별 점수 */}
        <Card id="card-scores" step="2" title="과목별 점수">
          <SubjectBlock
            label="국어"
            summary={subjectSummary(
              watch("korean_standard"),
              watch("korean_percentile"),
              showRaw ? watch("korean_raw") : undefined,
            )}
          >
            <div className={`grid gap-3 ${showRaw ? "grid-cols-3" : "grid-cols-2"}`}>
              {showRaw ? (
                <Field as="label" label="원점수" error={errors.korean_raw?.message}>
                  <NumberInput
                    {...numberField("korean_raw", "korean_standard", 3)}
                    error={errors.korean_raw?.message}
                  />
                </Field>
              ) : null}
              <Field as="label" label="표준점수" error={errors.korean_standard?.message}>
                <NumberInput
                  {...numberField("korean_standard", "korean_percentile", 3)}
                  error={errors.korean_standard?.message}
                />
              </Field>
              <Field as="label" label="백분위" error={errors.korean_percentile?.message}>
                <NumberInput
                  {...numberField("korean_percentile", "#chips-math", 3)}
                  error={errors.korean_percentile?.message}
                />
              </Field>
            </div>
          </SubjectBlock>

          <SubjectBlock
            label="수학"
            summary={subjectSummary(
              watch("math_standard"),
              watch("math_percentile"),
              showRaw ? watch("math_raw") : undefined,
              watch("math_selection"),
            )}
          >
            <Field label="선택과목" error={errors.math_selection?.message}>
              <div id="chips-math">
                <ChipGroup
                  cols={3}
                  value={watch("math_selection")}
                  options={MATH_SELECTIONS.map((s) => [s, s] as const)}
                  onSelect={(v) =>
                    selectChip(
                      "math_selection",
                      v,
                      showRaw ? "math_raw" : "math_standard",
                    )
                  }
                />
              </div>
            </Field>
            <div className={`grid gap-3 ${showRaw ? "grid-cols-3" : "grid-cols-2"}`}>
              {showRaw ? (
                <Field as="label" label="원점수" error={errors.math_raw?.message}>
                  <NumberInput
                    {...numberField("math_raw", "math_standard", 3)}
                    error={errors.math_raw?.message}
                  />
                </Field>
              ) : null}
              <Field as="label" label="표준점수" error={errors.math_standard?.message}>
                <NumberInput
                  {...numberField("math_standard", "math_percentile", 3)}
                  error={errors.math_standard?.message}
                />
              </Field>
              <Field as="label" label="백분위" error={errors.math_percentile?.message}>
                <NumberInput
                  {...numberField("math_percentile", "#chips-english", 3)}
                  error={errors.math_percentile?.message}
                />
              </Field>
            </div>
          </SubjectBlock>

          <SubjectBlock label="영어" summary={gradeSummary(watch("english_grade"))}>
            <Field label="등급 (절대평가)">
              <div id="chips-english">
                <GradeChips
                  value={watch("english_grade")}
                  onSelect={(g) => selectChip("english_grade", g, "#chips-history")}
                />
              </div>
            </Field>
          </SubjectBlock>

          <SubjectBlock label="한국사" summary={gradeSummary(watch("history_grade"))}>
            <Field label="등급 (절대평가)">
              <div id="chips-history">
                <GradeChips
                  value={watch("history_grade")}
                  onSelect={(g) => selectChip("history_grade", g, "#chips-inq1")}
                />
              </div>
            </Field>
          </SubjectBlock>

          <SubjectBlock
            label="탐구 1"
            summary={subjectSummary(
              watch("inquiry1_standard"),
              watch("inquiry1_percentile"),
              showRaw ? watch("inquiry1_raw") : undefined,
              watch("inquiry1_selection"),
            )}
          >
            <Field label="선택과목" error={errors.inquiry1_selection?.message}>
              <div id="chips-inq1">
                <ChipGroup
                  cols={4}
                  value={watch("inquiry1_selection")}
                  options={INQUIRY_SELECTIONS.map((s) => [s, s] as const)}
                  onSelect={(v) =>
                    selectChip(
                      "inquiry1_selection",
                      v,
                      showRaw ? "inquiry1_raw" : "inquiry1_standard",
                    )
                  }
                />
              </div>
            </Field>
            <div className={`grid gap-3 ${showRaw ? "grid-cols-3" : "grid-cols-2"}`}>
              {showRaw ? (
                <Field as="label" label="원점수" error={errors.inquiry1_raw?.message}>
                  <NumberInput
                    {...numberField("inquiry1_raw", "inquiry1_standard", 2)}
                    error={errors.inquiry1_raw?.message}
                  />
                </Field>
              ) : null}
              <Field as="label" label="표준점수" error={errors.inquiry1_standard?.message}>
                <NumberInput
                  {...numberField("inquiry1_standard", "inquiry1_percentile", 2)}
                  error={errors.inquiry1_standard?.message}
                />
              </Field>
              <Field as="label" label="백분위" error={errors.inquiry1_percentile?.message}>
                <NumberInput
                  {...numberField("inquiry1_percentile", "#chips-inq2", 2)}
                  error={errors.inquiry1_percentile?.message}
                />
              </Field>
            </div>
          </SubjectBlock>

          <SubjectBlock
            label="탐구 2"
            summary={subjectSummary(
              watch("inquiry2_standard"),
              watch("inquiry2_percentile"),
              showRaw ? watch("inquiry2_raw") : undefined,
              watch("inquiry2_selection"),
            )}
          >
            <Field label="선택과목" error={errors.inquiry2_selection?.message}>
              <div id="chips-inq2">
                <ChipGroup
                  cols={4}
                  value={watch("inquiry2_selection")}
                  options={INQUIRY_SELECTIONS.map((s) => [s, s] as const)}
                  onSelect={(v) =>
                    selectChip(
                      "inquiry2_selection",
                      v,
                      showRaw ? "inquiry2_raw" : "inquiry2_standard",
                    )
                  }
                />
              </div>
            </Field>
            <div className={`grid gap-3 ${showRaw ? "grid-cols-3" : "grid-cols-2"}`}>
              {showRaw ? (
                <Field as="label" label="원점수" error={errors.inquiry2_raw?.message}>
                  <NumberInput
                    {...numberField("inquiry2_raw", "inquiry2_standard", 2)}
                    error={errors.inquiry2_raw?.message}
                  />
                </Field>
              ) : null}
              <Field as="label" label="표준점수" error={errors.inquiry2_standard?.message}>
                <NumberInput
                  {...numberField("inquiry2_standard", "inquiry2_percentile", 2)}
                  error={errors.inquiry2_standard?.message}
                />
              </Field>
              <Field as="label" label="백분위" error={errors.inquiry2_percentile?.message}>
                <NumberInput
                  {...numberField("inquiry2_percentile", "#card-goal", 2)}
                  error={errors.inquiry2_percentile?.message}
                />
              </Field>
            </div>
          </SubjectBlock>
        </Card>

        {/* 3. 목표 (선택) */}
        <Card id="card-goal" step="3" title="목표" hint="선택 — 비워도 분석할 수 있어요">
          <Field as="label" label="대학 검색">
            <input
              value={universityQuery}
              onChange={(e) => setUniversityQuery(e.target.value)}
              placeholder="가천대, 연세대"
              className={inputClass}
            />
          </Field>

          {universityQuery.trim() ? (
            <OptionList
              loading={searchUniversityLoading}
              empty={searchUniversityOptions.length === 0}
            >
              {searchUniversityOptions.map((university) => (
                <UniversityOptionButton
                  key={university.id}
                  university={university}
                  selected={selectedUniversities.some(
                    (item) => item.id === university.id,
                  )}
                  onSelect={() => selectUniversity(university)}
                />
              ))}
            </OptionList>
          ) : null}

          <div className="grid grid-cols-5 gap-1">
            {UNIVERSITY_INITIAL_GROUPS.map((group) => {
              const selected = universityInitialGroup === group;
              return (
                <button
                  key={group}
                  type="button"
                  onClick={() => setUniversityInitialGroup(group)}
                  className={`h-9 rounded-lg border text-xs font-semibold transition ${
                    selected
                      ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-200 bg-white text-slate-600"
                  }`}
                >
                  {group}
                </button>
              );
            })}
          </div>
          <OptionList
            loading={browseUniversityLoading}
            empty={browseUniversityOptions.length === 0}
          >
            {browseUniversityOptions.map((university) => (
              <UniversityOptionButton
                key={university.id}
                university={university}
                selected={selectedUniversities.some(
                  (item) => item.id === university.id,
                )}
                onSelect={() => selectUniversity(university)}
              />
            ))}
          </OptionList>

          <TargetChipList
            label="선택한 대학"
            emptyLabel="대학 미선택"
            items={selectedUniversities.map((university) => ({
              id: university.id,
              label: university.display_name,
              active: activeUniversity?.id === university.id,
              meta: university.core_tier ?? undefined,
              onActivate: () => setActiveUniversityId(university.id),
              onRemove: () => removeUniversity(university.id),
            }))}
          />

          {selectedUniversities.length > 1 ? (
            <div className="flex flex-wrap gap-1.5">
              {selectedUniversities.map((university) => {
                const active = activeUniversity?.id === university.id;
                return (
                  <button
                    key={university.id}
                    type="button"
                    onClick={() => setActiveUniversityId(university.id)}
                    className={`h-8 rounded-lg border px-2 text-[11px] font-semibold transition ${
                      active
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 bg-white text-slate-600"
                    }`}
                  >
                    {university.display_name}
                  </button>
                );
              })}
            </div>
          ) : null}

          <Field as="label" label="모집단위 검색">
            <input
              value={unitQuery}
              onChange={(e) => setUnitQuery(e.target.value)}
              placeholder={
                activeUniversity
                  ? `${activeUniversity.display_name} 모집단위`
                  : "대학 선택 후 검색"
              }
              disabled={!activeUniversity}
              className={`${inputClass} disabled:bg-slate-50 disabled:text-slate-400`}
            />
          </Field>
          <OptionList
            loading={unitLoading}
            empty={Boolean(activeUniversity) && unitOptions.length === 0}
          >
            {unitOptions.map((unit) => {
              const selected = selectedUnits.some((item) => item.id === unit.id);
              return (
                <button
                  key={unit.id}
                  type="button"
                  onClick={() => selectUnit(unit)}
                  className={`flex min-h-12 items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left transition ${
                    selected
                      ? "border-slate-900 bg-slate-50"
                      : "border-slate-200 bg-white hover:border-slate-400"
                  }`}
                >
                  <span>
                    <span className="block text-sm font-semibold text-slate-900">
                      {unit.unit_name}
                    </span>
                    <span className="text-[11px] text-slate-500">
                      {unit.university_name} · {recruitmentGroupLabel(unit.recruitment_group)}
                      {unit.major_group ? ` · ${unit.major_group}` : ""}
                    </span>
                  </span>
                  <Badge tone={unit.analysis_readiness === "ready" ? "green" : "slate"}>
                    {readinessLabel(unit.analysis_readiness)}
                  </Badge>
                </button>
              );
            })}
          </OptionList>

          <TargetChipList
            label="선택한 모집단위"
            emptyLabel={
              selectedUniversities.length
                ? "대학 전체 모집단위"
                : "전체 모집단위"
            }
            items={selectedUnits.map((unit) => ({
              id: unit.id,
              label: `${unit.university_name} ${unit.unit_name}`,
              meta: readinessLabel(unit.analysis_readiness),
              onRemove: () => removeUnit(unit.id),
            }))}
          />

          <Field label="지원 성향">
            <ChipGroup
              cols={3}
              value={watch("risk_profile")}
              options={[
                ["conservative", "안정형"],
                ["balanced", "균형형"],
                ["aggressive", "공격형"],
              ]}
              onSelect={(v) => selectChip("risk_profile", v)}
            />
          </Field>
          <Field label="수시/정시">
            <ChipGroup
              cols={3}
              value={watch("susi_jungsi_preference")}
              options={[
                ["jungsi", "정시 중심"],
                ["susi", "수시 중심"],
                ["undecided", "고민 중"],
              ]}
              onSelect={(v) => selectChip("susi_jungsi_preference", v)}
            />
          </Field>
        </Card>

        {error ? (
          <p className="rounded-xl bg-band-risk-soft p-3 text-sm text-band-risk-fg">
            {error}
          </p>
        ) : null}

        <div className="sticky bottom-0 -mx-4 border-t border-slate-200 bg-white/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur">
          <button
            type="submit"
            disabled={isSubmitting}
            className="flex h-12 w-full items-center justify-center rounded-xl bg-slate-900 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:bg-slate-400"
          >
            {isSubmitting ? (status ?? "분석 중...") : "분석 시작"}
          </button>
        </div>
      </form>
    </main>
  );
}

/* ── UI 빌딩 블록 ── */

const inputClass =
  "mt-1 h-11 w-full rounded-xl border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-slate-900 focus:ring-2 focus:ring-slate-200";

function subjectSummary(
  standard?: number,
  percentile?: number,
  raw?: number,
  selection?: string,
): string {
  const parts: string[] = [];
  if (selection) parts.push(selection);
  if (raw !== undefined && !Number.isNaN(raw)) parts.push(`원점수 ${raw}`);
  if (standard !== undefined && !Number.isNaN(standard)) parts.push(`표준 ${standard}`);
  if (percentile !== undefined && !Number.isNaN(percentile))
    parts.push(`백분위 ${percentile}`);
  return parts.join(" · ");
}

function gradeSummary(grade?: number): string {
  return grade !== undefined && !Number.isNaN(grade) ? `${grade}등급` : "";
}

async function fetchJson<T>(url: string, signal: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`요청 실패(${res.status})`);
  return (await res.json()) as T;
}

function isAbortError(e: unknown): boolean {
  return (
    e instanceof DOMException && e.name === "AbortError"
  );
}

function OptionList({
  loading,
  empty,
  children,
}: {
  loading: boolean;
  empty: boolean;
  children: ReactNode;
}) {
  if (loading) {
    return (
      <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
        검색 중
      </p>
    );
  }
  if (empty) {
    return (
      <p className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
        검색 결과 없음
      </p>
    );
  }
  return <div className="grid gap-2">{children}</div>;
}

function UniversityOptionButton({
  university,
  selected,
  onSelect,
}: {
  university: ReferenceUniversityItem;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`flex min-h-12 items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left transition ${
        selected
          ? "border-slate-900 bg-slate-50"
          : "border-slate-200 bg-white hover:border-slate-400"
      }`}
    >
      <span>
        <span className="block text-sm font-semibold text-slate-900">
          {university.display_name}
        </span>
        <span className="text-[11px] text-slate-500">
          모집단위 {university.unit_count.toLocaleString("ko-KR")}개
        </span>
      </span>
      {university.core_tier ? <Badge tone="slate">{university.core_tier}</Badge> : null}
    </button>
  );
}

function TargetChipList({
  label,
  emptyLabel,
  items,
}: {
  label: string;
  emptyLabel: string;
  items: Array<{
    id: string;
    label: string;
    meta?: string;
    active?: boolean;
    onActivate?: () => void;
    onRemove: () => void;
  }>;
}) {
  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-slate-500">{label}</p>
      {items.length ? (
        <div className="flex flex-wrap gap-1.5">
          {items.map((item) => (
            <span
              key={item.id}
              className={`inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-xs font-semibold ${
                item.active
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 bg-slate-50 text-slate-700"
              }`}
            >
              <button
                type="button"
                onClick={item.onActivate}
                disabled={!item.onActivate}
                className="max-w-[13rem] truncate text-left disabled:cursor-default"
              >
                {item.label}
              </button>
              {item.meta ? (
                <span
                  className={`rounded-md px-1.5 py-0.5 text-[10px] ${
                    item.active
                      ? "bg-white/15 text-white"
                      : "bg-white text-slate-500"
                  }`}
                >
                  {item.meta}
                </span>
              ) : null}
              <button
                type="button"
                aria-label={`${item.label} 삭제`}
                onClick={item.onRemove}
                className={`flex size-5 items-center justify-center rounded-md ${
                  item.active
                    ? "bg-white/15 text-white"
                    : "bg-white text-slate-500"
                }`}
              >
                x
              </button>
            </span>
          ))}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-400">
          {emptyLabel}
        </p>
      )}
    </div>
  );
}

function Badge({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "green" | "slate";
}) {
  return (
    <span
      className={`shrink-0 rounded-lg px-2 py-1 text-[11px] font-bold ${
        tone === "green"
          ? "bg-emerald-50 text-emerald-700"
          : "bg-slate-100 text-slate-600"
      }`}
    >
      {children}
    </span>
  );
}

function recruitmentGroupLabel(group: ReferenceUnitItem["recruitment_group"]): string {
  return { ga: "가군", na: "나군", da: "다군", none: "군외" }[group];
}

function readinessLabel(readiness: ReferenceUnitItem["analysis_readiness"]): string {
  return {
    ready: "분석 가능",
    limited: "검토 중",
    unsupported: "제외",
  }[readiness];
}

function uniqueStrings(values: readonly string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function Card({
  id,
  step,
  title,
  hint,
  children,
}: {
  id: string;
  step: string;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="space-y-4 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
    >
      <div className="flex items-center gap-2">
        <span className="flex size-5 items-center justify-center rounded-full bg-slate-900 text-[11px] font-bold text-white">
          {step}
        </span>
        <h2 className="text-sm font-bold text-slate-900">{title}</h2>
        {hint ? <span className="text-[11px] text-slate-400">{hint}</span> : null}
      </div>
      {children}
    </section>
  );
}

function SubjectBlock({
  label,
  summary,
  children,
}: {
  label: string;
  summary?: string;
  children: ReactNode;
}) {
  return (
    <div className="space-y-2 rounded-xl bg-slate-50 p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-bold text-slate-700">{label}</h3>
        {summary ? (
          <p className="truncate text-[11px] font-medium tabular-nums text-band-match-fg">
            {summary}
          </p>
        ) : null}
      </div>
      {children}
    </div>
  );
}

/**
 * 입력 필드 래퍼.
 * 단일 input을 감싸면 as="label"로 렌더해 라벨-입력을 프로그램적으로 연결한다
 * (스크린리더/터치 타깃). 칩 그룹처럼 버튼 여러 개를 감쌀 때는 div 유지 —
 * label이면 라벨 텍스트 탭이 첫 버튼을 클릭해 의도치 않은 선택이 일어난다.
 */
function Field({
  label,
  error,
  as = "div",
  children,
}: {
  label: string;
  error?: string;
  as?: "div" | "label";
  children: ReactNode;
}) {
  const Tag = as;
  return (
    <Tag className="block text-xs font-medium text-slate-500">
      {label}
      {children}
      {error ? <span className="mt-1 block text-band-risk-fg">{error}</span> : null}
    </Tag>
  );
}

/** 카드(칩) 선택 그룹 — 선택 즉시 다음 입력으로 자동 진행 */
function ChipGroup({
  value,
  options,
  cols,
  onSelect,
}: {
  value: string | undefined;
  options: readonly (readonly [string, string])[];
  cols: number;
  onSelect: (value: string) => void;
}) {
  return (
    <div
      className="mt-1 grid gap-1.5"
      style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      role="radiogroup"
    >
      {options.map(([v, label]) => {
        const selected = value === v;
        return (
          <button
            key={v}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onSelect(v)}
            className={`h-10 rounded-xl border px-1 text-xs font-medium transition ${
              selected
                ? "border-slate-900 bg-slate-900 font-semibold text-white shadow-sm"
                : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

/** 등급 1~9 칩 (1~2등급 강조, 선택 즉시 다음으로) */
function GradeChips({
  value,
  onSelect,
}: {
  value: number | undefined;
  onSelect: (grade: number) => void;
}) {
  return (
    <div className="mt-1 grid grid-cols-9 gap-1" role="radiogroup">
      {Array.from({ length: 9 }, (_, i) => i + 1).map((g) => {
        const selected = value === g;
        return (
          <button
            key={g}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onSelect(g)}
            className={`h-10 rounded-lg border text-sm font-semibold tabular-nums transition ${
              selected
                ? "border-slate-900 bg-slate-900 text-white shadow-sm"
                : "border-slate-200 bg-white text-slate-600 hover:border-slate-400"
            }`}
          >
            {g}
          </button>
        );
      })}
    </div>
  );
}

function NumberInput({
  error,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  error?: string;
} & UseFormRegisterReturn) {
  return (
    <input
      type="number"
      inputMode="numeric"
      enterKeyHint="next"
      className={`${inputClass} ${error ? "border-band-risk" : ""}`}
      {...props}
    />
  );
}
