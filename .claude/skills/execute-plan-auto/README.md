# execute-plan-auto

Execute a prepared implementation plan by running subagents sequentially in unattended mode.

## Usage

```
/execute-plan-auto <plan-name>
```

## Example

```
/execute-plan-auto my-feature
```

This will:
1. Read `plans/my-feature-plan.md` and `plans/my-feature-plan-subagent-prompts.md`
2. **Verify all prerequisites** (run verification commands, display results)
3. Stop if any prerequisite fails
4. Execute each subagent sequentially
5. Run tests after each phase
6. Retry up to 2 times on failure
7. Stop execution on unrecoverable failure
8. Write results to `plans/my-feature-plan-report.md`

## Prerequisites

Before using this skill, you should have:
1. Created a plan file: `plans/<plan-name>-plan.md`
2. Run `/prepare-plan <plan-name>` to generate the subagent prompts file

## Files

| File | Purpose |
|------|---------|
| `plans/<name>-plan.md` | The implementation plan (checkboxes updated on success) |
| `plans/<name>-plan-subagent-prompts.md` | Prerequisites + prompts for each subagent |
| `plans/<name>-plan-report.md` | Execution report (created by this skill) |

## Prerequisites Verification

Before executing any phase, the skill:

1. Reads the Prerequisites section from the subagent prompts file
2. Runs each verification command
3. Displays results to the user:

```
## Prerequisites Check

| Prerequisite | Status | Details |
|--------------|--------|---------|
| PostgreSQL on 5432 | PASS | pg_isready returned 0 |
| Redis on 6379 | FAIL | Connection refused |
| node_modules exists | PASS | Directory found |
```

4. **If any fail:** Stops execution (user must fix and re-run)
5. **If all pass:** Proceeds to execution loop

## Behavior

- **Prerequisites first:** Verify before any phase runs
- **Unattended:** No user confirmation between steps
- **Sequential:** One subagent at a time, in order
- **Isolated:** Each subagent has no context from previous ones
- **Retry:** Max 2 fix attempts per phase before stopping
- **Fail-fast:** Stops on unrecoverable failure (doesn't skip broken phases)

## Related Skills

- `/prepare-plan <name>` — Analyze dependencies and create subagent prompts
- `/execute-plan-confirm <name>` — Same as this, but with user confirmation after each step
