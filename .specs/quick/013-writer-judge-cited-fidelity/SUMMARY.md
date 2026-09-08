# Summary: 013 Writer judge cited fidelity

**Date:** 2026-09-03
**Status:** Done

## What changed

The writer LLM checklist now passes when student-requested facts are already cited with living `[n]`. It must not retry to rephrase, add headings, pick one canonical number, or expand a caveat when the evidence already lists two conflicting values and the markdown states both. WRITE-02 parametric-fill fail language is unchanged. Retry remains for missing facts, uncited claims, or hole-rule violations.

## Verification

- Checklist contains no-retry-for-cited-fidelity rules and still mentions parametric fill: `ok`

## Commit

(not created — commit when asked)
