# Frontend Experience System Design

## Status

- Date: 2026-07-16
- Feature: Frontend experience system
- Owner decision: approved for autonomous delivery through implementation, deployment, and independent acceptance
- Selected approach: shared Python-rendered experience kernel
- Compatibility dependency: accept or reject the returned Weekly Review public-authorization fix before editing overlapping auth code

## Problem

Command Workbench (`/command`), Weekly Review (`/weekly-review`), and Daily Market Brief (`/daily-market-brief`) are served by related Python HTTP code but behave like separate products. They use different navigation, layout, visual tokens, responsive breakpoints, error recovery, and browser-token storage. The fragmentation makes new pages expensive to add and makes access-token failures look like user errors.

The system needs one operational product experience without replacing the current Python rendering stack or weakening access boundaries.

## Goals

1. Provide one information architecture and primary navigation model across the three existing URLs.
2. Establish enforceable layout, visual, responsive, error, and accessibility rules.
3. Give protected user-facing surfaces one coherent browser access session.
4. Keep Daily Market Brief reads, current-session generation, saved-date lookup, and public history jobs tokenless.
5. Preserve existing URLs, domain behavior, confirmation guards, and server-side authorization.
6. Introduce the system through a small, independently testable implementation slice.
7. Keep the active Weekly Review authorization regression flow authoritative for its own fix and reconcile its returned ref before overlapping edits.

## Non-Goals

- Replacing Python renderers with a SPA or frontend framework.
- Changing report, command, market-data, or research domain models.
- Unifying user access credentials with Ops API, deployment, database, provider, or other machine credentials.
- Making Daily Market Brief private or adding a token control to it.
- Changing `/`, `/command`, `/weekly-review`, or `/daily-market-brief` URL behavior.
- Migrating every inner table, report block, or result card in the first slice.
- Printing, logging, committing, transmitting, or documenting secret values.

## Current Architecture Inventory

### Command Workbench

- `render_command_workbench_html()` lives in `investment_knowledge_mcp/command_workbench.py`.
- The same renderer is served by `investment_knowledge_mcp/command_api.py` and `investment_knowledge_mcp/weekly_review_web.py`.
- Page HTML and action catalog are public. Parse and execute APIs are protected.
- The browser currently stores `command_workbench_token` and exposes a separate token field.
- The page has no product-level navigation and uses a teal, two-column shell with its own breakpoints.
- The server returns a useful authorization recovery payload, but the page collapses it to a bare `unauthorized` error.

### Weekly Review

- Routes, authorization, APIs, public error handling, and the full HTML/CSS/JS renderer live in `investment_knowledge_mcp/weekly_review_web.py`.
- `/` and `/weekly-review` render the same page.
- The deployed regression showed that the page could load while its first report API request returned `401 unauthorized`.
- The active Weekly Review coordinator has a returned development fix at `aef9424`; its final deployed and acceptance-tested ref remains a compatibility input, not code to duplicate here.
- The browser currently stores `weekly_review_web_token` and displays a second token field.
- The desktop shell has product navigation, a main report column, and a local report rail, but the product navigation omits Command Workbench and mixes page anchors with destinations.

### Daily Market Brief

- The renderer and APIs also live in `investment_knowledge_mcp/weekly_review_web.py`.
- Public reads, current-session generation, saved dates, and public history jobs are deliberately tokenless and bounded.
- The page has no token control and sends no Authorization header.
- Its navigation already links to all three surfaces, but its shell and breakpoints are still independently defined.

### Shared Versus Duplicated Code

The surfaces share Python service infrastructure, route conventions, system fonts, safe server-side error sanitization, and broadly similar tables. They duplicate complete CSS foundations, navigation markup, spacing, colors, radii, breakpoints, control sizing, status banners, and page-shell behavior.

## Considered Approaches

### 1. Written Conventions Only

Keep all renderers independent and document visual rules. This has the lowest initial risk but does not enforce consistency and leaves token recovery fragmented.

### 2. Shared Python Experience Kernel — Selected

Add a small Python module that owns navigation metadata, design tokens, shell primitives, access-session browser helpers, and status/error primitives. Existing renderers retain page-specific content and JavaScript. This matches the repository's deployment model and creates enforceable contracts without adding a build chain.

### 3. Template/Static-Asset or SPA Migration

Move pages immediately into templates, static bundles, or a dedicated frontend application. This may become useful later, but it creates unnecessary migration and deployment risk for the current scope, especially around dual Command serving and Weekly Review authorization.

## Information Architecture

The primary navigation follows the operating cycle:

1. `每日简报` — observe the current market
2. `每周复盘` — reflect on portfolio and evidence
3. `命令工作台` — investigate and run protected operations

