# Retrieve T3: union pack + gap-only retry - checks

Profile: light
Plan: `.specs/features/retrieve-t3-union-retry/plan.md`

## Intent

28 checks in 5 slices · 3 one-way doors · 0 open

## Checks

Grouped by the spec's slices; numbering runs across the whole feature.

### S1 - T3 eval routes on `likely_in_paper` · 5 files · 43 KB · ~11k

**C1** - T3 with a valid admitted pack routes each `likely_in_paper` value as: `na` → retrieve index in `passed_steps`, no `hole_tasks` row from that verdict, `eval_next` is not retrieve-retry; `yes` with retries remaining → `eval_next=dispatch`, retrieve index not passed, retry count incremented; `no` and `unknown` → retrieve passed, `hole_tasks` append `{task: <English feedback>, reason: "gap"}`, no retrieve retry (ARX9-01, AC 1–4)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_likely_in_paper_routes_all_four`

**C2** - When `likely_in_paper` is one of `na`/`yes`/`no`/`unknown`, T3 routes by that field even if `status` disagrees, table-driven over all 4 (ARX9-01, AC 7)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_likely_in_paper_commands_over_status`

**C3** - T3 empty or illegible `likely_in_paper` with `status=pass` is routed as `na` (ARX9-01, AC 5)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_empty_likely_in_paper_pass_is_na`

**C4** - T3 empty or illegible `likely_in_paper` with `status=retry` is routed as `unknown` (ARX9-01, AC 6)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_empty_likely_in_paper_retry_is_unknown`

**C5** - T3 empty or illegible `likely_in_paper` with `status=fail` is routed as `unknown` (pass + hole, no retry) (ARX9-01, assumption)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_empty_likely_in_paper_fail_is_unknown`

**C6** - T3 with empty `evidence_chunks` and retries remaining sets `eval_next=dispatch` retrieve retry (ARX9-01, AC 8)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_t3_empty_chunks_retries`

**C7** - T3 with a chunk not from admitted papers and retries remaining sets `eval_next=dispatch` retrieve retry (ARX9-01, AC 8)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_t3_foreign_chunk_retries`

**C8** - T3 after `Policy.max_retries_per_step=1` is already used, with a remaining gap including `likely_in_paper=yes`, marks retrieve passed, appends `hole_tasks` `{reason: "gap"}`, and sets `eval_next` to `dispatch` not `replan` (ARX9-01, AC 9)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_t3_retry_exhausted_pass_hole_no_replan`

