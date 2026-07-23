# update-docs

Check and update project documentation to stay aligned with recent code changes.

## Usage

```
/update-docs                    # Auto-detect changes via git diff
/update-docs my-feature         # Use plan file to determine what changed
```

## Example

```
/update-docs 2026-03-05-03-writer-agent-remove-full-text
```

This will:
1. Read `docs/docs-manifest.yaml` for the list of documentation files
2. Read the plan and report to understand what changed
3. Check each documentation file for alignment
4. Update only misaligned files
5. Display a summary of what was updated

## Configuration

Create `docs/docs-manifest.yaml` in your project root:

```yaml
# Documentation files to keep aligned with code changes.
# Used by the /update-docs skill.
#
# Paths are relative to the project root.

# Core project documentation (always checked)
primary:
  - CLAUDE.md

# Specification and design documents
specs:
  - specs/orchestrator-design.md
  - specs/multiagent-system-spec.md

# User-facing documentation
docs:
  - docs/adding-entities.md
  - docs/prompt_translation_guide.md

# Directories to scan for additional doc files (*.md)
# Files already listed above are not checked twice.
scan_dirs:
  - docs/
```

### Manifest Sections

| Section | Purpose |
|---------|---------|
| `primary` | Core docs that almost always need updating (e.g., CLAUDE.md) |
| `specs` | Design/architecture specs — the "source of truth" |
| `docs` | How-to guides, references, onboarding docs |
| `scan_dirs` | Directories to scan for any `.md` files not explicitly listed |

All paths are relative to the project root.

## How It Determines What Changed

1. **With plan name argument**: Reads `plans/<name>-plan.md` and `plans/<name>-plan-report.md`
2. **Without argument**: Uses `git diff` to detect recent changes

## What It Checks

- New models, classes, or functions not yet documented
- Removed or renamed entities still referenced in docs
- Changed behavior (new fields, defaults, env vars)
- New files/directories missing from project structure sections
- Outdated examples referencing old patterns
- Test count discrepancies

## What It Does NOT Do

- Rewrite sections that are already correct
- Add documentation for unimplemented features
- Change formatting or style unnecessarily
- Touch files that are already aligned

## Related Skills

- `/prepare-plan <name>` — Create subagent prompts for a plan
- `/execute-plan-auto <name>` — Execute plan subagents (unattended)
- `/execute-plan-confirm <name>` — Execute plan subagents (with confirmation)
