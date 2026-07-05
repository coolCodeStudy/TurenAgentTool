# Change Packages

`docs/changes/` is the lightweight repo-native change-package area for substantial work.

Use it when a feature or infrastructure change needs more than a one-line queue item and should be resumable without chat history.
Do not use it for tiny doc edits, one-line status corrections, or routine daily logs.

## Source Of Truth

Change packages do not replace current truth:

- Product truth stays in `docs/product/`.
- Technical plans stay in `docs/techplans/`.
- Delivery truth stays in `docs/project-management/Feature-Registry.md`.
- Acceptance truth stays in `docs/project-management/Acceptance-Queue.md`.
- Dispatch truth stays in `docs/project-management/Delivery-Queue.md`.

A change package is the working folder for an active change. After acceptance, fold durable truth back into the files above and archive or close the package.

## Required Files

Each substantial change package should contain:

```text
docs/changes/<change-id>/
  proposal.md
  requirements.md
  design.md
  tasks.md
  handoff.md
```

Use `_template/` as the starting shape.

## Verification

Run:

```bash
python3 scripts/verify_change_package.py --all
```

Or for one package:

```bash
python3 scripts/verify_change_package.py docs/changes/frontend-experience-system
```

The verifier checks required files, required headings, and basic project-management links.
