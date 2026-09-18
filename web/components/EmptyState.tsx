"use client"

const SUGGESTIONS = [
  "What is LoRA and why does it cut trainable parameters?",
  "How does FlashAttention avoid materialising the attention matrix?",
  "Compare DPO with RLHF for preference alignment.",
] as const

type Props = {
  onPick: (text: string) => void
  disabled?: boolean
}

export function EmptyState({ onPick, disabled = false }: Props) {
  return (
    <div className="empty">
      <div className="empty-orb" aria-hidden="true" />
      <h1>Where do we start?</h1>
      <p className="ui muted intro">
        Ask an AI/ML question. The desk searches arXiv, plans the work, and writes a cited
        answer.
      </p>
      <div className="pills">
        {SUGGESTIONS.map((text) => (
          <button
            key={text}
            type="button"
            className="pill ui"
            disabled={disabled}
            onClick={() => onPick(text)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  )
}
