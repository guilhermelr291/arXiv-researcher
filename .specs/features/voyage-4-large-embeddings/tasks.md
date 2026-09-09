# Voyage 4 Large Embeddings Tasks

**Design**: `.specs/features/voyage-4-large-embeddings/design.md`  
**Spec**: `.specs/features/voyage-4-large-embeddings/spec.md`  
**Status**: Validated T1–T8 2026-09-08 (code; unittest discover 57/57). Live Independent Tests remain UAT. Not committed.

`.specs/codebase/TESTING.md` does not exist. Same as v1 / orchestrator / admission / Voyage rerank / SSE: graph e2e (pytest, Testcontainers) is **out of scope**. Co-located **stdlib `unittest`** covers the embedding adapter (mocked partner), wipe-script refuse path (no DB), and restored `cut_reranked` / `score_chunks` mapping (mocked `compress_documents`). Live Independent Tests (1024-d ingest after wipe; leftover 1536 INSERT fail; `2609.01617` / `1706.03762` retrieve) stay **UAT** after Execute (may be blocked by B-001). Do **not** call the live Voyage API in unit tests.

HEAD still has `vector(1536)` and the missing-`kind` DROP/DELETE in `ensure_schema`. The working tree may already contain Policy 1024, CREATE-only DDL, and an untracked wipe script — Execute SHALL still satisfy every Done-when (do not assume WIP is complete or correct).

Do **not** change Gate, plan vocabulary, hybrid weights, first-stage `k`, `cut_reranked` knobs (`retrieve_rerank_top_n` on HEAD is **15** — leave it), splitter, HTML parse, SSE names, Citation fields, or RetrieveRunner control flow. No `ContextualCompressionRetriever`. No app `import voyageai`. No boot DROP. No checkpointer wipe. No `output_dimension`. No OpenAI embedding fallback.

**Local coverage matrix** (substitutes for missing TESTING.md):

| Code layer | Required test type | Parallel-safe |
| ---------- | ------------------ | ------------- |
| `pyproject.toml` / lockfile | none | Yes |
| `policy.py` constants | none | Yes |
| `adapters/voyage_embeddings.py` | unit | Yes |
| `repo/chunks.py` DDL / `ensure_schema` | none (Postgres UAT) | Yes |
| `scripts/wipe_paper_chunks.py` | unit (refuse path only; `--yes` is UAT) | Yes |
| `ingest/rerank.py` (`score_chunks` + existing cut helpers) | unit | Yes |
| `main.py` lifespan | none (boot needs Postgres) | Yes |
| `agents/retrieve.py` / `agents/factory.py` | none (no code change; grep Done-when) | Yes |
| markdown / `.env.example` | none | Yes |

**Gate commands:**

| Gate | Command |
| ---- | ------- |
| quick (per task) | `uv run python -m unittest tests.<module>` |
| full (after T8) | `uv run python -m unittest discover -s tests` |

---

## Execution Plan

### Phase 1: Foundation (parallel)

```
T1 [P]     T2 [P]     T5 [P]
```

### Phase 2: Adapter, DDL, rerank client (parallel after their deps)

```
T1 ──→ T3 [P]
T2 ──→ T4 [P]
T1 ──→ T6 [P]
```

### Phase 3: Lifespan wiring (sequential)

```
T3, T4 ──→ T7
```

T7 needs the adapter (T3) and 1024 CREATE-only DDL (T4). Do **not** leave HEAD on T7 without T4 if committing — Voyage 1024 ingest would target leftover `vector(1536)` schema.

T6 does **not** block T7 (rerank client vs embedding vendor).

### Phase 4: Docs (sequential)

```
T6, T7 ──→ T8
```

T5 does not block later phases (operator script is independent).

---

## Task Breakdown

### T1: Swap runtime Voyage dep to `langchain-voyageai` [P]

**What**: Add `langchain-voyageai>=0.4.1`; drop the direct `voyageai` runtime line (partner pulls the SDK transitively).
**Where**: `pyproject.toml` (and lockfile)
**Depends on**: None
**Reuses**: existing `uv` lock workflow; keep `langchain-openai` for chat
**Requirement**: VOY-06

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `langchain-voyageai>=0.4.1` is listed under `[project].dependencies`
- [x] Direct `voyageai` is **not** listed under `[project].dependencies`
- [x] Lockfile updated (`uv lock` / `uv sync`)
- [x] `langchain-openai` remains (chat only); no `langchain_community.embeddings.VoyageEmbeddings` added

