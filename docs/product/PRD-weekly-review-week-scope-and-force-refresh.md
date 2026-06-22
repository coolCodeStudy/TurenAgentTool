# PRD: Weekly Review Week Scope And Force Refresh

> Status note (2026-06-18): This PRD is kept as historical product context. The accepted current behavior is simpler than several sections below: weekly review stores one report row per natural week; `Force refresh` requires explicit confirmation and then overwrites that same weekly report; there is no `refresh_draft`, compare view, or DB status machine. The current implementation contract is documented in `docs/techplans/weekly-review-week-scope-force-refresh.md`.

## 1. Background

The first version of the weekly review web workbench allows users to generate a review from arbitrary `start/end` dates. That is cheap while the product only uses trades and position snapshots, but it becomes expensive and inconsistent once the product adds indexes, macro calendars, news themes, opportunity lists, and LLM-generated story candidates.

Arbitrary ranges create three problems:

- A user can query ranges such as `6.13-6.17` and `6.13-6.20`, repeatedly triggering data fetches, news searches, and model generation.
- Arbitrary ranges break the product definition of a weekly review, making reports hard to compare across weeks.
- Users may refresh accidentally and burn token budget, external API quota, and time without realizing it.

The weekly review should therefore move from an arbitrary date-range query tool to a fixed-week workbench: generate once, read many times, and run the full pipeline only when the user explicitly requests a force refresh.

## 2. Product Goals

1. A weekly review can only be generated for a fixed week.
2. The same week is generated once by default; later visits read the existing report or draft.
3. The user can explicitly click `Force refresh` to run the full data fetch and story-generation pipeline again.
4. Force refresh must protect user-edited or finalized reports and must never silently overwrite them.
5. The page must clearly show whether the current content is missing, cached, a draft, a finalized report, or a refreshed draft.

## 3. Non-Goals

- Do not support arbitrary free-form date ranges.
- Do not turn the weekly review into a real-time news feed.
- Do not fetch news or spend LLM tokens every time the page opens.
- Do not overwrite a finalized report without explicit user confirmation.

## 4. Week Definition

Use natural weeks by default:

```text
Monday 00:00:00 through Sunday 23:59:59
```

The page and API should use `week_start` as the primary input. `week_start` must be a Monday.

Display format:

```text
2026-W25
2026-06-15 to 2026-06-21
```

If a user chooses any date from a date picker, the system normalizes that date to its natural week. The product does not preserve arbitrary `start/end` values.

## 5. User Stories

### 5.1 Open This Week's Review

As a user, when I open the page, I want to see the current natural week's review state:

- If the week has not been generated, show `Missing` and the primary button `Generate weekly review`.
- If a draft exists, show the draft and data-source status.
- If a finalized report exists, show the finalized report and make any new edits explicit.

### 5.2 View A Historical Week

As a user, when I select `2026-W24`, I want to see the existing review for that week instead of rerunning the pipeline.

### 5.3 Force Refresh

As a user, when I know source data has changed or I want to rerun macro/news/index inputs, I can click `Force refresh`.

The confirmation must say:

```text
This will refetch trades, positions, indexes, macro events, news/theme data, and opportunity lists, then regenerate the story draft.
It will not directly overwrite a finalized report.
```

### 5.4 Protect Finalized Reports

As a user, if I already finalized a report and then click `Force refresh`, the system should create a refreshed draft version so I can compare it before deciding whether to replace the finalized report.

## 6. Page Interaction

### 6.1 Top Controls

Replace `Start date / End date` with `Select week`.

Controls:

| Control | Description |
| --- | --- |
| Previous week | Switch to the previous natural week. |
| This week | Switch to the current natural week. |
| Next week | Allow viewing a future week, but do not generate trading review content by default. |
| Week selector | Accept `YYYY-Www` or any date, then normalize to Monday. |
| Generate weekly review | Show only when no report or draft exists for the week. |
| Force refresh | Show when a report or draft exists; requires confirmation. |
| Save finalized report | Save the current draft as the finalized weekly review. |

### 6.2 Status Bar

The status bar must show:

```text
Review week: 2026-W25
Report status: Missing / Draft / Finalized / Refreshed draft / Stale
Generated at: 2026-06-21 22:15
Last refreshed: 2026-06-22 08:30
Sources: Trades, positions, indexes, macro, news, opportunity lists
LLM: Not used / Story candidates generated
```

### 6.3 Force Refresh Confirmation

Dialog copy:

```text
Force refresh 2026-W25?

The system will rerun the full pipeline:
- Backfill trades and position snapshots
- Fetch index data
- Fetch macro calendar events
- Fetch news/theme heat
- Fetch opportunity lists
- Regenerate the overall story draft

If a finalized report already exists, this result will be saved as a refreshed draft and will not directly overwrite the finalized report.
```

