# Quick Task 020: RAGAS Faithfulness max_tokens

**Date:** 2026-09-09
**Status:** Done

## Description

Stop `scripts/ragas_writer_report.py` from crashing on `IncompleteOutputException` when Faithfulness statement generation hits the judge `max_tokens` cap.

## Files Changed

- `scripts/ragas_writer_report.py` — `llm_factory(..., max_tokens=16384)` (override `RAGAS_MAX_TOKENS`); skip `IncompleteOutputException` like collections `ValueError`
- `tests/test_ragas_report_script.py` — AST lock that `max_tokens` is present

## Verification

- [x] `uv run python -m unittest tests.test_ragas_report_script` — 4 tests pass
- [ ] Re-run `uv run python scripts/ragas_writer_report.py --run-id 01a08757-496e-7160-b96d-3bdde26bc58d --limit 100` prints scores (or skip), does not traceback

## Commit

Included with `feat(eval): add LangSmith RAGAS Writer report script` (judge `max_tokens` + skip truncated output).
