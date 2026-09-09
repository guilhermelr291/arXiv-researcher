# Writer Stream + RAGAS Report Tasks

**Design**: `.specs/features/writer-stream-ragas/design.md`  
**Spec**: `.specs/features/writer-stream-ragas/spec.md`  
**Status**: Verified T1–T10 2026-09-08 (code; unittest discover 88/88). Live Independent Tests remain UAT. Not committed. Spec/design still formally Draft.

`.specs/codebase/TESTING.md` does not exist. Same as v1 / SSE dispatcher / Voyage: graph e2e (pytest, Testcontainers) is **out of scope**. Co-located **stdlib `unittest`** covers the SSE allowlist, Writer stream (tiny in-process `StateGraph` + mocked `astream`), evaluate auto-pass, finalize halt payloads, Chainlit source locks, and the RAGAS mapper. Live Independent Tests (`POST /research` until `done`, Chainlit typewriter + `[n]` panel, RAGAS on a real LangSmith trace) stay **UAT** after Execute (may be blocked by B-001). Do **not** call live OpenAI, Voyage, LangSmith, or RAGAS `ascore` in unittest discover. Do **not** `import ragas` from any file under `tests/`.

Do **not** change Gate, plan vocabulary, admission, retrieve cut/pack/expand, `[n]` prompt format, search/retrieve Strategies, Voyage embeddings, HTTP body `{ query, thread_id }`, `make_execute_node`, dispatcher `include_types` / `stream_mode`, or graph topology (`execute → evaluate → finalize`). No `on_chat_model_*` SSE names. No `WriterEvalStrategy` stub. No Chainlit Strategy dict. No `Settings()` in the RAGAS script.

**Local coverage matrix** (substitutes for missing TESTING.md):

| Code layer | Required test type | Parallel-safe |
| ---------- | ------------------ | ------------- |
| `api/sse.py` (`SSE_EVENTS`, `SseFrame`) | unit | Yes |
| `api/schemas.py` (`AnswerCompleteData` delete) | none (type only; allowlist tests cover the name) | Yes |
| `api/stream_dispatcher.py` (handlers follow frozenset; no source change expected) | unit (existing module + inverted name tests) | Yes |
| `api/executor.py` (`_SSE01_NAMES` list only) | unit | Yes |
| `graph/nodes/finalize.py` | unit | Yes |
| `agents/writer.py` (`WriterRunner` stream + `_visible_text`) | unit | Yes |
| `graph/nodes/evaluate.py` | unit | Yes |
| `graph/build.py` / `GraphDeps` | unit (`test_research_graph`) | Yes |
| `main.py` lifespan / `scripts/draw_graph.py` | none (boot needs Postgres; draw is a script) | Yes |
| `eval/strategies.py` (delete Writer strategy) | unit (import lock + `test_internal_english`) | Yes |
| `ui/app.py` | unit (source inspect; no live Chainlit) | Yes |
| `eval/ragas_map.py` | unit | Yes |
| `pyproject.toml` optional extra | none | Yes |
| `scripts/ragas_writer_report.py` | unit (`ast.parse` the file; **no** `import ragas`) | Yes |
| `graph/nodes/execute.py` | none (no code change) | Yes |

**Gate commands:**

| Gate | Command |
| ---- | ------- |
| quick (per task) | `uv run python -m unittest tests.<module>` |
| full (after T10) | `uv run python -m unittest discover -s tests` |

**Commit constraint:** T1 without T2 makes `finalize` emit a name the dispatcher rejects. T4 without T5 makes `build_graph` pass a removed `writer_eval` argument. T3 without T4–T6 still runs `WriterEvalStrategy` after the student already saw tokens. Prefer one Execute session for T1–T7 (runtime) then T8–T10 (report). Parallel `[P]` tasks must **not** each `git commit` (STATE lesson).

---

## Execution Plan

### Phase 1: Foundation (parallel)

