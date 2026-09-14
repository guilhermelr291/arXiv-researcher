# Retrieve writer-recall: parallel items + dataset mock search - checks

Profile: light
Plan: `.specs/features/retrieve-recall-parallel-mock/plan.md`

## Intent

12 checks in 3 slices · 3 one-way doors · 0 open

## Checks

Grouped by the spec's slices; numbering runs across the whole feature.

### S1 - At most five concurrent item runs · 3 files · 18 KB · ~5k

**C1** - A 6-item dataset never has more than 5 `graph.ainvoke` calls in flight (ARX16-01, AC 1)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_six_items_at_most_five_ainvoke_in_flight`

**C2** - A 3-item dataset starts every remaining `ainvoke` before the first one returns, and in-flight never exceeds 5 (ARX16-01, AC 2)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_three_items_overlap_under_cap`

**C3** - `report_from_item_runs` and `_write_report` run only after the item batch finishes; the item batch does not call them (ARX16-01, AC 3)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_cli_reports_after_item_batch`

**C4** - `runs[i].query` equals `dataset.items[i].query` for all 6 items when `ainvoke` completes in reverse start order (ARX16-01, AC 4)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_runs_align_to_dataset_order`

**C5** - When item index 2 raises, that `ItemRun.stop_reason` is `error`, the other five still finish, and `len(runs)` is 6 (ARX16-01, AC 5)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_one_raise_does_not_cancel_siblings`

**C6** - When item index 2 exceeds `timeout_seconds`, that `ItemRun.stop_reason` is `timeout`, the other items still finish, and `len(runs)` is 6 (ARX16-01, AC 6)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_one_timeout_does_not_cancel_siblings`

**C7** - Six items in one batch receive six distinct `thread_id` values (ARX16-01, AC 7)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_thread_ids_are_unique`

**C8** - Item batch uses `asyncio.Semaphore(5)` and `asyncio.gather(..., return_exceptions=True)` and does not use `asyncio.TaskGroup` (ARX16-01, door 2)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_batch_uses_semaphore_gather_not_taskgroup`

### S2 - Search is the dataset paper, not live arXiv · 2 files · 12 KB · ~3k

**C9** - The eval CLI passes `mock_arxiv_id=paper_report_key(dataset.arxiv_id, dataset.version)` into `ArxivPaperAdapter` and does not pass `settings.mock_arxiv_id` (ARX16-02, AC 8, door 1)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_cli_pins_mock_arxiv_id_to_dataset_paper`

**C10** - `ArxivPaperAdapter(mock_arxiv_id="2609.11929v1").search` returns one `PaperHit` with that arxiv id and version and does not call `export.arxiv.org` (ARX16-02, AC 9)
Proof: `uv run python -m unittest tests.test_arxiv_mock -k test_mock_search_returns_pinned_hit_without_http`

**C11** - That mock `search` logs `MOCK_ARXIV_ID=2609.11929v1; skipping live arXiv search` (ARX16-02, AC 10)
Proof: `uv run python -m unittest tests.test_arxiv_mock -k test_mock_search_logs_skip_line`

### S3 - Postgres pool sized for the cap · 1 file · 4 KB · ~1k

**C12** - The eval CLI `AsyncConnectionPool` is constructed with `max_size=5` (ARX16-03, AC 11, door 3)
Proof: `uv run python -m unittest tests.test_retrieve_recall_parallel -k test_cli_pool_max_size_is_five`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| Landing doors (3) | dataset mock pin C9 · Semaphore+gather C8 · pool `max_size=5` C12 | - |
| Item terminal kinds (3) | aligned success C4 · `stop_reason=error` C5 · `stop_reason=timeout` C6 | - |
| Dataset sizes vs cap (2) | N=6 cap 5 C1 · N=3 overlap C2 | - |
| Fan-out literals (2) | C8, table-driven over all 2 | - |
| Mock search observables (2) | pinned `PaperHit` C10 · skip log C11 | - |
| startup config: eval CLI (2 assemblies) | mock pin C9 · pool `max_size` C12 | - |

- Claims naming a log line or constructor kwarg: C9, C11, C12 - proofs assert those strings
- No other check claims more than the single case its proof exercises
- C8's table-driven proof asserts `Semaphore(5)` and `gather(..., return_exceptions=True)` and the absence of `TaskGroup` in the batch helper
- C3 proves report write is after the batch; it does not re-prove scoring

## Swept

- validation: C9 - mock id is `paper_report_key`, not Settings
- failure modes: C5, C6
- idempotency: n/a - this slice does not add a dedup key; a second CLI run writes a new timestamped report as today
- authorization: n/a - v1 has no auth (AD-008)
- concurrency: C1, C2, C7, C8
- data lifecycle: n/a - no migrate, wipe, or chunk DROP
- dependency failure: C5 - an item exception is captured; siblings finish; OpenAI/Voyage/Postgres errors on one item take that path
- state transitions: n/a - graph routing and `halt_before_writer` are unchanged
- observability: C11

## Handoff

Intended split, with the arithmetic, written before any code:

- S1–S3 ≈ `scripts/retrieve_writer_recall.py` + `eval/retrieve_recall.py` + `adapters/arxiv.py` (read) + two test modules ≈ 35 KB ≈ 9k tokens, under 150k — one builder
- Surface stays the eval CLI; FastAPI is out of scope so no HTTP slice to split on

- **Boundary:** C1-C12 closed at `a9cf032e5637c68af0c89c51f7e58d4c884e0306`
- **Settled mid-build:** `run_e2e_items` lives in `scripts/retrieve_writer_recall.py` because `src/plan_based_researcher/eval/` writes were blocked; no Landing change
- **Abandoned:** sibling `scripts/retrieve_item_batch.py` — extra import path for a script entrypoint
