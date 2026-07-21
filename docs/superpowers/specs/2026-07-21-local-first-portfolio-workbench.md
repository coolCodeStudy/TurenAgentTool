# Local-First Portfolio Matching and Financial Workbench Design

## Status

- Date: 2026-07-21
- Feature: Frontend experience system
- Owner authorization: autonomous implementation, deployment, and local-first acceptance.
- Scope: desktop Command Workbench, Weekly Review, and Daily Market Brief. Existing URLs and access boundaries remain unchanged.

## Problem

`SpaceX` is visible as the current holding `US.SPCX` in Weekly Review but Command only resolves stock-profile records. A missing profile therefore makes a known holding appear unknown. Weekly also begins a public read without making progress, duration, failure, or retry sufficiently explicit.

## Decisions

1. Command resolves a name, market-qualified code, or symbol against recent persisted account snapshots only after stock-profile resolution has no match. It does not open a live Futu connection from an interactive parse request.
2. A holding without a research profile routes to the existing explicit profile-bootstrap preview. It never writes, executes, or fabricates a decision automatically.
3. Command preview identifies a holding-derived target as `Current holding / 当前持仓` and continues to show its canonical code, such as `US.SPCX`.
4. Weekly disables its period controls during an active read, announces active status, records successful elapsed time, explains failure, and exposes a retry action. Generation guards continue to prevent an older response from replacing a newer selection.
5. Daily remains a tokenless read/history journey. Its existing busy, success, failure, and selectable-history contracts remain the shared baseline.
6. Local Playwright against the deployed URL and Owner Chrome are the primary acceptance evidence. GitHub Actions keeps one manual, tokenless public Playwright diagnostic; it has no protected fixture job and cannot block this feature for a missing secret. A separate feature-scoped protected workflow remains available for other active features without changing this Frontend decision.

## Non-Goals

- Mobile redesign, a SPA migration, automatic research-profile creation, automatic command execution, changes to Daily public access, or a new credential mechanism.
- This does not remove protected command/Weekly operations. It only removes an unused CI credential prerequisite from Frontend acceptance.

## Acceptance Criteria

1. `决策 SpaceX` and `决策 US.SPCX` resolve the recent holding `US.SPCX`; an unprofiled holding requires explicit profile setup and produces no write.
2. Existing profiles retain profile-first resolution.
3. Weekly presents disabled controls while loading, a completed elapsed-time message, and a visible retry on a recoverable load error.
4. All three desktop pages retain one financial shell, public Daily reads/history, public Weekly reads, and recoverable protected Command/Weekly states.
5. Local unit/browser checks and local Playwright production regression pass after the serialized `weekly-review-web` deployment. GitHub public browser checks are diagnostic only.
