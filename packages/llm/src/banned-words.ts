/**
 * 금지 표현 필터 (§11.4). 리포트는 생성 후 반드시 이 필터를 통과해야 한다.
 * 통과 못하면 재생성하거나 차단한다.
 */
export const BANNED_PHRASES: readonly string[] = [
  "합격 보장",
  "무조건 합격",
  "확실히 붙음",
  "불합격 확정",
  "100%",
  "반드시",
  "진학사보다 정확",
  "예측 정확도 최고",
  "이 대학은 쓰면 붙는다",
];

/** 텍스트에 포함된 첫 금지어를 반환(없으면 null). */
export function findBannedPhrase(text: string): string | null {
  for (const phrase of BANNED_PHRASES) {
    if (text.includes(phrase)) return phrase;
  }
  return null;
}

/** 객체의 모든 문자열 값을 재귀 검사. 위반 시 throw. */
export function assertNoBannedPhrases(value: unknown): void {
  const hit = scan(value);
  if (hit) {
    throw new Error(`금지 표현 포함: "${hit}" (§11.4)`);
  }
}

function scan(value: unknown): string | null {
  if (typeof value === "string") return findBannedPhrase(value);
  if (Array.isArray(value)) {
    for (const v of value) {
      const hit = scan(v);
      if (hit) return hit;
    }
    return null;
  }
  if (value && typeof value === "object") {
    for (const v of Object.values(value)) {
      const hit = scan(v);
      if (hit) return hit;
    }
  }
  return null;
}
