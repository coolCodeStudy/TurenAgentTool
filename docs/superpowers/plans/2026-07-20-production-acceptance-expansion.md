# Production Acceptance Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repeatable production-safe coverage for every public gateway contract and the protected/no-token boundary.

**Architecture:** Keep the existing Python route registry authoritative. Add a Playwright request-context spec for production-safe HTTP contracts and extend the existing browser suite only for non-mutating visible journeys. Protected success remains isolated behind `E2E_PROTECTED_ACCESS_TOKEN`.

**Tech Stack:** Python 3.11 route contracts and unittest, Playwright Test/TypeScript, GitHub Actions.

## Global Constraints

- Use `E2E_BASE_URL` for cloud targets; do not use a local URL for acceptance.
- Never send a valid production write request from automated acceptance.
- Use invalid payloads only when testing public POST validation; assert that no job/report is created.
- Treat missing `E2E_PROTECTED_ACCESS_TOKEN` as an explicit skipped protected-success case, not a pass.

### Task 1: Production-safe API contract spec

**Files:**
- Create: `e2e/public-api-contracts.spec.ts`
- Test: `e2e/public-api-contracts.spec.ts`

**Interfaces:**
- Consumes: deployed `E2E_BASE_URL`, public gateway routes, and unauthenticated protected routes.
- Produces: repeatable API evidence without a valid mutation.

- [ ] **Step 1: Write public route and asset assertions**

Use `request.get()` for every public route and assert `200`, expected content type, and a non-empty response. Assert JSON `ok: true` for the public API endpoints.

- [ ] **Step 2: Write no-token protected-boundary assertions**

Use request-context POST/GET calls without Authorization to assert `401` plus the documented recovery payload before handler invocation.

- [ ] **Step 3: Write invalid public-write assertions**

POST invalid fields to Daily generate and history-job endpoints. Assert `400` and the validation message; do not use an admitted market/date combination.

- [ ] **Step 4: Run against production**

Run: `E2E_BASE_URL=http://47.84.190.191:8010 npx playwright test e2e/public-api-contracts.spec.ts --project=desktop-public`

Expected: all accepted public routes and safe rejection boundaries pass without creating data.

### Task 2: Browser coverage completion

**Files:**
- Modify: `e2e/cloud-pages.spec.ts`
- Test: `e2e/cloud-pages.spec.ts`

**Interfaces:**
- Consumes: rendered Daily, Weekly, and Command pages.
- Produces: visible public control, navigation, and recovery evidence.

- [ ] **Step 1: Add read-only Daily market-switch and saved-date behavior**

Assert each market control changes selected state and settles into a status/error state; do not press `生成`.

- [ ] **Step 2: Add Weekly navigation coverage**

Assert previous/current-week controls change the read request and settle visibly; do not press generate except the no-token recovery CTA.

- [ ] **Step 3: Run public cloud browser suite**

Run: `E2E_BASE_URL=http://47.84.190.191:8010 npm run test:e2e:cloud -- --project=desktop-public`

Expected: each visible non-mutating primary journey passes with no overflow or stuck loading region.

### Task 3: CI fixture and acceptance closure

**Files:**
- Modify: `.github/workflows/cloud-e2e.yml`
- Modify: `docs/product/Acceptance-Testing-Agent-Protocol.md`
- Modify: `docs/project-management/Acceptance-Queue.md`

**Interfaces:**
- Consumes: a repository secret named `E2E_PROTECTED_ACCESS_TOKEN`, if the owner has configured it.
- Produces: explicit public pass and protected-success pass/skip reporting.

- [ ] **Step 1: Inject the protected fixture only into the protected job**

Map `${{ secrets.E2E_PROTECTED_ACCESS_TOKEN }}` to the protected Playwright process environment. Never echo it or upload it in artifacts.

- [ ] **Step 2: Run the public workflow and protected fixture job when available**

Dispatch `cloud-e2e.yml` against the production base URL. Confirm it never runs deploy jobs.

- [ ] **Step 3: Update durable acceptance state**

Record exact ref, workflow run, public/fixture result, artifacts, and any remaining blocker in the Acceptance and Delivery Queues.
