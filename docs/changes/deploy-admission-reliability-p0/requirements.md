# Deploy Admission Reliability P0 Requirements

## Preconditions

An executable production request is admissible only when:

1. the requested commit is pushed and equals the freshly fetched
   `origin/main` tip;
2. the server-computed classification and targets agree with the request;
3. no GitHub `production-deploy` job, Ops control-plane mutation, or host deploy
   lock is active;
4. the mode-specific resource, Docker, Compose, PostgreSQL, and source gates
   pass;
5. `full_image` has a GitHub-built immutable archive for the same SHA and any
   emergency override has a sanitized reason of at least 20 characters;
6. Deploy Intent names feature/operating lane, commit, mode, targets, reason,
   verification surfaces, and watch owner/path.

If a branch or older SHA is supplied, the typed recovery action must say to
integrate it into authoritative `main`, push, and dispatch the new main tip.

## Coordinator-Facing Request

The GitHub workflow is the supported coordinator entry point:

```json
{
  "ref": "<current-origin-main-sha>",
  "mode": "no_deploy | targeted_quick | config_restart | full_image",
  "targets": ["weekly-review-web"],
  "feature_routes": ["/weekly-review", "/health"],
  "source": "github_actions",
  "requested_by": "<non-secret coordinator label>",
  "emergency_reason": "<full_image override only>"
}
```

`archive_path` is an internal GitHub-to-Ops transport field. It is never a
coordinator/MCP parameter. Aliases `quick` and `full` may be accepted for
backward compatibility but responses and durable evidence use canonical names.

The MCP/local client must expose supported quick/config fields or reject before
network dispatch. `full` and `full_image` must raise a typed
`full_image_requires_workflow` error that directs the caller to the GitHub
builder path; supplying only `emergency_reason` can never make the local client
capable of transporting an image.

## Terminal Response And Event Evidence

The Ops call is synchronous. HTTP 200 means a terminal successful result. A
terminal failure uses a typed 4xx response. Once an event ID has been allocated,
both paths include:

- `deploy_event_id` and stable `status_url`;
- canonical mode, resolved authoritative SHA, requested and affected services;
- resource observations and the mode-specific required thresholds;
- stable-health window and final service/aggregate health;
- feature-route smoke evidence when routes were supplied;
- rollback/cleanup state;
- explicit `return_to_coordinator` next action.

The durable lifecycle is `admitted -> executing -> stable-health verification
-> succeeded | failed/rolled_back | failed/manual-recovery`. The HTTP request
waits for the terminal transition; status lookup returns the same sanitized
terminal evidence. Validation failures before event allocation may omit an
event ID but must still return a typed error and next action.

## Memory And Packaging Policy

- Use Linux `MemAvailable`, not raw free memory.
- `targeted_quick` and `config_restart` require at least 512 MiB.
- `full_image` requires a provisional 768 MiB before load, then at least
  512 MiB after load and before application activation. These are safety
  reserves, not performance claims.
- Never bypass the memory gate with an emergency reason and never count swap as
  additional available physical memory.
- GitHub builds and caches the immutable image; ECS does not run Docker build.
- All Compose activation and rollback operations use `--no-build`.
- P1 telemetry will measure phase-by-phase memory decline, swap, PSI, cgroup
  events, and OOM counters before recalibrating thresholds.

## Security Boundaries

- GitHub PAT/Actions permission authorizes repository and workflow operations.
- Ops API credentials authorize private control-plane calls and remain in
  GitHub Secrets or the internal service environment.
- Browser tokens authorize privileged product writes. Public read contracts,
  including Daily Market Brief and the approved Weekly Review reads, must not
  depend on GitHub or Ops credentials.
- No credential value, authenticated URL, or secret-bearing command output may
  appear in events, errors, docs, commits, or coordinator returns.

## Acceptance

Regression tests must reproduce stale-main admission, duplicate-channel
serialization, the hidden full-image mismatch, missing Ops configuration,
resource rejection without evidence, synchronous-response ambiguity, and
browser/Ops token-bucket conflation. Existing public URLs and tokenless Daily
Market Brief reads remain regression guards.
