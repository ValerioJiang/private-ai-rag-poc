---
name: execute-plan-auto
description: Execute plan subagents sequentially (unattended mode)
disable-model-invocation: true
argument-hint: [plan-name]
allowed-tools: Read, Write, Edit, Task, Grep, Glob, Bash
---

# Execute Plan: $ARGUMENTS[0] (Unattended Mode)

Execute the implementation plan by running each subagent sequentially without user confirmation between steps.

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
   - **STOP execution** — do not proceed to phases
   - User must fix prerequisites and re-run the skill

5. **If all prerequisites PASS:**
   - Display success summary
   - Proceed to execution loop

## Step 2: Execution Loop

Read `plans/$0-plan-subagent-prompts.md` and for each subagent section:

1. **Spawn** the subagent using the Task tool with the section's prompt
2. **Wait** for completion
3. **Verify** by running relevant tests
4. **On PASS — update `plans/$0-plan.md`:**
   - Mark each completed step `[x]` (e.g., `- [ ] **1.1**` → `- [x] **1.1**`)
   - Mark each "Phase Complete When" item `[x]`
   - Set `**Status:** NOT_STARTED` → `**Status:** DONE`
   - Append success summary to report
   - Continue to next subagent
5. **On FAIL:**
   - Attempt fix (max 2 retries)
   - If fixed: mark pass and continue
   - If still failing: append failure to report and **STOP execution**

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
- Retries: [0/1/2]
- Errors: [if any]

## Phase 2: [Task Name]
...
```

## Rules

- **Verify prerequisites FIRST** — stop if any fail
- Execute phases SEQUENTIALLY, never in parallel
- STOP on unrecoverable failure (don't skip broken phases)
- Each subagent is isolated (no shared context)
- Max 2 fix attempts per phase before stopping
