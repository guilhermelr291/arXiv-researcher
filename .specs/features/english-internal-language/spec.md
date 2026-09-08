# English Internal Language Specification

**Feature:** `english-internal-language`  
**Spec status:** Implemented 2026-09-06 (prompt/schema locks; live UAT pending)  
**Date:** 2026-09-06  
**Parent:** AD-004 / PROJECT.md (project artifacts in English; student-facing answers follow the query language)  
**Trigger:** LangSmith trace `01a0786a-ba4b-74f0-8a12-685eccf10738` — planner `task`, eval `feedback`, and Voyage rerank query were Portuguese because the student asked in Portuguese.

This spec locks **working language** of the graph. It does not change routing, admission, retrieve cut, SSE event names, or Writer `[n]` shape.

## Problem Statement

Prompts are English, but they never tell the planner or judges to *emit* English. The model then mirrors the student query: Portuguese `task` → Portuguese eval → Portuguese Voyage query. Rerank prefers overview prose that matches that long Portuguese instruction over methodology equations. AD-004 already required English internals; the runtime drifted.

## Goals

- [x] Plan `task` / `reasoning`, eval `feedback` / `reasoning`, search/retrieve formulate, and the Voyage rerank query (task + retry feedback) are English even when the student query is not.
- [x] Writer `markdown` (and gate student-facing `reason`) match the query language from `gate.language`.

## Out of Scope

| Feature | Reason |
| ------- | ------ |
| Chainlit chrome / `chainlit_pt-BR.md` | UI i18n is not the agent loop |
| Translating paper titles, abstracts, or chunk `content` | Evidence stays as ingested |
| A second LLM call to translate plan/eval for the UI | Plan and eval stay English in SSE |
| Changing Voyage model, `cut_reranked`, or formulated hybrid query rules | Parent retrieve spec |
| Translating `insufficient` beyond whatever English eval feedback already is | Eval is internal |

---

## User Stories

### P1: Internal English, answer in query language ⭐ MVP

**User Story**: As a student who asks in any language, I want the researcher to plan, search, retrieve, rerank, and evaluate in English, and to write the final answer in my language, so retrieval matches English papers and the answer is still readable for me.

**Why P1**: Direct product rule (AD-004). Portuguese internals already hurt rerank on a methodology question.

**Acceptance Criteria**:

1. WHEN the student query is not English THEN the planner SHALL emit English `task` and `reasoning` for every step.
2. WHEN search, retrieve, or writer eval runs THEN `feedback` (and search-wave `reasoning`) SHALL be English.
3. WHEN retrieve reranks THEN the Voyage query SHALL be the English retrieve `task` (plus English step feedback on retry).
4. WHEN the writer runs THEN `writer_markdown` SHALL match `gate.language` / the student query language, even if the current writing task is English.
5. WHEN the gate refuses THEN `reason` SHALL match the query language (student-facing). WHEN the gate allows THEN `reason` MAY match the query language.

**Independent Test**: Portuguese methodology question on a cached paper. LangSmith: planner tasks English; `rerank` input `query` English; `answer_complete` markdown Portuguese.

---

## Edge Cases

- WHEN the student query is already English THEN internals and answer SHALL both be English.
- WHEN `gate.language` is empty THEN the writer SHALL still match the student query language from the query text.
- WHEN writer eval retries THEN feedback SHALL stay English; the writer SHALL keep answering in the query language.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| LANG-01 | P1: planner English task/reasoning | Execute | Verified |
| LANG-02 | P1: eval feedback/reasoning English | Execute | Verified |
| LANG-03 | P1: writer markdown = query language | Execute | Verified |
| LANG-04 | P1: gate reason = query language | Execute | Verified |
| LANG-05 | P1: rerank query inherits English task | Execute | Verified |

**Coverage:** 5 total, mapped to prompt/schema locks (no separate tasks.md).

---

## Success Criteria

- [x] Structured-output field descriptions state English for plan/eval strings.
- [ ] A non-English query produces English plan + eval in LangSmith; writer markdown in the query language.
