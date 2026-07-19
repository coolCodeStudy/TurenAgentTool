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
    await expect
      .poll(() =>
        page
          .locator("html")
          .evaluate((documentElement) => documentElement.scrollWidth <= documentElement.clientWidth),
      )
      .toBe(true);
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

  test("selecting a completed history task reads it without creating another task", async ({ page }) => {
    const job = {
      id: "history-task-42",
      status: "completed",
      completed_count: 1,
      total_count: 1,
      items: [{ market: "CN", market_date: "2026-07-17" }],
    };
    const historyRequests: { method: string; url: string }[] = [];

    await page.route((url) => url.pathname === "/api/daily-market-brief/history-jobs", async (route) => {
      const request = route.request();
      historyRequests.push({ method: request.method(), url: request.url() });
      if (request.url().includes("id=history-task-42")) {
        await route.fulfill({ json: { ok: true, job } });
        return;
      }
      await route.fulfill({ json: { ok: true, jobs: [job] } });
    });
    await page.route((url) => url.pathname === "/api/daily-market-brief/dates", (route) =>
      route.fulfill({ json: { ok: true, dates: ["2026-07-17"] } }),
    );
    await page.route((url) => url.pathname === "/api/daily-market-brief", (route) =>
      route.fulfill({
        json: {
          ok: true,
          status: "ready",
          market_date: "2026-07-17",
          context: {
            market: { name: "A股", code: "CN" },
            market_date: "2026-07-17",
            generated_at: {},
            indexes: [],
            sectors: [],
            gainers: [],
            capital_flow: [],
            source_status: {},
          },
          markdown: "# Daily brief",
        },
      }),
    );

    await openExperience(page, "/daily-market-brief");
    const task = page.getByRole("button", { name: /#history-task-42/ });
    await expect(task).toBeVisible();
    await task.click();

    await expect(page.locator("#summary")).not.toBeEmpty();
    expect(historyRequests.some(({ url }) => url.includes("id=history-task-42"))).toBe(true);
    expect(historyRequests.every(({ method }) => method === "GET")).toBe(true);
  });

  test("selecting a running history task polls it without creating another task", async ({ page }) => {
    const job = {
      id: "history-task-queued",
      status: "running",
      completed_count: 0,
      total_count: 1,
      current_market: "CN",
      current_market_date: "2026-07-17",
      items: [{ market: "CN", market_date: "2026-07-17" }],
    };
    const historyRequests: { method: string; url: string }[] = [];
    const mutationRequests: { method: string; url: string }[] = [];

    await page.route((url) => url.pathname === "/api/daily-market-brief/history-jobs", async (route) => {
      const request = route.request();
      historyRequests.push({ method: request.method(), url: request.url() });
      if (request.url().includes("id=history-task-queued")) {
        await route.fulfill({ json: { ok: true, job } });
        return;
      }
      await route.fulfill({ json: { ok: true, jobs: [job] } });
    });
    await page.route((url) => url.pathname === "/api/daily-market-brief/generate", async (route) => {
      const request = route.request();
      mutationRequests.push({ method: request.method(), url: request.url() });
      await route.fulfill({ status: 500, json: { ok: false, error: "Unexpected mutation" } });
    });
    await page.route((url) => url.pathname === "/api/daily-market-brief/dates", (route) =>
      route.fulfill({ json: { ok: true, dates: [] } }),
    );
    await page.route((url) => url.pathname === "/api/daily-market-brief", (route) =>
      route.fulfill({ json: { ok: true, status: "missing", market_date: "2026-07-17" } }),
    );

    await openExperience(page, "/daily-market-brief");
    const task = page.getByRole("button", { name: /#history-task-queued/ });
    await expect(task).toBeVisible();
    await task.click();

    await expect(page.getByRole("status")).toContainText("历史简报任务 #history-task-queued");
    await expect.poll(() => historyRequests.filter(({ url }) => url.includes("id=history-task-queued")).length).toBeGreaterThanOrEqual(2);
    expect(historyRequests.every(({ method }) => method === "GET")).toBe(true);
    expect(mutationRequests).toEqual([]);
  });
});

test.describe("Weekly Review desktop journey", () => {
  test("settles a public read when the week changes", async ({ page }) => {
    await openExperience(page, "/weekly-review");
    await page.getByRole("button", { name: "本周" }).click();

    await expect(page.getByRole("status")).not.toContainText("正在读取", { timeout: 10_000 });
    await expect(page.locator("#error-message")).toBeHidden();
    await expect(page.getByRole("heading", { name: "本周复盘", exact: true })).toBeVisible();
  });

  test("Weekly missing review offers protected recovery without an access token", async ({ page }) => {
    await openExperience(page, "/weekly-review");
    await page.getByLabel("复盘周").fill("2026-01-05");
    await page.getByLabel("复盘周").press("Tab");
    await expect(page.locator("#weekly-recovery")).toBeVisible({ timeout: 10_000 });

    await page.getByRole("button", { name: "生成 / 刷新复盘" }).click();
    await expect(page.locator("#weekly-access-panel")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("#weekly-access-message")).toContainText("Private access");
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
