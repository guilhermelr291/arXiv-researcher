# Chat messages trimming and summarization checks

Profile: light
Plan: `.specs/features/chat-messages-trimming-and-summarization/plan.md`

40 checks in 3 slices, 1 builder · 2 one-way doors · 0 open, of which 0 block

## Checks

### S1 - Compaction row and summarizer · ~40 KB · ~10k

**C1** - Lifespan startup creates the compaction table with `CREATE TABLE IF NOT EXISTS`, primary key `thread_id`, and the lifespan function source contains no `DROP` (CMP-01, AC 1–2)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_schema_is_create_only_and_lifespan_ensures_it`

**C2** - Two successful writes for `thread_id` `t-1` leave exactly 1 row, and the stored summary is the second text `NEW-SUMMARY` (CMP-01, AC 3, AC 7)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_second_write_keeps_one_row`

**C3** - The store accepts each of `running`, `ready`, `applied`, `failed`, and `discarded`, the DDL names those five, and status `paused` is rejected and not stored (CMP-01, AC 4)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_status_set_rejects_paused`

**C4** - The row does not become `running` when counted tokens are 48000, when the failed finish is 29 seconds old, when status is already `running` (watermark stays `wm-0`), or when status is `ready` (CMP-01, AC 5)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_job_start_refusals`

**C5** - The row becomes `running` and stores watermark `wm-1` when counted tokens are 48001, the prefix is 8000 tokens, and the row is absent, `applied`, `discarded`, or `failed` with a finish 30 seconds old; `state.messages` and `conversation_summary` stay unchanged, and a stored summary `OLD-SUMMARY` stays `OLD-SUMMARY` (CMP-01, AC 5–6)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_job_start_sets_running_without_touching_messages`

**C6** - Summarizer success on `thread_id` `t-1` sets status `ready`, summary `NEW-SUMMARY`, watermark `wm-2`, and error `""` (CMP-01, AC 7)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_success_overwrites_summary_and_clears_error`

**C7** - The ready row stores token count before 50000, estimated token count after 20000, summary token count 400, summarizer input token count 12000, and summarizer output token count 300 (CMP-01, AC 8)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_ready_row_stores_five_token_counts`

**C8** - The summarizer `ChatOpenAI` call passes `reasoning_effort` `medium` and `max_completion_tokens` 2500 (CMP-01, AC 9)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_summarizer_reasoning_effort_and_max_tokens`

**C9** - `with_structured_output` is called with field names `current_user_goal`, `decisions_made`, `constraints_and_preferences`, `important_entities_and_values`, `what_has_been_done`, and `open_items`, and the stored summary contains the headings `## Current user goal`, `## Decisions made (with the reason, when it matters)`, `## Stated constraints and preferences`, `## Important entities and values`, `## What has already been done`, and `## Open items and unanswered questions` in that order (CMP-01, AC 10)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_structured_output_fields_and_headings`

**C10** - The summarizer input contains the applied summary `PRIOR-GOAL`, the message `BEFORE-MARK`, and the watermark message `AT-MARK`, and omits the later message `AFTER-MARK` (CMP-01, AC 11)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_summarizer_input_is_prefix_through_watermark`

**C11** - When the summarizer raises `boom`, status is `failed`, the stored error contains `boom`, and the summary stays `OLD-SUMMARY` (CMP-01, AC 12)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_summarizer_exception_sets_failed_and_keeps_summary`

**C12** - When the summarizer has not returned 90 seconds after the row entered `running`, status is `failed` and the summary stays `OLD-SUMMARY` (CMP-01, AC 12)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_summarizer_timeout_at_90_seconds_sets_failed`

**C13** - A compaction pass that starts a job and a pass that reaches `ready` each leave transcript insert, update, and delete counts at 0 (CMP-01, AC 13)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_compaction_does_not_write_transcript_items`

**C14** - The summarizer registry spec is named `summarizer`, its model is `gpt-5.6-luna`, its tools are `()`, that name is absent from `PLAN_AGENTS`, and `planner_prompt_abilities()` does not contain `summarizer` (CMP-01, AC 14)
Proof: `uv run python -m unittest tests.test_compaction_store -k test_summarizer_model_and_exclusion_from_plan_agents`

### S2 - Apply the cut and read it from the planner · ~115 KB · ~29k

**C15** - When status is `ready`, counted tokens are 48001, watermark `m2` is in `state.messages`, and the row base watermark equals the state's applied watermark, the cut removes `m1` and `m2` and sets `conversation_summary` to `STORED-SUMMARY` (CMP-02, AC 1)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_ready_over_48000_removes_through_watermark`

**C16** - After that cut, the row status is `applied` and the state's applied watermark equals `m2` (CMP-02, AC 2)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_applied_status_and_state_watermark_after_cut`

