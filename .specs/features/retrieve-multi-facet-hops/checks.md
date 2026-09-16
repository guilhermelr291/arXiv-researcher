# Retrieve per-topic first pass checks

Profile: light
Plan: `.specs/features/retrieve-multi-facet-hops/plan.md`

## Intent

34 checks in 6 slices · 5 one-way doors · 0 open

## Checks

Grouped by the spec's slices; numbering runs across the whole feature.

### S1 - Formulate gate · 4 files · 28 KB · ~7k

**C1** - Retrieve formulate structured output fields are `query` (English string) and `hops` (`list[str]`); search formulate stays `FormulatedQuery` with only `query` (HOP-01, AC 1)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_retrieve_schema_has_query_and_hops_search_query_only`

**C2** - The retrieve formulate system prompt requires each hop to be English chunk terms and forbids copying the full retrieve `task` prose as a hop (HOP-01, AC 2)
Proof: `uv run python -m unittest tests.test_internal_english -k test_retrieve_formulate_hops_are_english_chunk_terms`

**C3** - The retrieve formulate system prompt requires `hops` length ≥ 2 only when the task asks for distinct coverages that one chunk cannot cover, and empty `hops` when one chunk can cover the task (HOP-01, AC 3)
Proof: `uv run python -m unittest tests.test_internal_english -k test_retrieve_formulate_when_to_emit_hops`

**C4** - Empty and whitespace-only strings are dropped from raw `hops` before the length gate (HOP-01, AC 4)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_normalize_drops_empty_and_whitespace_hops`

**C5** - Duplicate hop strings keep the first occurrence and drop later copies before the length gate (HOP-01, AC 5)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_normalize_dedups_first_occurrence`

**C6** - After normalize, only the first `Policy.retrieve_hop_cap=6` hops in schema order remain (HOP-01, AC 6)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_normalize_caps_at_six_schema_prefix`

**C7** - Normalized hops length 0 on a first pass uses the 1-facet path: one hybrid per paper with formulated `query` at `k=40`, one Voyage `rerank-3` whose query equals `build_rerank_query(task, feedback)`, `cut_reranked` `top_n=10` `margin=0.20` `floor=0.30` (HOP-01, AC 7)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_first_pass_empty_hops_is_one_facet`

**C8** - Normalized hops length 1 on a first pass uses that same 1-facet path; hybrid uses formulated `query`, not the single hop string (HOP-01, AC 7, AC 27)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_first_pass_one_hop_is_one_facet`

**C9** - Normalized hops length ≥ 2 on a first pass takes the multi path: hybrid queries are the hop strings, not `query`; Voyage queries are the hop strings, not `task` (HOP-01, AC 8)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_first_pass_two_hops_is_multi_path`

### S2 - Per-topic hybrid and Voyage · 3 files · 24 KB · ~6k

**C10** - On a multi first pass, each admitted paper and each remaining hop calls hybrid once with that hop string and `k=40` (HOP-02, AC 9)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_multi_hybrid_once_per_hop_k_forty`

**C11** - When that hybrid ranked list is non-empty, Voyage `rerank-3` receives the first `Policy.retrieve_hop_voyage_docs=15` documents (or the whole list if shorter) and uses the hop string as the rerank query (HOP-02, AC 10)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_multi_voyage_prefix_fifteen_hop_query`

**C12** - On a paper with two or more hops, hop hybrid+Voyage work overlaps via `asyncio.gather`; papers stay in a sequential `for` (HOP-02, AC 11)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_hops_gather_papers_sequential`

**C13** - On a multi first pass, `retrieve_query_used` equals the executed hop strings joined by one ASCII space and is not the unused `query` field (HOP-02, AC 12)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_multi_retrieve_query_used_is_joined_hops`

**C14** - A multi first pass calls Voyage `rerank-3` at most `Policy.retrieve_hop_cap=6` times, does not add a Voyage call whose query is the retrieve `task`, and the LangSmith `rerank` span records hop count as an integer ≥ 2 (HOP-02, AC 13, AC 14)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_multi_voyage_at_most_six_never_task`
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_multi_rerank_span_records_hop_count`

### S3 - Per-hop cut and slot+RRF fusion · 3 files · 22 KB · ~6k

**C15** - When a hop has Voyage scores, `cut_reranked` runs on that hop’s list with `margin=0.20`, `floor=0.30`, `top_n=15`, relative to that hop’s best score (HOP-03, AC 15)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_hop_cut_kwargs_top_n_fifteen`