**Tests**: none
**Gate**: none

**Verify**: `uv sync` succeeds; `python -c "import langchain_voyageai; from langchain_voyageai import VoyageAIEmbeddings, VoyageAIRerank"`; `pyproject.toml` has no standalone `voyageai` dependency line

**Commit**: `chore(embeddings): depend on langchain-voyageai instead of voyageai`

---

### T2: `Policy.embedding_dimensions = 1024` [P]

**What**: Add the named width constant used by chunk DDL. Do not touch cut / first-stage knobs.
**Where**: `src/plan_based_researcher/policy.py`
**Depends on**: None
**Reuses**: existing `Policy` class (PAT-10)
**Requirement**: VOY-03

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `Policy.embedding_dimensions == 1024`
- [x] Unchanged: `retrieve_first_stage_k == 40`, `retrieve_rerank_top_n == 15`, `retrieve_rerank_margin == 0.20`, `retrieve_rerank_floor == 0.30`
- [x] Unchanged: hybrid weights, `retrieve_k_per_paper`, splitter knobs, `max_papers`
- [x] No other Policy fields added or renamed

**Tests**: none
**Gate**: none

**Verify**: `python -c "from plan_based_researcher.policy import Policy; assert Policy.embedding_dimensions==1024; assert Policy.retrieve_first_stage_k==40; assert Policy.retrieve_rerank_top_n==15; assert Policy.retrieve_rerank_margin==0.20; assert Policy.retrieve_rerank_floor==0.30"`

**Commit**: `feat(embeddings): set Policy.embedding_dimensions to 1024`

---

### T3: `VoyageEmbeddingAdapter` [P]

**What**: Production `EmbeddingPort` wrapping `VoyageAIEmbeddings` (`voyage-4-large`, no `output_dimension`). Do not delete `openai_embeddings.py` yet (T7).
**Where**: `src/plan_based_researcher/adapters/voyage_embeddings.py` (new); `tests/test_voyage_embeddings.py` (new)
**Depends on**: T1
**Reuses**: `adapters/openai_embeddings.py` two-method async wrapper shape; `ports/embeddings.py` unchanged
**Requirement**: VOY-01, VOY-06

**Tools**:

- MCP: `user-context7` (optional; re-check `VoyageAIEmbeddings` kwargs vs 0.4.1)
- Skill: `context7-mcp` (only if Context7 is used)

**Done when**:

- [x] `EMBEDDING_MODEL_ID == "voyage-4-large"` in this module
- [x] `VoyageEmbeddingAdapter(api_key=...)` constructs `VoyageAIEmbeddings(model=EMBEDDING_MODEL_ID, api_key=api_key, truncation=True)` when a key is passed; otherwise lets the partner read `VOYAGE_API_KEY`
- [x] SHALL NOT pass `output_dimension`; SHALL NOT pass `model="voyage-4"` / `voyage-4-lite`
- [x] `embed_documents` → `await self._embeddings.aembed_documents(texts)` (partner `input_type="document"`)
- [x] `embed_query` → `await self._embeddings.aembed_query(text)` (partner `input_type="query"`)
- [x] File does not `import voyageai` / `from voyageai`
- [x] `openai_embeddings.py` still exists (T7 deletes it)
- [x] `EmbeddingPort` protocol file **not** edited

**Tests**: unit
**Gate**: quick

**Done when (tests)**:

- [x] `tests/test_voyage_embeddings.py` mocks `VoyageAIEmbeddings` (no live HTTP)
- [x] Constructor test: `model="voyage-4-large"`, `truncation=True`, `api_key` forwarded, `output_dimension` absent
- [x] `embed_documents` / `embed_query` delegate to `aembed_documents` / `aembed_query`; mocked vectors have length **1024**
- [x] Gate check passes: `uv run python -m unittest tests.test_voyage_embeddings`
- [x] Test count: **4** tests pass (no silent deletions)

**Verify**: Gate command above; `python -c "from plan_based_researcher.adapters.voyage_embeddings import EMBEDDING_MODEL_ID, VoyageEmbeddingAdapter; assert EMBEDDING_MODEL_ID=='voyage-4-large'"`

**Commit**: `feat(embeddings): add VoyageEmbeddingAdapter for voyage-4-large`

---

### T4: CREATE-only chunk DDL at Policy width [P]

