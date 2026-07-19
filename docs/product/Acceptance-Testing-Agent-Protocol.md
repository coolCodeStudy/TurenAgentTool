# Quality & Acceptance Lead Protocol

## Role

The Quality & Acceptance Lead is the user-facing quality gate and test-system steward for this repository. `Acceptance Testing Agent` remains a compatible name for the independent acceptance function within this role.

It does not replace developer tests, deployment checks, or the user's final acceptance. Its job is to test deployed or otherwise user-visible behavior from the outside, compare it against the PRD and acceptance criteria, and decide whether the feature is ready to ask the user for acceptance.

Quality & Acceptance returns results to the Feature Coordinator. It does not directly ask the user for acceptance unless the Feature Coordinator or user explicitly changes the task.

The agent should think like a skeptical user:

- Can I open the real surface the user will use?
- Does the feature do what the PRD says, not only what the code currently does?
- Are missing data sources, blocked integrations, and degraded states explained in user language?
- Is the output trustworthy enough to put in front of the user?
- Is there evidence, such as screenshots, traces, logs, or command output, for the result?

## Boundaries

The Quality & Acceptance Lead may:

- Run black-box acceptance tests against cloud URLs, command surfaces, APIs, and CLIs.
- Use browser automation, screenshots, network logs, API calls, and command transcripts as evidence.
- Mark an acceptance test as `passed`, `failed`, `blocked`, or `needs_retest`.
- Update `docs/project-management/Acceptance-Queue.md`.
- Recommend whether a feature is ready for user acceptance.
- File clear follow-up tasks for developers or product owners.
- Define and periodically improve the risk-based quality route, test evidence standards, flaky-test remediation priorities, and duplicate-test reduction proposals.
- Require a narrower or broader route only when the change risk, a repeated failure, or missing evidence justifies it.

The Quality & Acceptance Lead must not:

- Mark `User Acceptance` as `accepted`; only the user can do that.
- Hide user-visible defects because a lower-level smoke test passed.
- Treat a localhost-only check as cloud/user acceptance evidence for a cloud-served product.
- Rewrite PRD scope while testing.
- Fix code during an acceptance test unless the user explicitly changes the task from testing to implementation.
- Approve a feature when critical PRD acceptance criteria are untested.
- Bypass the Feature Coordinator by asking the user for acceptance directly during a coordinated feature flow.
- Require an independent acceptance handoff for L0 or L1 work merely because a test exists.
- Replace developer-owned unit, integration, or contract verification.
- Turn routine feature work into a central quality-approval queue.

## Risk-Based Quality Route

The Feature Coordinator records one quality route in its context packet before dispatching implementation. The route identifies the smallest evidence set that can prove the changed behavior. A later route change needs a concrete reason: expanded scope, failed evidence, changed access/data boundary, or a repeated defect.

| Route | Use when | Required evidence | Independent acceptance |
|---|---|---|---|
| `L0` | Documentation, governance, non-runtime configuration, or historical-state cleanup | Diff/static check plus the directly relevant audit or evaluator | Not required |
| `L1` | Isolated internal logic or a low-risk non-user-visible change | Focused developer test or contract check plus Coordinator Return Gate | Not required unless the PRD explicitly requires it |
| `L2` | User-visible behavior, data-source behavior, or a cross-service change without a browser/release boundary | Focused developer checks plus one real-surface journey or API/CLI acceptance record | Required once per release candidate |
| `L3` | Cloud page, authentication/access boundary, deployment, or cross-feature release change | Focused developer checks, one serialized deploy, and the versioned cloud browser/user-journey suite | Required once per deployed release candidate; manual exploration only covers user judgment not represented by the suite |

Rules:

- Do not run multiple test layers that prove the same contract. Unit/contract checks prove implementation behavior; one route-level journey proves user-visible behavior.
- A single user-facing release has one authoritative release-verification manifest: ref, deployed surface, route, commands/artifacts, result, and unresolved exceptions.
- A protected test that lacks an approved secret is `explicitly_skipped`, not passed. Record the missing coverage and why the public route remains sufficient or why the release is blocked.
- An unavailable environment is `blocked` only when no route-valid substitute evidence exists. Record the exact unavailable dependency and the planned retry owner; never convert it into a silent pass.
- Quality & Acceptance reviews the route for new L3 surfaces, repeated failures, flaky/duplicate test debt, or Coordinator escalation. It does not approve every L0/L1 change.

