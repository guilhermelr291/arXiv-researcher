# Retrieve Writer-Pack Recall — Locked Context

**Feature:** `retrieve-writer-recall`  
**Gathered:** 2026-09-10  
**Spec:** `.specs/features/retrieve-writer-recall/spec.md`  
**Status:** Tasks drafted 2026-09-10 (`.specs/features/retrieve-writer-recall/tasks.md`); spec/design still formally Draft; awaiting task approval before Execute

## Feature Boundary

Offline Recall@k of writer-pack `chunk_id`s after a real session through retrieve. **Writer off.** No isolated RetrieveRunner story (no P2).

## Decisions

1. **The only eval in this feature is E2E.** Isolated frozen-task retrieve is out of scope and SHALL NOT return as a later story in this spec. Attribution is the E2E report (planner retrieve task + admitted papers), not a second harness.
2. **SUT is `evidence_chunks`** (what the Writer *would* see). Not first-stage hybrid, not LangSmith spans, not generated markdown.
3. **Student `query` is the graph input.** It MUST contain the expected arXiv id so search can pin `id:NNNN.NNNNN` and close the collection for that golden item. No “use the article with id” glued onto the retrieve task.
4. **Writer SHALL NOT run** on the eval harness (token cost; this slice is not generation quality). Production Writer unchanged.
5. **Stop after retrieve eval pass** (or terminal outcome before Writer). Search/retrieve retries and one replan stay. Fresh `thread_id` per item.
6. **Hit = writer-visible evidence.** `chunk_id` in the pack, or a table/equation body inlined into another packed excerpt (`expand_hits`). Injected hits are annotated. Prose stays id-equality. (Quick 022; supersedes “packer false negatives stay visible”.)
7. **Qrel is `required_chunk_ids` only.** Metric is required-set coverage at the delivered list.
8. **Expected paper** is dataset `arxiv_id` + `version`. Report admitted papers so a wrong search hit is obvious.
9. **First corpus:** DocuSearch `2609.01617v1`. Gold ids must match the current Postgres ingest.
10. **No CI recall floor.** Report only.

## Deferred

- Open-world E2E without a pinned arXiv id (true N-paper search).
- Scoring Writer faithfulness on this same harness (use RAGAS).

Isolated retrieve eval is **not** deferred. It is out of scope.
