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

  test("switches every market and reads a selected saved date without generation", async ({ page }) => {
    const readRequests: { method: string; url: string }[] = [];

    await page.route((url) => url.pathname.startsWith("/api/daily-market-brief"), async (route) => {
      const request = route.request();
      readRequests.push({ method: request.method(), url: request.url() });
      const requestUrl = new URL(request.url());

      if (requestUrl.pathname === "/api/daily-market-brief/dates") {
        await route.fulfill({ json: { ok: true, dates: ["2026-07-17"] } });
        return;
      }
      if (requestUrl.pathname === "/api/daily-market-brief/history-jobs") {
        await route.fulfill({ json: { ok: true, jobs: [] } });
        return;
      }

      const market = requestUrl.searchParams.get("market") || "CN";
      const marketDate = requestUrl.searchParams.get("date") || "2026-07-17";
      await route.fulfill({
        json: {
          ok: true,
          status: "ready",
          market_date: marketDate,
          context: {
            market: { name: market, code: market },
            market_date: marketDate,
            generated_at: {},
            indexes: [],
            sectors: [],
            gainers: [],
            capital_flow: [],
            source_status: {},
          },
          markdown: "# Daily brief",
        },
      });
    });

    await openExperience(page, "/daily-market-brief");
    const marketButton = (market: string) => page.locator(`[data-market="${market}"]`);
    await expect(marketButton("CN")).toHaveClass(/active/);

    for (const market of ["HK", "US", "CN"]) {
      await marketButton(market).click();
      await expect(marketButton(market)).toHaveClass(/active/);
      await expect(page.getByRole("status")).toContainText("已读取", { timeout: 10_000 });
    }

    await expect(page.getByLabel("已保存日期")).toHaveValue("");
    await page.getByLabel("已保存日期").selectOption("2026-07-17");
    await expect(page.getByLabel("市场日期")).toHaveValue("2026-07-17");
    await expect(page.getByRole("status")).toContainText("已读取", { timeout: 10_000 });
    await expect
      .poll(() => readRequests.some(({ url }) => url.includes("market=CN") && url.includes("date=2026-07-17")))
      .toBe(true);
    expect(readRequests.every(({ method }) => method === "GET")).toBe(true);
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
  test("shows a busy state and elapsed completion time for a slow public read", async ({ page }) => {
    let releaseInitialRead: (() => void) | undefined;
    await page.route((url) => url.pathname === "/api/weekly-review", async (route) => {
      await new Promise<void>((resolve) => {
        releaseInitialRead = resolve;
      });
      const weekStart = new URL(route.request().url()).searchParams.get("week_start");
      await route.fulfill({
        json: {
          ok: true,
          status: "missing",
          week: { start: weekStart },
          context: null,
          markdown: "",
        },
      });
    });

    await openExperience(page, "/weekly-review");
    await expect.poll(() => Boolean(releaseInitialRead)).toBe(true);
    await expect(page.getByRole("button", { name: "上一周" })).toBeDisabled();
    await expect(page.getByRole("button", { name: "本周" })).toBeDisabled();
    await expect(page.getByLabel("复盘周")).toBeDisabled();

    releaseInitialRead?.();

    await expect(page.getByRole("status")).toContainText("读取完成，用时", { timeout: 10_000 });
    await expect(page.getByRole("button", { name: "上一周" })).toBeEnabled();
    await expect(page.getByRole("button", { name: "本周" })).toBeEnabled();
  });

  test("settles a public read when the week changes", async ({ page }) => {
    await openExperience(page, "/weekly-review");
    await page.getByRole("button", { name: "本周" }).click();

    await expect(page.getByRole("status")).not.toContainText("正在读取", { timeout: 10_000 });
    await expect(page.locator("#error-message")).toBeHidden();
    await expect(page.getByRole("heading", { name: "本周复盘", exact: true })).toBeVisible();
  });

  test("navigates to the previous and current weeks with read-only requests", async ({ page }) => {
    const readRequests: { method: string; weekStart: string | null }[] = [];

    await page.route((url) => url.pathname === "/api/weekly-review", async (route) => {
      const request = route.request();
      const requestUrl = new URL(request.url());
      const weekStart = requestUrl.searchParams.get("week_start");
      readRequests.push({ method: request.method(), weekStart });
      await route.fulfill({
        json: {
          ok: true,
          status: "missing",
          week: { start: weekStart },
          context: null,
          markdown: "",
        },
      });
    });

    await openExperience(page, "/weekly-review");
    const weekDate = page.getByLabel("复盘周");
    const initialWeek = await weekDate.inputValue();
    await expect(page.locator("#review-period")).toContainText("复盘周期");
    await expect(page.locator("#review-period")).toContainText("至");

    await page.getByRole("button", { name: "上一周" }).click();
    await expect(page.getByRole("status")).toContainText("这一周还没有", { timeout: 10_000 });
    const previousWeek = await weekDate.inputValue();
    expect(previousWeek).not.toBe(initialWeek);
    await expect(page.locator("#review-period")).toContainText(previousWeek.replaceAll("-", "/"));

    await page.getByRole("button", { name: "本周" }).click();
    await expect(page.getByRole("status")).toContainText("这一周还没有", { timeout: 10_000 });
    const currentWeek = await weekDate.inputValue();
    expect(currentWeek).not.toBe(previousWeek);
    await expect
      .poll(() => readRequests.some(({ weekStart }) => weekStart === previousWeek) && readRequests.some(({ weekStart }) => weekStart === currentWeek))
      .toBe(true);
    expect(readRequests.every(({ method }) => method === "GET")).toBe(true);
  });

  test("Weekly source detail drawer shows safe source context without another request", async ({ page }) => {
    const readRequests: { authorization: string | null; method: string; url: string }[] = [];
    const oversizedReason = `Public reason\nwith\ttabs ${"x".repeat(500)} reason-tail-diagnostic`;
    await page.route((url) => url.pathname.startsWith("/api/"), async (route) => {
      const requestUrl = new URL(route.request().url());
      expect(requestUrl.pathname, `Unexpected API request: ${route.request().method()} ${requestUrl.pathname}`).toBe(
        "/api/weekly-review",
      );
      readRequests.push({
        authorization: await route.request().headerValue("authorization"),
        method: route.request().method(),
        url: route.request().url(),
      });
      await route.fulfill({
        json: {
          ok: true,
          status: "existing",
          week: { start: "2026-06-22", end: "2026-06-28" },
          markdown: "# 本周复盘",
          context: {
            holdings_table: [
              { market: "HK", code: "HK.00001", name: "正向标的", theme: "AI", market_val: 1000, current_pl_val: 80, weekly_pl_delta: 12.5, currency: 'HKD</td><img data-hostile-currency="yes" src=x>', status: "持有", knowledge_note: "观察", next_step: "跟踪" },
              { market: "US", code: "US.NEG", name: "负向标的", theme: "Cloud", market_val: 900, current_pl_val: -40, weekly_pl_delta: -8.25, currency: "USD", status: "持有", knowledge_note: "观察", next_step: "跟踪" },
              { market: "CN", code: "SH.600000", name: "旧版标的", theme: "Bank", market_val: 800, current_pl_val: 10, currency: "CNY", status: "持有", knowledge_note: "观察", next_step: "跟踪" },
            ],
            trades: {
              records: [
                { trade_date: "2026-06-23", create_time: "2026-06-23 10:15:00", trd_side: "BUY", code: "HK.00001", stock_name: "正向标的", qty: 100, price: 10.5, amount: 1050, currency: "HKD" },
                { trade_date: "2026-06-24", create_time: "2026-06-24 14:30:00", trd_side: "SELL", code: "US.NEG", stock_name: "负向标的", qty: 5, price: 180, amount: 900, currency: "USD" },
              ],
            },
            source_status: {
              trades: { status: "ok", count: 3, provider: "ledger", fetched_at: "2026-06-28T16:00:00Z" },
              indexes: {
                status: "partial",
                count: 2,
                coverage: "2/3 markets",
                missing: ["US"],
                uncovered_active_markets: ["US"],
                selected_source: "yahoo_chart",
                from_cache: false,
              },
              events: {
                status: "source_blocked",
                count: 0,
                reason: oversizedReason,
                checked_categories: ["company_announcements_or_filings", "user_knowledge"],
                source_blocked_categories: ["macro_calendar", "general_news_theme_feed"],
                cached: true,
                provider_errors: ["raw-provider-diagnostic-marker"],
              },
              local_knowledge: {
                status: "missing",
                count: { nested: "nested-count-diagnostic" },
                reason: { nested: ["nested-reason-diagnostic"] },
                failures: ["raw-failure-diagnostic-marker"],
              },
            },
            highlights: [], blowups: [], index_summary: [], story: {}, next_week: [], holder_attribution: [], warnings: [],
          },
        },
      });
    });

    await openExperience(page, "/weekly-review");
    await expect(page.getByRole("region", { name: "当前持仓" })).toContainText("本周盈亏");
    const positiveRow = page.getByRole("row", { name: /正向标的/ });
    const positiveMarketValueCell = positiveRow.locator("td").nth(3);
    const positiveCurrentPlCell = positiveRow.locator("td").nth(4);
    const positiveWeeklyCell = positiveRow.locator("td").nth(5);
    await expect(positiveMarketValueCell).toContainText('1,000.00 HKD</td><img data-hostile-currency="yes" src=x>');
    await expect(positiveCurrentPlCell).toContainText('80.00 HKD</td><img data-hostile-currency="yes" src=x>');
    await expect(positiveWeeklyCell).toContainText('+12.50 HKD</td><img data-hostile-currency="yes" src=x>');
    await expect(page.locator('[data-hostile-currency="yes"]')).toHaveCount(0);
    await expect(page.getByRole("region", { name: "当前持仓" })).toContainText("-8.25 USD");
    await expect(page.getByRole("region", { name: "当前持仓" })).toContainText("—");
    await expect(page.locator("body")).not.toContainText("raw-provider-diagnostic-marker");

    const sourceCard = page.locator('[data-source-key="indexes"]');
    await expect(sourceCard).toHaveAttribute("role", "button");
    await expect(sourceCard).toHaveAttribute("tabindex", "0");
    await expect(sourceCard).toHaveAttribute("aria-haspopup", "dialog");
    await expect(sourceCard).toHaveAccessibleName(/查看数据详情$/);
    await sourceCard.focus();
    await sourceCard.press("Enter");
    const dialog = page.locator("#source-detail-dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("指数");
    await expect(dialog).toContainText("2026-06-22 至 2026-06-28");
    await expect(dialog).toContainText("yahoo_chart");
    await expect(dialog).toContainText("部分可用");
    await expect(dialog).toContainText("2/3 markets");
    await expect(dialog).toContainText("未覆盖活跃市场");
    await expect(dialog).toContainText("否（直接读取数据）");
    await expect(dialog).not.toContainText("raw-provider-diagnostic-marker");
    expect(readRequests).toHaveLength(1);
    expect(readRequests[0].method).toBe("GET");
    expect(readRequests[0].authorization).toBeNull();

    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(sourceCard).toBeFocused();
    expect(readRequests).toHaveLength(1);

    await sourceCard.press("Space");
    await expect(dialog).toBeVisible();
    await page.mouse.click(100, 100);
    await expect(dialog).not.toBeVisible();
    await expect(sourceCard).toBeFocused();
    expect(readRequests).toHaveLength(1);

    await sourceCard.press("Space");
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "关闭" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(sourceCard).toBeFocused();
    expect(readRequests).toHaveLength(1);

    const tradesCard = page.locator('[data-source-key="trades"]');
    await tradesCard.click();
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("交易记录");
    await expect(dialog).toContainText("3");
    await expect(dialog).toContainText("本复盘周逐笔交易");
    await expect(dialog).toContainText("2026-06-23");
    await expect(dialog).toContainText("买入");
    await expect(dialog).toContainText("正向标的");
    await expect(dialog).toContainText("100");
    await expect(dialog).toContainText("10.50 HKD");
    await expect(dialog).toContainText("1,050.00 HKD");
    await expect(dialog).toContainText("卖出");
    await expect(dialog).toContainText("负向标的");
    await expect(dialog).toContainText("900.00 USD");
    await dialog.getByRole("button", { name: "关闭" }).click();
    await expect(dialog).not.toBeVisible();
    await expect(tradesCard).toBeFocused();
    expect(readRequests).toHaveLength(1);

    const eventsCard = page.locator('[data-source-key="events"]');
    await eventsCard.focus();
    await eventsCard.press("Space");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("外部事件");
    await expect(dialog).toContainText("已检查类别");
    await expect(dialog).toContainText("company_announcements_or_filings");
    await expect(dialog).toContainText("来源阻塞类别");
    await expect(dialog).toContainText("macro_calendar");
    await expect(dialog).toContainText("是（使用缓存数据）");
    await expect(dialog).toContainText("Public reason with tabs");
    const reasonValue = dialog.locator("dd", { hasText: "Public reason with tabs" });
    expect((await reasonValue.textContent())?.length).toBeLessThanOrEqual(400);
    await expect(dialog).not.toContainText("reason-tail-diagnostic");
    await page.keyboard.press("Escape");
    await expect(dialog).not.toBeVisible();
    await expect(eventsCard).toBeFocused();
    expect(readRequests).toHaveLength(1);

    const localKnowledgeCard = page.locator('[data-source-key="local_knowledge"]');
    await localKnowledgeCard.click();
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("本地知识");
    await expect(dialog).not.toContainText("nested-count-diagnostic");
    await expect(dialog).not.toContainText("nested-reason-diagnostic");
    await expect(dialog).not.toContainText("raw-provider-diagnostic-marker");
    await expect(dialog).not.toContainText("raw-failure-diagnostic-marker");
    await dialog.getByRole("button", { name: "关闭" }).click();
    expect(readRequests).toHaveLength(1);
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

  test("Weekly generation immediately shows progress and prevents duplicate submission", async ({ page }) => {
    let releaseGeneration: (() => void) | undefined;
    let generationRequests = 0;
    await page.route((url) => url.pathname === "/api/weekly-review", async (route) => {
      const weekStart = new URL(route.request().url()).searchParams.get("week_start");
      await route.fulfill({
        json: { ok: true, status: "missing", week: { start: weekStart }, context: null, markdown: "" },
      });
    });
    await page.route((url) => url.pathname === "/api/weekly-review/generate", async (route) => {
      generationRequests += 1;
      await new Promise<void>((resolve) => {
        releaseGeneration = resolve;
      });
      await route.fulfill({ json: { ok: true, status: "generated" } });
    });

    await openExperience(page, "/weekly-review");
    const generate = page.locator("#weekly-generate");
    await expect(generate).toBeVisible();
    await generate.click();

    await expect.poll(() => Boolean(releaseGeneration)).toBe(true);
    await expect(generate).toBeDisabled();
    await expect(generate).toHaveText("正在生成复盘...");
    await expect(page.getByRole("status")).toContainText("正在生成本周复盘");
    expect(generationRequests).toBe(1);

    releaseGeneration?.();
    await expect(generate).toBeEnabled();
    await expect(generate).toHaveText("生成 / 刷新复盘");
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

  test("@protected parses a protected read-only command only when a feature-specific fixture is configured", async ({ page }) => {
    const token = process.env.E2E_PROTECTED_ACCESS_TOKEN;
    test.skip(!token, "A protected fixture is not configured for this run.");

    await openExperience(page, "/command");
    await page.getByLabel("Command").fill("系统状态");
    await page.getByRole("button", { name: "Preview" }).click();
    await expect(page.locator("#access-panel")).toBeVisible();

    await page.getByLabel("Access credential").fill(token);
    await page.getByRole("button", { name: "Continue" }).click();

    await expect(page.locator("#preview")).toContainText("系统状态", { timeout: 10_000 });
  });

});
