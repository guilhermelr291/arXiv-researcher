# Quick Task 015: Mock arXiv search for cached UAT

**Date:** 2026-09-05
**Status:** Done

## Description

Skip live arXiv search/HTML when `MOCK_ARXIV_ID` is set so retrieve UAT can reuse cached chunks without rate limits.

## Files Changed

- `src/plan_based_researcher/adapters/arxiv.py` — pin `search` to one `PaperHit`; `load_html` returns `missing` (no network)
- `src/plan_based_researcher/config.py` — `mock_arxiv_id` from `MOCK_ARXIV_ID`
- `src/plan_based_researcher/main.py` — pass setting into `ArxivPaperAdapter`
- `.env` / `.env.example` — `MOCK_ARXIV_ID=2609.01617v1` (local UAT)

## Verification

- [x] `ArxivPaperAdapter(mock_arxiv_id="2609.01617v1").search(...)` returns that id/v1, allowlisted cats, no API call
- [x] `load_html` under mock returns `missing`
- [x] Empty `mock_arxiv_id` leaves `_mock` None (live path)
- [x] Postgres has chunks for `2609.01617` v1 (`paper_has_chunks` true, 43 rows)

## Commit

(not created — commit when asked)
