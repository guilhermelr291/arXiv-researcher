# Desk Markdown with GFM tables and KaTeX

Sources:

- conversation 2026-09-18 (user brief: reusable Next.js Markdown, `react-markdown`, `remark-gfm`, `remark-math`, `rehype-katex`, KaTeX CSS)
- grill-me 2026-09-18 this conversation - replace assistant homemade parser (1-A); `math={!streaming}` (2-B); module without `"use client"`, CSS in the module (3-A); cite via post-GFM `linkReference` (4-A); no `rehype-raw`; Writer prompt unchanged; `$` / `$$` only
- `.specs/features/agui-frontend/plan.md` AC 60–64, 65 - citation buttons, unknown `[n]` as text, links stay links, no sources list after the answer, assistant text has no container
- `src/plan_based_researcher/ingest/html_parse.py` `_rewrite_inline_math` / `_equation_tex` - evidence already uses `$tex$` inline and `$$\n...\n$$` display
- https://github.com/remarkjs/remark-math - `remark-math` `singleDollarTextMath` default true; `rehype-katex` Options omit `displayMode` and `throwOnError`; output elements use class `katex`
- https://katex.org/docs/api.html - invalid TeX throws unless the renderer suppresses it; CSS from the `katex` package, not a CDN
- `.specs/project/STATE.md` AD-029 - `web/` HTTP-only desk; `[n]` is thread-scoped SOURCES

## Problem

The student reads Writer markdown in the desk through a line-oriented parser (`web/lib/markdown.tsx`). That parser understands a subset of GFM tables and inline marks, and it is the only implementation of the citation contract (`[n]` → source button). It does not parse `$` / `$$` TeX. Evidence chunks already contain those delimiters from HTML ingest, and the Writer copies them into the answer, so a methodology answer shows raw TeX instead of a formula.

The same parser is not GitHub-flavored Markdown: task lists, strikethrough, and table edge cases diverge from what `remark-gfm` would produce, and there is no module a Server Component can import.

Evidence in the source: none quantified; the brief names the missing capabilities (GFM tables via `remark-gfm`, inline and display math via KaTeX).

When this ships, a finished assistant message shows GFM tables and KaTeX for `$` / `$$`, `[n]` is still a source button, and while tokens stream the student still sees growing prose without a half-open `$` swallowing the paragraph.

## Out of scope

| Excluded | Why |
| --- | --- |
| Writer prompt / delimiter change (`\(`, `\[`, `\begin{equation}`) | grill-me: ingest already emits `$` / `$$`; this slice is the desk |
| `rehype-raw` / HTML-in-markdown | grill-me: Writer does not emit HTML; raw would XSS packed excerpts |
| MathJax, `rehype-mathjax`, KaTeX auto-render on `document.body` | brief pins `rehype-katex` |
| Buffering the assistant until `TEXT_MESSAGE_END` | grill-me 2-C rejected; typewriter stays |
| KaTeX on every `TEXT_MESSAGE_CONTENT` delta | grill-me 2-A rejected; incomplete `$` breaks the tree |
| Dark-mode KaTeX theme / token overrides | grill-me default: inherit `.assistant-text` `color` |
| Extra CSS for GFM task lists / strikethrough | grill-me default: plugin output only |
| Changing `Citation` hover (150 ms) / stay (300 ms) / source panel | AG-UI AC 62–63 unchanged; Markdown only calls the existing `CiteRenderer` |
| Python gate, Writer, ingest, AG-UI wire | front-only; `web/` remains HTTP-only (AD-029) |
| Auth, HITL, Dockerised UI | AGENTS.md out of v1 |

## Assumptions

| Assumption | Chosen default | Rationale | Confirmed? |
| --- | --- | --- | --- |
| Assistant path | `Renderers` assistant case mounts Markdown; `parseBlocks` / `renderMarkdown` are removed | grill-me 1-A | y |
| Stream vs math | `math={!block.streaming}` | grill-me 2-B | y |
| Module shape | `web/components/Markdown.tsx` (or equivalent under `web/`), no `"use client"`, `import "katex/dist/katex.min.css"` in that module; props `source`, `math?` default `true`, `cite?` | grill-me 3-A | y |
| Cite mechanism | remark plugin after `remark-gfm`: numeric shortcut `linkReference` → cite; unknown n is text `[n]`; `[text](url)` and `[n](url)` stay `a`; inline code is untouched | grill-me 4-A | y |
| Invalid TeX | Markdown must not throw; `rehype-katex` public Options omit `throwOnError` so the plugin’s built-in handling is used, not a flag we pass | remark-math `rehype-katex` readme `Omit<KatexOptions, 'displayMode' \| 'throwOnError'>`; KaTeX default otherwise throws | n |
| `cite` omitted | numeric `[n]` renders as the characters `[n]`, never a button | RSC / reuse without SOURCES; desk always passes `cite` | n |
| `renderCitedMarkdown` | deleted with the homemade parser; those vitest cases mount Markdown | grill-me leftover default: one parser | n |
| KaTeX error colour | keep plugin default (includes hex inside KaTeX CSS / error span) | not a component literal; AG-UI “no hex in components” stays for `web/components` and `web/lib` we author | n |
| Profile | `light` (AGENTS.md has no `tlc-spec-lean` profile) | skill default; this is a UI slice, so `light` will not catch arrangement or a test that would pass under a wrong implementation | n |
| Package versions | whatever `npm --prefix web install` of the five named packages resolves on the lockfile | brief named packages, not versions | n |

