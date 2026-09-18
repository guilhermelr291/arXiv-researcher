"use client"

import { useEffect } from "react"

import type { SourceItem } from "../lib/types"

type Props = {
  source: SourceItem | null
  onClose: () => void
}

export function SourcePanel({ source, onClose }: Props) {
  useEffect(() => {
    if (!source) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [source, onClose])

  if (!source) return null

  return (
    <aside className="source-panel" aria-label="Source">
      <div className="panel-top">
        <span className="mono">
          Source [{source.n}] · arXiv:{source.arxiv_id} · {source.year}
        </span>
        <button type="button" className="close" onClick={onClose}>
          Close
        </button>
      </div>
      <h2>{source.title}</h2>
      <p className="excerpt">{source.excerpt}</p>
      <a className="open-link" href={source.url} target="_blank" rel="noreferrer">
        Open on arXiv
        <ArrowIcon />
      </a>
    </aside>
  )
}

function ArrowIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M4 12 12 4M6 4h6v6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
