---
name: read-the-docs
description: Read documents representing the single source of truth for the codebase
disable-model-invocation: true
allowed-tools: Read, Grep, Glob
---

# Read the Docs

Read documents listed in @docs/docs-manifest.yaml to build codebase knowledge.

## How to use the manifest

Read `docs/docs-manifest.yaml` to discover available categories and their files.
The `primary` category is always read first; all other categories are loaded on demand.

## Behavior

1. Read `docs/docs-manifest.yaml`
2. If **no argument** was provided:
   - List the available categories (name + description from manifest comments) to the user
   - Do NOT read any doc files — return to prompt and wait for instructions
3. If **one or more categories** were provided (e.g., `/read-the-docs architecture` or `/read-the-docs architecture, configuration`):
   - Parse the argument as a list (split on commas and/or spaces, ignore extra whitespace)
   - Read all files in the `primary` category first
   - Then read the files in each requested category
4. If **`all`** was provided as argument:
   - Read all files in all categories
5. If the current session already has conversation history, focus on the theme currently discussed when choosing what to highlight from the docs
