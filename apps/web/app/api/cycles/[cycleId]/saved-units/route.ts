import type { SavedUnit } from "@pacer/core";
import { saveAdmissionUnitRequest } from "@pacer/shared";
import { NextResponse } from "next/server";
import { authorizeCycle } from "@/lib/authz";
import { getSavedUnitService } from "@/lib/container";
import { badRequest, fromDomainError, notFound } from "@/lib/http";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(
  _req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const units = await getSavedUnitService().list(cycleId);
    return NextResponse.json({ saved_units: units.map(serialize) });
  } catch (e) {
    return fromDomainError(e);
  }
}

export async function POST(
  req: Request,
  ctx: { params: Promise<{ cycleId: string }> },
): Promise<NextResponse> {
  const { cycleId } = await ctx.params;
  const json: unknown = await req.json().catch(() => null);
  const parsed = saveAdmissionUnitRequest.safeParse(json);
  if (!parsed.success) return badRequest(parsed.error);

  const cycle = await authorizeCycle(cycleId);
  if (!cycle) return notFound();

  try {
    const saved = await getSavedUnitService().save({
      cycleId,
      unitId: parsed.data.unit_id,
      priority: parsed.data.priority ?? null,
      memo: parsed.data.memo ?? null,
    });
    return NextResponse.json(
      { status: "saved" as const, saved_unit: serialize(saved) },
      { status: 201 },
    );
  } catch (e) {
    return fromDomainError(e);
  }
}

function serialize(unit: SavedUnit) {
  return {
    saved_unit_id: unit.id,
    unit_id: unit.unitId,
    university: unit.university,
    unit_name: unit.unitName,
    recruitment_group: unit.recruitmentGroup,
    priority: unit.priority,
    memo: unit.memo,
  };
}
