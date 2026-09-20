# Writer calculator checks

Profile: light
Plan: `.specs/features/writer-calculator/plan.md`

## Intent

36 checks in 1 slice · 4 one-way doors · 0 open

## Checks

Grouped by the spec's slices; numbering runs across the whole feature.

### S1–S6 - Writer calculator · 8 files · 48 KB · ~12k

**C1** - `REGISTRY["writer"].tools` equals `("calculator",)` (CALC-01, AC 1)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_registry_writer_tools_is_calculator`

**C2** - `planner_prompt_abilities()` contains the substring `compute arithmetic on numbers present in packed chunks` (CALC-01, AC 2)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_planner_abilities_include_arithmetic_capability`

**C3** - `planner_prompt_abilities()` does not contain the substring `calculator` (CALC-01, AC 3)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_planner_abilities_omit_calculator_name`

**C4** - `PLAN_AGENTS` equals `frozenset({"search", "retrieve", "writer"})` (CALC-01, AC 4)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_plan_agents_unchanged`

**C5** - When `PlannerRunner._complete` is given a `ResearchPlan` whose first step `agent` is `calculator`, it raises `ValueError` whose message contains `invalid agent name` (CALC-01, AC 5)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_complete_rejects_calculator_agent_name`

**C6** - When `WriterRunner.run` receives a model response whose `tool_calls` has one `calculator` call with expression `2+3*4` and a later response with visible text `The total is 14 [1]`, the runner invokes the calculator once with `2+3*4` and sets `writer_markdown` to `The total is 14 [1]` (CALC-02, AC 6)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_runner_invokes_calculator_then_sets_markdown`

**C7** - When the model streams only visible text and no `tool_calls`, `WriterRunner` emits `answer_start`, then `answer_delta` chunks whose concatenated `text` equals `writer_markdown`, then `citations` (CALC-02, AC 7)
Proof: `uv run python -m unittest tests.test_writer_stream -k test_tiny_graph_two_deltas_then_citations`

**C8** - The product graph compiled in `graph/build.py` has node names `gate`, `planner`, `dispatch`, `search`, `execute`, `evaluate`, `replan`, `finalize` and does not have a node named `calculator` or `tools` (CALC-02, AC 8)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_product_graph_nodes_exclude_calculator_and_tools`

**C9** - When the calculator returns an error string, `WriterRunner` appends that string as the tool result and does not set `outcome` to `error` from that string (CALC-02, AC 9)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_calculator_error_string_is_tool_result_not_outcome_error`

**C10** - When the model requests a tool name other than `calculator`, `WriterRunner` returns a tool-result error string and does not raise (CALC-02, AC 10)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_unknown_tool_name_is_tool_error_not_raise`

**C11** - When `WriterRunner` has already finished `Policy.writer_calculator_rounds` calculator invocations in that run, the next model call does not expose the calculator tool (CALC-02, AC 11)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_after_round_cap_model_call_has_no_calculator_tool`

**C12** - When the calculator is given `2+3*4` it returns the string `14` (CALC-03, AC 12)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_2_plus_3_times_4_is_14`

**C13** - When the calculator is given `10/4` it returns the string `2.5` (CALC-03, AC 13)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_10_div_4_is_2_5`

**C14** - When the calculator is given `2**10` it returns the string `1024` (CALC-03, AC 14)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_2_pow_10_is_1024`

**C15** - When the calculator is given `1e3+1` it returns the string `1001` (CALC-03, AC 15)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_1e3_plus_1_is_1001`

**C16** - When the calculator is given `-(2+3)` it returns the string `-5` (CALC-03, AC 16)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_unary_minus_paren_is_minus_5`

**C17** - When the expression is `""` or only whitespace, the calculator returns a string containing `error` and does not raise, table-driven over those 2 (CALC-03, AC 17)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_empty_or_whitespace_returns_error`

**C18** - When the expression contains a name such as `os`, the calculator returns a string containing `error` and does not raise (CALC-03, AC 18)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_name_os_returns_error`

**C19** - When the expression is `1/0`, the calculator returns a string containing `error` and does not raise (CALC-03, AC 19)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_div_zero_returns_error`

