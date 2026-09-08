# SSE Agent Dispatcher Tasks

**Design**: `.specs/features/sse-agent-dispatcher/design.md`  
**Spec**: `.specs/features/sse-agent-dispatcher/spec.md`  
**Status**: Validated 2026-09-07 (T1–T7 uncommitted). Full gate: `uv run python -m unittest discover -s tests` — 34 passed (test modules restored during verify after `.py` files were missing from disk). Live sample on `:8001`: headers + incremental `gate`/`plan`/`step_start`/`step_end`. Full Independent Tests until `done`/`insufficient`, Chainlit, follow-up `thread_id` remain UAT.

`.specs/codebase/TESTING.md` does not exist. Same as v1 / orchestrator / admission / Voyage: graph e2e (pytest, Testcontainers) is **out of scope**. Co-located **stdlib `unittest`** covers `SseFrame`, `StreamDispatcher` (including a tiny in-process `StateGraph` + `get_stream_writer`), `ResearchGraph` (stub compile, no Postgres), `ResearchExecutor` (fake graph), and the route via FastAPI dependency override. Live Independent Tests (`POST /research` until `done`/`insufficient`, Chainlit, follow-up `thread_id`) stay **UAT** after Execute (may be blocked by B-001).

Do **not** edit `graph/nodes/*`, `ui/app.py`, `eval/strategies.py`, or rename `POST /research`. No `answer_delta`. No `call_model` node. Do not add `sse-starlette`. Keep `build_graph` for `scripts/draw_graph.py`.

**Local coverage matrix** (substitutes for missing TESTING.md):

| Code layer | Required test type | Parallel-safe |
| ---------- | ------------------ | ------------- |
| `api/sse.py` (`SseFrame`, `SSE_HEADERS`) | unit | Yes |
| `api/stream_dispatcher.py` | unit | Yes |
| `graph/research_graph.py` | unit | Yes |
| `api/executor.py` | unit | Yes |
| `api/deps.py` (`get_executor`) | unit | Yes |
| `main.py` lifespan | none (boot needs Postgres) | Yes |
| `api/routes.py` | unit (source + TestClient override; no live graph) | Yes |

**Gate commands:**

| Gate | Command |
| ---- | ------- |
| quick (per task) | `uv run python -m unittest tests.<module>` |
| full (after T7) | `uv run python -m unittest discover -s tests` |

---

## Execution Plan

### Phase 1: Frame + wrapper (parallel)

```
T1 [P]     T3 [P]
```

### Phase 2: Dispatcher (after T1)

```
T1 ──→ T2
```

### Phase 3: Facade (after T2 and T3)

```
T2, T3 ──→ T4
```

### Phase 4: DI + lifespan (parallel after T4)

```
T4 ──┬→ T5 [P]
     └→ T6 [P]
```

### Phase 5: Route (after T5 and T6)

```
T1, T5, T6 ──→ T7
```

T7 needs T1 (`SSE_HEADERS`), T5 (`get_executor`), and T6 (lifespan stores `executor`). Do not leave HEAD on T7 without T6 — `app.state.executor` would be missing.

**Commit constraint:** T4 introduces `ResearchExecutor` unused by the route until T7. Prefer executing T4–T7 in one session if committing.

---

## Task Breakdown

### T1: `SseFrame` + unbuffered SSE headers [P]

**What**: Add `SseFrame` and `SSE_HEADERS`; keep `encode_sse` as a wrapper so Chainlit still imports `SSE_EVENTS`.
**Where**: `src/plan_based_researcher/api/sse.py`  
**Tests file**: `tests/test_sse_frame.py`
**Depends on**: None
**Reuses**: existing `SSE_EVENTS` and `encode_sse` body (`json.dumps(..., default=str)`)
**Requirement**: STRM-01, STRM-03

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `SseFrame(event, data)` is a frozen dataclass; `encode()` returns UTF-8 `event: …\ndata: <json>\n\n`
- [x] Unknown `event` raises `ValueError` (same allowlist as `SSE_EVENTS`)
- [x] `SSE_HEADERS` is `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`
- [x] `encode_sse(event, data)` equals `SseFrame(event, data).encode()`
- [x] `ui/sse_map.py` still imports `SSE_EVENTS` unchanged
- [x] Not LangChain `dumps`

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] Gate check passes: `uv run python -m unittest tests.test_sse_frame`
- [x] Test count: 5 tests pass (no silent deletions)

**Verify**: encode a `plan` `{ "steps": [] }` and an `answer_complete` `{ "markdown": "", "citations": [] }`; JSON keys round-trip; `SSE_HEADERS` has exactly those three keys