```
T1 [P]     T4 [P]     T8 [P]     T9 [P]
```

### Phase 2: Emitters, UI, wiring (parallel after their deps)

```
T1 ──┬→ T2 [P]
     ├→ T3 [P]
     └→ T7 [P]

T4 ──→ T5 [P]
```

T5 is `[P]` with T2/T3/T7 (different files). It does **not** depend on T1.

### Phase 3: Delete Writer strategy (sequential)

```
T5 ──→ T6
```

### Phase 4: RAGAS CLI (sequential)

```
T8, T9 ──→ T10
```

---

## Task Breakdown

### T1: SSE allowlist `answer_delta` + `citations` [P]

**What**: Replace `answer_complete` in `SSE_EVENTS` with `answer_delta` and `citations`; delete unused `AnswerCompleteData`; invert dispatcher/executor name tests.
**Where**: `src/plan_based_researcher/api/sse.py`; `src/plan_based_researcher/api/schemas.py`  
**Tests file**: `tests/test_sse_frame.py`; `tests/test_stream_dispatcher.py`; `tests/test_research_executor.py`
**Depends on**: None
**Reuses**: `SseFrame.encode` / `StreamDispatcher.default()` already maps every `SSE_EVENTS` name; `ui/sse_map.py` already drops names not in the frozenset
**Requirement**: WSTR-02

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [ ] `SSE_EVENTS` is exactly `gate`, `plan`, `step_start`, `step_end`, `eval`, `answer_delta`, `citations`, `done`, `insufficient`, `error`
- [ ] `SSE_EVENTS` SHALL NOT contain `answer_complete`
- [ ] `AnswerCompleteData` is deleted from `api/schemas.py`; `Citation` unchanged
- [ ] `stream_dispatcher.py` source is unchanged unless a test forces a fix (handlers must still equal `SSE_EVENTS`)
- [ ] `include_types` remains `("chain",)` — not this task’s job to change it; existing test still passes

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] `SseFrame("citations", {"citations": []})` round-trips JSON keys (`citations`, no `markdown`)
- [ ] `SseFrame("answer_delta", {"text": "x"})` round-trips
- [ ] `SseFrame("answer_complete", …)` raises `ValueError`
- [ ] `test_no_answer_delta_handler` is inverted: default handlers **include** `answer_delta` and `citations` and **exclude** `answer_complete`; dispatch of `answer_complete` raises `UnknownStreamKindError`
- [ ] `tests/test_research_executor.py` `_SSE01_NAMES` matches the new allowlist (still used only to forbid those strings in executor `if`/`elif`)
- [ ] Gate check passes: `uv run python -m unittest tests.test_sse_frame tests.test_stream_dispatcher tests.test_research_executor`
- [ ] Test count: **7** (`test_sse_frame`) + **10** (`test_stream_dispatcher`) + **6** (`test_research_executor`) pass (no silent deletions)

**Verify**: `python -c "from plan_based_researcher.api.sse import SSE_EVENTS; assert 'answer_delta' in SSE_EVENTS and 'citations' in SSE_EVENTS and 'answer_complete' not in SSE_EVENTS"`

**Commit**: `feat(sse): allowlist answer_delta and citations; drop answer_complete`

---

### T2: Finalize emits `done` only [P]

**What**: On `outcome == "done"`, emit `done` `{ "outcome": "done" }` only — no `answer_complete`. Halt paths unchanged.
**Where**: `src/plan_based_researcher/graph/nodes/finalize.py`  
**Tests file**: `tests/test_finalize.py` (new)
**Depends on**: T1
**Reuses**: existing `refused` / `insufficient` / `error` payloads; `get_stream_writer`
**Requirement**: WSTR-04

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [ ] `outcome == "done"` branch has no `"answer_complete"` string and does not write `markdown` / `citations` to the stream
- [ ] `refused` still emits `done` `{ outcome, reason }`; `insufficient` / `error` payloads unchanged
- [ ] Pre-Writer halt still has no `answer_delta` / `citations` (Writer never ran)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] Tiny graph or patched `get_stream_writer`: `done` yields exactly one `done` payload; spy call list has no `answer_complete`
- [ ] Source inspect: `finalize.py` contains no `answer_complete`
- [ ] `refused` / `insufficient` still emit today’s event names
- [ ] Gate check passes: `uv run python -m unittest tests.test_finalize`
- [ ] Test count: **4** tests pass (no silent deletions)

