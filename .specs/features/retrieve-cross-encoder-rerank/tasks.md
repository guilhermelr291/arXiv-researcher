# Retrieve Cross-Encoder Rerank Tasks (Voyage)

**Design**: `.specs/features/retrieve-cross-encoder-rerank/design.md` (approved 2026-09-04)  
**Spec**: `.specs/features/retrieve-cross-encoder-rerank/spec.md` (approved 2026-09-04)  
**Status**: Voyage T1–T7 executed 2026-09-04 (uncommitted). Qwen T1–T7 (2026-09-03) is **superseded** and SHALL NOT ship as the live path. Live UAT not in this list.

`.specs/codebase/TESTING.md` does not exist. Same as v1 / orchestrator / admission / structured-aware: graph e2e (pytest, Testcontainers) is **out of scope**. Exception required by this spec’s Independent Test: **stdlib `unittest`** for `cut_reranked`, `scores_from_rerank_results`, query/document helpers, and subprocess no-torch import — co-located in T4. Live Independent Tests (`2609.01617` v1 methodology; `1706.03762` v7 E1 expansion) stay **UAT** after Execute (may be blocked by B-001). Do **not** call the live Voyage API in unit tests.

No new graph nodes, no new SSE names, no Citation/`EvidenceChunk` score field, no `CrossEncoderReranker` / `ContextualCompressionRetriever`, no Qwen/torch scorer, no silent `rerank-3-lite` / `rerank-2.5`. Hybrid weights stay 0.7/0.3. `pack_hits` / `expand_hits` signatures stay as they are.

Retrieve already walks first-stage `k=40` → unique concat → `to_thread(score_chunks)` → per-paper `cut_reranked` → pack/expand. These tasks **replace the scorer and knobs**, they do not re-introduce that walk.

---

## Execution Plan

### Phase 1: Foundation (all `[P]`)

```
T1 [P]  T2 [P]  T3 [P]  T5 [P]
```

### Phase 2: Voyage scorer (sequential; same file as tests)

```
T1 ──→ T4  rerank.py + unittest
```

### Phase 3: DI + retrieve call site (sequential)

```
T2, T3, T4 ──→ T6  factory + main + retrieve.py
```

T5 does **not** block T6 (abilities text is planner-facing only).

### Phase 4: Project docs (sequential)

```
T6 ──→ T7  PROJECT.md stack line
```

**Commit constraint:** T4 changes `score_chunks` to require `api_key=`. Do not leave HEAD on T4 without T6 if committing — retrieve would TypeError. Execute T4 then T6 in the same session (or squash).

---

## Task Breakdown

### T1: Swap runtime deps to `voyageai` [P]

**What**: Add `voyageai`; remove `torch`, `sentence-transformers`, and `transformers` from runtime dependencies.
**Where**: `pyproject.toml` (and lockfile)
**Depends on**: None
**Reuses**: existing `uv` lock workflow
**Requirement**: DEP-01

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `voyageai` is listed under `[project].dependencies`
- [x] `torch`, `sentence-transformers`, and `transformers` are **not** listed under `[project].dependencies`
- [x] Lockfile updated (`uv lock` / `uv sync`)
- [x] OpenAI packages remain the LLM/embedding vendor; no OpenAI rerank client added

**Tests**: none
**Gate**: none

**Verify**: `uv sync` succeeds; `python -c "import voyageai; print(voyageai.__version__)"`; `pyproject.toml` has no `torch` / `sentence-transformers` / `transformers` lines

**Commit**: `chore(rerank): replace torch CrossEncoder stack with voyageai`

---

### T2: Voyage-scale Policy cut defaults [P]

**What**: Set adaptive-cut defaults to Voyage `relevance_score` scale; keep first-stage `k` and leftover parent fields.
**Where**: `src/plan_based_researcher/policy.py`
**Depends on**: None
**Reuses**: existing `Policy` class; do **not** delete `retrieve_k_per_paper` or `retrieve_overfetch_factor`
**Requirement**: POL-11, RETR-10, RERANK-04, RERANK-06

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `Policy.retrieve_first_stage_k == 40`
- [x] `Policy.retrieve_rerank_top_n == 12`
- [x] `Policy.retrieve_rerank_margin == 0.20`
- [x] `Policy.retrieve_rerank_floor == 0.30`
- [x] `retrieve_k_per_paper` and `retrieve_overfetch_factor` still exist
- [x] Hybrid weights, `max_papers`, splitter knobs unchanged

