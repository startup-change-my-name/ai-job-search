import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.JOB_CONTROL_TEST_URL;
if (!baseURL) throw new Error("Set JOB_CONTROL_TEST_URL to the running dashboard URL.");
const target = new URL(baseURL);
const isLoopback = ["127.0.0.1", "localhost", "[::1]"].includes(target.hostname);
const identity = process.env.JOB_CONTROL_TEST_IDENTITY;
if (identity && !isLoopback) {
  throw new Error("Synthetic identity headers are allowed only for loopback tests.");
}

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: "list",
  use: {
    baseURL,
    extraHTTPHeaders: identity ? { "Tailscale-User-Login": identity } : {},
    // Artifacts can contain private hostnames/identity; opt in only in private storage.
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
