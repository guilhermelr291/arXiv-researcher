# Quick Task 022: Count expanded table/equation as writer-pack recall

**Date:** 2026-09-11
**Status:** Done

## Description

Product Recall@k treats a qrel table or equation as a hit when `expand_hits` inlined its body into another packed excerpt, and the report annotates that injection.

## Files Changed

- `src/plan_based_researcher/eval/retrieve_recall.py` — writer-visible hit + injected annotation
- `scripts/retrieve_writer_recall.py` — pass ingested qrel atoms into scoring
- `tests/test_retrieve_recall.py` — unit coverage for id hits, injected hits, prose non-hits
- `.specs/features/retrieve-writer-recall/spec.md` — hit lock
- `.specs/features/retrieve-writer-recall/context.md` — decision 6
- `.specs/features/retrieve-writer-recall/design.md` — hit lock / out of scope
- `.specs/project/STATE.md` — AD-026

## Verification

- [x] `uv run python -m unittest tests.test_retrieve_recall` (11 tests, OK)
- [x] Table body in a host excerpt counts as Recall@k = 1.0 with an injected note
- [x] Direct `chunk_id` hit is unchanged and not annotated as injected

## Commit

Not created unless requested.
