"use client"

import { useEffect, useState } from "react"

import { loadRecents, type Recent } from "../lib/recents"

type Props = {
  activeId?: string | null
}

export function Sidebar({ activeId }: Props) {
  const [recents, setRecents] = useState<Recent[]>([])

  useEffect(() => {
    setRecents(loadRecents())
  }, [activeId])

  return (
    <aside className="sidebar" aria-label="Threads">
      <a className="brand" href="/">
        <span className="brand-mark" aria-hidden="true" />
        arXiv desk
      </a>
      <a className="new-thread ui" href="/">
        <PlusIcon />
        New conversation
      </a>
      <div>
        <p className="recents-label">Recent</p>
        {recents.length === 0 ? (
          <p className="recents-empty">Threads you start appear here.</p>
        ) : (
          <ul className="recents">
            {recents.map((row) => (
              <li key={row.threadId}>
                <a
                  className={row.threadId === activeId ? "recent active" : "recent"}
                  href={`/c/${row.threadId}`}
                  title={row.title}
                >
                  {row.title}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}
