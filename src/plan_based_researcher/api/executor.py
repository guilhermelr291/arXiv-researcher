"""Research graph SSE execute facade (STRM-02, STRM-05, STRM-09, STRM-12)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

from plan_based_researcher.api.sse import SseFrame
from plan_based_researcher.api.stream_dispatcher import StreamDispatcher
from plan_based_researcher.graph.research_graph import ResearchGraph

_SENTINEL = object()


class ResearchExecutor:
    def __init__(self, graph: ResearchGraph, dispatcher: StreamDispatcher) -> None:
        self._graph = graph
        self._dispatcher = dispatcher

    async def execute(
        self, query: str, thread_id: str, timeout_seconds: int
    ) -> AsyncIterator[bytes]:
        graph = self._graph
        dispatcher = self._dispatcher
        config = {"configurable": {"thread_id": thread_id}}
        stream = None
        try:
            stream = graph.astream_events(
                graph.initial_graph_state(query),
                config=config,
                version="v2",
                include_types=dispatcher.include_types,
                **dispatcher.astream_kwargs,
            )
            aiter = stream.__aiter__()
            deadline = time.monotonic() + timeout_seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    yield SseFrame("insufficient", {"reason": "timeout"}).encode()
                    return
                try:
                    event = await asyncio.wait_for(
                        anext(aiter, _SENTINEL),
                        timeout=remaining,
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    yield SseFrame("insufficient", {"reason": "timeout"}).encode()
                    return
                if event is _SENTINEL:
                    return
                frame = dispatcher.dispatch(event)
                if frame is not None:
                    yield frame.encode()
        except Exception as exc:
            yield SseFrame("error", {"message": str(exc)}).encode()
        finally:
            aclose = getattr(stream, "aclose", None) if stream is not None else None
            if aclose is not None:
                await aclose()
