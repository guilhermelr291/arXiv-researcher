const KEY = "pbr.recents"

export type Recent = {
  threadId: string
  title: string
  updatedAt: string
}

export function loadRecents(): Recent[] {
  if (typeof localStorage === "undefined") return []
  try {
    const raw = localStorage.getItem(KEY)
    const parsed = raw ? (JSON.parse(raw) as Recent[]) : []
    return parsed.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
  } catch {
    return []
  }
}

export function upsertRecent(threadId: string, message: string, now = new Date()): Recent[] {
  const title = message.slice(0, 80)
  const next = loadRecents().filter((row) => row.threadId !== threadId)
  next.unshift({ threadId, title, updatedAt: now.toISOString() })
  localStorage.setItem(KEY, JSON.stringify(next))
  return next
}
