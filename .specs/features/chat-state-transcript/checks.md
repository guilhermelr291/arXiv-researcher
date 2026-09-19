# Chat state transcript checks

Profile: light
Plan: `.specs/features/chat-state-transcript/plan.md`

## Intent

33 checks in 4 slices · 9 one-way doors · 0 open

## Checks

Grouped by the spec's slices; numbering runs across the whole feature.

### S1 - Transcript store and schema · 5 files · 25 KB · ~6k

**C1** - The transcript schema SQL contains `CREATE TABLE IF NOT EXISTS threads` and `CREATE TABLE IF NOT EXISTS transcript_items` and does not contain `DROP`; FastAPI `lifespan` source calls that schema helper (TRN-01, AC 1)
Proof: `uv run python -m unittest tests.test_transcript_store -k test_schema_sql_create_if_not_exists_without_drop`
Proof: `uv run python -m unittest tests.test_transcript_store -k test_lifespan_calls_transcript_ensure_schema`

**C2** - Inserting a transcript item with thread id `tid-1` stores `threads.id` equal to `tid-1`; `POST /agent` with `threadId` `tid-1` calls `astream` with `config.configurable.thread_id` equal to `tid-1` (TRN-01, AC 2)
Proof: `uv run python -m unittest tests.test_transcript_store -k test_insert_stores_thread_id`
Proof: `uv run python -m unittest tests.test_agent_route -k test_post_uses_body_thread_id_as_store_and_checkpoint_id`

**C3** - The store persists kinds `user` and `assistant_turn` and writing kind `tool_call` adds no row, table-driven over those 3 (TRN-01, AC 3)
Proof: `uv run python -m unittest tests.test_transcript_store -k test_kinds_user_assistant_turn_reject_tool_call`

**C4** - An inserted `assistant_turn` JSON has keys `outcome`, `content`, `gate`, `plan`, `steps`, `citations`; `gate` has `in_domain` and `reason`; each `plan[]` item has `index`, `agent`, `task`, `status`, `feedback`; `steps` has `count`, `elapsed_ms`, `nodes`; each `nodes[]` item has `name` and `query_used`; each `citations[]` item has `n`, `chunk_id`, `arxiv_id`, `title`, `year`, `url`, `excerpt`, table-driven over those fields (TRN-01, AC 4)
Proof: `uv run python -m unittest tests.test_transcript_store -k test_assistant_turn_json_key_set`

### S2 - HTTP read from items · 4 files · 22 KB · ~6k

**C5** - `GET /threads` responds `200` with a JSON array of objects each `{threadId, title, updatedAt}` sorted by `updatedAt` descending (TRN-02, AC 5)
Proof: `uv run python -m unittest tests.test_threads_route -k test_list_threads_sorted_updated_at_desc`

**C6** - `GET /threads` with no threads responds `200` `[]` (TRN-02, AC 6)
Proof: `uv run python -m unittest tests.test_threads_route -k test_list_threads_empty_is_200_array`

**C7** - `GET /threads/{thread_id}` with at least one transcript item responds `200` `{threadId, messages, status}`; when the checkpointer snapshot for that id has message content `from-checkpoint` and the transcript user content is `from-transcript`, `messages` contains `from-transcript` and does not contain `from-checkpoint` (TRN-02, AC 7)
Proof: `uv run python -m unittest tests.test_threads_route -k test_get_thread_200_from_transcript_not_checkpoint`

**C8** - `GET /threads/{thread_id}` with no transcript items responds `404` `{"detail":"thread not found"}` when a `MemorySaver` snapshot for that id has messages (TRN-02, AC 8)
Proof: `uv run python -m unittest tests.test_threads_route -k test_empty_transcript_is_404_despite_checkpoint`

**C9** - `GET /threads/{thread_id}` `messages` includes a `UserMessage` whose `id` and `content` equal the stored `user` item (TRN-02, AC 9)
Proof: `uv run python -m unittest tests.test_threads_route -k test_replay_user_item_id_and_content`