Buttons:

```text
Cancel
Confirm force refresh
```

## 7. Backend Behavior

### 7.1 Normal Read

Request:

```text
GET /api/weekly-review?week=2026-W25
```

Flow:

1. Parse `week` into `week_start/week_end`.
2. Query `review_reports` for an existing report for that week.
3. If one exists, return it without triggering external providers or LLM generation.
4. If none exists, return `status=missing` so the frontend can show `Generate weekly review`.

### 7.2 First Generation

Request:

```text
POST /api/weekly-review/generate
{
  "week": "2026-W25"
}
```

Flow:

1. If a draft or finalized report already exists for the week, return the existing content by default.
2. If no report exists, run the full generation pipeline.
3. Save the result as `draft`.
4. Return the draft, source status, and estimated generation cost.

### 7.3 Force Refresh

Request:

```text
POST /api/weekly-review/refresh
{
  "week": "2026-W25",
  "force": true
}
```

Flow:

1. Bypass the weekly report cache.
2. Pass `refresh=true` to external sources.
3. Run the full pipeline again.
4. If no finalized report exists, overwrite or update the current automatic draft.
5. If a finalized report exists, create a `refresh_draft` and do not overwrite the finalized report.
6. Record refresh reason, refresh time, and source payload versions.

## 8. Data Model Recommendations

### 8.1 `review_reports`

Recommended fields:

```text
report_type      weekly
period_start     Monday date
period_end       Sunday date
status           draft / finalized / refresh_draft / archived
version          Version number within the same week
generated_at
refreshed_at
finalized_at
generation_mode  initial / force_refresh / manual_edit
token_usage      JSONB
source_status    JSONB
portfolio_snapshot JSONB
summary          Markdown
```

Recommended uniqueness:

```text
UNIQUE(report_type, period_start, status)
```

For a stricter model, split versions into a separate table so there can be only one finalized report per week.

### 8.2 `weekly_review_sources`

New cache table:

```text
week_start
week_end
source_type      trades / positions / indexes / macro / news / opportunities
source_key       Provider name or query key
payload          JSONB
fetched_at
expires_at
refresh_run_id
error
```

Uses:

- Avoid refetching external data when the same week is opened repeatedly.
- Create a new `refresh_run_id` during force refresh.
- Make the overall story traceable to concrete source payloads.

### 8.3 `weekly_review_runs`

Record each generation or refresh run:

```text
id
week_start
mode             initial / force_refresh
status           running / succeeded / failed
started_at
finished_at
duration_ms
token_usage
source_counts
error
```

## 9. Story Source Strategy

The weekly review story must be built from traceable evidence. It should not be a generic AI-written market summary. The story engine should combine four source families: macro calendar, market behavior, market-theme news, and opportunity lists.

### 9.1 Macro Calendar Sources

Macro events explain the market backdrop and the next week's risk windows.

Preferred P1 sources:

| Source | Use | Notes |
| --- | --- | --- |
| Federal Reserve FOMC calendar | FOMC meetings, SEP windows, rate-decision timing | Official source. Use for current and next-week event flags. |
| BLS release calendar | CPI, PPI, payrolls, JOLTS, unemployment, wage data | Official source. Prefer calendar/ICS-style ingestion when available. |
| BEA release schedule | GDP, PCE, corporate profits, international accounts | Official source. |
| Trading Economics API | Paid/optional unified economic calendar | Optional enhancement when an API token is available. |

Output shape:

```json
{
  "source_type": "macro",
  "events": [
    {
      "date": "2026-06-17",
      "region": "US",
      "title": "FOMC rate decision",
      "importance": "high",
      "why_it_matters": "Affects USD rates, risk appetite, and long-duration growth assets.",
      "source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
    }
  ]
}
```

Macro events should be split into:

- Events that happened during the review week.
- Events scheduled for the next two weeks.
- Events that directly map to portfolio exposures such as AI infrastructure, semiconductors, Hong Kong growth stocks, rates-sensitive growth, or commodities.

### 9.2 Market Behavior Sources

Market behavior is the price and flow evidence that confirms or weakens a story.

Preferred P1 source:

| Source | Use | Notes |
| --- | --- | --- |
| Futu OpenD `request_history_kline` | Weekly index and stock performance, max daily move | Use for indexes, held stocks, and key theme tickers. |
| Futu OpenD `get_market_snapshot` | Current quote snapshot and index snapshot | Use for latest state and validation. |
| Futu OpenD `get_capital_flow` | Stock-level capital flow | Use as supporting evidence only, not as a standalone conclusion. |
| Futu OpenD `get_plate_stock` | Plate/sector member lists where available | Use to map market themes to stock baskets. |

