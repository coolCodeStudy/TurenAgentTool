# Daily Market Brief US Gainer Eligibility Design

Date: 2026-07-16
Status: approved for implementation planning
Feature: Daily Market Brief

## Problem

The US `Top Gainers` section can currently include leveraged or inverse exchange-traded products. Some of those products expose split-adjustment artifacts as very large daily gains, even though the product promise is a liquid common-stock leaderboard. The current implementation filters warrants and low-turnover rows, but it does not require common-equity eligibility or a minimum market capitalization.

## Product Decision

US top gainers must satisfy all of the following:

- The security is an ordinary operating-company equity or ADR/common share, not an ETF, ETN, fund, leveraged/inverse product, warrant, right, unit, or similar derivative security.
- Market capitalization is at least USD 500,000,000.
- The existing USD 10,000,000 turnover threshold remains in force.
- There is no fixed maximum daily percentage gain. A qualifying common stock may legitimately gain more than 100%, including after an IPO or other corporate event.
- A row with missing, zero, malformed, or unavailable market capitalization is ineligible. The report must degrade transparently instead of relaxing the threshold or inventing a value.

This rule applies to both live US reports and historical US reconstructions. Historical reconstruction uses the market capitalization from the current spot-universe snapshot at generation time to select candidates; exact-date price change and turnover still come from the requested historical session. The source status must identify this current-universe limitation and resulting survivorship bias.

## Data Flow

1. AKShare/Eastmoney primary rows read the provider's `Market Cap` / `Total Market Value` field.
2. Direct Eastmoney fallback requests and retains field `f20` as market capitalization.
3. Sina Finance fallback retains `mktcap`, which the endpoint reports in USD.
4. A shared US eligibility helper validates security type and market capitalization before ranking.
5. Eligible rows are sorted by the provider's reported percentage change; no percentage cap or clamping is applied.
6. The top five rows are persisted with their market capitalization and a metric label that records both turnover and market-cap thresholds.

## Security Classification

Provider security-type metadata should be used when available. Because the existing providers do not expose a consistent type field across every fallback, conservative symbol and name checks also reject known non-common-equity terms and patterns, including ETF, ETN, fund, leveraged/inverse, short/bear/bull multiples, warrants, rights, and units. The filter must specifically reject the reported Direxion examples while retaining ordinary companies such as Microsoft and Dow Inc.

## Failure Behavior

- If a provider supplies fewer than five eligible rows, render only the eligible rows and report the actual count.
- If no eligible rows remain, show the existing product-language unavailable/degraded state.
- Do not expose raw provider, SSL, HTTP, database, or traceback details.
- Existing persisted reports remain unchanged until they are regenerated after deployment.

## Verification

Automated tests must prove that:

- Direxion and other ETF/leveraged/inverse rows are excluded even when their market cap and turnover exceed the thresholds.
- Common stocks below USD 500,000,000, and rows without market cap, are excluded.
- Common stocks at or above USD 500,000,000 remain eligible.
- A qualifying common stock with a gain above 100% remains eligible.
- AKShare, direct Eastmoney, Sina fallback, and historical-universe paths use the same USD 500,000,000 threshold.
- The stored row carries market capitalization and an auditable metric label.

After deployment, regenerate the affected US report and verify through the public Daily Market Brief page/API that every displayed US gainer is an eligible common equity with market capitalization of at least USD 500,000,000.
