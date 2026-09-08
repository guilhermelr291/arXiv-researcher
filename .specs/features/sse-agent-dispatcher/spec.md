# SSE Agent Dispatcher Specification

**Feature:** `sse-agent-dispatcher`  
**Spec status:** Validated 2026-09-07 (T1–T7 unit gate 34/34; live headers + incremental SSE-01 frames on `POST /research`. Full until `done`/`insufficient`, Chainlit, follow-up `thread_id` still UAT; uncommitted)  
**Date:** 2026-09-07  
**Parent product:** `.specs/features/arxiv-grounded-research/spec.md` (SSE-01, SSE-02, API-01, CAP-01, UI-01–03)  
**Architecture constraints:** `.specs/features/arxiv-grounded-research/context.md` (PAT-01, PAT-07, PAT-11, PAT-12 still apply; PAT-11 consume path is amended below)  
**Source:** Streaming pattern dump (Agent / graph wrapper / StreamDispatcher / SseFrame) plus viability analysis; specify 2026-09-07.

This spec refactors **how** `POST /research` streams. It does **not** change Gate, plan vocabulary, admission, retrieve, Writer grounding, SSE **event names**, SSE **payload shapes**, Chainlit behavior, or the request body `{ query, thread_id }`.

## Problem Statement

The research API already streams domain progress over SSE, but the edge mixes HTTP concerns, LangGraph iteration, allowlisting, and encoding in one route helper. The intended shape is: a compiled-once **graph wrapper**, an **execute facade** that only iterates, and a **dispatcher** that owns event types and encodes frames — so adding or refusing a stream kind is a dictionary entry, not another `if`. Proxy buffering and idle connection defaults can also stall or cut a long tool/arXiv step. Token-level LangChain callbacks (`on_chat_model_stream`) must not become the student answer.

## Goals

- [x] `POST /research` remains `text/event-stream` with `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no`, so intermediaries do not cache or buffer frames.
- [x] SSE encoding is a dedicated frame type; a dispatcher maps incoming stream kinds to handlers (no per-kind `if` in the execute facade).
- [x] A facade owns `execute` (async iterator of SSE frames) and receives a **graph wrapper** plus a **dispatcher**.
- [x] The graph is compiled once in a wrapper class (checkpointer and `GraphDeps` preserved); LLMs stay on the factory/runners, not a `call_model` node inside the wrapper.
- [x] The facade consumes `astream_events` (v2). Client-visible names stay SSE-01. Writer typewriter / `answer_delta` stays forbidden.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Chainlit Strategy / handler dict in `ui/app.py` | Specify 2026-09-07: UI event Strategy is a later slice; parser may stay as-is |
| Rename route to `/agent/execute` | Breaks Chainlit (`RESEARCH_API_URL`) and API-01 |
| Request body `message` instead of `{ query, thread_id }` | Checkpointer and follow-up require `thread_id` (AD-009) |
| Client event names `on_chat_model_start` / `on_chat_model_stream` / `on_chat_model_end` / `on_tool_start` / `on_tool_end` | Student contract is SSE-01; LC callback names leak prompts and unvalidated tokens |
| Writer `answer_delta` / typewriter of grounded markdown | Parent SSE-02 / AD-007; answer only after Writer eval pass |
| ReAct `WeatherGraph` (`MessagesState`, `bind_tools`, `ToolNode`, `call_model` on the graph) | This product is gate → plan → dispatch → search\|execute → evaluate → replan; PAT-02 already split runners from nodes |
| Second orchestrator / supervisor on top of `StateGraph` | PAT-01 |
| FastAPI or Chainlit adapter classes | PAT-08 |
| Chainlit importing the graph | UI-03 |
| New SSE event names (`replan`, `token`, `delta`, …) | Parent SSE-01 vocabulary |
| Changing eval Strategy objects (`SearchEvalStrategy` / …) | PAT-05 is verdicts, not SSE |
| Auth, timeout budget change, checkpointer schema | Parent CAP-01 / THR-01 |

### Supersedes (parent)

Upon approval, these rows are **replaced**. Unnamed parent IDs stay in force.

