# Frontend Experience System Design

## Approach

Use this package as the first repo-native change-package trial. The first phase is inventory and coordination, not implementation. The coordinator should route to a Frontend Experience/Product owner to define the surfaces and first slice, then route engineering only after scope is narrow.

## Files Or Surfaces

Likely surfaces to inventory:

- Command Workbench: `/command`.
- Weekly Review: `/weekly-review`.
- Daily Market Brief: pending feature.
- Any command-generated cards or reports exposed through the Web surface.

Likely files to inspect:

- Python Web rendering modules under `investment_knowledge_mcp/`.
- `docs/project-management/Delivery-Queue.md`.
- Product PRDs for active Web-facing features.

## Data And State

This package should update:

- `docs/changes/frontend-experience-system/*`
- `docs/project-management/Delivery-Queue.md`
- Future PRD or technical plan only after Product/Frontend scope is decided.

It should not update `Feature-Registry.md` until a concrete user-facing feature or implementation slice is approved.

## Risks

- Overbuilding a new frontend platform before the first slice is clear.
- Mixing product acceptance with frontend consistency acceptance.
- Accidentally changing cloud surfaces without independent acceptance testing.
- Adding another permanent role instead of a risk-based Frontend Experience Reviewer gate.

## Reviewer Gates

- Frontend Experience Reviewer: required before any implementation slice is dispatched.
- Acceptance Reviewer: required after a deployed user-facing frontend slice.
- Release Reviewer: required only if the slice touches multiple active cloud surfaces.
- Security/Access Reviewer: required only if auth, private token, or secret behavior changes.
