import crypto from "node:crypto";
import { cookies, headers } from "next/headers";
import { notFound } from "next/navigation";
import { NextResponse, type NextRequest } from "next/server";

const ADMIN_COOKIE = "pacer_admin_token";

export async function requireAdminRequest(req: NextRequest): Promise<NextResponse | null> {
  if (process.env.ADMIN_ENABLED !== "1") return NextResponse.json({ error: "not_found" }, { status: 404 });
  if (!isLocalhost(req.headers.get("host"))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const expected = process.env.ADMIN_TOKEN;
  if (!expected) return NextResponse.json({ error: "admin_token_missing" }, { status: 403 });
  const actual = req.headers.get("x-admin-token") ?? req.cookies.get(ADMIN_COOKIE)?.value ?? "";
  if (!constantTimeEqual(actual, expected)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return null;
}

export async function requireAdminPage(): Promise<void> {
  if (process.env.ADMIN_ENABLED !== "1") notFound();
  const host = (await headers()).get("host");
  if (!isLocalhost(host)) notFound();
  const expected = process.env.ADMIN_TOKEN;
  const actual = (await cookies()).get(ADMIN_COOKIE)?.value ?? "";
  if (!expected || !constantTimeEqual(actual, expected)) notFound();
}

/** 로그인 처리: 다른 admin 경로와 동일하게 404/localhost/상수시간 비교를 거친 뒤 쿠키를 설정한다. */
export function adminLoginResponse(req: NextRequest, token: string): NextResponse {
  if (process.env.ADMIN_ENABLED !== "1") return NextResponse.json({ error: "not_found" }, { status: 404 });
  if (!isLocalhost(req.headers.get("host"))) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  const expected = process.env.ADMIN_TOKEN;
  if (!expected || !token || !constantTimeEqual(token, expected)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return setAdminCookie(token);
}

export function setAdminCookie(token: string): NextResponse {
  const response = NextResponse.json({ status: "ok" });
  response.cookies.set(ADMIN_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    path: "/",
  });
  return response;
}

function isLocalhost(host: string | null): boolean {
  const normalized = (host ?? "").split(":")[0];
  return normalized === "localhost" || normalized === "127.0.0.1" || normalized === "[::1]" || normalized === "::1";
}

function constantTimeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  if (left.length !== right.length) return false;
  return crypto.timingSafeEqual(left, right);
}