| Parent ID / lock | What no longer holds |
| ---------------- | -------------------- |
| PAT-11 consume wording | Mapper on `graph.astream(..., stream_mode=["updates", "custom"])` as the **required** consume API. **Unchanged:** FastAPI `StreamingResponse`; no SSE framework product; Chainlit is HTTP client; no `answer_delta`. |
| Parent P1 AC “run the graph asynchronously (`astream` / async handlers)” | The HTTP generator SHALL iterate **`astream_events`** (version **v2**), not `astream` updates+custom as the mandated path. **Unchanged:** async FastAPI; `thread_id` in config; timeout still wraps the iterator (CAP-01). |

**Amended (not replaced):** SSE-01 names and payload keys; SSE-02; API-01 path and body; PAT-01, PAT-07 (compile once), PAT-12 (`Depends`); UI-01–03 (Chainlit keeps consuming the same frames).

**Locked from specify (do not reopen in Design):**

- Public route stays **`POST /research`**. Body stays **`{ query, thread_id }`**. Missing/blank `thread_id` stays HTTP 400.
- Client `event:` names stay exactly: `gate`, `plan`, `step_start`, `step_end`, `eval`, `answer_complete`, `done`, `insufficient`, `error`.
- `data:` for those events keeps the same JSON object shapes the nodes already emit (Chainlit must work without a UI Strategy refactor).
- Dispatcher **owns** `include_types` (and the handler map). The execute facade SHALL NOT hardcode LangChain/LangGraph event types.
- Unknown kind that **passes** the dispatcher’s include filter SHALL **fail** the stream (no silent skip). Kinds excluded by `include_types` SHALL never reach handlers.
- `Cache-Control: no-cache` is for **HTTP intermediaries** (do not cache an event stream), not because the LLM is deterministic.
- `Connection: keep-alive` does not replace CAP-01 timeout; it only asks HTTP/1.1 hops not to close the pipe while the generator is alive.
- `X-Accel-Buffering: no` is required so nginx (and similar) do not batch frames. “Token a token” here means **unbuffered SSE frames**, not Writer tokens.
- Graph wrapper `__init__` compiles with existing **`GraphDeps` + checkpointer**. SHALL NOT reconstruct `ChatOpenAI` per request. SHALL NOT move specialist `ainvoke` into a graph-local `call_model`.
- Naming: avoid colliding with node `dispatch` (`graph/nodes/dispatch.py`) and eval `*Strategy`. SSE types are a **dispatcher** + **frame**; eval stays Strategy.

---

## User Stories

### P1: Unbuffered SSE frames ⭐ MVP

**User Story**: As an API client (Chainlit or curl), I want each research progress frame flushed immediately over a long-lived stream, so a slow arXiv/tool step does not look frozen and proxies do not cache or batch the response.

**Why P1**: Without correct SSE headers, the dispatcher refactor is invisible or broken behind nginx.

**Acceptance Criteria**:

1. WHEN `POST /research` succeeds as a stream THEN the response SHALL use `Content-Type: text/event-stream` (or `text/event-stream` plus charset) and SHALL include headers `Cache-Control: no-cache`, `Connection: keep-alive`, and `X-Accel-Buffering: no`.
2. WHEN a domain event is dispatched THEN the HTTP body SHALL contain one SSE frame `event: <name>\ndata: <json>\n\n` and SHALL NOT wait for a later event to flush that frame (no app-level batching of tokens or events).
3. WHEN the graph is still running (including a long tool or arXiv call) THEN the server SHALL keep the response body open until the generator finishes, errors, or CAP-01 timeout fires.

**Independent Test**: Inspect `POST /research` response headers. Confirm the three headers plus `text/event-stream`. Confirm frames appear as events occur (gate/plan), not only at end of run.

---

### P1: SseFrame + domain dispatcher

**User Story**: As a maintainer, I want stream kinds registered in a handler map owned by the dispatcher, so adding or refusing an event type is a dictionary change and unknown kinds fail loudly.

**Why P1**: This is the pattern the edge is being refactored toward; the facade must not encode or branch on kind.

**Acceptance Criteria**:

1. WHEN a frame is encoded THEN a dedicated SSE frame type SHALL produce `event:` / `data:` text (UTF-8). `data` SHALL be JSON. For SSE-01 events, JSON SHALL round-trip the same object keys/values Chainlit already reads (not LangChain `dumps` LC-serialization envelopes).
2. WHEN the dispatcher is constructed THEN it SHALL take a mapping of kind → handler. The default mapping SHALL cover every SSE-01 name that nodes emit via `get_stream_writer`.
3. WHEN `dispatch` receives an event whose kind has no handler THEN the system SHALL raise a dedicated unknown-kind error (not return an empty string, not skip).
4. WHEN the execute facade iterates the graph THEN it SHALL call `dispatcher.dispatch(...)` (or equivalent) for each included event and SHALL NOT contain per-kind `if/elif` for encoding.
5. WHEN a caller reads `include_types` THEN that list SHALL come from the dispatcher, not from the facade or the route.

