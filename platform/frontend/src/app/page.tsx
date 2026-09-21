import { headers } from "next/headers";
import { OperationsCockpit } from "@/components/OperationsCockpit";
import { requireAuthorizedLogin } from "@/lib/auth";
import type { SystemStatus } from "@/lib/status";

export const dynamic = "force-dynamic";

async function loadStatus(): Promise<SystemStatus> {
  const incoming = await headers();
  requireAuthorizedLogin(incoming);

  const backend = process.env.BACKEND_INTERNAL_URL;
  const token = process.env.INTERNAL_PROXY_TOKEN;
  if (!backend || !token) {
    throw new Error("Missing internal service configuration");
  }

  const response = await fetch(`${backend}/api/v1/system/status`, {
    headers: { "X-Job-Control-Proxy-Token": token },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`Status request failed: ${response.status}`);
  }
  return response.json();
}

export default async function Home() {
  return <OperationsCockpit status={await loadStatus()} />;
}
