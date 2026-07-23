# execute-plan-confirm

Execute a prepared implementation plan by running subagents sequentially with user confirmation before and after each step.

## Usage

```
/execute-plan-confirm <plan-name>
```

## Example

```
/execute-plan-confirm my-feature
```

This will:
1. Read `plans/my-feature-plan.md` and `plans/my-feature-plan-subagent-prompts.md`
2. **Verify all prerequisites** (run verification commands, display results)
3. Ask user to confirm before proceeding (or retry if prerequisites failed)
4. For each phase: ask confirmation before starting
5. Execute the subagent and run tests
6. For each phase: ask confirmation after completion (for review)
7. On failure: auto-retry up to 2 times, then ask user
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

4. **If any fail:** Asks user "Fix and retry, or stop?"
5. **If all pass:** Asks user "All verified. Start execution?"

## Execution Flow

```
┌─────────────────────────────────────┐
│      Verify Prerequisites           │
└──────────────┬──────────────────────┘
               │
       ┌───────┴───────┐
       │               │
    ALL PASS       ANY FAIL
       │               │
       ▼               ▼
"Start execution?" "Retry or Stop?"
       │               │
       ▼               │
┌──────────────────────┴──────────────┐
│ "About to start Phase N. Proceed?" │
└──────────────┬──────────────────────┘
               │ Continue
               ▼
        ┌─────────────┐
        │ Run Phase N │
        └──────┬──────┘
               │
       ┌───────┴───────┐
       │               │
      PASS            FAIL
       │               │
       ▼               ▼
   Mark [x]      Auto-retry (max 2)
       │               │
       │         ┌─────┴─────┐
       │         │           │
       │       Fixed    Still failing
       │         │           │
       │         ▼           ▼
       │     Mark [x]   "Failed after 2 retries.
       │         │       Retry or Stop?"
       │         │           │
       ▼         ▼           │
┌──────────────────────┐     │
│ "Phase N complete.   │◄────┘
│  Continue?"          │
└──────────┬───────────┘
           │ Continue
           ▼
      Next Phase
```

## Behavior

- **Prerequisites first:** Verify and confirm before any phase runs
- **Confirmed:** User confirmation before and after each phase
- **Sequential:** One subagent at a time, in order
- **Isolated:** Each subagent has no context from previous ones
- **Auto-retry:** 2 automatic retries on failure, then ask user
- **No skip:** Failed phases cannot be skipped (stop and modify plan instead)

## Comparison with execute-plan-auto

| Feature | auto | confirm |
|---------|------|---------|
| Prerequisites verification | Yes, stop on fail | Yes, ask retry/stop |
| Pre-phase confirmation | No | Yes |
| Post-phase confirmation | No | Yes |
| Auto-retry on failure | 2 times, then stop | 2 times, then ask |
| Skip failed phases | No | No |
| User can review each step | No | Yes |

## Related Skills

- `/prepare-plan <name>` — Analyze dependencies and create subagent prompts
- `/execute-plan-auto <name>` — Execute subagents sequentially (unattended)
