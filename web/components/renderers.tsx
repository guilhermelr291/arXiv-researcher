"use client"

import type { ReactNode } from "react"

import type { Block } from "../lib/blocks"
import { renderMarkdown } from "../lib/markdown"
import type { SourceItem } from "../lib/types"
import { Citation } from "./Citation"
import { PlanBlock } from "./PlanBlock"
import { StepRail } from "./StepRail"

type Props = {
  blocks: Block[]
  sources: SourceItem[]
  onOpenSource: (source: SourceItem) => void
}

const ACTIVITY = new Set<Block["kind"]>(["gate", "plan", "steps"])

function renderBlock(block: Block, sources: SourceItem[], onOpenSource: Props["onOpenSource"]) {
  switch (block.kind) {
    case "user":
      return (
        <p key={block.id} className="user-msg">
          {block.content}
        </p>
      )
    case "gate":
      return (
        <p key={block.id} className={block.inDomain ? "gate ok ui" : "gate refused ui"}>
          <span className="verdict">{block.inDomain ? "in domain" : "refused"}</span>
          <span>{block.reason}</span>
        </p>
      )
    case "plan":
      return <PlanBlock key={block.id} items={block.items} collapsed={block.collapsed} />
    case "steps":
      return (
        <StepRail
          key={block.id}
          nodes={block.nodes}
          live={block.live}
          count={block.count}
          seconds={block.seconds}
        />
      )
    case "assistant":
      return (
        <div key={block.id} className="assistant-text">
          {renderMarkdown(block.content, sources, (n, key) => (
            <Citation key={key} sources={sources} n={n} onOpen={onOpenSource} />
          ))}
          {block.streaming ? <span className="cursor" aria-hidden="true" /> : null}
        </div>
      )
    case "outcome":
      return (
        <p key={block.id} className="outcome ui muted">
          <span className="status">{block.outcome}</span>
          <span>{block.reason}</span>
        </p>
      )
    case "error":
      return (
        <p key={block.id} className="error ui warn">
          {block.message}
        </p>
      )
  }
}

/** Consecutive gate / plan / steps blocks share one tight `.activity` group. */
export function Renderers({ blocks, sources, onOpenSource }: Props) {
  const out: ReactNode[] = []
  let group: ReactNode[] = []
  let groupId = ""

  const flush = () => {
    if (group.length === 0) return
    out.push(
      <div key={`activity-${groupId}`} className="activity">
        {group}
      </div>,
    )
    group = []
  }

  for (const block of blocks) {
    const node = renderBlock(block, sources, onOpenSource)
    if (ACTIVITY.has(block.kind)) {
      if (group.length === 0) groupId = block.id
      group.push(node)
      continue
    }
    flush()
    out.push(node)
  }
  flush()
  return <>{out}</>
}
