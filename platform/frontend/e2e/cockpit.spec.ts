import { expect, test } from "@playwright/test";

test("cockpit stays readable and phone navigation remains touchable", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Operations cockpit" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Service health" })).toBeVisible();
  for (const name of ["Postgres", "Airflow"]) {
    const card = page.getByRole("article").filter({ has: page.getByRole("heading", { name, exact: true }) });
    await expect(card).toHaveAttribute("data-state", "healthy");
    await card.scrollIntoViewIfNeeded();
    await expect(card).toBeInViewport();
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  if (test.info().project.name === "phone") {
    const navigation = page.getByRole("navigation", { name: "Primary" });
    await expect(navigation).toBeInViewport();
    for (const name of ["Inbox", "Jobs", "Runs"]) {
      const link = navigation.getByRole("link", { name });
      const box = await link.boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(44);
      expect(box?.width).toBeGreaterThanOrEqual(44);
      await link.tap();
      await expect(page).toHaveURL(new RegExp(`#${name.toLowerCase()}$`));
    }
  }
});

test("authorized status request reports healthy dependencies", async ({ request }) => {
  const response = await request.get("/api/status");
  expect(response.status()).toBe(200);
  const status = await response.json();
  for (const name of ["postgres", "airflow"]) {
    expect(status.services).toEqual(expect.arrayContaining([expect.objectContaining({ name, state: "healthy" })]));
  }
});

for (const identity of [undefined, "not-allowed@example.com"]) {
  test(`${identity ? "unapproved" : "missing"} identity receives 403 on page and API`, async ({ browser, baseURL }) => {
    // Serve replaces client-supplied identity. Denial tests target the local app boundary only.
    test.skip(!["127.0.0.1", "localhost", "[::1]"].includes(new URL(baseURL!).hostname), "Direct-header denial checks require loopback.");
    const context = await browser.newContext({
      baseURL,
      extraHTTPHeaders: identity ? { "Tailscale-User-Login": identity } : {},
    });
    try {
      const page = await context.newPage();
      for (const route of ["/", "/api/status"]) {
        const response = await page.goto(route);
        expect(response?.status()).toBe(403);
        await expect(page.getByRole("heading", { name: "Operations cockpit" })).toHaveCount(0);
      }
    } finally {
      await context.close();
    }
  });
}
