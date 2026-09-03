# State

**Last Updated:** 2026-09-03
**Current Work:** Feature `structured-aware-chunking` — Execute T1–T19 done. Manual UAT still pending (B-001).

---

## Recent Decisions (Last 60 days)

### AD-001: Plan-based multi-agent researcher (2026-08-25)

**Decision:** Build an AI researcher where a planner agent generates the plan and an orchestrator loop assigns, evaluates, and retries or advances each step.
**Reason:** Plan-based control with per-step evaluation is the core product approach.
**Trade-off:** More moving parts than a single LLM call; slower and more token-heavy.
**Impact:** LangGraph graph is a loop around execute + evaluate, not a linear chain only.

### AD-002: v1 is backend-only (2026-08-25) — SUPERSEDED by AD-008

**Decision:** v1 ships FastAPI + LangGraph only.
**Reason:** Prove the agent loop before investing in UI.
**Trade-off:** No user-facing product until a client exists.
**Impact:** Superseded: Chainlit is in v1 as HTTP client of the API.

### AD-003: Stack — Python, FastAPI, LangChain, LangGraph, OpenAI, Tavily (2026-08-25) — SUPERSEDED by AD-005

**Decision:** OpenAI for LLM, Tavily for search.
**Reason:** User-selected at project init.
**Trade-off:** Tied to those vendors.
**Impact:** Superseded: Tavily removed; evidence is arXiv only; Postgres/pgvector added.

### AD-004: Project language is English (2026-08-25)

**Decision:** All project artifacts (code, docs, comments, API, prompts) are in English.
**Reason:** User requirement.
**Trade-off:** None material.
**Impact:** Specs, identifiers, and prompts stay in English. Student-facing answers follow the query language.

### AD-005: ArXiv-only AI/ML student researcher (2026-08-25)

**Decision:** Product domain is AI/ML forever. Evidence is arXiv only (allowlist `cs.AI`, `cs.LG`, `cs.CL`, `cs.CV`, `cs.NE`, `cs.RO`, `stat.ML`). Audience is students: didactic structure, every technical claim cited. Prefer papers from the last 5 years unless the planner marks a historical step.
**Reason:** Grill-me; Tavily/web cannot satisfy “papers only.”
**Trade-off:** No blogs, docs, or non-arXiv venues; keyword arXiv search is weaker than a semantic corpus.
**Impact:** Drop Tavily. Researcher uses LangChain arXiv tools + `ArxivLoader` PDFs.

### AD-006: Agent roster and models (2026-08-25)

**Decision:** Gate → Planner → Orchestrator/Evaluator loop → Researcher → Writer. Planner and Writer: `gpt-5.1`. Gate, Orchestrator, Researcher: `gpt-5-mini`. Embeddings: `text-embedding-3-small`. Caps: `max_steps=8`, `max_retries_per_step=2`, `max_papers=8`, timeout ~2 min. Splitter 500/100.
**Reason:** Strong model on plan/write; cheap model on high-volume gate/eval/tools.
**Trade-off:** Eval quality vs cost; 2 min may cut long PDF ingest.
**Impact:** Config keys and node implementations follow this split.

### AD-007: Grounded generation (2026-08-25)

**Decision:** Format chunks as `[n]` before the Writer. Writer may cite only those indices. Response is markdown plus `citations[]` (id, title, year, url, excerpt, chunk_id). Contradictions must be stated. No `answer_delta`; `answer_complete` only after Writer eval passes.
**Reason:** Student must inspect passages; streaming unvalidated prose breaks grounding.
**Trade-off:** Answer appears all at once; steps still stream.
**Impact:** Orchestrator Writer checklist is normative. Chainlit maps `[n]` to side-panel `cl.Text`.

### AD-008: SSE API + Chainlit on host (2026-08-25)

**Decision:** Single async `POST /research` (`text/event-stream`). Body `{ query, thread_id }`. Chainlit on host (port 8000 assumed) calls API on host (port 8001 assumed). Only Postgres/pgvector in Docker. No auth.
**Reason:** One contract for tests and UI; stream progress without exposing ungrounded text.
**Trade-off:** Tests must parse SSE; two local processes.
**Impact:** No sync JSON research route. Chainlit does not import the graph.

### AD-009: pgvector paper store + AsyncPostgresSaver (2026-08-25)

