import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { isAuthorized, parseAllowedLogins } from "@/lib/auth";

export function proxy(request: NextRequest) {
  const allowed = parseAllowedLogins(process.env.TAILSCALE_ALLOWED_LOGINS ?? "");
  const login = request.headers.get("Tailscale-User-Login");
  if (!isAuthorized(login, allowed)) {
    return NextResponse.json({ detail: "Access denied" }, { status: 403 });
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
