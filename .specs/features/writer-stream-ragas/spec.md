# Writer Stream + RAGAS Report Specification

**Feature:** `writer-stream-ragas`  
**Spec status:** Verified T1–T10 2026-09-08 (code; unittest discover 88/88). Live Independent Tests remain UAT. Not committed.  
**Date:** 2026-09-08  
**Gray areas:** Locked in grill-me 2026-09-08; `discuss.md` skipped  
**Parent product:** `.specs/features/arxiv-grounded-research/spec.md` (SSE-01, SSE-02, GROUND-01–03, UI-01–03, ORCH-03)  
**Parent loop:** `.specs/features/orchestrator-eval-replan/spec.md` (WRITE-01)  
**Parent admission:** `.specs/features/admission-retrieve-per-topic/spec.md` (WRITE-02)  
**Parent SSE edge:** `.specs/features/sse-agent-dispatcher/spec.md` (STRM-10, STRM-11)  
**Architecture constraints:** `.specs/features/arxiv-grounded-research/context.md` (PAT-01, PAT-07, PAT-11 consume path, PAT-12)

This spec changes **when** the student sees Writer markdown, **which SSE names** carry the answer, and **where** faithfulness is measured. It does **not** change Gate, plan vocabulary, admission, retrieve cut, `[n]` prompt format, search/retrieve eval, or Voyage embeddings.

## Problem Statement

The Writer buffers a full structured object, then an LLM judge (`WriterEvalStrategy`) can retry before any student-visible text. That latency is the product of AD-007 / SSE-02: unvalidated prose must not appear. The student waits through generate + judge for a single `answer_complete`. Quality of the markdown is no longer a graph verdict: RAGAS faithfulness and answer relevancy run **offline** on real traces. The runtime should stream tokens as the Writer produces them, deliver structured `citations[]` once `[n]` exist, and drop the Writer eval loop.

## Goals

- [ ] In-domain runs stream Writer markdown to the client as `answer_delta` while the model generates; the student never waits for a Writer judge.
- [ ] After the last token, the client receives `citations[]` on a `citations` event (no second copy of the full markdown). `answer_complete` is gone.
- [ ] Writer execute is one-shot: no `WriterEvalStrategy`, no Writer `eval` SSE, no Writer retry. Search and retrieve eval stay.
- [ ] Chainlit typewriters the deltas and attaches side-panel `[n]` from `citations`.
- [ ] A LangSmith-backed script reports RAGAS `Faithfulness` and `AnswerRelevancy` on real (`query`, writer-facing chunks, markdown). It does not fail CI and does not score retrieve with context_* metrics.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| RAGAS as a runtime gate or Writer retry | Grill-me: student already sees tokens; scores are a report |
| Pytest / CI fail on faithfulness or relevancy thresholds | Report only; no floor in this slice |
| `context_precision` / `context_recall` / context relevancy | Grill-me: writer metrics only |
| Live graph inside the RAGAS script (arXiv + retrieve + Writer) | Dataset is existing LangSmith traces; recollection is manual |
| LangChain `on_chat_model_stream` (or other `on_chat_model_*` / `on_tool_*`) on the SSE wire | STRM-10; tokens go through `get_stream_writer` |
| Typewriter **after** a Writer eval pass (deferred ROADMAP item) | Eval is removed; stream is the answer |
| Re-sending full markdown on `citations` or `done` | Grill-me: deltas are sufficient for the text |
| Fake Writer `eval` pass frames | No Writer eval event at all |
| Changing search/retrieve judges, WRITE-02 **prompt** hole rule, Gate, admission, Voyage retrieve | Parent |
| LangSmith online-eval UI rules (hosted evaluators) | Script + collections `ascore` |
| Hover/JSX citation widgets | Still deferred |

### Supersedes (parent specs / decisions)

Upon approval, these rows are **replaced**. Unnamed parent IDs stay in force.

