# Structured-Aware Chunking Specification

**Feature:** `structured-aware-chunking`  
**Spec status:** Implemented (Execute T1–T19 2026-09-03). Manual UAT still pending (B-001).  
**Date:** 2026-09-02  
**Gray areas:** Resolved in grill-me 2026-09-02; `discuss.md` skipped  
**Parent admission:** `.specs/features/admission-retrieve-per-topic/spec.md` (approved)  
**Parent loop:** `.specs/features/orchestrator-eval-replan/spec.md` (approved)  
**Parent product:** `.specs/features/arxiv-grounded-research/spec.md` (approved v1)  
**Architecture constraints:** `.specs/features/arxiv-grounded-research/context.md` (PAT-01–PAT-12 still apply)  
**Parser CLI:** `scripts/arxiv_html_units.py` (debug wrapper over `ingest/html_parse.py`)  
**Design:** `.specs/features/structured-aware-chunking/design.md` (executed)  
**Tasks:** `.specs/features/structured-aware-chunking/tasks.md` (T1–T19 executed 2026-09-03)

This spec defines **only** how retrieve **ingests** arXiv HTML, how prose and atomic units are stored, and how hybrid retrieve **expands** placeholders into Writer/UI excerpts. Gate, search (titles+abstracts, no full text), admission 1/topic, U1, T1/T2a/T3 routing, hybrid **weights** 0.7/0.3, `FormulatedQuery`, SSE event **names**, Chainlit, checkpointer, models, `max_steps=8`, `max_papers=8`, `max_retries_per_step=1`, `max_replans=1`, timeout, Writer `[n]` **format**, and `Citation` **fields** stay as in the parent specs unless an ID below explicitly supersedes them.

## Problem Statement

Retrieve today loads arXiv **PDFs** with `ArxivLoader` and splits the dumped text with tiktoken `RecursiveCharacterTextSplitter` (512/50). The Writer never sees which section a passage came from, and tables, display equations, and figures are shredded or dropped. Students asking about a BLEU row or the attention formula get prose fragments instead of the atomic element. HTML on `arxiv.org/html/{id}v{version}` already has that structure; a validated spike extracts it. This feature replaces PDF ingest with structured HTML ingest and placeholder-aware retrieve.

## Goals

- [ ] Retrieve ingest uses arXiv HTML only. Cache miss fetches HTML, not PDF. Existing local PDF chunks are wiped.
- [ ] Prose chunks keep section identity; tables and display equations are atomic rows that are never split.
- [ ] Hybrid retrieve still runs **per admitted paper**, returns **at most 5** packed hits, and inlines full tables/equations into those excerpts without spending extra `[n]` slots.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| Image / figure units, PNG/SVG download, vision embeddings | Explicit cut: tables + equations only |
| LLM-generated summaries of units | Grill-me: extractive / caption heuristics; query-side `FormulatedQuery` already paraphrases |
| PDF fallback when HTML is missing | Grill-me Q1-A; omit the paper (ranked_keys fallback still applies) |
| Dual PDF+HTML corpus, `ingest_source` column | Local wipe; HTML-only from here |
| Separate `units` table / LangChain PGVectorStore / ParentDocumentRetriever | One `chunks` table; summary/vector vs body via `embedding_text` + `content` |
| New SSE event names, `Citation` extra fields (`kind`, `section`) | Parent contract; excerpt carries the expanded body |
| Changing Gate, search API, admission U1, T1/T2a/T3 **routing**, hybrid **weights**, Writer `[n]` **shape** | Parent |
| Graph node / execute-dispatch changes | Ingest stays in retrieve + adapters + repo (PAT-01) |
| Global semantic search over the full library | Parent RAG scope |
| Production migration / dual-write | Local only; recreate schema |

### Supersedes (parent specs)

Upon approval, these IDs are **replaced** by this feature (do not implement both). Unnamed parent IDs stay in force.

| Parent ID | What no longer holds |
| --------- | -------------------- |
| ARX-01 (retrieve load) | Retrieve ingest uses LangChain `ArxivLoader` PDF. **Unchanged:** search still uses LangChain arXiv **search** tools; no other search vendors. |
| ARX-03 (cache miss) | Miss downloads **PDF**, hit skips PDF. **Unchanged:** unique `(arxiv_id, version)`; RAG only over selected papers. |
| RETR-02 (`k`) | `retrieve_k_per_paper=3` and post-ensemble slice **3**. **Unchanged:** one hybrid call per usable paper; concat in admission order; continuous `[n]`; no union `LIMIT k`; follow-up without current-plan searches hybrid over thread `papers` only. |
| RETR-03 (walk) | First usable **PDF** per ranking; empty PDF ≠ arXiv miss. **Unchanged:** walk `ranked_keys` in the same execute; T3 retry does not re-walk exhausted keys; at most one usable paper per ranking. |
| Product spec out-of-scope row “Full-text from arXiv TeX/HTML” | v1 used PDF; this feature makes HTML the retrieve source. |
| Quick 011 (scope) | 512/50 tiktoken applies to the **whole PDF text**. **Unchanged:** `Policy.chunk_size=512`, `chunk_overlap=50`, `chunk_encoding=cl100k_base` still apply to **prose inside a section**. |