**Tests**: none
**Gate**: none

**Verify**: `python -c "from plan_based_researcher.policy import Policy; assert Policy.retrieve_first_stage_k==40; assert Policy.retrieve_rerank_top_n==12; assert Policy.retrieve_rerank_margin==0.20; assert Policy.retrieve_rerank_floor==0.30; assert Policy.retrieve_k_per_paper==5; assert Policy.retrieve_overfetch_factor==3"`

**Commit**: `feat(rerank): set Voyage margin 0.20 and floor 0.30 on Policy`

---

### T3: Require `VOYAGE_API_KEY` on Settings [P]

**What**: Add required non-empty `voyage_api_key` so API boot fails without the env var.
**Where**: `src/plan_based_researcher/config.py`
**Depends on**: None
**Reuses**: existing `Settings` (`BaseSettings`, `env_file=".env"`); env name `VOYAGE_API_KEY` via pydantic-settings default alias
**Requirement**: DEP-01

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `Settings.voyage_api_key: str` with `Field(min_length=1)` (or equivalent non-empty constraint)
- [x] Missing or blank `VOYAGE_API_KEY` makes `Settings()` raise (process must not start)
- [x] `openai_api_key`, `database_url`, host/port/timeout fields unchanged
- [x] No Voyage HTTP client constructed in `config.py`

**Tests**: none
**Gate**: none

**Verify**: `python -c "import os; os.environ.pop('VOYAGE_API_KEY', None); from plan_based_researcher.config import Settings; raised=False
try:
    Settings(_env_file=None)
except Exception:
    raised=True
assert raised, 'Settings must fail without VOYAGE_API_KEY'"`
(Adapt if `Settings()` always loads `.env`; the check is: constructing Settings with voyage key absent/blank fails.)

**Commit**: `feat(rerank): require VOYAGE_API_KEY at Settings boot`

---

### T4: Voyage `ingest/rerank.py` and unit tests

**What**: Replace Qwen/HF scoring with `voyageai.Client.rerank`, index→input mapping, and Voyage-scale `cut_reranked`; update stdlib tests. No retrieve/factory edits in this task.
**Where**: `src/plan_based_researcher/ingest/rerank.py`; `tests/test_cut_reranked.py`
**Depends on**: T1
**Reuses**: keep `build_rerank_query` and `document_text` behavior; `ports.chunks.ChunkRecord`
**Requirement**: RERANK-01, RERANK-02, RERANK-04, RERANK-06, DEP-01

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `RERANK_MODEL_ID == "rerank-3"` and `RERANK_TIMEOUT_SECONDS == 30.0`
- [x] Removed: Qwen instruction, `_PREFIX` / `_SUFFIX`, `format_queries`, `format_document`, `get_cross_encoder`, `RERANK_MAX_LENGTH`, `RERANK_BODY_TOKENS`, any `torch` / `HuggingFaceCrossEncoder` import
- [x] `build_rerank_query(task, feedback)`: stripped task; non-empty feedback → `f"{task}\n\n{feedback}"`; SHALL NOT read `retrieve_query_used`
- [x] `document_text(chunk)`: stripped `metadata.section` + newline + `content`, or `content` only; no local tokenizer truncate
- [x] `cut_reranked(ranked, *, top_n=12, margin=0.20, floor=0.30 | None)` with that signature and type hints (`floor: float | None = 0.30`)
- [x] Docstring states scores are **Voyage relevance scores (~0–1), not logits**, and the cut is **relative to the best score of this query’s candidate list**, except the optional absolute `floor` on that list’s best
- [x] Empty `ranked` → `[]`; `floor is not None` and best `< floor` → `[]`; walk `break` on margin or `top_n`; `margin == 0` keeps ties with best
- [x] `scores_from_rerank_results(n_docs, results) -> list[float]` maps `result.index` + `result.relevance_score` to input order; raises `ValueError` on missing, duplicate, or out-of-range index
- [x] `score_chunks(chunks, query, *, api_key: str) -> list[float]`: empty chunks → `[]` (no HTTP); else `voyageai.Client(api_key=api_key, timeout=RERANK_TIMEOUT_SECONDS, max_retries=0).rerank(query, [document_text(c) for c in chunks], model=RERANK_MODEL_ID, truncation=True)` with **no** `top_k`; return `scores_from_rerank_results`; no sigmoid / min-max
- [x] No `CrossEncoderReranker` / `ContextualCompressionRetriever`; no `rerank-3-lite` / `rerank-2.5`
- [x] `tests/test_cut_reranked.py`: (a) margin `0.20` prefix / `top_n=12` when best ≥ `0.30`; (b) `floor=0.30` and best `= 0.25` → `[]`; (c) post-gap item not kept; empty input; `margin=0` keeps only ties; default `floor` (omit kwarg) drops weak best; `build_rerank_query` / `document_text`; `scores_from_rerank_results` happy path + missing + duplicate index; **subprocess** import of `plan_based_researcher.ingest.rerank` does not import `torch`
- [x] Qwen `format_queries` / `format_document` / Instruct tests **deleted**
- [x] Tiny `ChunkRecord` fixtures only — no DB, no Voyage HTTP, no GPU

