import { NextResponse } from "next/server";
import { getAnonSessionId } from "@/lib/anon-session";
import { ADMISSION_YEAR } from "@/lib/constants";
import { getAuthService } from "@/lib/container";
import { createSupabaseServerClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: Request): Promise<NextResponse> {
  const requestUrl = new URL(req.url);
  const code = requestUrl.searchParams.get("code");
  const next = safeNextPath(requestUrl.searchParams.get("next"));
  const errorRedirect = new URL(`/dashboard?auth=error`, requestUrl.origin);

  if (!code) return NextResponse.redirect(errorRedirect);

  const supabase = await createSupabaseServerClient();
  if (!supabase) return NextResponse.redirect(errorRedirect);

  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) return NextResponse.redirect(errorRedirect);

  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();
  if (userError || !user) return NextResponse.redirect(errorRedirect);

  const auth = getAuthService();
  const { user: appUser } = await auth.getOrCreateUserFromSupabase({
    supabaseId: user.id,
    email: user.email ?? null,
    phone: user.phone ?? null,
    kakaoId:
      user.identities?.find((identity) => identity.provider === "kakao")?.id ??
      null,
  });

  const anonSessionId = await getAnonSessionId();
  if (anonSessionId) {
    await auth.mergeAnonCycleToUser({
      userId: appUser.id,
      anonSessionId,
      admissionYear: ADMISSION_YEAR,
    });
  }

  return NextResponse.redirect(new URL(next, requestUrl.origin));
}

function safeNextPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return "/dashboard";
  }
  return value;
}