**Amended (not replaced):** RETR-04 / T1 / T2a / T3 / WRITE-02 still apply; wording “PDF” in those stories means **HTML ingest** (empty/missing HTML is the ingest failure). LOOP-04/05, ADM-01–04, SEARCH formulate, GROUND-01–03 unchanged.

**Locked knobs (grill-me, not reopened in Design):**

- No LLM at ingest for unit descriptions.
- Equation `embedding_text` is extractive: section path + window `min(containing subsection, 200 tiktoken tokens)` around the placeholder + tag + TeX.
- Table `embedding_text` is caption + header row + first two data rows.
- Ensemble **overfetch** at least `3 × retrieve_k_per_paper` candidates per paper, then pack to 5 unique.
- Parser runs **in memory** in the retrieve path; MUST NOT write `_tmp_arxiv_html` (CLI spike MAY remain as a debug wrapper).

---

## User Stories

### P1: Structured HTML ingest ⭐ MVP

**User Story**: As a student, I want evidence taken from the paper’s HTML structure so that tables and display equations stay whole and I can tell which section a passage came from.

**Why P1**: PDF splitter is why structure is lost. Without this story there is nothing to retrieve.

**Acceptance Criteria**:

1. WHEN retrieve has a cache miss for `(arxiv_id, version)` THEN the system SHALL fetch `https://arxiv.org/html/{arxiv_id}v{version}` (or the equivalent arXiv HTML URL used by the spike) and SHALL NOT call `ArxivLoader` / download the PDF. Sync HTTP/parse SHALL run off the event loop (`asyncio.to_thread` or equivalent).
2. WHEN HTML is parsed THEN the system SHALL extract display **equations** and **tables** as atomic units and residual **prose** as markdown. Inline math SHALL remain `$tex$` inside prose or table markdown and SHALL NOT become equation units. Layout-only `ltx_tabular` tables (empty after dropping zero-width `ltx_rule` spacers) SHALL be discarded, not stored.
3. WHEN a `figure.ltx_table` wraps an inner table THEN the system SHALL collapse it to **one** `table` unit: caption from the figure, body from the inner tabular markdown. WHEN a `figure.ltx_figure` (image) is found THEN the system SHALL splice its caption into the prose as plain text and SHALL NOT create a unit, SHALL NOT download assets, and SHALL NOT leave a `[FIGURE:…]` placeholder.
4. WHEN prose is emitted THEN each atomic table/equation SHALL be replaced by a canonical placeholder `[TABLE:{html_id}]` or `[EQUATION:{html_id}]` (`html_id` is the element id from the HTML, unique within the paper). The production retrieve path SHALL persist units and chunks to Postgres only, not to disk sidecars.
5. WHEN prose is split THEN the system SHALL split on markdown headings first. WHEN a section exceeds `Policy.chunk_size` (512 tiktoken tokens, `cl100k_base`) THEN it SHALL apply `RecursiveCharacterTextSplitter` **inside that section only** with `Policy.chunk_overlap` (50). Tables and equations SHALL never be split, including bodies larger than 512 tokens.
6. WHEN rows are persisted THEN `chunks` SHALL store, per row: `kind` (`prose` \| `table` \| `equation`); `unit_id` (HTML id for atomics, NULL for prose); `embedding_text` (what is embedded); `content` (what BM25 and expansion use); `embedding vector(1536)`; `metadata` JSONB with **exactly** `section` (heading path), `caption` (string, may be empty), `unit_ids` (ordered placeholder ids in this chunk; for an atomic row, `[self]`). Identity of an atomic unit SHALL be `(arxiv_id, version, unit_id)`.
7. WHEN `embedding_text` is built for **prose** THEN each placeholder SHALL be replaced by a label `Equation ({tag})` or `Table {n}: {caption}` (tag/caption from the unit; empty caption → label without the trailing clause). `content` for prose SHALL **keep** the canonical placeholders.
8. WHEN `embedding_text` is built for a **table** THEN it SHALL be caption + header row + first two data rows. WHEN for an **equation** THEN it SHALL be section path + extractive window (locked knob) + tag + TeX. No LLM call SHALL be used to write these strings.
9. WHEN `content` is built for an atomic row THEN it SHALL be a caption/tag line plus the full body (table markdown or TeX). The body SHALL NOT be truncated.
10. WHEN HTML is missing, non-HTML, or parses to unusable empty prose **and** no units THEN that key SHALL be treated as an ingest failure: try the **next** `ranked_keys` entry in the same execute (amended RETR-03). It SHALL NOT fall back to PDF. A paper with zero stored chunks SHALL NOT be usable (parent: omit from hybrid concat).
11. WHEN `(arxiv_id, version)` already has HTML-derived chunks THEN retrieve SHALL skip the fetch and SHALL use stored rows (amended ARX-03).
12. WHEN this feature is deployed locally THEN existing PDF `chunks` (and papers that only exist for that corpus, as needed) SHALL be wiped and `chunks` recreated for the new columns. The PDF ingest code path in retrieve SHALL be removed, not left as dead fallback.