**Open questions:** none - all resolved or logged above.

## Criteria

### S1: Finished assistant markdown keeps GFM and citations (P1)

**Acceptance Criteria**

1. WHEN an assistant block’s `content` contains a GFM pipe table (header, separator, one body row) THEN the system SHALL render one `table` whose `th` texts equal the header cells and whose `td` texts equal the body cells
2. WHEN `SOURCES` contains item `n` and the markdown contains a shortcut `[n]` that is not a destination link THEN the system SHALL render a `button` with `aria-label` equal to `Source n`
3. IF `[n]` matches no `SOURCES` item THEN the system SHALL render the characters `[n]` as text and SHALL NOT render a `button` with `aria-label` `Source n` for that n
4. WHEN the markdown contains `[label](url)` THEN the system SHALL render an `a` whose `href` equals that `url`
5. WHEN the markdown contains `[n](url)` with digits `n` THEN the system SHALL render an `a` whose `href` equals that `url` and SHALL NOT render a citation `button` for that occurrence
6. WHEN the markdown contains inline code whose text includes `[n]` THEN the system SHALL render that `[n]` inside `code` and SHALL NOT render a citation `button` from that occurrence
7. WHEN Markdown `source` is `""` THEN the system SHALL render no `h1`, `h2`, `h3`, `h4`, `table`, `ul`, `ol`, or `p`
8. The Markdown pipeline SHALL NOT include `rehype-raw`

**Independent test:** `npm --prefix web exec -- vitest run` on the assistant `Renderers` fixture (headings, lists, table, cites, links, unknown n, code) plus an empty `source` case.

### S2: KaTeX on a complete message (P1)

**Acceptance Criteria**

9. WHEN `math` is true and `source` contains inline `$a+b$` THEN the system SHALL render an element with class `katex`
10. WHEN `math` is true and `source` contains a display `$$` block THEN the system SHALL render an element with class `katex-display`
11. IF `math` is true and the TeX inside `$` or `$$` is not valid KaTeX THEN Markdown SHALL still return a React tree (no throw)
12. The Markdown module SHALL contain `import "katex/dist/katex.min.css"`
13. WHERE the `math` prop is omitted the system SHALL behave as `math={true}`

**Independent test:** vitest mount of Markdown with `math` true / omitted; assert `.katex` / `.katex-display`; invalid TeX does not throw.

### S3: Stream does not run KaTeX (P1)

**Acceptance Criteria**

14. WHILE an assistant block has `streaming` true the system SHALL pass `math={false}` into Markdown
15. WHEN `math` is false and `source` contains `$a+b$` THEN the system SHALL NOT render an element with class `katex`
16. WHEN an assistant block has `streaming` false THEN the system SHALL pass `math={true}` into Markdown

**Independent test:** vitest: `math={false}` leaves `$a+b$` without `.katex`; `Renderers` with `streaming: true` vs `false` on the same formula string.

### S4: One RSC-safe module, one parser (P1)

**Acceptance Criteria**

17. The Markdown module SHALL NOT contain a `"use client"` directive
18. IF `cite` is omitted THEN a shortcut `[n]` SHALL render as the characters `[n]` and SHALL NOT render a source `button`
19. The `web/package.json` `dependencies` object SHALL include `react-markdown`, `remark-gfm`, `remark-math`, `rehype-katex`, and `katex`
20. The assistant block SHALL NOT call `renderMarkdown` or `parseBlocks`

**Independent test:** vitest (omit `cite`; grep the Markdown file for `"use client"`); `package.json` contains the five names; no remaining production import of `renderMarkdown` / `parseBlocks`.

## Traceability

| ID | Slice | Criteria | Status |
| --- | --- | --- | --- |
| MD-01 | S1 | 1–8 | Pending |
| MD-02 | S2 | 9–13 | Pending |
| MD-03 | S3 | 14–16 | Pending |
| MD-04 | S4 | 17–20 | Pending |

## Observable

| Surface | Decision | Landing |
| --- | --- | --- |
| screen reading column (assistant) | empty state | AC 7 |
| screen reading column (assistant) | loading / streaming | AC 14, 15, 16 - prose GFM + cites, no KaTeX until the message ends |
| screen reading column (assistant) | error state | AC 11 - invalid TeX does not throw; no separate error chrome |
| screen reading column (assistant) | unauthorised state | n/a - no auth in v1 |
| screen reading column (assistant) | density and ordering | existing - `.assistant-text` rules in `web/app/globals.css` (type, table, gap); this slice does not restyle the column |
| screen reading column (assistant) | destructive action confirms | n/a - Markdown is read-only |
| screen citation popover / source panel | hover, focus, click | existing - `Citation` (AG-UI AC 62–63); Markdown only invokes `cite` |
| API | response / error / versioning | n/a - no HTTP change; AG-UI wire unchanged (AD-029) |
| command `npm --prefix web exec -- vitest run` | flags / exit | existing - vitest in `web/`; proofs stay there, not the `uv` unittest gate |
| document `AGENTS.md` | structure | n/a - no new invariant; `web/` stays HTTP-only |
| collection npm `web/` dependencies | naming / duplicates | AC 19 - the five packages listed once under `dependencies` |

