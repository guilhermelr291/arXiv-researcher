# Out-of-domain question response checks

Profile: light
Plan: `.specs/features/out-of-domain-question-response/plan.md`

20 checks in 3 slices · 3 one-way doors · 0 open, of which 0 block

## Checks

Grouped by the spec's slices; numbering runs across the whole feature.

### S1 - In-domain gate is not a product turn · 7 files · 90 KB · ~23k

**C1** - When the gate runner returns `in_domain=true`, custom writer payloads contain no object whose `event` is `"gate"` (OOD-01, AC 1)
Proof: `uv run python -m unittest tests.test_gate_node -k test_in_domain_emits_no_gate_event`

**C2** - `POST /agent` `200` for an in-domain FakeGraph stream (no custom `event: "gate"`) yields SSE with no `ACTIVITY_SNAPSHOT` whose `activityType` is `"GATE"` (OOD-01, AC 2)
Proof: `uv run python -m unittest tests.test_agent_route -k test_in_domain_sse_has_no_gate_activity`

**C3** - Replaying a `done` turn emits, after the user message, `PLAN` then `STEPS` then `assistant` then `SOURCES`, and emits no `GATE`, for both `snapshot_to_agui_messages` and `items_to_agui_messages` (OOD-01, AC 3)
Proof: `uv run python -m unittest tests.test_threads_route -k test_done_replay_order`
Proof: `uv run python -m unittest tests.test_threads_route -k test_done_turn_replay_order`

**C4** - When the adapter is fed a leftover custom chunk `{"event": "gate", "data": {in_domain, language, reason}}`, parsed events contain no `ACTIVITY_SNAPSHOT` with `activityType` `"GATE"` (OOD-01, AC 4)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_leftover_gate_chunk_is_not_activity_snapshot`

### S2 - Refuse speaks on the Writer text channel · 6 files · 80 KB · ~20k

**C5** - When the gate runner returns `in_domain=false` and `reason="out of scope"`, custom payloads are `answer_start` with a uuid `message_id` then exactly one `answer_delta` whose `text` is `"out of scope"`, and no payload has `event` `"gate"` (OOD-02, AC 5)
Proof: `uv run python -m unittest tests.test_gate_node -k test_refused_emits_answer_start_then_one_delta`

**C6** - That refused gate-node update includes `writer_message_id` equal to the `answer_start` `message_id` and does not include a `messages` key (OOD-02, AC 6)
Proof: `uv run python -m unittest tests.test_gate_node -k test_refused_sets_writer_message_id_without_messages`

**C7** - When `finalize` runs with `outcome="refused"`, `gate.reason="out of scope"`, and `writer_message_id="msg-refused"`, it appends exactly one `AIMessage` whose `content` is `"out of scope"`, whose `id` is `"msg-refused"`, and whose `response_metadata.outcome` is `"refused"` (OOD-02, AC 7)
Proof: `uv run python -m unittest tests.test_finalize -k test_refused_aimessage_id_is_writer_message_id`

**C8** - When the adapter has emitted `TEXT_MESSAGE_START` for `message_id` `mid` and no `citations` event follows, then a custom `done` `{outcome: "refused", reason: "out of scope"}`, parsed events include `TEXT_MESSAGE_END` with that `mid` at an index before `RUN_FINISHED` (OOD-02, AC 8)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_refused_text_end_before_run_finished`

**C9** - That same stream's `RUN_FINISHED` has `result.outcome="refused"` and `result.reason="out of scope"` (OOD-02, AC 9)
Proof: `uv run python -m unittest tests.test_agui_adapter -k test_refused_run_finished_reason`

**C10** - When compiled-graph `ainvoke` gets a gate runner with `in_domain=false`, `factory.create` is never called with `"planner"` or `"writer"` and the returned state's `outcome` is `"refused"` (OOD-02, AC 10)
Proof: `uv run python -m unittest tests.test_gate_node -k test_refused_ainvoke_skips_planner_and_writer`

**C11** - On that refused path, the `answer_delta` `text`, the finalize `AIMessage.content`, and `gate.reason` are the same string `"out of scope"` (OOD-02, AC 11)
Proof: `uv run python -m unittest tests.test_gate_node -k test_refused_stream_text_equals_aimessage_and_reason`

### S3 - Desk and replay show a reply, not a verdict · 4 files · 55 KB · ~14k

**C12** - After `TEXT_MESSAGE_START` / `TEXT_MESSAGE_CONTENT` delta `"out of scope"` then `RUN_FINISHED` `{outcome: "refused"}`, desk state has an `assistant` block with `content` `"out of scope"`, `streaming=false`, and no block `kind="outcome"` (OOD-03, AC 12)
Proof: `npm --prefix web exec -- vitest run -t "refused run finished keeps assistant not outcome"`