**Commit**: `feat(sse): add SseFrame encoder and unbuffered SSE headers`

---

### T2: `StreamDispatcher` + unknown-kind

**What**: Add dispatcher with SSE-01 handler map, LC `include_types` / `astream_kwargs`, and `dispatch` unwrap rules from the design.
**Where**: `src/plan_based_researcher/api/stream_dispatcher.py`  
**Tests file**: `tests/test_stream_dispatcher.py`
**Depends on**: T1
**Reuses**: `SseFrame`, `SSE_EVENTS`
**Requirement**: STRM-04, STRM-10, STRM-11

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `UnknownStreamKindError(kind: str)` exists (not a bare `ValueError` only)
- [x] `StreamDispatcher.default()` has one handler per `SSE_EVENTS` name (dict entries, not `if/elif` on those names)
- [x] No `answer_delta` (or `on_chat_model_*`) handler key
- [x] `include_types` default is `("chain",)` — must not contain `chat_model`, `llm`, or `tool`
- [x] `astream_kwargs == {"stream_mode": "custom"}` with **string** `"custom"`, not `["custom"]`
- [x] `dispatch` follows design unwrap: `on_chain_stream` + `{event, data}` chunk → handler; lifecycle / node-state chunk → `None`; writer-shaped unknown name → `UnknownStreamKindError`; `{event}` without `data` → fail
- [x] File is **not** named `dispatch.py` and type is **not** `*Strategy`

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] Gate check passes: `uv run python -m unittest tests.test_stream_dispatcher`
- [x] Test count: 10 tests pass (no silent deletions)
- [x] One test compiles a **tiny** `StateGraph` (no Postgres, no LLM) that `get_stream_writer()`-emits `{event: "plan", data: {...}}`, iterates `astream_events(version="v2", include_types=dispatcher.include_types, **dispatcher.astream_kwargs)`, and `dispatch` yields a `plan` `SseFrame`

**Verify**: known `on_chain_stream` envelope → `event: plan`; unknown inner event raises `UnknownStreamKindError`; `on_chain_start` → `None`

**Commit**: `feat(sse): add StreamDispatcher for astream_events envelopes`

---

### T3: `ResearchGraph` compile-once wrapper [P]

**What**: Wrapper that compiles via `build_graph` and exposes `astream_events` plus `initial_graph_state`.
**Where**: `src/plan_based_researcher/graph/research_graph.py`  
**Tests file**: `tests/test_research_graph.py`
**Depends on**: None
**Reuses**: `graph/build.py` `GraphDeps` / `build_graph`; `_initial_state` keys from `api/routes.py` (copy, do not leave a second source after T7)
**Requirement**: STRM-06, STRM-08

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `ResearchGraph.__init__(deps, checkpointer=None)` sets `self._compiled = build_graph(deps, checkpointer=checkpointer)`
- [x] `astream_events(self, input, config=None, **kwargs)` is a thin pass-through to `self._compiled.astream_events`
- [x] `initial_graph_state(query: str)` returns today’s keys (`query`, `messages` user content, empty `papers`/`plan`, `eval_next="dispatch"`, `outcome="pending"`, retrieve_ingest/hole maps, etc.) — not a single `messages` string
- [x] No `ChatOpenAI` construct; no `call_model` node; `scripts/draw_graph.py` still imports `build_graph`

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] Gate check passes: `uv run python -m unittest tests.test_research_graph`
- [x] Test count: 3 tests pass (no silent deletions)
- [x] Compiles with stub factory/eval objects (same idea as `scripts/draw_graph.py`) — no API keys, no Postgres

**Verify**: `initial_graph_state("q")["query"] == "q"` and `eval_next == "dispatch"`; source of `research_graph.py` contains `build_graph` and does not contain `ChatOpenAI` / `call_model`

**Commit**: `feat(graph): add ResearchGraph compile-once wrapper`

---

### T4: `ResearchExecutor` facade

