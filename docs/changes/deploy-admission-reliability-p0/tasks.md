# Deploy Admission Reliability P0 Tasks

1. Add failing source-policy and workflow serialization tests.
2. Require exact current `origin/main`, remove redundant out-of-lock source
   resolution, and serialize Ops control-plane updates.
3. Add failing memory/evidence/no-build tests.
4. Add mode-specific memory admission, phase observations, failure evidence,
   and explicit `--no-build` activation/rollback.
5. Add failing Ops client/MCP contract tests.
6. Implement structured client errors, request validation, supported
   target/route/provenance fields, local full-image rejection, truthful
   synchronous rendering, and HTTP 200 terminal success.
7. Add flow-audit regression cases for deploy state and separate product versus
   internal credential domains.
8. Update deployment documentation, the Agent Operating Model Roadmap, and
   precise Delivery Queue recovery rows without creating a product feature.
9. Run focused tests, deployment contract suite, flow audits/evals, full
   relevant regression, and independent review.
10. Commit and push the task branch. Reconcile authoritative `main` deliberately.
    If control-plane code is accepted, record Deploy Intent and run the separate
    serialized Ops API install before any business deploy/retest.