**Tests**: unit (`unittest`)
**Gate**: `python -m unittest tests.test_cut_reranked -v`

**Done when (gate)**:

- [x] Gate check passes: `python -m unittest tests.test_cut_reranked -v`
- [x] Test count: **14** tests pass (7 cut + 2 query + 1 document + 3 score-map + 1 no-torch subprocess; no silent deletions)

**Verify**: Gate command above; `python -c "import sys; from plan_based_researcher.ingest.rerank import RERANK_MODEL_ID, cut_reranked, score_chunks; assert RERANK_MODEL_ID=='rerank-3'; assert 'torch' not in sys.modules"`

**Commit**: `feat(rerank): score with Voyage rerank-3 and cut on relevance_score`

---

### T5: Retrieve registry abilities [P]

**What**: Describe hybrid overfetch, task rerank, and adaptive packed `[n]` cut — not k=5, not CrossEncoder, not model ids.
**Where**: `src/plan_based_researcher/agents/registry.py`
**Depends on**: None
**Reuses**: existing retrieve `AgentSpec`; `planner_prompt_abilities()` already concatenates this string
**Requirement**: RERANK-03

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] Retrieve abilities mention hybrid first-stage overfetch, rerank against the evidence **task**, adaptive packed `[n]` cut, then expand
- [x] Abilities still say the task is the goal and the agent formulates the hybrid query; still say do not search arXiv
- [x] Abilities do **not** say `k=5` from ensemble order
- [x] Abilities do **not** mention CrossEncoder, Voyage, model ids, logits, or `margin`
- [x] `EvidenceChunk` TypedDict / `Citation` schema **not** edited in this task (or any task)

**Tests**: none
**Gate**: none

**Verify**: `python -c "from plan_based_researcher.agents.registry import REGISTRY; a=REGISTRY['retrieve'].abilities; assert 'k=5' not in a; assert 'CrossEncoder' not in a; assert 'Voyage' not in a; assert 'rerank' in a.lower(); assert 'task' in a.lower()"`; grep `graph/state.py` and `api/schemas.py` find no `score` field on `EvidenceChunk` / `Citation`

**Commit**: `feat(rerank): drop CrossEncoder from retrieve abilities`

---

### T6: Inject Voyage key and call `score_chunks(..., api_key=)`