| Parent ID / lock | What no longer holds |
| ---------------- | -------------------- |
| SSE-02 | No `answer_delta`; student-visible answer only after Writer eval pass (`answer_complete`). |
| AD-007 (streaming / eval gate) | No `answer_delta`; `answer_complete` only after Writer eval passes. **Unchanged:** `[n]` prompt format; `citations[]` fields; contradictions stated in the markdown. |
| SSE-01 name list | Names include `answer_complete` and exclude `answer_delta`. **Replaced names:** see Locked. |
| STRM-11 | No `answer_delta`; `answer_complete` only after Writer eval pass. |
| WRITE-01 (gate) | Writer eval remains ORCH-03; retry = rewrite on the same evidence; pass → `answer_complete` only. |
| ORCH-03 as a **runtime** Writer checklist | Orchestrator LLM/deterministic Writer judge before the student sees text. **Unchanged:** GROUND-01 formatting; GROUND-02 `citations[]` built from used `[n]`; GROUND-03 in the Writer prompt. |
| sse-agent-dispatcher locked client names | Exactly `gate` … `answer_complete` … `error` with no `answer_delta`. |
| sse-agent-dispatcher out-of-scope “Writer `answer_delta` / typewriter” | This slice **adds** typewriter via custom SSE. |
| PROJECT.md out-of-scope ``answer_delta`` | Streaming Writer tokens is in v1 after this feature. |
| ROADMAP Future “Writer `answer_delta` after eval pass” | Deltas happen **without** eval pass. |

**Amended (not replaced):** SSE-01 is still `text/event-stream` with `event:` / `data:` JSON. STRM-10 still forbids LC callback **names** on the wire; Writer markdown **is** student-visible, but only as `answer_delta`. WRITE-02 hole rule stays in the Writer **prompt**; there is no retry if the model fills a hole. GROUND-02 payload lives on `citations`, not `answer_complete`. UI-02 still maps `[n]` to side-panel `cl.Text`. CAP-01 / search / retrieve eval / replan unchanged. `writer_markdown` and `citations` remain graph state (checkpoint / LangSmith).

**Locked from specify (do not reopen in Design):**

- **Student contract:** stream always. Writer markdown quality SHALL NOT set `insufficient` or trigger Writer retry. Caps, Gate, search/retrieve eval, timeout, and execute exceptions still can.
- **SSE names:** `gate`, `plan`, `step_start`, `step_end`, `eval`, `answer_delta`, `citations`, `done`, `insufficient`, `error`. SHALL NOT emit `answer_complete`.
- **`answer_delta` `data`:** JSON object `{ "text": "<chunk>" }` where `text` is a non-empty string fragment of the markdown (token or larger model chunk). Concatenating `text` in order SHALL equal `writer_markdown` stored on state.
- **`citations` `data`:** JSON object `{ "citations": [ ... ] }` with the same Citation fields as today (`n`, `arxiv_id`, `title`, `year`, `url`, `excerpt`, `chunk_id`). SHALL NOT include `markdown`.
- **Order (Writer success):** `step_start` (writer) → zero or more `answer_delta` → one `citations` → `step_end` (writer) → later `done` (no `answer_complete`). `eval` SHALL NOT appear for the Writer step.
- **Channel:** deltas and `citations` SHALL be emitted via LangGraph `get_stream_writer()` (dispatcher custom / `on_chain_stream` unwrap). SHALL NOT add `chat_model` / `llm` to dispatcher `include_types` for this purpose.
- **Writer model call:** drop `with_structured_output(WriterOutput)` for the streaming path. Parse used `[n]` after the full text (same membership rules as today: only indices present in `evidence_chunks`). Unknown `[n]` are omitted from `citations[]`; that SHALL NOT fail the run.
- **Writer eval:** `WriterEvalStrategy` SHALL NOT run. Graph wiring SHALL NOT require a Writer eval Strategy to complete a Writer step. `max_retries_per_step` still applies to search/retrieve only.
- **Chainlit:** this slice. Typewriter from `answer_delta`; side panel from `citations` using existing `side_panel_texts`. Ignore leftover `answer_complete` if a proxy replayed an old server (parser may drop unknown names; server must not emit it).
- **RAGAS:** `ragas.metrics.collections.Faithfulness` and `AnswerRelevancy` via `ascore` (`user_input`, `response`, and for faithfulness `retrieved_contexts`). Judge LLM/embeddings follow current RAGAS collections docs (OpenAI client + `llm_factory` / `embedding_factory` with `text-embedding-3-small` for AnswerRelevancy). SHALL NOT use Voyage retrieve embeddings for the metric. SHALL NOT call context_* metrics.
- **RAGAS dataset:** LangSmith traces from this project. Mapper: `user_input` = student query; `response` = Writer markdown; `retrieved_contexts` = **writer-facing** `evidence_chunks` excerpts **after** rerank + `cut_reranked` + pack/expand (the list formatted into the Writer prompt). SHALL NOT use the rerank span’s first-stage / pre-cut list. Skip a trace if any of the three fields is missing. Output is a report (stdout and/or LangSmith feedback). Process exit SHALL NOT encode a score threshold.
- **Insufficient / refuse / error before Writer:** SHALL NOT emit `answer_delta` or `citations`. Same as today with no `answer_complete`.

