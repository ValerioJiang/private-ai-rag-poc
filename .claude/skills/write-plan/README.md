# write-plan

Write an execution-ready plan to file with full context for implementation in a new session.

## Usage

```
/write-plan <plan-name>
```

## Example

```
/write-plan API-refactor
```

This will:
1. Read all relevant source files discussed during planning
2. Capture prerequisites (services, docker, env vars, dependencies)
3. Capture context (design decisions, alternatives rejected, assumptions)
4. Write `plans/2026-03-07-1423-API-refactor-plan.md` with all required sections

## When to Use

Use this skill at the end of a planning session when:
1. You've discussed and designed an implementation approach
2. You want to implement it in a **new session** (not the current one)
3. You need the plan to be **self-contained** (no prior context required)

## Workflow

```
Planning Session                          New Session
┌─────────────────────┐                  ┌─────────────────────┐
│ 1. Discuss feature  │                  │ 1. Open plan file   │
│ 2. Design approach  │                  │ 2. Verify prereqs   │
│ 3. /write-plan name │──── plan.md ────▶│ 3. Implement phases │
└─────────────────────┘                  └─────────────────────┘
```

## Files

| File | Purpose |
|------|---------|
| `plans/YYYY-MM-DD-HHMM-<name>-plan.md` | Output: Self-contained implementation plan |

## Output File Structure

The generated plan includes these sections:

```markdown
# Plan: <name>

## Problem/Goal
What problem does this solve

## Context
### Design Decisions
### Alternatives Considered
### Assumptions
### Edge Cases Discussed

## Prerequisites
### Services
### Docker
### Environment
### Dependencies
### Build/Setup

## Design
High-level design with schema/model definitions

## Implementation Phases

### Phase 1: [Title]
**Status:** NOT_STARTED
**Read first:** [files to read]
**Files to modify:** [file list]
**Changes:** [checkboxes with code snippets]
**Verify:** [test commands]
**Phase Complete When:** [acceptance criteria]

### Phase 2: [Title]
...
```

## Key Features

| Feature | Description |
|---------|-------------|
| **Self-contained** | New session needs no prior context |
| **Concrete code snippets** | Exact code to add/modify, not descriptions |
| **Verification commands** | Every phase has testable success criteria |
| **Prerequisites captured** | Services, docker, env vars from planning discussion |
| **Design context** | Decisions made, alternatives rejected, assumptions |

## Existing File Handling

- **File exists with same name:** Merge/update the existing file
- **Plan written to internal workdir during discussion:** Ignored, creates new output file

## Related Skills

- `/prepare-plan <name>` — Split large plan into subagent prompts for parallel execution
- `/execute-plan-auto <name>` — Execute plan phases sequentially (unattended)
- `/execute-plan-confirm <name>` — Execute plan with user confirmation after each phase
