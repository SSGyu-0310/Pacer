import { NotFoundError, ValidationError } from "@pacer/core";
import { NextResponse } from "next/server";
import type { z } from "zod";

/** Zod 검증 실패 → 400 */
export function badRequest(issues: z.ZodError): NextResponse {
  return NextResponse.json(
    { error: "invalid_request", issues: issues.flatten() },
    { status: 400 },
  );
}

/** 리소스 없음/접근 불가 → 404 (존재 여부를 구분해 노출하지 않는다) */
export function notFound(): NextResponse {
  return NextResponse.json({ error: "not_found" }, { status: 404 });
}

/** 도메인 오류 → HTTP 매핑. 모르는 오류는 다시 던진다(500은 프레임워크가). */
export function fromDomainError(e: unknown): NextResponse {
  if (e instanceof ValidationError) {
    return NextResponse.json(
      { error: "validation_failed", message: e.message, details: e.warnings },
      { status: 400 },
    );
  }
  if (e instanceof NotFoundError) return notFound();
  if (isPrismaError(e)) {
    if (e.code === "P2003" || e.code === "P2025") return notFound();
    if (e.code === "P2002") {
      return NextResponse.json({ error: "conflict" }, { status: 409 });
    }
  }
  if (isLlmFailure(e)) {
    return NextResponse.json(
      {
        error: "report_generation_failed",
        message: "AI 리포트 생성 결과가 검증을 통과하지 못했습니다. 잠시 후 다시 시도해 주세요.",
      },
      { status: 502 },
    );
  }
  throw e;
}

function isPrismaError(e: unknown): e is { code: string } {
  return (
    typeof e === "object" &&
    e !== null &&
    "code" in e &&
    typeof (e as { code?: unknown }).code === "string" &&
    (e as { code: string }).code.startsWith("P")
  );
}

function isLlmFailure(e: unknown): boolean {
  return (
    e instanceof Error &&
    (e.name === "LlmOutputError" ||
      e.message.startsWith("금지 표현 포함") ||
      e.message.startsWith("LLM 호출 실패"))
  );
}

/** 아직 구현 안 된 엔드포인트 → 501 (스캐폴딩 표식) */
export function notImplemented(name: string): NextResponse {
  return NextResponse.json({ error: "not_implemented", endpoint: name }, { status: 501 });
}
