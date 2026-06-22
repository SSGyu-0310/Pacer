import { NextResponse, type NextRequest } from "next/server";
import { adminLoginResponse } from "@/lib/admin-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const { token } = (await req.json().catch(() => ({}))) as { token?: string };
  return adminLoginResponse(req, token ?? "");
}
