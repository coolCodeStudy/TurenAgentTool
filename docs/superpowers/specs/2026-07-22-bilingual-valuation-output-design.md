# Bilingual Stock Valuation Output Design

## Problem and product decision

The Stock Valuation Command Workbench currently renders user-facing valuation cards and the valuation-method library as English Markdown. The approved product change is to make these two valuation presentations Chinese-first while preserving the canonical English Markdown at the bottom for auditability and specialist review.

`render_valuation_card(packet)` remains a valuation-owned renderer. The implementation should introduce a small presentation contract that can be reused by future product surfaces, but this release must change only Stock Valuation P0. Generic Command Workbench responses, Weekly Review, Daily Market Brief, decision cards, messaging, and locale preferences are out of scope.

## Scope

### In scope

- Stock valuation create response (`valuation <target>` and supported aliases).
- Stock valuation latest-artifact response.
- Valuation method-library response (`valuation methods` and supported aliases).
- Chinese-first Markdown presentation for US, HK, and KR targets.
- Exact canonical English Markdown appended under `## English original (原文)`.
- Controlled-label translation with visible English fallback for unknown dynamic text.
- Renderer, parity, safety, and regression tests.

### Out of scope

- Changes to `stock_valuation_packet.v1` or bounded evidence JSON.
- Persisting a second translated Markdown artifact.
- LLM or external translation dependencies.
- Auth, session, ingress, Compose, public-port, or shared-service wiring changes.
- Repository-wide translation of Command Workbench output.
- User locale negotiation or saved language preferences.

## Output contract

Every affected valuation Markdown response has this shape:

```markdown
<Chinese-first presentation>

## English original (原文)

<canonical English presentation>
```

The English section is generated from the same validated public projection and canonical English renderer that existed before this change. It is not independently reconstructed from translated text. Tests must compare the English body byte-for-byte with the canonical renderer output, allowing only the explicit wrapper delimiter.

The Chinese section translates controlled headings, labels, status/degraded/recovery copy, safety wording, metric labels, frame names, and method descriptions. It preserves verbatim:

- symbols, market-qualified targets, standard method names where they are identifiers, and provider/source IDs;
- numeric values, units, currencies, dates, timestamps, freshness/as-of values, and URLs;
- formula names, input references, fact IDs, source IDs, and other traceability tokens.

Unknown or free-form English text must remain visible in the Chinese section with an explicit original/fallback marker. The English section remains authoritative for complete fidelity.

## Architecture and data flow

1. `command_router.py` builds or loads the validated valuation packet exactly as it does today.
2. The valuation module creates one bounded public projection for card rendering. Artifact persistence and evidence projection remain unchanged.
3. A valuation presentation helper renders the canonical English card/method output and applies a deterministic controlled-label mapping to produce the Chinese-first section.
4. The helper composes the two sections with the exact `## English original (原文)` delimiter.
5. Existing Command Workbench response handling receives the resulting Markdown without auth, HTML, gateway, or service-topology changes.

The helper must be deterministic, side-effect free, and dependency-light. It must not inspect or mutate databases, user insights, research candidates, credentials, or artifact schemas.

## Translation and safety rules

- Translate only allow-listed labels and controlled copy owned by the valuation renderer.
- Keep dynamic values and provenance tokens intact; never translate a symbol, source ID, fact ID, period, currency, formula input reference, or URL.
- Use a visible English fallback for an unrecognized dynamic phrase rather than guessing or dropping it.
- Preserve existing degraded-state semantics, safety copy, path-like target rejection, and no-insight-write behavior.
- Do not log, persist, or return credentials or token-like values.

## Verification and acceptance

1. Create and latest valuation responses for representative US, HK, and KR targets begin with Chinese presentation and end with the English-original delimiter.
2. The English body exactly matches the canonical pre-change English card for the same packet, including ordering and all values.
3. The Chinese body retains every required P0 section: status, gaps, facts, calculations, selected frames, assumptions, interpretation, watch items, source coverage, freshness, and safety/recovery state.
4. The method library is bilingual with the same ordering and specialist markers.
5. Artifact JSON and bounded evidence JSON remain schema-identical and contain no duplicated translated Markdown.
6. Unknown/free-form text has visible fallback coverage; existing leakage, path-safety, and no-write regressions remain green.
7. No auth, ingress, Compose, public-port, or unrelated product surface changes appear in the diff.
8. After implementation is integrated, the coordinator makes one serialized `weekly-review-web` quick-deploy decision and routes the same acceptance item to independent testing. User acceptance remains pending while `AT-2026-07-19-001` is blocked.

## Implementation boundary

Expected implementation files are `investment_knowledge_mcp/stock_valuation.py` and focused valuation/router tests. `command_router.py` may change only if the existing response path needs to call the new presentation helper. `command_workbench.py`, auth/session code, Compose, ingress, and public-port wiring must remain unchanged unless a test proves an existing contract requires a narrowly scoped compatibility adjustment.

## Design status

Approved by the Owner on 2026-07-22 after Product Agent review. Product Return Gate: accepted and routed by Feature Coordinator. Existing protected Stock P0 fixture/session blocker is unchanged and is not waived by this presentation enhancement.
