export function parseAllowedLogins(raw: string): Set<string> {
  return new Set(
    raw
      .split(",")
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean),
  );
}

export function isAuthorized(login: string | null, allowed: Set<string>): boolean {
  return login !== null && allowed.has(login.trim().toLowerCase());
}

export function requireAuthorizedLogin(headers: Pick<Headers, "get">): string {
  const login = headers.get("Tailscale-User-Login");
  const allowed = parseAllowedLogins(process.env.TAILSCALE_ALLOWED_LOGINS ?? "");
  if (!isAuthorized(login, allowed)) {
    throw new Error("UNAUTHORIZED_TAILSCALE_IDENTITY");
  }
  return login!.trim().toLowerCase();
}
