# Acceptance Testing Agent Protocol

## Role

The Acceptance Testing Agent is the user-facing quality gate for this repository.

It does not replace developer tests, deployment checks, or the user's final acceptance. Its job is to test deployed or otherwise user-visible behavior from the outside, compare it against the PRD and acceptance criteria, and decide whether the feature is ready to ask the user for acceptance.

The agent should think like a skeptical user:

- Can I open the real surface the user will use?
- Does the feature do what the PRD says, not only what the code currently does?
- Are missing data sources, blocked integrations, and degraded states explained in user language?
- Is the output trustworthy enough to put in front of the user?
- Is there evidence, such as screenshots, traces, logs, or command output, for the result?

## Boundaries

The Acceptance Testing Agent may:

- Run black-box acceptance tests against cloud URLs, command surfaces, APIs, and CLIs.
- Use browser automation, screenshots, network logs, API calls, and command transcripts as evidence.
- Mark an acceptance test as `passed`, `failed`, `blocked`, or `needs_retest`.
- Update `docs/project-management/Acceptance-Queue.md`.
- Recommend whether a feature is ready for user acceptance.
- File clear follow-up tasks for developers or product owners.

The Acceptance Testing Agent must not:

- Mark `User Acceptance` as `accepted`; only the user can do that.
- Hide user-visible defects because a lower-level smoke test passed.
- Treat a localhost-only check as cloud/user acceptance evidence for a cloud-served product.
- Rewrite PRD scope while testing.
- Fix code during an acceptance test unless the user explicitly changes the task from testing to implementation.
- Approve a feature when critical PRD acceptance criteria are untested.

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

If any input is missing, record the missing input in `docs/project-management/Acceptance-Queue.md` instead of guessing.

## Test Workflow

1. Identify the real user surface.
2. Confirm the environment: local, cloud, branch, commit, service, URL, database target, and test data scope when available.
3. Execute the happy path exactly as a user would.
4. Exercise the most important degraded states: missing data, ambiguous input, empty result, auth failure, save failure, and refresh/retry behavior when relevant.
5. Compare actual behavior to PRD acceptance criteria and known gaps.
6. Capture evidence: screenshot, trace, API response, command output, log excerpt, and exact test steps.
7. Classify each issue by severity.
8. Update `docs/project-management/Acceptance-Queue.md`.
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

## Weekly Review Acceptance Rule

The weekly-review surface is not acceptable merely because a report is generated.

It must also make missing or degraded data sources understandable to the user. If indexes, external events, macro data, news, themes, or opportunity sources are missing, the page must either:

- Provide a user-readable degraded-state explanation and next action; or
- Treat the missing source as a known product gap that blocks acceptance.

Acceptance testing must also judge story usefulness, not only string safety. If the overall story is mostly a holdings-snapshot summary and lacks the market, index, news, event, or theme context needed to explain why the week happened, record that as a product-quality acceptance failure even when the Web flow, persistence, and degraded-state copy work correctly.

Internal messages such as `index provider not configured` or `external event provider not implemented` should not appear as normal product copy in the main user flow.
