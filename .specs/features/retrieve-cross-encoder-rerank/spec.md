# Retrieve Cross-Encoder Rerank Specification

**Feature:** `retrieve-cross-encoder-rerank`  
**Spec status:** Approved 2026-09-04 (Voyage API). Prior Execute T1–T7 (Qwen local, 2026-09-03) is **superseded** by this amendment and SHALL NOT ship as the live rerank path.  
**Date:** 2026-09-03; Voyage amendment 2026-09-04  
**Gray areas:** Locked in specify 2026-09-03 (overfetch + adaptive cut + task query); Voyage vendor / score scale / floor locked in discuss 2026-09-04 (`.specs/features/retrieve-cross-encoder-rerank/context.md`)  
**Context:** `.specs/features/retrieve-cross-encoder-rerank/context.md` (approved 2026-09-04)  
**Parent chunking:** `.specs/features/structured-aware-chunking/spec.md` (executed)  
**Parent admission:** `.specs/features/admission-retrieve-per-topic/spec.md` (approved)  
**Parent loop:** `.specs/features/orchestrator-eval-replan/spec.md` (approved)  
**Parent product:** `.specs/features/arxiv-grounded-research/spec.md` (approved v1)  
**Architecture constraints:** `.specs/features/arxiv-grounded-research/context.md` (PAT-01–PAT-12 still apply)

This spec defines **only** how retrieve **ranks and cuts** hybrid candidates before `pack_hits` / `expand_hits`. HTML ingest, placeholder expansion, hybrid **weights** 0.7/0.3, `FormulatedQuery` for the **first-stage** lexical/vector query, admission 1/topic, U1, T1/T2a/T3 routing, Gate, search, SSE event **names**, Chainlit, checkpointer, Writer `[n]` **format**, and `Citation` **fields** stay as in the parent specs unless an ID below explicitly supersedes them.

**Client amendment (Execute 2026-09-08):** `.specs/features/voyage-4-large-embeddings/` supersedes app `voyageai.Client` as the required HTTP client. `score_chunks` uses `langchain_voyageai.VoyageAIRerank` (`compress_documents`). Unchanged: `rerank-3`, truncation, no Writer `top_k`, index/`relevance_score` mapping, `cut_reranked`, pack/expand, RRF fallback, boot fail without `VOYAGE_API_KEY`. UAT of retrieve Independent Tests is **not** complete.

## Problem Statement

Packed retrieve used to keep the first `retrieve_k_per_paper=5` unique `unit_id`s of EnsembleRetriever RRF order. On methodology questions the first-stage query is a keyword dump, so isolated equations and results tables occupy `[1]`–`[5]` while section prose sits in overfetch ranks ~7–27. Overfetch already retrieved the useful passages — the leak is **RRF order plus a tight count cut**.

A local Qwen3 0.6B seq-cls CrossEncoder was wired to reorder those candidates (Execute T1–T7). First retrieve in a process downloads ~2.4 GB of weights and scores on CPU; uvicorn `--reload` also walks the torch tree. That path is too slow for this product’s ~2 min research timeout. This amendment keeps overfetch + task-conditioned rerank + adaptive cut, and **replaces the scorer** with Voyage AI’s rerank API.

## Goals

