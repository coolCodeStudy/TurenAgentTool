# Earnings Brief Studio V1 Source Review

**State:** `reviewed_for_implementation`
**Reviewed:** 2026-07-24
**Release:** `earnings-brief:US.AAPL:FY2025-Q1:v1`

## Source Set

| Source ID | Tier | Official locator | Reviewed evidence |
|---|---|---|---|
| `source:aapl:fy2025-q1:release` | issuer IR | [Apple reports first quarter results](https://www.apple.com/newsroom/2025/01/apple-reports-first-quarter-results/) | Fiscal quarter ended 2024-12-28; revenue `$124.3bn`; diluted EPS `$2.40`; Services record; active installed base all-time high. |
| `source:aapl:fy2025-q1:10q` | regulatory filing | [Apple FY2025 Q1 Form 10-Q](https://www.sec.gov/Archives/edgar/data/320193/000032019325000008/aapl-20241228.htm) | Total sales `$124,300m`; net income `$36,330m`; total gross margin `$58,275m` and `46.9%`; Greater China sales `$18,513m`; product/category sales `$69,138m`, `$8,987m`, `$8,088m`, `$11,747m`, and Services `$26,340m`; comparative FY2024 Q1 sales `$119,575m`. |

## Review Decisions

- The Twitter/X image is visual-density inspiration only and is not included in the source set.
- The fixture includes only figures confirmed in the issuer release or SEC filing.
- The trend chart uses the exact year-over-year comparable quarters exposed by the reviewed 10-Q. It does not attribute intervening-quarter figures to that filing.
- The gross-margin display is independently recomputed from gross profit divided by revenue and tested within one-decimal rounding tolerance.
- The forward quantitative-guidance card is typed `not_disclosed`; it carries no numeric value.
- Bull/base/bear scenarios are analytical hypotheses with validation conditions, not issuer guidance or personalized advice.
- The stored `content_hash` values identify the bounded reviewed evidence summaries used by this fixture, not a redistributed copy of the full documents.
