# Retrieve Writer-Pack Recall Tasks

**Design**: `.specs/features/retrieve-writer-recall/design.md`  
**Spec**: `.specs/features/retrieve-writer-recall/spec.md`  
**Status**: Code-validated T1–T8 (2026-09-10; no commits). Full unittest discover 130/130. Live Independent Test still UAT (preflight green: paper ingested, 0 missing qrels; CLI not run).

`.specs/codebase/TESTING.md` does not exist. Same as writer-stream / SSE dispatcher: graph e2e (pytest, Testcontainers) is **out of scope**. Co-located **stdlib `unittest`** covers dataset load, Recall@k (already executed), report payload, dispatch halt, `ResearchGraph.ainvoke`, fake-graph `run_e2e_item`, CLI AST locks, and production source inspect. Live Independent Test (ingest `2609.01617v1`, CLI, no Writer execute) stays **UAT** after Execute (may be blocked by B-001). Do **not** call live OpenAI, Voyage, arXiv, or Postgres in unittest discover.

Do **not** change Gate, planner, search, retrieve, Writer, SSE names, Chainlit, `POST /research`, `execute.py`, or `AgentFactory`’s Writer registration. Isolated `RetrieveRunner` eval is **deleted**, not deferred. No new `GraphState` keys. No `interrupt_before`. Eval compile uses `checkpointer=None`. Items run **sequentially**.

**Local coverage matrix** (substitutes for missing TESTING.md):

| Code layer | Required test type | Parallel-safe |
| ---------- | ------------------ | ------------- |
| `eval/retrieve_recall.py` (load, scorer, report, `ItemRun`) | unit | Yes (file conflicts still serialize tasks) |
| `eval/retrieve/2609.01617v1.json` | unit (shipped load) | Yes |
| `graph/nodes/dispatch.py` | unit | Yes |
| `graph/build.py` / `graph/research_graph.py` | unit (`test_research_graph`) | Yes |
| `scripts/retrieve_writer_recall.py` | unit (`ast.parse`; no graph run) | Yes |
| `main.py` / `api/executor.py` / `graph/nodes/execute.py` / `agents/factory.py` / `scripts/draw_graph.py` | unit (source inspect) | Yes |
| Independent Test (live CLI) | UAT (not unittest) | No |

**Gate commands:**

| Gate | Command |
| ---- | ------- |
| quick (per task) | `uv run python -m unittest tests.<module>` |
| full (after T8) | `uv run python -m unittest discover -s tests` |

**Commit constraint:** Parallel `[P]` tasks must **not** each `git commit` (STATE lesson). T1 merges JSON + loader so `test_shipped_dataset_loads` never goes red. T6 without T4/T5 cannot compile the halt graph. T7 without T6 leaves the CLI importing deleted helpers.

---

## Execution Plan

### Phase 1: Foundation (parallel)

```
T1 [P]     T3 [P]
```

### Phase 2: Report + compile wiring (parallel after their deps)

```
T1 ──→ T2
T3 ──→ T4 [P with T2]
```

### Phase 3: Item runner (after report models)

```
T2 ──→ T5 [P with T4 if T4 still running]
T4 ──→ T8 [P with T5 / T6]
```

### Phase 4: CLI (needs halt compile + ItemRun)

```
T4, T5 ──→ T6
```

### Phase 5: Delete isolated leftover (sequential)

```
T6 ──→ T7
```

---

## Task Breakdown

### T1: Student-query dataset load + rewrite shipped JSON [P]

