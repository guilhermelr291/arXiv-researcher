import { readFileSync } from "node:fs"
import { join } from "node:path"

import { render } from "@testing-library/react"

import { Citation } from "./Citation"
import { Markdown } from "./Markdown"
import { Renderers } from "./renderers"
import type { SourceItem } from "../lib/types"

const source: SourceItem = {
  n: 1,
  arxiv_id: "2401.00001",
  title: "LoRA",
  year: 2024,
  url: "https://arxiv.org/abs/2401.00001",
  excerpt: "low-rank adaptation of large models",
  chunk_id: "c1",
}

function cite(n: number, key: string) {
  return <Citation key={key} sources={[source]} n={n} onOpen={() => undefined} />
}

const markdownModule = join(__dirname, "Markdown.tsx")

describe("Markdown", () => {
  it("gfm pipe table renders th and td", () => {
    const { container } = render(
      <Markdown source={"| A | B |\n| --- | --- |\n| 1 | 2 |"} />,
    )
    const tables = container.querySelectorAll("table")
    expect(tables).toHaveLength(1)
    const th = [...tables[0].querySelectorAll("th")].map((el) => el.textContent)
    const td = [...tables[0].querySelectorAll("td")].map((el) => el.textContent)
    expect(th).toEqual(["A", "B"])
    expect(td).toEqual(["1", "2"])
  })

  it("shortcut n is source button", () => {
    const { container } = render(<Markdown source="See [1]" cite={cite} />)
    expect(container.querySelector('button[aria-label="Source 1"]')).toBeTruthy()
  })

  it("unknown n is plain text", () => {
    const { container } = render(<Markdown source="See [99]" cite={cite} />)
    expect(container.textContent).toContain("[99]")
    expect(container.querySelector('button[aria-label="Source 99"]')).toBeNull()
  })

  it("markdown link stays an anchor", () => {
    const { container } = render(
      <Markdown source="See [docs](https://arxiv.org/abs/1)" />,
    )
    expect(container.querySelector("a")?.getAttribute("href")).toBe(
      "https://arxiv.org/abs/1",
    )
  })

  it("numeric destination link is not a cite button", () => {
    const { container } = render(
      <Markdown source="See [1](https://arxiv.org/abs/1)" cite={cite} />,
    )
    expect(container.querySelector("a")?.getAttribute("href")).toBe(
      "https://arxiv.org/abs/1",
    )
    expect(container.querySelector('button[aria-label="Source 1"]')).toBeNull()
  })

  it("inline code n is not a cite button", () => {
    const { container } = render(<Markdown source="Use `[1]` here" cite={cite} />)
    expect(container.querySelector("code")?.textContent).toContain("[1]")
    expect(container.querySelector('button[aria-label="Source 1"]')).toBeNull()
  })

  it("empty source renders none of the eight block tags", () => {
    const { container } = render(<Markdown source="" />)
    for (const tag of ["h1", "h2", "h3", "h4", "table", "ul", "ol", "p"] as const) {
      expect(container.querySelector(tag), tag).toBeNull()
    }
  })

  it("markdown module does not import rehype-raw", () => {
    const text = readFileSync(markdownModule, "utf8")
    expect(text.includes("rehype-raw")).toBe(false)
  })

  it("inline dollar math renders katex", () => {
    const { container } = render(<Markdown source="$a+b$" math />)
    expect(container.querySelector(".katex")).toBeTruthy()
  })

  it("display dollar math renders katex-display", () => {
    const { container } = render(<Markdown source={"$$\na+b\n$$"} math />)
    expect(container.querySelector(".katex-display")).toBeTruthy()
  })

  it("invalid tex does not throw", () => {
    expect(() => render(<Markdown source="$\notatex$" math />)).not.toThrow()
  })

  it("markdown module imports katex min css", () => {
    const text = readFileSync(markdownModule, "utf8")
    expect(text).toContain('import "katex/dist/katex.min.css"')
  })

  it("omitted math prop still renders katex", () => {
    const { container } = render(<Markdown source="$a+b$" />)
    expect(container.querySelector(".katex")).toBeTruthy()
  })

  it("streaming assistant does not render katex", () => {
    const { container } = render(
      <Renderers
        blocks={[{ kind: "assistant", id: "a", content: "$a+b$", streaming: true }]}
        sources={[]}
        onOpenSource={() => undefined}
      />,
    )
    expect(container.querySelector(".katex")).toBeNull()
  })

  it("math false leaves dollar text without katex", () => {
    const { container } = render(<Markdown source="$a+b$" math={false} />)
    expect(container.querySelector(".katex")).toBeNull()
  })

  it("finished assistant renders katex", () => {
    const { container } = render(
      <Renderers
        blocks={[{ kind: "assistant", id: "a", content: "$a+b$", streaming: false }]}
        sources={[]}
        onOpenSource={() => undefined}
      />,
    )
    expect(container.querySelector(".katex")).toBeTruthy()
  })

  it("markdown module has no use client directive", () => {
    const text = readFileSync(markdownModule, "utf8")
    expect(text.includes('"use client"')).toBe(false)
  })

  it("omitted cite leaves shortcut n as text", () => {
    const { container } = render(<Markdown source="See [1]" />)
    expect(container.textContent).toContain("[1]")
    expect(container.querySelector('button[aria-label="Source 1"]')).toBeNull()
  })

  it("package json lists the five markdown packages", () => {
    const deps = JSON.parse(
      readFileSync(join(__dirname, "..", "package.json"), "utf8"),
    ).dependencies as Record<string, string>
    for (const name of [
      "react-markdown",
      "remark-gfm",
      "remark-math",
      "rehype-katex",
      "katex",
    ]) {
      expect(deps[name], name).toBeTruthy()
    }
  })

  it("assistant renderer does not call homemade parser", () => {
    const text = readFileSync(join(__dirname, "renderers.tsx"), "utf8")
    for (const id of ["renderMarkdown", "parseBlocks"]) {
      expect(text.includes(id), id).toBe(false)
    }
  })

  it("backslash-bracket display math renders katex-display", () => {
    const { container } = render(
      <Markdown source={"\\[ s_{\\mathrm{RRF}}(d) \\]"} math />,
    )
    expect(container.querySelector(".katex-display")).toBeTruthy()
    expect(container.textContent ?? "").not.toMatch(/\[\s*s_/)
  })

  it("backslash-paren inline math renders katex", () => {
    const { container } = render(<Markdown source={"\\( a+b \\)"} math />)
    expect(container.querySelector(".katex")).toBeTruthy()
  })
})
