# Quick Task 019: English Voyage rerank query

**Date:** 2026-09-06
**Status:** Done

## Description

Stop Portuguese retrieve tasks from becoming the Voyage rerank query by locking the planner to emit English `task`/`reasoning` (after the student query, with a counterexample). Voyage still uses `build_rerank_query(task, feedback)` — no language sniffing in retrieve.

## Files Changed

- `src/plan_based_researcher/agents/planner.py` — shared English lock + few-shot; repeated after Query / Student query
- `tests/test_internal_english.py` — lock strings for the planner prompt

## Verification

- [x] Planner source requires English and forbids copying the query language
- [x] Retrieve has no `english_rerank_task` / word-list detector
- [x] `python -m unittest tests.test_internal_english -v`

## Commit

(not created — commit when asked)
