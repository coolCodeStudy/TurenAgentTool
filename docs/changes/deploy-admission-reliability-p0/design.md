# Deploy Admission Reliability P0 Design

## Ownership And Channel

```text
Feature Coordinator (GitHub permission)
  -> GitHub Actions production-deploy concurrency
  -> private tunnel and request assembly
  -> independent ECS Ops API
  -> host deploy lock and shared DeploymentEngine
  -> durable event + stable-health evidence
  -> originating coordinator Return Gate
```

GitHub Actions owns dispatch for coordinator-driven releases. The Ops API owns
admission and execution. The local/MCP client is an operator convenience, not a
second full-image transport. Every event records one source/owner; a caller must
not launch another channel while that ref has an active or queued event.

The Ops API update workflow shares the `production-deploy` concurrency group
and acquires the same host lock before install/restart/stop operations. A
business app release does not update `/opt/investment-ops`; changed control-plane
code requires a separate serialized `ops-api.yml` install.

## Source Policy

The engine fetches `origin/main` while holding the host lock. `main` resolves to
that tip. An explicit SHA is accepted only when it equals that same tip. An
ancestor is no longer sufficient. This makes a queued stale push fail closed
instead of rolling production backward.

The Ops handler validates syntax but does not perform a second authoritative
resolution outside the lock. A rejection uses `source_policy_rejected` and
names the integrate/push/redispatch recovery.

## Interface Validation

`OpsClientError` carries `http_status`, `error_code`, sanitized `message`,
`data`, and `next_action`. The client parses structured JSON errors rather than
embedding the raw response body in a string. Request validation canonicalizes
modes, validates refs/targets/routes, and rejects unsupported full-image local
dispatch before opening the network connection.

The MCP tool returns `ok: false` with the structured typed error. Rendered
errors are never wrapped in `ok: true`. Success copy says the synchronous
deployment completed and includes the event/status handoff.

## Resource Admission And Evidence

The resource snapshot is attached to deployment context before evaluation, so
even a preflight rejection writes observed disk/memory values. Evidence adds
`required_available_memory_bytes`, phase/minimum observations, and the mode.

`full_image` performs the higher start check before `docker load`, then collects
again after load and before service activation. A drop below the reserve stops
before further mutation or invokes the existing rollback path if selectors were
already changed. Application Compose operations explicitly use `--no-build`.

The existing stability policy remains 30 seconds for quick/config and 60
seconds for full image. The final API evidence reads the durable event so it
includes target durations, resource metrics, rollback status, and final health.
Feature routes are forwarded from GitHub/MCP and tested through the existing
health checker.

## Failure Behavior

- Syntax/schema/source rejection: no mutation; typed action.
- Resource/runtime rejection: no selector/service mutation; durable failed
  event with actual/required evidence.
- Activation or health failure: existing selector/service rollback.
- Rollback failure: durable lockout and manual recovery; no automatic retry or
  second channel.
- Ops update lock conflict: fail/queue at GitHub and fail closed at the host;
  never restart the Ops service during a business deployment.

## P1 Boundaries

Registry/digest transport, SBOM/signing, phase telemetry, swap policy,
per-service memory limits, and threshold calibration are follow-up work. They do
not block the P0 truthful contract and safe coordinator path.