- [x] First-stage hybrid overfetches enough candidates per paper that methodology subsections can enter the pool (not only the previous 15-per-leg cap).
- [x] One Voyage `rerank-3` pass reorders those candidates against the retrieve **task** (not the formulated keyword query), using Voyage `relevance_score` values.
- [x] Writer `[n]` is cut with an **adaptive** filter relative to that query’s best score (`margin=0.20`) plus a `top_n=12` ceiling and a `floor=0.30` on that paper’s best, then `pack_hits` / `expand_hits`.
- [x] No local torch / HuggingFace CrossEncoder on the retrieve path; missing `VOYAGE_API_KEY` fails API startup.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Local `tomaarsen/Qwen3-Reranker-0.6B-seq-cls` / any torch CrossEncoder | Too slow (Hub download + CPU); discuss 2026-09-04 drops this path |
| Generative `Qwen/Qwen3-Reranker-0.6B` yes/no logits | Integration cost; not the Voyage path |
| `Qwen3-Reranker-4B` / `8B` | Local models deferred; this amendment removes 0.6B rather than promoting 4B |
| `rerank-3-lite` / `rerank-2.5` as silent fallback | Model id locked to Preview `rerank-3`; runtime errors use RRF pack, not another Voyage model |
| `ContextualCompressionRetriever` wrapping `EnsembleRetriever` | Custom per-paper hybrid, `pack_hits`, `expand_hits`; compressor `top_k` would skip those |
| Voyage `top_k` as the Writer cut | `top_k` would skip `cut_reranked` / `unit_id` pack; score the full unique list then cut |
| New LangGraph node (`rerank`) | PAT-01; scoring + cut live in `RetrieveRunner` + `ingest/rerank.py` |
| MMR | Still out; diversity is section-aware only via pack `unit_id` dedup |
| Treating Voyage scores as logits / keeping `margin=4.0` | Voyage `relevance_score` is ~0–1; logit margin never fires |
| Union `LIMIT k` across papers | Parent: per-paper cut, concat in admission order |
| Score on `EvidenceChunk` / `Citation` | Student contract unchanged; scores are retrieve-internal |
| Changing Gate, search, admission U1, T1/T2a/T3 **routing**, hybrid **weights**, Writer `[n]` **shape**, SSE names | Parent |
| Formulating a third LLM query just for rerank | Task text already exists |
| Prepending the old Qwen Instruct string to the Voyage query | Discuss: task (+ retry feedback) only |
| Full-paper / full-PDF rerank | Cost; not this product |
| OpenAI rerank API | Voyage is the sole extra rerank vendor |

### Supersedes (parent specs)

Upon approval, these IDs / rows are **replaced** by this feature (do not implement both). Unnamed parent IDs stay in force.

| Parent ID | What no longer holds |
| --------- | -------------------- |
| RETR-05 (packed `k=5`) | Writer budget is **at most 5** unique hits per paper from **ensemble order**. **Unchanged:** one hybrid call per usable paper; concat in admission order; continuous `[n]`; no union `LIMIT k`. |
| RETR-08 (overfetch then pack-to-5) | Ensemble overfetch `3 × 5`, then `pack_hits` on **RRF order** to 5 unique. **Unchanged:** mixed index; vector on `embedding_text`; BM25 on `content`; `unit_id` dedup + backfill; expansion after pack (RETR-07 / RETR-09). |
| Admission out-of-scope “global rerank” | Task-conditioned rerank is **in** this feature (Voyage order + adaptive cut). **Unchanged:** no MMR; no global union `k`; `Citation` still has no score. |

### Supersedes (this feature’s Qwen Execute)

| Prior lock (2026-09-03) | What no longer holds |
| ----------------------- | -------------------- |
| RERANK-01 HuggingFace seq-cls | `HuggingFaceCrossEncoder` on `tomaarsen/Qwen3-Reranker-0.6B-seq-cls`; Instruct/Query/Document template; raw logits; Identity activation |
| POL-11 cut defaults | `margin=4.0`, `floor=None` (logit scale) |
| DEP-01 torch stack | `sentence-transformers`, `transformers>=4.51.0`, `torch`; lazy HF singleton; CUDA else CPU |
| Qwen instruction string | Locked English Instruct paragraph prepended via the chat template |

**Amended (not replaced):** RETR-07 / RETR-09 (expand after the **kept** hits); T1/T2a/T3; WRITE-02; SEARCH formulate; GROUND-01–03; RETR-10 first-stage `k=40`; one score pass; per-paper cut; RRF fallback on **runtime** score failure. `Policy.retrieve_overfetch_factor` stays unused.

**Locked knobs (specify + discuss, not reopened in Design):**