**What**: Rename dataset records to `items[].query` with a mandatory `arxiv_id` substring pin; rewrite the 15 DocuSearch rows so each `query` is still the student question and contains `2609.01617`.
**Where**: `src/plan_based_researcher/eval/retrieve_recall.py`; `eval/retrieve/2609.01617v1.json`  
**Tests file**: `tests/test_retrieve_recall.py`
**Depends on**: None
**Reuses**: `_nonempty_str`, existing `ValueError` style; keep `recall_at_k` / `chunk_ids_from_evidence` untouched
**Requirement**: RWR-01

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `RetrieveItem` (frozen) has `id`, `query`, `required_chunk_ids`, optional `question_type` / `reference_answer` (default `""`)
- [x] `RetrieveDataset.items` replaces `questions`; `RetrieveQuestion` / `questions` / item field `question` are gone from this module’s public load path
- [x] `load_dataset` requires `arxiv_id`, `version`, non-empty `items`; each item: `id`, `query`, non-empty `required_chunk_ids` (non-empty strings)
- [x] Load **fails** if `dataset.arxiv_id` is not a contiguous substring of that item’s `query` (`2609.01617v1` counts as containing `2609.01617`)
- [x] Load **fails** on empty `required_chunk_ids`, duplicate item ids, top-level `questions` as the list key, or an item that only has `question` (do **not** dual-read frozen-task `question`)
- [x] Optional passthrough kept when present: dataset `title`; item `question_type`, `reference_answer`
- [x] Shipped JSON: 15 items, `arxiv_id` `"2609.01617"`, `version` `"1"`; each `query` contains `2609.01617`; `required_chunk_ids` unchanged; **no** “use the article with id” glued on as a retrieve task
- [x] `missing_qrel_ids` takes the item sequence (`dataset.items`); `evaluate_writer_pack` still compiles (uses `item.query`) until T7 deletes it
- [x] `__all__` exports `RetrieveItem` (not `RetrieveQuestion`)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] `RecallAtKTest` (4) and `EvidenceIdsTest` (2) still pass unchanged
- [x] `test_shipped_dataset_loads`: `len(dataset.items) == 15`; every `query` contains `dataset.arxiv_id`; `DEFAULT_KS[-1] == Policy.retrieve_rerank_top_n`
- [x] Tempfile: empty `required_chunk_ids` → `ValueError`; missing pin → `ValueError`; `questions` key only → `ValueError`; item `question` without `query` → `ValueError`; duplicate ids → `ValueError`
- [x] `MissingQrelTest` uses `RetrieveItem(query=...)`
- [x] Isolated leftover tests (`RetrieveEvalStateTest`, `EvaluateWriterPackTest`) still collect (constructors updated to `items` / `query`) — deleted in T7
- [x] Gate check passes: `uv run python -m unittest tests.test_retrieve_recall`
- [x] Test count: **17** tests pass (13 existing + 4 new load rejects; no silent deletions)

**Verify**: `uv run python -c "from pathlib import Path; from plan_based_researcher.eval.retrieve_recall import load_dataset; d=load_dataset(Path('eval/retrieve/2609.01617v1.json')); assert all(d.arxiv_id in i.query for i in d.items) and len(d.items)==15"`

**Commit**: `feat(eval): load student-query retrieve dataset with arxiv pin`

---

### T2: Amend QuestionScore / RecallReport payload

