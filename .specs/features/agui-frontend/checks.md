# AG-UI transport + Next.js research desk checks

Profile: light
Plan: `.specs/features/agui-frontend/plan.md`

## Intent

73 checks in 6 slices · 7 one-way doors · 0 open

## Checks

Grouped by the spec's slices; numbering runs across the whole feature.

### S1 - The thread remembers · 8 files · 65 KB · ~16k

**C1** - When `finalize` runs with `outcome="done"`, `messages` gains one `AIMessage` whose `content` equals `writer_markdown` and whose `id` equals state `writer_message_id` (AGUI-01, AC 1)
Proof: `uv run python -m unittest tests.test_finalize -k test_done_appends_aimessage_with_writer_id`

**C2** - When `finalize` runs with `outcome` in `refused`, `insufficient`, `error`, `messages` gains one `AIMessage` whose `content` is the terminal reason and whose `response_metadata.outcome` equals that outcome, table-driven over all 3 (AGUI-01, AC 2)
Proof: `uv run python -m unittest tests.test_finalize -k test_non_done_appends_aimessage_with_reason`

**C3** - An `AIMessage` appended by `finalize` has `response_metadata` keys `outcome`, `gate`, `plan`, `steps`, `citations`; each `plan` item has `index`, `agent`, `task`, `status`, `feedback`; `steps` has `count` and `elapsed_ms` (AGUI-01, AC 3)
Proof: `uv run python -m unittest tests.test_finalize -k test_aimessage_metadata_key_set`
Proof: `uv run python -m unittest tests.test_finalize -k test_plan_item_projection_fields`

**C4** - Before the first `answer_delta`, the Writer emits custom event `answer_start` with a uuid `message_id` and returns that id as `writer_message_id` (AGUI-01, AC 4)
Proof: `uv run python -m unittest tests.test_writer_stream -k test_answer_start_before_first_delta`

**C5** - After a second run on the same `thread_id`, checkpoint `messages` contain the first turn's `HumanMessage`-shaped dict and `AIMessage` before the second turn's pair (AGUI-01, AC 5)
Proof: `uv run python -m unittest tests.test_thread_messages -k test_second_run_keeps_first_turn`

**C6** - Gate and planner human payloads contain the last `Policy.history_window_exchanges=6` exchanges of `messages` in order and omit exchanges 7 and 8 of an 8-exchange fixture, table-driven over both agents (AGUI-01, AC 6)
Proof: `uv run python -m unittest tests.test_history_prompts -k test_gate_and_planner_window_is_six`

**C7** - The Writer prompt contains the last `Policy.writer_history_exchanges=2` exchanges and the numbered evidence, and omits older exchanges of a 4-exchange fixture (AGUI-01, AC 7)
Proof: `uv run python -m unittest tests.test_history_prompts -k test_writer_window_is_two_plus_evidence`

**C8** - On a thread with admitted `papers`, the planner prompt lists each paper's arxiv id and title and states that a plan may omit `search` for an already admitted paper (AGUI-01, AC 8)
Proof: `uv run python -m unittest tests.test_history_prompts -k test_planner_lists_admitted_papers_and_omit_search`

**C9** - A `writer` step with empty `evidence_chunks` and at least one prior `AIMessage` with `citations` builds evidence from those citations renumbered from `[1]` in message order, deduplicated by `chunk_id` (AGUI-01, AC 9)
Proof: `uv run python -m unittest tests.test_writer_thread_evidence -k test_empty_chunks_renumber_prior_citations`

**C10** - A `writer` step with empty `evidence_chunks` and no prior `AIMessage` citations sets `outcome="insufficient"` and does not call the Writer model (AGUI-01, AC 10)
Proof: `uv run python -m unittest tests.test_writer_thread_evidence -k test_empty_chunks_no_citations_insufficient`

**C11** - Writer `citations` are numbered per turn starting at 1 and each item has `n`, `chunk_id`, `arxiv_id`, `title`, `year`, `url`, `excerpt`, table-driven over all 7 fields (AGUI-01, AC 11)
Proof: `uv run python -m unittest tests.test_writer_stream -k test_citations_per_turn_fields`

**C12** - An invoke with new input on a thread whose checkpoint `next` is non-empty starts from `START` and the previously pending node does not run (AGUI-01, AC 12)
Proof: `uv run python -m unittest tests.test_pending_next -k test_new_input_discards_pending_and_starts`

