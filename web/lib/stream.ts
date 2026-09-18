import type { AguiEvent, RunAgentInput } from "./types"

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8001"

export function apiUrl(path: string): string {
  return `${API}${path}`
}

export async function consumeSse(
  response: Response,
  onEvent: (event: AguiEvent) => void,
  signal?: AbortSignal,
): Promise<{ terminal: "finished" | "error" | "dropped" }> {
  const reader = response.body?.getReader()
  if (!reader) return { terminal: "dropped" }
  const decoder = new TextDecoder()
  let buffer = ""
  let terminal: "finished" | "error" | "dropped" = "dropped"
  try {
    while (true) {
      if (signal?.aborted) break
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split("\n\n")
      buffer = parts.pop() ?? ""
      for (const part of parts) {
        for (const line of part.split("\n")) {
          if (!line.startsWith("data:")) continue
          const event = JSON.parse(line.slice(5).trim()) as AguiEvent
          onEvent(event)
          if (event.type === "RUN_FINISHED") terminal = "finished"
          if (event.type === "RUN_ERROR") terminal = "error"
        }
      }
    }
  } catch {
    return { terminal }
  }
  return { terminal }
}

export async function postAgent(
  input: RunAgentInput,
  onEvent: (event: AguiEvent) => void,
  signal?: AbortSignal,
): Promise<{ terminal: "finished" | "error" | "dropped" }> {
  const response = await fetch(apiUrl("/agent"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  })
  return consumeSse(response, onEvent, signal)
}

export function normalRunInput(threadId: string, content: string): RunAgentInput {
  return {
    threadId,
    runId: crypto.randomUUID(),
    messages: [{ id: crypto.randomUUID(), role: "user", content }],
    tools: [],
    context: [],
    forwardedProps: {},
  }
}

export function resumeRunInput(threadId: string): RunAgentInput {
  return {
    threadId,
    runId: crypto.randomUUID(),
    messages: [],
    tools: [],
    context: [],
    forwardedProps: { resume: true },
  }
}