**What**: `_CHUNKS_SQL` uses `vector({Policy.embedding_dimensions})`; `ensure_schema` only CREATE IF NOT EXISTS (remove kind wipe).
**Where**: `src/plan_based_researcher/repo/chunks.py`
**Depends on**: T2
**Reuses**: `_schema_statements`, existing upsert / similarity SQL; Policy import
**Requirement**: VOY-03, VOY-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `_CHUNKS_SQL` embedding column is `vector({Policy.embedding_dimensions})` (f-string / format from Policy, not a raw `1536`)
- [x] `ensure_schema`: `CREATE EXTENSION IF NOT EXISTS vector`; `CREATE TABLE IF NOT EXISTS` papers; `CREATE TABLE IF NOT EXISTS` chunks + existing indexes
- [x] Removed: `DROP TABLE chunks`, `DELETE FROM papers`, `_legacy_chunks_without_kind`, `_CHUNKS_KIND_STATE_SQL` (or equivalent kind-missing wipe)
- [x] Unchanged columns: `kind`, `unit_id`, `embedding_text`, `content`, JSONB `{section, caption, unit_ids}`, atomic identity index, `chunk_index` unique
- [x] Upsert / `similarity_search` / `list_chunks` SQL unchanged
- [x] No `ALTER COLUMN`; no Python length-assert before INSERT

**Tests**: none
**Gate**: none

**Verify**: grep `ensure_schema` / `chunks.py` finds no `DROP TABLE chunks` and no `DELETE FROM papers`; grep `_CHUNKS_SQL` finds `Policy.embedding_dimensions`; `python -c "from plan_based_researcher.repo import chunks as c; from plan_based_researcher.policy import Policy; assert f'vector({Policy.embedding_dimensions})' in c._CHUNKS_SQL; assert 'DROP TABLE' not in c._CHUNKS_SQL"`

**Commit**: `feat(store): create chunks as vector(1024) without boot wipe`

---

### T5: Operator wipe script `--yes` [P]

**What**: CLI that DROPs `chunks` and DELETEs `papers` only with `--yes`; refuse path exits 2 with no DB connection.
**Where**: `scripts/wipe_paper_chunks.py` (new); `tests/test_wipe_paper_chunks.py` (new)
**Depends on**: None
**Reuses**: `Settings.database_url`; `dict_row` + `autocommit=True`; `scripts/draw_graph.py` argparse + `if __name__`; Windows `WindowsSelectorEventLoopPolicy` (STATE lesson)
**Requirement**: VOY-04

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `--yes` required. Without it: refusal on **stderr**, `sys.exit(2)`, **no** `Settings()`, **no** DB connect
- [x] With `--yes`: `Settings()` → async psycopg (`autocommit=True`, `dict_row`) → print before-counts → `DROP TABLE IF EXISTS chunks` → `DELETE FROM papers` if `papers` exists
- [x] SHALL NOT `DROP SCHEMA`; SHALL NOT `DROP TABLE` by wildcard; SHALL NOT drop LangGraph checkpointer tables
- [x] SHALL NOT import the graph, embeddings, `voyageai`, or `langchain_voyageai`
- [x] SHALL NOT call `PgChunkRepository.ensure_schema` (script does not CREATE)
- [x] Windows: `WindowsSelectorEventLoopPolicy` before `asyncio.run`

**Tests**: unit
**Gate**: quick

**Done when (tests)**:

- [x] Subprocess (or argv) without `--yes`: return code **2**; stderr mentions `--yes` / refuse; `Settings` and `AsyncConnection.connect` are not called (patch or no-network)
- [x] Do **not** run `--yes` against a live DB in this unittest (UAT)
- [x] Gate check passes: `uv run python -m unittest tests.test_wipe_paper_chunks`
- [x] Test count: **2** tests pass (no silent deletions)

**Verify**: Gate command above; `uv run python scripts/wipe_paper_chunks.py` → exit 2, no SQL

**Commit**: `feat(store): add wipe_paper_chunks.py requiring --yes`

---

### T6: `score_chunks` via `VoyageAIRerank.compress_documents` [P]

**What**: Replace app `voyageai.Client.rerank` with `VoyageAIRerank.compress_documents`; restore and extend `tests/test_cut_reranked.py`. Retrieve walk files are grep-only (no edits).
**Where**: `src/plan_based_researcher/ingest/rerank.py`; `tests/test_cut_reranked.py` (restore if missing)
**Depends on**: T1
**Reuses**: `build_rerank_query`, `document_text`, `cut_reranked`, `scores_from_rerank_results`, `RERANK_MODEL_ID = "rerank-3"`, LangSmith `@traceable(name="voyage_rerank")` + `_voyage_rerank_inputs` (omit API key)
**Requirement**: VOY-05, VOY-06, VOY-07

