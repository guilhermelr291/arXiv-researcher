# Quick Task 012: Search by arXiv id, no body terms in abstract

**Date:** 2026-09-03
**Status:** Done

## Description

Search formulation must use `id:` when the student query or task contains an arXiv id, and must not AND retrieve-only body terms (equations, tables, BLEU, Transformer-big) into `ti:`/`abs:`.

## Files Changed

- `src/plan_based_researcher/agents/search.py` — allow `id:`; forbid body-term AND; pass student query into formulate
- `src/plan_based_researcher/agents/query_schema.py` — optional `student_query` on `formulate_human`

## Verification

- [x] Prompt requires `id:NNNN.NNNNN` when an arXiv id is present and forbids retrieve-only AND
- [x] `formulate_human` includes the student query so the id is visible even if the planner omitted it
- [x] Live `id:1706.03762` returns that paper

## Commit

(not created — commit when asked)
