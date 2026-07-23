# prepare-plan

Analyze a plan's dependencies and generate subagent prompts for sequential execution.

## Usage

```
/prepare-plan <plan-name>
```

## Example

```
/prepare-plan my-feature
```

This will:
1. Read `plans/my-feature-plan.md`
2. Analyze dependencies between tasks
3. Group dependent tasks that cannot be split
4. **Identify prerequisites** (services, docker, env vars, dependencies, build steps)
5. Update the plan with dependency information
6. Create `plans/my-feature-plan-subagent-prompts.md` with prerequisites at the top

## Prerequisites

Before using this skill, you should have:
1. Created a plan file: `plans/<plan-name>-plan.md`
2. The plan should contain discrete tasks/phases to be implemented

## Files

| File | Purpose |
|------|---------|
| `plans/<name>-plan.md` | Input: The implementation plan (will be updated) |
| `plans/<name>-plan-subagent-prompts.md` | Output: Prerequisites + prompts for each subagent |

## What It Does

1. **Dependency Analysis:** Identifies which tasks depend on each other
2. **Grouping:** Tasks that share context or dependencies are grouped into single subagent prompts
3. **Prerequisites Extraction:** Identifies services, docker containers, environment variables, dependencies, and build steps needed
4. **Prompt Generation:** Creates self-contained prompts for each phase
5. **Plan Update:** Adds dependency information to the original plan

## Output File Structure

The generated `plans/<name>-plan-subagent-prompts.md` follows this structure:

```markdown
# Prerequisites

Before executing any phase, ensure:

## Services
- [ ] PostgreSQL running on port 5432 (verify: `pg_isready -h localhost -p 5432`)

## Docker
- [ ] Run `docker-compose up -d` (verify: `docker-compose ps`)

## Environment
- [ ] DATABASE_URL is set (verify: `test -n "$DATABASE_URL"`)

## Dependencies
- [ ] Run `npm install` (verify: `test -d node_modules`)

## Build
- [ ] Run `npm run build` (verify: `test -d dist`)

---

# Phase 1: [Task Name]
[subagent prompt]

# Phase 2: [Task Name]
[subagent prompt]
```

**Important:** Each prerequisite includes a verification command that execute-plan skills will run.

## Subagent Prompt Requirements

Each generated prompt will be:
- **Self-contained:** No assumed context from previous subagents
- **Testable:** Clear success criteria that can be verified
- **Independent:** Can run in isolation (unless grouped with dependencies)

## Related Skills

- `/execute-plan-auto <name>` — Execute subagents sequentially (unattended)
- `/execute-plan-confirm <name>` — Execute subagents with user confirmation after each step
