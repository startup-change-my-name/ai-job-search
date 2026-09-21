import { afterEach, describe, expect, it } from "vitest";
import {
  isAuthorized,
  parseAllowedLogins,
  requireAuthorizedLogin,
} from "./auth";

describe("Tailscale identity authorization", () => {
  const allowed = parseAllowedLogins("owner@example.com, second@example.com ");

  it("normalizes configured logins", () => {
    expect([...allowed]).toEqual(["owner@example.com", "second@example.com"]);
  });

  it("accepts an exact case-insensitive login", () => {
    expect(isAuthorized("Owner@Example.com", allowed)).toBe(true);
  });

  it("rejects missing, partial, and unlisted logins", () => {
    expect(isAuthorized(null, allowed)).toBe(false);
    expect(isAuthorized("owner", allowed)).toBe(false);
    expect(isAuthorized("other@example.com", allowed)).toBe(false);
  });

  afterEach(() => {
    delete process.env.TAILSCALE_ALLOWED_LOGINS;
  });

  it("requires an allowed identity from the Tailscale header", () => {
    process.env.TAILSCALE_ALLOWED_LOGINS = " owner@example.com ";

    expect(
      requireAuthorizedLogin(
        new Headers({ "Tailscale-User-Login": "Owner@Example.com" }),
      ),
    ).toBe("owner@example.com");
  });

  it("rejects a missing or unlisted Tailscale identity", () => {
    process.env.TAILSCALE_ALLOWED_LOGINS = "owner@example.com";

    expect(() => requireAuthorizedLogin(new Headers())).toThrow(
      "UNAUTHORIZED_TAILSCALE_IDENTITY",
    );
    expect(() =>
      requireAuthorizedLogin(
        new Headers({ "Tailscale-User-Login": "other@example.com" }),
      ),
    ).toThrow("UNAUTHORIZED_TAILSCALE_IDENTITY");
  });
});