- Model id: Voyage **`rerank-3`** (Preview). SHALL NOT call `rerank-3-lite` or `rerank-2.5` as a silent substitute.
- Scoring SHALL be Voyage rerank (`voyageai.Client.rerank` or equivalent HTTP). **Client class superseded** (embeddings amendment): `langchain_voyageai.VoyageAIRerank` (`compress_documents`); scoring/cut locks stay. Each document SHALL be scored against the retrieve **task**. Return values SHALL be Voyage **`relevance_score`** (~0–1). SHALL NOT apply sigmoid / min-max. SHALL NOT interpret them as Qwen logits.
- SHALL NOT use Voyage `top_k` (or `CrossEncoderReranker` / `ContextualCompressionRetriever`) as the Writer cut. Score the **full** `chunk_id`-unique first-stage list (or `top_k=len(documents)` so every candidate returns), map scores back to input order, then `cut_reranked`.
- Rerank **query** = current retrieve `step.task`. On retry, concatenate that task with this step’s evaluator feedback (`eval_by_step`). SHALL NOT use `retrieve_query_used` / `FormulatedQuery`. SHALL NOT prepend the old Qwen Instruct paragraph.
- Rerank **document** = `metadata.section` + newline + chunk `content` (placeholders still in prose; expansion stays after pack). Empty section → `content` only.
- **One** Voyage call per retrieve execute over the concatenated per-paper overfetch (dedupe `chunk_id` first). Then restore per-paper lists; sort and cut **per paper** (the “best” score is that paper’s best for this query, not a global max across papers).
- First-stage `k` per hybrid leg: **40**.
- Call site (not a LangGraph node): `RetrieveRunner.run` obtains scores, then `cut_reranked` in `ingest/rerank.py`, then `pack_hits(k=len(cut))`, then `expand_hits`.
- Adaptive cut defaults: `top_n=12`, `margin=0.20`, `floor=0.30`. Policy SHALL store those values and pass them in; the walk SHALL NOT hardcode them. `margin` / `floor` are **un-calibrated** on this corpus until UAT; UAT MAY retune **only** those two numbers without reopening model id or query source.
- Sync Voyage I/O SHALL run off the event loop (`asyncio.to_thread` or equivalent async client). SHALL NOT import `torch` on the retrieve / FastAPI path.
- WHEN Voyage **runtime** score fails (timeout, 5xx, network) THEN retrieve SHALL skip `cut_reranked` and `pack_hits` from **ensemble order** with `k=top_n` and SHALL NOT crash the graph. Log the failure. SHALL NOT fall back to Qwen or to another Voyage model.
- WHEN `VOYAGE_API_KEY` is missing at process start THEN the API SHALL **refuse to start** (boot error). That is not the runtime fallback path.
- OpenAI remains the LLM vendor. Embeddings vendor is Voyage per the embeddings amendment (`voyage-4-large`, 1024-d); Voyage remains the sole extra rerank vendor. Runtime deps SHALL include a Voyage client; SHALL NOT require `torch` / `sentence-transformers` / `transformers` for retrieve.

---

## User Stories

### P1: Larger first-stage hybrid ⭐ MVP

**User Story**: As a student asking for a full method, I want retrieve to consider more than the old top-15 ensemble hits per paper so that methodology subsections can appear in the candidate pool at all.

**Why P1**: Rerank cannot promote a chunk that never entered overfetch (knowledge-graph construction / experimental protocol on the failing trace). Recall is the first leak to close.

**Acceptance Criteria**:

1. WHEN hybrid runs per usable paper THEN each leg (vector similarity and BM25) SHALL request `Policy.retrieve_first_stage_k` (**40**) hits for that paper. EnsembleRetriever SHALL still RRF-merge the union (weights 0.7/0.3 unchanged).
2. WHEN `Policy` is read THEN `retrieve_overfetch_factor * retrieve_k_per_paper` SHALL NOT be the first-stage `k`. The named first-stage cap SHALL be `retrieve_first_stage_k`.
3. WHEN a paper has fewer than 40 chunks THEN the legs SHALL return that many (parent tiny-document rule).
4. WHEN first-stage returns THEN retrieve SHALL **not** yet slice to 5 or `top_n`; the full unique union for that paper is the rerank input (after `chunk_id` dedup).

