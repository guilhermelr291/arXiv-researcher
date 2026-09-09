# ArXiv-Grounded Plan-Based Research Specification

**Feature:** `arxiv-grounded-research`  
**Spec status:** Approved (2026-08-26)  
**Source:** Grill-me decisions, 2026-08-25  
**Architecture constraints:** `.specs/features/arxiv-grounded-research/context.md` (2026-08-26)  
**Design:** `.specs/features/arxiv-grounded-research/design.md` (draft)

**Loop amendment (approved 2026-08-27):** `.specs/features/orchestrator-eval-replan/spec.md` supersedes **ORCH-01**, **ORCH-02**, **CAP-01 retry count**, **PLAN-01 agent set** (combined `researcher`), and **THR-02 mechanism** (`reuse_existing_papers`). Unchanged here: Gate, ORCH-03, GROUND-*, SSE event names, UI-*, `max_steps=8`, `max_papers=8`, timeout.

**Chunking amendment (executed 2026-09-03):** `.specs/features/structured-aware-chunking/spec.md` supersedes retrieve-side **ARX-01** / **ARX-03** PDF load (`ArxivLoader`) and the out-of-scope row “Full-text from arXiv TeX/HTML”. Search still titles+abstracts. Retrieve ingest is arXiv HTML; 512/50 applies inside a heading section. Packed `retrieve_k_per_paper=5` from that amendment is superseded by the rerank amendment below.

**Rerank amendment (executed 2026-09-03):** `.specs/features/retrieve-cross-encoder-rerank/` supersedes packed `k=5` from ensemble order (**RETR-05**) and RRF pack-to-5 / overfetch `3×k` (**RETR-08**). First-stage hybrid `k=40`; adaptive cut `top_n=12`. Unchanged: HTML ingest, placeholder expand, T1/T2a/T3 routing. UAT of this amendment is not complete.

**Embeddings amendment (Execute 2026-09-08):** `.specs/features/voyage-4-large-embeddings/` supersedes **EMB-01** model + 1536 store (`text-embedding-3-small` into `vector(1536)`). Production embeddings are Voyage `voyage-4-large` at default **1024**-d (`Policy.embedding_dimensions`). Unchanged: pgvector store; RAG scoped to selected papers; HTML ingest + `embedding_text`. Live Independent Tests of this amendment are **not** complete.

## Problem Statement

Students asking AI/ML questions get fluent answers that mix parametric memory with the open web. That is unreliable for learning: claims are hard to check, sources are not papers, and a single LLM pass does not plan or correct itself. This feature answers only from arXiv papers in a fixed AI/ML category allowlist, with a plan-based multi-agent loop, per-step evaluation, and grounded generation (every technical claim tied to a retrieved chunk).

## Goals

- A student can submit an AI/ML question and receive a didactic, cited answer whose technical claims map to arXiv chunks, via SSE and a Chainlit chat.
- Out-of-domain questions are refused before any arXiv call; weak evidence yields an insufficient-evidence result, not a hallucinated completion.
- The same Chainlit chat can follow up: the graph resumes via `AsyncPostgresSaver` and the planner reuses papers or searches again.

## Out of Scope


| Feature                                                                           | Reason                                                                   |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Tavily / general web search                                                       | Evidence is arXiv only                                                   |
| Persistent corpus search over all ingested papers                                 | RAG is limited to papers selected for the current thread/query           |
| Semantic Scholar, OpenAlex, or other paper APIs                                   | Single source: arXiv                                                     |
| Full-text from arXiv TeX/HTML (non-PDF)                                           | **Superseded** by `structured-aware-chunking` (HTML retrieve ingest)     |
| Native hover tooltips on `[n]`                                                    | Chainlit has no native hover; v1 uses side-panel `cl.Text`               |
| Custom Chainlit JSX citation widgets                                              | Deferred                                                                 |
| `answer_delta` / typewriter of the Writer                                         | Answer is shown only after orchestrator eval passes                      |
| Auth, multi-user accounts, billing                                                | Deferred                                                                 |
| Durable history across new browser sessions unless the client resends `thread_id` | No auth; v1 does not delete threads, but does not ship a history product |
| Human-in-the-loop plan approval                                                   | Autonomous run with caps                                                 |
| Dockerizing the API or Chainlit                                                   | Only Postgres/pgvector runs in Docker                                    |
| Synchronous JSON `POST /research` (non-SSE)                                       | Single async SSE route                                                   |
| Parametric “tutorial” answers without chunk citations                             | Violates grounding                                                       |
| Mobile/desktop native clients                                                     | Chainlit is the v1 UI                                                    |


