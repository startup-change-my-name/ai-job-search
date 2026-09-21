import { headers } from "next/headers";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET } from "./route";

vi.mock("next/headers", () => ({ headers: vi.fn() }));

describe("GET /api/status", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetAllMocks();
    delete process.env.TAILSCALE_ALLOWED_LOGINS;
    delete process.env.BACKEND_INTERNAL_URL;
    delete process.env.INTERNAL_PROXY_TOKEN;
  });

  it("rechecks identity and does not call the backend when unauthorized", async () => {
    process.env.TAILSCALE_ALLOWED_LOGINS = "owner@example.com";
    vi.mocked(headers).mockResolvedValue(new Headers() as never);
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    const response = await GET();

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({ detail: "Access denied" });
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("forwards only an authenticated call with the internal token", async () => {
    process.env.TAILSCALE_ALLOWED_LOGINS = "owner@example.com";
    process.env.BACKEND_INTERNAL_URL = "http://backend:8000";
    process.env.INTERNAL_PROXY_TOKEN = "test-proxy-token";
    vi.mocked(headers).mockResolvedValue(
      new Headers({ "Tailscale-User-Login": "Owner@Example.com" }) as never,
    );
    const fetchSpy = vi.fn().mockResolvedValue(
      Response.json({ status: "ok" }, { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchSpy);

    const response = await GET();

    expect(fetchSpy).toHaveBeenCalledWith(
      "http://backend:8000/api/v1/system/status",
      {
        headers: { "X-Job-Control-Proxy-Token": "test-proxy-token" },
        cache: "no-store",
      },
    );
    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ status: "ok" });
  });
});