**Tools**:

- MCP: `user-context7` (optional; re-check `VoyageAIRerank.compress_documents` / `top_k`)
- Skill: `context7-mcp` (only if Context7 is used)

**Done when**:

- [x] `score_chunks(chunks, query, *, api_key: str) -> list[float]` signature unchanged
- [x] Empty `chunks` → `[]`; do **not** construct `VoyageAIRerank`; no HTTP
- [x] Non-empty: `Document(page_content=document_text(c), metadata={"input_index": i})` per input order
- [x] `VoyageAIRerank(model=RERANK_MODEL_ID, api_key=api_key, top_k=len(docs), truncation=True)` then `compress_documents(docs, query)` (sync)
- [x] SHALL NOT pass `top_k=Policy.retrieve_rerank_top_n`; SHALL NOT omit `top_k`; SHALL NOT use `ContextualCompressionRetriever`; SHALL NOT call `acompress_documents`
- [x] Map compressed docs via `metadata["input_index"]` + `metadata["relevance_score"]` into objects with `.index` / `.relevance_score`; return `scores_from_rerank_results(len(chunks), ...)`
- [x] Missing `input_index` / `relevance_score` raises (retrieve `except Exception` → RRF fallback; no graph test)
- [x] No `import voyageai` / `from voyageai` in this file (or anywhere under `src/plan_based_researcher` after this task’s rerank edit — adapter in T3 uses `langchain_voyageai` only)
- [x] Remove unused `RERANK_TIMEOUT_SECONDS` if nothing else references it
- [x] `cut_reranked` / `build_rerank_query` / `document_text` / `scores_from_rerank_results` behavior **unchanged**
- [x] `agents/retrieve.py` and `agents/factory.py` **not** edited: still `to_thread(score_chunks, ..., api_key=)`; still per-paper `cut_reranked` then `pack_hits` / `expand_hits`; still ensemble `pack_hits(k=top_n)` on exception; still `document_text` (via `score_chunks`); no `ContextualCompressionRetriever`

**Tests**: unit
**Gate**: quick

**Done when (tests)**:

- [x] Restored cut / query / document / `scores_from_rerank_results` cases (tiny `ChunkRecord` fixtures; no DB; no Voyage HTTP)
- [x] `score_chunks([])` returns `[]` and does not construct `VoyageAIRerank` (patch constructor)
- [x] Mock `compress_documents` returns score-sorted `Document`s with `input_index` + `relevance_score`; assert **input-order** floats
- [x] Missing `input_index` or `relevance_score` raises
- [x] Constructor called with `top_k == len(docs)`, `model="rerank-3"`, `truncation=True` (not `Policy.retrieve_rerank_top_n`)
- [x] Gate check passes: `uv run python -m unittest tests.test_cut_reranked`
- [x] Test count: **17** tests pass (7 cut + 2 query + 1 document + 3 score-map + 1 empty no-construct + 1 compress mapping + 2 missing metadata + 1 constructor `top_k`; no silent deletions)
- [x] STATE lesson: if only `__pycache__/*.pyc` exists, restore the `.py` file before treating the gate as green

**Verify**: Gate command above; grep `src/plan_based_researcher` finds no `import voyageai` / `from voyageai` and no `ContextualCompressionRetriever`; grep `retrieve.py` finds `cut_reranked`, `pack_hits`, `expand_hits`, `to_thread`, `score_chunks`; grep `graph/build.py` finds no `rerank` node

**Commit**: `feat(rerank): score via VoyageAIRerank.compress_documents`

---

### T7: Wire Voyage embeddings in lifespan

**What**: Construct `VoyageEmbeddingAdapter` with `settings.voyage_api_key`; delete `OpenAIEmbeddingAdapter` from production retrieve/ingest.
**Where**: `src/plan_based_researcher/main.py`; delete `src/plan_based_researcher/adapters/openai_embeddings.py`
**Depends on**: T3, T4
**Reuses**: existing `HybridRetrieveAdapter(repo, embeddings)` and `AgentFactory(..., api_key=settings.openai_api_key, voyage_api_key=settings.voyage_api_key)`
**Requirement**: VOY-01, VOY-02, VOY-06

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `embeddings = VoyageEmbeddingAdapter(api_key=settings.voyage_api_key)`
- [x] OpenAI key still passed into `AgentFactory` / eval strategies for **chat** only
- [x] No `OpenAIEmbeddingAdapter` / `OpenAIEmbeddings` / `text-embedding-3-small` on the retrieve/ingest path
- [x] `openai_embeddings.py` deleted; no remaining imports of it
- [x] No Voyage HTTP ping at startup
- [x] `factory.py` / `retrieve.py` / `hybrid.py` **not** edited in this task (port injection unchanged)
- [x] `Settings.voyage_api_key` still the shared embed + rerank key (no new env var)

