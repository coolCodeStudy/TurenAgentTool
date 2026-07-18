# Deploy Admission Reliability P0 Proposal

## Status

Approved for implementation by the Owner directive. This is operating-model
infrastructure, not a product Feature Registry item.

## Problem

Feature delivery currently crosses several partially overlapping interfaces:
GitHub Actions, the private Ops API, the local Ops client, and the MCP
`cloud_deploy` tool. The historical failures are concrete:

- a stale commit reachable from `origin/main` can still be deployed after a
  newer authoritative tip exists;
- `full` maps to `full_image`, but the MCP client cannot transport the required
  immutable image archive and did not expose the conditional emergency reason;
- an isolated coordinator worktree may not have a reachable private Ops URL or
  Ops credential even though it has an approved GitHub token;
- failures after event allocation do not consistently return the durable event
  identifier or the observed resource evidence;
- the Ops API executes synchronously but returns HTTP 202 and the client says
  that deployment merely started;
- an Ops API control-plane update can overlap a business deployment;
- browser access-token policy and internal Ops credentials are discussed as if
  they were one security boundary.

The GitHub runs `29511640343` and `29512741489` both reached the private Ops API
and were rejected before activation because Linux `MemAvailable` was below the
512 MiB production floor. No deploy lock conflict or GitHub-token failure was
involved.

## Decision

Use GitHub Actions as the coordinator-facing production dispatch surface and
the private Ops API as the single internal executor. A coordinator needs a
pushed authoritative commit and GitHub permission; it does not need to discover
the private URL or Ops credential.

Keep 512 MiB as a fail-closed minimum for `targeted_quick` and
`config_restart`. It is a reserve derived from a prior OOM incident on the
approximately 1.6 GiB, no-swap host, not a measured restart-cost model. Do not
lower it to make the current release pass. `full_image` must preserve a larger
provisional start reserve and recheck the 512 MiB floor after image load and
before activation. Record the actual and required values so a rejection is
actionable and future measurements can replace the provisional margin.

Keep image construction off ECS. GitHub Buildx remains the only approved
`full_image` builder; ECS may only load an immutable SHA-tagged archive. Add
`--no-build` to application activation and rollback commands so this boundary
is enforced rather than implied.

## Alternatives Considered

1. Lower the quick-deploy memory floor. Rejected for P0 because there is no
   restart peak measurement and the host has already suffered OOM termination.
2. Restore a background/asynchronous Ops deployment queue. Rejected for P0
   because it adds crash recovery and queue durability work while the current
   engine already produces terminal evidence synchronously.
3. Push images to a registry and deploy immutable digests. Valuable P1 work,
   but it changes registry credentials, egress, provenance, rollback identity,
   and retention; it is not required to fix current admission and contract
   failures.

## Product-Safe Outcome

Rejected requests do not change the active release. Failures after event
allocation return a sanitized event ID, status URL, observed resource evidence,
and next action. Rollback remains automatic after selector or service mutation;
rollback failure persists lockout and manual-recovery evidence. Existing public
product URLs and Daily Market Brief tokenless read behavior are unchanged.
