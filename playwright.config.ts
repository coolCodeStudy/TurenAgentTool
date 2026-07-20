import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:8010";
const protectedNoArtifacts = process.env.E2E_PROTECTED_NO_ARTIFACTS === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  reporter: protectedNoArtifacts ? [["list"]] : [["html", { open: "never" }], ["list"]],
  use: {
    baseURL,
    viewport: { width: 1440, height: 1000 },
    trace: protectedNoArtifacts ? "off" : "retain-on-failure",
    screenshot: protectedNoArtifacts ? "off" : "only-on-failure",
    video: protectedNoArtifacts ? "off" : "retain-on-failure",
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
