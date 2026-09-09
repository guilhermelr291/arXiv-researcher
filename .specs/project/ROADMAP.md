# Roadmap

**Current Milestone:** Voyage 4 large embeddings (code executed; live UAT pending)  
**Status:** `.specs/features/voyage-4-large-embeddings/` T1–T8 executed 2026-09-08 (not committed). Corpus reset is `scripts/wipe_paper_chunks.py --yes`, not boot. Live Independent Tests (1024 ingest after wipe; leftover 1536 INSERT fail; `2609.01617` / `1706.03762` retrieve) remain UAT (may be blocked by B-001). SSE agent dispatcher T1–T7 remain validated/uncommitted.

---

## Foundation

**Goal:** FastAPI app, env config (OpenAI + Postgres), health check, Dockerized Postgres/pgvector, checkpointer `setup()`.
**Target:** App starts, DB reachable, checkpoint and vector tables exist.

### Features

**API Skeleton** - DONE

- FastAPI application and project layout
- Environment-based config (OpenAI, `DATABASE_URL`)
- Health endpoint
- Docker Compose: Postgres with pgvector only

---

## ArXiv-grounded research

**Goal:** Students get didactic, cited AI/ML answers from arXiv only, with a visible plan-based loop.
**Target:** Spec `.specs/features/arxiv-grounded-research/spec.md` verified end-to-end (API + Chainlit).
**Spec:** Approved 2026-08-26. Design approved. Tasks executed 2026-08-26 (automated tests deferred).

### Features

**ArXiv-Grounded Plan-Based Research** - IMPLEMENTED

- Domain gate; planner; orchestrator eval/retry; arXiv researcher; grounded writer
- SSE `POST /research` (`query`, `thread_id`)
- pgvector lazy ingest `(arxiv_id, version)`
- `AsyncPostgresSaver` thread state
- Chainlit steps + side-panel citations

---

## Orchestrator eval + remaining-plan replan

**Goal:** Orchestrator interprets a variable `search` / `retrieve` / `writer` plan; eval is semantic per artifact; 1 retry (2 attempts) per step; 1 remaining-only replan per run; then `insufficient`.
**Target:** Execute `.specs/features/orchestrator-eval-replan/tasks.md` (T1–T24 done, uncommitted). LOOP-02 `eval_by_step` + query formulation 2026-08-28. Manual UAT still blocked by B-001.
**Spec:** Approved 2026-08-27.
**Design:** Approved 2026-08-27.

### Features

**Semantic step eval and remaining-plan replan** - VALIDATION ISSUES (uncommitted)

- Plan shapes: explain / compare (`search` × N) / follow-up (omit `search`)
- Search eval on titles+abstracts (no PDF); retrieve `[n]` + hybrid 0.7/0.3 under the hood; writer unchanged grounding
- 1 retry per step with feedback; 1 replan of the remaining suffix only
- Caps: retries + 1 replan, plus existing `max_steps` / timeout / `max_papers`

---

## Admission 1/topic + per-paper retrieve

**Goal:** Each search step admits at most one usable paper; retrieve floors chunks per paper; first search miss does not burn replan; missing topics are announced, never filled from model weights.
**Target:** Manual UAT of `.specs/features/admission-retrieve-per-topic/spec.md` (blocked by B-001).
**Spec:** Approved 2026-08-29. Validation fixes applied 2026-08-30 (replan artifact remap + Writer `hole_tasks`).
**Design:** Approved 2026-08-29.
**Tasks:** T1–T15 executed 2026-08-30.
**Routing atlas:** `.specs/features/admission-retrieve-per-topic/graph-flow.md`.

### Features

**Fair admission and per-paper retrieve** - IMPLEMENTED (UAT pending)

- 1 paper per named `search` step (judge ranking, clip, U1); admit on ingest, not at search eval pass
- Retrieve `k=3` per paper (no union `LIMIT k`); PDF fallback walks the same ranking — **superseded** by `structured-aware-chunking` (`retrieve_k_per_paper=5`, HTML ingest, no PDF fallback)
- Search attempt 1 always retries; attempt 2 S8a; retrieve T1/T2a/T3 + Writer hole rule (WRITE-02)

---

## Structured-aware HTML chunking

**Goal:** Retrieve ingest uses arXiv HTML; tables and display equations stay atomic; prose keeps section identity; hybrid still per-paper with expanded excerpts.
**Target:** Independent Tests of `.specs/features/structured-aware-chunking/spec.md` on `1706.03762` v7 passed 2026-09-03 (quick 014). Missing-HTML hole path not re-run.
**Spec:** Implemented 2026-09-03 (grill-me 2026-09-02). Code validation 2026-09-03 passed. Retrieve/cache/Writer UAT 2026-09-03.
**Design:** Executed 2026-09-03.
**Tasks:** T1–T19 executed 2026-09-03.

