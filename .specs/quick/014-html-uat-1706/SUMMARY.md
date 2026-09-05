# Summary: 014 HTML UAT on 1706.03762 v7

**Date:** 2026-09-03
**Status:** Done

## What changed

Closed structured-aware Independent Tests using `1706.03762` v7 as the canonical paper. Live check: `.specs/quick/014-html-uat-1706/verify.py` against cached pgvector rows + hybrid retrieve. Writer evidence from LangSmith `01a06917-e169-73f1-992c-ef624783dee9`. Spec/ROADMAP/STATE/tasks updated. Missing-HTML hole path was not re-run. Chainlit side panel was not re-clicked; Citation excerpts are the same expanded strings.

## Verification

- Ingest: 38 chunks; `[EQUATION:S3.E1]` in prose; no `figure`; `S6.T3` 902 tokens; label in `embedding_text`; `paper_has_chunks` true
- Retrieve (a)(c)(d): E1 TeX in excerpt; Table 2 markdown with 28.4; k=5
- Retrieve (b): first excerpt TeX, second `Equation ((1))` label
- Search `id:1706.03762` hits the original paper

## Commit

(not created — commit when asked)