**Verify**: grep `src/plan_based_researcher/graph/nodes/finalize.py` for `answer_complete` → no matches

**Commit**: `feat(graph): emit done without answer_complete`

---

### T3: Stream `WriterRunner` via `ChatOpenAI.astream` [P]

**What**: Drop `WriterOutput` / `with_structured_output`; `astream` visible text as `answer_delta`; after a completed stream emit one `citations` and return the same strings on state.
**Where**: `src/plan_based_researcher/agents/writer.py`  
**Tests file**: `tests/test_writer_stream.py` (new)
**Depends on**: T1
**Reuses**: `_used_citation_ns`, `_citations_from_chunks`, `_format_chunks`, `_system_prompt`, `_user_prompt`, `living_and_missing`, `Citation`; `make_execute_node` **unchanged**
**Requirement**: WSTR-01, WSTR-02

**Tools**:

- MCP: `user-context7` (optional; `AIMessageChunk` / `ChatOpenAI.astream` content blocks)
- Skill: `context7-mcp` (only if Context7 is used)

**Done when**:

- [ ] `ChatOpenAI(...)` is constructed **without** `with_structured_output`; `WriterOutput` is deleted; `__all__` no longer exports it
- [ ] `_visible_text(chunk)` returns student-visible markdown; skips empty; skips reasoning / CoT blocks (`type == "text"` kept when `content` is a list)
- [ ] `_emit_custom(event, data)` calls `get_stream_writer()({"event": event, "data": data})`; on `RuntimeError` no-ops
- [ ] `run`: for each astream chunk, if `_visible_text` is non-empty, append and `_emit_custom("answer_delta", {"text": text})`
- [ ] `writer_markdown = "".join(accumulator)` equals the concatenation of emitted `text` values
- [ ] After a **completed** stream, always `_emit_custom("citations", {"citations": [...]})` (may be `[]`); parse `[n]` with existing membership rules; unknown `[n]` omitted
- [ ] If `astream` raises: do **not** emit `citations`; let the exception propagate; already-emitted deltas stay
- [ ] Return keys unchanged: `writer_markdown`, `citations`, `last_agent="writer"`
- [ ] `api_key` still passed into `ChatOpenAI` when provided
- [ ] Prompts / WRITE-02 coverage block unchanged

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] `_visible_text`: string `content` kept; list-of-blocks fixture keeps `type=="text"` and drops reasoning
- [ ] Tiny `StateGraph` (no Postgres): mocked `astream` yields two visible chunks; dispatcher yields two `answer_delta` then one `citations`; concat == returned `writer_markdown`; `include_types` still excludes `chat_model`
- [ ] Empty completed markdown still emits `citations` (possibly `[]`)
- [ ] Mocked `astream` that yields one delta then raises: `citations` event absent
- [ ] Unknown `[n]` omitted from `citations[]`; run still returns
- [ ] `_emit_custom` outside a node does not raise
- [ ] No live LLM
- [ ] Gate check passes: `uv run python -m unittest tests.test_writer_stream`
- [ ] Test count: **8** tests pass (no silent deletions)

**Verify**: `python -c "from plan_based_researcher.agents.writer import WriterRunner; import inspect; s=inspect.getsource(WriterRunner); assert 'with_structured_output' not in s and 'astream' in s"`

**Commit**: `feat(writer): stream markdown as answer_delta and emit citations once`

