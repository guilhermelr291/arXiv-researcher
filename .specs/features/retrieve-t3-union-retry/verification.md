# Retrieve T3: union pack + gap-only retry verification

**Verdict**: PASS
**Profile**: light
**Diff range**: c01e776..HEAD
**Round**: 1 - full
**Verifier**: independent sub-agent (author != verifier)

Profile is **light**: every named proof was run at HEAD; each named test exists and appeared as `ok`; each check C1–C28 has a located `file:line` assertion; level/sampling gaps are recorded; Swept `existing` was re-read against the code. Faults were **not** injected. Coverage was **not** recomputed. Binding sources were **not** opened. No standard/ui steps ran.

## Checks

Batched proof (one invocation, HEAD `d982196`):

`uv run python -m unittest tests.test_t3_eval tests.test_t3_query tests.test_cut_reranked tests.test_t3_pack_union tests.test_t3_voyage tests.test_t3_writer_holes tests.test_internal_english -v`

Exit 0. 50 tests, 0 failed. Every named proof below appeared individually as `ok` (21 extra tests from `test_cut_reranked` / `test_internal_english` also ran `ok`).

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | T3 routes `na`/`yes`/`no`/`unknown`: pass vs retry vs hole | `test_likely_in_paper_routes_all_four` ok | `tests/test_t3_eval.py:110` - `self.assertIn(1, update["passed_steps"])`; `:112` `self.assertNotIn(1, update["passed_steps"])`; `:114` `self.assertEqual(update["eval_next"], "dispatch")`; `:115` `self.assertEqual(update["retry_counts"].get("1"), 1)`; `:122` `self.assertIn({"task": _GAP, "reason": "gap"}, holes)` | PASS |
| C2 | Readable `likely_in_paper` commands over disagreeing `status`, all 4 | `test_likely_in_paper_commands_over_status` ok | `tests/test_t3_eval.py:139` - `self.assertIn(1, update["passed_steps"])`; `:143` `self.assertEqual(update["eval_next"], "dispatch")`; `:146` `self.assertIn({"task": _GAP, "reason": "gap"}, ...)` | PASS |
| C3 | Empty/illegible `likely_in_paper` + `status=pass` routes as `na` | `test_empty_likely_in_paper_pass_is_na` ok | `tests/test_t3_eval.py:162` - `self.assertIn(1, update["passed_steps"])`; `:163` `self.assertNotIn({"task": _GAP, "reason": "gap"}, ...)`; `:167` `self.assertNotEqual(update.get("retry_counts", {}).get("1"), 1)` | PASS |
| C4 | Empty/illegible + `status=retry` routes as `unknown` (pass+hole, no retry) | `test_empty_likely_in_paper_retry_is_unknown` ok | `tests/test_t3_eval.py:175` - `self.assertIn(1, update["passed_steps"])`; `:176` `self.assertIn({"task": _GAP, "reason": "gap"}, ...)`; `:181` `self.assertNotEqual(update.get("retry_counts", {}).get("1"), 1)` | PASS |
| C5 | Empty/illegible + `status=fail` routes as `unknown` (pass+hole, no retry) | `test_empty_likely_in_paper_fail_is_unknown` ok | `tests/test_t3_eval.py:189` - `self.assertIn(1, update["passed_steps"])`; `:190` `self.assertIn({"task": _GAP, "reason": "gap"}, ...)`; `:194` `self.assertNotEqual(update["eval_next"], "replan")` | PASS |
| C6 | T3 empty `evidence_chunks` with retries left → retrieve retry | `test_t3_empty_chunks_retries` ok | `tests/test_t3_eval.py:201` - `self.assertNotIn(1, update["passed_steps"])`; `:202` `self.assertEqual(update["eval_next"], "dispatch")`; `:203` `self.assertEqual(update["retry_counts"].get("1"), 1)` | PASS |
| C7 | T3 foreign chunk with retries left → retrieve retry | `test_t3_foreign_chunk_retries` ok | `tests/test_t3_eval.py:210` - `self.assertNotIn(1, update["passed_steps"])`; `:211` `self.assertEqual(update["eval_next"], "dispatch")`; `:212` `self.assertEqual(update["retry_counts"].get("1"), 1)` | PASS |
| C8 | After `max_retries_per_step=1`, remaining gap including `yes` → pass+hole, `eval_next=dispatch` not `replan` | `test_t3_retry_exhausted_pass_hole_no_replan` ok | `tests/test_t3_eval.py:215` - `self.assertEqual(Policy.max_retries_per_step, 1)`; `:220` `self.assertIn(1, update["passed_steps"])`; `:221` `self.assertIn({"task": _GAP, "reason": "gap"}, ...)`; `:225` `self.assertEqual(update["eval_next"], "dispatch")`; `:226` `self.assertNotEqual(update["eval_next"], "replan")` | PASS |
| C9 | Ingest `t1` does not retry retrieve query; remaining replan via `plan_inadequate` | `test_t1_no_query_retry_replans` ok | `tests/test_t3_eval.py:237` - `self.assertNotIn(1, update["passed_steps"])`; `:238` `self.assertEqual(update["eval_next"], "replan")`; `:239` `self.assertFalse(update.get("retry_counts", {}).get("1"))` | PASS |
| C10 | Ingest `t2a` does not retry retrieve query; remaining replan via `plan_inadequate` | `test_t2a_no_query_retry_replans` ok | `tests/test_t3_eval.py:253` - `self.assertNotIn(1, update["passed_steps"])`; `:254` `self.assertEqual(update["eval_next"], "replan")`; `:255` `self.assertFalse(update.get("retry_counts", {}).get("1"))` | PASS |
| C11 | T3 does not set `plan_inadequate` for a paper-absent facet | `test_retrieve_checklist_no_plan_inadequate_for_paper_facet` ok; `test_likely_in_paper_no_does_not_set_plan_inadequate` ok | `tests/test_internal_english.py:55` - `self.assertNotIn("plan_inadequate", _retrieve_checklist())`; `tests/test_t3_eval.py:269` - `self.assertFalse((update.get("last_eval") or {}).get("plan_inadequate"))` | PASS |
| C12 | Judge schema order `reasoning`, `likely_in_paper`, `feedback`; values `na`/`yes`/`no`/`unknown`; no `gap_query` | `test_retrieve_eval_schema_field_order` ok | `tests/test_t3_query.py:117` - `self.assertEqual(names, ["reasoning", "likely_in_paper", "feedback"])`; `:119`–`:122` `self.assertIn("na"/"yes"/"no"/"unknown", str(lip.annotation))`; `:123` `self.assertNotIn("gap_query", names)` | PASS |
| C13 | Retry hybrid and Voyage query equal eval `feedback`, not the retrieve `task` | `test_retry_hybrid_and_voyage_query_is_feedback_only` ok | `tests/test_t3_query.py:144` - `self.assertEqual(hybrid_query, _FEEDBACK)`; `:145` `self.assertNotIn(_TASK, hybrid_query)`; `:146` `self.assertEqual(voyage_queries, [_FEEDBACK])` | PASS |
| C14 | First pass (empty feedback): Voyage query equals retrieve `task` | `test_empty_or_whitespace_feedback_returns_task_only` ok | `tests/test_cut_reranked.py:86` - `self.assertEqual(build_rerank_query("  explain RRF  ", ""), "explain RRF")` | PASS |
| C15 | Retry formulate includes `feedback` and `previous_query`, no `Task:` block with the full task | `test_retry_formulate_omits_full_task` ok | `tests/test_t3_query.py:161` - `self.assertIn(_FEEDBACK, human)`; `:162` `self.assertIn(_PREV, human)`; `:163` `self.assertNotIn(f"Task:\n{_TASK}", human)` | PASS |
| C16 | Checklist: `yes` feedback is English gap subquery; forbids `[n]`, keep-set sizes, copied numbers | `test_retrieve_checklist_yes_feedback_is_subquery` ok | `tests/test_internal_english.py:59` - `self.assertIn("English subquery", text)`; `:60` `self.assertIn("Do not recite [n]", text)`; `:61` `self.assertIn("keep-set sizes", text)`; `:62` `self.assertIn("numbers copied from current chunks", text)` | PASS |
| C17 | Checklist: `no`/`unknown` feedback is English facet of the hole | `test_retrieve_checklist_hole_feedback_is_facet` ok | `tests/test_internal_english.py:65` - `self.assertIn("English facet of the hole", _retrieve_checklist())` | PASS |
| C18 | Policy first-pass cut knobs `top_n=10`, `margin=0.20`, `floor=0.30` | `test_policy_first_pass_cut_knobs` ok | `tests/test_t3_pack_union.py:115` - `self.assertEqual(Policy.retrieve_rerank_top_n, 10)`; `:116` `self.assertEqual(Policy.retrieve_rerank_margin, 0.20)`; `:117` `self.assertEqual(Policy.retrieve_rerank_floor, 0.30)` | PASS |
| C19 | Retry keeps first-pass ids in `[n]` order and appends new ids | `test_retry_pins_first_pack_and_appends_n` ok | `tests/test_t3_pack_union.py:133` - `self.assertEqual(ids[:3], ["keep-a", "keep-b", "keep-c"])`; `:134` `self.assertEqual(ids[3:], ["new-d", "new-e"])`; `:135` `self.assertEqual(ns, [1, 2, 3, 4, 5])` | PASS |
| C20 | Retry adds at most `retrieve_retry_add_cap=5` new ids | `test_retry_adds_at_most_five_new_ids` ok | `tests/test_t3_pack_union.py:153` - `self.assertEqual(Policy.retrieve_retry_add_cap, 5)`; `:154` `self.assertLessEqual(len(new_ids), 5)`; `:155` `self.assertEqual(len(new_ids), 5)` | PASS |
| C21 | After retry union, length ≤ `retrieve_pack_cap_after_retry=15` | `test_retry_union_caps_at_fifteen` ok | `tests/test_t3_pack_union.py:167` - `self.assertEqual(Policy.retrieve_pack_cap_after_retry, 15)`; `:168` `self.assertLessEqual(len(out["evidence_chunks"]), 15)`; `:169` `self.assertEqual(len(out["evidence_chunks"]), 15)` | PASS |
| C22 | No retry → Writer-facing pack length ≤ 10 | `test_first_pass_pack_at_most_ten` ok | `tests/test_t3_pack_union.py:180` - `self.assertLessEqual(len(out["evidence_chunks"]), 10)`; `:181` `self.assertEqual(len(out["evidence_chunks"]), 10)` | PASS |
| C23 | Retry floor 0.30 on new candidates only; none pass → first pack unchanged | `test_retry_floor_miss_keeps_first_pack` ok | `tests/test_t3_pack_union.py:193` - `self.assertEqual([row["chunk_id"] for row in out["evidence_chunks"]], ["keep-a", "keep-b"])`; `:197` `self.assertEqual([row["n"] for row in out["evidence_chunks"]], [1, 2])` | PASS |
| C24 | `yes` retry: `score_chunks` twice, second list is not the unioned pack | `test_yes_retry_rerank_called_twice_not_on_union` ok | `tests/test_t3_voyage.py:159` - `self.assertEqual(len(calls), 1)`; `:162` `self.assertEqual(len(calls), 2)`; `:165` `self.assertNotEqual(calls[1], union_ids)` | PASS |
| C25 | Retry hybrid `k=10`; Voyage scores that short list, not 40 and not keep-set ids | `test_retry_scores_short_list_not_keep_set` ok | `tests/test_t3_voyage.py:180` - `self.assertEqual(hybrid.k_values, [Policy.retrieve_retry_first_stage_k])`; `:181` `self.assertEqual(Policy.retrieve_retry_first_stage_k, 10)`; `:183` `self.assertEqual(len(scored[0]), 10)`; `:184` `self.assertNotEqual(len(scored[0]), 40)`; `:185` `self.assertTrue(set(_KEEP_IDS).isdisjoint(scored[0]))` | PASS |
| C26 | T3 `na`/`no`/`unknown` → one `score_chunks` call, table-driven over 3 | `test_na_no_unknown_rerank_once` ok | `tests/test_t3_voyage.py:200` - `self.assertEqual(len(calls), 1)`; `:218` `self.assertNotEqual(update.get("retry_counts", {}).get("1"), 1)`; `:219` `self.assertEqual(len(calls), 1)` | PASS |
| C27 | Writer Missing topics lists hole `task` with reason `gap`; system prompt includes `HOLE_RULE` | `test_writer_prompt_lists_gap_hole_tasks` ok | `tests/test_t3_writer_holes.py:33` - `self.assertIn(f"{_HOLE} (gap)", user)`; `:34` `self.assertIn(Policy.HOLE_RULE, _system_prompt())` | PASS |
| C28 | Writer `step_index` distinct: user prompt empty of retrieve-step eval feedback | `test_writer_step_eval_feedback_ignores_retrieve` ok | `tests/test_t3_writer_holes.py:65` - `self.assertNotIn(_RETRIEVE_FEEDBACK, user)`; `:66` `self.assertNotIn("59M", user)` | PASS |