**C13** - After `RUN_FINISHED` `{outcome: "insufficient", reason: "not enough papers"}`, desk state has a block `kind="outcome"` with that `reason` and no `assistant` block (OOD-03, AC 13)
Proof: `npm --prefix web exec -- vitest run -t "insufficient run finished is outcome chip not assistant"`

**C14** - Replaying an `assistant_turn` / checkpoint `AIMessage` with `outcome="refused"` and content `"out of scope"` emits `AssistantMessage` with `id` equal to the turn id and `content` `"out of scope"`, and emits neither `GATE` nor `OUTCOME`, for both mappers (OOD-03, AC 14)
Proof: `uv run python -m unittest tests.test_threads_route -k test_refused_replay_is_assistant_not_gate_or_outcome`

**C15** - Replaying an `assistant_turn` / checkpoint `AIMessage` with `outcome` in `insufficient`, `error` emits `OUTCOME` `{outcome, reason}` and emits neither `GATE` nor `AssistantMessage`, table-driven over those 2 outcomes and both mappers (OOD-03, AC 15)
Proof: `uv run python -m unittest tests.test_threads_route -k test_insufficient_error_replay_is_outcome_not_gate`

**C16** - `applyReplay` given `{role: "assistant", id: "ai-refused", content: "out of scope"}` yields an `assistant` block with that `id` and `content` (OOD-03, AC 16)
Proof: `npm --prefix web exec -- vitest run -t "applyReplay refused assistant is markdown block"`

**C17** - `POST /agent` with empty `messages` and `forwardedProps.resume` not `true` still responds `400` `{"detail":"one user message or resume is required"}` (OOD-02, Surface)
Proof: `uv run python -m unittest tests.test_agent_route -k test_empty_messages_without_resume_is_400`

**C18** - `POST /agent` with `forwardedProps.resume` `true` and checkpoint `next` empty still responds `409` `{"detail":"nothing to resume"}` (OOD-02, Surface)
Proof: `uv run python -m unittest tests.test_agent_route -k test_resume_idle_is_409`

**C19** - `POST /agent` with a body that is not a valid `RunAgentInput` still responds `422` with the validation detail (OOD-02, Surface)
Proof: `uv run python -m unittest tests.test_agent_route -k test_invalid_body_is_422`

**C20** - `GET /threads/{thread_id}` with no transcript items still responds `404` `{"detail":"thread not found"}` (OOD-03, Surface)
Proof: `uv run python -m unittest tests.test_threads_route -k test_empty_transcript_is_404_despite_checkpoint`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `POST /agent` statuses (4) | `200` C2 · `400` C17 · `409` C18 · `422` C19 | - |
| `GET /threads/{thread_id}` statuses (2) | `200` C3 · `404` C20 | - |
| door 1 GATE not a product surface (3) | no custom `gate` C1 · adapter never `GATE` C4 · replay omits `GATE` C3 | - |
| door 2 refuse Writer text events (7) | `answer_start`+delta C5 · `writer_message_id` C6 · `AIMessage` C7 · `TEXT_MESSAGE_END` C8 · `RUN_FINISHED` C9 · no planner/writer C10 · text=reason C11 | - |
| door 3 desk `refused` vs `insufficient` (2) | `refused` keeps assistant C12 · `insufficient` chip C13 | - |
| replay mappers × refuse surface (2) | `snapshot_to_agui_messages` C14 · `items_to_agui_messages` C14 | - |
| halt replay outcomes without GATE (2) | `insufficient` C15 · `error` C15 | - |
| gate `in_domain` (2) | `true` C1 · `false` C5 | - |

- Claims naming a status code, route or response shape: C2, C17, C18, C19, C20 - each has a proof that crosses the HTTP boundary
- No other check claims more than the single case its proof exercises

## Swept

- validation: n/a - no new request body; `GateDecision.reason` remains the structured field
- failure modes: C5, C8 - refuse still streams and closes text without `citations`
- idempotency: existing - `POST /agent` 409 idle resume (C18); no new write key
- authorization: n/a - no auth in v1
- concurrency: existing - `wrap_node` `gate` rail; no new shared mutable surface
- data lifecycle: n/a - Relations none; stored `assistant_turn` / `AIMessage` already hold `reason`
- dependency failure: n/a - no new I/O; OpenAI gate runner unchanged
- state transitions: C10, C12, C13 - `refused` → finalize + assistant block; `insufficient` stays chip
- observability: existing - `STEP_STARTED` `gate` remains; `ACTIVITY_SNAPSHOT` `GATE` is removed (C1, C4)

## Handoff

Intended split, with the arithmetic, written before any code:

- S1+S2+S3 = ~57k, one surface (desk+wire); no handoff