**C20** - When the expression length is greater than `Policy.writer_calculator_expression_max`, the calculator returns a string containing `error` and does not raise (CALC-03, AC 20)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_eval_over_max_length_returns_error`

**C21** - The calculator implementation module's AST contains no `eval(` or `exec(` call (CALC-03, AC 21)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_calculator_module_ast_has_no_eval_or_exec_call`

**C22** - When the model streams a chunk that has `tool_call_chunks` and no visible text, `WriterRunner` does not emit `answer_delta` for that chunk (CALC-04, AC 22)
Proof: `uv run python -m unittest tests.test_writer_stream -k test_tool_call_chunk_without_text_emits_no_answer_delta`

**C23** - When a calculator round is followed by streamed markdown `Hello [1]`, concatenating `answer_delta` `text` values in order equals `writer_markdown` and equals `Hello [1]` (CALC-04, AC 23)
Proof: `uv run python -m unittest tests.test_writer_stream -k test_calculator_then_markdown_deltas_equal_writer_markdown`

**C24** - `WriterRunner` custom SSE `event` names are only `answer_start`, `answer_delta`, or `citations` (CALC-04, AC 24)
Proof: `uv run python -m unittest tests.test_writer_stream -k test_writer_events_only_answer_start_delta_citations`

**C25** - Citations list only `[n]` that exist in `evidence_chunks`; unknown n is omitted and the run still succeeds (CALC-04, AC 25)
Proof: `uv run python -m unittest tests.test_writer_stream -k test_unknown_citation_n_omitted`

**C26** - `Policy.GROUNDING_RULE` states that a number obtained by arithmetic on operands that each have a real `[n]` is a derived result: cite the operands; do not invent a citation for the result; do not treat the result as a new source (CALC-05, AC 26)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_grounding_rule_derived_arithmetic_carve_out`

**C27** - The Writer system prompt includes `Policy.GROUNDING_RULE` (CALC-05, AC 27)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_writer_system_prompt_includes_grounding_rule`

**C28** - `REGISTRY["writer"].abilities` mentions computing arithmetic on packed-chunk numbers (CALC-05, AC 28)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_writer_abilities_mention_packed_chunk_arithmetic`

**C29** - `REGISTRY["writer"].abilities` does not mention the tool name `calculator` (CALC-05, AC 29)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_writer_abilities_omit_calculator_name`

**C30** - The Writer inner graph routes the writer model node with `tools_condition` so `tool_calls` go to the tools node and the absence of `tool_calls` ends the inner graph (CALC-06, AC 30)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_inner_graph_routes_with_tools_condition`

**C31** - The Writer inner graph executes tool calls with `ToolNode` (CALC-06, AC 31)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_inner_graph_tools_node_is_tool_node`

**C32** - The calculator tool `handle_tool_error` equals `True` (CALC-06, AC 32)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_calculator_handle_tool_error_true`

**C33** - The calculator tool `handle_validation_error` equals `True` (CALC-06, AC 33)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_calculator_handle_validation_error_true`

**C34** - The Writer `ToolNode` is constructed with `handle_tool_errors` equal to `True` (CALC-06, AC 34)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_writer_tool_node_handle_tool_errors_true`

**C35** - When the model emits a `calculator` tool call whose arguments fail schema validation, `WriterRunner.run` does not raise and feeds a tool message containing `error` into the next writer model call (CALC-06, AC 35)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_invalid_calculator_args_feed_error_tool_message`

**C36** - When the calculator raises `ToolException`, `WriterRunner.run` does not raise and feeds a tool message containing `error` into the next writer model call (CALC-06, AC 36)
Proof: `uv run python -m unittest tests.test_writer_calculator -k test_tool_exception_feeds_error_tool_message`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| `calculator` tool statuses (2) | `200` C12 · `400` C17 | - |
| Landing doors (4) | inner ToolNode loop C30 · calculator contract C12 · planner-facing copy C1 · grounding carve-out C26 | - |
| `PLAN_AGENTS` (3) | `search` C4 · `retrieve` C4 · `writer` C4 | - |
| product graph nodes (8) | C8, table-driven over all 8 | - |
| Writer SSE events (3) | `answer_start` C7 · `answer_delta` C7 · `citations` C7 | - |
| grammar success literals (5) | `2+3*4` C12 · `10/4` C13 · `2**10` C14 · `1e3+1` C15 · `-(2+3)` C16 | - |
| calculator reject cases (4) | empty/whitespace C17 · name `os` C18 · `1/0` C19 · over max length C20 | - |
| empty/whitespace expressions (2) | `""` C17 · whitespace C17 | - |
| tool error handles (3) | `handle_tool_error` C32 · `handle_validation_error` C33 · `ToolNode handle_tool_errors` C34 | - |
| `POST /agent` Writer SSE names (3) | `answer_start` C24 · `answer_delta` C24 · `citations` C24 | - |

- Claims naming a status, route or response shape: C12, C17, C24 - C12/C17 are the calculator tool 200/400 strings; C24 is the Writer SSE name set
- No other check claims more than the single case its proof exercises

## Swept

- validation: C17, C18, C20, C35
- failure modes: C9, C10, C19, C36
- idempotency: n/a - calculator is a pure expression; no delivery id
- authorization: C1, C10, C11
- concurrency: n/a - inner graph is per `WriterRunner.run`; no shared calculator store
- data lifecycle: n/a - no stored-data shape change
- dependency failure: n/a - calculator is local; no Voyage/arXiv
- state transitions: C6, C11, C30
- observability: C7, C22, C24

## Handoff

Intended split, with the arithmetic, written before any code:

- S1–S6 = ~12k, all Writer/registry/policy; under 150k → one builder, no handoff

- **Boundary:** C1–C36 closed locally (no commit — AGENTS.md defers tlc-spec-lean build commits)
- **Settled mid-build:** none
- **Abandoned:** none