**What**: Execute facade that only iterates `astream_events` v2, dispatches, times out, and `aclose`s.
**Where**: `src/plan_based_researcher/api/executor.py`  
**Tests file**: `tests/test_research_executor.py`
**Depends on**: T2, T3
**Reuses**: `iter_sse` control flow in `api/routes.py` (`wait_for`, deadline, `_SENTINEL`)
**Requirement**: STRM-02, STRM-05, STRM-09, STRM-12

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `ResearchExecutor(graph: ResearchGraph, dispatcher: StreamDispatcher)`
- [x] `execute(query, thread_id, timeout_seconds) -> AsyncIterator[bytes]`
- [x] Calls `graph.astream_events(..., version="v2", include_types=dispatcher.include_types, **dispatcher.astream_kwargs)` — does **not** hardcode `"chain"` or `"custom"`
- [x] `config = {"configurable": {"thread_id": thread_id}}`; input is `graph.initial_graph_state(query)`
- [x] Each included event: `frame = dispatcher.dispatch(event)`; if not `None`, `yield frame.encode()` immediately (no batch list)
- [x] Timeout → `SseFrame("insufficient", {"reason": "timeout"}).encode()` then return
- [x] `except Exception` → `SseFrame("error", {"message": str(exc)}).encode()`
- [x] `finally` calls `aclose` if present
- [x] No SSE-01 name `if/elif` in this file; no `graph.astream(` (without `_events`)

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] Gate check passes: `uv run python -m unittest tests.test_research_executor`
- [x] Test count: 6 tests pass (no silent deletions)
- [x] Fake graph records kwargs (`version`, `include_types`, `stream_mode`) and yields envelopes; fake or real dispatcher
- [x] Source inspect: `executor.py` has no SSE-01 name literals in `if`/`elif` (`gate`, `plan`, `step_start`, `step_end`, `eval`, `answer_complete`, `done`, `insufficient`, `error` used only as `SseFrame("insufficient"` / `"error"` for timeout/exception)

**Verify**: timeout path yields `event: insufficient`; raised iterator error yields `event: error`; `aclose` ran

**Commit**: `feat(sse): add ResearchExecutor astream_events facade`

---

### T5: `get_executor` Depends [P]

**What**: Replace `get_graph` with `get_executor` reading `request.app.state.executor`.
**Where**: `src/plan_based_researcher/api/deps.py`  
**Tests file**: `tests/test_api_deps.py`
**Depends on**: T4
**Reuses**: existing `get_settings` pattern
**Requirement**: STRM-07

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `get_executor(request)` returns `request.app.state.executor`
- [x] `get_graph` is removed (or no remaining production caller)
- [x] `get_settings` unchanged

**Tests**: unit  
**Gate**: quick

**Done when (tests)**:

- [x] Gate check passes: `uv run python -m unittest tests.test_api_deps`
- [x] Test count: 1 test pass (no silent deletions)

**Verify**: dummy request with `app.state.executor` is returned by `get_executor`

**Commit**: `feat(api): inject ResearchExecutor via Depends`

---

### T6: Lifespan compiles wrapper once [P]

**What**: Lifespan builds `ResearchGraph` + `ResearchExecutor(wrapper, StreamDispatcher.default())` once; store on `app.state`.
**Where**: `src/plan_based_researcher/main.py`
**Depends on**: T4
**Reuses**: existing pool, `checkpointer.setup()`, factory, `GraphDeps`, eval strategies
**Requirement**: STRM-06, STRM-08

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `app.state.executor = ResearchExecutor(ResearchGraph(deps, checkpointer=checkpointer), StreamDispatcher.default())`
- [x] Factory / eval strategies / `ChatOpenAI` still constructed in lifespan (or factory), **not** inside `ResearchExecutor.execute`
- [x] `app.state.settings` and `app.state.pool` unchanged
- [x] No `app.state.graph = build_graph(...)` left as the hot path (compiled graph lives on the wrapper)

**Tests**: none  
**Gate**: none

**Verify**: `main.py` lifespan source constructs `ResearchGraph` and `ResearchExecutor` once; `execute` is not called at import; `uv run python -c "from plan_based_researcher.main import create_app"` still imports (Settings/env may fail — inspect source if boot needs secrets)

**Commit**: `feat(api): compile ResearchGraph once in lifespan`

---

### T7: `POST /research` streams from the facade

**What**: Route only validates input, reads timeout, returns `StreamingResponse(executor.execute(...))` with `SSE_HEADERS`; delete `iter_sse` / `_initial_state` / `_custom_payload`.
**Where**: `src/plan_based_researcher/api/routes.py`  
**Tests file**: `tests/test_research_route.py`
**Depends on**: T1, T5, T6
**Reuses**: `_parse_research_request`, HTTP 400 behavior, `get_settings` timeout
**Requirement**: STRM-01, STRM-07

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `POST /research` uses `Depends(get_executor)` and `StreamingResponse(executor.execute(query, thread_id, timeout_seconds), media_type="text/event-stream", headers=SSE_HEADERS)`
- [x] Handler body does not iterate the graph
- [x] Module has no `astream(` call (including `astream_events`)
- [x] `_initial_state`, `iter_sse`, `_custom_payload` removed from this file
- [x] Missing/blank `thread_id` and non-JSON body still HTTP 400 and do not open SSE