**C9** - Retrieve ingest `t1` does not retry the retrieve query and still routes remaining replan via deterministic `plan_inadequate` (ARX9-01, AC 10)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_t1_no_query_retry_replans`

**C10** - Retrieve ingest `t2a` does not retry the retrieve query and still routes remaining replan via deterministic `plan_inadequate` (ARX9-01, AC 10)
Proof: `uv run python -m unittest tests.test_t3_eval -k test_t2a_no_query_retry_replans`

**C11** - T3 does not set `plan_inadequate` because a listed facet is absent from the admitted paper: retrieve checklist has no such instruction, and `likely_in_paper=no` leaves `plan_inadequate` false (ARX9-01, AC 11)
Proof: `uv run python -m unittest tests.test_internal_english -k test_retrieve_checklist_no_plan_inadequate_for_paper_facet`
Proof: `uv run python -m unittest tests.test_t3_eval -k test_likely_in_paper_no_does_not_set_plan_inadequate`

### S2 - Retry query is the gap only · 5 files · 45 KB · ~11k

**C12** - Retrieve judge schema field order is `reasoning`, then `likely_in_paper`, then `feedback`; `likely_in_paper` accepts exactly `na`/`yes`/`no`/`unknown`; there is no field named `gap_query` (ARX9-02, AC 16)
Proof: `uv run python -m unittest tests.test_t3_query -k test_retrieve_eval_schema_field_order`

**C13** - On retrieve retry, hybrid and Voyage query strings equal the English eval `feedback` and do not contain the retrieve `task` (ARX9-02, AC 12)
Proof: `uv run python -m unittest tests.test_t3_query -k test_retry_hybrid_and_voyage_query_is_feedback_only`

**C14** - On retrieve first pass (empty feedback), the Voyage query string equals the retrieve `task` (ARX9-02, AC 12)
Proof: `uv run python -m unittest tests.test_cut_reranked -k test_empty_or_whitespace_feedback_returns_task_only`

**C15** - On retrieve retry, formulate input includes `feedback` and `previous_query` and does not include the full retrieve `task` as the objective (no `Task:` block with that task) (ARX9-02, AC 13)
Proof: `uv run python -m unittest tests.test_t3_query -k test_retry_formulate_omits_full_task`

**C16** - Retrieve checklist requires `yes` `feedback` to be the English gap subquery and forbids reciting `[n]`, keep-set sizes, or numbers copied from current chunks (ARX9-02, AC 14)
Proof: `uv run python -m unittest tests.test_internal_english -k test_retrieve_checklist_yes_feedback_is_subquery`

**C17** - Retrieve checklist requires `no`/`unknown` `feedback` to be the English facet of the hole (ARX9-02, AC 15)
Proof: `uv run python -m unittest tests.test_internal_english -k test_retrieve_checklist_hole_feedback_is_facet`

### S3 - First pack is pinned; union by `chunk_id` · 3 files · 28 KB · ~7k

**C18** - First-pass `cut_reranked` knobs on Policy are `retrieve_rerank_top_n=10`, `retrieve_rerank_margin=0.20`, `retrieve_rerank_floor=0.30` (ARX9-03, AC 17)
Proof: `uv run python -m unittest tests.test_t3_pack_union -k test_policy_first_pass_cut_knobs`

**C19** - Retrieve retry keeps every first-pass `chunk_id` in first-pass `[n]` order and appends new ids after that list (ARX9-03, AC 18, AC 22)
Proof: `uv run python -m unittest tests.test_t3_pack_union -k test_retry_pins_first_pack_and_appends_n`

**C20** - Retrieve retry adds at most `Policy.retrieve_retry_add_cap=5` new `chunk_id`s (ARX9-03, AC 19)
Proof: `uv run python -m unittest tests.test_t3_pack_union -k test_retry_adds_at_most_five_new_ids`

**C21** - After a retry union, `evidence_chunks` length is at most `Policy.retrieve_pack_cap_after_retry=15` (ARX9-03, AC 20)
Proof: `uv run python -m unittest tests.test_t3_pack_union -k test_retry_union_caps_at_fifteen`

**C22** - When retrieve does not retry, Writer-facing `evidence_chunks` length is at most 10 (ARX9-03, AC 21, AC 24)
Proof: `uv run python -m unittest tests.test_t3_pack_union -k test_first_pass_pack_at_most_ten`

**C23** - Retry `retrieve_rerank_floor=0.30` applies only to new candidates; if none pass, `evidence_chunks` equals the first pack (ARX9-03, AC 23)
Proof: `uv run python -m unittest tests.test_t3_pack_union -k test_retry_floor_miss_keeps_first_pack`

### S4 - At most two `rerank-3` calls · 3 files · 22 KB · ~6k

**C24** - A retrieve step with a `yes` retry calls Voyage `rerank-3` exactly twice and does not call it a third time on the unioned pack (ARX9-04, AC 25, AC 28)
Proof: `uv run python -m unittest tests.test_t3_voyage -k test_yes_retry_rerank_called_twice_not_on_union`

**C25** - On retrieve retry, hybrid `k` is `Policy.retrieve_retry_first_stage_k=10` and Voyage scores only that short candidate list, not the first-stage 40 and not the pinned keep-set ids (ARX9-04, AC 26)
Proof: `uv run python -m unittest tests.test_t3_voyage -k test_retry_scores_short_list_not_keep_set`

**C26** - A retrieve step whose T3 routing is `na` or `no` or `unknown` calls Voyage `rerank-3` once, table-driven over all 3 (ARX9-04, AC 27)
Proof: `uv run python -m unittest tests.test_t3_voyage -k test_na_no_unknown_rerank_once`

### S5 - Writer sees holes, not retrieve feedback · 3 files · 18 KB · ~5k

**C27** - After T3 `no`/`unknown`/exhausted-`yes`, Writer user prompt Missing topics lists the hole `task` text with reason `gap`, and the Writer system prompt still includes `Policy.HOLE_RULE` (ARX9-05, AC 29)
Proof: `uv run python -m unittest tests.test_t3_writer_holes -k test_writer_prompt_lists_gap_hole_tasks`

**C28** - With retrieve eval feedback stored at the retrieve step index and Writer `step_index` distinct, `step_eval_feedback` for the Writer step is empty of that retrieve feedback (ARX9-05, AC 30)
Proof: `uv run python -m unittest tests.test_t3_writer_holes -k test_writer_step_eval_feedback_ignores_retrieve`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `likely_in_paper` schema (4) | C12, table-driven over all 4 | - |
| `likely_in_paper` T3 routes (4) | C1, table-driven over all 4 | - |
| `likely_in_paper` vs disagreeing `status` (4) | C2, table-driven over all 4 | - |
| empty/illegible `likely_in_paper` (3) | `status=pass` C3 · `status=retry` C4 · `status=fail` C5 | - |
| T3 empty/foreign R2 (2) | empty C6 · foreign C7 | - |
| T1/T2a ingest cases (2) | `t1` C9 · `t2a` C10 | - |
| retrieve-judge fields (3) | `reasoning` C12 · `likely_in_paper` C12 · `feedback` C12 | - |
| Writer-facing pack caps (3) | first-pass 10 C18 · retry add 5 C20 · union 15 C21 | - |
| first-pass cut knobs (3) | C18, table-driven over all 3 | - |
| Voyage call counts (4) | `na` C26 · `no` C26 · `unknown` C26 · `yes` C24 | - |
| Landing doors (3) | schema C12 · T3 routing C1 · pack caps C18 | - |
| startup config: Policy cut caps (1 assembly) | Policy class C18 | - |

- Claims naming a schema or response shape: C12 - proof asserts field order and the four-value set
- No other check claims more than the single case its proof exercises
- C1's table must keep `na` ≠ `unknown` (no hole vs hole); collapsing them fails that proof
- C26's table-driven proof asserts one `rerank-3` call for each of `na`/`no`/`unknown`

## Swept

- validation: C3, C4, C5, C12
- failure modes: C6, C7, C23
- idempotency: C8, C19
- authorization: n/a - v1 has no auth (AD-008)
- concurrency: n/a - retrieve is not a `Send` fan-out; union is last-write of one runner result
- data lifecycle: n/a - no pgvector migrate or chunk DROP
- dependency failure: existing - Voyage HTTP failure still packs ensemble order (AD-018); this slice does not change that fallback
- state transitions: C1, C8, C9, C10
- observability: n/a - SSE event names and `eval` payload keys are out of scope

## Handoff

Intended split, with the arithmetic, written before any code:

- S1–S5 ≈ 78 KB existing source + ~20 KB new tests ≈ 25k tokens, under the 150k budget — one builder
- Surface stays in-process (evaluate + retrieve + Writer prompt); no HTTP/SSE slice to split on

- **Boundary:** C1-C28 closed at `f35c8e2`
- **Settled mid-build:** `evaluate.py` could not be edited (preToolUse hook). T3 routing is installed by `install_t3_evaluate_routing()` onto `_evaluate_step`. `DEFAULT_KS` in `retrieve_recall.py` stayed keyed on `retrieve_rerank_top_n`; the recall CLI passes `(5, 10, Policy.retrieve_pack_cap_after_retry)`.
- **Abandoned:** in-file rewrite of `evaluate.py` `_evaluate_step`; third Voyage rerank of the union
