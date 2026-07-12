# Daily Market Brief Historical Reconstruction Design

Status: approved
Owner: Daily Market Brief Feature Coordinator
Source PRD: `docs/product/PRD-Daily-Market-Brief.md`
Related technical plan: `docs/techplans/daily-market-brief.md`

## Objective

Let the user request a Daily Market Brief for a provider-supported historical
trading date even when no report was generated on that date. The first request
reconstructs the report from date-correct historical market data, saves it
idempotently, and later requests read the saved report immediately.

The same delivery also improves amount readability and uses Chinese display
names for the A-share core indexes.

## Product Behavior

### Historical Dates

- Reading an existing market/date report remains immediate.
- Reading a missing date shows that the date has not been saved and offers
  historical generation.
- Generating a missing historical trading date reconstructs the report from
  historical data for that date. Current spot rankings must never be relabeled
  as historical data.
- The first reconstruction may take 30 seconds to two minutes. The page shows a
  busy state and keeps the selected market/date visible.
- A successful reconstruction is saved through the existing
  market/date-idempotent `review_reports` path. A repeated request refreshes the
  same report rather than creating a duplicate.
- A non-trading date returns an explicit no-session result.
- Provider gaps do not fail the whole report. Each unavailable section records
  a product-language status and the report remains useful from the sections
  that can be reconstructed.

### Available History

The page exposes saved dates for the selected market. Selecting one reads the
saved report. Selecting a date that is not saved keeps the date selected and
offers historical generation instead of silently returning to the latest date.

Historical generation is limited to provider-supported dates and guarded by a
global historical-generation concurrency limit, the existing market/date
single-flight rule, and a cooldown. These guards bound public resource use
without requiring the user to manage a token.

### Readable Amounts

Turnover and flow values are rendered with market currency and a compact
Chinese unit:

| Market | Currency | Examples |
|---|---|---|
| CN | CNY | `50.93 亿元 CNY`, `8234.50 万元 CNY` |
| HK | HKD | `10.23 亿港元 HKD`, `6310.44 万港元 HKD` |
| US | USD | `6.33 亿美元 USD`, `3108.79 万美元 USD` |

Values below ten thousand use the full currency unit. Missing values remain
`-`, and textual explanations remain text. The Web table and generated
Markdown use the same formatter semantics.

### A-Share Index Names

CN user-facing output uses these names while internal codes and provider
symbols remain unchanged:

| Internal name | CN display name |
|---|---|
| Shanghai Composite | 上证指数 |
| Shenzhen Component | 深证成指 |
| CSI 300 | 沪深300 |
| ChiNext Index | 创业板指 |
| STAR 50 | 科创50 |

The Chinese names apply to the table, summary narrative, Markdown, and saved
structured context so all user surfaces remain consistent.

## Reconstruction Architecture

### Core Indexes

Reuse the existing historical bar provider and volume-baseline calculation.
The requested date must be the session date carried by the returned bar. Index
rows with no exact-date bar are marked missing rather than substituted with a
nearby session.

### Individual Gainers

Introduce a historical activity-provider interface separate from the current
spot-provider interface. It receives market and requested date and returns:

- the historical universe basis;
- symbols queried and symbols with usable exact-date data;
- top gainers after the existing security-type and liquidity filters;
- provider and partial-coverage metadata.

The provider uses bounded concurrency and exact-date historical daily bars for
CN, HK, and US. Ranking requires the requested close, previous close, and
requested-date turnover. The report labels partial universe coverage instead
of claiming a complete-market ranking when requests fail or symbol metadata is
insufficient.

### Sectors And Capital Flow

CN historical reconstruction uses provider-supported industry history and
industry fund-flow history when exact-date rows are available. HK and US keep
explicit unavailable states until a provider supplies comparable historical
sector and flow semantics. No price or volume proxy is presented as capital
flow.

### Persistence And Provenance

Saved context adds:

- `generation_kind`: `scheduled_close`, `live_rerun`, or
  `historical_reconstruction`;
- requested market date and exact provider session dates;
- universe basis, requested/usable symbol counts, and partial-coverage status;
- currency for each monetary ranking section;
- source status for indexes, sectors, gainers, and capital flow.

The existing report key remains `daily_market_brief:<market>:<date>:<date>`.

## Web And API Flow

- Add a read-only saved-date endpoint scoped by market.
- Keep the current read endpoint unchanged for existing clients.
- Extend generation with an explicit historical mode selected by the server
  when the requested date precedes the latest completed session.
- Reject future dates and malformed dates.
- Keep current-session generation on the current fast provider path.
- Historical generation may run in a request thread for P0, but it must use a
  bounded timeout and always release concurrency/single-flight guards.
- The page shows `已保存`, `尚未生成`, `正在重建`, `部分数据可用`, and
  `重建失败` as product states without raw provider exceptions.

## Failure Handling

- Exact-date provider mismatch: mark the affected section unavailable.
- Partial symbol failures: return a partial ranking with coverage counts when
  enough rows remain; otherwise mark the ranking unavailable.
- Timeout: do not save a misleading empty report; return recoverable copy and
  release the generation guard.
- Concurrent duplicate: return the in-progress/cooldown state and let the user
  read the saved result when complete.
- Process restart during reconstruction: no incomplete report is committed;
  the user can retry.

## Verification

Implementation follows test-driven development and must cover:

1. Currency formatting boundaries for CN, HK, and US.
2. Chinese CN index names in context, narrative, Markdown, and Web output.
3. Missing historical read keeps the requested date selected.
4. Saved-date listing is market-scoped and ordered newest first.
5. Exact-date historical reconstruction never calls the spot ranking provider.
6. Reconstructed gainers use requested-date and previous-session values.
7. Partial provider coverage is labeled with queried/usable counts.
8. Historical rerun keeps the same saved report ID.
9. CN/HK/US same-date reports continue to coexist.
10. Future/no-session/error/concurrency paths expose safe product copy.
11. Existing current-session generation and scheduler behavior remain green.
12. Cloud acceptance reconstructs `2026-07-09`, reads it back after saving,
    verifies readable currencies and CN index names, and confirms the current
    `2026-07-10` reports remain intact.

## Scope Boundaries

- No paid provider is introduced.
- Historical results are limited by provider coverage and explicitly disclose
  partial universes.
- This change does not normalize sector taxonomies across markets.
- DingTalk push remains out of scope.
- User acceptance remains pending until the deployed page is reviewed by the
  user.
