# Retrieve Writer-Pack Recall Specification

**Feature:** `retrieve-writer-recall`  
**Spec status:** Code-validated T1–T8 (2026-09-10; uncommitted). Gate 130/130. Isolated RetrieveRunner deleted. Live Independent Test still UAT (preflight green).  
**Date:** 2026-09-10  
**Gray areas:** Locked in grill-me 2026-09-10 (isolated) and product-eval follow-up 2026-09-10 (E2E); `discuss.md` skipped  
**Parent retrieve:** `.specs/features/retrieve-cross-encoder-rerank/spec.md`  
**Parent admission:** `.specs/features/admission-retrieve-per-topic/spec.md`  
**Parent loop:** `.specs/features/orchestrator-eval-replan/spec.md`  
**Parent SSE:** `.specs/features/sse-agent-dispatcher/spec.md` (graph consume path)

Offline product report: given a **student query**, run the production graph through gate → planner → search → retrieve (eval retries/replan included) and score whether qrel evidence reached the Writer pack (`chunk_id` or expanded table/equation body). **The Writer SHALL NOT run.** This feature SHALL NOT add or keep an isolated `RetrieveRunner` eval (frozen task, planner out).

## Problem Statement

Chunks that matter are the ones the Writer would see after a real session. Scoring `RetrieveRunner` on a frozen task can look healthy while production still fails, because the planner emits a different task and search may admit a different paper. The operator needs a small golden set of student queries (collection closed by pinning an arXiv id) and a harness that stops after retrieve so Writer tokens are not burned.

## Goals

- [x] Frozen JSON dataset of **student queries** (each query contains the target arXiv id) plus `required_chunk_ids`, load-validated.
- [x] E2E harness runs the compiled research graph from the student `query` through retrieve eval pass, then scores Recall@k on `evidence_chunks` and stops.
- [x] Writer execute is never invoked on this path (no `answer_delta`, no Writer LLM).
- [x] Production `POST /research` and Chainlit are unchanged (Writer still runs for students).
- [x] Pure Recall@k on writer-visible pack evidence (`k` in 5, 10, 15) is unit-tested with no LLM, Voyage, or Postgres (reuse existing scorer; qrel atoms passed in).

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| Writer markdown / citations / RAGAS | This report is evidence delivery, not generation quality |
| Changing Gate, planner, search, retrieve, or Writer **production** behavior | Harness-only stop; student path unchanged |
| Prompt prefix “use the article with id” on the retrieve **task** | Pin is the **student query** containing the arXiv id (`id:` search rule) |
| LangSmith as the id source | Score graph `evidence_chunks` after retrieve |
| CI fail on a recall floor | Report only |
| Open-world eval over arbitrary arXiv (no pinned paper) | Golden set closes the collection per item |
| Isolated `RetrieveRunner` harness (frozen retrieve task, planner/search out) | Product number is E2E only; a later isolated test would optimize the wrong input |

### Supersedes (this feature)

| Prior lock | What no longer holds |
| ---------- | -------------------- |
| AD-023 north-star | Product metric is isolated `RetrieveRunner` + frozen retrieve task, planner out |
| Spec locked “Retrieve input is the dataset `question` as the plan task” | E2E input is the student `query`; planner writes the retrieve task |
| Spec locked “CLI SHALL NOT invoke planner, gate, search” as the P1 harness | E2E invokes them; isolated retrieve is out of scope |
| ROADMAP “without running planner/search” as the feature goal | E2E includes them; Writer still excluded |

**Unchanged:** Recall@k formula, k = 5 / 10 / 15, qrel-must-exist-in-store preflight, no CI threshold, reports under `reports/retrieve/`. Quick 022: a table/equation qrel is also a hit when its body is inlined into another packed excerpt.

**Locked from specify (do not reopen):**

- **SUT:** `evidence_chunks` after the retrieve step that the graph actually ran (post formulate, hybrid, Voyage, `cut_reranked`, pack, expand). Not first-stage `k=40` alone. Not Writer excerpts after generation (Writer does not run).
- **Input:** dataset field `query` is a student question. It SHALL contain the expected `arxiv_id` (new-style `NNNN.NNNNN`, optional `vN`) so search formulation can emit `id:…` and close the collection for that item.
- **Graph:** same compiled graph as production (`gate → planner → dispatch → search|execute → evaluate → replan|finalize`). Harness uses a **fresh `thread_id` per item**.
- **Stop rule:** after retrieve eval **passes** (or the run ends with `insufficient` / `error` / `refused` / timeout **before** Writer execute), score whatever `evidence_chunks` exist and **SHALL NOT** `execute` a `writer` step. Search/retrieve retries and one remaining replan still apply, same caps as production.
- **Production unchanged:** students still get Writer. No new graph node required if the harness can halt before Writer execute.
- **Hit:** qrel `chunk_id` in `evidence_chunks[:k]`, **or** a table/equation qrel whose `content` appears in another packed excerpt in that prefix (`expand_hits` injection). `Recall@k` is hits / |qrel|. Macro and micro averages. The report SHALL annotate injected hits (qrel id, host id, kind). Prose qrels stay id-equality only.
- **Expected paper:** dataset `arxiv_id` + `version`. Report SHALL also list admitted `papers` so a search miss is visible (wrong paper → qrel ids absent → recall 0).
- **No isolated retrieve eval** in this feature: no frozen-task CLI, no P2 lantern, no follow-up story to split retrieve from planner/search via a second harness. Attribution stays in the E2E report (retrieve `task` + admitted papers).

