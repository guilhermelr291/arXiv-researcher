# Desk Markdown with GFM tables and KaTeX checks

Profile: light
Plan: `.specs/features/web-markdown-katex/plan.md`

## Intent

20 checks in 4 slices · 3 one-way doors · 0 open

## Checks

Grouped by the spec's slices; numbering runs across the whole feature.

### S1 - Finished assistant markdown keeps GFM and citations · 5 files · 40 KB · ~10k

**C1** - When Markdown `source` is a GFM pipe table with header `A` `|` `B`, a separator row, and body `1` `|` `2`, the tree contains one `table` whose `th` texts are `A` and `B` and whose `td` texts are `1` and `2` (MD-01, AC 1)
Proof: `npm --prefix web exec -- vitest run -t "gfm pipe table renders th and td"`

**C2** - When `cite` is provided, `SOURCES` contains item `n=1`, and `source` contains a shortcut `[1]` that is not a destination link, the tree contains a `button` with `aria-label` equal to `Source 1` (MD-01, AC 2)
Proof: `npm --prefix web exec -- vitest run -t "shortcut n is source button"`

**C3** - When `cite` is provided, `SOURCES` has no item `99`, and `source` contains `[99]`, the tree contains the characters `[99]` and contains no `button` with `aria-label` `Source 99` (MD-01, AC 3)
Proof: `npm --prefix web exec -- vitest run -t "unknown n is plain text"`

**C4** - When `source` contains `[docs](https://arxiv.org/abs/1)`, the tree contains an `a` whose `href` equals `https://arxiv.org/abs/1` (MD-01, AC 4)
Proof: `npm --prefix web exec -- vitest run -t "markdown link stays an anchor"`

**C5** - When `source` contains `[1](https://arxiv.org/abs/1)` and `SOURCES` contains item `n=1`, the tree contains an `a` whose `href` equals `https://arxiv.org/abs/1` and contains no `button` with `aria-label` `Source 1` (MD-01, AC 5)
Proof: `npm --prefix web exec -- vitest run -t "numeric destination link is not a cite button"`

**C6** - When `source` contains inline code whose text is `[1]` and `SOURCES` contains item `n=1`, that `[1]` is inside a `code` element and the tree contains no `button` with `aria-label` `Source 1` (MD-01, AC 6)
Proof: `npm --prefix web exec -- vitest run -t "inline code n is not a cite button"`

**C7** - When Markdown `source` is `""`, the tree contains zero of `h1`, `h2`, `h3`, `h4`, `table`, `ul`, `ol`, and `p`, table-driven over all 8 tag names (MD-01, AC 7)
Proof: `npm --prefix web exec -- vitest run -t "empty source renders none of the eight block tags"`

**C8** - The Markdown module source text does not contain the identifier `rehype-raw` (MD-01, AC 8)
Proof: `npm --prefix web exec -- vitest run -t "markdown module does not import rehype-raw"`

### S2 - KaTeX on a complete message · 2 files · 16 KB · ~4k

**C9** - When `math` is `true` and `source` is `$a+b$`, the tree contains an element with class `katex` (MD-02, AC 9)
Proof: `npm --prefix web exec -- vitest run -t "inline dollar math renders katex"`

**C10** - When `math` is `true` and `source` is a `$$` display block whose TeX is `a+b`, the tree contains an element with class `katex-display` (MD-02, AC 10)
Proof: `npm --prefix web exec -- vitest run -t "display dollar math renders katex-display"`

**C11** - When `math` is `true` and `source` is `$\\notatex$`, mounting Markdown does not throw (MD-02, AC 11)
Proof: `npm --prefix web exec -- vitest run -t "invalid tex does not throw"`

**C12** - The Markdown module source text contains the exact import `import "katex/dist/katex.min.css"` (MD-02, AC 12)
Proof: `npm --prefix web exec -- vitest run -t "markdown module imports katex min css"`

**C13** - When the `math` prop is omitted and `source` is `$a+b$`, the tree contains an element with class `katex` (MD-02, AC 13)
Proof: `npm --prefix web exec -- vitest run -t "omitted math prop still renders katex"`

