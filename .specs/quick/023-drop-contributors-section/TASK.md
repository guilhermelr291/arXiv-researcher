# Quick Task 023: Drop Contributors section at HTML parse

**Date:** 2026-09-11
**Status:** Done

## Description

`parse_arxiv_html` already removes bibliography, authors, and acknowledgements. Numbered **Contributors** end-matter (people lists) still became prose, e.g. `2609.11929v1` §7. Drop that heading/section in the library parser used by retrieve ingest and by `scripts/arxiv_html_units.py`. Do not drop scientific **Contributions** sections.

## Files Changed

- `src/plan_based_researcher/ingest/html_parse.py` — end-matter heading matcher includes Contributors
- `tests/test_html_parse.py` — Contributors dropped; Contributions kept; acknowledgements still dropped
- `.specs/quick/023-drop-contributors-section/` — this task

## Verification

- [x] `uv run python -m unittest tests.test_html_parse` (3 tests, OK)
- [x] Local `2609.11929v1` HTML parse has no Contributors people list (`Dahua Lin` absent; Conclusion kept). Contents still has a TOC link to §7.

## Commit

Not created unless requested.
