# Quick Task 018: Retrieve judge pass on core student request

**Date:** 2026-09-06
**Status:** Done

## Description

The retrieve LLM judge must pass when the keep-set covers the student query's core (pipeline/method), must not retry to hunt extra planner-task facets, and must set `plan_inadequate` when a facet is not in the paper — so T3 does not fire a second retrieve by default.

## Files Changed

- `src/plan_based_researcher/eval/strategies.py` — retrieve checklist + judge human: student query first; no retry for extra facets; `plan_inadequate` for paper holes
- `tests/test_internal_english.py` — lock strings for the new retrieve rules

## Verification

- [x] Checklist: pass on core student request; do not retry extra subsections; `plan_inadequate=true` when not in the paper
- [x] T3 query-miss rewrite sentence kept
- [x] `python -m unittest tests.test_internal_english -v`

## Commit

(not created — commit when asked)
