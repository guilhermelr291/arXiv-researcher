# State

**Last Updated:** 2026-09-04
**Current Work:** Voyage rerank T1–T7 code-validated (uncommitted). Next: live UAT (`2609.01617` v1, `1706.03762` v7); may be blocked by B-001. Set `VOYAGE_API_KEY` in local `.env` before API boot.

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

### AD-017: Retrieve CrossEncoder rerank (2026-09-03) — SUPERSEDED by AD-018

**Decision:** After per-paper hybrid overfetch, score candidates once with `tomaarsen/Qwen3-Reranker-0.6B-seq-cls` via `langchain_community.cross_encoders.HuggingFaceCrossEncoder.score` (raw logits; no sigmoid). Rerank query is the retrieve `task` (plus step eval feedback on retry), not `FormulatedQuery`. `RetrieveRunner.run` (`agents/retrieve.py`) calls `cut_reranked` (`ingest/rerank.py`): sort by logit desc, optional `floor` empties the paper if best < floor, else walk and `break` when `(best - current) > margin`, also cap `top_n`. Defaults `top_n=12`, `margin=4.0`, `floor=None` are function parameters. Then `pack_hits` / `expand_hits`. First-stage `k=40` per leg. No LangGraph rerank node. Load/score failure falls back to ensemble-order `pack_hits(k=top_n)`.
**Reason:** LangSmith trace `01a06938-a33c-7bd0-aaaa-de2129d4d34e` — useful methodology chunks were already in ensemble ranks 7–27. Seq-cls logits are not probabilities and are not calibrated across queries, so the keep-set is relative to that query’s best hit. User specified adaptive `margin` + `top_n` + optional `floor` instead of a fixed `top_n` or a sigmoid threshold.
**Trade-off:** Local `torch` + ~0.6B download; CPU cold start; `margin=4.0` is un-calibrated; `floor=None` by default so retrieve will not empty on a weak best hit until UAT sets a floor.
**Impact:** Spec `.specs/features/retrieve-cross-encoder-rerank/spec.md` (Execute T1–T7 2026-09-03, uncommitted; UAT pending). Design and tasks executed 2026-09-03. Supersedes RETR-05 packed k=5 and RETR-08 RRF-order pack-to-5. Reopens admission’s “global rerank” out-of-scope row for this slice only (no MMR, no Citation score). **Superseded 2026-09-04:** local Qwen scorer is not the live path (AD-018).

### AD-018: Voyage rerank-3 retrieve scorer (2026-09-04)

**Decision:** Approve `.specs/features/retrieve-cross-encoder-rerank/spec.md` and `design.md` as written (Voyage amendment). Replace the local Qwen CrossEncoder with `voyageai.Client.rerank` (`rerank-3`, `truncation=True`, no `top_k`), map `index` back to input order, then per-paper `cut_reranked` (`top_n=12`, `margin=0.20`, `floor=0.30`). Rerank query stays retrieve `task` (+ step feedback). Missing `VOYAGE_API_KEY` fails `Settings()` at boot. Runtime Voyage errors pack ensemble `k=top_n`. Drop `torch` / `sentence-transformers` / `transformers`. No new graph node, no Citation score, no silent model fallback.
**Reason:** User approved spec + design 2026-09-04. Local 0.6B Hub download + CPU score made retrieve unusable vs the ~2 min timeout.
**Trade-off:** Extra vendor (Voyage) besides OpenAI; Preview `rerank-3`; `margin`/`floor` un-calibrated until UAT; API key required to start the process.
**Impact:** Qwen Execute T1–T7 SHALL NOT ship. Tasks rewritten 2026-09-04. UAT still pending (`2609.01617` v1, `1706.03762` v7).

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
- Search formulate that forbids `id:` and ANDs body terms (equation names, Transformer-big) into `abs:` misses a named historical paper on attempt 1. Trace `01a06917-e169-73f1-992c-ef624783dee9` retried after zero hits; the student query already had `1706.03762`. Quick 012: `id:{NNNN.NNNNN}` when present; body facts stay on retrieve.
- Writer LLM judge can `retry` a grounded answer to demand extra caveats (EN-FR 41.8 vs 41.0 already cited). Quick 013: pass when requested facts are cited; do not retry to rephrase a stated contradiction.
- `sentence_transformers.CrossEncoder.predict` applies `nn.Sigmoid` when `num_labels=1`. The Qwen3 seq-cls model card’s `predict` example prints probabilities; transformers `.logits` are the raw values `margin=4.0` needs. `HuggingFaceCrossEncoder.score` is `predict` — pass `activation_fn=Identity()` in `model_kwargs` or the adaptive cut never fires.
- Installing `sentence-transformers` / `transformers` makes FastAPI lifespan import `torch` even when `ingest/rerank.py` lazy-imports. `chunk_build` does `from langchain_text_splitters import …`, and that package `__init__` eagerly imports `SentenceTransformersTokenTextSplitter`. `hybrid` does `from langchain_classic.retrievers import EnsembleRetriever`, whose package `__init__` pulls `ParentDocumentRetriever` → the same splitters. Lazy `get_cross_encoder()` is not enough; defer those two imports until first retrieve/ingest.
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
| 012 | Search `id:` when arXiv id is present; do not AND body terms into abs | 2026-09-03 | — | ✅ Done |
| 013 | Writer judge passes cited fidelity; no retry for extra caveats | 2026-09-03 | — | ✅ Done |
| 014 | HTML Independent Tests UAT on canonical `1706.03762` v7 | 2026-09-03 | — | ✅ Done |