---

## User Stories

### P1: Streamed Writer over SSE ⭐ MVP

**User Story**: As a student (or any `POST /research` client), I want the answer to appear as the Writer generates it, and the citation payloads when the text is finished, so I do not wait for a second LLM judge and I do not download the markdown twice.

**Why P1**: This is the student-visible contract change.

**Acceptance Criteria**:

1. WHEN the Writer model produces tokens THEN the system SHALL emit `answer_delta` frames with `{ "text": ... }` on the SSE stream before the Writer step ends.
2. WHEN the Writer markdown is complete THEN the system SHALL emit exactly one `citations` frame whose `citations[]` lists the `evidence_chunks` used by `[n]` in that markdown (GROUND-02 fields), and SHALL NOT include a markdown field on that event.
3. WHEN the Writer step finishes without an execute exception THEN the system SHALL mark the Writer step passed, SHALL NOT invoke `WriterEvalStrategy`, SHALL NOT emit `eval` for agent `writer`, and SHALL proceed to `done` when the plan is complete.
4. WHEN the client concatenates `answer_delta` `text` values in order THEN that string SHALL match graph `writer_markdown` for that run.
5. WHEN `SSE_EVENTS` / the dispatcher default map is inspected THEN they SHALL contain `answer_delta` and `citations` and SHALL NOT contain `answer_complete`.
6. WHEN chat-model callbacks occur internally THEN the client SHALL NOT receive `event: on_chat_model_stream` (or other `on_chat_model_*` / `on_tool_*` names).

**Independent Test**: In-domain `POST /research` until `done`. Assert `answer_delta` appears during the writer step; `citations` after the last delta and before `done`; no `answer_complete`; no Writer `eval`; no `on_chat_model_*`. Concatenated deltas equal stored markdown. `citations[].n` ⊆ evidence `[n]`.

---

### P1: Chainlit typewriter and side panel ⭐ MVP

**User Story**: As a student in Chainlit, I want to watch the answer type out and still open `[n]` excerpts in the side panel, so streaming does not drop inspectable citations.

**Why P1**: Chainlit is the v1 UI; it currently only builds the answer on `answer_complete`.

**Acceptance Criteria**:

1. WHEN `answer_delta` arrives THEN Chainlit SHALL append `text` to the student-facing answer message (typewriter), not wait for a final markdown event.
2. WHEN `citations` arrives THEN Chainlit SHALL attach side-panel `cl.Text` via `side_panel_texts` (same `[n]` → excerpt mapping as today).
3. WHEN `done` arrives after a successful Writer THEN Chainlit SHALL NOT require `answer_complete` to show the answer.

**Independent Test**: In-domain Chainlit run: message grows during Writer; after `citations`, clicking / mentioning `[n]` still opens the excerpt panel.

---

### P1: RAGAS report from LangSmith traces ⭐ MVP

**User Story**: As a maintainer, I want a script that scores real Writer answers with RAGAS faithfulness and answer relevancy against the chunks the Writer saw, so we still measure hallucination without blocking the student.

**Why P1**: Grill-me: this is the replacement for the runtime Writer judge.

**Acceptance Criteria**:

1. WHEN the script runs THEN it SHALL load traces from the configured LangSmith project and map each usable run to `user_input`, `retrieved_contexts`, `response` as locked above.
2. WHEN a trace lacks query, writer-facing chunks, or markdown THEN the script SHALL skip it (not treat it as score 0).
3. WHEN a usable run is scored THEN the script SHALL call collections `Faithfulness.ascore` and `AnswerRelevancy.ascore` and SHALL print both `result.value` values (and MAY write LangSmith feedback). SHALL NOT exit non-zero because a value is below a threshold.
4. WHEN `retrieved_contexts` is built THEN each item SHALL be the excerpt string from post-cut `evidence_chunks` (Writer prompt list), not pre-rerank candidates.