**Decision:** Same Postgres: pgvector chunks unique on `(arxiv_id, version)` (lazy download) and LangGraph `AsyncPostgresSaver` for current-chat graph state (messages, papers, plan, last chunks). RAG only over papers selected for the thread/query, not the whole library. Missing `thread_id` → 400. Threads are not deleted in v1. Follow-up: Planner chooses reuse vs new arXiv search. Sync PDF/arXiv I/O via `asyncio.to_thread`.
**Reason:** Avoid re-download; resume chat without `prior_papers` in the client body.
**Trade-off:** DB grows; anonymous `thread_id` is not a user account.
**Impact:** API is not stateless. `setup()` on startup. Client must persist `thread_id` for follow-up.

### AD-010: Growth patterns — registry/factory, outbound ports, no HTTP adapters (2026-08-26)

**Decision:** Structure the app as: LangGraph-only orchestrator; agent registry + factory; tool registry; plan interpreter; eval strategies with result types; typed state + reducers; compile graph once in FastAPI lifespan; outbound ports for arXiv and pgvector only; chunk repository; named policy objects; SSE via FastAPI `StreamingResponse` plus a mapper function; DI via `Depends`. Do not wrap FastAPI or Chainlit in adapter classes. Chainlit remains an HTTP client.
**Reason:** User confirmed hexagonal “edge adapters” are jargon, not extra wrappers; SSE is native FastAPI; registry/factory are for agents/tools so the planner prompt and dispatch share one source of truth.
**Trade-off:** Slightly more modules up front vs a single script of nodes.
**Impact:** Design and tasks must follow `.specs/features/arxiv-grounded-research/context.md` (PAT-01–PAT-12).

### AD-011: Semantic eval, 1 retry, 1 remaining replan (2026-08-27)

**Decision:** Orchestrator interprets a variable plan of `search` / `retrieve` / `writer`. Eval is semantic and artifact-specific (not “it ran”). 1 retry = 2 attempts on the same step. If that is not enough, or eval says the **plan** is wrong, 1 replan of the **remaining** suffix only; passed steps are not redone. Then `insufficient`. Typical plans: explain = search→retrieve→writer; compare = search×N→retrieve→writer; follow-up = retrieve→writer. Search does not load PDFs; retrieve hybrid 0.7/0.3 is under the hood. Caps: 1 retry/step, 1 replan/run, plus existing `max_steps` / timeout / `max_papers`.
**Reason:** User specified the loop; v1 combined researcher + retry-then-stop cannot drop a failed compare topic without either inventing coverage or failing the whole run.
**Trade-off:** Split roster (`search`/`retrieve` vs one `researcher`); stricter eval; one extra planner call per run at most.
**Impact:** Spec and design approved 2026-08-27. Supersedes ORCH-01, ORCH-02, CAP-01 retry count, combined `researcher` plan step, and THR-02 `reuse_existing_papers` mechanism. Gate, SSE event names, Writer grounding (ORCH-03), Chainlit unchanged. Consecutive `search` steps may `Send` in parallel; semantic search eval is **one** structured LLM call per wave with **N independent verdicts** (SEARCH-02).

### AD-013: Search/retrieve formulate the query; planner `task` is the goal (2026-08-28)

**Decision:** The planner `task` is a natural-language research goal (eval target + UI). The search agent always formulates the arXiv `search_query` via structured output (`FormulatedQuery`, `json_schema`, English prompt with API syntax). The retrieve agent always formulates an English hybrid query the same way. Retry uses **that step’s** feedback from `eval_by_step`, not a shared `last_eval`. Prompts are English; student `task`/feedback may be another language as input data.
**Reason:** Passing raw `task` (or the student query) to keyword arXiv / BM25 is weak; query writing belongs to the specialist agent. Wave retry was using the last verdict’s feedback (LOOP-02).
**Trade-off:** One extra `gpt-5-mini` call per search/retrieve attempt (including first try).
**Impact:** SEARCH-01 / RETR-01 / LOOP-02 updated. Planner abilities tell the planner not to emit arXiv syntax in `task`.

### AD-014: Admission 1/topic, per-paper retrieve, S8a / T1–T3 (2026-08-29)

**Decision:** One usable paper per passed search ranking. Wave judge returns a clipped ranking; uniqueness is champion-only at eval (U1); `papers` are written only after PDF ingest. Retrieve is hybrid per paper with `k=3`. Search attempt 1 always retries (`plan_inadequate` ignored for routing). Attempt 2 replan reuses `plan_inadequate` (S8a: no new search vs corrected search). Retrieve T1/T2a skip query retry; T2a hybrid on living papers then writer-only replan; T3 attempt 1 always retries the query (R2). Writer must not fill a missing topic from model weights (WRITE-02).
**Reason:** Grill-me 2026-08-28/29. FIFO lot admission and a single retrieve `k` starve compare topics; parametric fill would break grounded generation.
**Trade-off:** One angle per topic; T1 may spend the only replan then `insufficient`; `plan_inadequate` is overloaded on search attempt 2.
**Impact:** Spec `.specs/features/admission-retrieve-per-topic/spec.md` (approved 2026-08-29). Design `.specs/features/admission-retrieve-per-topic/design.md` (approved 2026-08-29). Supersedes SEARCH-01 admission, SEARCH-02 verdict shape, RETR-01 global `k`, LOOP-03 on search attempt 1. Routing atlas in `graph-flow.md`.

