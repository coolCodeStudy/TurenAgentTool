# Frontend Experience Visual Refresh Design

## Status

- Date: 2026-07-18
- Feature: Frontend experience system
- Owner authorization: autonomous delivery, including a professional display refresh
- Design decision: a unified operational workspace built on the existing Python-rendered experience kernel

## Problem

The first shared shell established common navigation and access behavior, but the visual result still combines three page-specific design systems. In particular, the shared left navigation is nested beside a second page sidebar (and, on Weekly Review, a third local rail), while most sections use another bordered card. This creates redundant chrome, weak information hierarchy, and a product that feels assembled rather than deliberately designed.

The refresh must improve visual clarity without changing routes, report or command semantics, protected access boundaries, or Daily Market Brief's public/tokenless journey.

## Options Considered

### 1. Token-only polish

Unify colors, radii, typography, and controls while retaining each page's nested rails and cards. This is low risk but leaves the core visual clutter and incompatible hierarchy.

### 2. Unified operational workspace — selected

Make the shared shell the single product chrome; remove duplicate page navigation rails; introduce a common page header, density scale, status strip, control treatment, table treatment, and recovery panel. Each page retains only page-specific content and, where genuinely useful, a lightweight contextual region inside the content flow. This resolves the structural cause of the unprofessional appearance without a framework migration.

### 3. New frontend application

Rebuild all pages in a component framework. This would offer more freedom but risks existing Python route/auth compatibility and is disproportionate to the display problem.

## Design Direction

The product should feel like a calm, high-trust investment operations workspace: deliberate, dense enough for daily use, and never decorative for its own sake.

- Use an ink/navy text foundation, a restrained blue action color, neutral surfaces, and semantic green/amber/red only for product state.
- Use one strong page title and compact supporting metadata; avoid generic visual weight from repeated outlines.
- Use whitespace and divider rules to group information. A bordered surface is reserved for a major workspace or an actionable recovery state, not every subsection.
- Prefer labels and sentence-case actions over ornamental chips. Chips remain only for compact, comparable metadata.
- Keep raw machine output visually subordinate behind disclosure controls.
- Keep Chinese-facing product copy clear and consistent; new durable source documentation stays English.

## Layout Model

### Shared product chrome

- A single 232px desktop rail contains the product wordmark, the three primary destinations, and a quiet access/status area when relevant.
- The shared rail is the only persistent left navigation. Remove Daily and Weekly's duplicate page sidebars.
- Desktop content uses a fluid readable column with a maximum working width. A contextual right rail is allowed only on wide Weekly Review desktops and only for report anchors; it disappears below 1200px.
- On compact layouts, the product rail becomes a sticky horizontal destination bar. Controls follow below it in source order. No JavaScript menu is required.

### Page composition

- **Command Workbench:** input and Preview form a single command bar. The Action Catalog becomes an adjacent contextual column on wide screens and an inline, collapsible section below the command area on compact screens. Preview and execution output are two deliberate work areas, not two equal cards competing for attention.
- **Weekly Review:** the header owns the week selector and public-read status. Source health becomes a flat metric strip. Major report chapters are separated by section headers and dividers; attribution details remain disclosures inside the relevant chapter.
- **Daily Market Brief:** market selector, date controls, and primary Generate action form one compact toolbar. Summary metrics become a flat peer grid; report sections follow the same Weekly Review hierarchy. Public-history jobs stay visible but secondary.

## Component Rules

### Tokens

- Spacing: 4, 8, 12, 16, 24, 32, 48px.
- Corner radius: 8px for controls, 12px for major actionable surfaces, 999px only for compact metadata.
- Type: system stack; 30px page title, 20px section title, 15px body, 13px metadata, monospace only for commands/symbols/raw diagnostics.
- Controls: 42px desktop / 44px compact minimum height; visible focus ring; one primary action per local action group.

### Surfaces and tables

- Major content workspaces may use a subtle border and white surface. Inner sections use divider spacing, not nested cards.
- Tables use a quiet header band, row hover/focus affordance, tabular numbers for market figures, and one labelled local horizontal scroll region when necessary.
- Empty, loading, warning, and error states use an icon-free semantic accent bar plus explanatory product text. They do not borrow error styling for ordinary absence of data.

### Accessibility and responsive guarantees

- Preserve the existing skip link, landmarks, active navigation semantics, live status, alert semantics, and keyboard control.
- At 390px, there is no page-level horizontal overflow. The primary navigation remains reachable, toolbars stack predictably, and only table regions may scroll horizontally.
- Respect `prefers-reduced-motion`; visual transitions are limited to short opacity/color changes and never gate content.

## Implementation Boundaries

- Extend `web_experience.py` with the shared workspace CSS, navigation/wordmark markup, common header/status/metric primitives, and responsive rules.
- Update `command_workbench.py` only for Command layout classes and CSS consumption; retain request, access, preview, execution, and confirmation behavior.
- Update `weekly_review_web.py` for Weekly and Daily layout classes and shared primitives; retain public/privileged API behavior and all Daily tokenless requests.
- Add renderer-contract tests that assert one shared navigation rail, no duplicate `.sidebar` chrome, shared token markers, compact layout rules, and preserved access/public boundaries.
- Do not add a frontend framework, external font, icon library, build process, or new public URL.

## Acceptance Criteria

1. `/command`, `/weekly-review`, and `/daily-market-brief` visibly share one brand/navigation shell and one component vocabulary.
2. Weekly and Daily no longer render duplicate page sidebars beside the shared product navigation.
3. Command action catalog remains usable on desktop and compact layouts without crowding command input/output.
4. Major content is grouped by hierarchy and dividers; no generic card-within-card clutter is introduced.
5. All pages have clear primary action hierarchy, visible focus states, and accessible 390px behavior.
6. Command protected access/recovery behavior and Weekly public-read behavior remain unchanged.
7. Daily Market Brief remains completely tokenless in HTML and browser request flow.
8. Renderer/unit checks, HTML/JavaScript syntax checks, and cloud API smoke pass before release. Browser acceptance is rerun against an approved browser URL after deployment.

## Non-Goals

- No new product workflow, report data model, charting system, or visual brand campaign.
- No secret/session redesign beyond the existing unified browser access model.
- No workaround for the in-app browser raw-IP URL policy. Browser acceptance requires an allowed production URL or browser environment.
