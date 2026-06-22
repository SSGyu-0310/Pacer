import type {
  EligibilityResult,
  EligibilityRules,
  NormalizedScores,
} from "../domain/entities";
import { SCIENCE_INQUIRY_SUBJECTS } from "./constants";

/**
 * 3. 지원 가능 조건 판정 (§8.1, §18.1 수학 선택 제한).
 * - 수학 선택과목 제한(예: 미적분/기하만 허용)
 * - 탐구 계열 제한(과탐/사탐)
 * - 한국사 최저 등급
 *
 * 판정 불가(선택과목 미입력 등)는 보수적으로 '불충족'으로 본다 —
 * 단정 금지 원칙(§2.1)상 자격 미확인 모집단위를 지원 가능으로 표시하지 않는다.
 */
export function checkEligibility(
  rules: EligibilityRules,
  scores: NormalizedScores,
): EligibilityResult {
  const failures: EligibilityResult["failures"] = [];

  // 수학 선택 제한
  if (rules.requiredMathSelections && rules.requiredMathSelections.length > 0) {
    const selection = scores.bySubject.get("math")?.selection;
    if (!selection || !rules.requiredMathSelections.includes(selection)) {
      failures.push({
        code: "math_selection",
        message: `수학 선택과목 제한: ${rules.requiredMathSelections.join("/")} 필요 (현재: ${selection ?? "미입력"})`,
      });
    }
  }

  // 탐구 계열 제한
  if (rules.requiredInquiryCategory) {
    const selections = (["inquiry1", "inquiry2"] as const)
      .map((s) => scores.bySubject.get(s)?.selection)
      .filter((s): s is string => s !== undefined);
    const matches = (sel: string) =>
      rules.requiredInquiryCategory === "science"
        ? SCIENCE_INQUIRY_SUBJECTS.includes(sel)
        : !SCIENCE_INQUIRY_SUBJECTS.includes(sel);
    if (selections.length === 0 || !selections.every(matches)) {
      failures.push({
        code: "inquiry_category",
        message: `탐구 계열 제한: ${rules.requiredInquiryCategory === "science" ? "과학탐구" : "사회탐구"} 필요`,
      });
    }
  }

  // 한국사 최저 등급
  if (rules.maxHistoryGrade !== undefined) {
    const grade = scores.bySubject.get("history")?.grade;
    if (grade === undefined || grade > rules.maxHistoryGrade) {
      failures.push({
        code: "history_grade",
        message: `한국사 ${rules.maxHistoryGrade}등급 이내 필요 (현재: ${grade ?? "미입력"})`,
      });
    }
  }

  return { eligible: failures.length === 0, failures };
}
