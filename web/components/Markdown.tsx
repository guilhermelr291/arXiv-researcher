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

function latexDelimitersToDollars(source: string): string {
  return source.replace(
    /(```[\s\S]*?```|`[^`\n]+`)|(\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\))/g,
    (whole, code: string | undefined) => {
      if (code) return code
      if (whole.startsWith("\\[")) return `$$\n${whole.slice(2, -2).trim()}\n$$`
      return `$${whole.slice(2, -2).trim()}$`
    },
  )
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
  const text = math ? latexDelimitersToDollars(source) : source

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