**What**: Per-item report fields become `query`, `retrieve_task`, `admitted_papers`, `stop_reason`, `thread_id`; serialize the list as `"items"` (not `"questions"`).
**Where**: `src/plan_based_researcher/eval/retrieve_recall.py`  
**Tests file**: `tests/test_retrieve_recall.py`
**Depends on**: T1
**Reuses**: `_averages`, `_k_score`, `score_question` body; RAGAS-style JSON keys stay snake_case
**Requirement**: RWR-05, RWR-09

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `QuestionScore.query` replaces `question`; added fields: `retrieve_task: str`, `admitted_papers: tuple[dict, ...]`, `stop_reason: str`, `thread_id: str` (defaults `""` / `()` so leftover `evaluate_writer_pack` still builds rows)
- [x] `score_question` kwargs: `query=` (not `question=`); optional `retrieve_task`, `admitted_papers`, `stop_reason`, `thread_id`
- [x] `RecallReport.items` replaces `questions`
- [x] `report_as_dict` emits `"items"` with those fields plus delivered ids, hits, misses, scores; header still `arxiv_id`, `version`, `ks`, `macro`, `micro`
- [x] `report_markdown` lists per item: `query`, retrieve `task` if any, admitted keys, delivered ids, Recall@5/@10/@15, `retrieve_query_used`; expected paper is dataset `arxiv_id`+`version` in the header; heading is not “Questions”
- [x] Wrong admitted paper is still scored (no skip)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] `ScoreQuestionTest` uses `query=`
- [x] New tests: `report_as_dict` includes `query`, `retrieve_task`, `admitted_papers`, `stop_reason`, `thread_id`; top-level key is `items` not `questions`
- [x] Markdown contains the query, a retrieve task string, an admitted `arxiv_id`, and `retrieve_query_used` when set
- [x] `EvaluateWriterPackTest` assertions use `report.items` / payload `"items"` until T7
- [x] Gate check passes: `uv run python -m unittest tests.test_retrieve_recall`
- [x] Test count: **20** tests pass (17 from T1 + 3 report tests; no silent deletions)

**Verify**: `uv run python -c "import inspect; from plan_based_researcher.eval.retrieve_recall import score_question, report_as_dict; assert 'query' in inspect.signature(score_question).parameters"`

**Commit**: `feat(eval): report retrieve task, admitted papers, and stop_reason`

---

### T3: Dispatch halt before Writer execute [P]

**What**: When `halt_before_writer` and the first unpassed agent is `writer`, return `Command(update={"outcome": "done"}, goto="finalize")` without execute.
**Where**: `src/plan_based_researcher/graph/nodes/dispatch.py`  
**Tests file**: `tests/test_dispatch_halt.py` (new)
**Depends on**: None
**Reuses**: `_first_unpassed_index`, search-wave `Send` branch, destinations `("search", "execute", "finalize")`
**Requirement**: RWR-07, RWR-08 (default off)

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] Signature is `make_dispatch_node(*, halt_before_writer: bool = False)` — default **False**
- [x] After the existing search-wave branch, if `first` exists and `plan[first].agent == "writer"` **and** `halt_before_writer`: `return Command(update={"outcome": "done"}, goto="finalize")`
- [x] Do **not** set `step_index` into execute; do **not** append writer to `passed_steps`
- [x] Retrieve still `goto="execute"`; search waves unchanged; `max_steps` / unknown agent / empty plan unchanged
- [x] Halt False + writer still `goto="execute"` (student compile)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] Halt True + unpassed writer: `goto == "finalize"` and update `outcome == "done"`; `step_index` absent from update
- [x] Halt True + unpassed retrieve: `goto == "execute"`
- [x] Halt False + unpassed writer: `goto == "execute"`
- [x] Search wave still returns `Send` to `"search"` (halt True does not steal a search head)
- [x] No live LLM / Postgres
- [x] Gate check passes: `uv run python -m unittest tests.test_dispatch_halt`
- [x] Test count: **4** tests pass (no silent deletions)

**Verify**: `uv run python -c "import inspect; from plan_based_researcher.graph.nodes.dispatch import make_dispatch_node; assert inspect.signature(make_dispatch_node).parameters['halt_before_writer'].default is False"`

**Commit**: `feat(graph): halt dispatch before writer execute`

---

### T4: Thread `halt_before_writer` + `ResearchGraph.ainvoke`

