"""SSE-01 handler map and astream_events unwrap (STRM-04, STRM-10, STRM-11)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from plan_based_researcher.api.sse import SSE_EVENTS, SseFrame


class UnknownStreamKindError(Exception):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(kind)


class StreamDispatcher:
    def __init__(
        self,
        handlers: Mapping[str, Callable[[object], SseFrame]],
        *,
        include_types: Sequence[str] = ("chain",),
        stream_mode: str = "custom",
    ) -> None:
        self._handlers = handlers
        self.include_types = include_types
        self.astream_kwargs: dict[str, str] = {"stream_mode": stream_mode}

    @classmethod
    def default(cls) -> StreamDispatcher:
        handlers = {
            name: (lambda data, name=name: SseFrame(name, data)) for name in SSE_EVENTS
        }
        return cls(handlers)

    def dispatch(self, event: Mapping[str, Any]) -> SseFrame | None:
        if event["event"] != "on_chain_stream":
            return None
        try:
            chunk: object = event["data"]["chunk"]
        except (KeyError, TypeError):
            chunk = None
        if isinstance(chunk, tuple) and chunk and chunk[0] == "custom":
            chunk = chunk[-1]
        if isinstance(chunk, dict) and "event" in chunk and "data" in chunk:
            kind = chunk["event"]
            try:
                handler = self._handlers[kind]
            except KeyError:
                raise UnknownStreamKindError(kind) from None
            return handler(chunk["data"])
        if isinstance(chunk, dict) and "event" in chunk:
            raise UnknownStreamKindError(chunk["event"])
        return None
