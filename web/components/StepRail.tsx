"use client"

import { useState } from "react"

import type { StepNode } from "../lib/types"
import { Chevron } from "./Chevron"

type Props = {
  nodes: StepNode[]
  live: boolean
  count: number
  seconds: number
}

export function StepRail({ nodes, live, count, seconds }: Props) {
  const [open, setOpen] = useState(false)

  if (!live) {
    const label = `${count} steps · ${seconds}s`
    return (
      <div className="step-rail collapsed panel">
        <button
          type="button"
          className="panel-head"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          <Chevron open={open} />
          <span className="label mono">{label}</span>
        </button>
        {open && nodes.length > 0 ? (
          <ol className="step-list">
            {nodes.map((node, index) => (
              <li key={`${node.name}-${index}`}>
                <span className="n">{String(index + 1).padStart(2, "0")}</span>
                <span>{node.name}</span>
                {node.queryUsed ? <span className="query">{node.queryUsed}</span> : null}
              </li>
            ))}
          </ol>
        ) : null}
      </div>
    )
  }

  return (
    <ol className="step-rail live" aria-label="Steps">
      {nodes.map((node, index) => {
        const current = index === nodes.length - 1
        if (!current) {
          return (
            <li
              key={`${node.name}-${index}`}
              className="step done"
              title={node.queryUsed ? `${node.name} · ${node.queryUsed}` : node.name}
            >
              {node.name}
            </li>
          )
        }
        return (
          <li key={`${node.name}-${index}`} className="step current mono" data-query={node.queryUsed ?? ""}>
            {node.name}
            {node.queryUsed ? <span className="query">{node.queryUsed}</span> : null}
          </li>
        )
      })}
    </ol>
  )
}
