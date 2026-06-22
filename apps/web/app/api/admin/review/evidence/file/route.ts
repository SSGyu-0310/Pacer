import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { NextResponse, type NextRequest } from "next/server";
import { requireAdminRequest } from "@/lib/admin-auth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const REPO_ROOT = process.cwd().replace(/\/apps\/web$/, "");
const ALLOWED_ROOTS = [
  path.resolve(REPO_ROOT, ".reference-data"),
  path.resolve(REPO_ROOT, "packages/reference-data/data"),
];

export async function GET(req: NextRequest) {
  const denied = await requireAdminRequest(req);
  if (denied) return denied;
  const rawPath = new URL(req.url).searchParams.get("path");
  if (!rawPath || rawPath.includes("..")) {
    return NextResponse.json({ error: "bad_path" }, { status: 400 });
  }
  const fullPath = path.resolve(REPO_ROOT, rawPath);
  if (!ALLOWED_ROOTS.some((root) => fullPath === root || fullPath.startsWith(root + path.sep))) {
    return NextResponse.json({ error: "forbidden_path" }, { status: 403 });
  }
  if (!existsSync(fullPath)) return NextResponse.json({ error: "not_found" }, { status: 404 });
  const bytes = await readFile(fullPath);
  return new NextResponse(bytes, {
    headers: {
      "content-type": contentType(fullPath),
      "cache-control": "no-store",
    },
  });
}

function contentType(filePath: string): string {
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".pdf") return "application/pdf";
  if (ext === ".png") return "image/png";
  if (ext === ".jpg" || ext === ".jpeg") return "image/jpeg";
  if (ext === ".html") return "text/html; charset=utf-8";
  return "text/plain; charset=utf-8";
}
