# Summary: 023 Drop Contributors section at HTML parse

**Date:** 2026-09-11
**Status:** Done

`parse_arxiv_html` (retrieve ingest and `scripts/arxiv_html_units.py`) now drops end-matter **Contributors** sections the same way it drops Acknowledgements, including numbered titles such as `7 Contributors`. Scientific **Contributions** headings stay. Papers already in Postgres keep old chunks until a cache miss / re-ingest.
