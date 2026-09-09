# Voyage 4 Large Embeddings Specification

**Feature:** `voyage-4-large-embeddings`  
**Spec status:** Validated T1–T8 2026-09-08 (code; unittest discover 57/57). Live Independent Tests remain UAT (may be blocked by B-001). Not committed.  
**Design:** Executed (`.specs/features/voyage-4-large-embeddings/design.md`, 2026-09-08)  
**Tasks:** Executed (`.specs/features/voyage-4-large-embeddings/tasks.md`, T1–T8 2026-09-08)  
**Date:** 2026-09-08  
**Gray areas:** Locked in grill-me 2026-09-08; wipe path amended 2026-09-08 (operator script, not boot); `discuss.md` skipped  
**Parent product:** `.specs/features/arxiv-grounded-research/spec.md` (approved v1)  
**Parent chunking:** `.specs/features/structured-aware-chunking/spec.md` (executed)  
**Parent rerank:** `.specs/features/retrieve-cross-encoder-rerank/spec.md` (Voyage Execute 2026-09-04; UAT pending)  
**Architecture constraints:** `.specs/features/arxiv-grounded-research/context.md` (PAT-01–PAT-12 still apply)

This spec replaces the **embedding vendor and vector width**, and swaps the Voyage **HTTP clients** to the LangChain partner package. It does **not** change Gate, plan vocabulary, admission, HTML ingest, dual-text (`embedding_text` / `content`), hybrid **weights** 0.7/0.3, first-stage `k=40`, `cut_reranked` knobs, `pack_hits` / `expand_hits`, `rerank-3`, SSE event **names**, Chainlit, checkpointer schema, or Writer `[n]` **format**.

## Problem Statement

Retrieve still embeds `embedding_text` with OpenAI `text-embedding-3-small` (1536-d) while Voyage already scores the same retrieve with `rerank-3`. The first-stage vector leg and the rerank vendor are therefore two families. `voyage-4-large` is the Voyage default retrieval embedding (1024-d); LangChain already ships `VoyageAIEmbeddings` / `VoyageAIRerank` the same way `OpenAIEmbeddings` is used today. Existing local rows are `vector(1536)` and `CREATE TABLE IF NOT EXISTS` will not alter them, so a client-only swap would mix spaces or fail on INSERT.

## Goals

- [x] Production embeddings are Voyage `voyage-4-large` at the model’s **default 1024** dimensions, behind the existing `EmbeddingPort`.
- [x] `Policy.embedding_dimensions` is **1024** and `chunks.embedding` DDL is `vector(1024)`. `ensure_schema` only `CREATE IF NOT EXISTS` — it never drops corpus tables.
- [x] Clearing an old 1536 corpus is an **operator script** (`scripts/wipe_paper_chunks.py`, requires `--yes`). Next API boot creates empty `vector(1024)` chunks; retrieve reingests HTML.
- [x] Voyage HTTP for embeddings **and** rerank goes through `langchain-voyageai` (`VoyageAIEmbeddings`, `VoyageAIRerank`). Retrieve logic stays hybrid → unique list → score every candidate → `cut_reranked` → pack / expand.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Boot-time `DROP TABLE chunks` / `DELETE FROM papers` in `ensure_schema` | User: automatic wipe is dangerous if the model/width changes again |
| `kind`-column auto-wipe remaining in `ensure_schema` | Same risk; migration already applied locally; pattern SHALL be removed |
| `ContextualCompressionRetriever` wrapping `EnsembleRetriever` | Grill-me: same retrieve logic; compressor `top_k` would skip `cut_reranked` / pack / expand |
| Voyage `top_k` (or compressor `top_k`) as the Writer cut | Parent RERANK lock; score the full unique list, then `cut_reranked` |
| Changing `rerank-3` / `cut_reranked` (`top_n=12`, `margin=0.20`, `floor=0.30`) | Client swap only |
| `output_dimension` 256 / 512 / 2048 | User locked Voyage default 1024 |
| In-place re-embed of existing `embedding_text` | Operator wipes; next retrieve reingests |
| OpenAI embedding fallback / dual corpus | One space only |
| `voyage-4` / `voyage-4-lite` | Model id locked to `voyage-4-large` |
| `langchain_community.embeddings.VoyageEmbeddings` | Legacy community class; partner package is the OpenAI analog |
| `int8` / `binary` / `ubinary` embeddings | Keep float vectors in pgvector |
| Voyage tokenizer for the 512/50 splitter | Parent `cl100k_base`; Voyage context 32k ≫ 512 |
| Wiping LangGraph checkpointer tables | Only paper/chunk vectors are incompatible |
| New env var for embeddings | Reuse required `VOYAGE_API_KEY` |
| Ping Voyage at FastAPI startup | Parent: boot gate is Settings, not a health call |
| New LangGraph node, Citation score, Gate/search/Writer contract | Parent |
| Production dual-write / online ALTER of `vector(1536)` → `vector(1024)` | Local script + recreate; ALTER cannot convert spaces |

