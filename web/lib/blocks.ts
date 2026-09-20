import type { AguiEvent, AguiMessage, PlanItem, SourceItem, StepNode } from "./types"

export type Block =
  | { kind: "user"; id: string; content: string }
  | { kind: "gate"; id: string; inDomain: boolean; reason: string }
  | { kind: "plan"; id: string; items: PlanItem[]; collapsed: boolean }
  | {
      kind: "steps"
      id: string
      nodes: StepNode[]
      live: boolean
      count: number
      seconds: number
      startedAt?: number
    }
  | {
      kind: "assistant"
      id: string
      content: string
      streaming: boolean
      sources?: SourceItem[]
    }
  | { kind: "outcome"; id: string; outcome: string; reason: string }
  | { kind: "error"; id: string; message: string }

export type DeskState = {
  blocks: Block[]
  sources: SourceItem[]
  status: "idle" | "streaming" | "interrupted"
  showResume: boolean
}

export const emptyDesk = (): DeskState => ({
  blocks: [],
  sources: [],
  status: "idle",
  showResume: false,
})

function applyPatch(items: PlanItem[], patch: AguiEvent["patch"]): PlanItem[] {
  const next = items.map((item) => ({ ...item }))
  for (const op of patch ?? []) {
    const parts = op.path.replace(/^\//, "").split("/")
    if (parts[0] !== "items") continue
    const index = Number(parts[1])
    const field = parts[2] as keyof PlanItem
    if (!next[index] || !field) continue
    if (op.op === "replace" || op.op === "add") {
      next[index] = { ...next[index], [field]: op.value as never }
    }
  }
  return next
}

function upsert(blocks: Block[], block: Block): Block[] {
  const index = blocks.findIndex((row) => row.id === block.id && row.kind === block.kind)
  if (index === -1) return [...blocks, block]
  const copy = blocks.slice()
  copy[index] = block
  return copy
}

function bindSources(blocks: Block[], items: SourceItem[]): Block[] {
  const next = blocks.slice()
  for (let index = next.length - 1; index >= 0; index -= 1) {
    if (next[index].kind === "assistant") {
      next[index] = { ...next[index], sources: items }
      break
    }
  }
  return next
}

export function applyReplay(messages: AguiMessage[]): DeskState {
  let state = emptyDesk()
  for (const message of messages) {
    if (message.role === "user") {
      state = {
        ...state,
        blocks: [
          ...state.blocks,
          { kind: "user", id: message.id, content: message.content },
        ],
      }
      continue
    }
    if (message.role === "assistant") {
      state = {
        ...state,
        blocks: [
          ...state.blocks,
          { kind: "assistant", id: message.id, content: message.content, streaming: false, sources: [] },
        ],
      }
      continue
    }
    const type = message.activityType
    const content = message.content
    if (type === "GATE") {
      state = {
        ...state,
        blocks: [
          ...state.blocks,
          {
            kind: "gate",
            id: message.id,
            inDomain: Boolean(content.in_domain ?? content.inDomain),
            reason: String(content.reason ?? ""),
          },
        ],
      }
    } else if (type === "PLAN") {
      state = {
        ...state,
        blocks: [
          ...state.blocks,
          {
            kind: "plan",
            id: message.id,
            items: (content.items as PlanItem[]) ?? [],
            collapsed: true,
          },
        ],
      }
    } else if (type === "STEPS") {
      const count = Number(content.count ?? 0)
      const elapsed = Number(content.elapsed_ms ?? content.elapsedMs ?? 0)
      const rawNodes = Array.isArray(content.nodes) ? content.nodes : []
      const nodes: StepNode[] = rawNodes.map((node) => {
        const row = node as { name?: string; query_used?: string; queryUsed?: string }
        return {
          name: String(row.name ?? ""),
          queryUsed: row.query_used ?? row.queryUsed,
        }
      })
      state = {
        ...state,
        blocks: [
          ...state.blocks,
          {
            kind: "steps",
            id: message.id,
            nodes,
            live: false,
            count,
            seconds: Math.round(elapsed / 100) / 10,
          },
        ],
      }
    } else if (type === "SOURCES") {
      const items = (content.items as SourceItem[]) ?? []
      state = { ...state, blocks: bindSources(state.blocks, items), sources: items }
    } else if (type === "OUTCOME") {
      state = {
        ...state,
        blocks: [
          ...state.blocks,
          {
            kind: "outcome",
            id: message.id,
            outcome: String(content.outcome ?? ""),
            reason: String(content.reason ?? ""),
          },
        ],
      }
    }
  }
  return state
}

export function applyEvent(state: DeskState, event: AguiEvent): DeskState {
  if (event.type === "RUN_STARTED") {
    // The client marks the run as started before the server echoes RUN_STARTED.
    if (state.blocks.some((b) => b.kind === "steps" && b.live)) {
      return { ...state, status: "streaming", showResume: false }
    }
    return {
      ...state,
      status: "streaming",
      showResume: false,
      blocks: upsert(state.blocks, {
        kind: "steps",
        id: `steps-${event.runId ?? state.blocks.length}`,
        nodes: [],
        live: true,
        count: 0,
        seconds: 0,
        startedAt: Date.now(),
      }),
    }
  }
  if (event.type === "STEP_STARTED") {
    const steps = state.blocks.find((b) => b.kind === "steps" && b.live) as
      | Extract<Block, { kind: "steps" }>
      | undefined
    const nodes = [...(steps?.nodes ?? []), { name: event.stepName ?? "" }]
    return {
      ...state,
      blocks: upsert(state.blocks, {
        kind: "steps",
        id: `steps-${event.runId ?? state.blocks.length}`,
        seconds: 0,
        startedAt: Date.now(),
        ...steps,
        nodes,
        live: true,
        count: nodes.length,
      }),
    }
  }
  if (event.type === "STEP_FINISHED") {
    const steps = state.blocks.find((b) => b.kind === "steps" && b.live) as
      | Extract<Block, { kind: "steps" }>
      | undefined
    if (!steps) return state
    const queryUsed = event.metadata?.query_used
    const nodes = steps.nodes.map((node, index) =>
      index === steps.nodes.length - 1 && node.name === event.stepName
        ? { ...node, queryUsed: typeof queryUsed === "string" ? queryUsed : node.queryUsed }
        : node,
    )
    return {
      ...state,
      blocks: upsert(state.blocks, { ...steps, nodes }),
    }
  }
  if (event.type === "ACTIVITY_SNAPSHOT" && event.activityType === "GATE") {
    const content = event.content ?? {}
    return {
      ...state,
      blocks: upsert(state.blocks, {
        kind: "gate",
        id: event.messageId ?? "gate",
        inDomain: Boolean(content.in_domain ?? content.inDomain),
        reason: String(content.reason ?? ""),
      }),
    }
  }
  if (event.type === "ACTIVITY_SNAPSHOT" && event.activityType === "PLAN") {
    const id = event.messageId ?? "plan"
    const next: Block = {
      kind: "plan",
      id,
      items: (event.content?.items as PlanItem[]) ?? [],
      collapsed: false,
    }
    // A replan arrives as a new snapshot; it supersedes the live plan of this run in place.
    const liveIndex = state.blocks.findIndex(
      (b) => b.kind === "plan" && !b.collapsed && b.id !== id,
    )
    if (liveIndex !== -1) {
      const blocks = state.blocks.slice()
      blocks[liveIndex] = next
      return { ...state, blocks }
    }
    return { ...state, blocks: upsert(state.blocks, next) }
  }
  if (event.type === "ACTIVITY_DELTA" && event.activityType === "PLAN") {
    const plan = state.blocks.find((b) => b.kind === "plan" && b.id === event.messageId) as
      | Extract<Block, { kind: "plan" }>
      | undefined
    if (!plan) return state
    return {
      ...state,
      blocks: upsert(state.blocks, {
        ...plan,
        items: applyPatch(plan.items, event.patch),
      }),
    }
  }
  if (event.type === "TEXT_MESSAGE_START") {
    return {
      ...state,
      blocks: upsert(state.blocks, {
        kind: "assistant",
        id: event.messageId ?? "assistant",
        content: "",
        streaming: true,
        sources: [],
      }),
    }
  }
  if (event.type === "TEXT_MESSAGE_CONTENT") {
    const current = state.blocks.find((b) => b.kind === "assistant" && b.id === event.messageId) as
      | Extract<Block, { kind: "assistant" }>
      | undefined
    return {
      ...state,
      blocks: upsert(state.blocks, {
        kind: "assistant",
        id: event.messageId ?? current?.id ?? "assistant",
        content: (current?.content ?? "") + (event.delta ?? ""),
        streaming: true,
        sources: current?.sources ?? [],
      }),
    }
  }
  if (event.type === "TEXT_MESSAGE_END") {
    const current = state.blocks.find((b) => b.kind === "assistant" && b.id === event.messageId) as
      | Extract<Block, { kind: "assistant" }>
      | undefined
    if (!current) return state
    return { ...state, blocks: upsert(state.blocks, { ...current, streaming: false }) }
  }
  if (event.type === "ACTIVITY_SNAPSHOT" && event.activityType === "SOURCES") {
    const items = (event.content?.items as SourceItem[]) ?? []
    return { ...state, blocks: bindSources(state.blocks, items), sources: items }
  }
  if (event.type === "RUN_FINISHED") {
    const outcome = event.result?.outcome ?? "done"
    const reason = event.result?.reason
    const steps = state.blocks.find((b) => b.kind === "steps" && b.live) as
      | Extract<Block, { kind: "steps" }>
      | undefined
    let blocks = state.blocks
    if (steps) {
      const seconds = steps.startedAt
        ? Math.round((Date.now() - steps.startedAt) / 100) / 10
        : steps.seconds
      blocks = upsert(blocks, {
        ...steps,
        live: false,
        count: steps.nodes.length || steps.count,
        seconds,
      })
    }
    blocks = blocks.map((b) => (b.kind === "plan" && !b.collapsed ? { ...b, collapsed: true } : b))
    if (outcome === "refused") {
      blocks = blocks.map((b) =>
        b.kind === "assistant" ? { ...b, streaming: false } : b,
      )
    } else if (outcome === "insufficient") {
      blocks = [
        ...blocks.filter((b) => b.kind !== "assistant"),
        {
          kind: "outcome",
          id: `outcome-${event.runId ?? blocks.length}`,
          outcome,
          reason: String(reason ?? ""),
        },
      ]
    }
    return { ...state, blocks, status: "idle", showResume: false }
  }
  if (event.type === "RUN_ERROR") {
    return {
      ...state,
      status: "idle",
      blocks: [
        ...state.blocks,
        { kind: "error", id: `error-${event.runId ?? state.blocks.length}`, message: event.message ?? "" },
      ],
    }
  }
  return state
}
