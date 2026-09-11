# Quick Task 024: Dump ingested chunks for recall qrels

**Date:** 2026-09-11
**Status:** Done

## Description

CLI dumps Postgres chunks for a paper as UTF-8 JSONL under `eval/retrieve/{arxiv_id}v{version}/{arxiv_id}v{version}.chunks.jsonl` so qrel labeling does not depend on ad-hoc `psql`.

## Files Changed

- `scripts/dump_paper_chunks.py` — parse `arxiv_id`/`version`, SQL dump to `eval/retrieve/`
- `tests/test_dump_paper_chunks.py` — id parse, row mapping, default output path (no DB)
- `.specs/quick/024-dump-paper-chunks/` — this task

## Verification

- [x] `uv run python -m unittest tests.test_dump_paper_chunks` (8 tests, OK)
- [x] Default path is `eval/retrieve/{id}v{ver}/{id}v{ver}.chunks.jsonl`; no `--out`

## Commit

Not created unless requested.
