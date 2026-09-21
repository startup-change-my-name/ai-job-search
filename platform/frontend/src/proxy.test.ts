import { afterEach, describe, expect, it } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

describe("Tailscale request boundary", () => {
  afterEach(() => {
    delete process.env.TAILSCALE_ALLOWED_LOGINS;
  });

  it("denies requests without an allowed exact login", async () => {
    process.env.TAILSCALE_ALLOWED_LOGINS = "owner@example.com";

    const response = proxy(new NextRequest("http://localhost/"));

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toEqual({ detail: "Access denied" });
  });

  it("allows a case-insensitive exact login", () => {
    process.env.TAILSCALE_ALLOWED_LOGINS = "owner@example.com";
    const request = new NextRequest("http://localhost/", {
      headers: { "Tailscale-User-Login": "Owner@Example.com" },
    });

    const response = proxy(request);

    expect(response.headers.get("x-middleware-next")).toBe("1");
  });
});
