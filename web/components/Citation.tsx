"use client"

import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

import type { SourceItem } from "../lib/types"

type Props = {
  sources: SourceItem[]
  n: number
  onOpen: (source: SourceItem) => void
}

const OPEN_DELAY_MS = 150
const CLOSE_DELAY_MS = 300
const GAP = 8
const EDGE = 12

export function Citation({ sources, n, onOpen }: Props) {
  const source = sources.find((item) => item.n === n)
  const [hover, setHover] = useState(false)
  const [open, setOpen] = useState(false)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const popRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = setTimeout(() => setOpen(hover), hover ? OPEN_DELAY_MS : CLOSE_DELAY_MS)
    return () => clearTimeout(id)
  }, [hover])

  useLayoutEffect(() => {
    if (!open) return
    const button = buttonRef.current
    const pop = popRef.current
    if (!button || !pop) return
    const anchor = button.getBoundingClientRect()
    const box = pop.getBoundingClientRect()
    const vw = window.innerWidth
    const centred = anchor.left + anchor.width / 2 - box.width / 2
    const left = Math.min(Math.max(centred, EDGE), Math.max(EDGE, vw - box.width - EDGE))
    const above = anchor.top - box.height - GAP
    const top = above >= EDGE ? above : anchor.bottom + GAP
    pop.style.left = `${left}px`
    pop.style.top = `${top}px`
  }, [open])

  useEffect(() => {
    if (!open) return
    const close = () => {
      setHover(false)
      setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close()
    }
    window.addEventListener("scroll", close, true)
    window.addEventListener("keydown", onKey)
    return () => {
      window.removeEventListener("scroll", close, true)
      window.removeEventListener("keydown", onKey)
    }
  }, [open])

  if (!source) return <>{`[${n}]`}</>

  const popover =
    open && typeof document !== "undefined"
      ? createPortal(
          <div
            ref={popRef}
            className="cite-pop"
            role="tooltip"
            onMouseEnter={() => setHover(true)}
            onMouseLeave={() => setHover(false)}
          >
            <span className="title">{source.title}</span>
            <span className="mono">
              arXiv:{source.arxiv_id} · {source.year}
            </span>
            <p className="excerpt">{source.excerpt}</p>
            <span className="hint">Click to open the source</span>
          </div>,
          document.body,
        )
      : null

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className="cite"
        aria-label={`Source ${n}`}
        aria-expanded={open}
        onMouseEnter={() => setHover(true)}
        onMouseLeave={() => setHover(false)}
        onFocus={() => setHover(true)}
        onBlur={() => setHover(false)}
        onClick={() => {
          setHover(false)
          setOpen(false)
          onOpen(source)
        }}
      >
        [{n}]
      </button>
      {popover}
    </>
  )
}