---

## User Stories

### P1: In-domain grounded research (API) ⭐ MVP

**User Story**: As a student, I want to ask an AI/ML question and get a didactic answer backed only by arXiv papers so that I can trust and inspect every technical claim.

**Why P1**: This is the product. Without a complete gate → plan → research → evaluate → write path over SSE, nothing else is demoable.

**Acceptance Criteria**:

1. WHEN a client sends `POST /research` with JSON `{ "query": "<AI/ML question>", "thread_id": "<uuid>" }` THEN the system SHALL respond with `Content-Type: text/event-stream` and SHALL run the graph asynchronously (`astream` / async handlers).
2. WHEN the query is in-domain THEN the Gate SHALL allow the Planner to run and SHALL NOT call arXiv before that decision.
3. WHEN the Planner runs THEN the system SHALL produce an ordered plan the Orchestrator can execute, and SHALL emit a `plan` SSE event. The planner should return an structured output with agent, task and reasoning. The agents and their habilities should be in the planner prompt.
4. WHEN the Orchestrator assigns a research step THEN the Researcher SHALL (a) find candidate papers with the LangChain arXiv tool (`ArxivRetriever` and/or `ArxivQueryRun`), (b) filter to the allowlist `cs.AI`, `cs.LG`, `cs.CL`, `cs.CV`, `cs.NE`, `cs.RO`, `stat.ML`, (c) prefer papers from the last 5 years unless the step is marked historical, (d) load full PDF text with `ArxivLoader` for selected ids not already stored, (e) split with `RecursiveCharacterTextSplitter` (`chunk_size=500`, `chunk_overlap=100`), (f) embed with OpenAI `text-embedding-3-small`, (g) persist chunks in pgvector keyed by `(arxiv_id, version)`, (h) retrieve chunks **only** from papers chosen for this query/thread (not the whole library).
5. WHEN a paper `(arxiv_id, version)` is already in pgvector THEN the Researcher SHALL skip PDF download and SHALL use stored chunks/embeddings.
6. WHEN the Writer is invoked THEN the system SHALL format retrieved chunks as `[n] arXiv:ID — Title (Year)\nexcerpt` and SHALL instruct the Writer to cite only those `[n]` values.
7. WHEN the Orchestrator evaluates the Writer output THEN it SHALL require: query language, student register, every technical claim citing a real `[n]`, no non-arXiv sources. WHEN eval fails and retries remain THEN the system SHALL retry with feedback. WHEN eval passes THEN the system SHALL emit `answer_complete` with the full markdown **and** `citations[]` (`n`, `arxiv_id`, `title`, `year`, `url`, `excerpt`, `chunk_id`) and SHALL NOT emit `answer_delta`.
8. WHEN papers in the evidence set contradict each other THEN the Writer SHALL include a limitations/contradictions section rather than picking a winner.
9. WHEN `max_steps=8`, `max_retries_per_step=2`, `max_papers=8`, or ~2 minute timeout is hit THEN the system SHALL emit `insufficient` or `error` on the SSE stream with the trace so far and SHALL NOT invent claims to “complete” the answer.
10. WHEN a research step returns zero adequate papers THEN the system SHALL treat coverage as insufficient (retry with feedback or `insufficient`), not fill gaps from the model weights.
11. WHEN the SSE stream proceeds THEN it SHALL include events in this vocabulary: `gate`, `plan`, `step_start`, `step_end` (including pgvector hit/miss and paper ids), `eval` (pass/retry/fail), `answer_complete`, then `done` or `insufficient` or `error`.

**Manual check**: `POST /research` with a new `thread_id` and an in-domain query (e.g. “What is LoRA?”). Consume SSE until `done`. Assert `answer_complete` markdown contains `[n]`, `citations[]` is non-empty, each `n` matches a citation, and every `arxiv_id` is on arXiv. Assert no Tavily/web tools were used.

---

### P1: Out-of-domain refusal (API)

**User Story**: As a student, I want off-topic questions rejected immediately so that the system does not pretend arXiv supports non-AI/ML answers and does not waste search quota.

**Why P1**: Grounding is meaningless if the pipeline searches arXiv for arbitrary questions.

**Acceptance Criteria**:

1. WHEN the query is not an AI/ML topic THEN the Gate (`gpt-5-mini`, structured output) SHALL refuse **before** the Planner searches and SHALL NOT call arXiv or download PDFs.
2. WHEN the Gate refuses THEN the SSE stream SHALL include a `gate` event recording refusal and SHALL end with a refusal payload (not a grounded paper answer).
3. WHEN `thread_id` is missing or empty THEN the API SHALL return HTTP 400 and SHALL NOT start the graph.

