#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Create an isolated task worktree for a Codex/user session.

Usage:
  bash scripts/create_task_worktree.sh <task-slug> [base-ref]

Defaults:
  worktree root: ../TurenAgentTool.worktrees
  branch:        codex/<task-slug>
  base-ref:      HEAD

Environment:
  WORKTREE_ROOT=/path/to/worktrees     Override the parent worktree directory.
  WORKTREE_BRANCH=codex/custom-branch  Override the branch name.
  WORKTREE_PATH=/path/to/task          Override the full target path.

Examples:
  bash scripts/create_task_worktree.sh weekly-review-product
  bash scripts/create_task_worktree.sh ops-deploy origin/main
EOF
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

task_slug=${1:-}
base_ref=${2:-HEAD}

if [ -z "$task_slug" ]; then
  usage >&2
  exit 1
fi

case "$task_slug" in
  *[!A-Za-z0-9._-]*|""|.*|*-)
    echo "Invalid task slug: $task_slug" >&2
    echo "Use letters, numbers, dots, underscores, and hyphens. Do not start with dot or end with hyphen." >&2
    exit 1
    ;;
esac

repo_root=$(git rev-parse --show-toplevel)
repo_name=$(basename "$repo_root")
default_worktree_root="$(dirname "$repo_root")/${repo_name}.worktrees"
worktree_root=${WORKTREE_ROOT:-$default_worktree_root}
branch=${WORKTREE_BRANCH:-codex/$task_slug}
target=${WORKTREE_PATH:-$worktree_root/$task_slug}

if [ -e "$target" ]; then
  echo "Target already exists: $target" >&2
  exit 1
fi

mkdir -p "$worktree_root"

if git -C "$repo_root" show-ref --verify --quiet "refs/heads/$branch"; then
  git -C "$repo_root" worktree add "$target" "$branch"
else
  git -C "$repo_root" worktree add -b "$branch" "$target" "$base_ref"
fi

cat <<EOF
Created task worktree.

Path:   $target
Branch: $branch

Next:
  cd "$target"
  python3 -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
  .venv/bin/python scripts/agent_preflight.py
EOF
