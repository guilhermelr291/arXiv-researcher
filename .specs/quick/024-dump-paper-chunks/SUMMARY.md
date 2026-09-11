# Summary 024: Dump paper chunks for qrel labeling

`uv run python scripts/dump_paper_chunks.py 2609.01617v1` writes UTF-8 JSONL to `eval/retrieve/2609.01617v1/2609.01617v1.chunks.jsonl` (`chunk_id`, `chunk_index`, `kind`, `section`, `content`). `--array` writes `.chunks.json`. Missing paper or empty chunks exit 2.

Does not generate the qrel dataset `eval/retrieve/{id}v{ver}.json`. Tests: `uv run python -m unittest tests.test_dump_paper_chunks` (8 OK).