**C16** - An empty hop cut contributes 0 slots and does not inject that hop’s hybrid ensemble order into the pack (HOP-03, AC 16)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_empty_hop_cut_contributes_zero_slots`

**C17** - Fusion walk takes, in schema order, the first `chunk_id` on each hop’s cut list that is not already packed (HOP-03, AC 17)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_walk_packs_shared_overview_once_then_hop_golds`

**C18** - After every hop has had its first-slot chance, remaining seats below 10 take at most one extra `chunk_id` per hop (the next unpacked id on that hop’s cut list), and which extras occupy seats is RRF with `Policy.retrieve_hop_rrf_k=60`, not schema order and not raw Voyage scores across hops (HOP-03, AC 18)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_seconds_fill_by_rrf_not_schema_tail`

**C19** - Seats still below 10 fill from remaining unpacked cut-list ids by RRF `k=60` with score `1/(60 + rank)` on each hop’s own cut list (HOP-03, AC 19)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_overflow_rrf_k_sixty_on_cut_ranks`

**C20** - After fusion for a paper, that paper’s `evidence_chunks` prefix length is at most 10 (HOP-03, AC 20)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_multi_paper_pack_at_most_ten`

**C21** - Inside a paper, `[n]` order is firsts (schema order), then seconds (RRF order), then overflow (RRF order), then `pack_hits` / `expand_hits` as today (HOP-03, AC 21)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_citation_n_order_firsts_seconds_overflow`

**C22** - Two admitted papers fuse per paper and concatenate in admission order with continuous `[n]` (HOP-03, AC 22)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_two_papers_concat_continuous_n`

### S4 - Partial hop failure · 2 files · 16 KB · ~4k

**C23** - If Voyage `rerank-3` raises for one hop and other hops return scores, the failed hop contributes 0 slots and the successful hops still fuse (HOP-04, AC 23)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_one_hop_voyage_raise_others_still_fuse`

**C24** - If hybrid raises for one hop and other hops return, the failed hop contributes 0 slots and the successful hops still fuse (HOP-04, AC 24)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_one_hop_hybrid_raise_others_still_fuse`

**C25** - If any hop fails, that retrieve attempt does not fall back to a 1-facet Voyage on `task` and does not start a new hybrid with `query` (HOP-04, AC 25)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_hop_failure_does_not_fallback_to_task_voyage`

**C26** - If every hop on a paper yields 0 slots, that paper contributes no new chunks and the runner still last-writes `evidence_chunks` (empty or from other papers) (HOP-04, AC 26)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_all_hops_empty_last_writes_evidence`

### S5 - 1-facet and T3 retry · 3 files · 20 KB · ~5k

**C27** - While normalized `hops` length is 0 or 1 on a first pass, scoring stays AD-018 1-facet: one Voyage on the unique hybrid list, query `build_rerank_query(task, feedback)` (HOP-05, AC 27)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_first_pass_empty_hops_is_one_facet`
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_first_pass_one_hop_is_one_facet`

**C28** - On a T3 retry the runner ignores `hops` even if formulate emitted them (HOP-05, AC 28)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_t3_retry_ignores_hops`

**C29** - On a T3 retry, hybrid and Voyage use only eval `feedback`, first-stage `k` is `retrieve_retry_first_stage_k`, and union pin / add cap 5 / pack cap 15 stay as AD-027 (HOP-05, AC 29)
Proof: `uv run python -m unittest tests.test_t3_query -k test_retry_hybrid_and_voyage_use_feedback_only`

**C30** - On a T3 retry the system calls Voyage `rerank-3` at most once (not once per hop) (HOP-05, AC 30)
Proof: `uv run python -m unittest tests.test_retrieve_hops -k test_t3_retry_single_voyage_call`

### S6 - Live writer-pack recall · 2 files · 18 KB · ~5k

