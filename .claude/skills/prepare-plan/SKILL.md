---
name: prepare-plan
description: Analyze plan dependencies and create subagent prompts file
disable-model-invocation: true
argument-hint: [plan-name]
allowed-tools: Read, Write, Edit, Task, Grep, Glob
---

# Prepare Plan: $ARGUMENTS[0]

We will NOT implement the plan in this session.
Instead the plan, written to file, will be implemented as follows:
1. I will start a new session
2. I will ask to read the plan from file and implement it in the following way:
   "Implement each single (atomic) part of the plan in a spawned agent."

To accomplish this we need to:
- Analyze if "Run each single task of the plan in a separate sub-agent, sequentially"
  is possible or there are dependencies between "tasks" that force the implementation of
  more than one "phase" in a single "batch/sub-agent" (like for example a common context that
  would be missed if implemented in two separated sub-agents)
- Read and update the plan in `plans/$0-plan.md`
- **Identify prerequisites** from the current session context (services, docker containers,
  environment variables, dependencies, build steps, etc.)
- Write the prompts for each single sub-agent to file: `plans/$0-plan-subagent-prompts.md`
  **with a Prerequisites section at the top**

## Prerequisites to Identify

Extract from the current session context:
- **Services:** Databases, message queues, caches (e.g., PostgreSQL, Redis, RabbitMQ)
- **Docker:** Containers or docker-compose services that must be running
- **Environment:** Variables that must be set (without exposing secrets)
- **Dependencies:** Packages or tools that must be installed
- **Build steps:** Commands to run before testing (e.g., `npm install`, `npm run build`)
- **Other:** Any setup mentioned during plan discussion

## Output File Structure (`plans/$0-plan-subagent-prompts.md`)

The file MUST follow this structure:

```markdown
# Prerequisites

Before executing any phase, ensure:

## Services
- [ ] PostgreSQL running on port 5432 (verify: `pg_isready -h localhost -p 5432`)
- [ ] Redis running on port 6379 (verify: `redis-cli ping`)

## Docker
- [ ] Run `docker-compose up -d` in `/path/to/docker`
- [ ] Verify: `docker-compose ps` shows all services running

## Environment
- [ ] DATABASE_URL is set (verify: `echo $DATABASE_URL`)
- [ ] API_KEY is set (verify: `test -n "$API_KEY"`)

## Dependencies
- [ ] Run `npm install` (verify: `test -d node_modules`)

## Build
- [ ] Run `npm run build` (verify: `test -d dist`)

---

# Phase 1: [Task Name]
[subagent prompt]

# Phase 2: [Task Name]
[subagent prompt]
...
```

**Important:** Each prerequisite MUST include a verification command in parentheses.

## Context: How These Files Will Be Used

The generated files will be used in a separate session where:
- Prerequisites are verified automatically before execution starts
- Each subagent prompt is executed sequentially in isolation
- Tests must pass before proceeding to the next subagent
- A report file (`plans/$0-plan-report.md`) tracks execution results

Therefore, when creating subagent prompts:
- Each prompt must be fully self-contained (no assumed context from previous subagents)
- Dependencies between tasks must be identified and grouped appropriately
- Success criteria must be clear and testable
- **Prerequisites must include verification commands so the new session can check them**