Market behavior outputs:

```json
{
  "source_type": "market_behavior",
  "themes": [
    {
      "theme": "AI memory / HBM",
      "confirming_tickers": ["US.MU", "KR.000660", "HK.07709"],
      "weekly_move_summary": "Theme basket outperformed broad indexes.",
      "capital_flow_signal": "mixed",
      "confidence": "medium"
    }
  ]
}
```

The story builder should treat market behavior as evidence, not as the story itself. A theme is stronger when news heat, price action, and portfolio exposure point in the same direction.

### 9.3 Market Theme News Sources

Market-theme news should answer: which narratives were active this week, and which of them matter to the user's portfolio?

Preferred P1 source:

| Source | Use | Notes |
| --- | --- | --- |
| GDELT DOC 2.0 API | Global news search, article list, timeline, multilingual coverage | Use for theme heat and source links. Do not feed full articles into the LLM by default. |

Optional P2 sources:

| Source | Use | Notes |
| --- | --- | --- |
| Xueqiu | Chinese investor sentiment and retail narrative | Use only through a controlled provider with cookies or user-approved import. Keep source URLs. |
| Tonghuashun | A-share theme and hot-sector narrative | Treat as optional and fragile; avoid making it a core dependency. |
| WeChat public articles | Long-form Chinese narrative and channel checks | Prefer manual/user-approved import or search-result summaries. |
| Yahoo Finance / Google News / official company news | Ticker-level news discovery | Use as fallback evidence sources. |

The first implementation should avoid a general web crawler. Use a theme dictionary and source-specific queries.

Initial theme dictionary:

| Theme | Query terms | Portfolio relevance |
| --- | --- | --- |
| AI memory / HBM | `HBM`, `DRAM price`, `NAND`, `memory price`, `SK hynix`, `Micron` | MU, SK hynix exposure, leveraged memory products, AI infrastructure. |
| MLCC / passive components | `MLCC`, `passive components`, `Murata`, `Yageo` | Electronics supply-chain cycle and component-price narratives. |
| Glass substrate / advanced packaging | `glass substrate`, `advanced packaging`, `chip packaging` | Semiconductor packaging and AI accelerator supply chain. |
| Optical modules / CPO | `CPO`, `optical module`, `silicon photonics`, `800G`, `1.6T` | Optical communication and AI data-center networking names. |
| Hong Kong growth | `Alibaba`, `Meituan`, `Xiaomi`, `Hang Seng Tech`, `Southbound` | Hong Kong growth holdings and sentiment. |
| High-volatility themes | `space`, `quantum`, `crypto finance`, `Circle`, `Rocket Lab` | Speculative US growth and high-volatility holdings. |

Theme output shape:

```json
{
  "source_type": "theme_news",
  "themes": [
    {
      "theme": "AI memory / HBM",
      "article_count": 18,
      "previous_article_count": 9,
      "heat_change": "up",
      "top_evidence": [
        {
          "title": "Memory pricing story example",
          "publisher": "Example Publisher",
          "published_at": "2026-06-16",
          "url": "https://example.com/story"
        }
      ],
      "portfolio_relevance": ["US.MU", "KR.000660", "HK.07709"],
      "confidence": "medium"
    }
  ]
}
```

The weekly review must not paste full news articles into prompts. It should pass only title, publisher, date, short extracted fact, URL, theme tag, and relevance.

### 9.4 Opportunity List Sources

Opportunity lists are rules-based events where a list changes or an index window opens. They should be generated through list snapshots and diffs instead of narrative scraping.

Preferred sources:

| Source | Use | Notes |
| --- | --- | --- |
| SSE/SZSE Stock Connect eligible securities lists | Southbound Stock Connect additions/removals | Store daily snapshots and compute diffs. |
| Nasdaq-100 official methodology and official announcements | Reconstitution and rebalance windows, additions/removals | Track official announcement windows and diff constituent lists where possible. |
| Futu IPO data | Hong Kong IPO subscription/listing calendar | Already aligned with the current weekly-review data path. |

Output shape:

```json
{
  "source_type": "opportunities",
  "items": [
    {
      "category": "stock_connect",
      "title": "Potential Southbound Stock Connect list change",
      "effective_date": "2026-06-24",
      "affected_symbols": ["HK.XXXXX"],
      "portfolio_relevance": "May affect liquidity and southbound fund access.",
      "source_url": "https://www.sse.com.cn/services/hkexsc/disclo/eligible/"
    }
  ]
}
```

Opportunity items should be classified as:

- Confirmed: official list or announcement already changed.
- Watch window: official methodology says a rebalance or review window is approaching.
- Rumor/news-only: present only if there is clear source attribution and low-confidence labeling.

