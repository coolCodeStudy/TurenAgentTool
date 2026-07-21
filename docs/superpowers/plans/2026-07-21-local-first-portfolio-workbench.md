# Local-First Portfolio Matching and Financial Workbench Plan

## Goal

Make known current holdings discoverable in Command, make Weekly asynchronous feedback clear, and make local browser acceptance authoritative for the three desktop financial surfaces.

## Steps

1. Add failing Python regressions for name/code holding resolution, profile precedence, and no automatic write. Resolve against recent persisted account snapshots and render the source label.
2. Add Weekly renderer and Playwright checks for busy controls and completed elapsed feedback; implement retry and generation-safe cleanup.
3. Keep Daily's existing public busy/history lifecycle and run its regression coverage with the shared desktop suite.
4. Remove protected-fixture CI job/config/test. Retain one manually dispatched, no-token public GitHub diagnostic and document its non-blocking role.
5. Run focused Python, Playwright enumeration, deploy classification, and delivery-state audit; review, integrate, deploy once, then run local Playwright against the deployed URL and request only visual Chrome confirmation.

## Guardrails

- Never read, log, commit, or request an access-token value.
- Never make a Command parse call depend on a live Futu network connection.
- Do not mutate Daily history tasks during acceptance.
- Preserve all public URLs and the Daily tokenless journey.