### S2 - One AG-UI run over SSE · 8 files · 75 KB · ~19k

**C13** - `POST /agent` with a valid `RunAgentInput` and one `UserMessage` responds `200` `text/event-stream` and the first frame is `RUN_STARTED` with the request's `threadId` and `runId` (AGUI-02, AC 13)
Proof: `uv run python -m unittest tests.test_agent_route -k test_valid_run_starts_with_run_started`

**C14** - `POST /agent` with a body that is not a valid `RunAgentInput` responds `422` with the validation detail (AGUI-02, AC 14)
Proof: `uv run python -m unittest tests.test_agent_route -k test_invalid_body_is_422`

**C15** - `POST /agent` with empty `messages` and `forwardedProps.resume` not `true` responds `400` `{"detail":"one user message or resume is required"}` (AGUI-02, AC 15)
Proof: `uv run python -m unittest tests.test_agent_route -k test_empty_messages_without_resume_is_400`

**C16** - `POST /agent` with `forwardedProps.resume` `true` and checkpoint `next` empty responds `409` `{"detail":"nothing to resume"}` (AGUI-02, AC 16)
Proof: `uv run python -m unittest tests.test_agent_route -k test_resume_idle_is_409`

**C17** - `POST /agent` with `forwardedProps.resume` `true` and `next` non-empty streams the graph from the checkpoint with input `None` on that `thread_id` (AGUI-02, AC 17)
Proof: `uv run python -m unittest tests.test_agent_route -k test_resume_calls_astream_with_none`

**C18** - The adapter consumes the graph with `graph.astream(input, config, stream_mode=["custom","updates"])` and its source contains no `astream_events` (AGUI-02, AC 18)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_consume_path_is_astream_custom_updates`

**C19** - Each node task start emits `STEP_STARTED` with `step_name` equal to the node name, table-driven over all 8 of `gate`, `planner`, `dispatch`, `search`, `execute`, `evaluate`, `replan`, `finalize`; when the node is `search` or `execute`, `metadata` is `{step_index, agent, task}` (AGUI-02, AC 19)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_step_started_for_every_node`
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_search_execute_step_started_metadata`

**C20** - Each node task end emits `STEP_FINISHED` with the same `step_name`; for `search` and `execute`, `metadata.query_used` equals the node's `step_end` `query_used` (AGUI-02, AC 20)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_step_finished_query_used_from_step_end`

**C21** - Two `search` tasks in one `Send` wave emit two `STEP_STARTED` events whose `metadata.step_index` differ (AGUI-02, AC 21)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_parallel_search_step_indexes_differ`

**C22** - A gate custom event becomes `ACTIVITY_SNAPSHOT` `activity_type="GATE"` with `content` `{in_domain, language, reason}` (AGUI-02, AC 22)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_gate_event_is_activity_snapshot`

**C23** - A planner `plan` event becomes `ACTIVITY_SNAPSHOT` `activity_type="PLAN"` with `content.items[]` each `{index, agent, task, status:"pending", feedback:null}` (AGUI-02, AC 23)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_plan_event_is_pending_snapshot`

**C24** - An `updates` chunk that changes the projected plan emits `ACTIVITY_DELTA` `activity_type="PLAN"` with a JSON Patch limited to the changed paths, on the same `message_id` as the snapshot (AGUI-02, AC 24)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_plan_delta_patch_same_message_id`

**C25** - An `eval` custom event sets the projected plan item at its `step_index` to `feedback` equal to the English `feedback` and `status` in `passed`, `retry`, `replan`, table-driven over all 3 (AGUI-02, AC 25)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_eval_updates_plan_item_status`

**C26** - An `answer_start` custom event becomes `TEXT_MESSAGE_START` with `message_id` equal to the event id and `role="assistant"` (AGUI-02, AC 26)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_answer_start_is_text_message_start`

**C27** - An `answer_delta` custom event becomes `TEXT_MESSAGE_CONTENT` with `delta` equal to its `text`, on that `message_id` (AGUI-02, AC 27)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_answer_delta_is_text_message_content`

**C28** - A `citations` custom event emits `TEXT_MESSAGE_END` then `ACTIVITY_SNAPSHOT` `activity_type="SOURCES"` with `content.items[]` `{n, arxiv_id, title, year, url, excerpt, chunk_id}` in `n` order (AGUI-02, AC 28)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_citations_end_then_sources`

