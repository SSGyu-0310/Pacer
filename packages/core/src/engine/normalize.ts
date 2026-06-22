import type { Subject } from "@pacer/shared";
import type { NormalizedScores, ScoreInput } from "../domain/entities";
import {
  ENGLISH_STRENGTH_MAX_GRADE,
  ENGLISH_WEAKNESS_MIN_GRADE,
  STRENGTH_DELTA,
} from "./constants";

/** 강·약점 판정 대상(상대평가, 백분위 기준) */
const PERCENTILE_SUBJECTS: readonly Subject[] = [
  "korean",
  "math",
  "inquiry1",
  "inquiry2",
];

/**
 * 2. 성적 정규화 (§8.1).
 * - 과목별 점수 맵 구성
 * - 강·약점 과목 도출(결정적 규칙):
 *   상대평가 과목은 본인 백분위 평균 대비 ±STRENGTH_DELTA,
 *   영어는 절대평가 등급 기준(1등급 강점 / 4등급 이하 약점).
 *   한국사·제2외국어는 강약점 판정에서 제외.
 */
export function normalizeScores(input: ScoreInput): NormalizedScores {
  const bySubject = new Map(input.scores.map((s) => [s.subject, s]));

  const percentiles: { subject: Subject; percentile: number }[] = [];
  for (const subject of PERCENTILE_SUBJECTS) {
    const p = bySubject.get(subject)?.percentile;
    if (p !== undefined) percentiles.push({ subject, percentile: p });
  }

  const strengthSubjects: Subject[] = [];
  const weaknessSubjects: Subject[] = [];

  if (percentiles.length >= 2) {
    const mean =
      percentiles.reduce((acc, x) => acc + x.percentile, 0) /
      percentiles.length;
    for (const { subject, percentile } of percentiles) {
      if (percentile >= mean + STRENGTH_DELTA) strengthSubjects.push(subject);
      else if (percentile <= mean - STRENGTH_DELTA)
        weaknessSubjects.push(subject);
    }
  }

  const englishGrade = bySubject.get("english")?.grade;
  if (englishGrade !== undefined) {
    if (englishGrade <= ENGLISH_STRENGTH_MAX_GRADE)
      strengthSubjects.push("english");
    else if (englishGrade >= ENGLISH_WEAKNESS_MIN_GRADE)
      weaknessSubjects.push("english");
  }

  return { bySubject, strengthSubjects, weaknessSubjects };
}