---

### T4: Evaluate auto-passes Writer [P]

**What**: `make_evaluate_node(search_eval, retrieve_eval)` only; Writer execute that returned is a pass with no Strategy and no `eval` SSE.
**Where**: `src/plan_based_researcher/graph/nodes/evaluate.py`  
**Tests file**: `tests/test_evaluate_writer.py` (new)
**Depends on**: None
**Reuses**: `_apply_route` / `_apply_max_steps` / `writer_just_passed`; search wave and retrieve `_evaluate_step` unchanged
**Requirement**: WSTR-03

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [ ] Signature is `make_evaluate_node(search_eval, retrieve_eval)` — no `writer_eval` parameter
- [ ] When `agent == "writer"` (from `last_agent` / plan): do **not** call a Strategy; do **not** `_emit_eval`; append `step_index` to `passed_steps`; `writer_just_passed=True`; reuse `_apply_route` / `_apply_max_steps`
- [ ] Search/retrieve still emit `eval` SSE
- [ ] Topology stays `execute → evaluate` (do not add `execute → finalize`)
- [ ] File does not import `WriterEvalStrategy`

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] Writer `last_agent`: update has `eval_next="finalize"`, `outcome="done"`, writer index in `passed_steps`
- [ ] Spy on `get_stream_writer` (or captured payloads): no `event == "eval"` for that Writer evaluate
- [ ] Retrieve path still calls `retrieve_eval.evaluate` and still `_emit_eval` (stub strategy)
- [ ] Gate check passes: `uv run python -m unittest tests.test_evaluate_writer`
- [ ] Test count: **3** tests pass (no silent deletions)

**Verify**: `python -c "import inspect, plan_based_researcher.graph.nodes.evaluate as e; assert 'writer_eval' not in inspect.signature(e.make_evaluate_node).parameters"`

**Commit**: `feat(graph): auto-pass Writer evaluate without a Strategy`

---

### T5: Drop `writer_eval` from `GraphDeps` [P]

**What**: `GraphDeps(factory, search_eval, retrieve_eval)`; wire `make_evaluate_node` with two Strategies; stop constructing `WriterEvalStrategy` at call sites.
**Where**: `src/plan_based_researcher/graph/build.py`; `src/plan_based_researcher/main.py`; `scripts/draw_graph.py`; `tests/test_research_graph.py`
**Depends on**: T4
**Reuses**: `ResearchGraph` wrapper; search/retrieve judges; PAT-07 compile-once
**Requirement**: WSTR-03

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [ ] `GraphDeps` has no `writer_eval` field
- [ ] `build_graph` calls `make_evaluate_node(deps.search_eval, deps.retrieve_eval)`
- [ ] Lifespan and `draw_graph.py` do not import or construct `WriterEvalStrategy`
- [ ] `tests/test_research_graph.py` `_stub_deps()` matches the new constructor
- [ ] Topology comments/edges still `execute → evaluate → finalize`

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] Gate check passes: `uv run python -m unittest tests.test_research_graph`
- [ ] Test count: **3** tests pass (no silent deletions)
- [ ] Compiles with stub factory + search/retrieve eval only — no API keys, no Postgres

**Verify**: `python -c "from plan_based_researcher.graph.build import GraphDeps; assert 'writer_eval' not in GraphDeps.__dataclass_fields__"`

**Commit**: `feat(graph): compile without a Writer eval Strategy`

---

### T6: Delete `WriterEvalStrategy`