**C17** - Message `m3`, appended after watermark `m2`, is still in `state.messages` after the cut (CMP-02, AC 3)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_message_after_watermark_remains`

**C18** - When status is `ready` and counted tokens are 0 or 48000, message ids are unchanged and status stays `ready` (CMP-02, AC 4)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_ready_at_or_under_48000_does_not_remove`

**C19** - When watermark `missing` is not in `state.messages`, status becomes `discarded`, message ids are unchanged, and `conversation_summary` stays `KEEP` (CMP-02, AC 5)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_missing_watermark_is_discarded`

**C20** - When the row base watermark is `old-mark` and the state's applied watermark is `other-mark`, status becomes `discarded`, message ids are unchanged, and `conversation_summary` stays `KEEP` (CMP-02, AC 5)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_base_watermark_mismatch_is_discarded`

**C21** - When status is `ready`, counted tokens are 48001, and the state's applied watermark already equals watermark `m2`, status becomes `applied` and message `m1` is still present (CMP-02, AC 6)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_already_applied_watermark_does_not_remove`

**C22** - A non-resume run's update stream includes `compact` before `gate` (CMP-02, AC 7)
Proof: `uv run python -m unittest tests.test_compaction_graph -k test_fresh_run_visits_compact_before_gate`

**C23** - `POST /agent` with `forwardedProps.resume` true calls `astream` with input `None`, and that resume stream does not include `compact` (CMP-02, AC 8)
Proof: `uv run python -m unittest tests.test_agent_route -k test_resume_calls_astream_with_none`
Proof: `uv run python -m unittest tests.test_compaction_graph -k test_resume_astream_none_skips_compact`

**C24** - When `conversation_summary` is `GOAL-42` and `state.messages` has 8 exchanges, the planner prompt contains `<conversation_summary>` after the instruction prefix and before `Query:`, the tag's text includes `GOAL-42`, and the prompt includes `user-1` (CMP-02, AC 9, AC 11)
Proof: `uv run python -m unittest tests.test_history_prompts -k test_planner_summary_before_query_and_all_messages`

**C25** - The planner prompt does not contain `<conversation_summary>` when `conversation_summary` is `""` and when the key is absent (CMP-02, AC 10)
Proof: `uv run python -m unittest tests.test_history_prompts -k test_planner_omits_summary_tag_when_empty`

**C26** - With 8 messages in `state.messages` and `conversation_summary` `GOAL-42`, the gate human prompt includes the last 6 message contents, omits the first 2, and does not contain `<conversation_summary>` or `GOAL-42` (CMP-02, AC 12)
Proof: `uv run python -m unittest tests.test_history_prompts -k test_gate_last_six_messages_omit_summary`

**C27** - With 4 exchanges in `state.messages` and `conversation_summary` `GOAL-42`, the writer user prompt includes the last 2 exchanges, omits the first 2, and does not contain `<conversation_summary>` or `GOAL-42` (CMP-02, AC 13)
Proof: `uv run python -m unittest tests.test_history_prompts -k test_writer_two_exchanges_omit_summary`

**C28** - `replan_remaining` with `conversation_summary` `GOAL-42` does not contain `<conversation_summary>` or `GOAL-42` (CMP-02, AC 14)
Proof: `uv run python -m unittest tests.test_history_prompts -k test_replan_remaining_omits_summary`

**C29** - The kept suffix totals 16000 tokens, its first message is a user message, and the watermark is the id of the message immediately before that suffix (CMP-02, AC 15)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_watermark_keeps_16000_tokens_from_a_user_message`

**C30** - When the tail that first reaches 16000 tokens starts on an assistant message, the kept suffix starts on the preceding user message and its token total is greater than 16000 (CMP-02, AC 16)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_watermark_extends_suffix_to_a_user_message`

**C31** - When the prefix before the only user boundary is 7999 tokens, or the list has no user message, the row does not become `running` and the message count is unchanged (CMP-02, AC 17)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_short_prefix_or_no_user_boundary_does_not_cut`

**C32** - Token counting uses tiktoken encoding `o200k_base` over the applied summary plus `state.messages`, omits system-message text and the papers list, and `Policy.chunk_encoding` stays `cl100k_base` (CMP-02, AC 18)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_token_count_uses_o200k_base_and_omits_system_and_papers`

**C33** - A message that already stores token count 100 contributes 100, including when `o200k_base` on its text is a different count (CMP-02, AC 19)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_stored_message_token_count_is_reused`

**C34** - The cut emits `RemoveMessage` for `m1` and for `m2`, and `add_messages` then drops `m1` and `m2` and keeps `m3` (CMP-02, AC 21)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_remove_message_ids_applied_by_add_messages`

**C35** - `ResearchGraph` with no compaction store includes `gate` in the update stream, leaves message ids unchanged, and writes no compaction row; `scripts/retrieve_writer_recall.py` calls `ResearchGraph` with `checkpointer=None` and passes no compaction store (CMP-02, AC 20)
Proof: `uv run python -m unittest tests.test_compaction_graph -k test_missing_store_enters_gate`
Proof: `uv run python -m unittest tests.test_compaction_graph -k test_recall_script_has_no_compaction_store`

