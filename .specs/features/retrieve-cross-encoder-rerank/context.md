# Retrieve Cross-Encoder Rerank Context

**Gathered:** 2026-09-04
**Spec:** `.specs/features/retrieve-cross-encoder-rerank/spec.md` (amendment: Voyage API replaces local Qwen)
**Status:** Spec + design approved 2026-09-04; Voyage tasks drafted; awaiting task approval before Execute

---

## Feature Boundary

Retrieve still overfetches hybrid candidates per paper, scores them **once** against the evidence **task**, cuts with `cut_reranked`, then `pack_hits` / `expand_hits`. This amendment replaces the **local** `tomaarsen/Qwen3-Reranker-0.6B-seq-cls` CrossEncoder with **Voyage AI’s rerank API**. Adaptive cut stays (relative to that query’s best score, plus `top_n`, plus optional `floor`). No new LangGraph node, no Citation/`EvidenceChunk` score field, no T1/T2a/T3 routing change, no hybrid-weight change.

---

## Implementation Decisions

### Reranker model (quality vs cost)

- Lock **`rerank-3`** (Voyage Preview as of 2026-09-01; highest accuracy; 32k context). Not lite. Not `rerank-2.5`.
- Preview is acceptable. Do **not** silently fall back to `rerank-2.5` if Preview errors — use the failure path below.
- Model id is locked. UAT that still ranks isolated equations above method prose SHALL retune **margin / floor** (and query text only if Specify allows), not swap the model without a spec amendment.

### Writer pack tightness (Voyage ~0–1 scores)

- Keep a **cluster close to this query’s best hit**, still capped at `top_n=12` (same walk/`break` as today; new numbers).
- **Floor on:** if even the best hit is junk, that paper contributes **no** chunks (empty → existing T3 retry path).
- Starting **margin ≈ 0.20** (medium cluster). Un-calibrated until UAT; UAT MAY retune only `margin` and `floor`.
- Do **not** keep `margin=4.0` (logit-scale leftover; would never fire on Voyage scores).

### When Voyage fails

- Runtime load/score failure (timeout, 5xx, network): **silent RRF fallback** — `pack_hits` ensemble order with `k=top_n`, then expand (same as today’s Qwen load/score fallback). Log the exception. Do not crash the graph.
- **Drop the local Qwen / torch path entirely.** No second fallback to HuggingFace.
- Missing `VOYAGE_API_KEY`: **refuse to start the API** (boot error). Not the same as a later Voyage outage.

### What Voyage sees

- **Query:** retrieve **task only** on first attempt; on retry, task + this step’s eval feedback. **No** extra locked instruction string prepended. **Not** `FormulatedQuery`.
- **Document:** `metadata.section` + newline + `content` (placeholders still in prose), same as today.

### Agent's Discretion

- **Query source (user said you decide):** use retrieve `task`, plus this step’s `eval_by_step` feedback on retry — same product lock as AD-017. Hybrid `FormulatedQuery` stays first-stage only.
- **Floor number (user said you decide):** start **`floor=0.30`** (Voyage unrelated examples sit ~0.25–0.28). Un-calibrated; UAT may retune with `margin`.
- **UAT model swap (user said you decide):** do **not** auto-upgrade/downgrade the model. Retune `margin` / `floor` first. Changing `rerank-3` needs a spec amendment.
- **SDK vs REST, truncation flag, mapping Voyage `index` back to chunk order, Settings field name:** design/implement. Prefer `voyageai.Client` + `VOYAGE_API_KEY`. Do not pass Voyage `top_k` as the Writer cut — score the full unique list (or `top_k=len(chunks)`), then `cut_reranked`.
- **Remove** `torch` / `sentence-transformers` / `transformers` from runtime deps once Qwen is gone (fixes lifespan import + `--reload` watching torch). Qwen3 Instruct/Query/Document template helpers can go if nothing else uses them.

---

## Specific References

- Voyage docs: `rerank-3` / `rerank-3-lite` Preview; `relevance_score` examples ~0.94 (on-query) vs ~0.25–0.28 (off-query). Official Python: `vo.rerank(query, documents, model=...)`.
- Pain that triggered this: local 0.6B download (~2.4 GB) + CPU score + uvicorn `--reload` scanning torch made retrieve wall-clock unusable.
- Parent locks that stay: first-stage `k=40`, one score pass per execute, per-paper cut (each paper’s own best), pack `k=len(cut)`, expand after pack, fallback is whole-execute not per-paper retry.

---

## Deferred Ideas

- `rerank-3-lite` if Preview `rerank-3` latency or cost hurts UAT — Captured during: discuss 2026-09-04
- Qwen3-Reranker-4B / local torch path — already deferred; this amendment **removes** 0.6B rather than promoting 4B
- OpenAI rerank API — still out of scope
- Citation / EvidenceChunk score field — still out of scope
