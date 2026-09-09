"""SSE frame mapper: spec event names only (SSE-01, SSE-02)."""

from __future__ import annotations

import json
from dataclasses import dataclass

SSE_EVENTS: frozenset[str] = frozenset(
    {
        "gate",
        "plan",
        "step_start",
        "step_end",
        "eval",
        "answer_delta",
        "citations",
        "done",
        "insufficient",
        "error",
    }
)

SSE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@dataclass(frozen=True, slots=True)
class SseFrame:
    event: str
    data: object

    def encode(self) -> bytes:
        if self.event not in SSE_EVENTS:
            raise ValueError(f"unknown SSE event: {self.event!r}")
        payload = json.dumps(self.data, default=str)
        return f"event: {self.event}\ndata: {payload}\n\n".encode("utf-8")


def encode_sse(event: str, data: object) -> bytes:
    """Encode one SSE frame as UTF-8 ``event:`` / ``data:`` bytes."""
    return SseFrame(event, data).encode()


def encode_payload(payload: dict) -> bytes:
    """Encode a LangGraph ``{event, data}`` dict to an SSE frame."""
    return encode_sse(payload["event"], payload["data"])
