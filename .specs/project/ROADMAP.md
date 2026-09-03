# Roadmap

**Current Milestone:** Structured-aware HTML chunking  
**Status:** Execute T1–T19 done 2026-09-03. Manual UAT still pending (B-001).

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
**Target:** Manual UAT of `.specs/features/structured-aware-chunking/spec.md` Independent Tests (`1706.03762` v7; blocked by B-001).
**Spec:** Implemented 2026-09-03 (grill-me 2026-09-02).
**Design:** Executed 2026-09-03.
**Tasks:** T1–T19 executed 2026-09-03.

### Features

**Structured-aware chunking** - IMPLEMENTED (UAT pending)

- HTML-only retrieve ingest; wipe local PDF chunks; no PDF fallback
- Heading split + 512/50 inside a section; tables/equations never split
- Dual text: embed `embedding_text`, BM25/expand `content`; JSONB `section` / `caption` / `unit_ids`
- Per-paper hybrid `k=5`, overfetch/dedup/backfill, in-place placeholder expansion

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
