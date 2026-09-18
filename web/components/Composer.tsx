"use client"

import { FormEvent, KeyboardEvent, useRef } from "react"

type Props = {
  value: string
  onChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  streaming: boolean
  disabled?: boolean
}

export function Composer({ value, onChange, onSend, onStop, streaming, disabled = false }: Props) {
  const areaRef = useRef<HTMLTextAreaElement>(null)
  const canSend = !disabled && value.trim().length > 0

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSend) return
    onSend()
    const area = areaRef.current
    if (area) area.style.height = ""
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return
    event.preventDefault()
    event.currentTarget.form?.requestSubmit()
  }

  function grow(area: HTMLTextAreaElement) {
    area.style.height = "auto"
    area.style.height = `${Math.min(area.scrollHeight, 200)}px`
  }

  return (
    <form className="composer" onSubmit={submit}>
      <textarea
        ref={areaRef}
        className="ui"
        rows={1}
        value={value}
        disabled={disabled}
        aria-label="Message"
        placeholder="Ask about a paper, a method, a result…"
        onChange={(event) => {
          onChange(event.target.value)
          grow(event.target)
        }}
        onKeyDown={onKeyDown}
      />
      {streaming ? (
        <button type="button" className="stop ui" onClick={onStop}>
          Stop
        </button>
      ) : (
        <button type="submit" className="send ui" disabled={!canSend}>
          Send
        </button>
      )}
    </form>
  )
}
