# Quick Task 021: Persist RAGAS reasoning in the repo

**Date:** 2026-09-09
**Status:** Done

## Description

Keep Faithfulness NLI verdicts and AnswerRelevancy generated questions (RAGAS collections drop these on `MetricResult`) and write JSON + Markdown under `reports/ragas/` so scores can be committed and compared over time.

## Files Changed

- `scripts/ragas_writer_report.py` — logged metric subclasses; stdout reasoning; default save to `reports/ragas/` (`--no-save`, `--out-dir`); optional LangSmith feedback comments
- `tests/test_ragas_report_script.py` — AST lock for persist + reasoning fields
- `reports/ragas/.gitkeep` — tracked empty archive directory

## Verification

- [x] `uv run python -m unittest tests.test_ragas_report_script`
- [ ] Live: `uv run python scripts/ragas_writer_report.py --run-id <trace> --limit 100` prints reasoning and writes `reports/ragas/*.json`

## Commit

Not created unless requested.
