import type { ReactNode } from "react"

import type { SourceItem } from "./types"

/** Renders `[n]` for a source. Receives the source index and a stable key. */
export type CiteRenderer = (n: number, key: string) => ReactNode

const INLINE =
  /(`[^`\n]+`)|(\*\*[^*\n]+?\*\*)|(\[([^\]\n]+)\]\(([^)\s]+)\))|(\[(\d+)\](?!\())/g

export const defaultCite: CiteRenderer = (n, key) => (
  <button key={key} type="button" className="cite" aria-label={`Source ${n}`} data-n={String(n)}>
    [{n}]
  </button>
)

export function renderInline(
  text: string,
  sources: ReadonlyMap<number, SourceItem>,
  cite: CiteRenderer,
  prefix: string,
): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  let i = 0
  for (const match of text.matchAll(INLINE)) {
    const start = match.index ?? 0
    const key = `${prefix}-${i++}`
    const [raw, code, bold, link, linkText, href, , citeN] = match
    let node: ReactNode | null = null
    if (code) {
      node = <code key={key}>{code.slice(1, -1)}</code>
    } else if (bold) {
      node = <strong key={key}>{renderInline(bold.slice(2, -2), sources, cite, key)}</strong>
    } else if (link) {
      node = (
        <a key={key} href={href} target="_blank" rel="noreferrer">
          {linkText}
        </a>
      )
    } else if (citeN !== undefined) {
      const n = Number(citeN)
      node = sources.has(n) ? cite(n, key) : null
    }
    if (node === null) continue
    if (start > last) nodes.push(text.slice(last, start))
    nodes.push(node)
    last = start + raw.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

type ListBlock = { kind: "list"; ordered: boolean; items: string[] }
type Blockish =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "code"; text: string }
  | { kind: "quote"; text: string }
  | { kind: "hr" }
  | { kind: "table"; header: string[]; rows: string[][] }
  | ListBlock

const HEADING = /^(#{1,4})\s+(.*)$/
const HR = /^(-{3,}|\*{3,}|_{3,})\s*$/
const UL = /^\s*[-*•]\s+(.*)$/
const OL = /^\s*\d+[.)]\s+(.*)$/
const TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/

function splitRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim())
}

export function parseBlocks(markdown: string): Blockish[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n")
  const blocks: Blockish[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i++
      continue
    }
    if (line.trimStart().startsWith("```")) {
      const buf: string[] = []
      i++
      while (i < lines.length && !lines[i].trimStart().startsWith("```")) buf.push(lines[i++])
      i++
      blocks.push({ kind: "code", text: buf.join("\n") })
      continue
    }
    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2].trim() })
      i++
      continue
    }
    if (HR.test(line)) {
      blocks.push({ kind: "hr" })
      i++
      continue
    }
    if (line.trim().startsWith("|") && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1])) {
      const header = splitRow(line)
      i += 2
      const rows: string[][] = []
      while (i < lines.length && lines[i].trim().startsWith("|")) rows.push(splitRow(lines[i++]))
      blocks.push({ kind: "table", header, rows })
      continue
    }
    if (line.trimStart().startsWith(">")) {
      const buf: string[] = []
      while (i < lines.length && lines[i].trimStart().startsWith(">")) {
        buf.push(lines[i++].replace(/^\s*>\s?/, ""))
      }
      blocks.push({ kind: "quote", text: buf.join(" ") })
      continue
    }
    const listMatch = UL.exec(line) ?? OL.exec(line)
    if (listMatch) {
      const ordered = !UL.test(line)
      const items: string[] = []
      while (i < lines.length) {
        const m = ordered ? OL.exec(lines[i]) : UL.exec(lines[i])
        if (m) {
          items.push(m[1])
          i++
          continue
        }
        // continuation line of the previous item
        if (lines[i].trim() && /^\s{2,}/.test(lines[i]) && items.length) {
          items[items.length - 1] += ` ${lines[i].trim()}`
          i++
          continue
        }
        break
      }
      blocks.push({ kind: "list", ordered, items })
      continue
    }
    const buf: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() &&
      !HEADING.test(lines[i]) &&
      !UL.test(lines[i]) &&
      !OL.test(lines[i]) &&
      !lines[i].trimStart().startsWith("```") &&
      !lines[i].trimStart().startsWith(">")
    ) {
      buf.push(lines[i++].trim())
    }
    blocks.push({ kind: "paragraph", text: buf.join(" ") })
  }
  return blocks
}

export function renderMarkdown(
  markdown: string,
  sources: SourceItem[],
  cite: CiteRenderer = defaultCite,
): ReactNode[] {
  const byN = new Map(sources.map((item) => [item.n, item]))
  return parseBlocks(markdown).map((block, index) => {
    const key = `b${index}`
    switch (block.kind) {
      case "heading": {
        const Tag = `h${block.level}` as "h1" | "h2" | "h3" | "h4"
        return <Tag key={key}>{renderInline(block.text, byN, cite, key)}</Tag>
      }
      case "paragraph":
        return <p key={key}>{renderInline(block.text, byN, cite, key)}</p>
      case "code":
        return (
          <pre key={key}>
            <code>{block.text}</code>
          </pre>
        )
      case "quote":
        return <blockquote key={key}>{renderInline(block.text, byN, cite, key)}</blockquote>
      case "hr":
        return <hr key={key} />
      case "table":
        return (
          <table key={key}>
            <thead>
              <tr>
                {block.header.map((cell, c) => (
                  <th key={c}>{renderInline(cell, byN, cite, `${key}-h${c}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((cell, c) => (
                    <td key={c}>{renderInline(cell, byN, cite, `${key}-${r}-${c}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )
      case "list": {
        const Tag = block.ordered ? "ol" : "ul"
        return (
          <Tag key={key}>
            {block.items.map((item, n) => (
              <li key={n}>{renderInline(item, byN, cite, `${key}-${n}`)}</li>
            ))}
          </Tag>
        )
      }
    }
  })
}
