"use client"

import { useEffect, useRef, useState } from "react"

import { applyEvent, applyReplay, emptyDesk, type DeskState } from "../lib/blocks"
import { upsertRecent } from "../lib/recents"
import { apiUrl, normalRunInput, postAgent, resumeRunInput } from "../lib/stream"
import type { AguiMessage, SourceItem } from "../lib/types"
import { Composer } from "./Composer"
import { EmptyState } from "./EmptyState"
import { Renderers } from "./renderers"
import { Sidebar } from "./Sidebar"
import { SourcePanel } from "./SourcePanel"

type Props = {
  threadId?: string
  hydrate?: boolean
}

type Terminal = "finished" | "error" | "dropped"

function failReplay(current: DeskState, message: string): DeskState {
  return {
    ...current,
    status: "idle",
    showResume: false,
    blocks: [
      ...current.blocks.map((block) =>
        block.kind === "steps" && block.live ? { ...block, live: false } : block,
      ),
      { kind: "error", id: `error-replay-${current.blocks.length}`, message },
    ],
  }
}

export function Chat({ threadId: initialId, hydrate = false }: Props) {
  const [threadId, setThreadId] = useState(initialId ?? "")
  const [desk, setDesk] = useState<DeskState>(emptyDesk())
  const [input, setInput] = useState("")
  const [ready, setReady] = useState(!hydrate)
  const [source, setSource] = useState<SourceItem | null>(null)
  const [manualResume, setManualResume] = useState(false)
  const autoResume = useRef(false)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const pinned = useRef(true)

  useEffect(() => {
    if (!hydrate || !initialId) return
    let cancelled = false
    ;(async () => {
      const response = await fetch(apiUrl(`/threads/${initialId}`))
      if (cancelled) return
      if (response.status === 404) {
        window.location.replace("/")
        return
      }
      const body = (await response.json()) as {
        messages: AguiMessage[]
        status: string
      }
      setDesk(applyReplay(body.messages ?? []))
      setReady(true)
      if (body.status === "interrupted") {
        setTimeout(() => {
          void runResume(initialId, true)
        }, 1000)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [hydrate, initialId])

  // Follow the stream while the reader is at the bottom; stop when they scroll up.
  useEffect(() => {
    const el = scrollRef.current
    if (!el || !pinned.current) return
    el.scrollTop = el.scrollHeight
  }, [desk.blocks])

  function onScroll() {
    const el = scrollRef.current
    if (!el) return
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  async function runStream(id: string, resume: boolean, text = "") {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setDesk((current) => ({ ...current, status: "streaming", showResume: false }))
    const inputPayload = resume ? resumeRunInput(id) : normalRunInput(id, text)
    if (!resume) setInput("")
    let terminal: Terminal = "dropped"
    try {
      const result = await postAgent(
        inputPayload,
        (event) => {
          setDesk((current) => applyEvent(current, event))
        },
        controller.signal,
      )
      if (controller.signal.aborted) {
        setDesk((current) => ({ ...current, status: "idle" }))
        return
      }
      terminal = result.terminal
    } catch {
      if (controller.signal.aborted) {
        setDesk((current) => ({ ...current, status: "idle" }))
        return
      }
      terminal = "dropped"
    }
    if (terminal === "dropped") {
      try {
        const replay = await fetch(apiUrl(`/threads/${id}`))
        if (!replay.ok) {
          setDesk((current) => failReplay(current, `thread replay failed (${replay.status})`))
          return
        }
        const body = (await replay.json()) as { messages: AguiMessage[]; status: string }
        setDesk(applyReplay(body.messages ?? []))
        if (body.status === "interrupted") {
          if (!autoResume.current) {
            autoResume.current = true
            setTimeout(() => {
              void runResume(id, true)
            }, 1000)
          } else {
            setManualResume(true)
            setDesk((current) => ({ ...current, status: "interrupted", showResume: true }))
          }
        }
      } catch {
        setDesk((current) => failReplay(current, "thread replay failed"))
      }
    }
  }

  async function runResume(id: string, fromInterrupt: boolean) {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    let terminal: Terminal = "dropped"
    try {
      const result = await postAgent(
        resumeRunInput(id),
        (event) => setDesk((current) => applyEvent(current, event)),
        controller.signal,
      )
      if (controller.signal.aborted) {
        setDesk((current) => ({ ...current, status: "idle" }))
        return
      }
      terminal = result.terminal
    } catch {
      if (controller.signal.aborted) {
        setDesk((current) => ({ ...current, status: "idle" }))
        return
      }
      terminal = "dropped"
    }
    if (fromInterrupt && terminal === "dropped") {
      setManualResume(true)
      setDesk((current) => ({ ...current, status: "interrupted", showResume: true }))
    }
  }

  async function send(raw: string) {
    const text = raw.trim()
    if (!text) return
    let id = threadId
    if (!id) {
      id = crypto.randomUUID()
      setThreadId(id)
      upsertRecent(id, text)
      history.replaceState(null, "", `/c/${id}`)
    }
    pinned.current = true
    setDesk((current) =>
      applyEvent(
        {
          ...current,
          blocks: [...current.blocks, { kind: "user", id: crypto.randomUUID(), content: text }],
        },
        { type: "RUN_STARTED" },
      ),
    )
    await runStream(id, false, text)
  }

  const emptyHome = !threadId && desk.blocks.length === 0
  const streaming = desk.status === "streaming"
  const shortId = threadId ? `thread ${threadId.slice(0, 8)}` : "new conversation"

  return (
    <div className="desk">
      <Sidebar activeId={threadId || null} />
      <SourcePanel source={source} onClose={() => setSource(null)} />
      <main className="stage">
        <header className="topbar">
          <span className="topbar-title mono">{shortId}</span>
          <span className={streaming ? "status-pill live" : "status-pill"}>
            <span className="dot" aria-hidden="true" />
            {streaming ? "researching" : ready ? "idle" : "loading"}
          </span>
        </header>

        {emptyHome ? (
          <EmptyState onPick={(text) => void send(text)} disabled={streaming} />
        ) : (
          <div className="scroll" ref={scrollRef} onScroll={onScroll}>
            <div className="column">
              <Renderers blocks={desk.blocks} sources={desk.sources} onOpenSource={setSource} />
            </div>
          </div>
        )}

        <div className="composer-dock">
          <div className="column">
            {desk.status === "interrupted" || manualResume ? (
              <div className="interrupt-strip warn ui">
                <span>Run interrupted.</span>
                <button type="button" onClick={() => void runResume(threadId, false)}>
                  Resume
                </button>
              </div>
            ) : null}
            <Composer
              value={input}
              onChange={setInput}
              onSend={() => void send(input)}
              onStop={() => abortRef.current?.abort()}
              streaming={streaming}
              disabled={hydrate && !ready}
            />
            <p className="composer-hint ui">
              Enter to send · Shift+Enter for a new line · answers cite arXiv only
            </p>
          </div>
        </div>
      </main>
    </div>
  )
}