### Supersedes (parent specs / decisions)

Upon approval, these rows are **replaced**. Unnamed parent IDs stay in force.

| Parent ID / lock | What no longer holds |
| ---------------- | -------------------- |
| EMB-01 (model + 1536 store) | Embed with OpenAI `text-embedding-3-small` into `vector(1536)`. **Unchanged:** pgvector store; RAG scoped to selected papers; HTML ingest + `embedding_text` (structured-aware). Splitter 500/100 already superseded by 512/50. |
| AD-006 embeddings line | Embeddings: `text-embedding-3-small` |
| PROJECT.md “LLM and embeddings: OpenAI only” | Embeddings are Voyage. **Unchanged:** OpenAI remains the LLM vendor (`gpt-5.1` / `gpt-5-mini`, `langchain-openai` chat). |
| STORE-01 / structured-aware `embedding vector(1536)` | Column width 1536. **Unchanged:** `kind`, `unit_id`, dual text, JSONB keys, atomic identity. |
| Structured-aware `ensure_schema` kind wipe | `DROP TABLE chunks` + `DELETE FROM papers` when `kind` is missing. **Unchanged:** `CREATE IF NOT EXISTS` for empty databases. |
| AD-018 / rerank design “`voyageai.Client.rerank` is the required client” | App code SHALL call `langchain_voyageai.VoyageAIRerank` (or its documented compress/rerank methods) instead of constructing `voyageai.Client` in app modules. **Unchanged:** `rerank-3`, `truncation`, no Writer `top_k`, index/`relevance_score` mapping, `cut_reranked`, RRF fallback, boot fail without `VOYAGE_API_KEY`. |

**Amended (not replaced):** RETR-01 hybrid; RETR-07 / RETR-09 expand; first-stage `k=40`; one score pass per execute; per-paper cut; LANG-05 English rerank query; PAT-08 embeddings stay behind a port; `ensure_schema` still runs in lifespan for CREATE.

**Locked from specify (do not reopen in Design):**