**C10** - `GET /threads/{thread_id}` for an `assistant_turn` with `outcome="done"` emits, in order, `ActivityMessage` `GATE`, `ActivityMessage` `PLAN`, `ActivityMessage` `STEPS`, `AssistantMessage` with `id` equal to the item id and `content` equal to the stored markdown, `ActivityMessage` `SOURCES`, table-driven over those 5 (TRN-02, AC 10)
Proof: `uv run python -m unittest tests.test_threads_route -k test_done_turn_replay_order`

**C11** - `GET /threads/{thread_id}` for an `assistant_turn` with `outcome` in `refused`, `insufficient`, `error` emits `ActivityMessage` `GATE` when `gate` is present, then `ActivityMessage` `OUTCOME` `{outcome, reason}`, and emits no `AssistantMessage`, table-driven over all 3 (TRN-02, AC 11)
Proof: `uv run python -m unittest tests.test_threads_route -k test_non_done_turn_replay_is_outcome_not_assistant`

**C12** - `GET /threads/{thread_id}` `status` is `"interrupted"` when the checkpoint snapshot `next` is non-empty and `"idle"` otherwise, with transcript items present in both cases (TRN-02, AC 12)
Proof: `uv run python -m unittest tests.test_threads_route -k test_status_from_checkpoint_next`

**C13** - Replayed `STEPS` `content` includes `count`, `elapsed_ms`, and `nodes` equal to the stored turn; when the turn stored `nodes` `[{name:"search", query_used:"LoRA"}]`, `nodes` is that list and not `[]` (TRN-02, AC 13)
Proof: `uv run python -m unittest tests.test_threads_route -k test_steps_replay_includes_stored_nodes`

**C14** - Two `done` turns on one thread: the `SOURCES` activity after the first `AssistantMessage` has that turn's `citations`, and the second `SOURCES` has the second turn's `citations` (TRN-02, AC 14)
Proof: `uv run python -m unittest tests.test_threads_route -k test_two_done_turns_sources_are_per_turn`

### S3 - Dual-write on POST /agent · 7 files · 45 KB · ~11k

**C15** - A non-resume `POST /agent` `200` with a `UserMessage` inserts a `user` transcript item with that message's `id` and `content` before `graph.astream` is first called (TRN-03, AC 15)
Proof: `uv run python -m unittest tests.test_agent_route -k test_non_resume_inserts_user_before_astream`

**C16** - When that `user` insert is the first item on the thread, `threads.title` equals the first 80 characters of the content, table-driven over content length 80 and 100 (TRN-03, AC 16)
Proof: `uv run python -m unittest tests.test_agent_route -k test_first_user_title_is_eighty_chars`

**C17** - `POST /agent` with `forwardedProps.resume=true` and a non-empty checkpoint `next` does not insert a `user` item (TRN-03, AC 17)
Proof: `uv run python -m unittest tests.test_agent_route -k test_resume_does_not_insert_user`

**C18** - Before the adapter yields `RUN_FINISHED`, the store already has an `assistant_turn` for that run; before it yields `RUN_ERROR`, the store already has an `assistant_turn` for that run (TRN-03, AC 18)
Proof: `uv run python -m unittest tests.test_agent_route -k test_assistant_turn_exists_before_run_finished`
Proof: `uv run python -m unittest tests.test_agent_route -k test_assistant_turn_exists_before_run_error`

**C19** - When `writer_message_id` is set, the `assistant_turn` `id` equals that `writer_message_id` (TRN-03, AC 19)
Proof: `uv run python -m unittest tests.test_agent_route -k test_assistant_turn_id_is_writer_message_id`

**C20** - When the Writer did not run, a timeout `RUN_FINISHED` `{outcome:"insufficient", reason:"timeout"}` inserts `assistant_turn` with `id` equal to the request `runId` and `outcome` `"insufficient"` (TRN-03, AC 20)
Proof: `uv run python -m unittest tests.test_agent_route -k test_timeout_assistant_turn_id_is_run_id`