**C36** - `initial_graph_state("q")` omits `conversation_summary` and the applied watermark, and a follow-up input leaves a checkpointed summary `KEEP` and watermark `m2` in place (door 2)
Proof: `uv run python -m unittest tests.test_research_graph -k test_initial_state_omits_summary_and_watermark`
Proof: `uv run python -m unittest tests.test_compaction_graph -k test_follow_up_input_keeps_checkpoint_summary`

### S3 - A failed job stays off the chat · ~8 KB · ~2k

**C37** - A checkpoint state that omits `conversation_summary` and the applied watermark, with no compaction row, leaves message ids unchanged and does not raise (Impact, stored data)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_omitted_checkpoint_fields_mean_no_summary`

**C38** - A `running` row whose start is 91 seconds old becomes `failed`; a start 90 seconds old stays `running`; 29 seconds after that failure time the row does not become `running`; 30 seconds after that failure time it may become `running` (CMP-03, AC 1)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_stale_running_fails_and_cooldown_is_30_seconds`

**C39** - Compact returns while the row is still `running` and `outcome` is `pending`; after the summarizer then resolves, status is `ready` and `outcome` is still `pending` (CMP-03, AC 2–3)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_summarizer_ready_after_turn_returns`

**C40** - After the turn has returned, a summarizer that raises leaves status `failed`, summary `OLD-SUMMARY`, and `outcome` `pending` (CMP-03, AC 2–3)
Proof: `uv run python -m unittest tests.test_compaction_apply -k test_summarizer_failure_after_turn_keeps_outcome_pending`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| compaction status (5) | C3, table-driven over all 5 | - |
| job-start refusal (6) | 48000 C4 · prefix 7999 C31 · failed 29s C4 · running C4 · ready C4 · no user boundary C31 | - |
| may-start row (4) | C5, table-driven over all 4 | - |
| summarizer fields (6) | C9, table-driven over all 6 | - |
| summary headings (6) | C9, table-driven over all 6 | - |
| apply outcome (4) | cut C15 · missing watermark C19 · base mismatch C20 · already applied C21 | - |
| token hold (2) | 0 C18 · 48000 C18 | - |
| prompt consumer (4) | planner C24 · gate C26 · writer C27 · replan C28 | - |
| planner summary (3) | non-empty C24 · empty C25 · key absent C25 | - |
| watermark boundary (4) | 16000 on user C29 · extend C30 · prefix 7999 C31 · no user C31 | - |
| token input (4) | C32, table-driven over all 4 | - |
| encoding (2) | o200k_base C32 · cl100k_base C32 | - |
| startup config: compaction store (2 assemblies) | FastAPI lifespan C1 · no-store ResearchGraph C35 | - |
| late job result (2) | ready C39 · failed C40 | - |
| stale running (4) | C38, table-driven over all 4 | - |
| door 1 summary text (2) | overwrite C6 · keep previous C11 | - |
| door 2 state fields (3) | summary on cut C15 · watermark on cut C16 · omitted from follow-up input C36 | - |
| removed ids (2) | m1 C34 · m2 C34 | - |

- `POST /agent` keeps its current statuses. C23 crosses resume: `astream` input `None`, and the resume stream has no `compact` update. This feature adds no HTTP status.
- No other check claims more than the single case its proof exercises.

## Swept

- validation: C3, C4, C18, C31
- failure modes: C11, C12, C19, C20, C40
- idempotency: C2, C21
- authorization: existing - CORS `WEB_ORIGIN` on `POST /agent`; no auth in v1
- concurrency: C5, C38, C39
- data lifecycle: C1, C2, C13, C37
- dependency failure: C11, C40
- state transitions: C5, C6, C15, C16, C19, C21, C38
- observability: C7, C11

## Handoff

Intended split, with the arithmetic, written before any code. Bytes are `Length` of the files each slice touches; tokens are bytes / 4.

- S1 existing files `main.py`, `registry.py`, `factory.py`, `policy.py`, `repo/transcript.py`, `tests/test_transcript_store.py` = 22179 bytes, plus about 18 KB of new store, runner, and tests → ~10k
- S2 existing files `build.py`, `state.py`, `research_graph.py`, `planner.py`, `gate.py`, `writer.py`, `history.py`, `replan.py`, `routes.py`, `scripts/retrieve_writer_recall.py`, `test_history_prompts.py`, `test_research_graph.py`, `test_agent_route.py`, `test_gate_node.py` = 94718 bytes, plus about 20 KB of new compact node and tests → ~29k
- S3 adds about 8 KB of tests on the S1 store and S2 compact path → ~2k
- S1–S3 ≈ 41k, under the 150k budget, all on the compaction path → one builder, no handoff
