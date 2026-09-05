# Quick Task 014: HTML retrieve UAT on 1706.03762 v7

**Date:** 2026-09-03
**Status:** Done

## Description

Close structured-aware HTML Independent Tests using `1706.03762` v7 as the canonical paper (ingest in DB, hybrid retrieve, expansion, Writer evidence from LangSmith `01a06917-e169-73f1-992c-ef624783dee9`).

## Files Changed

- `.specs/features/structured-aware-chunking/spec.md` — Independent Tests / traceability UAT
- `.specs/project/STATE.md` — quick task + UAT todo
- `.specs/project/ROADMAP.md` — milestone UAT status

## Verification

- [x] Ingest Independent Test against cached `1706.03762` v7 rows
- [x] Retrieve Independent Test (a)(b)(c)(d) via hybrid pack/expand
- [x] Cache hit: `paper_has_chunks` is true (no HTML refetch on the walk)
- [x] Writer: prior trace quotes E1 TeX and Table 2 BLEU with expanded excerpts

## Commit

(not created — commit when asked)