**C29** - When `finalize` finishes, the stream emits `RUN_FINISHED` with `result` `{outcome, reason}` and `reason` is `null` when `outcome` is `done` (AGUI-02, AC 29)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_run_finished_reason_null_when_done`

**C30** - When the graph iterator raises, the stream emits `RUN_ERROR` with `message` equal to `str(exc)` and then closes (AGUI-02, AC 30)
Proof: `uv run python -m unittest tests.test_agent_route -k test_iterator_raise_is_run_error`

**C31** - When the run exceeds `Settings.research_timeout_seconds`, the stream emits `RUN_FINISHED` with `result` `{outcome:"insufficient", reason:"timeout"}` and then closes (AGUI-02, AC 31)
Proof: `uv run python -m unittest tests.test_agent_route -k test_timeout_is_run_finished_insufficient`

**C32** - Every SSE frame is encoded with `ag_ui.encoder.EventEncoder`; the `POST /agent` response carries `Cache-Control: no-cache` and `X-Accel-Buffering: no` (AGUI-02, AC 32)
Proof: `uv run python -m unittest tests.test_agent_route -k test_frames_use_event_encoder`
Proof: `uv run python -m unittest tests.test_agent_route -k test_agent_stream_headers`

**C33** - A request with `Origin` equal to `WEB_ORIGIN` (default `http://localhost:3000`) receives `Access-Control-Allow-Origin` for that origin; `OPTIONS /agent` responds `200` (AGUI-02, AC 33)
Proof: `uv run python -m unittest tests.test_agent_route -k test_cors_allows_web_origin`
Proof: `uv run python -m unittest tests.test_agent_route -k test_options_agent_is_200`

**C34** - `POST /research` is not registered; `GET /health` remains registered (AGUI-02, AC 34)
Proof: `uv run python -m unittest tests.test_agent_route -k test_research_route_absent_health_present`

### S3 - Replay from the checkpoint · 3 files · 20 KB · ~5k

**C35** - `GET /threads/{thread_id}` on a checkpoint with at least one message responds `200` `{threadId, messages, status}` (AGUI-03, AC 35)
Proof: `uv run python -m unittest tests.test_threads_route -k test_get_thread_200_shape`

**C36** - `GET /threads/{thread_id}` on a checkpoint with no messages responds `404` `{"detail":"thread not found"}` (AGUI-03, AC 36)
Proof: `uv run python -m unittest tests.test_threads_route -k test_empty_thread_is_404`

**C37** - Replay maps each user dict or `HumanMessage` to a `UserMessage` with the same `id` and `content` (AGUI-03, AC 37)
Proof: `uv run python -m unittest tests.test_threads_route -k test_human_maps_to_user_message`

**C38** - Replay of an `AIMessage` with `response_metadata.outcome="done"` emits, in order, `ActivityMessage` `GATE`, `ActivityMessage` `PLAN`, `ActivityMessage` `STEPS` `{count, elapsed_ms}`, `AssistantMessage` with `id` equal to the `AIMessage.id` and `content` equal to its content, `ActivityMessage` `SOURCES`, table-driven over those 5 (AGUI-03, AC 38)
Proof: `uv run python -m unittest tests.test_threads_route -k test_done_replay_order`

**C39** - Replay of an `AIMessage` with `response_metadata.outcome` in `refused`, `insufficient`, `error` emits `ActivityMessage` `GATE` when gate is present, then `ActivityMessage` `OUTCOME` `{outcome, reason}`, and emits no `AssistantMessage`, table-driven over all 3 (AGUI-03, AC 39)
Proof: `uv run python -m unittest tests.test_threads_route -k test_non_done_replay_is_outcome_not_assistant`

**C40** - Replay `status` is `"interrupted"` when snapshot `next` is non-empty and `"idle"` otherwise (AGUI-03, AC 40)
Proof: `uv run python -m unittest tests.test_threads_route -k test_status_interrupted_vs_idle`

**C41** - Replay `PLAN` and `SOURCES` activity contents are the return value of the same `project_turn` function the live adapter uses (AGUI-03, AC 41)
Proof: `uv run python -m unittest tests.test_threads_route -k test_replay_uses_project_turn`