### S3 - Stream does not run KaTeX · 2 files · 8 KB · ~2k

**C14** - When `Renderers` mounts an assistant block with `streaming` `true` and `content` `$a+b$`, the tree contains no element with class `katex` (MD-03, AC 14)
Proof: `npm --prefix web exec -- vitest run -t "streaming assistant does not render katex"`

**C15** - When Markdown `math` is `false` and `source` is `$a+b$`, the tree contains no element with class `katex` (MD-03, AC 15)
Proof: `npm --prefix web exec -- vitest run -t "math false leaves dollar text without katex"`

**C16** - When `Renderers` mounts an assistant block with `streaming` `false` and `content` `$a+b$`, the tree contains an element with class `katex` (MD-03, AC 16)
Proof: `npm --prefix web exec -- vitest run -t "finished assistant renders katex"`

### S4 - One RSC-safe module, one parser · 4 files · 12 KB · ~3k

**C17** - The Markdown module source text does not contain a `"use client"` directive (MD-04, AC 17)
Proof: `npm --prefix web exec -- vitest run -t "markdown module has no use client directive"`

**C18** - When `cite` is omitted and `source` contains shortcut `[1]`, the tree contains the characters `[1]` and contains no `button` with `aria-label` `Source 1` (MD-04, AC 18)
Proof: `npm --prefix web exec -- vitest run -t "omitted cite leaves shortcut n as text"`

**C19** - `web/package.json` `dependencies` contains each of `react-markdown`, `remark-gfm`, `remark-math`, `rehype-katex`, and `katex`, table-driven over all 5 names (MD-04, AC 19)
Proof: `npm --prefix web exec -- vitest run -t "package json lists the five markdown packages"`

**C20** - `web/components/renderers.tsx` contains neither `renderMarkdown` nor `parseBlocks`, table-driven over both identifiers (MD-04, AC 20)
Proof: `npm --prefix web exec -- vitest run -t "assistant renderer does not call homemade parser"`

## Coverage

| Set (size) | Member -> proof | Unproven |
| --- | --- | --- |
| Landing doors (3) | npm stack C12, C19 · cite after GFM C2 · math gated C15 | - |
| empty `source` forbidden tags (8) | C7, table-driven over all 8 | - |
| citation shapes (6) | shortcut C2 · unknown C3 · `[label](url)` C4 · `[n](url)` C5 · inline code C6 · `cite` omitted C18 | - |
| math plugin outcomes (5) | inline `$` C9 · display `$$` C10 · invalid TeX C11 · `math` omitted C13 · `math` false C15 | - |
| assistant `streaming` (2) | `true` C14 · `false` C16 | - |
| npm `web/` named packages (5) | C19, table-driven over all 5 | - |
| homemade parser identifiers (2) | C20, table-driven over all 2 | - |

- Claims naming a DOM tag, class, `aria-label`, `href`, or throw: C1–C7, C9–C11, C13–C16, C18 - each has a proof that mounts Markdown or `Renderers`
- File-text claims (import, directive, package names, identifiers): C8, C12, C17, C19, C20
- No other check claims more than the single case its proof exercises

## Swept

- validation: C3, C7
- failure modes: C11
- idempotency: n/a - Markdown is a pure function of `source` and props; no delivery id
- authorization: n/a - no auth in v1
- concurrency: C14, C16
- data lifecycle: n/a - answers stay strings; no stored shape
- dependency failure: C11
- state transitions: C14, C16
- observability: n/a - no logging requirement in this slice

## Handoff

Intended split, with the arithmetic, written before any code:

- S1–S4 ≈ 76 KB · ~19k (Markdown module, `renderers.tsx`, `citations.ts`, homemade parser removal, `desk.test.tsx` / Markdown tests, `web/package.json`) — under 150k; one builder, no handoff

- **Boundary:** C1–C20 closed locally (no commit — AGENTS.md defers tlc-spec-lean build commits)
- **Settled mid-build:** CommonMark does not emit a shortcut `linkReference` for dangling `[n]`; appended Landing door 4 (text-node split after GFM) without rewriting door 2
- **Abandoned:** first cite plugin that only rewrote `linkReference` — the mdast for `See [1]` is a single `text` node