### AD-016: Structured-aware HTML chunking (2026-09-02)

**Decision:** Replace retrieve PDF ingest with arXiv HTML. Tables and display equations are atomic (`content` = caption/tag + full body, never truncated). Prose is heading-split then 512/50 inside a section, with canonical placeholders in `content` and human labels in `embedding_text`. `figure.ltx_table` collapses to one table unit; image figures become caption text (no units, no assets, no LLM summaries). Schema: `kind`, `unit_id`, `embedding_text`, `content`, JSONB `{section, caption, unit_ids}`. Hybrid per paper `k=5`; vector on `embedding_text`, BM25 on `content`; overfetch ≥3×k; dedup `unit_id` + backfill to 5 unique; in-place expansion (first occurrence full body, later label only). Direct atomic hit excerpt = section + `content`. Writer and Citation share that excerpt. Local wipe of PDF chunks; no PDF fallback; missing HTML omits/walks `ranked_keys`. Graph execute unchanged.
**Reason:** Grill-me 2026-09-02; RecursiveCharacterTextSplitter on PDF text drops section, table, and equation identity. Spike `scripts/arxiv_html_units.py` validated the parse.
**Trade-off:** Papers without HTML contribute no chunks; large tables can inflate Writer context; no figure retrieval in this slice.
**Impact:** Spec `.specs/features/structured-aware-chunking/spec.md` (executed 2026-09-03). Design and tasks T1–T19 executed 2026-09-03. Supersedes retrieve-side ARX-01/ARX-03 PDF load, RETR-02 `k=3`, RETR-03 PDF walk. Search/admission/T1–T3 routing unchanged.

### AD-015: Admission/retrieve design locks (2026-08-29)

**Decision:** Approve `.specs/features/admission-retrieve-per-topic/design.md` as written. `SearchStepVerdict.ranked_keys` is `list[PaperKey]`; clip + U1 are runtime (`eval/admission.py`). `papers` are written only after retrieve ingest. Hybrid is N calls of the existing adapter with `retrieve_k_per_paper=3`. Search API pool is `search_max_results=8` (not `max_papers`). Search attempt 1 always retries (`plan_inadequate` ignored for the edge). T1/T2a skip the retrieve mini-judge. T3 query miss always retries once. S8a stays on `plan_inadequate` per leftover search. WRITE-02 is prompt + writer judge. No new graph nodes.
**Reason:** User approved spec + design 2026-08-29.
**Trade-off:** `plan_inadequate` stays overloaded; T1 may spend the only replan then `insufficient`.
**Impact:** Tasks and implementation must follow that design. Do not reintroduce lot admission at search eval or union `retrieve_k`.

### AD-012: Eval-replan design locks (2026-08-27)

**Decision:** Approve `.specs/features/orchestrator-eval-replan/design.md`. Search waves use LangGraph `Send` and admit papers only after eval pass. Hybrid retrieve is `EnsembleRetriever` RRF weights 0.7/0.3 (`langchain-classic` + BM25), not linear score fusion. Follow-up omits `search` (drop `reuse_existing_papers`). `Policy.max_retries_per_step=1`, `max_replans=1`. Mixed-wave remaining head is the earliest unpassed step; later passed searches are not rerun.
**Reason:** User approved the design as written.
**Trade-off:** RRF ≠ raw 0.7/0.3 score mix; extra graph nodes (`dispatch`, `search`, `replan`).
**Impact:** Tasks and implementation must follow that design. PROJECT.md caps updated. Parent spec banner marks superseded IDs.

---

## Active Blockers

### B-001: Host port 5432 occupied (`hackathon2026-postgres`)

**Discovered:** 2026-08-27
**Impact:** `docker compose up` for this project's pgvector cannot bind 5432.
**Workaround:** Temporary pgvector on 5433 for repo smoke. Stop the other container, or map compose to a free port, before API/Chainlit UAT.
**Resolution:** Free 5432 or change this project's published port.

---

## Lessons Learned

