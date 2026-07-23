---
name: update-docs
description: Check and update project documentation to align with recent code changes
disable-model-invocation: true
argument-hint: [plan-name (optional)]
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Agent
---

# Update Documentation

Check and update project documentation files to align with recent code changes.

## Configuration

Read the docs manifest from `docs/docs-manifest.yaml` in the project root.
This file lists all documentation files that must stay aligned with the codebase.

If the manifest file does not exist, **STOP** and tell the user to create it
(show the expected format from this skill's README).

## Step 1: Load Manifest

Read `docs/docs-manifest.yaml` and parse the file lists:

- `primary` — Core project docs (always checked)
- `specs` — Specification/design docs
- `docs` — User-facing documentation
- `scan_dirs` — Directories to scan for additional files not listed above

For `scan_dirs` entries, list all `.md` files in those directories and add
them to the check list (excluding files already in primary/specs/docs).

## Step 2: Determine What Changed

Determine recent code changes using one of these strategies (in priority order):

1. **If a plan name argument is provided** (`$ARGUMENTS[0]`):
   Read `plans/$0-plan.md` and `plans/$0-plan-report.md` to understand
   what was changed. Use the plan's file list and change descriptions.

2. **If no argument provided**:
   Use `git diff HEAD~1..HEAD --name-only` and `git diff HEAD~1..HEAD --stat`
   to identify recently changed files and the scope of changes.
   If that yields nothing useful, use `git log --oneline -5` for broader context.

## Step 3: Check Each Documentation File

For each file in the manifest:

1. **Read** the documentation file
2. **Compare** against the code changes identified in Step 2
3. **Determine** if the doc is aligned or needs updates
4. **If misaligned**: Apply the minimal edit needed to bring it into alignment
5. **If aligned**: Skip (do not touch)

### What to check for:

- **New models/classes/functions** added but not documented
- **Removed or renamed** entities still referenced in docs
- **Changed behavior** (e.g., new fields, changed defaults, new env vars)
- **New files or directories** not reflected in project structure sections
- **Outdated examples** that reference old code patterns
- **Test count changes** (update if docs mention specific counts)

### What NOT to do:

- Do not rewrite sections that are already correct
- Do not add speculative documentation for unimplemented features
- Do not change formatting, style, or structure unless required by the update
- Do not update version numbers or dates unless explicitly wrong

## Step 4: Report

After checking all files, display a summary:

```
## Documentation Update Summary

| File | Status | Changes |
|------|--------|---------|
| CLAUDE.md | UPDATED | Added WriterContent to state models section |
| specs/orchestrator-design.md | ALIGNED | No changes needed |
| docs/adding-entities.md | ALIGNED | No changes needed |
| docs/prompt_translation_guide.md | UPDATED | Added WriterContent to JSON keys list |
```

If any files were updated, list the specific changes made to each.

## Rules

- **Read before writing** — always read each doc file before deciding if it needs changes
- **Minimal edits** — only change what is actually misaligned
- **Preserve voice** — match the existing writing style of each document
- **Skip aligned files** — do not make unnecessary edits
- **Use subagents** for checking multiple independent files in parallel when there are 4+ files