### S4 - Screen `/` and `/c/{threadId}` lifecycle · 8 files · 35 KB · ~9k

**C42** - Opening `/` renders only the centred input plus one app-description line and does not call `fetch` (AGUI-04, AC 42)
Proof: `npm --prefix web exec -- vitest run -t "home renders input and description without fetch"`

**C43** - The first send on `/` generates a uuid v4 `threadId`, `POST`s `/agent`, and calls `history.replaceState` with `/c/{threadId}` (AGUI-04, AC 43)
Proof: `npm --prefix web exec -- vitest run -t "first send posts agent and replaceState"`

**C44** - After the first send in the same tab, the client does not call `GET /threads/{threadId}` (AGUI-04, AC 44)
Proof: `npm --prefix web exec -- vitest run -t "same-tab first send skips get threads"`

**C45** - Opening `/c/{threadId}` directly calls `GET /threads/{threadId}` and renders the returned messages before the input is enabled (AGUI-04, AC 45)
Proof: `npm --prefix web exec -- vitest run -t "direct thread load waits for replay"`

**C46** - `GET /threads/{threadId}` status `404` navigates the client to `/` (AGUI-04, AC 46)
Proof: `npm --prefix web exec -- vitest run -t "thread 404 navigates home"`

**C47** - The first user message of a thread upserts `{threadId, title, updatedAt}` in `localStorage` with `title` equal to that message's first 80 characters (AGUI-04, AC 47)
Proof: `npm --prefix web exec -- vitest run -t "recents upsert title eighty chars"`

**C48** - While a run streams, the input stays enabled and Stop aborts the fetch via `AbortController.abort` (AGUI-04, AC 48)
Proof: `npm --prefix web exec -- vitest run -t "stop aborts fetch and input stays enabled"`

**C49** - A stream that ends without `RUN_FINISHED` or `RUN_ERROR` calls `GET /threads/{threadId}` and re-renders from that body (AGUI-04, AC 49)
Proof: `npm --prefix web exec -- vitest run -t "dropped stream refetches thread"`

**C50** - After that re-render, `status` `"interrupted"` starts one automatic resume run after 1000 ms; if that stream also ends without `RUN_FINISHED`, a manual Resume control is shown (AGUI-04, AC 50)
Proof: `npm --prefix web exec -- vitest run -t "interrupted auto-resumes once then shows resume"`

**C51** - While `status` is `"interrupted"`, a strip using `--warn` sits above the input with the Resume action and typing stays enabled (AGUI-04, AC 51)
Proof: `npm --prefix web exec -- vitest run -t "interrupted strip uses warn and does not block input"`

**C52** - `RUN_FINISHED` with `result.outcome` in `refused`, `insufficient` renders the reason as a marginalia line and no assistant text, table-driven over both (AGUI-04, AC 52)
Proof: `npm --prefix web exec -- vitest run -t "refused and insufficient render reason only"`

**C53** - `RUN_ERROR` renders `message` as a marginalia line using `--warn` (AGUI-04, AC 53)
Proof: `npm --prefix web exec -- vitest run -t "run error renders warn marginalia"`

**C54** - A normal run sends `RunAgentInput.messages` with exactly one `UserMessage`; a resume sends an empty `messages` array and `forwardedProps.resume=true` (AGUI-04, AC 54)
Proof: `npm --prefix web exec -- vitest run -t "normal run one user message resume empty"`

### S5 - Reading column, marginalia and citations · 10 files · 45 KB · ~11k

**C55** - While a run streams, StepRail shows the current node name in mono using `--accent` and previous nodes as dots using `--ok` (AGUI-05, AC 55)
Proof: `npm --prefix web exec -- vitest run -t "live step rail current accent previous ok"`

**C56** - On `RUN_FINISHED`, StepRail collapses to one line `"{count} steps · {seconds}s"` that expands to the full list on click (AGUI-05, AC 56)
Proof: `npm --prefix web exec -- vitest run -t "finished step rail collapses to count and seconds"`

**C57** - When a `search` step finishes, its rail entry shows `metadata.query_used` (AGUI-05, AC 57)
Proof: `npm --prefix web exec -- vitest run -t "search rail shows query used"`

**C58** - `GATE` renders as a single marginalia line with verdict and reason, not a card (AGUI-05, AC 58)
Proof: `npm --prefix web exec -- vitest run -t "gate is one marginalia line"`

