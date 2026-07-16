# Daily Market Brief Cross-Market Gainer Eligibility Design

Date: 2026-07-16
Status: approved for implementation
Feature: Daily Market Brief

## Problem

The `Top Gainers` section can include securities that are not ordinary company shares. The reported US examples were leveraged or inverse exchange-traded products whose split adjustments appeared as extreme daily gains. The current implementation filters some warrants and low-turnover rows, but it does not enforce a consistent common-equity and market-capitalization universe across CN, HK, and US markets.

## Product Decision

Top gainers must satisfy all of the following:

- The security is an ordinary operating-company equity or ADR/common share, not an ETF, ETN, fund, leveraged/inverse product, warrant, right, unit, preferred share, or similar derivative security.
- Market capitalization is at least CNY 3,500,000,000 for CN, HKD 4,000,000,000 for HK, and USD 500,000,000 for US.
- Existing turnover thresholds remain in force: CNY 50,000,000 for CN, HKD 20,000,000 for HK, and USD 10,000,000 for US.
- There is no fixed maximum daily percentage gain. A qualifying common stock may legitimately gain more than 100%, including after an IPO or another corporate event.
- A row with missing, zero, malformed, or unavailable market capitalization is ineligible. The report must degrade transparently instead of relaxing the threshold or inventing a value.

The rule applies to both live reports and historical reconstructions. Historical reconstruction uses market capitalization from the current spot-universe snapshot at generation time to select candidates; exact-date price change and turnover still come from the requested historical session. Source status must identify this current-universe limitation and resulting survivorship bias.

## Data Flow

1. AKShare/Eastmoney primary rows read the provider's `Total Market Value` field.
2. Direct Eastmoney fallbacks request and retain field `f20` as market capitalization.
3. Sina fallbacks retain a market-cap field when the endpoint provides one. A fallback row without market cap is not eligible.
4. A shared eligibility helper validates market-specific security type and minimum market capitalization before ranking.
5. Eligible rows are sorted by the provider's reported percentage change; no percentage cap or clamping is applied.
6. The top five rows are persisted with market capitalization and a metric label that records turnover and market-cap thresholds.

## Security Classification

Provider security-type metadata should be used when available. Because providers do not expose a consistent type field across every fallback, conservative symbol and name checks also reject known non-common-equity terms and patterns. These include ETF, ETN, fund, leveraged/inverse, short/bear/bull multiples, warrants, rights, units, and preferred-share markers. Existing CN `ST` and delisting filters remain in force. The filter must specifically reject the reported Direxion examples while retaining ordinary companies such as Microsoft and Dow Inc.

## Failure Behavior

- If a provider supplies fewer than five eligible rows, render only the eligible rows and report the actual count.
- If no eligible rows remain, show the existing product-language unavailable/degraded state.
- Do not expose raw provider, SSL, HTTP, database, or traceback details.
- Existing persisted reports remain unchanged until regenerated after deployment.

## Verification

Automated tests must prove that:

- Direxion and other ETF/leveraged/inverse rows are excluded even when market cap and turnover exceed the thresholds.
- Ordinary shares below each market's threshold, and rows without market cap, are excluded.
- Ordinary shares at or above each threshold remain eligible.
- A qualifying ordinary share with a gain above 100% remains eligible.
- AKShare, direct Eastmoney, available Sina fallback, and historical-universe paths use the same market-specific thresholds.
- Stored rows carry market capitalization and auditable metric labels.

After deployment, regenerate the affected reports and verify through the public Daily Market Brief page/API that every displayed gainer satisfies the ordinary-share, turnover, and market-cap rules.