**C21** - `finalize` still appends one `AIMessage` to `GraphState.messages`: `outcome="done"` uses `writer_markdown` and `writer_message_id`; `outcome` in `refused`, `insufficient`, `error` uses the terminal reason and that outcome in `response_metadata`; `response_metadata` keys are `outcome`, `gate`, `plan`, `steps`, `citations` (TRN-03, AC 21)
Proof: `uv run python -m unittest tests.test_finalize -k test_done_appends_aimessage_with_writer_id`
Proof: `uv run python -m unittest tests.test_finalize -k test_non_done_appends_aimessage_with_reason`
Proof: `uv run python -m unittest tests.test_finalize -k test_aimessage_metadata_key_set`

**C22** - `initial_graph_state("q")` still puts `{"role":"user","content":"q"}` as `messages[0]` (TRN-03, AC 22)
Proof: `uv run python -m unittest tests.test_research_graph -k test_initial_graph_state_query_and_eval_next`

**C23** - No file under `src/plan_based_researcher/graph/nodes/` imports the transcript store, table-driven over all 9 `.py` files (TRN-03, AC 23)
Proof: `uv run python -m unittest tests.test_transcript_isolation -k test_graph_nodes_do_not_import_transcript`

**C24** - Inserting a transcript item with an `id` that already exists leaves a single row for that `id` (TRN-03, AC 24)
Proof: `uv run python -m unittest tests.test_transcript_store -k test_repeat_id_leaves_one_row`

**C25** - `POST /agent` with empty `messages` and `forwardedProps.resume` not `true` still responds `400` `{"detail":"one user message or resume is required"}` (TRN-03, existing)
Proof: `uv run python -m unittest tests.test_agent_route -k test_empty_messages_without_resume_is_400`

**C26** - `POST /agent` with `forwardedProps.resume` `true` and checkpoint `next` empty still responds `409` `{"detail":"nothing to resume"}` (TRN-03, existing)
Proof: `uv run python -m unittest tests.test_agent_route -k test_resume_idle_is_409`

**C27** - `POST /agent` with a body that is not a valid `RunAgentInput` still responds `422` with the validation detail (TRN-03, existing)
Proof: `uv run python -m unittest tests.test_agent_route -k test_invalid_body_is_422`

### S4 - Desk Recents and per-turn hydrate · 7 files · 48 KB · ~12k

**C28** - When the desk mounts, it calls `GET /threads`; a `200` body `[{threadId:"tid-a", title:"LoRA notes", updatedAt:"2026-09-19T12:00:00Z"}]` renders `LoRA notes` in the sidebar; a `200` `[]` renders `Threads you start appear here.` (TRN-04, AC 25)
Proof: `npm --prefix web exec -- vitest run -t "sidebar fetches GET /threads and renders title"`
Proof: `npm --prefix web exec -- vitest run -t "empty GET /threads shows recents empty copy"`

**C29** - The repository does not contain `web/lib/recents.ts` (TRN-04, AC 26)
Proof: `uv run python -m unittest tests.test_transcript_isolation -k test_web_lib_recents_ts_absent`

**C30** - Opening `/c/{threadId}` calls `GET /threads/{threadId}` and renders `messages` before the input is enabled (TRN-04, AC 27)
Proof: `npm --prefix web exec -- vitest run -t "direct thread load waits for replay"`

**C31** - `GET /threads/{threadId}` status `404` navigates the client to `/` (TRN-04, AC 28)
Proof: `npm --prefix web exec -- vitest run -t "thread 404 navigates home"`

**C32** - After `applyReplay` of two `SOURCES` activities each after its `AssistantMessage`, a citation `[1]` on the first assistant block resolves to the first turn's excerpt `first-excerpt` and not `second-excerpt` (TRN-04, AC 29)
Proof: `npm --prefix web exec -- vitest run -t "first assistant cite uses first turn sources not second"`