**C59** - While streaming, the `PLAN` block is a numbered list with per-item status and applies `ACTIVITY_DELTA` without remounting the list; on `RUN_FINISHED` it collapses to one line (AGUI-05, AC 59)
Proof: `npm --prefix web exec -- vitest run -t "plan list survives delta then collapses"`

**C60** - For each `SOURCES` item, `[n]` in assistant markdown renders as a `<button>` with `aria-label` `"Source n"`; `[text](url)` stays an `<a>` (AGUI-05, AC 60)
Proof: `npm --prefix web exec -- vitest run -t "matching n is source button links stay links"`

**C61** - `[n]` with no matching `SOURCES` item renders as plain text, not a button (AGUI-05, AC 61)
Proof: `npm --prefix web exec -- vitest run -t "unknown n is plain text"`

**C62** - Hovering a citation button for 150 ms or focusing it opens a `--surface` popover with title, `arXiv:{id} · {year}` and a 2–3 line excerpt; the popover stays 300 ms after pointer leave (AGUI-05, AC 62)
Proof: `npm --prefix web exec -- vitest run -t "citation popover delay 150 stay 300"`

**C63** - Clicking a citation button opens the source panel from the right over the sidebar with the full excerpt and url, and the reading column width is unchanged (AGUI-05, AC 63)
Proof: `npm --prefix web exec -- vitest run -t "citation click opens panel over sidebar"`

**C64** - The client renders no sources list after the assistant text (AGUI-05, AC 64)
Proof: `npm --prefix web exec -- vitest run -t "no sources list after assistant"`

**C65** - The user message is full-width with a 2 px `--accent` left rule and 16 px inset; the assistant text has no container, border or background (AGUI-05, AC 65)
Proof: `npm --prefix web exec -- vitest run -t "user rule two px accent assistant unboxed"`

**C66** - The reading column uses a serif at 17 px / 1.65 with max-width 68ch; UI copy uses Inter 13–15 px; node names, ids and timings use mono 12 px (AGUI-05, AC 66)
Proof: `npm --prefix web exec -- vitest run -t "type tokens serif 17 ui inter mono 12"`

**C67** - Every colour in components comes from `lib/tokens.css` light and dark custom properties; component files contain no hex colour literals (AGUI-05, AC 67)
Proof: `npm --prefix web exec -- vitest run -t "tokens css has light and dark sets"`
Proof: `npm --prefix web exec -- vitest run -t "components contain no hex colour literals"`

**C68** - When `prefers-reduced-motion: reduce` is set, transitions and the streaming cursor are disabled (AGUI-05, AC 68)
Proof: `npm --prefix web exec -- vitest run -t "reduced motion disables transitions and cursor"`

**C69** - The client does not render CSS gradients, robot avatars, chat bubbles, skeleton shimmer or a generic spinner (AGUI-05, AC 69)
Proof: `npm --prefix web exec -- vitest run -t "no gradient avatar bubble shimmer spinner"`

### S6 - Chainlit and the old transport leave · 5 files · 20 KB · ~5k

**C70** - The repository does not contain `src/plan_based_researcher/ui/`, `src/plan_based_researcher/api/sse.py`, `src/plan_based_researcher/api/stream_dispatcher.py`, or `src/plan_based_researcher/api/executor.py`, table-driven over all 4 (AGUI-06, AC 70)
Proof: `uv run python -m unittest tests.test_agui_removal -k test_old_transport_paths_absent`

**C71** - `pyproject.toml` has no `chainlit` dependency and lists `ag-ui-protocol` (AGUI-06, AC 71)
Proof: `uv run python -m unittest tests.test_agui_removal -k test_pyproject_drops_chainlit_adds_ag_ui`

**C72** - No test module imports the removed paths, and `unittest discover -s tests` reports at least 190 cases (the count at checks authoring) (AGUI-06, AC 72)
Proof: `uv run python -m unittest tests.test_agui_removal -k test_no_test_module_imports_removed_paths`
Proof: `uv run python -m unittest tests.test_agui_removal -k test_discover_count_not_below_190`