Every page renders the same destination order, stable labels, active-page state, and `aria-current="page"`. The brand links to `/weekly-review` for compatibility; `/` continues to render Weekly Review.

Page-local navigation remains separate:

- Daily Market Brief: CN/HK/US tabs and saved-date controls
- Weekly Review: report sections and local contents links
- Command Workbench: action catalog, pinned items, and recent commands

Public and protected destinations remain visible in the primary navigation. Access is communicated in the page header and recovery state, not by hiding destinations.

## Shared Browser Access Model

### Boundary

- Protected user-facing surfaces use one browser access session: Command Workbench and any protected Weekly Review operations.
- Daily Market Brief never reads, writes, migrates, or requires that session.
- Machine credentials remain separate and are out of scope.

### Storage

The canonical browser key is `investment_knowledge_access_token`. It is used only to build an Authorization header for protected user-facing requests. The value must never enter command history, page URLs, telemetry, server logs, rendered results, repository files, or documentation.

The initial implementation preserves the current localStorage-based security posture. It does not claim that localStorage is equivalent to an HttpOnly server session. A future server-session design requires separate threat modeling and is not necessary to remove current friction.

### Compatibility Migration

On a protected page, the access helper resolves browser state in this order:

1. Use the canonical `investment_knowledge_access_token` when present.
2. Otherwise inspect legacy keys `command_workbench_token` and `weekly_review_web_token` locally in the browser.
3. If exactly one non-empty legacy value exists, copy it to the canonical key and remove both legacy keys.
4. If both legacy values exist and match, copy the value to the canonical key and remove both legacy keys.
5. If both exist and differ, do not guess. Remove neither, show a non-secret conflict recovery state, and ask the user to enter the current private access token once.
6. Missing or stale state shows the same product-language access panel on protected pages.

No token value is emitted in migration status, error text, events, logs, tests, screenshots, or durable evidence. Tests use obvious synthetic placeholders only.

### Recovery

Protected pages distinguish:

- `access_required`: no usable browser credential; explain that private access is required and provide one input/action.
- `access_rejected`: the server rejected the stored credential; clear the canonical credential only after explicit user action or a new value, then provide retry.
- `access_not_configured`: the protected service has no server credential configured; show a maintenance message rather than blaming the user.
- `request_failed`: non-auth service or network failure; preserve browser credential and show retry.

Successful protected requests retain the canonical value in browser storage. A visible `Forget access` action removes the canonical and legacy user-facing keys without contacting the server.

Weekly Review public reads must not be blocked by the access session. Only operations that the accepted Weekly Review compatibility ref keeps privileged may request the unified credential.

## Experience Rules

### Layout

- Desktop product navigation rail: 216px.
- Main content is fluid with `min-width: 0` and a readable maximum width appropriate to operational tables.
- An optional page-local rail may appear only when it adds navigation value.
- Page padding: 24px desktop, 16px compact.
- Spacing scale: 4, 8, 12, 16, 24, and 32px.

### Typography

- System font stack; no new font dependency.
- Page title: 28px/1.2.
- Section title: 18px/1.35.
- Body: 14px/1.5.
- Metadata: 12px/1.45.
- Monospace is reserved for commands, symbols, and raw diagnostic output.

### Color And Surfaces

- One neutral background, white primary surface, neutral border, and blue accent.
- Semantic success, warning, and failure colors must meet WCAG AA contrast.
- A content section may have one bordered surface. Nested content groups use spacing or dividers rather than additional cards.
- Status tiles are allowed only as a flat peer grid, not inside another bordered card.

### Controls

- Minimum 40px desktop control height and 44px touch target on compact layouts.
- Inputs require visible labels; placeholders are examples, not labels.
- Primary, secondary, and destructive actions have stable visual meanings.
- `:focus-visible` is always visible and is not removed.

### Responsive Behavior

- At compact widths, primary navigation becomes a wrapping or horizontally scrollable top row with no JavaScript menu dependency.
- Header controls stack in source order.
- Page-level horizontal overflow is prohibited at a 390px viewport.
- Wide tables use a labeled, keyboard-accessible local scroll container.
- Optional local rails become inline navigation or are omitted when duplicate.

### Accessibility

- Provide a skip link, semantic header/nav/main/aside landmarks, and one page-level `h1`.
- Use `aria-current` for active navigation.
- Use `role="status"` with polite live updates for progress and `role="alert"` for blocking errors.
- Never rely on color alone for state.
- Preserve keyboard operation for tabs, actions, history, and candidate selection.

## Code Organization

Create `investment_knowledge_mcp/web_experience.py` with narrowly scoped units:

- `PageIdentity` and primary destination metadata
- `render_primary_navigation(active_page)`
- shared shell/token CSS rendering
- browser access-session JavaScript helper rendering
- shared status/access panel markup

The module must not import repositories, command routing, report generation, or market providers. Page renderers depend on it; it does not depend on page renderers.

Page-specific code remains initially in:

- `command_workbench.py` for Command content and behavior
- `weekly_review_web.py` for Weekly Review and Daily Market Brief routes, APIs, and page-specific behavior

Renderer extraction into separate template files or packages is deferred until the shared contracts are stable.

## First Implementation Slice

The slice delivers:

1. The shared experience kernel.
2. One primary navigation model and shared shell tokens consumed by all three renderers.
3. Unified protected-browser access storage and migration for Command Workbench and privileged Weekly Review operations.
4. Product-recoverable protected-access states.
5. Preservation of Daily Market Brief's tokenless HTML and request flow.
6. Render-contract, authorization-matrix, migration, and responsive-structure tests.

It does not migrate page-specific content components or alter report/command semantics.

## Weekly Review Reconciliation Gate

Before changing `weekly_review_web.py` authorization or Weekly Review token UI:

1. Obtain the Weekly Review coordinator's returned branch, commit, endpoint matrix, tests, deploy event, and cloud acceptance result.
2. Inspect the exact diff and accept or reject it through the Coordinator Return Gate.
3. Start implementation from an authoritative ref containing the accepted fix, or cherry-pick only the accepted compatibility commit onto the implementation branch.
4. Preserve its public-read and privileged-operation decisions unless this design identifies a direct contradiction.
5. Run Weekly Review regression tests and independent cloud acceptance again after access unification.

The Frontend Experience coordinator owns shared session and shell behavior. The Weekly Review coordinator owns its public-read regression until its returned fix is accepted.

## Acceptance Criteria

### Navigation And Shell

- All three URLs render identical primary destinations in the same order.
- The active destination uses `aria-current="page"`.
- `/` still renders Weekly Review.
- Existing page controls and content regions remain available.
- New or changed layout does not introduce nested bordered-card clutter.

### Access

- A valid canonical browser credential works across Command Workbench and protected Weekly Review operations without re-entry.
- Safe legacy state migrates without exposing the value.
- Conflicting legacy values are not guessed or overwritten.
- Missing, rejected, unconfigured, and non-auth failures produce distinct product-language recovery.
- Token values do not appear in URLs, HTML output, command history, persisted events, logs, screenshots, or test evidence.
- Daily Market Brief HTML contains no access-token input and its public read, generation, saved-date, and history-job requests remain tokenless.
- Ops/deploy/database/provider credentials are unchanged and remain isolated.

### Compatibility And Regression

- Command Workbench parse/execute authorization and confirmation guards remain enforced.
- The accepted Weekly Review public-read behavior remains available without user token discovery.
- Weekly Review privileged operations remain protected according to the accepted compatibility matrix.
- Holder-attribution rendering and the known `2026-06-22` report remain usable.
- Daily Market Brief CN/HK/US, saved-date, and public history flows remain usable.
- Both Command-serving paths render the same experience shell.

### Responsive And Accessibility

- Desktop and 390px viewport checks show usable navigation and controls.
- No page-level horizontal overflow exists at 390px; only explicit table containers may scroll horizontally.
- Keyboard focus is visible and navigation/actions are keyboard operable.
- Progress and blocking errors expose the correct live-region semantics.

## Verification Strategy

- Unit tests for access-state resolution and legacy migration decisions.
- Renderer-contract tests for navigation, active state, labels, landmarks, access controls, and Daily Market Brief token absence.
- HTTP authorization-matrix tests for public and protected endpoints.
- Existing Command Workbench, Weekly Review holder-attribution, Daily Market Brief, smoke, and deploy-classification tests.
- Source and artifact scans for token values, raw Authorization headers, internal exceptions, and credential names in user-visible output.
- Coordinator cloud smoke after serialized deployment.
- Independent cloud acceptance from the real URLs, followed by the Coordinator Return Gate.

## Deployment And Delivery

The design/spec phase requires no deployment. Implementation deploy mode is determined from the accepted diff; because shared renderer code affects the Weekly Review Web service and the standalone Command API renderer, the deploy plan must identify every affected service rather than assuming one target. Deployment uses only the shared serialized workflow and a pushed authoritative ref.

Product completion requires implementation verification, stable cloud deployment, independent acceptance, durable state reconciliation, and explicit Owner acceptance. The coordinator may autonomously reach `ready_for_user_acceptance` but cannot mark Owner acceptance.