**Manual check**: `POST /research` with `thread_id` and query “What is the capital of France?”. Assert no arXiv HTTP traffic, `gate` refusal in the stream, no `answer_complete` with paper citations.

---

### P1: Chainlit research chat

**User Story**: As a student, I want a chat UI that shows the research as it happens and lets me open the passage behind each `[n]` so that I can learn from the papers, not only from the prose.

**Why P1**: v1 includes Chainlit as the student client of the SSE API.

**Acceptance Criteria**:

1. WHEN the student starts a chat THEN Chainlit SHALL create a `thread_id` (UUID) in `cl.user_session` and SHALL send it on every `POST /research`.
2. WHEN the API streams `step_start` / `step_end` THEN Chainlit SHALL render a `cl.Step` (including pgvector hit/miss). WHEN it streams `plan` THEN Chainlit SHALL show the plan as a step or message. WHEN it streams `answer_complete` THEN Chainlit SHALL show the final markdown and attach `cl.Text(name="[n]", content=excerpt, display="side")` for each citation so that mentioning `[n]` in the message opens the excerpt in the side panel.
3. WHEN a new chat is started THEN Chainlit SHALL generate a new `thread_id` (previous checkpoints remain in Postgres; v1 does not delete them).
4. WHEN Chainlit calls the API THEN it SHALL use the FastAPI SSE endpoint only (no in-process LangGraph). FastAPI and Chainlit SHALL run on the host; Postgres/pgvector SHALL run in Docker.

**Manual check**: With Postgres up and API on port 8001, run Chainlit on port 8000, ask an in-domain question, observe live steps, then click `[1]` and see the excerpt plus paper identity in the side panel.

---

### P2: Follow-up in the same thread

**User Story**: As a student, I want to ask “explain the second point again” in the same chat so that I do not trigger a full arXiv search when the papers are already in context.

**Why P2**: The MVP is a correct first answer. Follow-up is the reason for `AsyncPostgresSaver` and should ship in the same vertical slice if capacity allows, but the first-answer API can be demoed without it.

**Acceptance Criteria**:

1. WHEN a second `POST /research` uses the same `thread_id` THEN the graph SHALL load state via `AsyncPostgresSaver` (messages, papers with `arxiv_id`+version, plan, last cited chunks).
2. WHEN the Planner judges the follow-up to be about the same topic THEN the Researcher SHALL NOT search arXiv or download PDFs and SHALL write from the thread’s papers/chunks.
3. WHEN the Planner judges the follow-up to be a new topic THEN the system SHALL run arXiv search again and SHALL update `papers` in checkpoint state.
4. WHEN follow-up writing happens THEN grounding rules SHALL still apply (numbered chunks, eval, contradictions). Follow-up SHALL NOT answer from uncited parametric memory.

**Manual check**: Complete one in-domain research on `thread_id=T`. Send a clarifying follow-up on `T`. Assert the planner path skips arXiv when the topic is the same (no new downloads). Send a clearly different AI/ML topic on `T` and assert a new search runs.

---

### P2: Cache hit across threads

**User Story**: As the system operator, I want a paper version downloaded once so that later threads that select the same `(arxiv_id, version)` do not re-fetch the PDF.

**Why P2**: Correctness of the first answer does not depend on cross-thread cache; cost and rate limits do.

**Acceptance Criteria**:

1. WHEN thread B selects a paper already stored as `(arxiv_id, version)` by thread A THEN the Researcher SHALL skip PDF download and SHALL load chunks from pgvector.
2. WHEN the arXiv search returns a **new version** of the same id THEN the system SHALL insert a new row (unique `(arxiv_id, version)`) and SHALL use the version returned by **this** search for the answer.
3. WHEN RAG runs THEN it SHALL still be restricted to papers selected for the current query/thread, even if other papers exist in pgvector.

**Manual check**: Ingest paper `P` at version `v` in thread A. In thread B, force selection of `P` v (fixture or query). Assert no PDF download for that pair; embeddings come from Postgres.

---

## Edge Cases

