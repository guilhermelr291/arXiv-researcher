# Quick Task 016: LangSmith span on Voyage rerank fallback

**Date:** 2026-09-06
**Status:** Done

## Description

Emit a LangSmith child span for Voyage scoring and for the ensemble-order fallback so a RateLimitError (or any runtime score failure) is visible on the retrieve trace, not only in the uvicorn log.

## Files Changed

- `src/plan_based_researcher/ingest/rerank.py` — `@traceable(name="voyage_rerank")` on `score_chunks`; `process_inputs` drops `api_key` and logs query + chunk ids
- `src/plan_based_researcher/agents/retrieve.py` — `async with trace("rerank")` around score + pack; outputs `strategy=voyage|ensemble_order`, `error_type` / `error` on fallback

## Verification

- [x] `is_traceable_function(score_chunks)` is true
- [x] `_voyage_rerank_inputs` omits `api_key` and does not leak the secret string
- [x] `RetrieveRunner.run` source contains `async with trace(` and records `ensemble_order`
- [ ] Next retrieve UAT: LangSmith shows `rerank` under `execute`, with child `voyage_rerank` (error on RPM/TPM fail) and parent outputs `strategy=ensemble_order`

## Commit

(not created — commit when asked)
