# Codex Session Workflow

This repository supports multiple Codex sessions, but only if each session has a clear branch and worktree boundary.

## Workspace Roles

- Main workspace: `/Users/lishaocheng/code/TurenAgentTool`
- Default task worktree root: `/Users/lishaocheng/code/TurenAgentTool.worktrees/<task-slug>`
- Default task branch: `codex/<task-slug>`

Use the main workspace for integration, release, urgent fixes, and cloud verification. Use a task worktree for normal feature, product, or documentation work.

## Starting A New Task

For a new independent task, start from the latest `origin/main`:

```bash
git fetch origin main
bash scripts/create_task_worktree.sh <task-slug>
cd ../TurenAgentTool.worktrees/<task-slug>
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/agent_preflight.py
```

Do not create a new task branch from a mixed release branch unless the task is explicitly continuing that exact release branch. Mixed branches make later review show unrelated files and make it difficult to tell what should enter `main`.

## Continuing Existing Work

When a task already has a branch or worktree, continue there. Do not recreate it from the main workspace.

Useful checks:

```bash
git worktree list
git branch -vv
git status -sb
```

If a branch already exists but no worktree is attached, create a worktree for that branch:

```bash
git worktree add ../TurenAgentTool.worktrees/<task-slug> codex/<task-slug>
```

## Integration Flow

Use one of these patterns:

1. Small, isolated change:
   - Commit in the task worktree.
   - Push the task branch.
   - Cherry-pick or merge the specific commits into `main`.

2. Larger feature:
   - Keep product doc, tech plan, implementation, verification, and deployment notes in the same task branch when they are one feature.
   - Merge only after local verification and any required cloud verification.

3. High-risk deploy or infrastructure change:
   - Keep it in its own Ops branch.
   - Do not mix it with product PRDs, unrelated docs, or normal application changes.
   - Verify from inside out: deploy event, release files, container environment, logs, host-local curl, then public URL.

## What Must Not Happen

- Do not use one long-lived branch as a catch-all for unrelated sessions.
- Do not stage untracked files created by another session.
- Do not push a branch with unrelated product docs, Ops scripts, schema changes, and local experiments bundled together unless the bundle is intentionally the release scope.
- Do not treat a branch diff against `origin/main` as "uncommitted changes"; it shows all branch work not yet in `main`.
- Do not delete another session's worktree or untracked files unless the user explicitly asks for that exact cleanup.

## Cleanup Rules

After a task is merged:

```bash
git worktree remove ../TurenAgentTool.worktrees/<task-slug>
git branch -d codex/<task-slug>
```

If a branch still contains useful work that should not yet enter `main`, keep it as a named follow-up branch and record the reason in the final summary or the relevant tech plan.

If a branch only contains obsolete or accidental files, delete those files in that branch before merging anything else.