**What**: Pass the halt flag through `build_graph` / `ResearchGraph`; add a thin `ainvoke` pass-through. Production call sites keep omitting the flag.
**Where**: `src/plan_based_researcher/graph/build.py`; `src/plan_based_researcher/graph/research_graph.py`  
**Tests file**: `tests/test_research_graph.py`
**Depends on**: T3
**Reuses**: existing `GraphDeps`, `initial_graph_state`, stub factory compile; `scripts/draw_graph.py` stays `build_graph(deps)` default
**Requirement**: RWR-06, RWR-08

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `build_graph(deps, checkpointer=None, *, halt_before_writer: bool = False)` passes the flag into `make_dispatch_node`
- [x] `ResearchGraph.__init__(..., *, halt_before_writer: bool = False)` forwards to `build_graph`
- [x] `ResearchGraph.ainvoke(self, input, config=None, **kwargs)` delegates to `self._compiled.ainvoke` (CLI only)
- [x] `astream_events` unchanged (executor still uses it)
- [x] No new `GraphState` keys; topology comments/edges unchanged
- [x] `main.py` / `draw_graph.py` **not** edited in this task (defaults keep Writer on)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] Existing 3 `ResearchGraphTest` methods still pass (`initial_graph_state` key set unchanged)
- [x] `ainvoke` is callable; monkeypatched `_compiled.ainvoke` receives the same `input` / `config`
- [x] `halt_before_writer=True` still compiles with the stub factory (no Postgres)
- [x] `inspect.signature(build_graph)` / `ResearchGraph.__init__` default `halt_before_writer` is `False`
- [x] Gate check passes: `uv run python -m unittest tests.test_research_graph`
- [x] Test count: **6** tests pass (3 existing + 3 new; no silent deletions)

**Verify**: `uv run python -c "import inspect; from plan_based_researcher.graph.build import build_graph; from plan_based_researcher.graph.research_graph import ResearchGraph; assert 'halt_before_writer' in inspect.signature(build_graph).parameters; assert hasattr(ResearchGraph, 'ainvoke')"`

**Commit**: `feat(graph): compile halt_before_writer and expose ainvoke`

---

### T5: `ItemRun` + `run_e2e_item` (fake graph)

**What**: One graph snapshot per golden item: `ainvoke(initial_graph_state(query))` under timeout; derive retrieve task, admitted papers, and `stop_reason`.
**Where**: `src/plan_based_researcher/eval/retrieve_recall.py`  
**Tests file**: `tests/test_retrieve_e2e_item.py` (new)
**Depends on**: T2
**Reuses**: `score_question`, `ResearchGraph.initial_graph_state` shape (fake graph records `ainvoke` args; **no** Voyage/Postgres)
**Requirement**: RWR-06, RWR-09

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] Frozen `ItemRun`: `query`, `thread_id`, `outcome`, `stop_reason`, `evidence_chunks`, `retrieve_query_used`, `retrieve_task`, `admitted_papers`, `plan`
- [x] `async def run_e2e_item(graph, *, query, thread_id, timeout_seconds) -> ItemRun` calls `ainvoke(graph.initial_graph_state(query), config={"configurable": {"thread_id": thread_id}, "metadata": {"eval": "retrieve-writer-recall"}})` inside `asyncio.wait_for`
- [x] Timeout / cancel: empty `evidence_chunks`, `stop_reason="timeout"`
- [x] Success: copy `evidence_chunks`, `papers`, `plan`, `passed_steps`, `retrieve_query_used`, `outcome`, `error_message` from returned state
- [x] `extract_retrieve_task(plan, passed_steps) -> str` — task text of the **last passed** `agent=="retrieve"` step; `""` if none
- [x] `admitted_paper_keys(papers) -> list[dict]` — `{arxiv_id, version}` per entry
- [x] `stop_reason_from_state(state, *, timed_out: bool) -> str` matches the design table (`timeout`, `refused`, `error`, `insufficient`, `writer_skipped`, `writer_ran`)
- [x] Helper to build `QuestionScore` / `RecallReport` from dataset + `ItemRun`s (CLI must not reimplement averaging)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] Fake graph: `ainvoke` input `query` equals the item query; `config["configurable"]["thread_id"]` is the fresh id
- [x] Returned `evidence_chunks` scored via existing `score_question` (no LLM)
- [x] Timeout path: fake `ainvoke` that sleeps past timeout → `stop_reason=="timeout"`, empty delivered ids
- [x] `extract_retrieve_task`: last passed retrieve; none → `""`
- [x] `stop_reason_from_state`: one test each for `writer_skipped` (done + writer not in `passed_steps`) and `writer_ran`
- [x] Gate check passes: `uv run python -m unittest tests.test_retrieve_e2e_item`
- [x] Test count: **8** tests pass (no silent deletions)