**Independent Test**: On cached `2609.01617` v1 (or a fixture of its chunks), a methodology `FormulatedQuery` first-stage SHALL include at least one hit whose `metadata.section` contains `V-C Reciprocal Rank Fusion` **or** `V Methodology` prose, not only VIII result tables. Count of unique ensemble `chunk_id`s SHALL be `>15` when the paper has more than 15 chunks.

---

### P1: Task-conditioned Voyage rerank ⭐ MVP

**User Story**: As a student, I want the passages sent to the Writer ordered by whether they actually evidence the retrieve **task**, without waiting minutes for a local 0.6B model to download and run on CPU.

**Why P1**: Trace `01a06938-a33c-7bd0-aaaa-de2129d4d34e` showed relevant prose already in ranks 7–27. Ordering is the main quality lever; local Qwen made retrieve unusable on this machine.

**Acceptance Criteria**:

1. WHEN first-stage candidates exist THEN `RetrieveRunner.run` SHALL score them with Voyage **`rerank-3`** **once** per execute (concatenated unique list, then split back by paper). SHALL NOT call Voyage once per paper if that would duplicate the unique set; one call on the concatenated documents is required.
2. WHEN the Voyage request is built THEN **query** SHALL be the retrieve `task` (plus this step’s eval feedback on retry). **Document** SHALL be section + `content`. SHALL NOT send `FormulatedQuery`. SHALL NOT send the Qwen Instruct/Query/Document chat template.
3. WHEN Voyage returns `relevance_score` values THEN retrieve SHALL treat each value as a **raw Voyage score** (~0–1). It SHALL NOT pass scores through sigmoid, min-max, or a logit conversion before sort or cut.
4. WHEN scoring runs THEN it SHALL run off the event loop. The graph SHALL NOT gain a `rerank` node. Execute/dispatch/evaluate routing SHALL stay as today. SHALL NOT import `torch` to score.
5. WHEN the retrieve registry abilities are read THEN they SHALL describe hybrid overfetch, rerank against the evidence **task**, and an adaptive packed `[n]` cut — not “k=5 from ensemble order”, and SHALL NOT name model ids, logits, or `margin`.
6. WHEN `Citation` / `EvidenceChunk` / `answer_complete` are built THEN they SHALL NOT include a relevance score field.

**Independent Test**: Replay methodology retrieve on cached `2609.01617` v1 with the retrieve **task** as Voyage query. After sort by `relevance_score`, `V-C` / `IV High-Level Architecture` prose SHALL outrank isolated `kind=equation` hits `S5.Ex4` / `S5.Ex5`. Regression: formulated attention query on `1706.03762` v7 SHALL still allow packed expansion of E1 (RETR-07) after rerank. Importing `plan_based_researcher.ingest.rerank` SHALL NOT import `torch`.

---

### P1: Adaptive score cut after rerank ⭐ MVP

**User Story**: As a student, I want retrieve to keep the cluster of passages close (in Voyage score) to the best hit for **this** question, capped so the Writer is not flooded — and to get no junk context when even the best hit is worthless.

**Why P1**: A fixed `top_n` alone either pads with leftover overfetch or drops useful hits. Voyage scores are not logits; `margin=4.0` would keep everything until 12.

**Acceptance Criteria**:

1. WHEN per-paper `(chunk, score)` pairs exist THEN `RetrieveRunner.run` SHALL sort them by score descending (ties: first-stage ensemble order) and call `cut_reranked` in `src/plan_based_researcher/ingest/rerank.py`. Signature SHALL include type hints:

   ```python
   def cut_reranked(
       ranked: list[tuple[ChunkRecord, float]],
       *,
       top_n: int = 12,
       margin: float = 0.20,
       floor: float | None = 0.30,
   ) -> list[ChunkRecord]:
   ```

   `ranked` is already sorted descending by the float (Voyage `relevance_score`). The function SHALL take `top_n`, `margin`, and `floor` as parameters (defaults as above). Callers SHALL pass Policy values; SHALL NOT hardcode those numbers in the walk.

2. WHEN `cut_reranked` is documented THEN its docstring SHALL state that scores are **Voyage relevance scores (~0–1), not logits**, and that the cut is **relative to the best score of this query’s candidate list**, except the optional absolute `floor` on that list’s best.