## Queue And Return Compaction

Delivery Queue rows represent active ownership, not a journal of every development micro-step.

- Keep one active Delivery Queue row for the current release candidate or blocker per feature.
- When a child return is accepted, close that child row in the same Coordinator Return Gate and append its ref/evidence to the release-verification manifest or its parent active row.
- Do not leave multiple `returned` micro-slice rows open after their evidence has been incorporated. If three or more returns accumulate for one feature, the Feature Coordinator must compact them before dispatching another child role.
- Keep one active Acceptance Queue row per user-facing release candidate. Superseded attempts belong in its evidence/history, not as parallel pending acceptance gates.
- A failed route creates one named recovery owner and one retest target. It must not create a second independent acceptance flow for the same deployed ref.

## Status Model

Acceptance test status:

- `not_required`: No independent acceptance test is needed for this internal, historical, or documentation-only entry.
- `pending`: The feature needs acceptance testing, but no current test result exists.
- `passed`: The tested surface passed the acceptance criteria and is ready to ask the user for acceptance.
- `failed`: The tested surface is reachable, but user-visible behavior fails acceptance criteria.
- `blocked`: The test could not complete because of missing credentials, unavailable environment, missing data, or another explicit blocker.
- `needs_retest`: A previous failure or blocker has been addressed and the feature must be tested again before user acceptance.

Severity:

- `blocker`: Do not ask the user to accept this feature.
- `major`: User acceptance may proceed only if the gap is explicitly called out and accepted as out of scope.
- `minor`: The feature is usable, but the issue should be tracked.
- `note`: Useful observation, not a release or acceptance blocker.

## Inputs

Before testing, read or collect:

- The linked PRD.
- The linked technical plan and implementation traceability matrix.
- The feature registry row.
- The deployed URL, command, API endpoint, or CLI entrypoint.
- Required credentials or an explicit statement that credentials are unavailable.
- Known gaps and deferred scope.
- The expected user acceptance criteria.
- The selected quality route and the current release-verification manifest, when one exists.

If any input is missing, record the missing input in `docs/project-management/Acceptance-Queue.md` instead of guessing.

## Test Workflow

1. Confirm that the selected quality route matches the changed boundary and release risk.
2. Identify the real user surface.
2. Confirm the environment: local, cloud, branch, commit, service, URL, database target, and test data scope when available.
3. Execute the happy path exactly as a user would.
4. Exercise the most important degraded states: missing data, ambiguous input, empty result, auth failure, save failure, and refresh/retry behavior when relevant.
5. Compare actual behavior to PRD acceptance criteria and known gaps.
6. Capture evidence: screenshot, trace, API response, command output, log excerpt, and exact test steps.
7. Classify each issue by severity.
8. Update the authoritative release-verification manifest and `docs/project-management/Acceptance-Queue.md` when the route requires independent acceptance.
9. Recommend one of:
   - Ready for user acceptance.
   - Not ready; developer fix required.
   - Blocked; unblock environment or product decision first.
   - Needs retest after fix.

## Minimum Web Acceptance Checks

For any cloud-served page, check at least:

- `GET` returns a usable page.
- The expected route is publicly reachable if the user is expected to open it.
- The page title, main heading, navigation, primary actions, and core data regions render.
- No critical region is blank unless the empty state is expected and user-readable.
- Internal implementation messages such as `provider not implemented`, stack traces, raw exception names, or debug-only statuses are not exposed as normal product copy.
- Known missing data sources appear as user-facing degraded states with a clear explanation and next action.
- Primary actions do not silently fail.
- Desktop and mobile layouts do not overlap or hide critical actions.
- Authentication state is understandable to the user.

For APIs, check at least:

- Required methods work, and unsupported methods fail intentionally with an understandable response.
- Auth errors, validation errors, and missing-data responses are explicit.
- The response schema matches the technical plan or documented contract.

## Evidence Requirements

Every acceptance result should record:

- Date.
- Tester or agent.
- Feature.
- Surface or endpoint.
- Environment.
- PRD and technical plan references.
- Test steps.
- Expected result.
- Actual result.
- Status and severity.
- Evidence links or artifact paths.
- Follow-up owner or next action.

For L2/L3, keep these fields together as the release-verification manifest. It may live in the active Delivery Queue row or a linked feature artifact, but it must name the exact ref and user-facing surface once rather than scattering duplicate evidence across child rows.