**What**: Remove `WriterEvalStrategy` and Writer-only helpers from `eval/strategies.py`; drop `_writer_checklist` from English-lock tests.
**Where**: `src/plan_based_researcher/eval/strategies.py`; `tests/test_internal_english.py`
**Depends on**: T5
**Reuses**: `SearchEvalStrategy` / `RetrieveEvalStrategy` unchanged; Writer English lock stays on `agents/writer.py` `_system_prompt` (already in `test_planner_and_writer_prompts`)
**Requirement**: WSTR-03

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [ ] No class `WriterEvalStrategy`; `__all__` is `EvalStrategy`, `SearchEvalStrategy`, `RetrieveEvalStrategy` only
- [ ] Deleted with it: `_writer_checklist`, `_format_living_missing`, `_chunk_ns`, `_is_arxiv_url`, `_CITATION_RE`, `_URL_RE`, `living_and_missing` import, `urlparse` if unused
- [ ] Search/retrieve checklists and classes untouched
- [ ] Not replaced by a stub that always passes

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] `from plan_based_researcher.eval.strategies import WriterEvalStrategy` raises `ImportError`
- [ ] `tests/test_internal_english.py` no longer imports `_writer_checklist`; search/retrieve English assertions remain; still **5** tests
- [ ] Gate check passes: `uv run python -m unittest tests.test_internal_english tests.test_evaluate_writer tests.test_research_graph`
- [ ] Test count: **5** (`test_internal_english`) + **3** (`test_evaluate_writer`) + **3** (`test_research_graph`) pass (no silent deletions)

**Verify**: `python -c "from plan_based_researcher.eval import strategies as s; assert not hasattr(s, 'WriterEvalStrategy')"`

**Commit**: `refactor(eval): remove WriterEvalStrategy`

---

### T7: Chainlit typewriter + side panel [P]

**What**: Typewrite `answer_delta` onto one `cl.Message`; attach `side_panel_texts` on `citations`; remove `answer_complete` branch.
**Where**: `src/plan_based_researcher/ui/app.py`  
**Tests file**: `tests/test_chainlit_writer.py` (new)
**Depends on**: T1
**Reuses**: `side_panel_texts`, `iter_sse_frames`; existing Step handling for plan/eval/search/retrieve
**Requirement**: WSTR-05

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [ ] One `cl.Message | None` (or equivalent holder) lives across `_handle_event` calls (same lifetime idea as `open_steps`)
- [ ] `answer_delta`: ignore empty `text`; `stream_token(text)` (create `cl.Message(content="")` on first token)
- [ ] `citations`: `elements` from `side_panel_texts`; assign `message.elements`; `await message.send()`. If zero deltas, `send()` an empty-content message with elements
- [ ] No `answer_complete` branch
- [ ] `done` / `gate` / `insufficient` unchanged; on `error` after partial deltas, `send()` the partial message if not yet finalized
- [ ] No Chainlit Strategy dict

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] Source inspect: `app.py` contains `answer_delta`, `citations`, `stream_token`, `side_panel_texts`
- [ ] Source inspect: no `answer_complete` string in `app.py`
- [ ] Gate check passes: `uv run python -m unittest tests.test_chainlit_writer`
- [ ] Test count: **3** tests pass (no silent deletions)
- [ ] No live Chainlit / HTTP

**Verify**: grep `src/plan_based_researcher/ui/app.py` for `answer_complete` → no matches; grep `stream_token` and `side_panel_texts` → matches

**Commit**: `feat(ui): typewrite answer_delta and attach citations side panel`

---

### T8: `ragas_map` Writer triples [P]

