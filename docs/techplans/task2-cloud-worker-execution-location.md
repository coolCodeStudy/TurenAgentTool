# Task 2 Tech Plan: Make Cloud Worker The Default Research Execution Location

## Background

In the previous portfolio-coverage work, a Codex desktop session ran source discovery, SEC/HKEX/PDF cleaning, draft generation, audit/review, and import locally through MCP tools. The flow worked, but execution location was opaque: the user did not explicitly choose local batch research, and job status did not show whether the task ran in local Codex, cloud worker, or import-only mode.

The larger issue is capability drift. If source discovery, cleaning, audit/review, and import experience stays in local scripts, the cloud worker will not inherit it. Future batch research and portfolio refreshes should run by default on the cloud worker, and the cloud worker must use the same productized research pipeline. Local Codex should mainly debug, fill gaps, review manually, fix tools, and import confirmed drafts.

## Core Purpose

Task 2 is not just adding an `execution_location` field. The purpose is:

1. Productize the locally proven research flow into a code path the cloud worker can execute directly.
2. When the user asks to cover a portfolio or refresh stocks, create cloud tasks by default instead of running local batch research manually.
3. Let local Codex query cloud-produced draft, audit, review, token usage, warnings, and import status.
4. Make local and cloud execution share one research pipeline.
5. Use `execution_location` as observability and confusion prevention.

## Goals

- Make the local research flow the default cloud-worker execution path.
- Route batch research and portfolio refreshes into cloud worker queues by default.
- Let cloud worker complete source collection, draft enrichment, validation, audit, review, artifact persistence, and optional import.
- Let local Codex query job status, artifact summaries, token usage, warnings, and import status.
- Show `execution_location` on all research jobs.
- Make local script execution clearly show `local_codex`, and require explicit confirmation for local batch execution.

## Non-Goals

- Do not rewrite the core research-agent logic.
- Do not change Futu account or trading logic.
- Do not optimize research display; display slimming belongs to Task 3.
- Do not treat deployment notes as completion. The cloud worker must actually run the same research pipeline.

## Terms

- `cloud_worker`: research/codex worker running on the cloud host.
- `local_codex`: current Codex desktop session or local shell.
- `manual_import`: user-confirmed draft imported manually into the knowledge base.
- `import_only`: import an existing artifact without running research.

## Entrypoints To Review

MCP tools:

- `create_research_job`
- `create_portfolio_research_jobs`
- `list_research_jobs`

Scripts:

- `scripts/create_research_jobs.py`
- `scripts/research_agent_worker.py`
- `scripts/research_stock.py`
- `scripts/create_research_draft.py`
- `scripts/import_research_draft.py`

Natural-language command router:

- Create research task.
- View research task.
- Import research result.

## Data Model Recommendation

Prefer existing `research_jobs` metadata/json fields. Add schema only if needed.

Suggested fields:

```text
execution_location: cloud_worker | local_codex | manual_import | import_only
worker_name: string | null
requested_by: string | null
created_from: mcp_tool | script | command_router | codex_desktop
artifact_location: local_path | object_url | null
started_at: timestamptz | null
finished_at: timestamptz | null
```

## Implementation Steps

1. Read the current local research path and identify actual required capabilities:
   - source collection from SEC/HKEX/issuer pages/PDFs
   - source cleaning from iXBRL/PDF/text excerpts
   - draft enrichment
   - validation/audit/review
   - import into InvestmentKnowledge
2. Read the cloud worker path and confirm whether `research_agent_worker.py` calls the same capabilities or only a partial mock/seed flow.
3. Extract or complete the shared research pipeline so local scripts and cloud worker call the same core functions.
4. Make cloud worker persist artifact metadata:
   - draft JSON
   - audit report
   - review report
   - warnings
   - token usage
   - source policy
   - import status
5. Set default `execution_location=cloud_worker` in unified research-job creation.
6. Make `create_portfolio_research_jobs` create cloud tasks by default.
7. Have `research_agent_worker.py` write `worker_name`, `started_at`, and `finished_at`.
8. Add execution banners to local scripts:
   - `research_stock.py`: `execution_location=local_codex`
   - `create_research_draft.py`: `execution_location=local_codex`
   - `import_research_draft.py`: `manual_import` or `import_only`
9. Show execution location, worker, artifact presence, token usage, warnings, and import status in `list_research_jobs` by default.
10. Make command-router paths distinguish task listing from task creation so read commands do not create jobs.
11. Deploy to ECS/cloud host and restart MCP, research worker, or related services.
12. Create a real or small test research job and confirm cloud worker runs source -> draft -> audit -> review -> artifact -> status.
13. Query the job from local Codex and confirm it is a cloud execution result, not a local artifact.

## Acceptance Criteria

- Single-stock research jobs default to cloud worker with `execution_location=cloud_worker`.
- Portfolio research jobs default to cloud worker.
- Cloud worker completes at least one test security through source collection, draft, validation, audit, review, and artifact writeback.
- `list_research_jobs` shows execution location, worker, artifact presence, token usage, warnings, and import status by default.
- Local scripts clearly display `local_codex`, `manual_import`, or `import_only`.
- Local batch research requires an explicit confirmation parameter.
- Viewing jobs does not accidentally create jobs.
- Trading/account write logic is unchanged.

## Test Suggestions

- Unit test: created research job includes `execution_location=cloud_worker`.
- Unit test: portfolio job batch creation sets execution location on every job.
- Unit/integration test: `list_research_jobs` output includes execution location.
- Regression: natural-language list commands do not create tasks.
- Manual test: local import draft output cannot be mistaken for cloud-worker completion.
- Cloud smoke test: after deployment, create a mock or real research job and confirm ECS worker claims, runs, and writes status/artifact metadata.

## Risks

- If the existing job schema lacks metadata, migration must be production-compatible.
- If command-router intent matching is too broad, "view" may still be interpreted as "create."
- If the cloud worker is down, default cloud execution will queue but not complete; status output must show worker health.
- If local scripts and cloud worker use different code paths, local improvements will not reach cloud execution.
- If cloud artifacts only live on cloud local disk, local Codex may not be able to inspect them; job metadata or accessible storage is needed.