- Embedding **model id:** `voyage-4-large`. SHALL NOT call `voyage-4`, `voyage-4-lite`, or OpenAI embedding models in production retrieve/ingest.
- Embedding **width:** Voyage default **1024**. SHALL NOT pass `output_dimension`. `Policy.embedding_dimensions` SHALL be `1024`. pgvector DDL SHALL use that constant (`vector(1024)`).
- Embedding **client:** `langchain_voyageai.VoyageAIEmbeddings` wrapped like today’s `OpenAIEmbeddingAdapter` (`aembed_documents` / `aembed_query`). `embed_documents` SHALL use Voyage `input_type="document"`; `embed_query` SHALL use `input_type="query"`. SHALL NOT embed retrieval texts with `input_type=None`.
- Rerank **client:** `langchain_voyageai.VoyageAIRerank` with **`model="rerank-3"`**. SHALL NOT wrap the hybrid retriever in `ContextualCompressionRetriever`. SHALL NOT pass `top_k=Policy.retrieve_rerank_top_n` into the Voyage/LangChain rerank call. Score the **full** unique first-stage list (`top_k` omitted or `top_k=len(documents)`).
- Rerank **pipeline:** unchanged. Query = retrieve `task` (+ step feedback on retry). Document = `document_text`. One call per execute. Map scores to input order. Per-paper `cut_reranked` then `pack_hits` / `expand_hits`. Runtime failure → ensemble pack `k=top_n`.
- **Schema at boot:** `ensure_schema` SHALL only `CREATE EXTENSION` / `CREATE TABLE IF NOT EXISTS` (papers + chunks at 1024). SHALL NOT `DROP` `chunks` or `DELETE` `papers` on API start (including the old missing-`kind` branch).
- **Corpus reset:** a repo script (`scripts/wipe_paper_chunks.py`) SHALL `DROP TABLE IF EXISTS chunks` and `DELETE FROM papers` only when invoked with **`--yes`**. Without `--yes` it SHALL exit non-zero and mutate nothing. SHALL NOT drop checkpointer tables. After the script, the next `ensure_schema` creates empty `vector(1024)` chunks; `paper_has_chunks` is false until HTML ingest.
- **Key:** same required `VOYAGE_API_KEY` / `Settings.voyage_api_key` for embeddings and rerank. No second Voyage key.
- App modules under `src/plan_based_researcher` SHALL NOT `import voyageai`. The partner package may depend on `voyageai` transitively.
- Splitter, HTML parse, `embedding_text` heuristics, hybrid weights, SSE, Chainlit: unchanged.

---

## User Stories

### P1: Voyage embeddings on ingest and query ⭐ MVP

**User Story**: As a student, I want first-stage vector retrieve to use Voyage `voyage-4-large` on the same `embedding_text` already stored for BM25/expand, so the hybrid vector leg and Voyage rerank share one vendor family.

**Why P1**: This is the quality change. Schema and client wiring exist only to make this space consistent.

**Acceptance Criteria**:

1. WHEN retrieve ingests a paper (cache miss) THEN the system SHALL call `EmbeddingPort.embed_documents` on each draft’s `embedding_text` and SHALL persist vectors of length **1024**.
2. WHEN hybrid vector retrieve runs THEN `EmbeddingPort.embed_query` SHALL embed the formulated hybrid query with the same model and width, with Voyage query `input_type`.
3. WHEN the production embedding adapter is constructed THEN it SHALL wrap `langchain_voyageai.VoyageAIEmbeddings` with `model="voyage-4-large"` and SHALL NOT construct `langchain_openai.OpenAIEmbeddings` for retrieve/ingest.
4. WHEN `langchain-openai` is still a dependency THEN it SHALL be used for chat models only, not for embeddings on the retrieve path.
5. WHEN FastAPI lifespan wires retrieve THEN it SHALL pass the Voyage embedding adapter into `HybridRetrieveAdapter` / `RetrieveRunner` (same `EmbeddingPort` as today).

**Independent Test**: After a cache-miss ingest, `SELECT vector_dims(embedding)` (or equivalent) is 1024 for new rows. Grep production retrieve/ingest wiring finds `VoyageAIEmbeddings` / `voyage-4-large` and does not find `OpenAIEmbeddings` / `text-embedding-3-small`. A unit or smoke test of the adapter returns length-1024 lists (live or mocked partner client).

---

### P1: 1024 DDL + operator wipe script ⭐ MVP

**User Story**: As a maintainer, I want the schema width in Policy/DDL and a script I run on purpose, so changing embedding models cannot delete the local corpus on a forgotten boot.

**Why P1**: `CREATE TABLE IF NOT EXISTS` will not alter `vector(1536)`. Automatic DROP on start is how a future swap silently destroys papers.

**Acceptance Criteria**:

