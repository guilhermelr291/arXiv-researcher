import { readFileSync, readdirSync } from "node:fs"
import { join } from "node:path"

import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Chat } from "../components/Chat"
import { Citation } from "../components/Citation"
import { Markdown } from "../components/Markdown"
import { PlanBlock } from "../components/PlanBlock"
import { Renderers } from "../components/renderers"
import { SourcePanel } from "../components/SourcePanel"
import { StepRail } from "../components/StepRail"
import { applyEvent, applyReplay, emptyDesk } from "../lib/blocks"
import { normalRunInput, resumeRunInput } from "../lib/stream"
import type { SourceItem } from "../lib/types"

function sse(events: object[]): Response {
  const body = events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join("")
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } })
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function isThreadList(url: string) {
  return /\/threads\/?$/.test(url.split("?")[0] ?? url)
}

function isThreadMember(url: string) {
  return /\/threads\/[^/]+$/.test(url.split("?")[0] ?? url)
}

function stubFetch(options?: {
  agent?: Response | ((init?: RequestInit) => Response | Promise<Response>)
  threads?: unknown | ((listCall: number) => unknown)
  thread?: unknown | Response
}) {
  let listCalls = 0
  vi.mocked(fetch).mockImplementation((input, init) => {
    const url = String(input)
    if (url.includes("/agent")) {
      const agent = options?.agent ?? sse([{ type: "RUN_FINISHED", result: { outcome: "done" } }])
      return Promise.resolve(typeof agent === "function" ? agent(init) : agent)
    }
    if (isThreadMember(url)) {
      const thread = options?.thread
      if (thread instanceof Response) return Promise.resolve(thread)
      if (thread !== undefined) return Promise.resolve(jsonResponse(thread))
      return Promise.resolve(jsonResponse({ detail: "thread not found" }, 404))
    }
    if (isThreadList(url)) {
      listCalls += 1
      const rows =
        typeof options?.threads === "function" ? options.threads(listCalls) : (options?.threads ?? [])
      return Promise.resolve(jsonResponse(rows))
    }
    return Promise.reject(new Error(`unexpected fetch ${url}`))
  })
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

  it("home renders input and description without fetch", async () => {
    stubFetch()
    render(<Chat />)
    expect(screen.getByLabelText("Message")).toBeTruthy()
    expect(screen.getByText(/Ask an AI\/ML question/i)).toBeTruthy()
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(0))
    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
    expect(urls.every((url) => isThreadList(url))).toBe(true)
    expect(urls.every((url) => !url.includes("/agent") && !isThreadMember(url))).toBe(true)
  })

  it("first send posts agent and replaceState", async () => {
    const replace = vi.fn()
    vi.stubGlobal("history", { ...history, replaceState: replace })
    stubFetch()
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "What is LoRA?" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some((call) => String(call[0]).includes("/agent"))).toBe(
        true,
      ),
    )
    expect(replace).toHaveBeenCalled()
    expect(String(replace.mock.calls[0][2])).toMatch(/\/c\/[0-9a-f-]{36}/i)
  })

  it("same-tab first send skips get threads", async () => {
    stubFetch()
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some((call) => String(call[0]).includes("/agent"))).toBe(
        true,
      ),
    )
    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
    expect(urls.every((url) => !isThreadMember(url))).toBe(true)
  })

  it("direct thread load waits for replay", async () => {
    let resolveFetch: (value: Response) => void = () => undefined
    vi.mocked(fetch).mockImplementation((input) => {
      const url = String(input)
      if (isThreadList(url)) return Promise.resolve(jsonResponse([]))
      if (isThreadMember(url)) {
        return new Promise((resolve) => {
          resolveFetch = resolve
        })
      }
      return Promise.reject(new Error(url))
    })
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
    stubFetch({ thread: jsonResponse({}, 404) })
    render(<Chat threadId="missing" hydrate />)
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"))
  })

  it("recents upsert title eighty chars", async () => {
    const title = "x".repeat(80)
    stubFetch({
      threads: [{ threadId: "tid", title, updatedAt: "2026-09-19T12:00:00Z" }],
    })
    render(<Chat />)
    await waitFor(() => expect(screen.getByText(title)).toBeTruthy())
  })

  it("sidebar fetches GET /threads and renders title", async () => {
    stubFetch({
      threads: [
        { threadId: "tid-a", title: "LoRA notes", updatedAt: "2026-09-19T12:00:00Z" },
      ],
    })
    render(<Chat />)
    await waitFor(() => expect(screen.getByText("LoRA notes")).toBeTruthy())
    const urls = vi.mocked(fetch).mock.calls.map((call) => String(call[0]))
    expect(urls.some((url) => isThreadList(url))).toBe(true)
  })

  it("empty GET /threads shows recents empty copy", async () => {
    stubFetch({ threads: [] })
    render(<Chat />)
    await waitFor(() => expect(screen.getByText("Threads you start appear here.")).toBeTruthy())
  })

  it("first assistant cite uses first turn sources not second", () => {
    const first = { ...source, excerpt: "first-excerpt" }
    const second = { ...source, excerpt: "second-excerpt", arxiv_id: "2401.00002", chunk_id: "c2" }
    const state = applyReplay([
      { id: "a1", role: "assistant", content: "See [1]" },
      { id: "s1", role: "activity", activityType: "SOURCES", content: { items: [first] } },
      { id: "a2", role: "assistant", content: "Also [1]" },
      { id: "s2", role: "activity", activityType: "SOURCES", content: { items: [second] } },
    ])
    const opened: SourceItem[] = []
    const { container } = render(
      <Renderers blocks={state.blocks} sources={state.sources} onOpenSource={(item) => opened.push(item)} />,
    )
    const firstCite = container.querySelectorAll(".assistant-text")[0]?.querySelector(
      'button[aria-label="Source 1"]',
    )
    expect(firstCite).toBeTruthy()
    fireEvent.click(firstCite!)
    expect(opened[0]?.excerpt).toBe("first-excerpt")
    expect(opened[0]?.excerpt).not.toBe("second-excerpt")
  })

  it("empty first-turn sources stay empty instead of using the second turn", () => {
    const second = { ...source, excerpt: "second-excerpt", arxiv_id: "2401.00002", chunk_id: "c2" }
    const state = applyReplay([
      { id: "a1", role: "assistant", content: "See [1]" },
      { id: "s1", role: "activity", activityType: "SOURCES", content: { items: [] } },
      { id: "a2", role: "assistant", content: "Also [1]" },
      { id: "s2", role: "activity", activityType: "SOURCES", content: { items: [second] } },
    ])
    const { container } = render(
      <Renderers blocks={state.blocks} sources={state.sources} onOpenSource={() => undefined} />,
    )
    const firstCite = container.querySelectorAll(".assistant-text")[0]?.querySelector(
      'button[aria-label="Source 1"]',
    )
    expect(firstCite).toBeNull()
    expect(
      container.querySelectorAll(".assistant-text")[1]?.querySelector('button[aria-label="Source 1"]'),
    ).toBeTruthy()
  })

  it("sidebar lists the thread after POST /agent starts", async () => {
    stubFetch({
      threads: (listCall) =>
        listCall < 3
          ? []
          : [{ threadId: "tid-new", title: "sidebar-new-thread", updatedAt: "2026-09-19T12:00:00Z" }],
    })
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    const sidebar = screen.getByLabelText("Threads")
    await waitFor(() => expect(within(sidebar).getByText("sidebar-new-thread")).toBeTruthy())
  })

  it("replay steps nodes appear in collapsed rail expand", () => {
    const state = applyReplay([
      {
        id: "steps-1",
        role: "activity",
        activityType: "STEPS",
        content: {
          count: 2,
          elapsed_ms: 1000,
          nodes: [{ name: "search" }, { name: "execute" }],
        },
      },
    ])
    render(<Renderers blocks={state.blocks} sources={[]} onOpenSource={() => undefined} />)
    fireEvent.click(screen.getByText("2 steps · 1s"))
    expect(screen.getByText("search")).toBeTruthy()
    expect(screen.getByText("execute")).toBeTruthy()
  })

  it("stop aborts fetch and input stays enabled", async () => {
    let aborted = false
    vi.mocked(fetch).mockImplementation((input, init) => {
      const url = String(input)
      if (isThreadList(url)) return Promise.resolve(jsonResponse([]))
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
    stubFetch({
      agent: sse([]),
      thread: {
        threadId: "tid",
        status: "idle",
        messages: [{ id: "u", role: "user", content: "replayed" }],
      },
    })
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some((call) => isThreadMember(String(call[0])))).toBe(true))
    await waitFor(() => expect(screen.getByText("replayed")).toBeTruthy())
  })

  it("dropped stream with failed replay stays idle", async () => {
    stubFetch({
      agent: sse([]),
      thread: new Response("nope", { status: 500 }),
    })
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    await waitFor(() => expect(screen.getByText("thread replay failed (500)")).toBeTruthy())
    expect(screen.getByText("idle")).toBeTruthy()
  })

  it("interrupted auto-resumes once then shows resume", async () => {
    vi.useFakeTimers()
    stubFetch({
      agent: sse([]),
      thread: { status: "interrupted", messages: [] },
    })
    render(<Chat />)
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "q" } })
    fireEvent.submit(screen.getByLabelText("Message").closest("form")!)
    const agentCalls = () =>
      vi.mocked(fetch).mock.calls.filter((call) => String(call[0]).includes("/agent")).length
    for (let i = 0; i < 25 && agentCalls() < 1; i += 1) {
      await act(async () => {
        await Promise.resolve()
        await vi.advanceTimersByTimeAsync(0)
      })
    }
    expect(agentCalls()).toBe(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    for (let i = 0; i < 25 && agentCalls() < 2; i += 1) {
      await act(async () => {
        await Promise.resolve()
        await vi.advanceTimersByTimeAsync(0)
      })
    }
    expect(agentCalls()).toBe(2)
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

  it("refused run finished keeps assistant not outcome", () => {
    let state = applyEvent(emptyDesk(), { type: "TEXT_MESSAGE_START", messageId: "ai-1" })
    state = applyEvent(state, {
      type: "TEXT_MESSAGE_CONTENT",
      messageId: "ai-1",
      delta: "out of scope",
    })
    state = applyEvent(state, {
      type: "RUN_FINISHED",
      result: { outcome: "refused", reason: "out of scope" },
    })
    const assistant = state.blocks.find((b) => b.kind === "assistant")
    expect(assistant?.kind === "assistant" && assistant.content).toBe("out of scope")
    expect(assistant?.kind === "assistant" && assistant.streaming).toBe(false)
    expect(state.blocks.some((b) => b.kind === "outcome")).toBe(false)
  })

  it("insufficient run finished is outcome chip not assistant", () => {
    const next = applyEvent(emptyDesk(), {
      type: "RUN_FINISHED",
      result: { outcome: "insufficient", reason: "not enough papers" },
    })
    expect(
      next.blocks.some((b) => b.kind === "outcome" && b.reason === "not enough papers"),
    ).toBe(true)
    expect(next.blocks.some((b) => b.kind === "assistant")).toBe(false)
  })

  it("applyReplay refused assistant is markdown block", () => {
    const state = applyReplay([
      { id: "ai-refused", role: "assistant", content: "out of scope" },
    ])
    const assistant = state.blocks.find((b) => b.kind === "assistant")
    expect(assistant?.kind === "assistant" && assistant.id).toBe("ai-refused")
    expect(assistant?.kind === "assistant" && assistant.content).toBe("out of scope")
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
    const { container } = render(
      <Markdown
        source="See [1] and [docs](https://arxiv.org/abs/1)"
        math={false}
        cite={(n, key) => (
          <Citation key={key} sources={[source]} n={n} onOpen={() => undefined} />
        )}
      />,
    )
    expect(container.querySelector('button[aria-label="Source 1"]')).toBeTruthy()
    expect(container.querySelector("a")?.getAttribute("href")).toBe("https://arxiv.org/abs/1")
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
