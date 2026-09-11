# Summary 022: Expanded table/equation counts as recall

Product Recall@k now matches writer-visible evidence. If a table or equation qrel is missing from packed `chunk_id`s but its body was inlined into another excerpt (`expand_hits`), it is a hit. Markdown/JSON annotate `Injected: <qrel> (<kind>) into <host>`. Prose qrels stay id-equality.

CLI passes `qrel_atoms_from_chunks(stored)` after preflight so scoring stays offline (no extra Postgres in the scorer). Re-run `scripts/retrieve_writer_recall.py` to refresh `reports/retrieve/` — q06 should move from 0.000 to 1.000 with an injected note.

AD-026. Tests: `uv run python -m unittest tests.test_retrieve_recall` (11 OK).
