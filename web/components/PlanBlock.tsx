"use client"

import { useState } from "react"

import type { PlanItem } from "../lib/types"
import { Chevron } from "./Chevron"

type Props = {
  items: PlanItem[]
  collapsed: boolean
}

function summary(items: PlanItem[]): string {
  const passed = items.filter((item) => item.status === "passed").length
  return `Plan · ${items.length} ${items.length === 1 ? "step" : "steps"}${
    passed ? ` · ${passed} passed` : ""
  }`
}

function PlanList({ items }: { items: PlanItem[] }) {
  return (
    <ol className="plan-list">
      {items.map((item) => (
        <li key={item.index} className="plan-item">
          <span className="plan-index">{String(item.index + 1).padStart(2, "0")}</span>
          <span className="plan-task">
            <span className="plan-agent">{item.agent}</span>
            {item.task}
            {item.feedback ? <span className="plan-feedback">{item.feedback}</span> : null}
          </span>
          <span className={`status ${item.status}`}>{item.status}</span>
        </li>
      ))}
    </ol>
  )
}

export function PlanBlock({ items, collapsed }: Props) {
  const [open, setOpen] = useState(false)

  if (collapsed) {
    return (
      <div className="panel">
        <button
          type="button"
          className="panel-head plan-line ui"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <Chevron open={open} />
          <span className="label">{summary(items)}</span>
        </button>
        {open ? <PlanList items={items} /> : null}
      </div>
    )
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <span className="label">{summary(items)}</span>
        <span className="meta">live</span>
      </div>
      <PlanList items={items} />
    </div>
  )
}