1. WHEN `Policy` is read THEN `embedding_dimensions` SHALL be **1024**. WHEN `chunks` is created THEN `embedding` SHALL be `vector(1024)` using that constant.
2. WHEN `ensure_schema` runs THEN it SHALL `CREATE IF NOT EXISTS` papers/chunks only. Grep of `ensure_schema` SHALL find no `DROP TABLE chunks` and no `DELETE FROM papers`.
3. WHEN `scripts/wipe_paper_chunks.py` is run **without** `--yes` THEN it SHALL exit non-zero and SHALL NOT drop or delete corpus rows.
4. WHEN the script is run **with** `--yes` THEN it SHALL `DROP TABLE IF EXISTS chunks` and `DELETE FROM papers`, and SHALL NOT drop LangGraph checkpointer tables.
5. WHEN the script has run and the API boots THEN `ensure_schema` SHALL create empty `chunks` at 1024. A later retrieve of a previously cached key SHALL miss (`paper_has_chunks` false) and HTML-ingest + Voyage-embed.
6. WHEN the API boots against a leftover `vector(1536)` table (script not run) THEN `ensure_schema` SHALL NOT drop it. Ingest of 1024-d vectors SHALL fail at INSERT until the operator runs the script (safe fail, not silent mix).

**Independent Test**: Grep `repo/chunks.py` `ensure_schema` has no DROP/DELETE of corpus tables; `_CHUNKS_SQL` uses `Policy.embedding_dimensions`. Run the wipe script without `--yes` → exit ≠ 0, row counts unchanged. With `--yes` against a local DB: `chunks` gone, `papers` empty, checkpoint tables still present. Next API boot creates `vector(1024)` chunks.

---

### P1: LangChain Voyage rerank client, same cut ⭐ MVP

**User Story**: As a maintainer, I want `score_chunks` to use the same LangChain partner abstraction as embeddings (`VoyageAIRerank`), without changing what the Writer sees.

**Why P1**: User asked for the OpenAI-style wrapper on **both** Voyage calls. Changing the compressor pipeline would change ranking, which is out of scope.

**Acceptance Criteria**:

1. WHEN `score_chunks` scores a non-empty list THEN it SHALL use `langchain_voyageai.VoyageAIRerank` with `model="rerank-3"` (same timeout / no-retry intent as today: 30s, `max_retries=0` or partner equivalent).
2. WHEN that call is made THEN every input document SHALL receive a `relevance_score`. The function SHALL still return one float per input chunk **in input order** (`scores_from_rerank_results` or equivalent mapping from partner results / `relevance_score` metadata).
3. WHEN `RetrieveRunner` obtains scores THEN it SHALL still `cut_reranked` per paper, then `pack_hits` / `expand_hits`. SHALL NOT instantiate `ContextualCompressionRetriever` on the retrieve path.
4. WHEN Voyage scoring fails at runtime THEN retrieve SHALL still pack ensemble order with `k=top_n` and SHALL NOT crash the graph (parent).
5. WHEN application source under `src/plan_based_researcher` is grepped THEN there SHALL be no `import voyageai` / `from voyageai`. LangSmith `voyage_rerank` tracing SHALL still omit the API key (quick 016).

**Independent Test**: Grep `src/plan_based_researcher` for `voyageai` imports (none) and for `ContextualCompressionRetriever` (none on retrieve). `score_chunks` tests still map index → input order and still feed `cut_reranked`. Existing `tests.test_cut_reranked` (or successor) still pass. Optional: mock `VoyageAIRerank` to prove `score_chunks` does not construct `voyageai.Client`.

---

## Edge Cases

