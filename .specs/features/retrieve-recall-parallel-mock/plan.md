# Retrieve writer-recall: parallel items + dataset mock search

Sources:

- https://linear.app/arxiv-researcher/issue/ARX-16/paralelizar-retrieve-writer-recall-5-por-vez-e-mockar-o-paper-do - ticket: concurrency 5, dataset-pinned mock, pool size, report after all items, unittest isolation
- `.specs/features/retrieve-writer-recall/spec.md` / AD-024 / AD-025 - E2E graph through retrieve, Writer off, `run_e2e_item`, reports under `reports/retrieve/`
- `.specs/quick/015-mock-arxiv-search/TASK.md` - `ArxivPaperAdapter(mock_arxiv_id=...)` skips live search and HTML
- `.specs/project/STATE.md` AD-019 English internals, AD-010 ports, AD-005 arXiv-only - FastAPI still uses `Settings.mock_arxiv_id`; this feature is eval CLI only

## Problem

The operator scores a golden set of student queries with `scripts/retrieve_writer_recall.py`. Today that CLI awaits each item in a `for` loop, so wall time is the sum of N full graph runs. Search still follows `MOCK_ARXIV_ID` from `.env`. If that env is empty or points at a different paper than the dataset, `search` hits `export.arxiv.org` (rate limit, extra latency) even though preflight already required the scored paper and its chunks in Postgres. HTML fetch under mock returns `missing`, which is the intended cache-hit path; the live search call is not.

Ticket gives no conversion figure; the cost is operator time and arXiv 429s on a dataset that is already closed to one ingested paper.

When this ships, a dataset with N items still writes the same report shape, items run with a hard cap of 5 concurrent `ainvoke`s, search returns that dataset’s paper without calling arXiv, and one item’s exception does not cancel the others.

## Out of scope

| Excluded | Why |
| --- | --- |
| Live HTML ingest / `load_html` success in this CLI | ticket: paper+chunks already in Postgres; mock HTML stays `missing` |
| Changing `report_from_item_runs` scoring | ticket; Quick 022 hit rules stay |
| FastAPI `POST /research` / Chainlit / production `ArxivPaperAdapter` wiring | ticket: eval CLI only; API still uses `settings.mock_arxiv_id` |
| Unbounded fan-out against Voyage or OpenAI | ticket: ceiling is 5 |
| ARX-14 retriever metrics / ARX-13 retry-vs-first-pass metric | related, not this slice |
| New CLI flags (`--concurrency`) | ticket freezes 5; a flag is extra surface |
| `asyncio.TaskGroup` for the item batch | sibling cancel on first exception contradicts the ticket |

## Assumptions

| Assumption | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Concurrency constant | 5, not a CLI flag | ticket “lotes de 5” / “teto fixo de 5” | n |
| Pool `max_size` | 5 | matches the semaphore; default pool `max_size` is 4 and would stall 5 retrieves | n |
| Dataset mock pin | `paper_report_key(arxiv_id, version)` → `{arxiv_id}v{version}` passed as `mock_arxiv_id`; ignore `settings.mock_arxiv_id` in this CLI | ticket: do not depend on `.env` being right | n |
| One compiled graph | share one `ResearchGraph(..., checkpointer=None, halt_before_writer=True)` across items; distinct `thread_id` per item | compile is expensive; LangGraph `ainvoke` is per-config; checkpointer is already None | n |
| Item batch primitive | `asyncio.gather(..., return_exceptions=True)` plus `asyncio.Semaphore(5)` | gather keeps input order; `return_exceptions=True` does not cancel siblings | n |
| `--item-id` | same bounded runner with a 1-item list | existing flag; no special-case sequential path | n |
| tlc-spec-lean profile | `light` (project has no profile pin in `AGENTS.md`) | default of the skill; CLI has no UI | n |

**Open questions:** none - all resolved or logged above.

## Criteria

### S1: At most five concurrent item runs (P1)

**Acceptance Criteria**

1. WHEN the E2E CLI runs a dataset with more than 5 items THEN the system SHALL have at most 5 `graph.ainvoke` calls in flight at any time
2. WHEN the E2E CLI runs a dataset with 5 or fewer items THEN the system SHALL start every remaining item without waiting for an earlier item to finish, still under the cap of 5
3. WHEN every item `run_e2e_item` has finished (success, timeout `ItemRun`, or captured exception) THEN the system SHALL call `report_from_item_runs` once and SHALL NOT write `reports/retrieve` JSON/Markdown before that call
4. WHEN item i in `dataset.items` finishes THEN `runs[i]` SHALL be that item’s `ItemRun` (same index alignment `report_from_item_runs` already requires)
5. WHEN `run_e2e_item` raises THEN the system SHALL append an `ItemRun` with `stop_reason="error"` for that item and SHALL NOT cancel other in-flight items
6. WHEN `run_e2e_item` hits `research_timeout_seconds` THEN that item SHALL keep today’s timeout `ItemRun` (`stop_reason="timeout"`) and other items SHALL continue
7. WHEN two items run in the same CLI process THEN each SHALL use a distinct `thread_id`

**Independent test:** fake `ResearchGraph.ainvoke` that records max in-flight (hold a barrier past 5 starts), N=6 queries, assert max concurrent == 5, `len(runs)==6`, order of queries matches `dataset.items`; one fake raise in the middle still yields 6 runs and the others complete.

### S2: Search is the dataset paper, not live arXiv (P1)