### Features

**Structured-aware chunking** - IMPLEMENTED (UAT on `1706.03762` v7 passed 2026-09-03)

- HTML-only retrieve ingest; wipe local PDF chunks; no PDF fallback
- Heading split + 512/50 inside a section; tables/equations never split
- Dual text: embed `embedding_text`, BM25/expand `content`; JSONB `section` / `caption` / `unit_ids`
- Per-paper hybrid `k=5`, overfetch/dedup/backfill, in-place placeholder expansion — **packed k and RRF-order pack superseded** by `retrieve-cross-encoder-rerank` (Voyage Execute 2026-09-04; UAT pending)

---

## Retrieve cross-encoder rerank

**Goal:** Hybrid overfetches more candidates; one Voyage `rerank-3` API call reorders them against the retrieve task; `cut_reranked` keeps the prefix within `margin=0.20` of that query’s best `relevance_score`, with `floor=0.30` and `top_n=12`, then `pack_hits` / expand.
**Target:** UAT: methodology query on `2609.01617` v1 plus regression on `1706.03762` v7. Do not treat UAT as complete.
**Spec:** `.specs/features/retrieve-cross-encoder-rerank/` — approved 2026-09-04 (Voyage). Prior Qwen Execute T1–T7 superseded as the live scorer.  
**Design:** Approved 2026-09-04 (Voyage). Qwen/HF design superseded.  
**Tasks:** Voyage T1–T7 executed 2026-09-04 (uncommitted). Qwen T1–T7 executed 2026-09-03 (superseded path).

### Features

**Task-conditioned retrieve rerank** - IMPLEMENTED (UAT pending)

- First-stage hybrid `k=40` per leg per paper (not pack-on-RRF@5)
- Voyage `rerank-3` scored once per execute on the retrieve **task** (no torch)
- Adaptive cut: `cut_reranked` (`top_n=12`, `margin=0.20`, `floor=0.30`) then `pack_hits` / expand
- No new graph node; no Citation score field; runtime Voyage fail → RRF pack; missing API key → boot fail

---

## SSE agent dispatcher

**Goal:** Refactor `POST /research` streaming: SSE headers, `SseFrame` + domain dispatcher, execute facade, compile-once graph wrapper, consume `astream_events` v2. Client event names and Chainlit stay unchanged.
**Target:** Live Independent Tests of `POST /research` until `done`/`insufficient`; Chainlit unchanged; follow-up `thread_id`.
**Spec:** Validated 2026-09-07 (unit + live headers/first frames; full Independent Tests still UAT).
**Design:** Validated 2026-09-07.
**Tasks:** T1–T7 executed 2026-09-07 (uncommitted).

### Features

**SSE Agent Dispatcher** - VALIDATED (full Independent Tests still UAT)

- Headers: `Cache-Control`, `Connection: keep-alive`, `X-Accel-Buffering: no`
- Dispatcher owns `include_types` and kind → handler; unknown kind fails
- Facade `execute` + graph wrapper compiled once (no ReAct `call_model`)
- Out: Chainlit Strategy, `/agent/execute`, body `message`, `answer_delta`, LC callback event names on the wire

---

## Voyage 4 large embeddings

**Goal:** First-stage vectors use Voyage `voyage-4-large` (1024-d); operator script wipes 1536 corpus; Voyage embed and rerank HTTP go through `langchain-voyageai` without changing `cut_reranked`.
**Target:** Approve spec + design + tasks, then Execute T1–T8. Independent Tests: 1024-d ingest, wipe script `--yes`, `VoyageAIRerank` still feeds the current cut.
**Spec:** Executed 2026-09-08 (grill-me locks; wipe amended to operator script). Discuss skipped. Live Independent Tests UAT pending.  
**Design:** Executed 2026-09-08.  
**Tasks:** Executed T1–T8 2026-09-08 (not committed).

### Features

**Voyage 4 large embeddings** - IMPLEMENTED (UAT pending)

- Replace OpenAI `text-embedding-3-small` with `VoyageAIEmbeddings` (`voyage-4-large`, default 1024)
- `Policy.embedding_dimensions=1024`; `ensure_schema` CREATE-only; `scripts/wipe_paper_chunks.py --yes` drops chunks/papers
- `score_chunks` uses `VoyageAIRerank` (`rerank-3`); no `ContextualCompressionRetriever`; no app `import voyageai`

---

## Future Considerations

- Auth, multi-user accounts, billing
- Thread TTL / delete and cross-session history UI
- Hover/JSX citation tooltips
- Writer `answer_delta` after eval pass
- Image/figure units and vision embeddings (cut from structured-aware-chunking)
- LLM unit summaries (cut; extractive/caption heuristics in v1 of that feature)
- Dockerize API and Chainlit
- Global semantic search over the full ingested corpus
- Human-in-the-loop plan approval