**C73** - `AGENTS.md` names the `/agent` and `/threads` routes, the `web/` commands, and the revised text of invariants 1, 6, 8 and 9, table-driven over those 4 invariants (AGUI-06, AC 73)
Proof: `uv run python -m unittest tests.test_agui_docs -k test_agents_md_agent_threads_web_invariants`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `POST /agent` statuses (4) | 200 C13 · 400 C15 · 409 C16 · 422 C14 | - |
| `OPTIONS /agent` statuses (1) | 200 C33 | - |
| `GET /threads/{thread_id}` statuses (2) | 200 C35 · 404 C36 | - |
| Landing doors (7) | wire C13 · messages C1 · history prompts C6 · astream C18 · `ag-ui-protocol` C71 · `web/` C42 · thread grounding C9 | - |
| Relations entities (5) | THREAD C5 · CHECKPOINT C5 · MESSAGE C1 · TURN_PROJECTION C3 · CITATION C11 | - |
| terminal outcomes (4) | `done` C1 · `refused` C2 · `insufficient` C2 · `error` C2 | - |
| Writer empty-evidence (2) | prior citations C9 · none C10 | - |
| graph nodes `STEP_STARTED` (8) | C19, table-driven over all 8 | - |
| `search`/`execute` start metadata (2) | `search` C19 · `execute` C19 | - |
| Send search `STEP_STARTED` (2) | first C21 · second C21 | - |
| eval plan statuses (3) | C25, table-driven over all 3 | - |
| live AG-UI event kinds (12) | `RUN_STARTED` C13 · `STEP_STARTED` C19 · `STEP_FINISHED` C20 · GATE snapshot C22 · PLAN snapshot C23 · PLAN delta C24 · `TEXT_MESSAGE_START` C26 · `TEXT_MESSAGE_CONTENT` C27 · `TEXT_MESSAGE_END` C28 · SOURCES C28 · `RUN_FINISHED` C29 · `RUN_ERROR` C30 | - |
| replay activity types (5) | GATE C38 · PLAN C38 · STEPS C38 · SOURCES C38 · OUTCOME C39 | - |
| replay done sequence (5) | C38, table-driven over all 5 | - |
| thread `status` (2) | `idle` C40 · `interrupted` C40 | - |
| citation fields (7) | C11, table-driven over all 7 | - |
| `response_metadata` keys (5) | C3, table-driven over all 5 | - |
| plan item projection fields (5) | C3, table-driven over all 5 | - |
| SOURCES item fields (7) | C28, table-driven over all 7 | - |
| Policy history windows (2) | `history_window_exchanges=6` C6 · `writer_history_exchanges=2` C7 | - |
| `RunAgentInput` send shapes (2) | one `UserMessage` C54 · empty+resume C54 | - |
| `RUN_FINISHED` non-done UI (2) | `refused` C52 · `insufficient` C52 | - |
| removed transport paths (4) | C70, table-driven over all 4 | - |
| AGENTS.md invariants revised (4) | C73, table-driven over all 4 | - |
| startup config: CORS `WEB_ORIGIN` (1 assembly) | shared CORS install used by `create_app` and the `/agent` TestClient C33 | - |
| `GET /health` remains registered (1) | C34 | - |

- Claims naming a status code, route or response shape: C13, C14, C15, C16, C17, C30, C31, C32, C33, C34, C35, C36 - each has a proof that crosses the HTTP boundary
- No other check claims more than the single case its proof exercises
- C19's table must keep all 8 node names; a missing `dispatch` start would still look like a live run
- C28 asserts `TEXT_MESSAGE_END` before `SOURCES`, not either event alone
- C72 pins discover at 190, the unittest count on 2026-09-17 before this feature

## Swept

- validation: C14, C15
- failure modes: C10, C30, C31, C49, C53
- idempotency: C47
- authorization: n/a - v1 has no auth (plan Out of scope)
- concurrency: n/a - concurrent runs on one thread are out of scope (plan)
- data lifecycle: C37 - pre-feature checkpoints with user dicts only map to `UserMessage`s; no migration
- dependency failure: C30, C31
- state transitions: C1, C2, C12, C40
- observability: C13, C19, C22, C29, C73

## Handoff

Intended split, with the arithmetic, written before any code:

- S1 ~16k + S2 ~19k + S3 ~5k + S4 ~9k + S5 ~11k + S6 ~5k ≈ 65k tokens, under the 150k budget — one builder
- Surface changes from Python (`POST /agent`, `GET /threads/{thread_id}`) to `web/` at S4, but the running estimate still fits; do not split mid-outcome