**Acceptance Criteria**

8. WHEN the CLI constructs `ArxivPaperAdapter` THEN `mock_arxiv_id` SHALL be `{dataset.arxiv_id}v{dataset.version}` and SHALL NOT be `settings.mock_arxiv_id`
9. WHEN that adapter `search` runs THEN it SHALL return one `PaperHit` for that arxiv id and version and SHALL NOT call `export.arxiv.org`
10. WHEN that adapter `search` runs THEN the process SHALL log `MOCK_ARXIV_ID={arxiv_id}v{version}; skipping live arXiv search` with the dataset paper key (existing logger format in `adapters/arxiv.py`)

**Independent test:** construct the adapter with a dataset key other than env; `search` returns that id; no HTTP (adapter mock path). CLI source or helper asserts the pin string is `paper_report_key`, not `Settings.mock_arxiv_id`.

### S3: Postgres pool sized for the cap (P1)

**Acceptance Criteria**

11. WHEN the CLI opens `AsyncConnectionPool` THEN `max_size` SHALL be 5

**Independent test:** inspect pool constructor kwargs in the CLI module (import or AST); no live Postgres.

## Traceability

| ID | Slice | Criteria | Status |
| --- | --- | --- | --- |
| ARX16-01 | S1 | 1, 2, 3, 4, 5, 6, 7 | Pending |
| ARX16-02 | S2 | 8, 9, 10 | Pending |
| ARX16-03 | S3 | 11 | Pending |

## Observable

| Surface | Decision | Landing |
| --- | --- | --- |
| command `scripts/retrieve_writer_recall.py` | flags and defaults | existing - `--dataset`, `--item-id`, `--no-save`, `--out-dir` unchanged; concurrency is not a flag |
| command `scripts/retrieve_writer_recall.py` | output format | AC 3 - same JSON/Markdown after all items; `report_from_item_runs` unchanged |
| command `scripts/retrieve_writer_recall.py` | verbosity | AC 10 - existing mock warning log |
| command `scripts/retrieve_writer_recall.py` | exit codes | existing - process exit 2 on preflight (paper/chunks/qrels/`--item-id`); 0 after scoring even when some items are `error`/`timeout` |
| command `scripts/retrieve_writer_recall.py` | fail halfway | AC 5, 6 - per-item capture; no sibling cancel |
| screen | n/a - Chainlit out of scope | n/a - no UI work |
| API `POST /research` | response shape | n/a - FastAPI unchanged |
| API `POST /research` | error shape and codes | n/a - FastAPI unchanged |
| API `POST /research` | who may call it | n/a - FastAPI unchanged |
| API `POST /research` | versioning | n/a - FastAPI unchanged |
| API `POST /research` | rate limit | n/a - FastAPI unchanged; eval ceiling is AC 1 |

## Flow

Reuses `run_e2e_item`, `report_from_item_runs`, `paper_report_key`, `ArxivPaperAdapter` mock path, `ResearchGraph` with `halt_before_writer=True` and `checkpointer=None`, and preflight on `PgChunkRepository`. Does not add a graph node or change scoring.

1. operator args + dataset path -> `scripts/retrieve_writer_recall.py` (exists) - `load_dataset` / `filter_dataset` (`retrieve_recall.py`, exists)
2. preflight -> `PgChunkRepository` (exists) - paper, chunks, qrel ids; exit 2 if missing
3. `paper_report_key` (exists) -> `ArxivPaperAdapter` (exists, door 1) - mock search hit for the dataset paper
4. one `ResearchGraph` (exists) compiled with `halt_before_writer=True`, `checkpointer=None`
5. each `dataset.items` row -> `run_e2e_item` (exists) under `asyncio.Semaphore(5)` + `asyncio.gather(..., return_exceptions=True)` (door 2); pool `max_size=5` (door 3)
6. out: `report_from_item_runs` (exists) then stdout Markdown and optional `reports/retrieve/` files

## Relations

None - no stored-data shape change

## Surface

None - nothing consumed outside

## Landing

| One-way door | Literal shape | Alternative rejected |
| --- | --- | --- |
| Eval CLI pins mock search to the dataset paper | `ArxivPaperAdapter(mock_arxiv_id=paper_report_key(dataset.arxiv_id, dataset.version))` | Keep `settings.mock_arxiv_id` - env can be empty or a different paper, so search still hits `export.arxiv.org` |
| Item fan-out cap | `asyncio.Semaphore(5)` and `asyncio.gather(..., return_exceptions=True)` around `run_e2e_item` | `asyncio.TaskGroup` - first exception cancels siblings; unbounded `gather` - no Voyage/OpenAI ceiling |
| Pool sized to the cap | `AsyncConnectionPool(..., max_size=5)` in this CLI only | Default pool `max_size` (4) - five concurrent retrieves can wait forever for a connection |

- Nothing else in this change is hard to reverse (no schema, no HTTP contract, no new dependency)

## Impact

| Front | What changes |
| --- | --- |
| domain | no new term; `MOCK_ARXIV_ID` log line stays the adapter’s existing warning; pin source for this CLI is the dataset paper key, not Settings |
| domain | existing term: `thread_id` still means one LangGraph config per item; now issued concurrently, still unique |
| stored data | nothing to migrate; preflight still requires paper+chunks already in Postgres |
| FastAPI | unchanged: production adapter still uses `settings.mock_arxiv_id` |
| Policy / scoring | unchanged |
