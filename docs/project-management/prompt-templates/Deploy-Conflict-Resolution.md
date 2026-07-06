# Deploy Conflict Resolution Prompt Template

```text
You are resolving a cross-feature deploy/ref conflict.

This is a Global PM or Release Integration task, not a normal feature-level routing task.

Inputs:
- Current deployed ref:
- Accepted feature ref(s):
- Ref that caused regression:
- Must-preserve actions/surfaces:
- Known acceptance rows:
- Deploy path:

Rules:
- Produce or authorize an exact combined release ref.
- Do not directly redeploy an older feature branch if it may clobber newer accepted behavior.
- Do not print or record token values.
- Deployment must use the shared Ops API or serialized workflow path.

Verify before returning:
- Required action catalog entries are present.
- Focused parser/UI smoke for each affected feature passes.
- Unit or compile checks for touched modules pass.
- Delivery state does not falsely mark user acceptance accepted.

Return:
- Combined release ref:
- Commit SHA:
- Verification:
- Deploy decision:
- Authorized deploy owner:
- Required retest:
- Remaining blockers:
```
