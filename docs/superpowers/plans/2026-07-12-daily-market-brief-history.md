# Daily Market Brief Historical Reconstruction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add date-correct historical Daily Market Brief reconstruction and persistence, readable market-currency amounts, saved-date navigation, and Chinese A-share index names.

**Architecture:** Keep current-session spot generation unchanged and add a separate historical activity provider that ranks exact-date daily bars under bounded concurrency. Route historical Web generation through the existing idempotent report upsert and generation gate, expose saved dates through a read-only endpoint, and render amounts through one market-aware formatter shared by Markdown semantics and the Web page.

**Tech Stack:** Python 3.11, standard-library HTTP server and concurrency primitives, PostgreSQL/psycopg repository helpers, AKShare historical daily APIs, existing Yahoo index-bar provider, inline HTML/CSS/JavaScript Web surface, `unittest`.

## Global Constraints

- Current spot rankings must never be relabeled as historical data.
- First-time historical generation may take 30 seconds to two minutes.
- No paid provider is introduced.
- Public historical generation must keep single-flight, cooldown, bounded concurrency, and timeout controls.
- HK/US historical sector and capital-flow gaps remain explicit until comparable providers exist.
- A repeated market/date generation updates the existing report ID.
- User-facing errors must not expose raw provider, SSL, stack-trace, database, or filesystem details.
- User acceptance remains pending until deployed cloud verification is complete and the user explicitly accepts.

---

### Task 1: Display Semantics And Currency Formatting