- `ChatOpenAI` validates `OPENAI_API_KEY` at construct time. Agent factory must pass `api_key` into Gate, Planner, and Writer runners; relying on env alone fails when Settings reads `.env` without exporting it.
- Parallel `[P]` tasks cannot each `git commit` safely; implement in parallel, then serialize atomic commits on the orchestrator.
- Sharing one psycopg pool with `AsyncPostgresSaver` (`dict_row`) means app SQL must read rows by column name (or set `tuple_row` on those cursors). Indexing `row[0]` crashes on cache hit and on RAG `fetchall`.
- On Windows, psycopg async cannot use the default `ProactorEventLoop`; smoke/scripts need `WindowsSelectorEventLoopPolicy` (uvicorn typically already uses a compatible loop).
- LangChain `ArxivRetriever` / `Search.results()` builds a new `arxiv.Client` per call (`page_size=100`). Parallel `Send("search")` then bursts `export.arxiv.org` and 429s. A shared Client (`page_size=8`, `delay_seconds=3`) plus an adapter lock keeps the graph fan-out and serializes HTTP.
- LangGraph last-value channels reject more than one write per superstep. Parallel `Send("search")` all set `last_agent`; that key needs a last-write reducer (`Annotated[str, last_write]`), same class of issue as `search_artifacts` already had.
- LangGraph 1.x compiled graphs only persist keys declared on `GraphState`. A routing field such as `eval_next` must be on the TypedDict or evaluate→replan is dropped and the loop always dispatches.
- Search-wave eval emits N `eval` SSE frames but `_evaluate_wave` used to keep a single `last_eval` (last verdict). Fixed 2026-08-28: persist `eval_by_step` per index; search/retrieve retry reads that step’s feedback.
- Remaining-only replan compacting prefix to `passed_steps=range(len(prefix))` is safe only if every index-keyed map (`search_artifacts`, `eval_by_step`, `retrieve_ingest.gap_step_indices`) is remapped or stored by task identity. This feature made retrieve depend on `search_artifacts[str(plan_index)]`; mixed-wave S8a then walks the wrong ranking.
- Chainlit loads `.env` and, if `DATABASE_URL` is set, instantiates `ChainlitDataLayer` (`asyncpg`). This project's `DATABASE_URL` is the API's psycopg/pgvector URL. The Chainlit process must drop that env var after import; do not add `asyncpg` or share the researcher schema with Chainlit persistence.
- `langchain-community` 0.4.2 `ArxivAPIWrapper` still calls `Search.results()` and `Result.download_pdf()`. `arxiv` 4.x removed both. Keep `arxiv>=2.2.0,<4` until the wrapper (or a successor package) uses `Client.results`.
- Search-wave judge `ranked_keys` are clipped to artifact hits. If the prompt omits `arxiv_id`/`version`, the model invents ids (`QLoRA-2023`) and a passing step becomes a retry. Trace `01a058c6-e1a8-71a0-b9e1-44ed67f3f1a6` then exhausted the 120s cap on the second eval. Quick 010: judge emits per-step `ranked_hit_indices` instead; clip still gates the artifact.
- PyMuPDF `get_text()` (LangChain `ArxivLoader`) can emit U+0000. Postgres TEXT / psycopg reject it. Strip NUL in the arXiv adapter after load. Trace `01a058da-c1b4-7633-befb-39b6249739c7`.

---

## Quick Tasks Completed

| #   | Description | Date | Commit | Status |
| --- | ----------- | ---- | ------ | ------ |
| 001 | Install v1 stack (FastAPI, LangGraph, LangChain, OpenAI, Tavily) via uv | 2026-08-25 | — | ✅ Done |
| 002 | Script to draw compiled LangGraph as Mermaid PNG | 2026-08-30 | — | ✅ Done |
| 003 | Enable LangSmith tracing via `.env` + `load_dotenv()` | 2026-08-30 | — | ✅ Done |
| 004 | Chainlit crash on `DATABASE_URL`/`asyncpg`; add `chainlit_pt-BR.md` | 2026-08-30 | — | ✅ Done |
| 005 | Pin `arxiv<4` so LangChain `Search.results()` still exists | 2026-08-30 | — | ✅ Done |
| 006 | Shared arXiv Client (`page_size=8`, 3s delay) + global request lock | 2026-08-30 | 4fe59c3 | ✅ Done |
| 007 | `last_agent` last-write reducer so parallel search `Send` can merge | 2026-08-30 | 2673a51 | ✅ Done |
| 008 | Search-wave judge prompt includes real `arxiv_id`/`version` so clip can keep rankings | 2026-08-31 | — | ✅ Done |
| 009 | Strip NUL bytes from arXiv PDF text before pgvector upsert | 2026-08-31 | — | ✅ Done |
| 010 | Search-wave judge ranks via per-step hit indexes, not invented arXiv ids | 2026-08-31 | — | ✅ Done |
| 011 | PDF chunking uses tiktoken 512/50 (`cl100k_base`), not characters | 2026-08-31 | — | ✅ Done |