**Tests**: none
**Gate**: none

**Verify**: grep `src/plan_based_researcher` finds `VoyageEmbeddingAdapter` / `voyage-4-large` and does not find `OpenAIEmbeddingAdapter` / `OpenAIEmbeddings` / `text-embedding-3-small`; `python -c "from plan_based_researcher.main import create_app"` (import only; do not boot lifespan without Postgres)

**Commit**: `feat(embeddings): wire VoyageEmbeddingAdapter in FastAPI lifespan`

---

### T8: PROJECT stack, `.env.example`, parent width/client banners

**What**: Document Voyage embeddings 1024-d; OpenAI LLM-only; add `VOYAGE_API_KEY` to the example env; banner parent EMB-01 / STORE-01 width / AD-018 client.
**Where**: `.specs/project/PROJECT.md`; `.env.example`; `.specs/features/arxiv-grounded-research/spec.md`; `.specs/features/structured-aware-chunking/spec.md`; `.specs/features/retrieve-cross-encoder-rerank/spec.md`
**Depends on**: T6, T7
**Reuses**: existing parent amendment-banner style (chunking / rerank headers)
**Requirement**: VOY-08, VOY-06

**Tools**:

- MCP: NONE
- Skill: NONE

**Done when**:

- [x] `PROJECT.md` Key dependencies: embeddings Voyage `voyage-4-large` (1024-d); Voyage `rerank-3` still the retrieve scorer; OpenAI remains `gpt-5.1` / `gpt-5-mini` via `langchain-openai` **chat**
- [x] `PROJECT.md` Constraints: embeddings are Voyage (not “LLM and embeddings: OpenAI only”); OpenAI is the LLM vendor
- [x] `.env.example` includes `VOYAGE_API_KEY=` (no secret value)
- [x] Parent `arxiv-grounded-research/spec.md`: EMB-01 model+1536 superseded by this feature; Constraints Embeddings row no longer claims `text-embedding-3-small` as live
- [x] Parent `structured-aware-chunking/spec.md`: STORE-01 **width** `vector(1536)` superseded (columns / identity unchanged); kind-wipe at boot superseded
- [x] Parent `retrieve-cross-encoder-rerank/spec.md`: app `voyageai.Client` as the required client superseded by `VoyageAIRerank` (scoring/cut locks unchanged)
- [x] Do **not** claim UAT-complete; do **not** rewrite admission T1/T2a/T3 routing text

**Tests**: none
**Gate**: full

**Done when (gate)**:

- [x] Gate check passes: `uv run python -m unittest discover -s tests`
- [x] Existing SSE / english test modules still present and passing (no silent deletions)
- [x] New modules from T3 / T5 / T6 included in discover

**Verify**: grep `PROJECT.md` for `voyage-4-large` and 1024; grep `.env.example` for `VOYAGE_API_KEY`; full unittest discover

**Commit**: `docs(embeddings): switch stack to Voyage voyage-4-large 1024-d`

---

## Parallel Execution Map

```
Phase 1 (Parallel):
  ├── T1 [P]  pyproject langchain-voyageai
  ├── T2 [P]  Policy.embedding_dimensions
  └── T5 [P]  wipe script + refuse-path unittest

Phase 2 (Parallel after deps):
  T1 complete → T3 [P]  VoyageEmbeddingAdapter + unittest
  T2 complete → T4 [P]  CREATE-only vector(1024) DDL
  T1 complete → T6 [P]  VoyageAIRerank + restore test_cut_reranked

Phase 3 (Sequential):
  T3 and T4 complete → T7  lifespan + delete OpenAI embedding adapter

Phase 4 (Sequential):
  T6 and T7 complete → T8  PROJECT / .env.example / parent banners
```

