# Plan Review Gate

After completing discovery, codebase research, or clarifying questions (such as `/grill-me`):

1. **Present the Plan First**: Always output a clear, structured implementation plan to the user for review before executing any changes.
2. **Wait for Explicit Approval**: Do **not** call `exit_plan_mode` to hand off to execution, and do **not** modify files, until the user explicitly approves the plan (e.g., "Proceed", "Approved", "LGTM", or clicking Proceed).
3. **Exception**: Only skip the review gate when the user explicitly says to execute immediately without review, or for trivial single-step follow-ups that the user already approved.

# Branch & Pull Request Workflow

1. **Never Edit Directly on `main`**: Before making code or configuration changes, always create and switch to a dedicated feature branch (e.g., `git checkout -b feat/<short-description>`).
2. **Open a Pull Request for Review**: Push the feature branch to `origin` and open a Pull Request (`gh pr create`) for user review rather than pushing or merging directly into `main`.
3. **Merge Only After Approval**: Wait for explicit user approval before merging the PR.