**Independent Test**: Unit-test encode of one `plan` payload; dispatch known kind → valid SSE; dispatch unknown kind → error; facade/route source has no SSE-01 name branches.

---

### P1: Execute facade + compile-once graph wrapper

**User Story**: As the API process, I want one graph wrapper compiled at lifespan and an execute facade that only streams, so each request does not rebuild the graph or the LLMs.

**Why P1**: PAT-07 plus the WeatherGraph “compile in the wrapper” idea, without ReAct `call_model`.

**Acceptance Criteria**:

1. WHEN the FastAPI app starts THEN a graph wrapper SHALL compile **once** with `GraphDeps` and `AsyncPostgresSaver` (same as today: pool, `setup()`, factory, eval strategies).
2. WHEN `POST /research` runs THEN the route SHALL return `StreamingResponse` from the execute facade (not inline `graph.astream` / `astream_events` in the route module).
3. WHEN the facade is constructed THEN it SHALL receive the graph wrapper and the dispatcher (defaults allowed in tests; production wiring is lifespan / `Depends`).
4. WHEN a request executes THEN `thread_id` SHALL still be passed as LangGraph `configurable.thread_id`. Initial graph input SHALL still include `query` and the existing state keys the nodes require (not a single `messages` string like the Weather sample).
5. WHEN two requests run THEN they SHALL reuse the same compiled graph and the same runner LLM instances (no `ChatOpenAI` construct per request on the hot path).

**Independent Test**: Lifespan still compiles once (code inspection + boot). Route handler body only validates input, reads timeout, and returns `StreamingResponse(facade.execute(...))`. Follow-up with the same `thread_id` still resumes checkpointed state.

---

### P1: Consume `astream_events` without leaking model tokens

**User Story**: As a student in Chainlit, I want the same progress events as today (`gate` … `done` / `insufficient` / `error`), even though the server iterates `astream_events`, so I never see unvalidated Writer tokens or LangChain callback names.

**Why P1**: Switching consume API is in scope; changing the student contract is not.

**Acceptance Criteria**:

1. WHEN the facade streams THEN it SHALL iterate the wrapper’s `astream_events(..., version="v2", include_types=<dispatcher.include_types>)` (or the wrapper method that is a thin pass-through to the compiled graph).
2. WHEN nodes emit `get_stream_writer()` payloads `{ event, data }` with SSE-01 names THEN those SHALL still reach the client as those names (the dispatcher may map an LC envelope such as custom/`on_custom_event` onto the inner `event` field).
3. WHEN chat-model or tool callback events are produced internally THEN the client SHALL NOT receive `event: on_chat_model_stream` (or other `on_chat_model_*` / `on_tool_*` names) and SHALL NOT receive Writer markdown except on `answer_complete` after eval pass.
4. WHEN CAP-01 timeout fires THEN the stream SHALL still emit `insufficient` with `{ "reason": "timeout" }` (or the existing timeout payload) and close.
5. WHEN an unhandled exception occurs in the generator THEN the stream SHALL still emit `error` with a message and close (same as today’s route helper).
6. WHEN `include_types` is too narrow to recover SSE-01 custom payloads THEN Design SHALL widen `include_types` (or equivalent include filters) rather than fall back to `astream` as the public execute path.

**Independent Test**: `POST /research` in-domain until `done` or `insufficient`. Assert only SSE-01 names. Assert `answer_complete` still only after Writer pass. Assert no `on_chat_model_*` frames. Timeout path still yields `insufficient`.

---

## Edge Cases

