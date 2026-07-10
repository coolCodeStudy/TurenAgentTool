# Task 2 Report: Production Source Policy and Durable Deployment State

## Status

Implemented and locally committed. No push or deployment performed.

## RED Evidence

Command:

```text
.venv/bin/python -m unittest tests.test_deploy_state -v
```

Result: failed during test import with `ModuleNotFoundError: No module named 'scripts.deploy_state'`. This was the expected failure before the production module existed.

## GREEN Evidence

Focused command after implementation:

```text
.venv/bin/python -m unittest tests.test_deploy_state -v
```

Result: `Ran 9 tests in 0.005s`, `OK`.

Full-suite command:

```text
.venv/bin/python -m unittest discover -s tests -p 'test*.py' -v
```

Result: `Ran 39 tests in 13.690s`, `OK`.

An initial generic discovery attempt, `.venv/bin/python -m unittest discover -v`, reported `Ran 0 tests` because this repository's test directory is not package-discoverable from the project root. The explicit `-s tests -p 'test*.py'` command above is the meaningful full-suite verification.

Additional checks:

```text
.venv/bin/python scripts/agent_preflight.py
git diff --check
```

Both completed successfully before the full suite.

## Files

- `scripts/deploy_state.py`
  - Defines the exact `DeploymentState` and `DeploymentEvent` dataclasses.
  - Resolves only `main` through `origin/main` or a lowercase 40-character SHA.
  - Verifies every target SHA is an ancestor of `origin/main` through `CommandRunner`.
  - Strictly validates state schema and rejects malformed or unknown fields.
  - Persists state and events through sibling temporary files, `flush()`, `os.fsync()`, and `os.replace()`.
  - Creates event directories as needed and rejects event IDs that escape the event directory.
- `tests/test_deploy_state.py`
  - Covers source resolution, unreachable and invalid refs, atomic state round trips, malformed state, event persistence, and event-path traversal.
- `.superpowers/sdd/task-2-report.md`
  - Records verification evidence and review notes as required.

## Self-Review

- The implementation consumes the existing `CommandRunner.run(command: tuple[str, ...], timeout: int | None = None)` interface without changing Task 1 files.
- State validation runs before writing, so invalid state cannot replace a prior durable state file.
- Temporary files are removed on both successful replacement and failure paths.
- JSON output contains only the declared state/event fields; no environment lookup, credentials, or raw command output is persisted.
- The source policy does not resolve arbitrary branch names and proves SHA ancestry before returning a target.
- Focused and full tests cover all requested behavior and existing tests remain green.

## Concerns

- Consumers must continue to write `schema_version=1`; schema migration is outside Task 2.
- Event loading is not part of the requested interface, so event persistence is verified by reading the emitted JSON in tests rather than by a public event loader.
