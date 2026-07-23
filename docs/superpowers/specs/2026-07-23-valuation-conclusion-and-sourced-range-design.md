# Valuation Conclusion and Sourced Range Design

## Decision

Stock Valuation P0.1 separates two answers that users can otherwise confuse:

1. **Current market valuation** answers what the market is pricing now, using the latest supported price, market capitalization, enterprise value, and trailing multiples already in the validated packet.
2. **Defensible fair-value range** is shown only when a validated scenario bundle supplies the required forward inputs, valuation method, and provenance. It is never inferred from an LLM response or an unreviewed social-media claim.

This is a reusable single-stock contract for US, HK, and KR. It is not a Tesla-specific calculation or a generic Command Workbench translation change.

## User-Facing Contract

The Chinese-first valuation card gains a top-level `估值结论 / Valuation conclusion` section before data gaps.

- It always states the available current market price, market capitalization, and enterprise value.
- It states either a calculated range with method and scenario provenance, or `暂不可计算 / unavailable` with the exact missing input categories.
- It names the next evidence path without exposing a file path, credential, prompt, provider diagnostic, or raw web response.
- The canonical English section remains appended byte-for-byte under `## English original (原文)`.

The first implementation deliberately provides the truthful unavailable state. It does not manufacture a range from default discount rates, arbitrary multiples, or unverified estimates.

## Source and Worker Boundary

The required inputs for a range are:

- a candidate peer universe and comparable multiple evidence, or an explicit intrinsic-value method;
- forward revenue, earnings, or free-cash-flow assumptions for bear/base/bull;
- discount rate, terminal-value or target-multiple assumption, and calculation date;
- source identity, period/date, source class, and validation status for every numerical input.

Official filings, issuer investor-relations documents, regulated exchange filings, FRED/Damodaran-style public rate inputs, and licensed provider data are appropriate sources depending on the input. Twitter/X and general web search are discovery leads only.

The existing cloud research worker may collect source-backed *candidates* using `official_first` research. Its Codex CLI output is not itself a numerical source and may not write a fair-value result into a valuation packet. Candidate inputs require typed validation and explicit provenance before a later scenario-bundle calculator can use them.

## Implementation Slices

The work is intentionally split because the two pieces have different truth boundaries:

1. **P0.1 presentation and honesty (this release):** add the conclusion section, state exact missing evidence, preserve identifiers during Chinese rendering, and correct frame copy only where data supports it.
2. **P0.2 sourced scenario calculator (next bounded technical plan):** introduce a versioned, source-validated scenario bundle and deterministic intrinsic/relative calculation methods. It cannot be safely bundled with P0.1 because no validated reusable forward-input source contract exists yet.

The split is due to external-source validation and market-data provenance, not a deferral of ordinary implementation work.

## Acceptance Criteria

1. Every valuation create/latest card has a Chinese-first valuation conclusion before data gaps and the exact English original after it.
2. Available market facts are shown as current market valuation; unavailable facts are named rather than fabricated.
3. A fair-value range is unavailable unless validated forward scenario/method evidence exists, and the missing categories are specific.
4. Canonical identifiers such as `fact:operating_cash_flow`, source-family IDs, symbols, numbers, dates, currencies, and input refs remain unchanged in the Chinese section.
5. Existing artifact/evidence schemas, authentication, no-write safety, ingress, Compose, and public-port wiring remain unchanged.
6. Unit, router, Workbench, delivery-state, and deployed public/tokenless smoke checks pass before independent acceptance is routed.