---

## Deferred Ideas

- [ ] Automated test suite (pytest / Testcontainers) — Captured during: tasks phase (explicitly deferred)
- [ ] Writer `answer_delta` after eval pass — Captured during: grill-me
- [ ] Auth, multi-user, billing — Captured during: project init
- [ ] Thread TTL/delete and history UI across browser sessions — Captured during: grill-me
- [x] arXiv TeX/HTML instead of PDF extract — Promoted to feature `structured-aware-chunking` (spec draft 2026-09-02)
- [ ] Image/figure units + vision — Captured during: structured-aware-chunking grill-me
- [ ] LLM summaries of tables/equations — Captured during: structured-aware-chunking grill-me
- [ ] Dockerize API and Chainlit — Captured during: grill-me
- [ ] Global semantic search over full ingested corpus — Captured during: grill-me
- [ ] HITL plan approval — Captured during: grill-me
- [ ] Human-in-the-loop two-step plan confirm — Captured during: grill-me

---

## Todos

- [x] User approve `.specs/features/arxiv-grounded-research/spec.md` before Design
- [x] User approve `.specs/features/arxiv-grounded-research/design.md` before Tasks
- [x] Automated tests deferred (no pytest/Testcontainers in v1 tasks)
- [x] User approve `.specs/features/arxiv-grounded-research/tasks.md` before Execute
- [x] Remove Tavily from runtime dependencies when implementing Foundation
- [x] Fix: `PgChunkRepository` row mapping under `dict_row` (ARX-03 / EMB-01)
- [x] Fix: `CREATE TABLE` / `CREATE INDEX` `IF NOT EXISTS` on API restart (RUN-01)
- [x] Fix: researcher retry uses `last_eval.feedback`; `citations[]` only used `[n]`
- [x] User approve `.specs/features/orchestrator-eval-replan/spec.md`
- [x] User approve `.specs/features/orchestrator-eval-replan/design.md` before Tasks
- [x] After spec+design approval: update PROJECT.md caps (`max_retries_per_step` → 1 retry / 2 attempts; add `max_replans=1`) and parent spec superseded IDs
- [x] User approve `.specs/features/orchestrator-eval-replan/tasks.md` before Execute
- [x] Execute T1–T24 for `orchestrator-eval-replan` (uncommitted; user asked not to commit)
- [x] Fix LOOP-02: persist per-step eval feedback so search-wave retries rewrite from that step’s verdict (see validation report)
- [ ] Manual UAT: in-domain SSE, out-of-domain gate, Chainlit `[n]` side panel, follow-up omit-search (needs free Postgres port)
- [ ] Manual UAT: admission 1/topic, per-paper k=3, LOOP-04/05, T1/T2a/T3, WRITE-02 (needs free Postgres port)
- [ ] Atomic commits per task T1–T24 when the user asks to commit (partially mixed into admission commits for files those tasks share)
- [x] User requested Design for `admission-retrieve-per-topic` (2026-08-29; spec still draft)
- [x] User approve `.specs/features/admission-retrieve-per-topic/spec.md` and `design.md` before Tasks
- [x] User asked to Execute `.specs/features/admission-retrieve-per-topic/tasks.md` (2026-08-30)
- [x] Execute T1–T15 for `admission-retrieve-per-topic`
- [x] Fix: replan prefix packing remaps `search_artifacts` / `eval_by_step` to new indices (mixed-wave S8a)
- [x] Fix: Writer living/missing must survive replan (store hole **tasks**, exclude gaps from living)
- [x] User requested Design for `structured-aware-chunking` (2026-09-03; spec still formally Draft)
- [x] User requested Tasks for `structured-aware-chunking` (2026-09-03; spec/design still formally Draft)
- [x] User asked to Execute `.specs/features/structured-aware-chunking/tasks.md` (2026-09-03)
- [x] Execute T1–T19 for `structured-aware-chunking`; update PROJECT.md (HTML ingest, `retrieve_k_per_paper=5`) and parent spec superseded banners
- [ ] Manual UAT: structured-aware HTML chunking Independent Tests (`1706.03762` v7 ingest/retrieve; needs free Postgres port)

---

## Preferences

**Model Guidance Shown:** 2026-08-27 — validation / STATE / spec traceability is a good fit for a faster model.
