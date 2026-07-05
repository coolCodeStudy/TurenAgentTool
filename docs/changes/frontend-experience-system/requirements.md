# Frontend Experience System Requirements

## User Journeys

- The Owner can see which user-facing product surfaces exist and which ones feel inconsistent.
- A Feature Coordinator can dispatch Product/Frontend/Development work from this package without requiring the Owner to restate the UX problem.
- A Frontend Experience Reviewer can judge a proposed UI change against explicit surfaces and acceptance criteria.
- The Owner can move between the active Weekly Review and Command Workbench pages through one shared primary navigation model without seeing fake future-page affordances.

## Acceptance Criteria

- Current surfaces are inventoried with URL/command entrypoint, implementation location, navigation behavior, and obvious UX risks.
- The first implementation slice is named and scoped.
- Shared frontend principles are defined for navigation, page layout, loading/error states, responsive behavior, and acceptance evidence.
- Delivery Queue remains the active dispatch state.
- No routine daily log is created.

First-slice frontend acceptance criteria:

- Product decision: the first implementation slice is the recommended two-surface release, applying a shared server-rendered app shell, primary navigation, and design-token contract to both `/weekly-review` and `/command`.
- Active user-facing pages expose one shared primary navigation model with clear active state.
- The first slice must not add a Daily Market Brief link unless its Product package or PRD exists; a disabled future placeholder is acceptable only if Product explicitly asks for it.
- Existing API routes, auth headers, localStorage token keys, command execution guards, weekly-review generation, save/refresh behavior, and candidate-insight behavior remain unchanged.
- Desktop and mobile verification captures `/weekly-review` and every changed `/command` route owner.
- Primary controls remain reachable by keyboard and visible at mobile widths.
- Status, error, loading, and result updates have a defined announcement or focus-management behavior.
- No user acceptance is marked by the implementation or review agents.

Reviewer-gate requirements:

- Frontend Experience Reviewer is required before implementation handoff.
- Release Reviewer is required before deploy if both `/weekly-review` and `/command` are changed in one release.
- Acceptance Reviewer is required after the deployed user-facing slice exists.
- Security/Access Reviewer is required only if auth headers, token storage, private route behavior, secret handling, or token/error exposure changes.

## Degraded Behavior

If implementation ownership or framework direction is unclear, the coordinator should stop at a Product/Frontend decision packet rather than making a broad technical migration.

If cloud deployment is not required for inventory, the deploy decision must be `not_required`.

If Development finds that applying the shell to both `/weekly-review` and `/command` cannot be safely released together, it must return a technical blocker or revised plan to the Feature Coordinator rather than silently shrinking the PRD to Weekly Review only.

## Out Of Scope

- Full redesign.
- Framework migration.
- Rebuilding every product surface.
- User acceptance for any product feature.