**Files:**
- Modify: `investment_knowledge_mcp/daily_market_brief.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Test: `tests/test_daily_market_brief.py`

**Interfaces:**
- Produces: `format_market_amount(value: Any, market: str) -> str`
- Produces: CN `MarketConfig.index_configs` with Chinese display names and unchanged codes.
- Consumes: `context["market"]["code"]` in Web rank rendering.

- [ ] **Step 1: Write failing tests for CN index names and amount boundaries**

```python
def test_cn_indexes_use_chinese_display_names(self) -> None:
    result = dmb.build_daily_market_brief(
        market="CN", market_date=date(2026, 7, 9), save=False,
        market_bar_loader=fake_market_bar_loader, use_fixture=True,
        now=datetime(2026, 7, 9, 18, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    self.assertEqual(
        ["上证指数", "深证成指", "沪深300", "创业板指", "科创50"],
        [row["name"] for row in result.context["indexes"]],
    )
    self.assertIn("上证指数", result.markdown)
    self.assertNotIn("Shanghai Composite", result.markdown)

def test_format_market_amount_uses_currency_and_chinese_units(self) -> None:
    self.assertEqual("50.93 亿元 CNY", dmb.format_market_amount(5_093_000_000, "CN"))
    self.assertEqual("6310.44 万港元 HKD", dmb.format_market_amount(63_104_400, "HK"))
    self.assertEqual("6.33 亿美元 USD", dmb.format_market_amount(633_303_877.53, "US"))
    self.assertEqual("-", dmb.format_market_amount(None, "US"))
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `.venv/bin/python -m unittest tests.test_daily_market_brief.DailyMarketBriefTests.test_cn_indexes_use_chinese_display_names tests.test_daily_market_brief.DailyMarketBriefTests.test_format_market_amount_uses_currency_and_chinese_units`

Expected: failures because CN names are English and `format_market_amount` does not exist.

- [ ] **Step 3: Add the market-aware formatter and Chinese names**

```python
MARKET_CURRENCIES = {
    "CN": {"code": "CNY", "unit": "元"},
    "HK": {"code": "HKD", "unit": "港元"},
    "US": {"code": "USD", "unit": "美元"},
}

def format_market_amount(value: Any, market: str) -> str:
    number = _number(value)
    if number is None:
        return "-"
    currency = MARKET_CURRENCIES[_normalize_market(market)]
    absolute = abs(number)
    if absolute >= 100_000_000:
        return f"{number / 100_000_000:.2f} 亿{currency['unit']} {currency['code']}"
    if absolute >= 10_000:
        return f"{number / 10_000:.2f} 万{currency['unit']} {currency['code']}"
    return f"{number:.2f} {currency['unit']} {currency['code']}"
```

Change the five CN index `name` values to the approved Chinese names. Pass market code into Markdown rank rendering and add equivalent `formatMarketAmount(value, market)` JavaScript for the Web `成交额/说明` column.

- [ ] **Step 4: Run the complete Daily Market Brief test module**

Run: `.venv/bin/python -m unittest tests.test_daily_market_brief`

Expected: all tests pass after updating assertions that intentionally expected the old CN English names.

- [ ] **Step 5: Commit the display deliverable**

```bash
git add investment_knowledge_mcp/daily_market_brief.py investment_knowledge_mcp/weekly_review_web.py tests/test_daily_market_brief.py
git commit -m "feat: improve daily brief market display"
```

### Task 2: Saved-Date Repository And API

**Files:**
- Modify: `investment_knowledge_mcp/repository.py`
- Modify: `investment_knowledge_mcp/daily_market_brief.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Test: `tests/test_daily_market_brief.py`

**Interfaces:**
- Produces: `repository.list_daily_market_brief_dates(market: str, limit: int = 120) -> list[str]`
- Produces: `GET /api/daily-market-brief/dates?market=CN` returning `{"ok": true, "market": "CN", "dates": [...]}`.

- [ ] **Step 1: Add failing fake-repository and response tests**

```python
def list_daily_market_brief_dates(self, *, market: str, limit: int = 120) -> list[str]:
    dates = sorted((day for row_market, day in self.rows if row_market == market), reverse=True)
    return dates[:limit]

def test_saved_dates_are_market_scoped_and_newest_first(self) -> None:
    self.fake_repository.rows[("CN", "2026-07-09")] = {"id": 1, "report_date": "2026-07-09"}
    self.fake_repository.rows[("CN", "2026-07-10")] = {"id": 2, "report_date": "2026-07-10"}
    self.fake_repository.rows[("HK", "2026-07-10")] = {"id": 3, "report_date": "2026-07-10"}
    self.assertEqual(["2026-07-10", "2026-07-09"], dmb.list_daily_market_brief_dates("CN"))
```

- [ ] **Step 2: Verify the test fails for the missing domain function**

Run: `.venv/bin/python -m unittest tests.test_daily_market_brief.DailyMarketBriefTests.test_saved_dates_are_market_scoped_and_newest_first`

Expected: `AttributeError` for `list_daily_market_brief_dates`.

- [ ] **Step 3: Implement the repository query and domain wrapper**

```python
def list_daily_market_brief_dates(market: str, limit: int = 120) -> list[str]:
    normalized_market = market.strip().upper()
    with transaction() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT report_date
            FROM review_reports
            WHERE report_type = 'daily_market_brief'
              AND portfolio_snapshot->'market'->>'code' = %s
            ORDER BY report_date DESC
            LIMIT %s
            """,
            (normalized_market, max(1, min(int(limit), 366))),
        ).fetchall()
    return [row["report_date"].isoformat() if hasattr(row["report_date"], "isoformat") else str(row["report_date"]) for row in rows]
```

Add the domain wrapper in `daily_market_brief.py` and a read-only handler branch in `weekly_review_web.py`.

- [ ] **Step 4: Add HTML contract assertions**

Assert the page contains `/api/daily-market-brief/dates`, a saved-date selector or datalist, and copy distinguishing `已保存` from `尚未生成`. Run the full Daily Market Brief tests and expect PASS.

- [ ] **Step 5: Commit the saved-date deliverable**

```bash
git add investment_knowledge_mcp/repository.py investment_knowledge_mcp/daily_market_brief.py investment_knowledge_mcp/weekly_review_web.py tests/test_daily_market_brief.py
git commit -m "feat: expose saved daily brief dates"
```

### Task 3: Historical Activity Provider

**Files:**
- Create: `investment_knowledge_mcp/daily_market_history.py`
- Modify: `investment_knowledge_mcp/daily_market_brief.py`
- Test: `tests/test_daily_market_history.py`

**Interfaces:**
- Produces: `HistoricalActivityResult` dataclass with `sectors`, `gainers`, `capital_flow`, and `source_status`.
- Produces: `load_historical_market_activity(market: str, market_date: date, *, akshare_module: Any | None = None, max_workers: int = 4, timeout_seconds: float = 90.0) -> HistoricalActivityResult`.
- Produces: `HistoricalActivityProvider = Callable[[str, date], HistoricalActivityResult]`.
- Consumes: normalized spot symbol/name metadata only as a universe; all ranking values come from exact-date historical bars.

- [ ] **Step 1: Write failing exact-date ranking tests with a fake AKShare module**

```python
def test_cn_historical_gainers_rank_exact_date_bars(self) -> None:
    fake = FakeHistoricalAkshare(
        universe=[{"代码": "000001", "名称": "甲"}, {"代码": "000002", "名称": "乙"}],
        histories={
            "000001": [{"日期": "2026-07-08", "收盘": 10, "成交额": 80_000_000}, {"日期": "2026-07-09", "收盘": 11, "成交额": 90_000_000}],
            "000002": [{"日期": "2026-07-08", "收盘": 10, "成交额": 90_000_000}, {"日期": "2026-07-09", "收盘": 12, "成交额": 100_000_000}],
        },
    )
    result = load_historical_market_activity("CN", date(2026, 7, 9), akshare_module=fake, max_workers=1)
    self.assertEqual("000002", result.gainers[0]["code"])
    self.assertEqual(20.0, result.gainers[0]["change_pct"])
    self.assertEqual(100_000_000, result.gainers[0]["turnover"])
    self.assertEqual("2026-07-09", result.gainers[0]["session_date"])
```

Also test that a history ending on `2026-07-10` cannot satisfy a `2026-07-09` request without an exact row, partial coverage records queried/usable counts, and HK/US sectors/flow remain explicitly unavailable.

- [ ] **Step 2: Run the new test module and verify RED**

Run: `.venv/bin/python -m unittest tests.test_daily_market_history`

Expected: import failure because `daily_market_history.py` does not exist.

- [ ] **Step 3: Implement bounded historical ranking**

Create the dataclass and provider. Use `ThreadPoolExecutor(max_workers=max_workers)`, a monotonic deadline, and market adapters:

```python
def _rank_exact_date_history(rows: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    normalized = sorted((_normalize_history_row(row) for row in rows), key=lambda row: row["date"])
    position = next((idx for idx, row in enumerate(normalized) if row["date"] == target.isoformat()), None)
    if position is None or position == 0:
        return None
    current, previous = normalized[position], normalized[position - 1]
    if not previous["close"]:
        return None
    return {
        "change_pct": (current["close"] - previous["close"]) / previous["close"] * 100,
        "turnover": current.get("turnover"),
        "session_date": current["date"],
    }
```

CN uses `stock_zh_a_hist(symbol=..., period="daily", start_date=..., end_date=..., adjust="")`; HK uses `stock_hk_hist` with the same date arguments; US uses `stock_us_hist(symbol=..., period="daily", start_date=..., end_date=..., adjust="")` with the exact provider code from `stock_us_spot_em()` such as `105.MSFT`, not a bare ticker. Apply existing turnover and security-name filters before selecting five rows. Default to four total workers and no more than two concurrent requests per Eastmoney host; add bounded retry for rate-limit, connection, JSON, and empty-response failures. Never call the existing spot ranking provider for ranking values.

- [ ] **Step 4: Run provider and existing tests**

Run: `.venv/bin/python -m unittest tests.test_daily_market_history tests.test_daily_market_brief`

Expected: PASS with no live network dependency.

- [ ] **Step 5: Commit the historical provider**

```bash
git add investment_knowledge_mcp/daily_market_history.py investment_knowledge_mcp/daily_market_brief.py tests/test_daily_market_history.py
git commit -m "feat: reconstruct historical market activity"
```

### Task 4: Historical Generation, Persistence, And Web Flow

**Files:**
- Modify: `investment_knowledge_mcp/daily_market_brief.py`
- Modify: `investment_knowledge_mcp/weekly_review_web.py`
- Modify: `tests/test_daily_market_brief.py`

**Interfaces:**
- Extends: `build_daily_market_brief(..., historical_activity_provider: HistoricalActivityProvider | None = None)`.
- Produces: `context["generation_kind"] == "historical_reconstruction"` for prior sessions.
- Extends: public POST generation to accept prior trading dates while still rejecting future dates.

- [ ] **Step 1: Add failing integration tests**

```python
def test_historical_generation_uses_historical_provider_and_saves(self) -> None:
    calls = []
    def historical_provider(market: str, market_date: date) -> HistoricalActivityResult:
        calls.append((market, market_date))
        return HistoricalActivityResult(
            sectors=[],
            gainers=[{
                "rank": 1, "code": "000001", "name": "历史样本",
                "change_pct": 10.0, "turnover": 100_000_000,
                "provider": "fixture_history", "session_date": market_date.isoformat(),
            }],
            capital_flow=[],
            source_status={
                "sectors": {"status": "historical_not_supported", "count": 0},
                "gainers": {"status": "ok", "count": 1, "queried": 1, "usable": 1},
                "capital_flow": {"status": "historical_not_supported", "count": 0},
            },
        )
    result = dmb.build_daily_market_brief(
        "CN", date(2026, 7, 9), save=True,
        now=datetime(2026, 7, 11, 18, 0, tzinfo=SG_TZ),
        market_bar_loader=fake_market_bar_loader,
        historical_activity_provider=historical_provider,
    )
    self.assertEqual([("CN", date(2026, 7, 9))], calls)
    self.assertEqual("historical_reconstruction", result.context["generation_kind"])
    self.assertEqual("2026-07-09", result.context["gainers"][0]["session_date"])
```

Add tests that the same historical date preserves report ID, current-session generation still calls the spot provider, future dates fail, weekends produce no-session state, and a provider timeout does not save an empty report.

- [ ] **Step 2: Verify RED**

Run the new named tests. Expected: signature failure and the existing historical-save guard raises `ValueError`.

- [ ] **Step 3: Split current and historical generation paths**

Remove the blanket prohibition on saving historical dates. Resolve generation kind first:

```python
latest_completed = resolve_latest_completed_session_date(config.code, now=generated_at)
generation_kind = "historical_reconstruction" if resolved_date < latest_completed else "live_rerun"
if resolved_date > latest_completed:
    raise ValueError(f"未来日期不可生成；最近已收盘交易日为 {latest_completed.isoformat()}。")
```

Call the historical provider only for historical reconstruction and copy its exact-date provenance into `source_status`. Save only after the context passes a validation function requiring exact requested session dates for every non-empty historical section.

- [ ] **Step 4: Extend the generation gate and Web states**

Keep the per-market/date lease and add one global historical lease. Historical requests return safe `429` copy when another reconstruction is active. Change page copy to `正在重建历史简报...`, preserve the selected missing date, refresh saved dates after success, and render `generation_kind` as `历史重建` or `收盘生成`.

- [ ] **Step 5: Run the full feature test module**

Run: `.venv/bin/python -m unittest tests.test_daily_market_history tests.test_daily_market_brief`

Expected: PASS, including existing current-session and scheduler cases.

- [ ] **Step 6: Commit the integrated feature**

```bash
git add investment_knowledge_mcp/daily_market_brief.py investment_knowledge_mcp/weekly_review_web.py tests/test_daily_market_brief.py
git commit -m "feat: generate saved historical daily briefs"
```

### Task 5: Delivery State, Review, Deploy, And Cloud Acceptance

**Files:**
- Modify: `docs/product/PRD-Daily-Market-Brief.md`
- Modify: `docs/techplans/daily-market-brief.md`
- Modify: `docs/project-management/Feature-Registry.md`
- Modify: `docs/project-management/Acceptance-Queue.md`
- Modify: `docs/project-management/Delivery-Queue.md`

**Interfaces:**
- Produces: pushed implementation branch and PR.
- Produces: classified deployment intent and cloud acceptance evidence for `2026-07-09`.

- [ ] **Step 1: Update durable product and technical traceability**

Record the approved historical-reconstruction behavior, readable currency units, CN names, provider-coverage disclosure, implementation evidence, and user acceptance remaining pending.

- [ ] **Step 2: Run complete verification**

```bash
.venv/bin/python -m unittest tests.test_daily_market_history tests.test_daily_market_brief
.venv/bin/python -m unittest discover -s tests
.venv/bin/python -m py_compile investment_knowledge_mcp/daily_market_history.py investment_knowledge_mcp/daily_market_brief.py investment_knowledge_mcp/weekly_review_web.py investment_knowledge_mcp/repository.py
.venv/bin/python scripts/audit_delivery_state.py --feature "Daily market brief"
git diff --check
```

Expected: all tests and audits pass.

- [ ] **Step 3: Request code review and fix accepted findings**

Review exact-date provenance, public-resource bounds, persistence semantics, product copy, currency correctness, and regressions in current-session generation.

- [ ] **Step 4: Push, create PR, merge, and classify deployment**

Expected classification: `targeted_quick` because Python runtime and docs change without image/dependency input changes. Deploy targets must include `weekly-review-web` and `daily-market-brief-scheduler`; PostgreSQL is not recreated.

- [ ] **Step 5: Run cloud acceptance**

From the production Web/API surface:

1. Generate CN `2026-07-09`; confirm five Chinese index names, exact date, readable CNY turnover, saved ID, and safe partial historical states.
2. Read CN `2026-07-09` again; confirm the same ID.
3. Generate/read HK and US `2026-07-09`; confirm exact-date indexes/gainers when available and explicit unsupported sections.
4. Confirm saved-date lists are market-scoped and include `2026-07-09` and `2026-07-10`.
5. Confirm existing `2026-07-10` report IDs `#19/#20/#21` are not overwritten.
6. Check desktop and mobile page rendering, raw-error/advice scans, scheduler health, and cloud system health.

- [ ] **Step 6: Close coordinator state without marking user acceptance**

Move independent acceptance to passed only when evidence supports it. Set feature state to `ready_for_user_acceptance`, commit/push the state-only change as `no_deploy`, and give the user the production page for final review.