- WHEN `chunks` still exists as `vector(1536)` THEN boot SHALL leave it; the operator MUST run the wipe script before Voyage ingest can succeed.
- WHEN `chunks` does not exist THEN `ensure_schema` SHALL create `vector(1024)` only and SHALL NOT delete `papers`.
- WHEN the wipe script deletes `papers` but checkpointer `GraphState.papers` still lists keys THEN retrieve SHALL reingest those keys (cache miss), not assume rows exist.
- WHEN `VoyageAIRerank` defaults `top_k` to a small integer THEN production wiring SHALL override so the call returns **all** candidates (omit `top_k` or set `top_k=len(documents)`). Design SHALL confirm the partner constructor default against this lock.
- WHEN the unique first-stage list is empty THEN `score_chunks` SHALL return `[]` and SHALL NOT call Voyage (unchanged).
- WHEN a single document exceeds Voyage embedding/rerank context THEN partner `truncation=True` (Voyage default) SHALL apply; SHALL NOT change atomic table/equation `content` storage.
- WHEN embed or rerank rate-limits THEN embed failure on ingest SHALL surface as retrieve ingest failure for that paper (walk `ranked_keys` as today). Rerank rate-limit SHALL use the parent RRF fallback, not a second Voyage model.
- WHEN `VOYAGE_API_KEY` is missing THEN `Settings()` SHALL still fail boot (parent). That is not the runtime rerank fallback.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status | Task |
| -------------- | ----- | ----- | ------ | ---- |
| VOY-01 | P1: Voyage embeddings | Execute | ✅ Verified (code) | T3, T7 |
| VOY-02 | P1: Voyage embeddings | Execute | ✅ Verified (code) | T7 |
| VOY-03 | P1: 1024 DDL + operator wipe | Execute | ✅ Verified (code) | T2, T4 |
| VOY-04 | P1: 1024 DDL + operator wipe | Execute | ✅ Verified (code; `--yes` UAT pending) | T4, T5 |
| VOY-05 | P1: LangChain rerank client | Execute | ✅ Verified (code) | T6 |
| VOY-06 | P1: LangChain rerank client | Execute | ✅ Verified (code) | T1, T3, T6, T7, T8 |
| VOY-07 | P1: LangChain rerank client | Execute | ✅ Verified (code) | T6 |
| VOY-08 | P1: Voyage embeddings | Execute | ✅ Verified (docs) | T8 |

| ID | Requirement (short) |
| -- | ------------------- |
| VOY-01 | Production embed/query via `VoyageAIEmbeddings`, model `voyage-4-large`, width 1024, `input_type` document vs query; `EmbeddingPort` unchanged. |
| VOY-02 | Lifespan/retrieve wiring uses the Voyage embedding adapter; no `OpenAIEmbeddings` on ingest/retrieve. |
| VOY-03 | `Policy.embedding_dimensions=1024`; `chunks.embedding` DDL uses it; other chunk columns unchanged. |
| VOY-04 | `ensure_schema` CREATE-only (no corpus DROP/DELETE, including no `kind` wipe). Operator `scripts/wipe_paper_chunks.py --yes` drops chunks and deletes papers; no `--yes` is a no-op; leftover 1536 fails INSERT, not silent mix. |
| VOY-05 | `score_chunks` uses `VoyageAIRerank` (`rerank-3`); full unique list scored; scores mapped to input order; no `ContextualCompressionRetriever`. |
| VOY-06 | No `import voyageai` in app source; `langchain-voyageai` is the runtime Voyage integration; `VOYAGE_API_KEY` shared. |
| VOY-07 | `cut_reranked` / pack / expand / RRF fallback / English task query / `document_text` unchanged. |
| VOY-08 | Docs: PROJECT.md embeddings vendor + parent EMB-01 / STORE-01 width superseded as in this spec. |

**ID format:** `VOY-NN`  
**Status values:** Pending → In Design → In Tasks → Implementing → Verified  

**Coverage:** 8 total, 8 mapped to tasks (see `tasks.md`). 0 unmapped.

---

## Success Criteria

- [ ] New ingest writes 1024-d Voyage vectors; hybrid `embed_query` uses the same model. (live Independent Test / UAT)
- [x] API boot never drops `chunks` / `papers`. Reset is `python scripts/wipe_paper_chunks.py --yes` then restart.
- [x] `score_chunks` is LangChain `VoyageAIRerank` + existing cut; retrieve grep has no `voyageai.Client` and no `ContextualCompressionRetriever`.
- [x] OpenAI remains the only LLM vendor; `text-embedding-3-small` is gone from production retrieve.