**What**: Pass `voyage_api_key` from Settings through factory into `RetrieveRunner`; call `score_chunks` with that key off the event loop; log Voyage failures as RRF fallback.
**Where**: `src/plan_based_researcher/main.py`; `src/plan_based_researcher/agents/factory.py`; `src/plan_based_researcher/agents/retrieve.py`
**Depends on**: T2, T3, T4
**Reuses**: existing retrieve walk (first-stage 40, unique concat, per-paper cut/pack/expand, `except Exception` fallback); T4 `score_chunks` / `build_rerank_query` / `cut_reranked`
**Requirement**: RETR-10, RERANK-01, RERANK-02, RERANK-04, RERANK-05, RERANK-06, POL-11, DEP-01

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] Lifespan `Settings()` still the boot gate; `AgentFactory(..., voyage_api_key=settings.voyage_api_key)`; **no** Voyage client constructed in lifespan
- [x] `RetrieveRunner(..., voyage_api_key: str)` stores the key; OpenAI `api_key` for formulate unchanged
- [x] After `merged` non-empty: formulate still produces `retrieve_query_used` (hybrid only); `rerank_query = build_rerank_query(task, feedback)` for Voyage only
- [x] Per paper: `hybrid.retrieve(query, [key], k=Policy.retrieve_first_stage_k)` — **not** `retrieve_overfetch_factor * retrieve_k_per_paper`
- [x] One `await asyncio.to_thread(score_chunks, unique, rerank_query, api_key=self._voyage_api_key)` per execute (keyword `api_key`)
- [x] On success: restore by `chunk_id`; per paper stable-sort by score descending; `cut_reranked(..., top_n=Policy.retrieve_rerank_top_n, margin=Policy.retrieve_rerank_margin, floor=Policy.retrieve_rerank_floor)` — **no** hardcoded 12 / 0.20 / 0.30 in the walk
- [x] `pack_hits(cut, k=len(cut))` then `expand_hits`; omit empty packs; continuous `[n]`
- [x] `except Exception`: `logger.exception("voyage rerank failed; packing ensemble order")`; **do not** call `cut_reranked`; `pack_hits(ensemble, k=Policy.retrieve_rerank_top_n)` then expand; do **not** import Qwen/torch or call another Voyage model
- [x] Return keys unchanged (`evidence_chunks` dicts still have `excerpt`, no `score`)
- [x] No new LangGraph node; execute / dispatch / evaluate routing untouched
- [x] No `CrossEncoderReranker` / `ContextualCompressionRetriever`

**Tests**: none
**Gate**: none

**Verify**: grep `retrieve.py` for `voyage_api_key`, `to_thread`, `score_chunks`, `cut_reranked`, `retrieve_first_stage_k`; grep finds no `retrieve_overfetch_factor` in `retrieve.py`; grep `graph/build.py` finds no `rerank` node; grep `main.py` for `voyage_api_key`; `python -c "from plan_based_researcher.graph.state import EvidenceChunk; assert 'score' not in EvidenceChunk.__annotations__"`

**Commit**: `feat(rerank): inject Voyage key and score retrieve off the event loop`

---

### T7: Update PROJECT stack (Voyage, not Qwen)

**What**: Document Voyage `rerank-3` as the retrieve scorer; drop local seq-cls / torch from PROJECT stack wording.
**Where**: `.specs/project/PROJECT.md` (Constraints rerank sentence if it still says Qwen Execute 2026-09-03 as the live scorer)
**Depends on**: T6
**Reuses**: existing PROJECT Constraints retrieve line (first-stage 40, `top_n=12`)
**Requirement**: DEP-01, POL-11 (docs)

**Tools**: MCP NONE · Skill NONE

**Done when**:

- [x] `PROJECT.md` Key dependencies name Voyage `rerank-3` (or Voyage rerank API) instead of `sentence-transformers` / Qwen3 0.6B seq-cls; OpenAI remains LLM + embeddings
- [x] Constraints still name first-stage `k=40` and adaptive cut `top_n=12` (and loop caps); mention `margin=0.20` / `floor=0.30` only if the Constraints paragraph already discusses cut knobs
- [x] Feature pointer still `.specs/features/retrieve-cross-encoder-rerank/`; do **not** claim UAT-complete
- [x] Do **not** rewrite admission T1/T2a/T3 routing text

**Tests**: none
**Gate**: none

**Verify**: grep `PROJECT.md` for `voyage` / `rerank-3`; grep `PROJECT.md` finds no `Qwen3-Reranker` / `sentence-transformers` as the live reranker

**Commit**: `docs(rerank): document Voyage rerank-3 instead of local Qwen`

---

## Parallel Execution Map

```
Phase 1 (Parallel):
  ├── T1 [P]  pyproject deps
  ├── T2 [P]  Policy knobs
  ├── T3 [P]  Settings VOYAGE_API_KEY
  └── T5 [P]  registry abilities

Phase 2 (Sequential):
  T1 complete → T4  ingest/rerank.py + unittest

Phase 3 (Sequential):
  T2, T3, T4 complete → T6  factory + main + retrieve.py

Phase 4 (Sequential):
  T6 complete → T7  PROJECT.md
```

