# Summary: 012 Search by arXiv id

**Date:** 2026-09-03
**Status:** Done

## What changed

Search formulate may use `id:`. When the task or student query contains an arXiv id, the query must be exactly `id:NNNN.NNNNN` (no title/abstract AND). Retrieve-only body terms (equations, tables, BLEU, Transformer-big) must not be ANDed into `ti:`/`abs:`. `formulate_human` now receives the student query so the id is visible even if the planner omitted it.

## Verification

- Prompt + `formulate_human` student-query injection: `ok`
- Live `id:1706.03762` returns that paper (n=1): `ok`

## Commit

(not created — commit when asked)