**Verify**: `uv run python -c "from plan_based_researcher.eval.retrieve_recall import run_e2e_item, stop_reason_from_state, extract_retrieve_task, admitted_paper_keys, ItemRun"`

**Commit**: `feat(eval): snapshot e2e retrieve items without Writer`

---

### T6: E2E CLI (Writer off)

**What**: Operator script compiles `ResearchGraph(..., halt_before_writer=True)`, preflights qrels, runs items sequentially, writes `reports/retrieve/`.
**Where**: `scripts/retrieve_writer_recall.py`  
**Tests file**: `tests/test_retrieve_recall_script.py`
**Depends on**: T4, T5
**Reuses**: leftover preflight (`get_paper` / `paper_has_chunks` / `list_chunks` / `missing_qrel_ids`); `_write_report` stamp + `index.jsonl`; RAGAS `--no-save` / `--out-dir`; Windows `WindowsSelectorEventLoopPolicy`; lifespan DI in `main.py` (`AgentFactory` + `GraphDeps` + eval strategies with `settings.openai_api_key`)
**Requirement**: RWR-04, RWR-05, RWR-06, RWR-07, RWR-09

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] Description: E2E graph through retrieve, Writer off — **not** “frozen RetrieveRunner”
- [x] Args unchanged: `--dataset` (default `eval/retrieve/2609.01617v1.json`), `--no-save`, `--out-dir` (default `reports/retrieve`)
- [x] Preflight **before** any `ainvoke`: paper missing / no chunks / `missing_qrel_ids` non-empty → stderr, exit **2**
- [x] `ResearchGraph(deps, checkpointer=None, halt_before_writer=True)`; one compiled graph; sequential items; fresh `thread_id` per item; timeout `Settings.research_timeout_seconds` **per item**
- [x] Factory constructed like lifespan (includes `WriterRunner` via `AgentFactory`); do **not** `factory.create("retrieve")` as the SUT; do **not** use `ResearchExecutor`
- [x] Do **not** set or clear `MOCK_ARXIV_ID`
- [x] Scoring success: stdout Markdown + files; process exit **0** even if every Recall@k is 0.0
- [x] Per-item unexpected exception after preflight: `stop_reason="error"` and continue; compile/settings failure: non-zero exit (not a recall code)
- [x] Filename stamp still `{scored_at}_{arxiv_id}v{version}` plus `index.jsonl` append

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] AST: `halt_before_writer=True`, `ResearchGraph`, `run_e2e_item` or `ainvoke`, `WindowsSelectorEventLoopPolicy`, `reports/retrieve`, `index.jsonl`, `missing_qrel_ids`, `GraphDeps`, `checkpointer=None`
- [x] AST: **not** `evaluate_writer_pack`, **not** `retrieve_eval_state`, **not** `factory.create("retrieve")`
- [x] AST: **not** `ResearchExecutor` / `answer_delta` as consume path
- [x] Drop / invert `test_planner_and_search_stay_out` (planner/search **are** on this path via the compiled graph)
- [x] Gate check passes: `uv run python -m unittest tests.test_retrieve_recall_script`
- [x] Test count: **3** tests pass (no silent deletions)

**Verify**: `uv run python -m ast tests/test_retrieve_recall_script.py` is not the gate — run the unittest module above and grep the script for `evaluate_writer_pack` → no matches

**Commit**: `feat(eval): e2e retrieve recall CLI through production graph`

---

### T7: Delete isolated RetrieveRunner harness

