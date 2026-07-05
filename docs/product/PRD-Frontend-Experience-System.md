# PRD: Frontend Experience System

## Status

- Status: ready for technical planning.
- Product owner: Product/Frontend Experience owner.
- First implementation slice: shared server-rendered app shell, primary navigation, and design-token contract for both `/weekly-review` and `/command`.
- Source change package: `docs/changes/frontend-experience-system/`.
- Delivery Queue: `DQ-2026-07-05-002`.
- User acceptance: not requested and not accepted.

## Problem

The active web product is becoming a set of page islands. Weekly Review and Command Workbench are both user-facing, but each owns its own inline Python-rendered HTML, CSS, JavaScript, layout rules, navigation behavior, status handling, and responsive behavior. The Owner has to infer how pages relate to one another, and future surfaces such as Daily Market Brief risk adding more inconsistent entrypoints if the product shell is not defined first.

## Goal

Create the first visible frontend system slice by giving the active web pages one coherent product shell while preserving current product behavior. The slice should make Weekly Review and Command Workbench feel like parts of the same application without introducing a new frontend framework or changing data, command, auth, or deployment contracts.

## First Slice Decision

Choose the recommended two-surface slice: apply a shared server-rendered app shell, primary navigation, and design-token contract to both `/weekly-review` and `/command` in one bounded release.

Rationale:

- `/weekly-review` and `/command` are the two active standalone user-facing pages. Improving only one page would leave the most obvious inconsistency in place.
- The current implementations are both Python-rendered inline pages, so a shared server-rendered contract is the smallest architecture step that proves reuse without a frontend migration.
- The two-surface release has a higher blast radius, but the risk is manageable with explicit reviewer gates, route-preservation checks, desktop/mobile screenshots, and no behavior changes.

The lower-risk fallback, Weekly Review shell first plus a link to the existing `/command`, is rejected for this slice because it would mainly polish one page and defer the central product problem: disconnected active surfaces.

## Users And Journeys

### Weekly Review User

The Owner opens `/weekly-review` or `/`, reads or generates a weekly review, reviews candidate insights, refreshes or saves the report, and can understand that Command Workbench is another active tool in the same application.

### Command Workbench User

The Owner opens `/command`, enters a token if needed, previews and runs supported commands, reviews result cards, and can return to Weekly Review without guessing another URL.

### Cross-Surface Navigation

The Owner can move between Weekly Review and Command Workbench using consistent primary navigation. The current page is visibly active. Navigation must not imply that Daily Market Brief or Candidate Insights are standalone pages.

### Mobile Check

The Owner can use the primary navigation, token field, primary actions, status messages, generated results, and action catalog on a narrow screen without overlapping controls or hidden required actions.

## Scope

The first implementation slice must include:

- A shared app shell contract for active server-rendered pages, including brand/header area, primary navigation, landmark structure, skip link, shared focus style, and responsive navigation behavior.
- Primary navigation entries for active standalone pages only: Weekly Review and Command Workbench.
- A shared design-token contract for page background, text, border, accent, status, error, success, warning, spacing, typography scale, controls, cards, notices, and tables.
- Shared CSS class naming or helper output for common shell elements, notices, buttons, cards, and status regions.
- Application of the shell and tokens to `/weekly-review`, `/`, and `/command`.
- Preservation of existing page-specific content: Weekly Review report controls and candidate insights remain in Weekly Review; Command Workbench action catalog, history, token entry, preview, execute, and result rendering remain in Command Workbench.
- Explicit desktop and mobile visual evidence for `/weekly-review` and `/command`.

## Non-Goals

- Do not introduce a new frontend framework, JavaScript bundler, SPA router, or template migration for this slice.
- Do not implement or link to Daily Market Brief until it has its own Product package or PRD and route.
- Do not make Candidate Insights a standalone navigation item.
- Do not change API routes, request or response payloads, auth headers, token storage keys, command parsing, confirmation guards, or private route behavior.
- Do not redesign Command Workbench result-card semantics.
- Do not change Weekly Review generation, persistence, source logic, candidate insight APIs, or report data models.
- Do not change cloud deploy behavior.
- Do not mark user acceptance as accepted.

## What Must Not Regress