**Independent Test**: Ingest `1706.03762` v7 from HTML (fixture or live). Assert: prose contains `[EQUATION:S3.E1]`; inner result tables are `kind=table` with caption from the wrapping `ltx_table`; no `figure` rows; no PNG files written; `S6.T3` (or equivalent) body stored whole even if `>512` tokens; layout spacers absent; `embedding_text` of a prose chunk containing E1 uses a human label, not `[EQUATION:S3.E1]`; cache hit does not refetch HTML.

---

### P1: Placeholder-aware retrieve ⭐ MVP

**User Story**: As a student, I want retrieved passages to include the actual table or equation they refer to so that I can check a number or a formula against the paper, not against a torn sentence.

**Why P1**: Ingest without expansion still hides tables behind placeholders. This is the student-visible slice.

**Acceptance Criteria**:

1. WHEN `Policy` is read THEN `retrieve_k_per_paper` SHALL be **5**. The system SHALL still call hybrid once per usable paper and SHALL concatenate in admission order with continuous `[n]`. It SHALL NOT use a union `LIMIT k` across papers.
2. WHEN hybrid runs THEN the vector leg SHALL rank on embeddings of `embedding_text`. The BM25 leg SHALL index `content`. Both **prose** and **atomic** rows SHALL participate in the same per-paper index.
3. WHEN candidates are packed THEN the system SHALL overfetch at least `3 × retrieve_k_per_paper` ensemble hits per paper, drop later rows that repeat an atomic `unit_id` already covered by a kept prose hit (or a kept atomic hit), **backfill** from the remaining ranked list until **5 unique** hits (or the list is exhausted), then stop. Duplicate atomic+prose of the same unit SHALL NOT both occupy slots.
4. WHEN a kept hit is **prose** THEN the system SHALL expand placeholders **in place** in the excerpt: the **first** occurrence of each `unit_id` in **rank order across the five hits** SHALL be replaced by that unit’s full `content` (never truncated, never split). Later prose hits that mention the same `unit_id` SHALL replace the placeholder with the **label only** (same label rules as ingest `embedding_text`). Expansion SHALL NOT add extra `[n]` slots and SHALL NOT count against `k`.
5. WHEN a kept hit is **atomic** THEN the excerpt SHALL be `metadata.section` plus that row’s `content` (caption/tag already in `content`). No further placeholder expansion is required.
6. WHEN the Writer and `Citation.excerpt` / Chainlit side panel are built THEN they SHALL use the **same** expanded excerpt string. `Citation` fields SHALL NOT gain `kind` or `section` in this feature.
7. WHEN a paper contributes fewer than 5 unique hits THEN the system SHALL return that many (parent tiny-document rule). WHEN a paper has zero chunks THEN it SHALL be omitted from concat (not usable).

**Independent Test**: After ingesting `1706.03762` v7: (a) formulated query about scaled dot-product attention returns a prose `[n]` whose excerpt contains the E1 TeX, not `[EQUATION:S3.E1]`; (b) query that ranks the same unit twice (prose + atomic, or two overlapping prose chunks) shows the full body once and a label the second time; (c) query about a BLEU / variation table inlines the **full** markdown table in some `[n]` even if the table is `>512` tokens; (d) each usable paper contributes at most 5 `[n]` blocks after concat.

---

## Edge Cases