**What**: Remove `retrieve_eval_state` and `evaluate_writer_pack` (and their tests). Scorer, preflight helper, and reports stay.
**Where**: `src/plan_based_researcher/eval/retrieve_recall.py`  
**Tests file**: `tests/test_retrieve_recall.py`
**Depends on**: T6
**Reuses**: `recall_at_k`, `score_question`, `missing_qrel_ids`, report writers
**Requirement**: RWR-03 (cancelled)

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `retrieve_eval_state` and `evaluate_writer_pack` deleted; not in `__all__`
- [x] Module docstring no longer claims frozen RetrieveRunner as the SUT
- [x] `paper_ref_from_record` may remain if still used; do not delete `missing_qrel_ids`

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] `RetrieveEvalStateTest` and `EvaluateWriterPackTest` **deleted** (cancelled path — not a silent skip)
- [x] `RecallAtKTest` 4/4 still pass; load + report tests from T1/T2 still pass
- [x] Importing `evaluate_writer_pack` / `retrieve_eval_state` raises `ImportError`
- [x] Gate check passes: `uv run python -m unittest tests.test_retrieve_recall`
- [x] Test count: **17** tests pass (20 from T2 minus 3 isolated tests; no silent deletions of RWR-02)

**Verify**: `uv run python -c "from plan_based_researcher.eval import retrieve_recall as m; assert not hasattr(m, 'evaluate_writer_pack') and not hasattr(m, 'retrieve_eval_state')"`

**Commit**: `refactor(eval): remove isolated RetrieveRunner recall harness`

---

### T8: Production freeze source inspect [P]

**What**: Prove the student path still executes Writer: lifespan omits halt, executor still `astream_events`, execute still allows `writer`, factory still registers Writer.
**Where**: no production edits except what T4 already defaulted  
**Tests file**: `tests/test_retrieve_production_freeze.py` (new)
**Depends on**: T4
**Reuses**: `tests/test_research_executor.py` astream_events lock; `inspect.getsource`
**Requirement**: RWR-08

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `main.py` source does not pass `halt_before_writer=True`
- [x] `scripts/draw_graph.py` does not pass `halt_before_writer=True`
- [x] `ResearchExecutor.execute` still calls `astream_events` only (no `ainvoke`)
- [x] `execute.py` still allows `agent == "writer"` / `("retrieve", "writer")`
- [x] `AgentFactory` still constructs `WriterRunner` for `"writer"`
- [x] `ui/app.py` / `api/routes.py` / `agents/writer.py` not edited by this feature (inspect: no `halt_before_writer`)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] One inspect test per bullet above (can be methods on one class)
- [x] Gate check passes: `uv run python -m unittest tests.test_retrieve_production_freeze`
- [x] Test count: **6** tests pass (no silent deletions)

**Verify**: `uv run python -c "from pathlib import Path; s=Path('src/plan_based_researcher/main.py').read_text(encoding='utf-8'); assert 'halt_before_writer=True' not in s"`

**Commit**: `test(eval): lock production writer path off halt flag`

---

## Parallel Execution Map

```
Phase 1 (parallel):
  T1 [P]     T3 [P]

Phase 2 (parallel after deps):
  T1 complete → T2
  T3 complete → T4
  T2 and T4 may run simultaneously

Phase 3:
  T2 complete → T5
  T4 complete → T8 [P]
  T5 and T4/T8 do not share files

Phase 4:
  T4 and T5 complete → T6
  T8 may still be in flight with T6 ([P])

Phase 5 (sequential):
  T6 complete → T7
```

**How parallel execution works:** `[P]` tasks run via sub-agents (one per task). Sequential tasks also go to sub-agents, one at a time. Orchestrator updates this file’s checkboxes after each gate.

