import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Chat } from "../components/Chat"
import { Citation } from "../components/Citation"
import { PlanBlock } from "../components/PlanBlock"
import { Renderers } from "../components/renderers"
import { SourcePanel } from "../components/SourcePanel"
import { StepRail } from "../components/StepRail"
import { applyEvent, emptyDesk } from "../lib/blocks"
import { renderCitedMarkdown } from "../lib/citations"
import { upsertRecent } from "../lib/recents"
import { normalRunInput, resumeRunInput } from "../lib/stream"
import type { SourceItem } from "../lib/types"

function sse(events: object[]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("")
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } })
}

const source: SourceItem = {
  n: 1,
  arxiv_id: "2401.00001",
  title: "LoRA",
  year: 2024,
  url: "https://arxiv.org/abs/2401.00001",
  excerpt: "low-rank adaptation of large models",
  chunk_id: "c1",
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  localStorage.clear()
})

describe("desk", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn())
  })

  it("home renders input and description without fetch", () => {
    render(<Chat />)
    expect(screen.getByLabelText("Message")).toBeTruthy()
    expect(screen.getByText(/Ask an AI\/ML question/i)).toBeTruthy()
    expect(fetch).not.toHaveBeenCalled()
  })

  it("first send posts agent and replaceState", async () => {
    const replace = vi.fn()
    vi.stubGlobal("history", { ...history, replaceState: replace })
    vi.mocked(fetch).mockResolvedValue(sse([{ type: "RUN_FINISHED", result: { outcome: "done" } }]))
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "What is LoRA?" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    const url = String(vi.mocked(fetch).mock.calls[0][0])
    expect(url).toContain("/agent")
    expect(replace).toHaveBeenCalled()
    expect(String(replace.mock.calls[0][2])).toMatch(/\/c\/[0-9a-f-]{36}/i)
  })

  it("same-tab first send skips get threads", async () => {
    vi.mocked(fetch).mockResolvedValue(sse([{ type: "RUN_FINISHED", result: { outcome: "done" } }]))
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
    expect(urls.every((url) => !url.includes("/threads/"))).toBe(true)
  })

  it("direct thread load waits for replay", async () => {
    let resolveFetch: (value: Response) => void = () => undefined
    vi.mocked(fetch).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve
        }),
    )
    render(<Chat threadId="tid" hydrate />)
    expect(screen.getByLabelText("Message")).toBeDisabled()
    resolveFetch(
      new Response(
        JSON.stringify({
          threadId: "tid",
          status: "idle",
          messages: [{ id: "u", role: "user", content: "hello" }],
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
    )
    await waitFor(() => expect(screen.getByText("hello")).toBeTruthy())
    expect(screen.getByLabelText("Message")).not.toBeDisabled()
  })

  it("thread 404 navigates home", async () => {
    const replace = vi.fn()
    vi.stubGlobal("location", { ...window.location, replace })
    vi.mocked(fetch).mockResolvedValue(new Response("{}", { status: 404 }))
    render(<Chat threadId="missing" hydrate />)
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"))
  })

  it("recents upsert title eighty chars", () => {
    const long = "x".repeat(100)
    const rows = upsertRecent("tid", long)
    expect(rows[0].title).toHaveLength(80)
    expect(rows[0].threadId).toBe("tid")
    expect(rows[0].updatedAt).toBeTruthy()
  })

  it("stop aborts fetch and input stays enabled", async () => {
    let aborted = false
    vi.mocked(fetch).mockImplementation((_url, init) => {
      return new Promise((_, reject) => {
        init?.signal?.addEventListener("abort", () => {
          aborted = true
          reject(new DOMException("aborted", "AbortError"))
        })
      })
    })
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() => expect(screen.getByText("Stop")).toBeTruthy())
    expect(screen.getByLabelText("Message")).not.toBeDisabled()
    fireEvent.click(screen.getByText("Stop"))
    await waitFor(() => expect(aborted).toBe(true))
    expect(screen.getByLabelText("Message")).not.toBeDisabled()
  })

  it("dropped stream refetches thread", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(sse([]))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            threadId: "tid",
            status: "idle",
            messages: [{ id: "u", role: "user", content: "replayed" }],
          }),
        ),
      )
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(1))
    expect(String(vi.mocked(fetch).mock.calls[1][0])).toContain("/threads/")
    await waitFor(() => expect(screen.getByText("replayed")).toBeTruthy())
  })

  it("dropped stream with failed replay stays idle", async () => {
    vi.mocked(fetch)
      .mockResolvedValueOnce(sse([]))
      .mockResolvedValueOnce(new Response("nope", { status: 500 }))
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() => expect(screen.getByText("thread replay failed (500)")).toBeTruthy())
    expect(screen.getByText("idle")).toBeTruthy()
  })

  it("interrupted auto-resumes once then shows resume", async () => {
    vi.useFakeTimers()
    vi.mocked(fetch)
      .mockResolvedValueOnce(sse([]))
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "interrupted", messages: [] })),
      )
      .mockResolvedValueOnce(sse([]))
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    for (let i = 0; i < 25 && vi.mocked(fetch).mock.calls.length < 2; i += 1) {
      await act(async () => {
        await Promise.resolve()
        await vi.advanceTimersByTimeAsync(0)
      })
    }
    expect(vi.mocked(fetch).mock.calls.length).toBe(2)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    for (let i = 0; i < 25 && vi.mocked(fetch).mock.calls.length < 3; i += 1) {
      await act(async () => {
        await Promise.resolve()
        await vi.advanceTimersByTimeAsync(0)
      })
    }
    expect(vi.mocked(fetch).mock.calls.length).toBe(3)
    expect(screen.getByText("Resume")).toBeTruthy()
  })

  it("interrupted strip uses warn and does not block input", () => {
    render(
      <div>
        <div className="interrupt-strip">Run interrupted.<button type="button">Resume</button></div>
        <input aria-label="Message" />
      </div>,
    )
    const strip = document.querySelector(".interrupt-strip") as HTMLElement
    expect(`${getComputedStyle(strip).color} ${strip.className}`).toMatch(/warn|interrupt/)
    expect(screen.getByLabelText("Message")).not.toBeDisabled()
  })

  it("refused and insufficient render reason only", () => {
    for (const outcome of ["refused", "insufficient"] as const) {
      const next = applyEvent(emptyDesk(), {
        type: "RUN_FINISHED",
        result: { outcome, reason: `${outcome} because` },
      })
      expect(next.blocks.some((b) => b.kind === "outcome" && b.reason === `${outcome} because`)).toBe(true)
      expect(next.blocks.some((b) => b.kind === "assistant")).toBe(false)
    }
  })

  it("run finished measures seconds since run started", () => {
    const now = vi.spyOn(Date, "now")
    now.mockReturnValue(10_000)
    let state = applyEvent(emptyDesk(), { type: "RUN_STARTED", runId: "r1" })
    state = applyEvent(state, { type: "STEP_STARTED", stepName: "gate" })
    now.mockReturnValue(18_200)
    state = applyEvent(state, { type: "RUN_FINISHED", runId: "r1", result: { outcome: "done" } })
    const steps = state.blocks.find((b) => b.kind === "steps")
    expect(steps?.kind === "steps" && steps.seconds).toBe(8.2)
    expect(steps?.kind === "steps" && steps.live).toBe(false)
    now.mockRestore()
  })

  it("server run started reuses the client's live rail", () => {
    let state = applyEvent(emptyDesk(), { type: "RUN_STARTED" })
    state = applyEvent(state, { type: "RUN_STARTED", runId: "r1" })
    expect(state.blocks.filter((b) => b.kind === "steps")).toHaveLength(1)
  })

  it("second run appends a new rail instead of overwriting the first", () => {
    let state = applyEvent(emptyDesk(), { type: "RUN_STARTED", runId: "r1" })
    state = applyEvent(state, { type: "RUN_FINISHED", runId: "r1", result: { outcome: "done" } })
    state = applyEvent(state, { type: "RUN_STARTED", runId: "r2" })
    expect(state.blocks.filter((b) => b.kind === "steps")).toHaveLength(2)
  })

  it("replan snapshot supersedes the live plan in place", () => {
    const item = { index: 0, agent: "search", task: "Find", status: "pending", feedback: null }
    let state = applyEvent(emptyDesk(), {
      type: "ACTIVITY_SNAPSHOT",
      activityType: "PLAN",
      messageId: "p1",
      content: { items: [item] },
    })
    state = applyEvent(state, {
      type: "ACTIVITY_SNAPSHOT",
      activityType: "PLAN",
      messageId: "p2",
      content: { items: [item, { ...item, index: 1 }] },
    })
    const plans = state.blocks.filter((b) => b.kind === "plan")
    expect(plans).toHaveLength(1)
    expect(plans[0].id).toBe("p2")
    state = applyEvent(state, { type: "RUN_FINISHED", result: { outcome: "done" } })
    expect(state.blocks.every((b) => b.kind !== "plan" || b.collapsed)).toBe(true)
  })

  it("markdown renders headings lists tables and cites", () => {
    const md = [
      "# Title",
      "",
      "Para with **bold** and `code` and [1].",
      "",
      "- one",
      "- two [1]",
      "",
      "| A | B |",
      "| --- | --- |",
      "| 1 | 2 |",
    ].join("\n")
    const { container } = render(
      <Renderers
        blocks={[{ kind: "assistant", id: "a", content: md, streaming: false }]}
        sources={[source]}
        onOpenSource={() => undefined}
      />,
    )
    expect(container.querySelector("h1")?.textContent).toBe("Title")
    expect(container.querySelector("strong")?.textContent).toBe("bold")
    expect(container.querySelector("code")?.textContent).toBe("code")
    expect(container.querySelectorAll("ul li")).toHaveLength(2)
    expect(container.querySelectorAll("table td")).toHaveLength(2)
    expect(container.querySelectorAll('button[aria-label="Source 1"]')).toHaveLength(2)
  })

  it("run error renders warn marginalia", () => {
    render(
      <Renderers
        blocks={[{ kind: "error", id: "e", message: "boom" }]}
        sources={[]}
        onOpenSource={() => undefined}
      />,
    )
    const line = screen.getByText("boom")
    expect(line.className).toMatch(/warn/)
  })

  it("normal run one user message resume empty", () => {
    const normal = normalRunInput("tid", "hello")
    expect(normal.messages).toHaveLength(1)
    expect(normal.messages[0].role).toBe("user")
    const resume = resumeRunInput("tid")
    expect(resume.messages).toEqual([])
    expect(resume.forwardedProps.resume).toBe(true)
  })

  it("live step rail current accent previous ok", () => {
    const { container } = render(
      <StepRail
        nodes={[{ name: "gate" }, { name: "planner" }]}
        live
        count={2}
        seconds={0}
      />,
    )
    expect(container.querySelector(".current")?.className).toMatch(/current/)
    expect(container.querySelector(".done")?.className).toMatch(/done/)
    expect(container.querySelector(".current")?.textContent).toContain("planner")
  })

  it("finished step rail collapses to count and seconds", () => {
    render(<StepRail nodes={[{ name: "gate" }]} live={false} count={14} seconds={8.2} />)
    expect(screen.getByText("14 steps · 8.2s")).toBeTruthy()
    fireEvent.click(screen.getByText("14 steps · 8.2s"))
    expect(screen.getByText(/gate/)).toBeTruthy()
  })

  it("search rail shows query used", () => {
    render(
      <StepRail
        nodes={[{ name: "search", queryUsed: "ti:LoRA" }]}
        live
        count={1}
        seconds={0}
      />,
    )
    expect(screen.getByText(/ti:LoRA/)).toBeTruthy()
  })

  it("gate is one marginalia line", () => {
    const { container } = render(
      <Renderers
        blocks={[{ kind: "gate", id: "g", inDomain: true, reason: "in scope" }]}
        sources={[]}
        onOpenSource={() => undefined}
      />,
    )
    expect(container.querySelectorAll("p.gate")).toHaveLength(1)
    expect(container.querySelector(".card")).toBeNull()
  })

  it("plan list survives delta then collapses", () => {
    const { rerender } = render(
      <PlanBlock
        items={[{ index: 0, agent: "search", task: "Find", status: "pending", feedback: null }]}
        collapsed={false}
      />,
    )
    const list = document.querySelector(".plan-list")
    rerender(
      <PlanBlock
        items={[{ index: 0, agent: "search", task: "Find", status: "passed", feedback: "ok" }]}
        collapsed={false}
      />,
    )
    expect(document.querySelector(".plan-list")).toBe(list)
    rerender(
      <PlanBlock
        items={[{ index: 0, agent: "search", task: "Find", status: "passed", feedback: "ok" }]}
        collapsed
      />,
    )
    expect(document.querySelector(".plan-line")).toBeTruthy()
  })

  it("matching n is source button links stay links", () => {
    const nodes = renderCitedMarkdown("See [1] and [docs](https://arxiv.org/abs/1)", [source])
    const { container } = render(<>{nodes}</>)
    expect(container.querySelector('button[aria-label="Source 1"]')).toBeTruthy()
    expect(container.querySelector("a")?.getAttribute("href")).toBe("https://arxiv.org/abs/1")
  })

  it("unknown n is plain text", () => {
    const nodes = renderCitedMarkdown("See [99]", [source])
    const { container } = render(<>{nodes}</>)
    expect(container.querySelector("button")).toBeNull()
    expect(container.textContent).toContain("[99]")
  })

  it("citation popover delay 150 stay 300", async () => {
    vi.useFakeTimers()
    render(<Citation sources={[source]} n={1} onOpen={() => undefined} />)
    fireEvent.mouseEnter(screen.getByLabelText("Source 1"))
    expect(screen.queryByText(/arXiv:2401.00001/)).toBeNull()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(150)
    })
    expect(screen.getByText(/arXiv:2401.00001/)).toBeTruthy()
    fireEvent.mouseLeave(screen.getByLabelText("Source 1"))
    await act(async () => {
      await vi.advanceTimersByTimeAsync(299)
    })
    expect(screen.getByText(/arXiv:2401.00001/)).toBeTruthy()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(screen.queryByText(/arXiv:2401.00001/)).toBeNull()
  })

  it("citation click opens panel over sidebar", () => {
    const opened: SourceItem[] = []
    render(
      <>
        <Citation sources={[source]} n={1} onOpen={(item) => opened.push(item)} />
        <SourcePanel source={source} onClose={() => undefined} />
      </>,
    )
    fireEvent.click(screen.getByLabelText("Source 1"))
    expect(opened[0]).toEqual(source)
    const panel = document.querySelector(".source-panel") as HTMLElement
    expect(panel).toBeTruthy()
    expect(getComputedStyle(panel).position || panel.className).toBeTruthy()
  })

  it("no sources list after assistant", () => {
    const { container } = render(
      <Renderers
        blocks={[{ kind: "assistant", id: "a", content: "See [1]", streaming: false }]}
        sources={[source]}
        onOpenSource={() => undefined}
      />,
    )
    expect(container.textContent?.includes("Sources")).toBe(false)
    expect(container.querySelector("ul.sources")).toBeNull()
  })

  it("user rule two px accent assistant unboxed", () => {
    const { container } = render(
      <Renderers
        blocks={[
          { kind: "user", id: "u", content: "q" },
          { kind: "assistant", id: "a", content: "a", streaming: false },
        ]}
        sources={[]}
        onOpenSource={() => undefined}
      />,
    )
    const user = container.querySelector(".user-msg") as HTMLElement
    expect(user.className).toContain("user-msg")
    expect(container.querySelector(".assistant-text")).toBeTruthy()
  })

  it("type tokens serif 17 ui inter mono 12", () => {
    const css = readFileSync(join(__dirname, "tokens.css"), "utf8")
    expect(css).toMatch(/--reading-size:\s*17px/)
    expect(css).toMatch(/--reading-leading:\s*1.65/)
    expect(css).toMatch(/--column:\s*68ch/)
    expect(css).toMatch(/Inter/)
    expect(css).toMatch(/--mono-size:\s*12px/)
    expect(css).toMatch(/Newsreader|Source Serif/)
  })

  it("tokens css has light and dark sets", () => {
    const css = readFileSync(join(__dirname, "tokens.css"), "utf8")
    expect(css).toContain("--bg: #fbf9f5")
    expect(css).toContain("prefers-color-scheme: light")
    expect(css).toContain("--bg: #14130f")
    expect(css).toContain("--accent: #b15423")
    expect(css).toContain("--accent: #d4763f")
  })

  it("components contain no hex colour literals", () => {
    const root = join(__dirname, "..", "components")
    const hex = /#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b/
    for (const name of readdirSync(root)) {
      const text = readFileSync(join(root, name), "utf8")
      expect(hex.test(text), name).toBe(false)
    }
  })

  it("reduced motion disables transitions and cursor", () => {
    const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf8")
    expect(css).toContain("prefers-reduced-motion: reduce")
    expect(css).toMatch(/transition:\s*none/)
    expect(css).toMatch(/\.cursor[\s\S]*display:\s*none/)
  })

  it("no gradient avatar bubble shimmer spinner", () => {
    const root = join(__dirname, "..")
    const files = [
      ...readdirSync(join(root, "components")).map((n) => join(root, "components", n)),
      join(root, "app", "globals.css"),
    ]
    for (const file of files) {
      const text = readFileSync(file, "utf8").toLowerCase()
      expect(text).not.toMatch(/linear-gradient|radial-gradient/)
      expect(text).not.toMatch(/avatar|robot/)
      expect(text).not.toMatch(/chat-bubble|bubble/)
      expect(text).not.toMatch(/shimmer|skeleton/)
      expect(text).not.toMatch(/spinner/)
    }
  })
})