**C33** - After `applyReplay` of `STEPS` with `nodes` `[{name:"search"},{name:"execute"}]`, expanding the collapsed StepRail lists `search` and `execute` (TRN-04, AC 30)
Proof: `npm --prefix web exec -- vitest run -t "replay steps nodes appear in collapsed rail expand"`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `GET /threads` statuses (1) | 200 C5 | - |
| `GET /threads` list fields (3) | `threadId` C5 · `title` C5 · `updatedAt` C5 | - |
| `GET /threads/{thread_id}` statuses (2) | 200 C7 · 404 C8 | - |
| `GET /threads/{thread_id}` body fields (3) | `threadId` C7 · `messages` C7 · `status` C7 | - |
| `POST /agent` statuses (4) | 200 C15 · 400 C25 · 409 C26 · 422 C27 | - |
| Landing doors (9) | 1 C1 · 2 C2 · 3 C21 · 4 C18 · 5 C28 · 6 C8 · 7 C7 · 8 C24 · 9 C3 | - |
| Relations entities (3) | THREAD C2 · TRANSCRIPT_ITEM C4 · CHECKPOINT C8 | - |
| transcript kinds (2) | `user` C3 · `assistant_turn` C3 | - |
| assistant_turn top keys (6) | C4, table-driven over all 6 | - |
| gate fields (2) | `in_domain` C4 · `reason` C4 | - |
| plan item fields (5) | C4, table-driven over all 5 | - |
| steps fields (3) | `count` C4 · `elapsed_ms` C4 · `nodes` C4 | - |
| step node fields (2) | `name` C4 · `query_used` C4 | - |
| citation fields (7) | C4, table-driven over all 7 | - |
| replay done sequence (5) | C10, table-driven over all 5 | - |
| non-done outcomes (3) | C11, table-driven over all 3 | - |
| thread `status` (2) | `interrupted` C12 · `idle` C12 | - |
| two-turn SOURCES (2) | first C14 · second C14 | - |
| assistant_turn id (2) | `writer_message_id` C19 · `runId` C20 | - |
| terminal frames (2) | `RUN_FINISHED` C18 · `RUN_ERROR` C18 | - |
| title length edges (2) | 80 C16 · 100 C16 | - |
| `graph/nodes/` modules (9) | C23, table-driven over all 9 | - |
| startup config: transcript schema (2 assemblies) | lifespan C1 · unittest store C4 | - |

- Claims naming a status code, route or response shape: C5, C6, C7, C8, C9, C10, C11, C12, C15, C25, C26, C27 - each has a proof that crosses the HTTP boundary
- C7 is the messages-source claim: a GET that still mapped checkpoint `messages` would contain `from-checkpoint`
- C14 and C32 both assert per-turn citations; C14 at the GET body, C32 at the desk `[n]` resolution. A last-write global `SOURCES` list would pass C14 and fail C32
- No other check claims more than the single case its proof exercises

## Swept

- validation: C3, C16, C25, C27
- failure modes: C8, C11, C18, C20
- idempotency: C24
- authorization: n/a - no auth in v1; list-all leak accepted until `owner_id` (plan)
- concurrency: n/a - concurrent runs on one thread are out of scope (plan)
- data lifecycle: C8 - no backfill; checkpoint-only threads are `404`
- dependency failure: C18, C20
- state transitions: C12, C15, C17
- observability: C5, C10, C28

## Handoff

Intended split, with the arithmetic, written before any code:

- S1 ~6k + S2 ~6k + S3 ~11k + S4 ~12k ≈ 35k tokens, under the 150k budget — one builder
- Surface changes from Python (`GET /threads`, `GET /threads/{thread_id}`, `POST /agent`) to `web/` at S4, but the running estimate still fits; do not split mid-outcome

- **Boundary:** C1–C33 closed locally (no commit — AGENTS.md defers tlc-spec-lean build commits)
- **Settled mid-build:** none
- **Abandoned:** assigning over `MemoryTranscriptStore.insert_assistant_turn` (slots dataclass is read-only); C18 orders via `store.log` vs `EventEncoder.encode`