- WHEN `thread_id` is missing or blank THEN the API SHALL return HTTP 400 and SHALL NOT open an SSE body (unchanged).
- WHEN the body is not JSON THEN the API SHALL return HTTP 400 (unchanged).
- WHEN `astream_events` yields a kind listed in `include_types` but omitted from the handler map THEN the stream SHALL fail via unknown-kind (then the generator’s `error` frame if the facade catches it). Design SHALL keep the two lists aligned so a healthy run never hits this.
- WHEN `astream_events` yields kinds **not** in `include_types` THEN the facade SHALL NOT see them (filter at the graph API).
- WHEN parallel `Send` search waves emit overlapping custom events THEN the client SHALL still receive one SSE-01 frame per writer payload, in arrival order (no coalescing).
- WHEN the client disconnects THEN the generator SHALL close the graph iterator (`aclose` if present), same resource-safety as today.
- WHEN a node emits a custom payload that is not `{ event, data }` with an SSE-01 `event` THEN the dispatcher SHALL fail (not skip). Nodes remain responsible for well-formed payloads.
- WHEN HTTP/2 is used THEN `Connection: keep-alive` MAY be ignored by the hop; `X-Accel-Buffering: no` and `Cache-Control: no-cache` SHALL still be set.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status | Task |
| -------------- | ----- | ----- | ------ | ---- |
| STRM-01 | P1: Unbuffered SSE frames | Execute | Verified (unit + live headers) | T1, T7 |
| STRM-02 | P1: Unbuffered SSE frames | Execute | Verified (unit + live incremental frames) | T4 |
| STRM-03 | P1: SseFrame + domain dispatcher | Execute | Verified (unit) | T1 |
| STRM-04 | P1: SseFrame + domain dispatcher | Execute | Verified (unit) | T2 |
| STRM-05 | P1: SseFrame + domain dispatcher | Execute | Verified (unit) | T4 |
| STRM-06 | P1: Execute facade + graph wrapper | Execute | Verified (unit; live boot) | T3, T6 |
| STRM-07 | P1: Execute facade + graph wrapper | Execute | Verified (unit + live route) | T5, T7 |
| STRM-08 | P1: Execute facade + graph wrapper | Execute | Verified (unit) | T3, T6 |
| STRM-09 | P1: Consume `astream_events` | Execute | Verified (unit) | T4 |
| STRM-10 | P1: Consume `astream_events` | Execute | Verified (unit; live first frames only) | T2 |
| STRM-11 | P1: Consume `astream_events` | Execute | Verified (unit; live first frames only) | T2 |
| STRM-12 | P1: Consume `astream_events` | Execute | Verified (unit) | T4 |

| ID | Requirement (short) |
| -- | ------------------- |
| STRM-01 | SSE headers: `Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no`; media type `text/event-stream`. |
| STRM-02 | No app-level batching; each dispatched frame is one SSE record flushed as produced. |
| STRM-03 | `SseFrame`-style encoder; JSON `data` compatible with current Chainlit parser for SSE-01. |
| STRM-04 | Dispatcher: kind → handler map; default covers SSE-01; unknown kind raises. |
| STRM-05 | Facade does not branch on kind; `include_types` owned by dispatcher. |
| STRM-06 | Graph wrapper compiles once in lifespan with `GraphDeps` + checkpointer. |
| STRM-07 | Route returns `StreamingResponse` from facade `execute`; no graph iterate in the route module. |
| STRM-08 | `thread_id` + full research initial state; LLMs not constructed per request; no graph-local `call_model`. |
| STRM-09 | Consume `astream_events` version v2 with dispatcher `include_types`. |
| STRM-10 | SSE-01 custom writer payloads still reach the client; LC `on_chat_model_*` / `on_tool_*` names do not. |
| STRM-11 | No `answer_delta`; `answer_complete` only after Writer eval pass (parent SSE-02). |
| STRM-12 | CAP-01 timeout → `insufficient`; unhandled exception → `error`; iterator `aclose` on exit. |

**ID format:** `STRM-NN`  
**Status values:** Pending → In Design → In Tasks → Implementing → Verified  

**Coverage:** 12 total, 12 mapped to tasks, 0 unmapped

---

## Success Criteria

- [x] `POST /research` headers include the three SSE headers (unit TestClient + live 8001). Chainlit in-domain run is still UAT.
- [x] Execute facade + dispatcher + graph wrapper are separate types; route and facade contain no SSE-01 `if/elif`.
- [x] Production path iterates `astream_events` v2; a grep of the route module finds no `astream(`.
- [x] A unit test fails the dispatcher on an unknown kind; a unit test encodes `plan` / `answer_complete` as today.
- [x] No `answer_delta` handler; no `on_chat_model_stream` on the wire (dispatcher `include_types` excludes `chat_model` / `llm` / `tool`). Live first frames (`gate`/`plan`/`step_start`/`step_end`) had no LC callback names. Full until `done`/`insufficient` is still UAT.
