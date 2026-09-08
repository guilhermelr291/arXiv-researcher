# Quick Task 017: LangSmith chunk lists before and after rerank

**Date:** 2026-09-06
**Status:** Done

## Description

Log first-stage unique chunks and post-rerank (or fallback packed) chunks on the LangSmith `rerank` span, using one serializer so Voyage child inputs reuse the same shape.

## Files Changed

- `src/plan_based_researcher/ingest/rerank.py` — `chunks_for_trace`; `voyage_rerank` inputs use it (still strips `api_key`)
- `src/plan_based_researcher/agents/retrieve.py` — `rerank` inputs `chunks`; outputs `chunks` (packed) and `chunks_scored` (full Voyage order) with scores when present

## Verification

- [x] `chunks_for_trace` emits rank, chunk_id, kind, section, preview ≤240, optional score
- [x] `_voyage_rerank_inputs` includes `chunks` and omits `api_key`
- [x] `RetrieveRunner.run` traces `chunks_for_trace(unique)` and `chunks_scored`
- [ ] Next retrieve UAT: LangSmith `rerank` Inputs = first-stage list; Outputs `chunks` = keep-set; `chunks_scored` only on Voyage success

## Commit

(not created — commit when asked)