- `/` and `/weekly-review` continue to render Weekly Review.
- `/command` continues to render through the public `weekly-review-web` route owner and the internal `command-api` route owner.
- Existing Weekly Review APIs continue to be present: `/api/weekly-review`, `/api/weekly-review/generate`, `/api/weekly-review/refresh`, `/api/weekly-review/save`, `/api/candidate-insights`, and candidate insight confirm/reject routes.
- Existing Command Workbench APIs continue to be present: `/api/command-workbench/actions`, `/api/command-workbench/parse`, and `/api/command-workbench/execute`.
- Browser token behavior remains unchanged, including current localStorage keys and authorization header behavior.
- Weekly Review generate, refresh, save, and candidate insight confirm/reject behavior remain unchanged.
- Command Workbench preview, execute, confirmation guards, local history, pinned actions, and result rendering behavior remain unchanged.
- No false Daily Market Brief affordance appears.

## Accessibility And Responsive Criteria

- Each changed page has a skip link and a meaningful `main` landmark.
- Primary navigation is keyboard reachable, has visible focus, and marks the current page with an accessible current-state indicator.
- Primary controls, token entry, status messages, generated results, and action catalog remain reachable without pointer-only interactions.
- Loading, error, status, and result updates use either a documented live-region pattern or deliberate focus management.
- Text and controls do not overlap at mobile widths.
- Tables and generated content can overflow horizontally only inside intentional scroll containers; page-level horizontal scrolling should not be introduced.
- Touch targets for primary navigation and page actions remain comfortably usable on mobile.
- Screenshots or equivalent visual evidence are captured for desktop and mobile states of `/weekly-review` and `/command`.

## Acceptance Criteria

1. `/weekly-review`, `/`, and `/command` share the same shell structure, primary navigation model, and design-token contract.
2. Primary navigation includes Weekly Review and Command Workbench, shows the active page, and links only to active routes.
3. Daily Market Brief is omitted from navigation unless a Product package or PRD and route exist before implementation; no dead link is allowed.
4. Weekly Review behavior is preserved for read/generate/refresh/save, candidate insights, source/status display, and generated report content.
5. Command Workbench behavior is preserved for token entry, parse/preview, execute, confirmation guards, local history, action catalog, and result cards.
6. Public `/command` through `weekly-review-web` and internal `/command` through `command-api` are both verified when `/command` rendering changes.
7. Desktop and mobile evidence show no overlapping navigation, hidden primary controls, or broken page layout on `/weekly-review` and `/command`.
8. Keyboard navigation and focus visibility are verified for shared navigation and primary page actions.
9. Status/error/loading/result update behavior is documented and verified for both pages.
10. No user acceptance is requested until the slice is deployed and independently acceptance-tested.

## Reviewer Gates

- Frontend Experience Reviewer: required before implementation handoff. The reviewer must check surfaces reviewed, consistency risks, responsive/accessibility risks, and whether the technical plan covers the PRD acceptance criteria.
- Release Reviewer: required before deploy if one release changes both `/weekly-review` and `/command`, which is the chosen first slice.
- Acceptance Reviewer: required after the deployed user-facing slice exists and before asking the Owner for user acceptance.
- Security/Access Reviewer: required only if implementation changes auth headers, token storage, private route behavior, secret handling, or token/error exposure. It is not required for the planned shell-only slice if those behaviors remain unchanged.

## Technical Planning Requirements

The next Development task must create a technical plan before implementation. The plan must identify:

- The shared server-rendered helper or module that owns shell metadata, nav entries, design tokens, and shared classes.
- How `/weekly-review`, `/`, and `/command` will consume the shared shell while preserving existing route owners.
- Renderer or smoke tests proving required links, route strings, API paths, token keys, and current behavior strings are preserved.
- Desktop and mobile screenshot or browser verification steps for both pages.
- Accessibility verification for skip link, landmarks, focus visibility, keyboard reachability, active nav state, and status/result announcements.
- Rollback or release-risk notes for the two-surface change.

## Open Gaps

- No Daily Market Brief route, renderer, package, or PRD exists in this worktree.
- No technical plan exists yet for the shell implementation.
- No implementation, deployment, independent acceptance test, or user acceptance exists for this frontend slice.