**What**: Pure mapping from LangSmith-like run objects to `WriterTriple` (or `None` to skip). No `ragas` import.
**Where**: `src/plan_based_researcher/eval/ragas_map.py` (new)  
**Tests file**: `tests/test_ragas_map.py` (new)
**Depends on**: None
**Reuses**: Writer-facing `evidence_chunks[].excerpt` shape from retrieve `_append_numbered` (do not import retrieve/rerank)
**Requirement**: WSTR-07

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [ ] `WriterTriple` TypedDict: `user_input: str`, `retrieved_contexts: list[str]`, `response: str`, `run_id: str | None`
- [ ] `unwrap_node_payload(payload)`: GraphState-like dict returned as-is; single nested dict under `execute` / `retrieve` / similar unwrapped one level
- [ ] `excerpts_from_evidence_chunks(chunks)`: `None` if missing or not a list; else `[excerpt]` in list order
- [ ] `map_execute_run(run, *, retrieve_chunks_by_trace=None)`: require Writer markdown on **outputs**; query from inputs (or `messages[0].content`); contexts from inputs.`evidence_chunks` excerpts, else same-trace retrieve fallback; `None` to skip
- [ ] SHALL NOT read keys `chunks`, `chunks_scored`, or treat runs named `rerank` / `voyage_rerank` as context sources
- [ ] File does not import `ragas`, `Settings`, or Voyage clients

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] Complete triple maps all four fields
- [ ] Missing query, excerpts, or markdown → `None`
- [ ] Nested `execute` payload unwraps one level
- [ ] A blob that also has rerank `chunks_scored` / `chunks` does **not** use those lists as `retrieved_contexts`
- [ ] Retrieve-output fallback used only when execute inputs lack `evidence_chunks`
- [ ] Gate check passes: `uv run python -m unittest tests.test_ragas_map`
- [ ] Test count: **7** tests pass (no silent deletions)

**Verify**: `python -c "import plan_based_researcher.eval.ragas_map as m; assert 'ragas' not in m.__file__"; python -c "import ast, pathlib; ast.parse(pathlib.Path('src/plan_based_researcher/eval/ragas_map.py').read_text(encoding='utf-8'))"`

**Commit**: `feat(eval): map LangSmith Writer runs to RAGAS triples`

---

### T9: Optional extra `ragas>=0.4` [P]

**What**: Add `[project.optional-dependencies] ragas = ["ragas>=0.4"]`. Runtime API extra stays empty of ragas.
**Where**: `pyproject.toml` (and `uv.lock`)
**Depends on**: None
**Reuses**: existing `uv lock` / `uv sync` workflow; `langchain-openai` stays for chat
**Requirement**: WSTR-06

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [ ] `[project.optional-dependencies]` has `ragas = ["ragas>=0.4"]`
- [ ] `[project].dependencies` does **not** list `ragas`
- [ ] Lockfile updated (`uv lock`)
- [ ] `main.py` / graph / UI still do not import ragas

**Tests**: none  
**Gate**: none

**Verify**: `uv lock` succeeds; `python -c "import tomllib, pathlib; p=tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8')); assert 'ragas' not in p['project']['dependencies'] and p['project']['optional-dependencies']['ragas']==['ragas>=0.4']"`

**Commit**: `chore(eval): add optional ragas extra for the Writer report`

---

### T10: `ragas_writer_report.py` CLI

**What**: LangSmith `list_runs` → mapper → collections `Faithfulness` + `AnswerRelevancy` `ascore`; print `.value`; optional feedback; skip incomplete; exit 0 unless auth/import/crash.
**Where**: `scripts/ragas_writer_report.py` (new)  
**Tests file**: `tests/test_ragas_report_script.py` (new; **ast.parse only**)
**Depends on**: T8, T9
**Reuses**: `ragas_map` from T8; `python-dotenv` `load_dotenv`; Windows `WindowsSelectorEventLoopPolicy` (STATE lesson)
**Requirement**: WSTR-06, WSTR-07

**Tools**:

- MCP: `user-context7` (RAGAS collections `ascore` / `llm_factory` / `embedding_factory`; LangSmith `Client.create_feedback` if the SDK shape is unclear)
- Skill: `context7-mcp` (only if Context7 is used)

**Done when**:

