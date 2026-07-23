# read-the-docs

Read the documents listed in `docs/docs-manifest.yaml` representing the single source of truth for the project.

## Usage

```
/read-the-docs                          # List available categories (no docs loaded)
/read-the-docs <category>               # Read primary + that category's docs
/read-the-docs <cat1> <cat2>            # Read primary + multiple categories
/read-the-docs <cat1>, <cat2>, <cat3>   # Same, comma-separated also works
/read-the-docs all                      # Read all docs (full context)
```

## Categories

Categories and their associated files are defined in `docs/docs-manifest.yaml`.
The `primary` category is always loaded first; all other categories are loaded on demand.

## Prerequisites

A `docs/docs-manifest.yaml` file must exist in the project root with categorized doc paths.
