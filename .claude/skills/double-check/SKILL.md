---
name: double-check
description: Cross-check agaings the codebase current findings and implementation hypotesys
disable-model-invocation: true
allowed-tools: Read, Grep, Glob
---

# Double Check

double check against the codebase findings made so far and the current implementation hypotesys to:
- find blind spots
- find undesired side effects on other parts of the codebase
- garantee completeness
- garantee coherence

## Behavior

1. execute the 'double-check' request
2. get back for discussion afterward
