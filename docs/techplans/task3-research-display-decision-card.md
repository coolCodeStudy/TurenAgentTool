# Task 3 Tech Plan: Default Research Display As Level 1 Decision Card

## Background

Stock research currently preserves a deep evidence layer: stock profile, sources, sectors, knowledge items, audit report, review report, and draft artifact. This is valuable for auditability, traceability, and future refreshes. But default display is too long, and the user can miss the core investment judgment.

The goal is not to store less. The goal is layered display: keep details in storage, but show only decision-useful summary by default.

## Goals

1. Preserve full `sources`, `knowledge_items`, and audit/review artifacts.
2. Show a Level 1 decision card by default for stock inspect/search output.
3. Show only status and summaries by default in research job lists.
4. Allow explicit expansion when evidence is needed.

## Non-Goals

- Do not delete existing knowledge items.
- Do not reduce source audit requirements.
- Do not change research execution location; that belongs to Task 2.

## Level 1 Decision Card Fields

Prefer generating these from existing `stocks` and `knowledge_items` before adding a new table:

```text
one_line_thesis
key_drivers: 1-3 items
core_risks: 1-3 items
watch_items: 1-3 items
data_freshness
source_status
audit_status
knowledge_count
source_count
```

## Display Layers

Level 1 default:

```text
RKLB US
Thesis: ...
Drivers:
- ...
Risks:
- ...
Watch:
- ...
Freshness: latest 10-Q covered, stale after ...
Evidence: 3 sources, 18 facts, audit pass
```

Level 2 evidence layer, explicit flags:

```text
include_sources=true
include_knowledge_items=true
include_audit=true
```

Level 3 artifact layer, verbose/full mode:

```text
include_draft_json=true
include_audit_markdown=true
include_review_markdown=true
```

## Entrypoints To Modify

Stock query/inspect:

- Command-router stock view/analysis output.
- Add a summary helper if needed; do not silently break MCP `search_stock` raw return.

Research jobs:

- `scripts/list_research_jobs.py`
- MCP `list_research_jobs`
- Command-router research-job display.

## Implementation Steps

1. Read current `search_stock`, command-router stock inspect, and `list_research_jobs` output paths.
2. Add a pure function that turns stock profile plus knowledge items into a Level 1 card.
3. Group knowledge items simply:
   - `business` may feed thesis/drivers.
   - `risk` feeds core risks.
   - `watch_item` feeds watch items.
   - Other types default to counts, not full display.
4. Make default stock inspect output show Level 1 card and counts.
5. Add detail/verbose parameters for full `knowledge_items` and `sources`.
6. Make default `list_research_jobs` output show:
   - symbol/market
   - status
   - provider/source policy
   - execution location
   - audit status
   - warnings count
   - token usage
   - artifact presence
   - import status
7. Keep full draft/audit/review access in verbose mode.
8. Manually snapshot-check `07709 HK`, `09995 HK`, `SPCX US`, and `RKLB US`.

## Acceptance Criteria

- Default stock view first screen shows thesis, drivers, risks, and watch items.
- Default output does not include long lists of more than 20 facts.
- Default `list_research_jobs` output does not include full `draft_json`, `audit_markdown`, or `review_markdown`.
- Verbose/detail mode can still retrieve full evidence.
- `import_stock_research_draft` does not drop any sources or knowledge items.
- MCP API compatibility is preserved; if response structure changes, provide a new tool or parameter instead of silently breaking old behavior.

## Test Suggestions

- Unit test: Level 1 card extracts reasonable fields from business/risk/watch_item knowledge.
- Unit test: default job list response excludes large fields.
- Unit test: `verbose=true` can return full fields.
- Manual checks:
  - `07709 HK`
  - `09995 HK`
  - `SPCX US`
  - `RKLB US`

## Risks

- Rule-based synthesis may produce weak thesis text; later work may need manual confirmation or LLM summary.
- Directly changing MCP `search_stock` return structure could break callers; prefer display-layer changes or a new summary endpoint.
- Slim defaults must not hide key risks; risk fields must always appear in Level 1.