3. WHEN `floor` is not `None` AND the best score (`ranked[0][1]`) is `< floor` THEN `cut_reranked` SHALL return `[]`. Default Policy `floor` SHALL be **0.30** (not `None`). WHEN a caller passes `floor=None` THEN this absolute check SHALL NOT run.

4. WHEN the best score passes `floor` (or `floor` is `None`) THEN the function SHALL walk `ranked` in order, append chunks, and **`break`** as soon as `(best - current) > margin`. It SHALL also stop when `len(kept) == top_n`. It SHALL NOT scan the tail after the margin break.

5. WHEN `cut_reranked` returns THEN retrieve SHALL run `pack_hits` with `k=len(cut)`, THEN `expand_hits` as RETR-07 / RETR-09. Continuous `[n]` across papers in admission order SHALL be unchanged.

6. WHEN `cut_reranked` returns `[]` for every usable paper THEN `evidence_chunks` SHALL be `[]` (existing T3 empty / retry path). WHEN only some papers are empty THEN concat the non-empty packs.

7. WHEN fallback (Voyage **runtime** score failure) runs THEN retrieve SHALL NOT call `cut_reranked`; it SHALL `pack_hits` on ensemble order with `k=top_n`, then expand as usual.

**Independent Test**: Unit-test `cut_reranked` on a descending ~0–1 list: (a) `top_n=12`, `margin=0.20`, `floor=0.30` keeps a prefix until the first gap `> 0.20` or 12 items when best ≥ 0.30; (b) `floor=0.30` and best `= 0.25` returns `[]`; (c) walk uses `break` (a later item after a gap is not kept). Replay methodology retrieve on cached `2609.01617` v1: packed `[n]` SHALL include methodology/architecture prose, not only VIII-A/VIII-D + two V-B equations; count `<= top_n`. Regression: `1706.03762` v7 still expands E1 / Table 2 BLEU with packed `n <= top_n`.

---

## Edge Cases

- WHEN overfetch is empty THEN retrieve SHALL emit `evidence_chunks=[]` as today (T3 empty / retry path unchanged).
- WHEN rerank scores tie THEN the system SHALL break ties by first-stage ensemble order (stable).
- WHEN two papers are admitted THEN Voyage runs once on the concatenated unique documents; **sort + `cut_reranked` are per paper** (each paper has its own best score).
- WHEN retry formulate changes the hybrid query THEN first-stage candidates may change; rerank query SHALL still be task + **this attempt’s** feedback, not the previous formulated string.
- WHEN section metadata is empty THEN the document string SHALL be `content` only.
- WHEN a document is long THEN Voyage’s own truncation (`truncation=True` default) MAY apply for scoring only; pack/expand SHALL keep full `content`.
- WHEN Voyage Preview `rerank-3` returns an API error THEN RRF fallback SHALL apply; SHALL NOT retry with `rerank-2.5` or Qwen.
- WHEN Hugging Face / torch is absent THEN retrieve SHALL still work (no local model).
- WHEN `ranked` is empty THEN `cut_reranked` SHALL return `[]` without reading a best score.
- WHEN `margin` is `0` THEN only hits tied with the best score (difference `<= 0`) SHALL be kept, still capped by `top_n`.
- WHEN `VOYAGE_API_KEY` is unset at boot THEN the process SHALL fail fast; a later missing-key during a request SHALL NOT be the normal path (Settings required).

---

## Requirement Traceability

Each requirement gets a unique ID for tracking across design, tasks, and validation.

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| RETR-10 | P1: Larger first-stage hybrid | Execute | ✅ Verified (UAT pending) |
| RERANK-01 | P1: Task-conditioned Voyage rerank | Execute | ✅ Verified (UAT pending) |
| RERANK-02 | P1: Task-conditioned Voyage rerank | Execute | ✅ Verified (UAT pending) |
| RERANK-03 | P1: Task-conditioned Voyage rerank | Execute | ✅ Verified |
| RERANK-04 | P1: Adaptive score cut after rerank | Execute | ✅ Verified (UAT pending) |
| RERANK-05 | P1: Adaptive score cut after rerank | Execute | ✅ Verified |
| RERANK-06 | P1: Adaptive score cut after rerank | Execute | ✅ Verified (UAT pending) |
| POL-11 | P1: Larger first-stage hybrid | Execute | ✅ Verified |
| DEP-01 | P1: Task-conditioned Voyage rerank | Execute | ✅ Verified |