---

## Deferred Ideas

- [ ] Automated test suite (pytest / Testcontainers) — Captured during: tasks phase (explicitly deferred)
- [ ] Writer `answer_delta` after eval pass — Captured during: grill-me
- [ ] Auth, multi-user, billing — Captured during: project init
- [ ] Thread TTL/delete and history UI across browser sessions — Captured during: grill-me
- [x] arXiv TeX/HTML instead of PDF extract — Promoted to feature `structured-aware-chunking` (spec draft 2026-09-02)
- [ ] Qwen3-Reranker-4B if 0.6B still ranks isolated equations above V-C prose — Captured during: retrieve-cross-encoder-rerank specify; 0.6B path to be removed by Voyage amendment
- [ ] `rerank-3-lite` if Preview `rerank-3` latency or cost hurts UAT — Captured during: Voyage discuss 2026-09-04
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
- [x] Code validation: structured-aware HTML chunking (T1–T19 Done-when + live `1706.03762` v7 parse/chunk/pack/expand; 2026-09-03)
- [x] Manual UAT: structured-aware HTML chunking Independent Tests (`1706.03762` v7 retrieve/cache/Writer; 2026-09-03 quick 014; missing-HTML hole not re-run)
- [ ] Commit quick 012–014 when asked
- [x] User requested Design for `retrieve-cross-encoder-rerank` (2026-09-03; spec still formally Draft)
- [x] User requested Tasks for `retrieve-cross-encoder-rerank` (2026-09-03; spec/design still formally Draft)
- [x] User asked to Execute `.specs/features/retrieve-cross-encoder-rerank/tasks.md` (2026-09-03; no commits)
- [x] Execute T1–T7 for `retrieve-cross-encoder-rerank`; update PROJECT.md (first-stage k=40, adaptive `top_n=12`) and parent spec superseded banners
- [x] Code validation: retrieve CrossEncoder rerank (T1–T7 Done-when + `cut_reranked` unittest; 2026-09-04). Major: torch at FastAPI lifespan (DEP-01)
- [x] Torch-at-lifespan import: superseded by Voyage design (remove `torch` / `sentence-transformers` / `transformers`; do not defer splitter/Ensemble imports)
- [x] User approve `.specs/features/retrieve-cross-encoder-rerank/context.md` (Voyage amendment) before Specify
- [x] User requested Design for Voyage `retrieve-cross-encoder-rerank` (2026-09-04; spec still formally Draft)
- [x] User approve Voyage spec + design (`.specs/features/retrieve-cross-encoder-rerank/spec.md` + `design.md`) 2026-09-04
- [x] Rewrite Voyage tasks.md (Qwen T1–T7 superseded)
- [x] User asked to Execute Voyage `.specs/features/retrieve-cross-encoder-rerank/tasks.md` (2026-09-04; no commits)
- [x] Execute Voyage T1–T7 (do not Execute from the Qwen task list)
- [x] Code validation: Voyage retrieve-cross-encoder-rerank T1–T7 (2026-09-04). Gate: 14/14 `tests.test_cut_reranked`. Live Independent Tests still UAT.
- [ ] Add `VOYAGE_API_KEY` to `.env.example` (boot now requires it; example file still OpenAI-only)
- [ ] Manual UAT: retrieve rerank Independent Tests after Voyage swap (`2609.01617` v1; `1706.03762` v7; may be blocked by B-001)
- [ ] Atomic commits when the user asks to commit (Voyage T1–T7 uncommitted; Qwen path superseded)

---

## Preferences

**Model Guidance Shown:** 2026-08-27 — validation / STATE / spec traceability is a good fit for a faster model.