- WHEN the query is AI/ML but arXiv returns nothing in-allowlist / in-window THEN the system SHALL emit `insufficient` with what was searched, not a parametric lecture.
- WHEN PDF parse yields unusable text THEN that paper SHALL fail the research step (retry or drop the paper); the Writer SHALL NOT cite empty chunks.
- WHEN eval exhausts `max_retries_per_step` THEN the Orchestrator SHALL not advance as success; the run SHALL end via `insufficient` or `error` according to remaining plan/caps.
- WHEN timeout (~2 min) fires THEN the server SHALL emit `insufficient` or `error`, close the SSE stream, and Chainlit SHALL show the trace received so far.
- WHEN `max_papers=8` is reached THEN the Researcher SHALL not add more unique papers; the Writer SHALL use only those already selected.
- WHEN the question is historical (e.g. original Transformer paper) THEN the Planner SHALL mark a historical step and SHALL NOT apply the 5-year preference for that step.
- WHEN two chunks disagree THEN the Writer SHALL describe both with citations and SHALL NOT choose a winner in the eval sense.
- WHEN the query language is Portuguese (or any language) THEN Gate/Planner/Writer-facing student text SHALL match that language; paper titles and excerpts stay as in the source (typically English).
- WHEN a sync arXiv/PDF library would block the event loop THEN the system SHALL run that work in `asyncio.to_thread` (or equivalent), not on the main loop.
- WHEN the client sends an unknown `thread_id` THEN the system SHALL treat it as a new thread (first checkpoint).
- WHEN Chainlit reconnects with the same `thread_id` THEN follow-up behavior (P2) SHALL apply; v1 SHALL NOT implement server-side thread deletion or TTL.

---

## Constraints (locked)


| Area             | Decision                                                                            |
| ---------------- | ----------------------------------------------------------------------------------- |
| Domain           | AI/ML only (product, not a temporary vertical)                                      |
| Evidence         | arXiv only                                                                          |
| Audience         | Student; didactic **structure**, not uncited analogies                              |
| Agents           | Gate → Planner → Orchestrator/Evaluator loop → Researcher → Writer                  |
| Models           | Planner + Writer: `gpt-5.1`. Gate, Orchestrator, Researcher: `gpt-5-mini`           |
| Embeddings       | Voyage `voyage-4-large` (1024-d); see embeddings amendment                          |
| Splitter         | `RecursiveCharacterTextSplitter` 500 / 100                                          |
| Caps             | `max_steps=8`, `max_retries_per_step=2`, `max_papers=8`, timeout ~2 min             |
| Checkpointer     | `AsyncPostgresSaver` in the **same** Postgres as pgvector; `setup()` on API startup |
| API              | Single async `POST /research` SSE; body `{ "query", "thread_id" }`                  |
| UI               | Chainlit on host; API on host (assumed ports 8000 / 8001); citations via side panel |
| Language of repo | English (code, docs, comments, prompts, API field names)                            |
| LLM vendor       | OpenAI                                                                              |
| Structure        | See `context.md` (PAT-01–PAT-12): registry/factory, outbound ports only, SSE via `StreamingResponse` |


---

## Requirement Traceability


| Requirement ID | Story                     | Phase    | Status |
| -------------- | ------------------------- | -------- | ------ |
| API-01         | P1: In-domain research    | Validate | ✅ Verified (static) |
| SSE-01         | P1: In-domain research    | Validate | ✅ Verified (static) |
| SSE-02         | P1: In-domain research    | Validate | ✅ Verified (static) |
| GATE-01        | P1: Out-of-domain refusal | Validate | ✅ Verified (static); ⏳ UAT |
| GATE-02        | P1: Out-of-domain refusal | Validate | ✅ Verified (static) |
| PLAN-01        | P1: In-domain research    | Validate | ✅ Verified (static); ⏳ UAT |
| ORCH-01        | P1: In-domain research    | Validate | ✅ Fixed (retry uses eval feedback); ⏳ UAT |
| ORCH-02        | P1: In-domain research    | Validate | ✅ Verified (static) |
| ORCH-03        | P1: In-domain research    | Validate | ✅ Verified (static); ⏳ UAT |
| ARX-01         | P1: In-domain research    | Validate | ⚠ Retrieve PDF superseded (`structured-aware-chunking` HTML-01) |
| ARX-02         | P1: In-domain research    | Validate | ✅ Verified (static) |
| ARX-03         | P2: Cache hit             | Validate | ⚠ PDF miss/hit superseded (`structured-aware-chunking` HTML-02) |
| ARX-04         | P1: In-domain research    | Validate | ✅ Verified (static) |
| EMB-01         | P1: In-domain research    | Validate | ✅ Fixed (RAG fetch via named columns); ⏳ UAT |
| GROUND-01      | P1: In-domain research    | Validate | ✅ Verified (static); ⏳ UAT |
| GROUND-02      | P1: In-domain research    | Validate | ✅ Fixed (`citations[]` from used `[n]`); ⏳ UAT |
| GROUND-03      | P1: In-domain research    | Validate | ✅ Verified (prompt only); ⏳ UAT |
| CAP-01         | P1: In-domain research    | Validate | ✅ Verified (static) |
| THR-01         | P2: Follow-up             | Validate | ✅ Verified (static); ⏳ UAT |
| THR-02         | P2: Follow-up             | Validate | ⏳ Pending UAT |
| UI-01          | P1: Chainlit chat         | Validate | ✅ Verified (static); ⏳ UAT |
| UI-02          | P1: Chainlit chat         | Validate | ✅ Verified (static); ⏳ UAT |
| UI-03          | P1: Chainlit chat         | Validate | ✅ Verified (static) |
| RUN-01         | P1: Chainlit chat         | Validate | ✅ Fixed (`CREATE TABLE IF NOT EXISTS`); ⏳ UAT |