**ID map (normative behavior):**

- **RETR-10** — First-stage hybrid `k=40` per leg per paper; do not slice before rerank; EnsembleRetriever weights unchanged.
- **RERANK-01** — Voyage `rerank-3`; one call per execute on unique documents; `relevance_score` as returned; off the event loop; no graph node; no torch.
- **RERANK-02** — Voyage query is retrieve `task` (+ step eval feedback on retry), not `FormulatedQuery`, not the Qwen Instruct template. Document is section + `content`.
- **RERANK-03** — Registry abilities describe overfetch + task rerank + adaptive cut; `Citation` / `EvidenceChunk` gain no score field; no model ids / logits / `margin` in planner text.
- **RERANK-04** — `cut_reranked` walk/`break`; Policy values passed from `RetrieveRunner`; defaults `top_n=12`, `margin=0.20`, `floor=0.30`.
- **RERANK-05** — Voyage runtime failure → `pack_hits` ensemble order, `k=top_n`; log; do not crash; do not fall back to Qwen or another Voyage model.
- **RERANK-06** — Default `floor=0.30`: if that paper’s best score `< floor`, return `[]` for that paper. Then `pack_hits` on the cut list + `expand_hits`.
- **POL-11** — `retrieve_first_stage_k=40`; `retrieve_rerank_top_n=12`; `retrieve_rerank_margin=0.20`; `retrieve_rerank_floor=0.30`; first-stage `k` is not `overfetch_factor * k`.
- **DEP-01** — Voyage client + `VOYAGE_API_KEY` required at boot; no `torch` / `sentence-transformers` / `transformers` on the retrieve path.

**Coverage:** 9 total, 9 mapped to stories, 0 unmapped.

---

## Success Criteria

- [ ] On the methodology task for `2609.01617` v1, packed `[n]` includes section prose for the method (architecture and/or V-C RRF), not only results tables and isolated V-B equations.
- [ ] Structured-aware Independent Test on `1706.03762` v7 still expands E1 / a results table in some excerpt; packed hits per paper ≤ `top_n`.
- [ ] Retrieve judge for a broad methodology task is less likely to `retry` solely because `[1]`–`[5]` were formulas/tables (qualitative UAT on LangSmith `01a06938-a33c-7bd0-aaaa-de2129d4d34e`).
- [x] `cut_reranked` unit tests cover margin `break` at 0.20, `top_n` cap, `floor=0.30` empty list, and empty input.
- [x] No new SSE names, no Citation schema change, no new LangGraph node, T1/T2a/T3 routing unchanged.
- [x] Retrieve scoring does not import `torch`; API process does not start without `VOYAGE_API_KEY`.
- [x] A retrieve on cached chunks completes without a multi-minute Hub/CPU cold start.

---

## Notes

LangChain’s `CrossEncoderReranker` + `ContextualCompressionRetriever` still skip this product’s pack/expand. Voyage `top_k` has the same trap. Keep custom score → `cut_reranked` → `pack_hits` / `expand_hits`.

`margin=0.20` and `floor=0.30` are on Voyage’s **relevance_score** scale (docs examples: on-query ~0.94, off-query ~0.25–0.28). UAT on `2609.01617` / `1706.03762` MAY retune **only** those two knobs without reopening model id or query source.

If UAT shows isolated equations still outrank V-C prose with `rerank-3`, do **not** silently switch to `rerank-3-lite`, `rerank-2.5`, or Qwen 4B without a spec amendment. `rerank-3-lite` is deferred if Preview latency/cost hurts.

`rerank-3` is Voyage Preview as of 2026-09-01. Preview errors are RRF fallback, not a different model.
