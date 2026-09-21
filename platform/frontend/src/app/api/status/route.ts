import { headers } from "next/headers";
import { NextResponse } from "next/server";
import { requireAuthorizedLogin } from "@/lib/auth";

export async function GET() {
  try {
    requireAuthorizedLogin(await headers());
  } catch {
    return NextResponse.json({ detail: "Access denied" }, { status: 403 });
  }

  const backend = process.env.BACKEND_INTERNAL_URL;
  const token = process.env.INTERNAL_PROXY_TOKEN;
  if (!backend || !token) {
    return NextResponse.json(
      { detail: "Server configuration error" },
      { status: 503 },
    );
  }

  const response = await fetch(`${backend}/api/v1/system/status`, {
    headers: { "X-Job-Control-Proxy-Token": token },
    cache: "no-store",
  });
  const body = await response.json();
  return NextResponse.json(body, { status: response.status });
}