**Parallelism constraint:** T1, T2, T3, T5 share no files. T4 edits `ingest/rerank.py` and `tests/test_cut_reranked.py` only. T6 is the only editor of `factory.py` / `main.py` / `retrieve.py` in this list. T5 is `[P]` and does not depend on T6 (and T6 does not depend on T5).

---

## Requirement Traceability

| ID | Tasks |
| -- | ----- |
| RETR-10 | T2, T6 |
| RERANK-01 | T1, T4, T6 |
| RERANK-02 | T4, T6 |
| RERANK-03 | T5 |
| RERANK-04 | T2, T4, T6 |
| RERANK-05 | T6 |
| RERANK-06 | T2, T4, T6 |
| POL-11 | T2, T6, T7 |
| DEP-01 | T1, T3, T4, T6, T7 |

**Coverage:** 9/9 spec IDs have ≥1 task. 0 unmapped tasks without a requirement.

---

## Task Granularity Check

| Task | Scope | Status |
| ---- | ----- | ------ |
| T1 | 1 file (`pyproject.toml` + lock) | ✅ Granular |
| T2 | 1 class (`policy.py` two defaults) | ✅ Granular |
| T3 | 1 Settings field | ✅ Granular |
| T4 | 1 module + its unittest (Voyage scorer + cut; cohesive) | ⚠️ Cohesive |
| T5 | 1 registry abilities string | ✅ Granular |
| T6 | DI + retrieve call site (3 files, one key) | ⚠️ Cohesive |
| T7 | 1 docs file (PROJECT stack) | ✅ Granular |

T4 is one module on purpose: `score_chunks`, index mapping, and `cut_reranked` are the Independent Test surface. T6 is one wiring slice on purpose: Settings → factory → runner → `to_thread` cannot land as three green commits after T4’s required `api_key=` (see commit constraint). Parent banners for packed k=5 already exist from Qwen T7; this rewrite does not redo them.

---

## Diagram-Definition Cross-Check

| Task | Depends On (body) | Diagram shows | Status |
| ---- | ----------------- | ------------- | ------ |
| T1 | None | Phase 1, no inbound | ✅ Match |
| T2 | None | Phase 1, no inbound | ✅ Match |
| T3 | None | Phase 1, no inbound | ✅ Match |
| T4 | T1 | T1→T4 | ✅ Match |
| T5 | None | Phase 1, no inbound | ✅ Match |
| T6 | T2, T3, T4 | T2→T6, T3→T6, T4→T6 | ✅ Match |
| T7 | T6 | T6→T7 | ✅ Match |

Phase-1 `[P]` tasks T1, T2, T3, T5 have no inter-deps. T4 / T6 / T7 are sequential. T5 is `[P]` and does not depend on T6.

---

## Test Co-location Validation

`.specs/codebase/TESTING.md` does not exist. Project default: automated graph tests deferred (STATE). This feature’s spec Independent Test **requires** `cut_reranked` (and mapping / no-torch) unit tests — co-located in T4 (the task that creates those functions). Voyage HTTP / retrieve wiring are not unit-tested here (live API + Postgres UAT).

| Task | Code layer | Matrix requires | Task says | Status |
| ---- | ---------- | --------------- | --------- | ------ |
| T1 | dependencies | none (no matrix; deferred) | none | ✅ OK |
| T2 | policy | none | none | ✅ OK |
| T3 | Settings field | none | none | ✅ OK |
| T4 | ingest pure functions + score mapping | spec Independent Test = unit | unit (`unittest`) | ✅ OK |
| T5 | registry string | none | none | ✅ OK |
| T6 | retrieve runner / factory | none (graph e2e deferred; UAT after Execute) | none | ✅ OK |
| T7 | markdown docs | none | none | ✅ OK |

No task uses “tested in another task” to skip T4’s required unit tests.

---

## Confirm before Execute

Voyage T1–T7 executed 2026-09-04 (uncommitted). Live UAT (`2609.01617` v1, `1706.03762` v7) is **not** in this list.

Operator must set `VOYAGE_API_KEY` in local `.env` before API boot (do not commit the secret).