**Parallelism constraint:** Phase-1 `[P]` tasks share no files. Phase-2 `[P]` tasks edit distinct files (`voyage_embeddings.py`, `chunks.py`, `rerank.py` + `test_cut_reranked.py`). Required test types for T3 / T5 / T6 are parallel-safe. T7 is the only editor of `main.py` / `openai_embeddings.py`. T4 is the only editor of `chunks.py`. T2 is the only editor of `policy.py`.

**How parallel execution works:** `[P]` tasks run via sub-agents (one per task). Sequential tasks also go to sub-agents, one at a time. Orchestrator updates this file’s checkboxes after each result.

**Commit constraint:** Parallel `[P]` tasks must not each `git commit` (STATE lesson). Serialize commits on the orchestrator. Do not commit T7 without T4.

---

## Requirement Traceability

| ID | Tasks |
| -- | ----- |
| VOY-01 | T3, T7 |
| VOY-02 | T7 |
| VOY-03 | T2, T4 |
| VOY-04 | T4, T5 |
| VOY-05 | T6 |
| VOY-06 | T1, T3, T6, T7, T8 |
| VOY-07 | T6 |
| VOY-08 | T8 |

**Coverage:** 8/8 spec IDs have ≥1 task. 0 unmapped tasks without a requirement.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1 | 1 manifest (`pyproject.toml` + lock) | ✅ Granular |
| T2 | 1 Policy field | ✅ Granular |
| T3 | 1 adapter + its unittest | ⚠️ Cohesive |
| T4 | 1 repo module (DDL + `ensure_schema`) | ✅ Granular |
| T5 | 1 script + refuse-path unittest | ⚠️ Cohesive |
| T6 | 1 scorer function + restored unittest (cut helpers stay in-file) | ⚠️ Cohesive |
| T7 | lifespan swap + delete orphaned OpenAI adapter | ⚠️ Cohesive |
| T8 | product docs + parent supersede banners (VOY-08) | ⚠️ Cohesive |

T3/T5/T6 keep tests in the same task (coverage matrix). T7 is one wiring slice so `main.py` never imports a deleted module. T8 is one docs requirement (VOY-08), not a second feature.

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram shows | Status |
| ---- | ----------------- | ------------- | ------ |
| T1 | None | Phase 1, no inbound | ✅ Match |
| T2 | None | Phase 1, no inbound | ✅ Match |
| T3 | T1 | T1→T3 | ✅ Match |
| T4 | T2 | T2→T4 | ✅ Match |
| T5 | None | Phase 1, no inbound | ✅ Match |
| T6 | T1 | T1→T6 | ✅ Match |
| T7 | T3, T4 | T3→T7, T4→T7 | ✅ Match |
| T8 | T6, T7 | T6→T8, T7→T8 | ✅ Match |

Phase-1 `[P]` T1/T2/T5 have no inter-deps. Phase-2 `[P]` T3/T4/T6 do not depend on each other. T7 is not `[P]` (depends on T3 and T4). T5 does not appear as a dependency of T7/T8.

---

## Test Co-location Validation

`.specs/codebase/TESTING.md` does not exist. Project default: automated graph tests deferred (STATE). This feature’s spec Independent Tests that are automatable without Postgres/Voyage HTTP are co-located with the tasks that create those layers.

| Task | Code layer | Matrix requires | Task says | Status |
| ---- | ---------- | --------------- | --------- | ------ |
| T1 | dependencies | none | none | ✅ OK |
| T2 | policy constants | none | none | ✅ OK |
| T3 | embedding adapter | unit | unit | ✅ OK |
| T4 | chunk DDL / `ensure_schema` | none (Postgres UAT) | none | ✅ OK |
| T5 | wipe CLI refuse path | unit | unit | ✅ OK |
| T6 | ingest score/cut helpers | unit | unit | ✅ OK |
| T7 | lifespan | none | none | ✅ OK |
| T8 | markdown / env example | none | none | ✅ OK |

No task uses “tested in another task” to skip T3/T5/T6 unit tests. Live 1024 ingest, leftover-1536 INSERT fail, and `--yes` against a real DB stay UAT (B-001 may block).

---

## Confirm before Execute

Live Independent Tests (`SELECT vector_dims(embedding)` = 1024 after wipe+ingest; leftover 1536 INSERT fail; retrieve on `2609.01617` / `1706.03762`) are **not** in this list.

Operator must set `VOYAGE_API_KEY` in local `.env` before API boot (do not commit the secret). After Execute, corpus reset is `python scripts/wipe_paper_chunks.py --yes` then restart — not an API boot wipe.