**ID map (normative behavior):**

- **API-01** — `POST /research`, JSON `{ query, thread_id }`, HTTP 400 without `thread_id`.
- **SSE-01** — `text/event-stream`; event names `gate`, `plan`, `step_start`, `step_end`, `eval`, `answer_complete`, `done`  `insufficient`  `error`.
- **SSE-02** — No `answer_delta`; student-visible answer only after Writer eval pass (`answer_complete`).
- **GATE-01** — Structured Gate before Planner; out-of-domain refuses with no arXiv I/O.
- **GATE-02** — AI/ML allowlist of arXiv categories as the only evidence domain.
- **PLAN-01** — Planner (`gpt-5.1`) emits an ordered executable plan; may mark historical steps.
- **ORCH-01** — Loop: assign → execute → evaluate → retry with feedback or advance.
- **ORCH-02** — Researcher eval: ≥1 allowlisted paper in date policy (or historical), query aligned to the step.
- **ORCH-03** — Writer eval: language, student tone, every technical claim has a real `[n]`, no extra sources.
- **ARX-01** — LangChain arXiv **search** tools remain. Retrieve full text is arXiv HTML (`structured-aware-chunking`); no other search vendors.
- **ARX-02** — Recency: prefer last 5 years unless historical step.
- **ARX-03** — Unique `(arxiv_id, version)`; miss fetches HTML, hit skips fetch when chunks exist; RAG not over the full library.
- **ARX-04** — `max_papers=8` unique papers per run.
- **EMB-01** — Split 500/100, store in pgvector. **Superseded** for model + 1536 width (`text-embedding-3-small` into `vector(1536)`): Voyage `voyage-4-large` at 1024-d (embeddings amendment). Unchanged: pgvector store.
- **GROUND-01** — Chunks formatted with `[n]` before the Writer; citations only from that list.
- **GROUND-02** — `citations[]` plus markdown; excerpt is the used chunk (or recut of it).
- **GROUND-03** — Contradictions must be stated; no silent winner.
- **CAP-01** — `max_steps=8`, `max_retries_per_step=2`, timeout ~2 min; cap hit → `insufficient`/`error`, no fabricated completion.
- **THR-01** — `AsyncPostgresSaver`, same DB as pgvector, state = messages + papers + plan + last chunks.
- **THR-02** — Same `thread_id` resumes; Planner chooses reuse vs new arXiv search.
- **UI-01** — Chainlit owns `thread_id` in session; new chat → new id.
- **UI-02** — Steps from SSE; final message + side-panel `cl.Text` for `[n]`.
- **UI-03** — Chainlit is HTTP client of FastAPI only.
- **RUN-01** — Postgres/pgvector in Docker only; API + Chainlit on host; app code async with `to_thread` for sync HTML/arXiv I/O.

**Coverage:** 24 total, 24 mapped to tasks (see `tasks.md`), 0 unmapped. 2026-08-27: ARX-03, EMB-01, RUN-01, ORCH-01, GROUND-02 fixed in code; live SSE/Chainlit UAT still pending.

---

## Success Criteria

Manual checks when the feature is runnable (no automated suite in this milestone):

- An in-domain question completes over SSE with `answer_complete` where every technical claim has a resolvable `[n]` and `citations[]` entry pointing at an arXiv paper.
- An out-of-domain question never touches arXiv.
- Chainlit shows live steps and side-panel excerpts for `[n]`.
- A same-thread follow-up can be answered from checkpointed papers without a new search when the Planner keeps the topic.
- Re-selecting the same `(arxiv_id, version)` does not re-fetch HTML.
- Caps and timeout never produce an uncited “complete” answer.

