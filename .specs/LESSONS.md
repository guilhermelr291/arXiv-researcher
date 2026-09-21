# LESSONS - auto-maintained by scripts/lessons.py

> Machine-owned. Do NOT hand-edit. Changes are overwritten on the next `lessons.py` write.
> Canonical state lives in `.specs/lessons.json`. Edit lessons only via the script.
> promote_threshold=2 distinct features · window_days=45 · quarantine_threshold=2

## Confirmed (load these at Plan/Checks)

Corroborated across multiple features. Safe to apply as guidance.

_none_

## Candidates (under observation - do NOT load as guidance yet)

Seen once or not yet corroborated. Tracked, not trusted.

### L-001 - Assert the encoder class name and the Cache-Control and X-Accel-Buffering literals at the assertion, not an SSE body substring or a helper return map.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `api` · harmful: 0
- features: agui-frontend
- evidence: C32 tests/test_agent_route.py:178 (api)
- last seen: 2026-09-17T18:53:55Z

### L-002 - A screen that must call a named HTTP method and path must assert that fetch, not only that the input waits for rendered messages.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `web` · harmful: 0
- features: agui-frontend
- evidence: C45 web/lib/desk.test.tsx:86 (web)
- last seen: 2026-09-17T18:53:55Z

### L-003 - Assert the token custom property the check names on the product component, not a className regex against fixture HTML.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `web` · harmful: 0
- features: agui-frontend
- evidence: C51 web/lib/desk.test.tsx:196 (web)
- last seen: 2026-09-17T18:53:55Z

### L-004 - Assert overlay geometry the check names (side, stacking, unchanged width); a truthy computed style is not a layout proof.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `web` · harmful: 0
- features: agui-frontend
- evidence: C63 web/lib/desk.test.tsx:347 (web)
- last seen: 2026-09-17T18:53:55Z

### L-005 - Assert the token values and lengths the check names (2px, --accent, 16px, unboxed), not only CSS class presence.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `web` · harmful: 0
- features: agui-frontend
- evidence: C65 web/lib/desk.test.tsx:374 (web)
- last seen: 2026-09-17T18:53:55Z

### L-006 - Keep each check's named vitest -t title in a living test file; deleting the only file that holds those titles leaves every check unproven even when vitest exits 0.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `web` · harmful: 0
- features: web-markdown-katex
- evidence: verification.md C1-C20 no evidence (web)
- last seen: 2026-09-18T18:49:02Z

### L-007 - Assert the check's concrete counts, statuses, and identifiers in the assertion expression, not only inside a helper the assertion never reads.
- signal: `spec_precision_gap` · recurrence: 1 feature(s) · scope: `compaction` · harmful: 0
- features: chat-messages-trimming-and-summarization
- evidence: C5 (compaction)
- last seen: 2026-09-21T19:37:02Z

### L-008 - Assert a missing write on the dependency the subject is constructed with; an unused stand-in that stays empty does not prove the subject wrote nothing.
- signal: `ac_gap` · recurrence: 1 feature(s) · scope: `compaction` · harmful: 0
- features: chat-messages-trimming-and-summarization
- evidence: C35 (compaction)
- last seen: 2026-09-21T19:37:02Z

## Quarantined (failed when applied - ignore)

A confirmed lesson that recurred alongside failure. Kept for the maintainer to review.

_none_
