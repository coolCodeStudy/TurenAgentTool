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

test.describe("AI Industry Panorama public journey", () => {
  type PanoramaEntity = {
    entity_id: string;
    label: string;
    kind: string;
    summary: string;
    aliases: string[];
    capability_roles: string[];
  };
  type PanoramaRelationship = {
    relationship_id: string;
    source_entity_id: string;
    target_entity_id: string;
    relationship_type: string;
    text: string;
    assertion_kind: string;
    lifecycle_state: string;
    geography_roles: [string, string][];
    reporting_period_start: string | null;
    reporting_period_end: string | null;
    effective_from: string | null;
    effective_to: string | null;
  };
  type PanoramaProjection = {
    entities: PanoramaEntity[];
    relationships: PanoramaRelationship[];
    facets: {
      lifecycle: { id: string; label: string }[];
      geography_role: { id: string; label: string }[];
    };
  };
  type ObservedRequest = { method: string; pathname: string };

  const sortedIds = (relationships: PanoramaRelationship[]) =>
    relationships.map((item) => item.relationship_id).sort();

  const relationshipIds = async (locator: import("@playwright/test").Locator) =>
    locator.evaluateAll((items) =>
      items
        .map((item) => item.getAttribute("data-relationship-id"))
        .filter((value): value is string => Boolean(value))
        .sort(),
    );

  const expectGraphTableIds = async (
    page: import("@playwright/test").Page,
    expectedIds: string[],
  ) => {
    const graph = page.locator("#panorama-graph [data-relationship-id]");
    const table = page.locator("#relationship-table-body [data-relationship-id]");
    await expect.poll(() => relationshipIds(graph)).toEqual(expectedIds);
    expect(await relationshipIds(table)).toEqual(expectedIds);
  };

  const expectNoPageOverflow = async (page: import("@playwright/test").Page) => {
    await expect
      .poll(() =>
        page
          .locator("html")
          .evaluate((documentElement) => documentElement.scrollWidth <= documentElement.clientWidth),
      )
      .toBe(true);
  };

  const searchRelationships = (projection: PanoramaProjection, query: string) => {
    const lowered = query.toLowerCase();
    const entities = new Map(projection.entities.map((item) => [item.entity_id, item]));
    return projection.relationships.filter((relationship) => {
      const endpointMatch = [
        entities.get(relationship.source_entity_id),
        entities.get(relationship.target_entity_id),
      ].filter(Boolean).some((entity) =>
        [
          entity!.label,
          entity!.kind,
          entity!.summary,
          ...entity!.aliases,
          ...entity!.capability_roles,
        ].some((value) => value.toLowerCase().includes(lowered)),
      );
      return endpointMatch || [
        relationship.relationship_type,
        relationship.text,
        relationship.assertion_kind,
      ].some((value) => value.toLowerCase().includes(lowered));
    });
  };

  const focusedRelationships = (
    projection: PanoramaProjection,
    entityId: string,
    hopDepth: number,
  ) => {
    let frontier = new Set([entityId]);
    const visited = new Set(frontier);
    const admitted = new Set<string>();
    for (let depth = 0; depth < hopDepth; depth += 1) {
      const next = new Set<string>();
      for (const relationship of projection.relationships) {
        const sourceSeen = frontier.has(relationship.source_entity_id);
        const targetSeen = frontier.has(relationship.target_entity_id);
        if (!sourceSeen && !targetSeen) continue;
        admitted.add(relationship.relationship_id);
        const other = sourceSeen
          ? relationship.target_entity_id
          : relationship.source_entity_id;
        if (!visited.has(other)) next.add(other);
      }
      next.forEach((id) => visited.add(id));
      frontier = next;
    }
    return [...admitted].sort();
  };

  const overlaps2026And2027 = (relationship: PanoramaRelationship) => {
    const usesReportingPeriod = Boolean(
      relationship.reporting_period_start || relationship.reporting_period_end,
    );
    const start = usesReportingPeriod
      ? relationship.reporting_period_start
      : relationship.effective_from;
    const end = usesReportingPeriod
      ? relationship.reporting_period_end
      : relationship.effective_to;
    if (!start && !end) return false;
    return (start || "0000-01-01") <= "2027-12-31"
      && (end || "9999-12-31") >= "2026-01-01";
  };

  const observeSameOrigin = (
    page: import("@playwright/test").Page,
    origin: string,
  ) => {
    const observed: ObservedRequest[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.origin === origin) {
        observed.push({ method: request.method(), pathname: url.pathname });
      }
    });
    return observed;
  };

  const expectReadOnlyPanoramaJourney = (observed: ObservedRequest[]) => {
    expect(observed.every(({ method }) => method === "GET" || method === "HEAD")).toBe(true);
    const panorama = observed
      .filter(({ pathname }) => pathname.includes("ai-industry-panorama"))
      .sort((left, right) => left.pathname.localeCompare(right.pathname));
    expect(panorama).toEqual([
      { method: "GET", pathname: "/ai-industry-panorama" },
      { method: "GET", pathname: "/api/ai-industry-panorama" },
      { method: "GET", pathname: "/assets/ai-industry-panorama.js" },
    ]);
  };

  test("AI Industry Panorama supports exact read-only evidence traversal on fresh desktop and mobile documents", async (
    { page, request, browser },
    testInfo,
  ) => {
    const apiResponse = await request.get("/api/ai-industry-panorama");
    expect(apiResponse.status()).toBe(200);
    const projection = await apiResponse.json() as PanoramaProjection;
    expect(projection.entities).toHaveLength(35);
    expect(projection.relationships).toHaveLength(48);

    const completeIds = sortedIds(projection.relationships);
    const microsoftSearchIds = sortedIds(searchRelationships(projection, "Microsoft"));
    const microsoftHopOneIds = focusedRelationships(
      projection,
      "entity:ENT-ORG-MICROSOFT",
      1,
    );
    const microsoftHopTwoIds = focusedRelationships(
      projection,
      "entity:ENT-ORG-MICROSOFT",
      2,
    );
    const unitedStatesIds = sortedIds(projection.relationships.filter((relationship) =>
      relationship.geography_roles.some(([id]) => id === "geography:us"),
    ));
    const periodIds = sortedIds(projection.relationships.filter(overlaps2026And2027));
    const committedIds = sortedIds(projection.relationships.filter(
      (relationship) => relationship.lifecycle_state === "committed",
    ));
    const announcedIds = sortedIds(projection.relationships.filter(
      (relationship) => relationship.lifecycle_state === "announced",
    ));
    const projectSiteIds = sortedIds(projection.relationships.filter(
      (relationship) =>
        relationship.geography_roles.some(([, role]) => role === "project_site"),
    ));
    const equipmentManufacturingIds = sortedIds(
      projection.relationships.filter((relationship) =>
        relationship.geography_roles.some(
          ([, role]) => role === "equipment_component_manufacturing",
        ),
      ),
    );
    const packagingTestIds = sortedIds(projection.relationships.filter(
      (relationship) =>
        relationship.geography_roles.some(([, role]) => role === "packaging_test"),
    ));
    const unknownRoleIds = sortedIds(projection.relationships.filter(
      (relationship) =>
        relationship.geography_roles.some(([, role]) => role === "unknown"),
    ));
    const disclosedIds = sortedIds(projection.relationships.filter(
      (relationship) => [
        "disclosed_fact",
        "company_guidance",
        "management_claim",
      ].includes(relationship.assertion_kind),
    ));
    expect(completeIds).toHaveLength(48);
    expect(microsoftSearchIds).not.toEqual(completeIds);
    expect(microsoftHopOneIds).toHaveLength(3);
    expect(microsoftHopTwoIds).toHaveLength(11);
    const microsoftHopTwoSet = new Set(microsoftHopTwoIds);
    expect(microsoftHopOneIds.every((id) => microsoftHopTwoSet.has(id))).toBe(true);
    expect(microsoftHopOneIds).not.toEqual(microsoftHopTwoIds);
    expect(unitedStatesIds).toHaveLength(8);
    expect(periodIds).toHaveLength(42);
    expect(committedIds).toHaveLength(12);
    expect(announcedIds).toEqual(["relationship:REL-AIP-0019"]);
    expect(projectSiteIds).toEqual([
      "relationship:REL-AIP-0019",
      "relationship:REL-AIP-0021",
      "relationship:REL-AIP-0022",
    ]);
    expect(equipmentManufacturingIds).toEqual([
      "relationship:REL-AIP-0018",
      "relationship:REL-AIP-0046",
      "relationship:REL-AIP-0047",
      "relationship:REL-AIP-0048",
    ]);
    expect(packagingTestIds).toEqual(["relationship:REL-AIP-0036"]);
    expect(unknownRoleIds).toEqual([
      "relationship:REL-AIP-0015",
      "relationship:REL-AIP-0016",
      "relationship:REL-AIP-0040",
    ]);
    expect(projection.facets.lifecycle.map((item) => item.id)).toContain("announced");
    expect(projection.facets.geography_role.map((item) => item.id)).toContain(
      "project_site",
    );
    expect(disclosedIds).toHaveLength(47);

    const baseOrigin = new URL(
      process.env.E2E_BASE_URL ?? "http://127.0.0.1:8010",
    ).origin;
    const desktopRequests = observeSameOrigin(page, baseOrigin);
    await page.goto("/ai-industry-panorama", { waitUntil: "commit" });
    await expect(page.locator("body")).toHaveAttribute("data-experience-ready", "true");
    await expect(page.getByRole("heading", { name: "AI Industry Panorama", exact: true })).toBeVisible();
    await expect(page.locator('nav a[href="/ai-industry-panorama"]')).toHaveAttribute("aria-current", "page");
    await expect(page.locator("#release-id")).toHaveText("ai-industry-panorama.2026-07-24.v1");
    await expect(page.locator("#taxonomy-version")).toHaveText(
      "ai-industry-panorama-taxonomy.2026-07-24.v1",
    );
    await expect(page.locator("#evidence-cutoff")).toHaveText("2026-07-24");
    await expect(page.locator("#change-summary li")).not.toHaveCount(0);
    await expect(page.getByRole("status")).toContainText("Curated start");
    await expectNoPageOverflow(page);

    const curatedIds = await relationshipIds(
      page.locator("#panorama-graph [data-relationship-id]"),
    );
    expect(curatedIds.length).toBeGreaterThan(0);
    expect(curatedIds).toEqual(
      await relationshipIds(page.locator("#relationship-table-body [data-relationship-id]")),
    );

    await page.getByRole("button", { name: "Reset panorama" }).click();
    await expectGraphTableIds(page, completeIds);

    const search = page.getByPlaceholder(
      "Entity, project, standard, capability, or alias",
    );
    await search.fill("Microsoft");
    await expectGraphTableIds(page, microsoftSearchIds);
    const microsoft = page.locator(
      '#panorama-graph [data-entity-id="entity:ENT-ORG-MICROSOFT"]',
    );
    await microsoft.focus();
    await expect(microsoft).toBeFocused();
    await microsoft.press("Enter");
    await expect(page.locator("#entity-drawer")).toBeFocused();
    await expect(page.locator("#entity-drawer")).toContainText("Microsoft Corporation");
    await expectGraphTableIds(page, microsoftHopTwoIds);

    await page.locator("#hop-depth").selectOption("1");
    await expectGraphTableIds(page, microsoftHopOneIds);
    await page.locator("#hop-depth").selectOption("2");
    await expectGraphTableIds(page, microsoftHopTwoIds);

    const assertFilter = async (id: string, value: string, expectedIds: string[]) => {
      await page.getByRole("button", { name: "Reset panorama" }).click();
      await page.locator(id).selectOption(value);
      await expectGraphTableIds(page, expectedIds);
    };
    await assertFilter("#geography-filter", "geography:us", unitedStatesIds);
    await assertFilter("#time-filter", "2026-2027", periodIds);
    await assertFilter("#lifecycle-filter", "committed", committedIds);
    await assertFilter("#lifecycle-filter", "announced", announcedIds);
    await expect(
      page.locator(
        '#relationship-table-body tr[data-relationship-id="relationship:REL-AIP-0019"]',
      ),
    ).toHaveCount(1);
    await page
      .locator(
        '#relationship-table-body tr[data-relationship-id="relationship:REL-AIP-0019"]',
      )
      .getByRole("button", { name: "View evidence" })
      .click();
    await expect(page.locator("#relationship-drawer")).toContainText(
      "Lifecycle: announced",
    );
    await expect(page.locator("#relationship-drawer")).toContainText(
      "United States (project_site)",
    );
    await assertFilter("#geography-role-filter", "project_site", projectSiteIds);
    await assertFilter(
      "#geography-role-filter",
      "equipment_component_manufacturing",
      equipmentManufacturingIds,
    );
    await page.getByRole("button", { name: "Reset panorama" }).click();
    await page.locator("#disclosed-only").check();
    await expectGraphTableIds(page, disclosedIds);
    expect(disclosedIds.length).toBeGreaterThan(0);

    await page.getByRole("button", { name: "Graph", exact: true }).click();
    await expect(page.locator("#graph-panel")).toBeVisible();
    await expect(page.locator("#table-panel")).toBeHidden();
    await page.getByRole("button", { name: "Table", exact: true }).click();
    await expect(page.locator("#graph-panel")).toBeHidden();
    await expect(page.locator("#table-panel")).toBeVisible();
    await page.getByRole("button", { name: "Both", exact: true }).click();

    await page.getByRole("button", { name: "Reset panorama" }).click();
    await search.fill("Advanced semiconductor packaging");
    const capability = page.locator(
      '#panorama-graph [data-entity-id="entity:ENT-CAP-ADVANCED-PACKAGING"]',
    );
    await capability.focus();
    await capability.press(" ");
    await expect(page.locator("#capability-drawer")).toBeFocused();
    await expect(page.locator("#capability-drawer")).toContainText("Advanced semiconductor packaging");

    await page.getByRole("button", { name: "Reset panorama" }).click();
    await search.fill("OCP Open Data Centers for AI");
    const standard = page.locator(
      '#panorama-graph [data-entity-id="entity:ENT-STD-OCP-ODCAI"]',
    );
    await standard.focus();
    await standard.press("Enter");
    await expect(page.locator("#entity-drawer")).toContainText(
      "Entity type: standards_program",
    );
    await expect(page.locator("#entity-drawer")).toContainText(
      "No admitted research or valuation link",
    );
    await expectGraphTableIds(page, [
      "relationship:REL-AIP-0003",
      "relationship:REL-AIP-0007",
      "relationship:REL-AIP-0010",
      "relationship:REL-AIP-0013",
      "relationship:REL-AIP-0025",
      "relationship:REL-AIP-0044",
      "relationship:REL-AIP-0045",
    ]);

    await page.getByRole("button", { name: "Reset panorama" }).click();
    const inferenceRow = page.locator(
      '#relationship-table-body tr[data-relationship-id="relationship:REL-AIP-0011"]',
    );
    await inferenceRow.getByRole("button", { name: "View evidence" }).click();
    const relationshipDrawer = page.locator("#relationship-drawer");
    await expect(relationshipDrawer).toBeFocused();
    await expect(relationshipDrawer).toContainText("Assertion kind: inferred_exposure");
    const metaPremise = relationshipDrawer.locator(
      '[data-premise-assertion-id="assertion:AST-AIP-0010"]',
    );
    const ocpPremise = relationshipDrawer.locator(
      '[data-premise-assertion-id="assertion:AST-AIP-0045"]',
    );
    await expect(metaPremise).toContainText("Meta Investor Relations");
    await expect(metaPremise).toContainText("Meta Reports First Quarter 2026 Results");
    await expect(metaPremise).toContainText("Publication: 2026-04-29");
    await expect(metaPremise.getByRole("link", { name: "Open official source" })).toHaveAttribute(
      "href",
      "https://investor.atmeta.com/investor-news/press-release-details/2026/Meta-Reports-First-Quarter-2026-Results/",
    );
    await expect(ocpPremise).toContainText("Open Compute Project Foundation");
    await expect(ocpPremise).toContainText("Open Data Centers for AI");
    await expect(ocpPremise).toContainText("Publication: Undated");
    await expect(ocpPremise.getByRole("link", { name: "Open official source" })).toHaveAttribute(
      "href",
      "https://www.opencompute.org/community/open-data-centers-for-ai",
    );
    for (const link of await relationshipDrawer.getByRole("link", { name: "Open official source" }).all()) {
      expect(await link.getAttribute("rel")).toBe("noopener noreferrer");
      expect(await link.getAttribute("target")).toBe("_blank");
    }
    expectReadOnlyPanoramaJourney(desktopRequests);
    await testInfo.attach("ai-panorama-desktop", {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });

    const mobileContext = await browser.newContext({
      viewport: { width: 390, height: 844 },
    });
    const mobilePage = await mobileContext.newPage();
    const mobileRequests = observeSameOrigin(mobilePage, baseOrigin);
    await mobilePage.goto("/ai-industry-panorama", { waitUntil: "commit" });
    await expect(mobilePage.locator("body")).toHaveAttribute("data-experience-ready", "true");
    await expect(mobilePage.getByRole("status")).toContainText("Curated start");
    await expectNoPageOverflow(mobilePage);
    const mobileCuratedIds = await relationshipIds(
      mobilePage.locator("#panorama-graph [data-relationship-id]"),
    );
    expect(mobileCuratedIds.length).toBeGreaterThan(0);
    expect(mobileCuratedIds).toEqual(
      await relationshipIds(mobilePage.locator("#relationship-table-body [data-relationship-id]")),
    );
    const graphScroll = mobilePage.locator("#panorama-graph-scroll");
    const scrollSize = await graphScroll.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }));
    expect(scrollSize.scrollWidth).toBeGreaterThan(scrollSize.clientWidth);
    await graphScroll.evaluate((element) => {
      element.scrollLeft = 240;
    });
    await expect.poll(() => graphScroll.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);

    const mobileSearch = mobilePage.getByPlaceholder(
      "Entity, project, standard, capability, or alias",
    );
    await mobileSearch.fill("Microsoft");
    await expectGraphTableIds(mobilePage, microsoftSearchIds);
    const mobileMicrosoft = mobilePage.locator(
      '#panorama-graph [data-entity-id="entity:ENT-ORG-MICROSOFT"]',
    );
    await mobileMicrosoft.focus();
    await mobileMicrosoft.press("Enter");
    await expectGraphTableIds(mobilePage, microsoftHopTwoIds);
    await mobilePage.getByRole("button", { name: "Reset panorama" }).click();
    await mobilePage.locator("#geography-filter").selectOption("geography:us");
    await expectGraphTableIds(mobilePage, unitedStatesIds);
    await expectNoPageOverflow(mobilePage);
    expectReadOnlyPanoramaJourney(mobileRequests);
    await testInfo.attach("ai-panorama-mobile-390", {
      body: await mobilePage.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
    await mobileContext.close();
  });
});
test("Earnings Brief Studio renders and exports a long PNG", async ({ page }) => {
  await page.goto("/earnings-brief-studio", { waitUntil: "load" });
  await expect(page.locator("#status")).toHaveText("已载入审核版本");
  await expect(page.locator('nav a[href="/earnings-brief-studio"]')).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("heading", { name: "Fiscal 2025 Q1 业绩简报" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "01 核心业绩" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "05 前瞻情景" })).toBeVisible();
  await expect(page.locator(".bar")).toHaveCount(2);
  await expect(page.locator(".margin-bar")).toHaveCount(2);
  await expect(page.locator(".mix span")).toHaveCount(5);
  await expect(page.locator('#source-list a[href^="https://"]')).toHaveCount(2);

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 PNG" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("AAPL-FY2025-Q1-earnings-brief-v1.png");
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  const png = Buffer.concat(chunks);
  expect(png.length).toBeGreaterThan(10_000);
  expect(png.subarray(1, 4).toString("ascii")).toBe("PNG");
  expect(png.readUInt32BE(16)).toBe(1440);
  expect(png.readUInt32BE(20)).toBeGreaterThan(2000);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "load" });
  await expect(page.locator("#status")).toHaveText("已载入审核版本");
  expect(
    await page.locator("html").evaluate((element) => element.scrollWidth <= element.clientWidth),
  ).toBe(true);
});