**Independent Test (UAT, after T8, not a unittest gate):** Ingest `2609.01617v1` with qrel ids present. Run `uv run python scripts/retrieve_writer_recall.py`. Confirm traces/logs show retrieve execute and **no** Writer `run` / no `answer_delta`; report lists pack ids and the planner retrieve `task`. May be blocked by B-001.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: Dataset load + shipped JSON | Loader + corpus (merged so shipped load stays green) | ⚠️ Cohesive dataset component |
| T2: Report payload | One module’s dataclasses + serializers | ✅ Granular |
| T3: Dispatch halt branch | One function | ✅ Granular |
| T4: `build_graph` + `ResearchGraph.ainvoke` | Compile-time flag wiring (2 files) | ⚠️ Cohesive compile wrapper |
| T5: `ItemRun` / `run_e2e_item` | One module’s snapshot helpers | ✅ Granular |
| T6: CLI rewrite | One script + AST tests | ✅ Granular |
| T7: Delete isolated helpers | One module cleanup after CLI no longer imports them | ✅ Granular |
| T8: Production freeze inspect | One new test module | ✅ Granular |

T1 is two files by necessity: changing `load_dataset` to require `items[].query` without rewriting the shipped JSON would fail `test_shipped_dataset_loads`. That is a merge, not deferred tests.

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram Shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | Phase 1 start `[P]` | ✅ Match |
| T2 | T1 | `T1 → T2` | ✅ Match |
| T3 | None | Phase 1 start `[P]` | ✅ Match |
| T4 | T3 | `T3 → T4` | ✅ Match |
| T5 | T2 | `T2 → T5` | ✅ Match |
| T6 | T4, T5 | `T4, T5 → T6` | ✅ Match |
| T7 | T6 | `T6 → T7` | ✅ Match |
| T8 | T4 | `T4 → T8`, `[P]` with T5/T6 (does not depend on them) | ✅ Match |

T5 does **not** depend on T4: the fake graph only needs `ainvoke` / `initial_graph_state` duck typing. T8 does **not** depend on T5–T7. T3 and T1 do not depend on each other (`[P]` valid). T6 and T8 do not depend on each other (`[P]` valid once T4 is done).

---

## Test Co-location Validation

| Task | Code Layer Created/Modified | Matrix Requires | Task Says | Status |
| ---- | --------------------------- | --------------- | --------- | ------ |
| T1: Dataset load + JSON | `eval/retrieve_recall.py` load + dataset JSON | unit | unit | ✅ OK |
| T2: Report payload | `eval/retrieve_recall.py` report models | unit | unit | ✅ OK |
| T3: Dispatch halt | `graph/nodes/dispatch.py` | unit | unit | ✅ OK |
| T4: Graph wiring | `graph/build.py` / `research_graph.py` | unit | unit | ✅ OK |
| T5: ItemRun | `eval/retrieve_recall.py` helpers | unit | unit | ✅ OK |
| T6: CLI | `scripts/retrieve_writer_recall.py` | unit (AST) | unit | ✅ OK |
| T7: Delete isolated | `eval/retrieve_recall.py` | unit | unit | ✅ OK |
| T8: Production freeze | inspect of main/executor/execute/factory | unit | unit | ✅ OK |

No task uses `Tests: none` to defer a required unit layer. Live Independent Test is UAT (matrix: not unittest), same as writer-stream RAGAS.

---

## Requirement Traceability (tasks)

| ID | Tasks | Notes |
| -- | ----- | ----- |
| RWR-01 | T1 | Pin + `items[].query` |
| RWR-02 | (already executed) | T1/T7 must keep `RecallAtKTest` |
| RWR-03 | T7 (delete); T6 (CLI stop using it) | Cancelled |
| RWR-04 | T6 | Preflight before `ainvoke` |
| RWR-05 | T2, T6 | Payload + files; no recall exit code |
| RWR-06 | T4, T5, T6 | Compiled graph + `run_e2e_item` |
| RWR-07 | T3, T6 | Halt + CLI compile flag |
| RWR-08 | T3 default, T4 default, T8 | Student Writer on |
| RWR-09 | T2, T5, T6 | Task + admitted papers on the row |