---

## User Stories

### P1: E2E writer-pack recall (Writer off) ⭐ MVP

**User Story**: As an operator, I want to ask the system a student question (with the paper id in the text) and see whether the required chunks reached the Writer pack, without generating an answer, so the number reflects a real session and does not spend Writer tokens.

**Why P1**: This is the product measurement.

**Acceptance Criteria**:

1. WHEN the E2E CLI runs an item THEN it SHALL invoke gate, planner, search (if the plan includes search), and retrieve, using the student `query` as graph input — not a frozen retrieve task.
2. WHEN retrieve eval passes THEN the harness SHALL score `evidence_chunks` and SHALL NOT call `WriterRunner` / SHALL NOT emit `answer_delta`.
3. WHEN the planner’s next unpassed step is `writer` THEN the harness SHALL stop before that execute.
4. WHEN Gate refuses, the run times out, or the graph reaches `insufficient`/`error` before a retrieve pack exists THEN that item SHALL record empty delivered ids (Recall@k = 0) and a reason, and SHALL NOT start the Writer.
5. WHEN `required_chunk_ids` are missing from Postgres for the expected `(arxiv_id, version)` THEN the process SHALL exit non-zero before scoring that dataset (ingest/qrel drift), same as today’s preflight.
6. WHEN scoring succeeds THEN stdout and `reports/retrieve/` SHALL include per-item: `query`, planner retrieve `task` if any, admitted paper keys, delivered ids, hits, misses, injected table/equation notes, Recall@5/@10/@15, `retrieve_query_used`, plus macro and micro averages. Exit code SHALL NOT encode a recall threshold.

**Independent Test**: Ingest `2609.01617v1` with qrel ids. Run the E2E CLI on the student-query dataset. Confirm logs/traces show no Writer execute; report contains pack ids and the retrieve task the planner wrote.

---

### P1: Student-query golden set

**User Story**: As an operator, I want a versioned JSON of student queries (not retrieve tasks) tied to required chunk ids, so the collection is closed per item by the arXiv id in the query.

**Why P1**: Without this, E2E has no qrel.

**Acceptance Criteria**:

1. WHEN a dataset JSON is loaded THEN the system SHALL require `arxiv_id`, `version`, and a non-empty list of items each with `id`, `query`, and non-empty `required_chunk_ids`.
2. WHEN an item `query` does not contain that dataset `arxiv_id` THEN load SHALL fail (pin is mandatory in v1 of this eval).
3. WHEN Recall@k is computed THEN a packed `chunk_id` is a hit, and a table/equation whose body appears in another packed excerpt is also a hit (8 of 10 packed ids → 0.8; short pack does not invent slots; injected atoms count toward coverage).

**Independent Test**: Load-validation unit tests (no network). Existing `recall_at_k` tests stay.

---

## Edge Cases

- WHEN `required_chunk_ids` is empty THEN load SHALL fail.
- WHEN `evidence_chunks` is missing or empty THEN Recall@k SHALL be 0.0.
- WHEN `k` < 1 THEN scoring SHALL raise `ValueError`.
- WHEN the same `chunk_id` appears twice in evidence THEN membership SHALL count once.
- WHEN search admits a paper other than the expected key THEN scoring still runs against `evidence_chunks` (likely misses); the report SHALL list admitted keys.
- WHEN retrieve retries then passes THEN score the **final** `evidence_chunks` after the passing retrieve, not an earlier pack.
- WHEN a leftover Writer step exists on the plan after retrieve pass THEN it SHALL NOT run.
- WHEN a table or equation qrel is missing from packed ids but its `content` is inlined in another packed excerpt THEN it SHALL count as a hit and the report SHALL annotate the host `chunk_id`.

---

## Requirement Traceability

| ID | Requirement | Story | Status |
| -- | ----------- | ----- | ------ |
| RWR-01 | Dataset load validation (amended: student `query` + arXiv id pin) | P1 golden set | ✅ Verified |
| RWR-02 | Recall@k on writer-visible pack evidence; k = 5, 10, 15; injected table/equation annotated | P1 golden set | ✅ Verified (quick 022) |
| RWR-03 | Isolated `RetrieveRunner` harness; planner/search out | — | Cancelled (deleted T7) |
| RWR-04 | Fail if qrel ids are not in the ingested corpus | P1 E2E | ✅ Verified (unit/AST; live preflight 2026-09-10: paper + 43 chunks, 0 missing qrels) |
| RWR-05 | Report JSON/Markdown under `reports/retrieve/`; no CI threshold | P1 E2E | ✅ Verified |
| RWR-06 | E2E graph from student `query` through retrieve; score pack | P1 E2E | ⚠️ Unit verified; live Independent Test pending |
| RWR-07 | Writer execute SHALL NOT run on the E2E harness | P1 E2E | ⚠️ Unit halt verified; live Independent Test pending |
| RWR-08 | Production research path unchanged | P1 E2E | ✅ Verified |
| RWR-09 | Report planner retrieve task + admitted papers per item | P1 E2E | ✅ Verified |

---

## Success Criteria

- [ ] Operator can run an E2E report where each item is a student question with `2609.01617` in the text and see Recall@k on `evidence_chunks` without a Writer call. *(unit harness executed; live Independent Test still UAT)*
- [x] A red E2E item still exposes the retrieve task and admitted papers in the same report (no second, isolated retrieve job).
- [x] Students on Chainlit / `POST /research` still get Writer answers. *(source-inspect T8; live UAT pending)*
