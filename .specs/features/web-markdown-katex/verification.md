# Desk Markdown with GFM tables and KaTeX verification

**Verdict**: FAIL
**Profile**: light
**Diff range**: 802bb20..working-tree
**Round**: 1 - full
**Verifier**: independent sub-agent (author != verifier)

Existence search (working tree): `Test-Path web/components/Markdown.test.tsx` is false. Grep of each exact `-t` title in `web/**/*.{ts,tsx}` returned zero hits. Titles appear only in `checks.md` (plus the leftover check string `unknown n is plain text` in `.specs/features/agui-frontend/checks.md`, not as a living test). `desk.test.tsx` still has overlapping cases under different titles (`markdown renders headings lists tables and cites`, `matching n is source button links stay links`); those titles are not the checks' proofs and did not run under the named filters. This slice also **deleted** the previous `it("unknown n is plain text")` from `desk.test.tsx`.

One batched invocation covering all 20 titles (verbose reporter). Result: **0 tests ran**, 34 skipped (entire `desk.test.tsx` file skipped), exit 0. No named title appeared as having run. A filter matching nothing is FAIL per check.

## Checks

| Check | Claim | Proof run | Evidence | Result |
| --- | --- | --- | --- | --- |
| C1 | GFM pipe table renders `th` A,B and `td` 1,2 | `npm --prefix web exec -- vitest run -t "gfm pipe table renders th and td"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C2 | shortcut `[1]` is `button` aria-label `Source 1` | `npm --prefix web exec -- vitest run -t "shortcut n is source button"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C3 | unknown `[99]` is text, no `Source 99` button | `npm --prefix web exec -- vitest run -t "unknown n is plain text"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C4 | `[docs](url)` stays an `a` with that href | `npm --prefix web exec -- vitest run -t "markdown link stays an anchor"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C5 | `[1](url)` is an `a`, not a cite button | `npm --prefix web exec -- vitest run -t "numeric destination link is not a cite button"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C6 | inline code `[1]` stays in `code`, no cite button | `npm --prefix web exec -- vitest run -t "inline code n is not a cite button"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C7 | empty `source` renders none of the eight block tags | `npm --prefix web exec -- vitest run -t "empty source renders none of the eight block tags"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C8 | Markdown module source has no `rehype-raw` | `npm --prefix web exec -- vitest run -t "markdown module does not import rehype-raw"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C9 | `math` true + `$a+b$` renders `.katex` | `npm --prefix web exec -- vitest run -t "inline dollar math renders katex"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C10 | `math` true + `$$` display renders `.katex-display` | `npm --prefix web exec -- vitest run -t "display dollar math renders katex-display"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C11 | invalid TeX `$\\notatex$` does not throw | `npm --prefix web exec -- vitest run -t "invalid tex does not throw"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C12 | module contains `import "katex/dist/katex.min.css"` | `npm --prefix web exec -- vitest run -t "markdown module imports katex min css"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C13 | omitted `math` still renders `.katex` for `$a+b$` | `npm --prefix web exec -- vitest run -t "omitted math prop still renders katex"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C14 | streaming assistant renders no `.katex` | `npm --prefix web exec -- vitest run -t "streaming assistant does not render katex"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C15 | `math={false}` leaves `$a+b$` without `.katex` | `npm --prefix web exec -- vitest run -t "math false leaves dollar text without katex"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C16 | finished assistant (`streaming` false) renders `.katex` | `npm --prefix web exec -- vitest run -t "finished assistant renders katex"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C17 | Markdown module has no `"use client"` directive | `npm --prefix web exec -- vitest run -t "markdown module has no use client directive"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C18 | omitted `cite` leaves shortcut `[1]` as text | `npm --prefix web exec -- vitest run -t "omitted cite leaves shortcut n as text"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C19 | `web/package.json` lists the five markdown packages | `npm --prefix web exec -- vitest run -t "package json lists the five markdown packages"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |
| C20 | assistant renderer does not call homemade parser | `npm --prefix web exec -- vitest run -t "assistant renderer does not call homemade parser"` — 0 ran (exit 0, 34 skipped) | no evidence | FAIL |

## Coverage

Profile `light` did not recompute Coverage from authority.

## Swept existing

`checks.md` Swept rows resolve to check ids (C3, C7, C11, C14, C16) or `n/a`, not to **existing**. Re-read against the working tree anyway for the plan Observable landings marked existing:

- `.assistant-text` type/table/gap rules still in `web/app/globals.css:322` (table rules at `:420`).
- Citation hover 150 ms / stay 300 ms still in `web/components/Citation.tsx:14-15` (`OPEN_DELAY_MS` / `CLOSE_DELAY_MS`).
- `npm --prefix web exec -- vitest run` still the front gate (`web/package.json` script `test`).

Those constraints are present. They do not settle C1–C20.

## Gate

```
npm --prefix web exec -- vitest run --reporter=verbose -t "<C1|…|C20 titles>"
```

0 passed, 0 failed, 34 skipped, exit 0. None of the twenty named titles appeared as having run. Vitest treated a non-matching `-t` as skip-all (green). That is not proof.

## Ranked gaps

1. C1 — no evidence (`web/components/Markdown.test.tsx` absent; title `gfm pipe table renders th and td` not in `web/**/*.{ts,tsx}`)
2. C2 — no evidence (title `shortcut n is source button` not in tree; `desk.test.tsx:387` title is `matching n is source button links stay links`, not the named proof)
3. C3 — no evidence (title `unknown n is plain text` removed from `desk.test.tsx` in this diff; file no longer contains the test)
4. C4 — no evidence (title `markdown link stays an anchor` not in tree)
5. C5 — no evidence (title `numeric destination link is not a cite button` not in tree)
6. C6 — no evidence (title `inline code n is not a cite button` not in tree)
7. C7 — no evidence (title `empty source renders none of the eight block tags` not in tree)
8. C8 — no evidence (title `markdown module does not import rehype-raw` not in tree)
9. C9 — no evidence (title `inline dollar math renders katex` not in tree)
10. C10 — no evidence (title `display dollar math renders katex-display` not in tree)
11. C11 — no evidence (title `invalid tex does not throw` not in tree)
12. C12 — no evidence (title `markdown module imports katex min css` not in tree)
13. C13 — no evidence (title `omitted math prop still renders katex` not in tree)
14. C14 — no evidence (title `streaming assistant does not render katex` not in tree)
15. C15 — no evidence (title `math false leaves dollar text without katex` not in tree)
16. C16 — no evidence (title `finished assistant renders katex` not in tree)
17. C17 — no evidence (title `markdown module has no use client directive` not in tree)
18. C18 — no evidence (title `omitted cite leaves shortcut n as text` not in tree)
19. C19 — no evidence (title `package json lists the five markdown packages` not in tree)
20. C20 — no evidence (title `assistant renderer does not call homemade parser` not in tree)