- [ ] argparse: `--project` (default `LANGSMITH_PROJECT` or `plan-based-researcher`), `--limit`, `--run-id`, `--write-feedback` (default off)
- [ ] `langsmith.Client().list_runs(...)`; collect retrieve `evidence_chunks` per `trace_id` from retrieve/execute outputs **before** scoring writers
- [ ] Each mapped triple: `Faithfulness.ascore` + `AnswerRelevancy.ascore`; print both `.value` and `run_id`
- [ ] Skip (print reason) on mapper `None` or collections `ValueError` (empty response/contexts) — not score 0
- [ ] Judge: `AsyncOpenAI()` + `llm_factory(os.environ.get("RAGAS_LLM_MODEL", "gpt-4o-mini"), client=...)` + `embedding_factory("openai", model="text-embedding-3-small", client=...)`. SHALL NOT use Voyage
- [ ] Exit `0` after a finished report even if every score is 0.0. Non-zero only for missing `OPENAI_API_KEY` / LangSmith auth / import errors / unexpected crashes
- [ ] Do not construct `Settings()`. `load_dotenv()`. On Windows, set `WindowsSelectorEventLoopPolicy` before `asyncio.run`
- [ ] Optional `create_feedback`; if the installed SDK rejects the call, print a warning and still exit 0

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [ ] `tests/test_ragas_report_script.py` reads `scripts/ragas_writer_report.py` as text and `ast.parse`s it — the test module SHALL NOT `import ragas` or import the script as a module
- [ ] AST/source: `Settings` absent; `WindowsSelectorEventLoopPolicy` present; `Faithfulness` and `AnswerRelevancy` present; `voyage` / `Voyage` / `text-embedding` Voyage model ids absent; `load_dotenv` present
- [ ] Gate check passes: `uv run python -m unittest tests.test_ragas_report_script tests.test_ragas_map`
- [ ] Test count: **4** (`test_ragas_report_script`) + **7** (`test_ragas_map`) pass (no silent deletions)
- [ ] Full gate: `uv run python -m unittest discover -s tests` (existing 57 plus T1–T10 new tests; no silent deletions)

**Verify**: `uv run python -m unittest discover -s tests`; `python -c "import ast, pathlib; ast.parse(pathlib.Path('scripts/ragas_writer_report.py').read_text(encoding='utf-8'))"`

**Commit**: `feat(eval): add LangSmith RAGAS Writer report script`

---

## Parallel Execution Map

```
Phase 1 (parallel):
  ├── T1 [P] SSE allowlist
  ├── T4 [P] Evaluate auto-pass
  ├── T8 [P] ragas_map
  └── T9 [P] optional ragas extra

Phase 2 (parallel after deps):
  T1 complete, then:
    ├── T2 [P] Finalize
    ├── T3 [P] Writer stream
    └── T7 [P] Chainlit
  T4 complete, then:
    └── T5 [P] GraphDeps   } can run with T2/T3/T7

Phase 3 (sequential):
  T5 ──→ T6 Delete WriterEvalStrategy

Phase 4 (sequential):
  T8, T9 ──→ T10 RAGAS script
```

**How parallel execution works:** `[P]` tasks run via sub-agents concurrently. Sequential tasks also go to sub-agents, one at a time.

T2, T3, and T7 are `[P]` and do not depend on each other. T1, T4, T8, and T9 are `[P]` and do not depend on each other. T5 is `[P]` with T2/T3/T7 but **not** with T4 (it depends on T4). T6 is not `[P]`. T10 is not `[P]`.

---

## Requirement Traceability

| ID | Task |
| -- | ---- |
| WSTR-01 | T3 ✅ |
| WSTR-02 | T1 (allowlist), T3 (emit `citations` / no markdown on that event) ✅ |
| WSTR-03 | T4, T5, T6 ✅ |
| WSTR-04 | T2 ✅ |
| WSTR-05 | T7 ✅ |
| WSTR-06 | T9, T10 ✅ |
| WSTR-07 | T8, T10 (mapper + script must not read rerank span lists) ✅ |