**Independent Test**: Point the script at a known successful Writer trace (or a saved fixture of that triple). Output includes two numeric scores. A deliberately incomplete trace is skipped. Code/review: mapper does not read rerank first-stage lists as `retrieved_contexts`.

---

## Edge Cases

- WHEN the run becomes `insufficient`, `refused`, or `error` before the Writer executes THEN the stream SHALL NOT contain `answer_delta` or `citations`.
- WHEN Writer markdown is empty THEN the system SHALL still emit `citations` (possibly `[]`) and `done` if the Writer step completed; SHALL NOT retry the Writer.
- WHEN the Writer raises mid-stream THEN already-sent `answer_delta` frames remain; the generator SHALL emit `error` (or the existing exception path) and SHALL NOT emit `citations` unless the markdown was finalized.
- WHEN `[n]` in markdown is not in `evidence_chunks` THEN that index SHALL be omitted from `citations[]`; the run SHALL still `done`.
- WHEN extra non-arXiv URLs appear in markdown THEN the run SHALL still `done` (no deterministic Writer fail).
- WHEN WRITE-02 would have failed (parametric fill of a missing topic) THEN the student still sees the text; RAGAS may score faithfulness low; the script SHALL still report if the triple is complete.
- WHEN `done` / `insufficient` / `error` / `gate` behave as today except for the missing `answer_complete` on success.
- WHEN follow-up is retrieve then Writer THEN the same delta/`citations` contract applies (no search).
- WHEN search/retrieve eval retries THEN those `eval` frames SHALL still appear; only Writer eval is gone.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| WSTR-01 | P1: Streamed Writer | Execute | Verified |
| WSTR-02 | P1: Streamed Writer | Execute | Verified |
| WSTR-03 | P1: Streamed Writer | Execute | Verified |
| WSTR-04 | P1: Streamed Writer | Execute | Verified |
| WSTR-05 | P1: Chainlit | Execute | Verified |
| WSTR-06 | P1: RAGAS report | Execute | Verified |
| WSTR-07 | P1: RAGAS report | Execute | Verified |

| ID | Requirement (short) |
| -- | ------------------- |
| WSTR-01 | `answer_delta` `{ "text" }` via `get_stream_writer`; concat = `writer_markdown`; no `on_chat_model_*` on the wire. |
| WSTR-02 | One `citations` `{ "citations": [...] }` after last delta; no markdown; no `answer_complete`; SSE allowlist updated. |
| WSTR-03 | Writer one-shot: no `WriterEvalStrategy`, no Writer `eval`, no Writer retry; quality does not `insufficient`. |
| WSTR-04 | Finalize `done` without `answer_complete`; pre-Writer halt still has no answer events. |
| WSTR-05 | Chainlit typewriter on deltas; side panel on `citations`. |
| WSTR-06 | RAGAS collections Faithfulness + AnswerRelevancy report from LangSmith; skip incomplete; no score threshold exit. |
| WSTR-07 | `retrieved_contexts` = post-rerank cut/expand `evidence_chunks` excerpts (Writer input), not first-stage rerank lists. |

**ID format:** `WSTR-NN`  
**Status values:** Pending → In Design → In Tasks → Implementing → Verified  

**Coverage:** 7 total, 7 mapped to tasks (`.specs/features/writer-stream-ragas/tasks.md` T1–T10). Unit gates Verified 2026-09-08. Independent Tests still UAT.

---

## Success Criteria

- [ ] In-domain SSE until `done`: `answer_delta` then `citations`, no `answer_complete`, no Writer `eval`, no LC callback event names.
- [ ] Chainlit shows growing markdown and `[n]` side panel from `citations`.
- [ ] Writer failure modes that used to retry (empty markdown, bad `[n]`, extra URL, hole fill) no longer loop; the run still ends via `done` if execute returned.
- [ ] RAGAS script prints faithfulness and answer relevancy for at least one real mapped trace; incomplete traces skipped.
