---
name: execute-plan-confirm
description: Execute plan subagents with user confirmation after each step
disable-model-invocation: true
argument-hint: [plan-name]
allowed-tools: Read, Write, Edit, Task, Grep, Glob, Bash, AskUserQuestion
---

# Execute Plan: $ARGUMENTS[0] (Confirmed Mode)

Execute the implementation plan by running each subagent sequentially
with user confirmation before and after each step.

## Files

| Input | Output |
|-------|--------|
| `plans/$0-plan.md` | Updated with [x] checkboxes |
| `plans/$0-plan-subagent-prompts.md` | - |
| - | `plans/$0-plan-report.md` |

## Step 1: Verify Prerequisites

Before executing any phase, read the Prerequisites section from `plans/$0-plan-subagent-prompts.md` and:

1. **Run each verification command** listed in the prerequisites
2. **Collect results** for each check (PASS/FAIL)
3. **Display summary to user:**

```
## Prerequisites Check

| Prerequisite | Status | Details |
|--------------|--------|---------|
| PostgreSQL on 5432 | PASS | pg_isready returned 0 |
| Redis on 6379 | FAIL | Connection refused |
| DATABASE_URL set | PASS | Variable is set |
| node_modules exists | PASS | Directory found |
```

4. **If any prerequisite FAILS:**
   - Display what failed and how to fix it
   - **Ask user:** "Prerequisites failed. Fix and retry, or stop?"
     - Retry → re-run verification checks
     - Stop → halt execution

5. **If all prerequisites PASS:**
   - Display success summary
   - **Ask user:** "All prerequisites verified. Start execution?"
     - Continue → proceed to execution loop
     - Stop → halt execution

## Step 2: Execution Loop

Read `plans/$0-plan-subagent-prompts.md` and for each subagent section:

### 2a. Pre-Phase Confirmation
**Ask user:** "About to start Phase N: [Task Name]. Proceed?"
- Continue → start the phase
- Stop → halt execution

### 2b. Execute Phase
- **Spawn** the subagent using the Task tool with the section's prompt
- **Wait** for completion
- **Verify** by running relevant tests

### 2c. Handle Result

**On PASS:**
- Mark `[x]` in `plans/$0-plan.md`
- Append success summary to report
- **Ask user:** "Phase N complete. Review above and continue?"
  - Continue → proceed to next phase
  - Stop → halt execution

**On FAIL:**
- Auto-retry up to 2 times (no confirmation needed)
- If still failing after 2 automatic retries:
  - Append failure details to report
  - **Ask user:** "Phase N failed after 2 retries. How to proceed?"
    - Retry → attempt another fix
    - Stop → halt execution (modify the plan and restart)

## Report Format (`plans/$0-plan-report.md`)

```
# Execution Report: $0

## Prerequisites
- Verified: [timestamp]
- All checks passed: YES/NO

## Phase 1: [Task Name]
- Status: PASS | FAIL
- Files modified: [list]
- Summary: [what was done]
- Retries: [0/1/2/N]
- Errors: [if any]

## Phase 2: [Task Name]
...
```

## Rules

- **Verify prerequisites FIRST** — ask user if any fail
- Ask confirmation BEFORE starting each phase
- Ask confirmation AFTER each phase completes (for review)
- Execute SEQUENTIALLY, never in parallel
- 2 automatic retries on failure, then ask for user decision
- No skip option — failed phases must be fixed or execution stopped
- Each subagent is isolated (no shared context)
