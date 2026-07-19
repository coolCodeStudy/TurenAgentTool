import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8010";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL,
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "desktop-public",
      use: { ...devices["Desktop Chrome"] },
      grepInvert: /@protected/,
    },
    {
      name: "desktop-protected",
      use: { ...devices["Desktop Chrome"] },
      grep: /@protected/,
    },
  ],
});
