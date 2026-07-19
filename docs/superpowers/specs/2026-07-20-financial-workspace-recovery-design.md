# Financial Workspace Recovery and Visual System Design

## Status

- Date: 2026-07-20
- Feature owner: Frontend Experience System Coordinator
- Authorization: The Owner directed autonomous closure of page display, non-responsive controls, and the overall frontend experience. This design applies that authorization to the reported Weekly Review, Daily history-task, and financial-quality desktop workspace issues.
- Scope: Desktop only. Existing public URLs and access boundaries remain unchanged.

## Observed Problems

1. `GET /api/weekly-review` returns `status: missing` for both the current and prior requested weeks because no report exists. The page is deliberately public-read-only and has no generate/refresh or access-recovery control, so an empty viewer looks broken rather than honestly explaining what is missing and how a permitted user can recover.
2. Daily Market Brief renders recent page-created history jobs as inert text rows. A user cannot select one to inspect its progress or move to its market/date. The public list intentionally excludes command/agent batch jobs and must continue to do so.
3. The existing pages use independent inline CSS and large white panels. The Daily control cluster is visually detached from its page context, leaving large inactive space and making the product feel like an internal form rather than a financial operating workspace.

## Goals

1. Open Weekly Review on the most recent readable review period when one exists; when no report exists, present a clear, safe recovery state rather than a blank viewer.
2. Turn Daily history jobs into compact, keyboard-accessible task rows that show status, progress, market/date, and resolve a selected task into the correct brief when completed.
3. Establish a high-confidence financial desktop visual language across Daily, Weekly, and Command: disciplined information hierarchy, compact execution controls, meaningful status color, data-first tables, and no nested-card clutter.
4. Preserve public Daily reads, public Weekly reads/protected writes, and protected Command actions.

## Non-Goals

- No SPA, frontend build migration, mobile redesign, data-provider rewrite, or automatic historical report generation.
- No changes to protected access mechanisms or token values.
- No page-wide dark mode; financial quality comes from contrast, typography, hierarchy, and measured accent use rather than decorative darkness.

## Options Considered

### A. Cosmetic CSS-only polish

Fastest, but preserves the wrong Weekly default and inert history rows. Rejected.

### B. Financial Research Workspace — selected

Retain Python renderers and route owners while introducing a small shared token/utility layer, a compact page command bar, report-aware defaults, and interactive task rows. It directly fixes the observed failures and yields a coherent visual system with contained risk.

### C. Replace the pages with a SPA

Could centralize styling, but duplicates route/access work and increases deployment risk. Rejected.

## Information Architecture and Layout

- Keep exactly one product rail with the three primary destinations. It has a dark ink surface, concise brand treatment, and an active destination marker.
- Every page has one `main`, one page title block, one compact contextual command bar immediately under the title, and then report/data sections.
- The command bar groups date, saved-report selector, and actions in reading order; it must remain aligned with the title, not float in unused right-side space.
- Use a restrained palette: ink/navy for hierarchy, warm white canvas, slate text, blue for primary actions, green for successful completion, amber for active/degraded work, and red only for blocking errors.
- Use tabular numerals for market dates, task progress, and market metrics. Use thin dividers and section spacing rather than card-inside-card nesting.

## Behaviour Contracts

### Weekly Review

- On first load, request the last completed review week, not a newly started calendar week, when a completed report is available.
- If no selected report exists, show an explicit empty state. It distinguishes an in-progress week from a missing historical report and offers a protected Generate/Refresh action through the canonical recoverable access flow.
- Existing public read behaviour stays tokenless. Generate/Refresh remains protected; no token is embedded or exposed in the page.

### Daily History Tasks

- Recent page-created jobs render as buttons with an accessible label containing task id, market/date, status, and progress. Command/agent batch jobs remain private and are never added to this public list.
- Selecting a completed job selects its market/date and loads the saved brief. Selecting an active or failed job displays its detailed progress/failure message and polls only that selected task.
- No task click creates, retries, cancels, or otherwise mutates a job.

### Shared Visual Rules

- Primary controls are 40px minimum desktop height; secondary actions are visually quieter than the single primary action.
- Status panels use a labeled live region and an error alert. A completed read replaces its loading state visibly.
- Data tables keep their labelled focusable overflow region and use a compact financial table header/number treatment.
- All changes retain visible keyboard focus and existing Chinese labels.

## Implementation Boundaries

- `investment_knowledge_mcp/web_experience.py`: shared navigation and reusable desktop visual primitives/tokens.
- `investment_knowledge_mcp/weekly_review_web.py`: Weekly default-period selection, Daily task rendering/selection, and the shared renderer styles consumed by those surfaces.
- `investment_knowledge_mcp/command_workbench.py`: apply the same shell/token rules without changing Command authorization or parser behaviour.
- Existing renderer and E2E tests gain regression coverage; no new route owner is introduced.

## Acceptance Criteria

1. A Monday cloud Weekly page opens a completed prior week when one exists; otherwise it shows a clear protected recovery state rather than blank report sections.
2. Daily history rows are interactive and selecting a completed row loads the matched market/date without generating data.
3. Desktop pages share the visual hierarchy above, have one global rail, and do not produce page-level horizontal overflow at 1440px.
4. Existing public Daily/Weekly journeys, Command unauthenticated recovery, and all declared access classes still pass.
5. New tests cover the Weekly period-selection boundary, Daily task selection/no-mutation contract, renderer semantic contracts, and cloud Playwright public journeys.

## Deployment and Watch Contract

- Implementation changes target `weekly-review-web` and, if Command shell code changes, the classifier-selected shared target set.
- The Coordinator records one Deploy Intent only after local tests and review pass, integrates reviewed changes into authoritative `main`, and uses the serialized deploy path.
- Watch path: public cloud Playwright desktop suite plus a direct check of Weekly default period and Daily task selection after deployment.