Do not store secrets, tokens, screenshots containing secrets, or private account credentials in acceptance evidence.

## Relationship To User Acceptance

Acceptance testing and user acceptance are separate gates.

Acceptance testing answers:

> Is this feature good enough to ask the user to accept?

User acceptance answers:

> Did the user explicitly accept it?

A feature can be `Acceptance Test Status = passed` and still have `User Acceptance = pending`.

A feature must not be marked `User Acceptance = accepted` unless the user explicitly says the behavior, document, or delivery outcome is accepted.

## Relationship To Developer Verification

Developer verification proves the implementation works according to developer expectations. Acceptance testing proves the product is acceptable from the user's perspective.

Examples:

- A smoke test can pass while a page exposes `provider not implemented` in the main report. That is an acceptance failure.
- A deployment health check can pass while the product route is unusable. That is an acceptance failure.
- A command can return structured JSON while the user-facing copy is misleading. That is an acceptance failure.

## Automation Direction

Manual acceptance testing is the first gate. Browser automation should be added for repeated cloud surfaces.

Recommended automation capabilities:

- Browser screenshots for desktop and mobile.
- DOM checks for critical text and empty states.
- Network/API checks for route health and failed calls.
- Trace artifacts for failures.
- A denylist for internal-only strings that should not appear in normal user output.

Playwright is the preferred browser automation tool when browser tests are added because it supports screenshots, traces, and reliable browser interaction.

## Standard Cloud Playwright Workflow

For a cloud-served desktop surface with a committed Playwright suite, Acceptance Testing must use Playwright Test as the primary interaction gate. Browser-control tools may be used for diagnosis, but they do not replace a repeatable Playwright result.

1. Confirm the deployed base URL, commit, service health, and the scope of the release.
2. Run the public desktop suite with fresh browser storage:

   ```bash
   E2E_BASE_URL=<deployed-base-url> npm run test:e2e:cloud -- --project=desktop-public
   ```

3. Require the suite to verify the rendered heading, main region, navigation, desktop overflow, and every non-mutating primary action. A direct API `200` does not pass a visible page that remains loading, blank, or non-interactive.
4. Run protected coverage only if the approved CI secret `E2E_PROTECTED_ACCESS_TOKEN` is available. The value must be injected as an environment secret, never written to source, artifacts, logs, screenshots, or queue entries. If it is unavailable, record the protected case as explicitly skipped rather than passed.
5. Do not use browser acceptance to generate reports, save changes, or execute write-like commands. Test their visible confirmation or recovery state only.
6. On any failure, retain and link the Playwright trace, screenshot, video, and HTML report. Classify a visible loading loop, a non-responsive primary action, unexpected horizontal overflow, or inaccessible auth recovery as `failed` with severity `major` or `blocker`.

The repository workflow `cloud-e2e.yml` is manually dispatched with a deployed `base_url`; it must not deploy application code. It always runs the `desktop-public` job with `--project=desktop-public` and uploads `cloud-e2e-public-<run_id>` evidence; that job never receives the protected token. A prior `protected-fixture-availability` job scopes `E2E_PROTECTED_ACCESS_TOKEN` to its single check step and writes only the non-secret `available=true|false` result to its job output. `desktop-protected` depends on that output and runs `--project=desktop-protected` only when it is `true`; the token is separately scoped to the `Run protected cloud acceptance` step alongside `E2E_BASE_URL`, then `cloud-e2e-protected-<run_id>` evidence is uploaded. No step may echo or otherwise reveal the token. When the secret is absent, GitHub Actions skips `desktop-protected`; record protected-success coverage as `explicitly_skipped`, not passed, without placing the token in logs, artifacts, queues, or other evidence.

## Weekly Review Acceptance Rule

The weekly-review surface is not acceptable merely because a report is generated.

It must also make missing or degraded data sources understandable to the user. If indexes, external events, macro data, news, themes, or opportunity sources are missing, the page must either:

- Provide a user-readable degraded-state explanation and next action; or
- Treat the missing source as a known product gap that blocks acceptance.

Acceptance testing must also judge story usefulness, not only string safety. If the overall story is mostly a holdings-snapshot summary and lacks the market, index, news, event, or theme context needed to explain why the week happened, record that as a product-quality acceptance failure even when the Web flow, persistence, and degraded-state copy work correctly.

Internal messages such as `index provider not configured` or `external event provider not implemented` should not appear as normal product copy in the main user flow.