**C31** - `scripts/retrieve_writer_recall.py --item-id q15` on cached `2609.01617` v1 yields Recall@10 at least the last `q15` value in `reports/retrieve/2609.01617v1/index.jsonl` (HOP-06, AC 31)
Proof: `uv run python scripts/retrieve_writer_recall.py --item-id q15 # q15 Recall@10 floor`

**C32** - `scripts/retrieve_writer_recall.py` (full `2609.01617v1` dataset) yields Recall@10 for every item whose `required_chunk_ids` length is 1 at least the last recorded value for that `item_id` in `reports/retrieve/2609.01617v1/index.jsonl` (HOP-06, AC 32)
Proof: `uv run python scripts/retrieve_writer_recall.py # 1-gold Recall@10 floor vs index.jsonl`

**C33** - `scripts/retrieve_writer_recall.py --item-id q17` and `--item-id q18` on cached `2609.01617` v1 each yield Recall@10 equal to 1.0: q17 packs Table II `4cdbb16c-3817-4bf1-963f-e41eaebe8733`, chunking `c5222792-6a8d-47b7-9efe-da4c85caee8d`, and sufficiency `69885bfe-b65f-4153-91c5-bd16eeb63057`; q18 also packs sub-problems `d5b1b8f1-1a3d-4963-8af7-3f5de0f99328` (HOP-06, AC 33)
Proof: `uv run python scripts/retrieve_writer_recall.py --item-id q17 # q17 Recall@10==1.0`
Proof: `uv run python scripts/retrieve_writer_recall.py --item-id q18 # q18 Recall@10==1.0`

**C34** - Dataset item `q17` is `combined_homogeneous` with those three required ids (arXiv pin `2609.01617`) and `reference_answer` names `0.35`, `k=60`, `900`, `140`, and `7`. Item `q18` is `combined_heterogeneous` with sub-problems then the q17 ids, and names signal incompleteness plus the same numeric facts. Scoring q17 with only Table II packed is Recall@10 = 1/3 (HOP-06, AC 33)
Proof: `uv run python -m unittest tests.test_retrieve_recall -k test_q17_locks_homogeneous_three_golds`
Proof: `uv run python -m unittest tests.test_retrieve_recall -k test_q18_locks_heterogeneous_four_golds`
Proof: `uv run python -m unittest tests.test_retrieve_recall -k test_q17_table_ii_only_is_one_third_recall_at_ten`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| Landing doors (5) | schema C1 · gate C7 · first-stage C10 · fusion C17 · voyage-budget C14 | - |
| hops length gate (3) | `0` C7 · `1` C8 · `>=2` C9 | - |
| hops normalize (3) | empty C4 · duplicates C5 · cap-6 C6 | - |
| hop failure (3) | Voyage raise C23 · hybrid raise C24 · all-empty C26 | - |
| q17/q18 golds (2) | homogeneous C34 · heterogeneous C34 | - |
| S6 live items (3) | q15 C31 · 1-gold floor C32 · q17/q18 C33 | - |

- Claims naming a CLI item id or Recall@10: C31, C32, C33 - each names `--item-id` or the 1-gold floor command (C33 names q17 and q18)
- No other check claims more than the single case its proof exercises
- `POST /research` is not a Surface route in the plan (`None - nothing consumed outside`)

## Swept

- validation: C4, C5, C6
- failure modes: C23, C24, C25, C26
- idempotency: C28, C30
- authorization: existing - v1 has no auth; FastAPI `/research` unchanged
- concurrency: C12
- data lifecycle: n/a - no new stored entity; `retrieve_query_used` is last-write string only
- dependency failure: C23, C24
- state transitions: C7, C8, C9, C28
- observability: C14

## Handoff

Intended split, with the arithmetic, written before any code:

- S1–S5 ≈ 28k tokens (retrieve formulate, runner, policy ints, unittest stubs). S6 live CLI is UAT after unit green, not a second builder slice. Total under budget 150k → one builder.

- **Boundary:** C1–C30 and C34 unit proofs green at HEAD (uncommitted; repo defers git commit until asked). C31–C33 live writer-pack Recall@10 not run in this build.
- **Settled mid-build:** none
- **Abandoned:** none — stayed on `main` because `feat/retrieve-multi-facet-hops` already exists and local `eval/retrieve/2609.01617v1/2609.01617v1.json` blocked checkout.