**Tests**: unit  
**Gate**: quick; then full discover

**Done when (tests)**:

- [x] Gate check passes: `uv run python -m unittest tests.test_research_route`
- [x] Full gate: `uv run python -m unittest discover -s tests` (includes T1–T5 modules; no silent deletions)
- [x] Test count: 4 tests in `test_research_route` pass
- [x] TestClient (or equivalent) with `get_executor` / `get_settings` overrides: response `content-type` starts with `text/event-stream`; headers include the three `SSE_HEADERS` keys
- [x] Source inspect: `routes.py` has no `astream(`

**Verify**: grep `src/plan_based_researcher/api/routes.py` for `astream` → no matches; 400 without `thread_id` unchanged

**Commit**: `feat(api): stream POST /research from ResearchExecutor`

---

## Parallel Execution Map

```
Phase 1 (parallel):
  ├── T1 [P] SseFrame
  └── T3 [P] ResearchGraph

Phase 2 (sequential):
  T1 ──→ T2 StreamDispatcher

Phase 3 (sequential):
  T2, T3 ──→ T4 ResearchExecutor

Phase 4 (parallel):
  T4 complete, then:
    ├── T5 [P] get_executor
    └── T6 [P] lifespan

Phase 5 (sequential):
  T1, T5, T6 ──→ T7 route
```

**How parallel execution works:** `[P]` tasks run via sub-agents concurrently. Sequential tasks also go to sub-agents, one at a time.

---

## Requirement Traceability

| ID | Task |
| -- | ---- |
| STRM-01 | T1 (`SSE_HEADERS`), T7 (on `StreamingResponse`) |
| STRM-02 | T4 |
| STRM-03 | T1 |
| STRM-04 | T2 |
| STRM-05 | T4 |
| STRM-06 | T3, T6 |
| STRM-07 | T5, T7 |
| STRM-08 | T3, T6 |
| STRM-09 | T4 |
| STRM-10 | T2 |
| STRM-11 | T2 (no `answer_delta` handler); nodes/UI not in this list |
| STRM-12 | T4 |

**Coverage:** 12 total, 12 mapped, 0 unmapped

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1: `SseFrame` + `SSE_HEADERS` | 1 module (`sse.py`) + tests | ✅ Granular |
| T2: `StreamDispatcher` | 1 class / 1 file + tests | ✅ Granular |
| T3: `ResearchGraph` + `initial_graph_state` | 1 file, cohesive wrapper | ✅ Granular (⚠️ same file, one concept) |
| T4: `ResearchExecutor` | 1 class / 1 file + tests | ✅ Granular |
| T5: `get_executor` | 1 function / 1 file + tests | ✅ Granular |
| T6: lifespan wiring | 1 file (`main.py`) | ✅ Granular |
| T7: `POST /research` | 1 endpoint / 1 file + tests | ✅ Granular |

---

## Diagram-Definition Cross-Check

| Task | Depends On (task body) | Diagram shows | Status |
| ---- | ---------------------- | ------------- | ------ |
| T1 | None | Phase 1 root | ✅ Match |
| T2 | T1 | `T1 → T2` | ✅ Match |
| T3 | None | Phase 1 root parallel with T1 | ✅ Match |
| T4 | T2, T3 | `T2, T3 → T4` | ✅ Match |
| T5 | T4 | `T4 → T5` | ✅ Match |
| T6 | T4 | `T4 → T6` | ✅ Match |
| T7 | T1, T5, T6 | `T1, T5, T6 → T7` | ✅ Match |

T5 and T6 are `[P]` and do not depend on each other. T1 and T3 are `[P]` and do not depend on each other.

---

## Test Co-location Validation

| Task | Code layer | Matrix requires | Task says | Status |
| ---- | ---------- | --------------- | --------- | ------ |
| T1 | `api/sse.py` | unit | unit | ✅ OK |
| T2 | `api/stream_dispatcher.py` | unit | unit | ✅ OK |
| T3 | `graph/research_graph.py` | unit | unit | ✅ OK |
| T4 | `api/executor.py` | unit | unit | ✅ OK |
| T5 | `api/deps.py` | unit | unit | ✅ OK |
| T6 | `main.py` lifespan | none | none | ✅ OK |
| T7 | `api/routes.py` | unit | unit | ✅ OK |

No task uses “tested in another task” to skip required tests.

---

## Out of this list (UAT after Execute)

- In-domain `POST /research` until `done` / `insufficient`; only SSE-01 names on the wire
- Chainlit on port 8000 with no UI changes
- Follow-up same `thread_id` resumes checkpoint
- Parallel `Send` search wave: one SSE-01 frame per writer payload, arrival order