## Flow

Reuses `Renderers` (exists), `Citation` (exists), `CiteRenderer` / `SourceItem` (exist), `.assistant-text` CSS (exists), and SOURCES already reduced into `sources`. Does not add a second citation transform and does not change the Writer or the AG-UI adapter.

1. assistant `block.content` + `sources` + `block.streaming` -> `Renderers` (exists) - chooses `math={!streaming}` and the existing `Citation` as `cite`
2. `Renderers` (exists) -> `Markdown` (door 1) with `source`, `math`, optional `cite`
3. `Markdown` (door 1) WHEN `math` is true first maps `\[` `\]` / `\(` `\)` to `$$` / `$` outside code (door 5), then `remark-math` + `rehype-katex` (door 3); `remark-gfm` then the cite plugin (doors 2 and 4)
4. matching cite nodes -> `Citation` (exists) via `cite`
5. out: DOM under `.assistant-text` (exists); streaming cursor stays a sibling of Markdown, as today

## Relations

None - no stored-data shape change

## Surface

None - nothing consumed outside

## Landing

| One-way door | Literal shape | Alternative rejected |
| --- | --- | --- |
| 1. npm stack in `web/` | `web/package.json` dependencies: `react-markdown`, `remark-gfm`, `remark-math`, `rehype-katex`, `katex`; CSS via `import "katex/dist/katex.min.css"` in the Markdown module | Homemade TeX in `parseBlocks` - no TeX engine, would fork GFM again. MathJax / `rehype-mathjax` - brief pins KaTeX. CSS in `app/layout.tsx` or a CDN `<link>` - taxes `/` and contradicts the package import |
| 2. Cite after GFM `linkReference` | remark plugin after `remark-gfm`: shortcut `linkReference` whose identifier is only digits; `cite(n)` if provided and the parent supplied a match; else text `[n]`; destination links `[text](url)` / `[n](url)` unchanged | Walk `p`/`li`/`td` children - GFM already turned `[1]` into `linkReference`. Regex on the raw string - fights fences and `[n](url)` |
| 3. Math plugins gated by `math` | `math` default `true`; desk passes `false` iff `block.streaming`; plugins `remark-math` (`singleDollarTextMath` default) + `rehype-katex`; delimiters `$` / `$$` only | KaTeX on every delta - incomplete `$` swallows the paragraph. Buffer until `TEXT_MESSAGE_END` - drops the typewriter. Passing `throwOnError` into `rehype-katex` - that key is omitted from the plugin Options type |
| 4. Dangling `[n]` is phrasing `text` | After `remark-gfm`, split `/\[(\d+)\]/` in `text` nodes whose parent is not `inlineCode` / `code` / `link` / `linkReference` / `image` / `definition`; still rewrite a numeric shortcut `linkReference` when a definition exists | Door 2 alone - CommonMark emits `linkReference` only when a matching definition exists, so `[1]` with no definition stays one `text` node and never reaches the cite map |
| 5. Writer `\[` `\]` maps to dollars | When `math` is true, replace `\[…\]` with `$$…$$` and `\(` `\)` with `$…$` outside fences/inline code, then `remark-math` (still `$` / `$$` only) | Change the Writer prompt to emit `$` / `$$` - out of scope. Leave `\[` as markdown-escaped `[` - the student sees `[ s_{\mathrm{RRF}}(d)` instead of KaTeX |

- Nothing else (file name `Markdown` vs `MarkdownRenderer`, exact mdast `hName`, whether `CiteRenderer` lives next to the module) is a door.

## Impact

| Front | What changes |
| --- | --- |
| domain | new term: `math` - boolean on Markdown; `false` means GFM + cite only; `true` (default) adds `remark-math` + `rehype-katex` |
| domain | existing term: assistant markdown rendering meant `renderMarkdown` / `parseBlocks` in `web/lib/markdown.tsx`. Callers today: `web/components/renderers.tsx`, `web/lib/citations.ts` (`renderCitedMarkdown` → `renderInline`). After this feature those call Markdown; the homemade parser is gone |
| stored data | nothing to migrate - answers stay strings on `AIMessage.content` / assistant blocks |
| decisions | after plan approval, append AD-030 in `.specs/project/STATE.md`: desk assistant markdown is `react-markdown` + `remark-gfm` + optional `remark-math`/`rehype-katex`; `[n]` is a post-GFM `linkReference` plugin; no `rehype-raw` |
| docs | none required in `AGENTS.md`; `web/package.json` is the install record |
| profile | `light` is thin for this UI slice (skill: will not catch arrangement or a test that passes under a wrong implementation); user can raise to `ui` / `standard` before checks |
