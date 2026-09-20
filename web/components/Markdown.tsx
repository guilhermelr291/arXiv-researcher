import type { ReactNode } from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import rehypeKatex from "rehype-katex"
import remarkGfm from "remark-gfm"
import remarkMath from "remark-math"

import "katex/dist/katex.min.css"

/** Renders `[n]` for a source. Receives the source index and a stable key. */
export type CiteRenderer = (n: number, key: string) => ReactNode

type Props = {
  source: string
  math?: boolean
  cite?: CiteRenderer
}

type MdNode = {
  type: string
  identifier?: string
  referenceType?: string
  children?: MdNode[]
  value?: string
  data?: { hName?: string; hProperties?: Record<string, string> }
}

const SKIP_TEXT = new Set(["inlineCode", "code", "link", "linkReference", "image", "definition"])
const SKIP_WALK = new Set(["math", "inlineMath"])
const CODE_PROTECT = /```[\s\S]*?```|`[^`\n]+`/g
const DOLLAR_PROTECT = /\$\$[\s\S]*?\$\$|\$[^$\n]+\$/g
const SKIP_WRAP_CMD = new Set(["begin", "end"])

function mapOutside(source: string, protect: RegExp, map: (chunk: string) => string): string {
  const re = protect.global ? protect : new RegExp(protect.source, `${protect.flags}g`)
  let out = ""
  let last = 0
  for (const match of source.matchAll(re)) {
    const index = match.index ?? 0
    out += map(source.slice(last, index))
    out += match[0]
    last = index + match[0].length
  }
  return out + map(source.slice(last))
}

function latexDelimitersToDollars(chunk: string): string {
  return chunk.replace(/\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)/g, (whole) => {
    const inner = whole.slice(2, -2).trim()
    // remark-math only treats `$$` as display math at column 0. Writer `\[`
    // blocks are often indented, so keep surrounding spaces on their own line.
    if (whole.startsWith("\\[")) return `\n$$\n${inner}\n$$\n`
    return `$${inner}$`
  })
}

function latexEnvironmentsToDollars(chunk: string): string {
  return chunk.replace(
    /\\begin\{([a-zA-Z*]+)\}([\s\S]*?)\\end\{\1\}/g,
    (_whole, _env: string, inner: string) => `$$\n${inner.trim()}\n$$`,
  )
}

function consumeBalanced(s: string, i: number, limit: number, open: string, close: string): number {
  let depth = 0
  for (let j = i; j < limit; j++) {
    const ch = s[j]
    if (ch === "\\") {
      j += 1
      continue
    }
    if (ch === open) depth += 1
    else if (ch === close) {
      depth -= 1
      if (depth === 0) return j + 1
    }
  }
  return -1
}

function findMatchingOpen(
  s: string,
  closerIndex: number,
  lineStart: number,
  open: string,
  close: string,
): number {
  let depth = 0
  for (let j = closerIndex; j >= lineStart; j--) {
    const ch = s[j]
    if (ch === close) depth += 1
    else if (ch === open) {
      depth -= 1
      if (depth === 0) return j
    }
  }
  return -1
}

function growRight(s: string, i: number): number {
  const nl = s.indexOf("\n", i)
  const limit = nl === -1 ? s.length : nl
  let lastGood = i
  while (i < limit) {
    if (/^\[\d+\]/.test(s.slice(i))) break
    if (s.startsWith("**", i)) break
    const c = s[i]
    if (c === " " || c === "\t") {
      i += 1
      continue
    }
    if (c === "\\") {
      const letter = /^\\[a-zA-Z]+\*?/.exec(s.slice(i))
      if (letter) {
        const name = letter[0].slice(1).replace(/\*$/, "")
        if (SKIP_WRAP_CMD.has(name)) break
        i += letter[0].length
        lastGood = i
        continue
      }
      if (i + 1 < limit && /[{}.,;! ]/.test(s[i + 1] ?? "")) {
        i += 2
        lastGood = i
        continue
      }
      break
    }
    if (c === "{" || c === "(") {
      const closed = consumeBalanced(s, i, limit, c, c === "{" ? "}" : ")")
      if (closed < 0) break
      i = closed
      lastGood = i
      continue
    }
    if (c === "[") {
      const closed = consumeBalanced(s, i, limit, "[", "]")
      if (closed < 0) break
      i = closed
      lastGood = i
      continue
    }
    if (c === "}" || c === ")") {
      i += 1
      lastGood = i
      continue
    }
    if (c === "_" || c === "^") {
      i += 1
      lastGood = i
      continue
    }
    if (c === "*" && i > 0 && (s[i - 1] === "^" || s[i - 1] === "_")) {
      i += 1
      lastGood = i
      continue
    }
    if (c === ".") {
      if (i + 1 < limit && /[0-9]/.test(s[i + 1] ?? "")) {
        i += 1
        lastGood = i
        continue
      }
      break
    }
    if (/[0-9=+\-*/<>|,:'′]/.test(c)) {
      i += 1
      lastGood = i
      continue
    }
    break
  }
  return lastGood
}

function growLeft(s: string, i: number): number {
  const lineStart = s.lastIndexOf("\n", i - 1) + 1
  while (i > lineStart) {
    const c = s[i - 1]
    if (c === " " || c === "\t") break
    if (/[A-Za-z0-9'′*]/.test(c) || c === "_" || c === "^") {
      i -= 1
      continue
    }
    if (c === "}" || c === ")") {
      const open = findMatchingOpen(s, i - 1, lineStart, c === "}" ? "{" : "(", c)
      if (open < 0) break
      i = open
      continue
    }
    if (c === "{" || c === "(") {
      i -= 1
      continue
    }
    break
  }
  return i
}

function isWholeLine(s: string, start: number, end: number): boolean {
  const lineStart = s.lastIndexOf("\n", start - 1) + 1
  const nl = s.indexOf("\n", end)
  const lineEnd = nl === -1 ? s.length : nl
  return s.slice(lineStart, start).trim() === "" && s.slice(end, lineEnd).trim() === ""
}

function wrapBareTex(chunk: string): string {
  const windows: { start: number; end: number }[] = []
  const cmd = /\\([a-zA-Z]+)\*?/g
  let match: RegExpExecArray | null
  while ((match = cmd.exec(chunk))) {
    if (SKIP_WRAP_CMD.has(match[1] ?? "")) continue
    const prev = windows[windows.length - 1]
    if (prev && match.index < prev.end) continue
    const start = growLeft(chunk, match.index)
    const end = growRight(chunk, match.index + match[0].length)
    if (prev && start <= prev.end) {
      prev.start = Math.min(prev.start, start)
      prev.end = Math.max(prev.end, end)
      continue
    }
    windows.push({ start, end })
  }
  let out = ""
  let last = 0
  for (const window of windows) {
    out += chunk.slice(last, window.start)
    const body = chunk.slice(window.start, window.end).trim()
    if (body) {
      out += isWholeLine(chunk, window.start, window.end) ? `$$\n${body}\n$$` : `$${body}$`
    }
    last = window.end
  }
  return out + chunk.slice(last)
}

function normalizeMathSource(source: string): string {
  return mapOutside(source, CODE_PROTECT, (chunk) => {
    const delimited = latexEnvironmentsToDollars(latexDelimitersToDollars(chunk))
    return mapOutside(delimited, DOLLAR_PROTECT, wrapBareTex)
  })
}

function rewriteNumericShortcutRefs(node: MdNode): void {
  if (SKIP_WALK.has(node.type)) return
  const kids = node.children
  if (!kids) return
  for (let i = 0; i < kids.length; i++) {
    const child = kids[i]
    const id = child.identifier ?? ""
    if (
      child.type === "linkReference" &&
      child.referenceType === "shortcut" &&
      /^\d+$/.test(id)
    ) {
      kids[i] = citeNode(id)
      continue
    }
    rewriteNumericShortcutRefs(child)
  }
}

function splitTextCites(node: MdNode): void {
  if (SKIP_WALK.has(node.type)) return
  const kids = node.children
  if (!kids) return
  const next: MdNode[] = []
  for (const child of kids) {
    if (child.type === "text" && child.value && !SKIP_TEXT.has(node.type)) {
      const pieces = splitCiteText(child.value)
      if (pieces) {
        next.push(...pieces)
        continue
      }
    }
    splitTextCites(child)
    next.push(child)
  }
  node.children = next
}

function splitCiteText(value: string): MdNode[] | null {
  const re = /\[(\d+)\]/g
  const out: MdNode[] = []
  let last = 0
  let found = false
  let match: RegExpExecArray | null
  while ((match = re.exec(value))) {
    found = true
    if (match.index > last) out.push({ type: "text", value: value.slice(last, match.index) })
    out.push(citeNode(match[1]))
    last = match.index + match[0].length
  }
  if (!found) return null
  if (last < value.length) out.push({ type: "text", value: value.slice(last) })
  return out
}

function citeNode(id: string): MdNode {
  return {
    type: "citeRef",
    data: { hName: "md-cite", hProperties: { n: id } },
    children: [{ type: "text", value: `[${id}]` }],
  }
}

function remarkCite() {
  return (tree: MdNode) => {
    rewriteNumericShortcutRefs(tree)
    splitTextCites(tree)
  }
}

export function Markdown({ source, math = true, cite }: Props) {
  let citeIndex = 0
  const remarkPlugins = math
    ? [remarkMath, remarkGfm, remarkCite]
    : [remarkGfm, remarkCite]
  const rehypePlugins = math ? [rehypeKatex] : []
  const text = math ? normalizeMathSource(source) : source

  const components: Components = {
    a({ href, children }) {
      return (
        <a href={href} target="_blank" rel="noreferrer">
          {children}
        </a>
      )
    },
    ...({
      "md-cite"({ n, children }: { n?: string; children?: ReactNode }) {
        const num = Number(n)
        if (!cite || !Number.isFinite(num)) {
          return <>{children ?? `[${n ?? ""}]`}</>
        }
        return cite(num, `c${citeIndex++}`)
      },
    } as Components),
  }

  return (
    <ReactMarkdown remarkPlugins={remarkPlugins} rehypePlugins={rehypePlugins} components={components}>
      {text}
    </ReactMarkdown>
  )
}
