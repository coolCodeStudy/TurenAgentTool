# Kline Agent V1 Technical Plan

## Scope

Implement bounded V1 single-stock Kline investigation for command/CLI use. V1 is read-only, does not place or prepare trades, does not emit buy/sell/hold instructions, and uses only deterministic pattern rules.

V1 covers:

- One explicit stock target per request.
- Daily bars fetched through the historical-bar provider abstraction: approved remote/cloud Futu when explicitly configured, and a no-credential Yahoo chart path for common U.S. stocks such as `US.NVDA`.
- Weekly and monthly bars derived from validated daily bars.
- Fixed daily/weekly/monthly rule library covering new highs, failed breakouts, moving average state, volume-price behavior, gaps, streaks, and drawdown/recovery.
- Source metadata, data quality warnings, deterministic observations, sample statistics, interpretation, watch items, and evidence limits in separate report sections.
- Useful insufficient-evidence output when provider data, bar count, or historical samples are weak.

Out of scope for this branch:

- Trading actions, order preparation, direct buy/sell/hold instructions.
- Portfolio/watchlist scans.
- Decision-card or weekly-review embedding.
- Database schema/cache for bars, runs, or observations.
- LLM-generated chart pattern discovery.
- AkShare fallback dependency. V1 keeps a provider abstraction so fallback can be added later without changing the report contract.
- Local FutuD/OpenD setup or login. Local Futu remains forbidden; approved remote/cloud Futu is allowed when the deployed environment already provides it.

## Entry Points

- Add `investment_knowledge_mcp/kline_agent.py` as the focused implementation module.
- Add command-router support for:
  - `K线 US.NVDA`
  - `K线 HK.00700`
  - `K线 000660 KR`
  - `K线调查 US.NVDA 5年 前复权`
- `scripts/ikg.py` already routes through `handle_command(...)`, so no separate CLI script is needed.

## Provider Design

Define a narrow historical OHLCV provider interface:

- Input: `symbol`, `market`, `years`, `adjust_type`.
- Output: normalized daily bars plus provider metadata and warnings.

Provider routing:

- `FutuHistoricalBarProvider` uses `futu.OpenQuoteContext.request_history_kline`.
- Provider symbols use Futu-style market prefixes: `US.NVDA`, `HK.00700`, `KR.000660`, `SH.600000`, or `SZ.000001`.
- Adjustment mapping:
  - raw: provider `AuType.NONE` when available.
  - forward-adjusted: provider `AuType.QFQ` when available.
  - backward-adjusted: provider `AuType.HFQ` when available.
- Provider unavailability, missing `futu-api`, OpenD connection errors, permission errors, and unsupported API versions return clear provider limitations instead of fabricated analysis.
- `YahooChartHistoricalBarProvider` is the no-credential U.S. daily OHLCV path. It maps `US.NVDA` to Yahoo symbol `NVDA`, fetches daily chart bars, applies adjusted-close ratio to OHLC for provider-equivalent adjusted output when requested, and emits a visible warning because Yahoo does not expose separate forward/backward OHLC adjustment series.
- `_default_historical_bar_provider()` uses `KLINE_PROVIDER=auto` by default. `auto` routes U.S. symbols to Yahoo chart so common U.S. stocks can produce useful V1 reports without local FutuD/OpenD. `KLINE_PROVIDER=futu` remains an explicit approved remote/cloud Futu path; `KLINE_PROVIDER=disabled` remains available for fixture/degraded local review.
- Command Workbench execution must call the normal command router for Kline commands. It must not force `disable_kline_live_provider=True` on the deployed `/command` surface, because that prevents approved live providers from producing real bars.

V1 derives weekly/monthly bars from daily bars. This keeps all timeframe statistics reproducible from one visible source and avoids cross-provider aggregation drift in the first version.

## Data Quality

Validate normalized bars before rule evaluation:

- Duplicate dates produce warnings and keep the first normalized bar.
- Impossible OHLC values produce warnings and drop the invalid bar.
- Non-positive OHLC values produce warnings and drop the invalid bar.
- Missing date gaps are summarized as possible holidays or missing provider data.
- Latest same-day bar is warned as possibly incomplete.
- Low bar count is reported as insufficient evidence.

Every report displays provider, provider symbol, market, currency, timezone, requested date range, actual date range, adjustment type, fetch time, raw bar count, normalized bar count, and data-quality warnings.

## Deterministic Rules

Rules are hard-coded with explicit trigger conditions. They never ask an LLM to infer patterns.

Daily rules:

- 52-week high.
- Failed breakout after a recent 52-week high.
- Moving-average break/reclaim/distance for 20d and 60d.
- High-volume up/down day, volume breakout/stalling.
- Gap up/down, fill, and persistence.
- Consecutive up/down streaks and reversal.
- Drawdown/recovery from recent high.

Weekly rules:

- Moving-average break/reclaim/distance for 20w and 40w.
- 52-week high / failed breakout.
- Consecutive up/down streaks and reversal.
- Drawdown/recovery from recent high.

Monthly rules:

- 12-month high / failed breakout.
- 10-month moving-average break/reclaim/distance.
- Consecutive up/down months and reversal.
- Drawdown/recovery from recent high.

## Statistics

For every shown observation, compute sample statistics from historical triggers excluding samples without the required forward window:

- sample count.
- mean and median forward return.
- win rate.
- best and worst sample.
- maximum adverse excursion / drawdown over the forward window.
- confidence from sample count and data-quality severity.

Default forward windows:

- Daily: 5, 20, 60 bars.
- Weekly: 4, 12, 26 bars.
- Monthly: 3, 6, 12 bars.

Rules with too few samples are shown as insufficient evidence only when currently relevant; otherwise they are suppressed.

## Report Contract

Report sections:

1. Metadata.
2. Data Quality.
3. Facts.
4. Statistics.
5. Interpretation.
6. Watch Items.
7. Evidence Limits.

The language must remain evidence-oriented. It may say that a condition is active, supported, weak, or worth monitoring, but it must not instruct the user to buy, sell, or hold.

## Verification

Add focused unit tests with fixture bars:

- Deterministic rules produce observations and statistics on synthetic data.
- Weak history produces insufficient-evidence output.
- Command parsing/router reaches Kline handling for supported syntaxes.
- Yahoo chart provider normalizes mocked U.S. daily bars with metadata, adjusted close mapping, and bar counts.
- Command Workbench Kline execution does not force the degraded provider on the weekly-review-hosted `/command` surface.

Run:

- `python3 -m unittest tests.test_kline_agent`
- A narrow command-router invocation with a monkeypatched provider through tests.
- Command Workbench browser preview coverage for exact Kline commands is verified by `tests.test_command_workbench_kline`.

If live Futu/OpenD is unavailable locally, document that limitation and rely on fixture or mocked-provider verification. As of 2026-07-03, local acceptance must not use local FutuD/OpenD; run local degraded-provider checks with `KLINE_PROVIDER=disabled` when needed. As of 2026-07-04, cloud Futu is explicitly allowed as an approved remote provider path; the blocker is local/cloud double login, not Futu itself. Full live-data acceptance can use an approved remote/cloud Futu environment or the no-credential Yahoo chart path, then must be deployed and retested from `/command`.

## Delivery Tracking

Update `docs/project-management/Feature-Registry.md` so Kline Agent links this plan, marks implementation as locally verified when tests pass, records evidence, keeps user acceptance pending, and names remaining V2/provider/cache gaps.
