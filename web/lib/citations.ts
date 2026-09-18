import type { ReactNode } from "react"

import { defaultCite, renderInline } from "./markdown"
import type { SourceItem } from "./types"

/**
 * Inline-only transform: `[n]` that matches a source becomes a `.cite` button
 * carrying `data-n`; `[text](url)` stays a link; unknown `[n]` stays text.
 */
export function renderCitedMarkdown(markdown: string, sources: SourceItem[]): ReactNode[] {
  const byN = new Map(sources.map((item) => [item.n, item]))
  return renderInline(markdown, byN, defaultCite, "c")
}