### 9.5 Story Builder Rules

The overall story section should use a fixed evidence hierarchy:

1. Portfolio facts: trades, position changes, highlights, blowups, current holdings.
2. Index and market behavior: broad market, sector/index baskets, key theme tickers.
3. Macro calendar: this week's events and next two weeks' risk windows.
4. Theme news: article count, heat change, top evidence links.
5. Opportunity lists: Stock Connect, Nasdaq-100, IPO, and other list/rebalance events.
6. User memory: confirmed insights and candidate insights.

The story output should remain structured:

```text
Main line:
Acceleration factors:
Negative signals:
Relationship to my portfolio:
Next-week validation points:
Evidence:
```

Rules:

- At least two evidence families must support a generated story candidate.
- If only one evidence family exists, label the story as weak or incomplete.
- If external sources are missing, explicitly say which source is missing.
- Theme confidence should be `high`, `medium`, or `low`, based on source count, market confirmation, and portfolio relevance.
- The LLM may synthesize wording, but it must not invent facts or cite sources that are not in the source payload.

### 9.6 References

- Federal Reserve FOMC calendar: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`
- BLS release calendar: `https://www.bls.gov/schedule/news_release/`
- BEA release schedule: `https://www.bea.gov/news/schedule`
- Trading Economics API: `https://tradingeconomics.com/api/`
- Futu historical Kline: `https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html`
- Futu market snapshot: `https://openapi.futunn.com/futu-api-doc/en/quote/get-market-snapshot.html`
- Futu capital flow: `https://openapi.futunn.com/futu-api-doc/en/quote/get-capital-flow.html`
- Futu plate stocks: `https://openapi.futunn.com/futu-api-doc/en/quote/get-plate-stock.html`
- GDELT DOC 2.0 API: `https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/`
- SSE Stock Connect eligible securities: `https://www.sse.com.cn/services/hkexsc/disclo/eligible/`
- Nasdaq-100 methodology: `https://indexes.nasdaqomx.com/docs/Methodology_NDX.pdf`

## 10. Generation Flow

Full pipeline:

```text
1. Parse week
2. Read or backfill trades
3. Read or backfill account and position snapshots
4. Fetch index data
5. Fetch macro calendar events
6. Fetch market-theme news and theme heat
7. Fetch opportunity lists
8. Build the fact board
9. Generate overall story candidates
10. Render the Markdown draft
11. Save draft or refresh_draft
```

Opening the page normally only does:

```text
1. Parse week
2. Read existing report
3. Return
```

## 11. Cost Control

Default behavior:

| Scenario | Fetch external data | Call LLM |
| --- | --- | --- |
| Open existing weekly review | No | No |
| Generate the week for the first time | Yes | Depends on configuration |
| Save finalized report | No | No |
| Force refresh | Yes | Yes |
| View historical week | No | No |

Force refresh should record cost:

```json
{
  "input_tokens": 12000,
  "output_tokens": 1800,
  "provider": "openai",
  "model": "...",
  "source_fetch_seconds": 18,
  "llm_seconds": 24
}
```

## 12. Acceptance Criteria

1. The page no longer exposes arbitrary `start/end` date inputs.
2. When the user selects any date, the system normalizes it to the natural week.
3. Opening an already-generated weekly review does not trigger external providers.
4. The `Force refresh` button requires confirmation.
5. Force refresh reruns the full pipeline.
6. A finalized report is never silently overwritten by force refresh.
7. Every report version for a week is traceable to its source payloads and generation run.
8. The UI clearly shows report status, generated time, refreshed time, and source status.

## 13. Implementation Priority

### P0

- Change the web page from date range selection to week selection.
- Add unified backend week parsing.
- Read an existing report by default when one exists for the same week.
- Add `Force refresh` button and confirmation dialog.
- Save force-refresh output as `draft` or `refresh_draft`.

### P1

- Add `weekly_review_runs`.
- Add `weekly_review_sources`.
- Add index provider integration.
- Add macro calendar provider using Fed, BLS, and BEA official sources.
- Add Futu OpenD market-behavior evidence for key indexes and theme tickers.
- Show cache/refresh state in source status.

### P2

- Add market theme provider using a theme dictionary and GDELT news heat.
- Add opportunity list provider for Stock Connect, Nasdaq-100 windows, and IPOs.
- Add optional paid Trading Economics integration.
- Show token/time cost.

### P3

- Add draft version comparison.
- Add finalized report replacement approval.
- Add optional Xueqiu, Tonghuashun, and WeChat import providers with source URLs and confidence labels.
- Close the loop for accepting, rejecting, and converting story candidates into user insights.
