export type Role = "user" | "assistant" | "activity"

export type UserMessage = {
  id: string
  role: "user"
  content: string
}

export type AssistantMessage = {
  id: string
  role: "assistant"
  content: string
}

export type ActivityMessage = {
  id: string
  role: "activity"
  activityType: string
  content: Record<string, unknown>
}

export type AguiMessage = UserMessage | AssistantMessage | ActivityMessage

export type RunAgentInput = {
  threadId: string
  runId: string
  messages: UserMessage[]
  tools: []
  context: []
  forwardedProps: { resume?: boolean }
}

export type SourceItem = {
  n: number
  arxiv_id: string
  title: string
  year: number
  url: string
  excerpt: string
  chunk_id: string
}

export type PlanItem = {
  index: number
  agent: string
  task: string
  status: string
  feedback: string | null
}

export type StepNode = {
  name: string
  queryUsed?: string
}

export type AguiEvent = {
  type: string
  threadId?: string
  runId?: string
  stepName?: string
  messageId?: string
  role?: string
  delta?: string
  activityType?: string
  content?: Record<string, unknown>
  patch?: { op: string; path: string; value?: unknown }[]
  result?: { outcome?: string; reason?: string | null }
  message?: string
  metadata?: Record<string, unknown>
}
