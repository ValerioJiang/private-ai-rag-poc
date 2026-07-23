---
name: write-plan
description: Write execution-ready plan to file with full context for new session
disable-model-invocation: true
argument-hint: [plan-name]
allowed-tools: Read, Write, Edit, Task, Grep, Glob
---

# Write Plan: $ARGUMENTS[0]

We will NOT implement the plan in this session.
Instead the plan created so far will be written to file.
The plan written to file **will be implemented in a new session.**

To accomplish this we need to include in the plan written to file **all the information needed** to implement it.
The new session will have no prior context from this discussion.

## Output File

**Filename pattern:** `plans/YYYY-MM-DD-HHMM-$ARGUMENTS[0]-plan.md`

Example: `plans/2026-03-07-1423-API-refactor-plan.md`

**Existing file handling:**
- If a file with this name already exists → merge/update it
- If the plan was partially written to an internal workdir file during discussion → ignore it, create new output file

---

## Plan File Structure Requirements

The plan file MUST include all elements needed for unattended execution in a new session.

### Required Plan Sections

1. **Problem/Goal** - What problem does this solve
2. **Context** - Design decisions made, alternatives rejected, key assumptions
3. **Prerequisites** - Services, docker, environment, dependencies needed
4. **Design** - High-level design with schema/model definitions
5. **Implementation Phases** - Each phase with the structure below

---

### Prerequisites Section

Capture all setup requirements discussed during planning:

```markdown
## Prerequisites

Before executing any phase, ensure:

### Services
- [ ] PostgreSQL running on port 5432 (verify: `pg_isready -h localhost -p 5432`)
- [ ] Redis running on port 6379 (verify: `redis-cli ping`)

### Docker
- [ ] Run `docker-compose up -d` in project root
- [ ] Verify: `docker-compose ps` shows all services running

### Environment
- [ ] `DATABASE_URL` is set (verify: `echo $DATABASE_URL`)
- [ ] `API_KEY` is set (verify: `test -n "$API_KEY"`)

### Dependencies
- [ ] Virtual environment active (verify: `which python`)
- [ ] Dependencies installed (verify: `uv sync --extra dev`)

### Build/Setup
- [ ] Database migrations applied (verify: `alembic current`)
```

**Important:** Each prerequisite MUST include a verification command in parentheses.

---

### Context Section

Capture decisions and reasoning from the planning discussion:

```markdown
## Context

### Design Decisions
- Chose X over Y because [reason]
- Using pattern Z for [benefit]

### Alternatives Considered
- **Option A:** [description] - Rejected because [reason]
- **Option B:** [description] - Rejected because [reason]

### Assumptions
- Assumes the existing `FooService` handles [X]
- Assumes no breaking changes to public API

### Edge Cases Discussed
- When [condition], the system should [behavior]
```

---

### Phase Structure

Each implementation phase MUST follow this structure:

```markdown
### Phase N: [Phase Title]

**Status:** NOT_STARTED

**Read first (executor should read before implementing):**
- `path/to/file1.py` - understand existing class structure
- `path/to/file2.py` - see current implementation pattern
- `tests/test_file.py` - understand existing test patterns

**Files to modify:**
- `path/to/file1.py`
- `path/to/file2.py`

**Changes:**

- [ ] **N.1** [Description of change]:
  ```python
  # Concrete code snippet showing EXACTLY what to add/modify
  class NewClass(BaseModel):
      field: str
  ```

- [ ] **N.2** [Description of change]:
  ```python
  # Another concrete code snippet
  ```

- [ ] **N.3** Add test `test_something` to `tests/test_file.py`:
  ```python
  def test_something():
      """Test description."""
      result = function_under_test()
      assert result == expected
  ```

**Verify:**
```bash
pytest tests/test_file.py -v
pytest tests/test_file.py -v -k "specific_test"
mypy src/module.py
```

**Phase Complete When:**
- [ ] All tests in `tests/test_file.py` pass
- [ ] No type errors (`mypy src/module.py`)
- [ ] [specific acceptance criterion for this phase]
```

---

## Checklist Requirements

Before finishing, verify the plan includes:

- [ ] **Problem/Goal** section explains the purpose
- [ ] **Context** section captures design decisions and assumptions
- [ ] **Prerequisites** section with verification commands
- [ ] Every step has a checkbox (`- [ ]`) with numbered identifier (1.1, 1.2, etc.)
- [ ] Every phase has `**Status:** NOT_STARTED`
- [ ] Every phase has `**Read first:**` section with file paths and reasons
- [ ] Every phase has `**Verify:**` section with explicit commands
- [ ] Every phase has `**Phase Complete When:**` checklist
- [ ] Code changes include **concrete code snippets** (not just descriptions)
- [ ] Test additions include **complete test code**
- [ ] Import statements are explicitly shown where needed

---

## Code Snippet Requirements

Code snippets must be:
- **Complete**: Show the full class/function, not just "add a field"
- **Contextual**: Include comments showing where in the file to add

**Bad example:**
```markdown
- [ ] Add `fetched_at` field to `FetchResult`
```

**Good example:**
```markdown
- [ ] **1.2** Add `fetched_at` field to `FetchResult` in `fetcher.py`:
  ```python
  class FetchResult(BaseModel):
      """Result of URL fetch."""
      success: bool
      content: str = ""
      error: Optional[str] = None
      url: str = ""
      title: Optional[str] = None
      fetched_at: str = ""  # ISO8601 timestamp  # NEW
      final_url: Optional[str] = None  # For redirect tracking  # NEW
  ```
```

---

## Workflow Summary

1. **Read all relevant source files** to understand existing code structure (needed for accurate code snippets)
2. **Capture prerequisites** from the planning discussion (services, docker, env vars)
3. **Capture context** (design decisions, alternatives rejected, assumptions)
4. **Write the plan file** with all required sections and structure
5. **Verify the checklist** before completing

---

## How This File Will Be Used

The plan file will be opened in a **new session without prior context**.
The executor must be able to implement it without asking clarifying questions.

- If the plan is small enough → execute directly in the new session
- If the plan is too large → the `prepare-plan` skill will split it into subagent prompts

The prerequisites section ensures the new session can verify the environment is ready before starting implementation.