- WHEN HTML returns 404 / 403 / empty LateXML THEN the system SHALL treat it as ingest failure for that key and SHALL continue the `ranked_keys` walk. It SHALL NOT download PDF.
- WHEN a section has no heading (preamble) THEN the system SHALL treat it as one section with `metadata.section` empty or a documented fallback such as `"Preamble"`, then split at 512 if needed.
- WHEN overlap-50 causes the same placeholder to appear in two prose chunks and both are in the top unique 5 THEN only the earlier-ranked excerpt SHALL contain the full unit body (P1 retrieve AC4).
- WHEN one prose chunk references several units THEN all of them SHALL expand (full body if first global occurrence of that `unit_id`, else label). `k` SHALL remain 5 hits, not 5+N.
- WHEN table markdown is malformed or wider than the Writer context THEN the system SHALL still inject it whole. This feature SHALL NOT truncate tables to protect the context window.
- WHEN `unit_ids` in metadata disagree with placeholders in `content` THEN expansion SHALL trust placeholders in `content` (source of truth) and MAY use `unit_ids` only as an aid.
- WHEN `html_id` collides across papers THEN lookup SHALL always include `(arxiv_id, version)`.
- WHEN search admits a paper that has no HTML THEN T2a/T1/WRITE-02 SHALL apply as today (hole / fallback walk), with “no usable paper” meaning no usable **HTML**.

---

## Requirement Traceability

Each requirement gets a unique ID for tracking across design, tasks, and validation.

| Requirement ID | Story | Phase | Status |
| -------------- | ----- | ----- | ------ |
| HTML-01 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| HTML-02 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| PARSE-01 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| PARSE-02 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| PARSE-03 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| SPLIT-01 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| STORE-01 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| EMB-02 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| RETR-05 | P1: Placeholder-aware retrieve | Execute | ✅ Verified (code); ⏳ UAT |
| RETR-06 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |
| RETR-07 | P1: Placeholder-aware retrieve | Execute | ✅ Verified (code); ⏳ UAT |
| RETR-08 | P1: Placeholder-aware retrieve | Execute | ✅ Verified (code); ⏳ UAT |
| RETR-09 | P1: Placeholder-aware retrieve | Execute | ✅ Verified (code); ⏳ UAT |
| MIG-01 | P1: Structured HTML ingest | Execute | ✅ Verified (code); ⏳ UAT |

**ID map (normative behavior):**

- **HTML-01** — Retrieve ingest source is arXiv HTML only; no `ArxivLoader` / PDF in retrieve.
- **HTML-02** — Cache hit on `(arxiv_id, version)` skips HTML fetch; miss fetches and upserts.
- **PARSE-01** — Display equations and tables are atomic units; inline math stays `$tex$`; layout `ltx_rule` tables discarded.
- **PARSE-02** — `ltx_table` figures collapse to one table unit; image figures become caption text; no assets, no `[FIGURE:…]`.
- **PARSE-03** — Prose `content` uses `[TABLE:{id}]` / `[EQUATION:{id}]`; retrieve path does not write disk sidecars.
- **SPLIT-01** — Heading split, then 512/50 only inside a section; never split atomics.
- **STORE-01** — `kind`, `unit_id`, `embedding_text`, `content`, `metadata {section, caption, unit_ids}`; atomic identity `(arxiv_id, version, unit_id)`.
- **EMB-02** — Prose vectors use labels in `embedding_text`; table/equation vectors use locked heuristics/extractive window; no ingest LLM; atomic `content` = caption/tag + full body.
- **RETR-05** — `retrieve_k_per_paper=5`; per-paper hybrid; concat; continuous `[n]`; no union `k`.
- **RETR-06** — Walk `ranked_keys`; first usable **HTML** ingest; empty/missing HTML ≠ arXiv miss; no PDF fallback.
- **RETR-07** — In-place expansion; first ranked occurrence of a `unit_id` gets full `content`; later prose gets label only; expansion does not consume `k`.
- **RETR-08** — Mixed index; vector on `embedding_text`, BM25 on `content`; overfetch ≥3×k; dedup `unit_id`; backfill to 5 unique.
- **RETR-09** — Atomic hit excerpt = section + `content`; Writer and Citation/UI share the expanded excerpt; no new Citation fields.
- **MIG-01** — Wipe local PDF chunks; recreate `chunks` schema; delete retrieve PDF path.

**Coverage:** 14 total, 14 mapped to stories, 0 unmapped. Execute T1–T19 2026-09-03. Independent Tests / live UAT still pending (B-001).

---

## Success Criteria

- [ ] Cache-miss retrieve of a paper with arXiv HTML stores section-aware prose plus atomic table/equation rows; no PDF download; no image files.
- [ ] Writer `[n]` list is at most 5 excerpts per usable paper, with placeholders expanded (full table/equation once per `unit_id` in that paper’s packed hits).
- [ ] A question about a table metric or a named display equation can be evidenced by the **full** element in some citation excerpt.
- [ ] Paper without HTML is skipped via `ranked_keys` fallback or becomes a WRITE-02 hole; the run does not fetch PDF.
- [ ] Search, admission 1/topic, T1/T2a/T3 routing, Gate, SSE names, and Writer `[n]` numbering format are unchanged.

---

## Confirm before Execute

Executed 2026-09-03 (`tasks.md` T1–T19). Manual UAT of Independent Tests (`1706.03762` v7) still pending (B-001).
