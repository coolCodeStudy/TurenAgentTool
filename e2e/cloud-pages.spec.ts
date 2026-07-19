import { expect, test } from "@playwright/test";

async function openExperience(page: import("@playwright/test").Page, route: string) {
  await page.goto(route, { waitUntil: "commit" });
  await expect(page.locator("html")).toHaveAttribute("data-experience-ready", "true", { timeout: 10_000 });
}

for (const [route, heading] of [
  ["/daily-market-brief", "每日市场简报"],
  ["/weekly-review", "本周复盘"],
  ["/command", "Command Workbench"],
] as const) {
  test(`desktop frame renders without horizontal overflow: ${route}`, async ({ page }) => {
    await openExperience(page, route);

    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    await expect(page.locator("html")).toEvaluate(
      (documentElement) => documentElement.scrollWidth <= documentElement.clientWidth,
    );
  });
}

test.describe("Daily Market Brief desktop journey", () => {
  test("renders a saved brief after Read", async ({ page }) => {
    await openExperience(page, "/daily-market-brief");
    await page.getByLabel("市场日期").fill("2026-07-17");
    await page.getByRole("button", { name: "读取" }).click();
    await expect(page.getByRole("status")).not.toContainText("正在读取", { timeout: 10_000 });
    await expect(page.locator("#summary")).not.toBeEmpty();
    await expect(page.locator("#indexes")).not.toBeEmpty();
    await expect(page.getByRole("heading", { name: "核心指数" })).toBeVisible();
  });
});

test.describe("Weekly Review desktop journey", () => {
  test("settles a public read when the week changes", async ({ page }) => {
    await openExperience(page, "/weekly-review");
    await page.getByRole("button", { name: "本周" }).click();

    await expect(page.getByRole("status")).not.toContainText("正在读取", { timeout: 10_000 });
    await expect(page.locator("#error-message")).toBeHidden();
    await expect(page.getByRole("heading", { name: "本周复盘" })).toBeVisible();
  });
});

test.describe("Command Workbench desktop journey", () => {
  test("shows recoverable private access instead of a stuck preview", async ({ page }) => {
    await openExperience(page, "/command");
    await expect(page.locator("#catalog")).not.toBeEmpty();

    await page.getByLabel("Command").fill("系统状态");
    await page.getByRole("button", { name: "Preview" }).click();

    await expect(page.locator("#access-panel")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("#access-message")).toContainText("Private access");
  });

  test("@protected parses a protected read-only command only when the CI credential is configured", async ({ page }) => {
    const token = process.env.E2E_PROTECTED_ACCESS_TOKEN;
    test.skip(!token, "E2E_PROTECTED_ACCESS_TOKEN is not configured for this run.");

    await openExperience(page, "/command");
    await page.getByLabel("Command").fill("系统状态");
    await page.getByRole("button", { name: "Preview" }).click();
    await expect(page.locator("#access-panel")).toBeVisible();

    await page.getByLabel("Access credential").fill(token);
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.locator("#preview")).toContainText("系统状态", { timeout: 10_000 });
  });
});