## Level and sampling

Claims broader than their proofs (not Unproven: each still has a settling `file:line`):

- **C14** sits on `build_rerank_query`, not `RetrieveRunner.run`. First pass at HEAD still calls `build_rerank_query(task, feedback)` (`retrieve.py`); empty feedback → stripped task is what the helper test asserts. The named method body is unchanged in `c01e776..HEAD`; behaviour matches the plan's independent test (helper, not live Voyage).
- **C22** also cites AC 24 (extras beyond 10 only from a T3 `yes` retry). The proof only asserts first-pass length 10. No assertion that a >10 pack cannot come from another retry path (R2 foreign pin+add).
- **C5** "no retry" is implied by pass+hole+not-replan; unlike C4 it does not assert `retry_counts`.
- **C9/C10** stub `EvalResult.plan_inadequate=True` and assert graph routing; they do not prove the retrieve strategy emits that result for t1/t2a.
- **C16/C17/C11-checklist** are prompt-string locks, not LLM output.
- **C24** counts patched `score_chunks` across two manual `RetrieveRunner.run` calls, not a graph `yes` hop and not `VoyageAIRerank`. Matches the plan's fake-`score_chunks` independent test.
- **C26** infers a single Voyage call from first-pass `score_chunks` plus eval not incrementing retry (does not re-invoke retrieve after eval). Table covers all 3 of `na`/`no`/`unknown`.
- **C27** uses one pre-built `hole_tasks` row; it does not drive T3 `no` / `unknown` / exhausted-`yes` itself (those hole appends are C1/C8). It asserts the formatted `task (gap)` substring, not the "Missing topics" heading.
- **C1/C2** are table-driven over all 4 `likely_in_paper` values (`subTest`).

## Swept existing

| Row | Cited constraint | In code at HEAD? |
| --- | --- | --- |
| dependency failure | Voyage HTTP failure still packs ensemble order (AD-018); this slice does not change that fallback | Yes. `retrieve.py:452` `except Exception`; `:454` log `voyage rerank failed; packing ensemble order`; `:456` `strategy = "ensemble_order"`; `:460` `pack_hits(result_i.ranked, k=top_n)`. Fallback remains. `k` now follows `top_n` (first pass `retrieve_rerank_top_n`, retry `retrieve_retry_add_cap`) rather than a hardcoded first-pass cap. |

`n/a` swept rows (authorization, concurrency, data lifecycle, observability) are policy; nothing in the code for them to be wrong about.

## Gate

`uv run python -m unittest tests.test_t3_eval tests.test_t3_query tests.test_cut_reranked tests.test_t3_pack_union tests.test_t3_voyage tests.test_t3_writer_holes tests.test_internal_english -v` - 50 passed, 0 failed (29 named proofs all `ok`)