**Coverage:** 7 total, 7 mapped, 0 unmapped. T1–T10 executed 2026-09-08.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: SSE allowlist | 1 frozenset + delete unused schema + co-located name tests | ✅ Granular (⚠️ tests in 3 modules; one allowlist change) |
| T2: Finalize `done` only | 1 function / 1 file + tests | ✅ Granular |
| T3: `WriterRunner` stream | 1 class / 1 file + tests | ✅ Granular (⚠️ cohesive helpers in same file) |
| T4: Evaluate auto-pass | 1 function / 1 file + tests | ✅ Granular |
| T5: `GraphDeps` wiring | 1 field removed across call sites | ✅ Granular (⚠️ 4 files, one constructor) |
| T6: Delete `WriterEvalStrategy` | 1 class + Writer-only helpers | ✅ Granular |
| T7: Chainlit typewriter | 1 handler / 1 file + tests | ✅ Granular |
| T8: `ragas_map` | 1 module + tests | ✅ Granular |
| T9: optional extra | 1 pyproject key | ✅ Granular |
| T10: report script | 1 CLI script + ast tests | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | Phase 1 root | ✅ Match |
| T2 | T1 | `T1 → T2` | ✅ Match |
| T3 | T1 | `T1 → T3` | ✅ Match |
| T4 | None | Phase 1 root parallel with T1 | ✅ Match |
| T5 | T4 | `T4 → T5` | ✅ Match |
| T6 | T5 | `T5 → T6` | ✅ Match |
| T7 | T1 | `T1 → T7` | ✅ Match |
| T8 | None | Phase 1 root | ✅ Match |
| T9 | None | Phase 1 root | ✅ Match |
| T10 | T8, T9 | `T8, T9 → T10` | ✅ Match |

T2, T3, T7 are `[P]` and do not depend on each other. T1, T4, T8, T9 are `[P]` and do not depend on each other. T5 does not depend on T2/T3/T7.

---

## Test Co-location Validation

| Task | Code layer | Matrix requires | Task says | Status |
| ---- | ---------- | --------------- | --------- | ------ |
| T1 | `api/sse.py` (+ dispatcher/executor name lists) | unit | unit | ✅ OK |
| T1 schemas delete | `api/schemas.py` | none | none (covered by SseFrame name tests) | ✅ OK |
| T2 | `graph/nodes/finalize.py` | unit | unit | ✅ OK |
| T3 | `agents/writer.py` | unit | unit | ✅ OK |
| T4 | `graph/nodes/evaluate.py` | unit | unit | ✅ OK |
| T5 | `graph/build.py` / `GraphDeps` | unit | unit | ✅ OK |
| T5 `main.py` / `draw_graph.py` | lifespan / script | none | none | ✅ OK |
| T6 | `eval/strategies.py` | unit | unit | ✅ OK |
| T7 | `ui/app.py` | unit | unit | ✅ OK |
| T8 | `eval/ragas_map.py` | unit | unit | ✅ OK |
| T9 | `pyproject.toml` | none | none | ✅ OK |
| T10 | `scripts/ragas_writer_report.py` | unit | unit (`ast.parse`, no ragas import) | ✅ OK |

No task uses “tested in another task” to skip required tests. T10 must not pull `ragas` into default `unittest discover`.

---

## Out of this list (UAT after Execute)

- In-domain `POST /research` until `done`: `answer_delta` during writer, one `citations`, no `answer_complete`, no Writer `eval`, no `on_chat_model_*`; concat deltas == checkpoint `writer_markdown`; `citations[].n` ⊆ evidence `[n]`
- Chainlit: message grows during Writer; after `citations`, `[n]` still opens the excerpt panel
- Follow-up retrieve→writer: same delta/`citations` contract
- Empty markdown / unknown `[n]` / extra URL / WRITE-02 hole fill: still `done`, no Writer retry
- RAGAS script on one real mapped trace prints two numbers; a stripped fixture/trace skips; process exit does not encode a score threshold
- `make_execute_node` still `step_start` → `run` → `step_end` with no edits
