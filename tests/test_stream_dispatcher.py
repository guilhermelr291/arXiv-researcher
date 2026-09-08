"""STRM-04, STRM-10, STRM-11: StreamDispatcher unwrap and SSE-01 handlers."""

from __future__ import annotations

import unittest
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import START, StateGraph

from plan_based_researcher.api.sse import SSE_EVENTS
from plan_based_researcher.api.stream_dispatcher import (
    StreamDispatcher,
    UnknownStreamKindError,
)


def _on_chain_stream(chunk: object) -> dict:
    return {"event": "on_chain_stream", "data": {"chunk": chunk}}


def _handlers(dispatcher: StreamDispatcher) -> dict:
    mapping = getattr(dispatcher, "handlers", None)
    if mapping is None:
        mapping = getattr(dispatcher, "_handlers")
    return mapping


class StreamDispatcherTest(unittest.TestCase):
    def test_unknown_kind_raises_unknown_stream_kind_error(self) -> None:
        dispatcher = StreamDispatcher.default()
        with self.assertRaises(UnknownStreamKindError) as ctx:
            dispatcher.dispatch(
                _on_chain_stream({"event": "not_a_real_kind", "data": {}})
            )
        self.assertIsInstance(ctx.exception, UnknownStreamKindError)
        self.assertEqual(ctx.exception.kind, "not_a_real_kind")

    def test_default_handlers_cover_sse_events(self) -> None:
        dispatcher = StreamDispatcher.default()
        handlers = _handlers(dispatcher)
        self.assertEqual(set(handlers), set(SSE_EVENTS))
        for name in SSE_EVENTS:
            frame = dispatcher.dispatch(_on_chain_stream({"event": name, "data": {}}))
            self.assertIsNotNone(frame)
            self.assertEqual(frame.event, name)

    def test_no_answer_delta_handler(self) -> None:
        dispatcher = StreamDispatcher.default()
        self.assertNotIn("answer_delta", _handlers(dispatcher))
        with self.assertRaises(UnknownStreamKindError):
            dispatcher.dispatch(
                _on_chain_stream({"event": "answer_delta", "data": {}})
            )

    def test_include_types_default_is_chain_only(self) -> None:
        dispatcher = StreamDispatcher.default()
        self.assertEqual(tuple(dispatcher.include_types), ("chain",))
        for forbidden in ("chat_model", "llm", "tool"):
            self.assertNotIn(forbidden, dispatcher.include_types)

    def test_astream_kwargs_stream_mode_string_custom(self) -> None:
        dispatcher = StreamDispatcher.default()
        self.assertEqual(dispatcher.astream_kwargs, {"stream_mode": "custom"})
        self.assertIsInstance(dispatcher.astream_kwargs["stream_mode"], str)
        self.assertNotIsInstance(dispatcher.astream_kwargs["stream_mode"], list)

    def test_on_chain_stream_known_event_yields_plan_frame(self) -> None:
        dispatcher = StreamDispatcher.default()
        frame = dispatcher.dispatch(
            {
                "event": "on_chain_stream",
                "data": {"chunk": {"event": "plan", "data": {"steps": []}}},
            }
        )
        self.assertIsNotNone(frame)
        self.assertEqual(frame.event, "plan")
        self.assertTrue(frame.encode().decode("utf-8").startswith("event: plan"))

    def test_on_chain_start_returns_none(self) -> None:
        dispatcher = StreamDispatcher.default()
        self.assertIsNone(dispatcher.dispatch({"event": "on_chain_start", "data": {}}))

    def test_lifecycle_node_state_chunk_returns_none(self) -> None:
        dispatcher = StreamDispatcher.default()
        self.assertIsNone(dispatcher.dispatch(_on_chain_stream({"foo": 1})))

    def test_writer_event_without_data_fails(self) -> None:
        dispatcher = StreamDispatcher.default()
        with self.assertRaises((UnknownStreamKindError, ValueError)):
            dispatcher.dispatch(_on_chain_stream({"event": "plan"}))


class TinyState(TypedDict):
    x: str


class TinyGraphWriterTest(unittest.IsolatedAsyncioTestCase):
    async def test_tiny_stategraph_writer_emits_plan_frame(self) -> None:
        dispatcher = StreamDispatcher.default()

        async def emit(state: TinyState) -> TinyState:
            get_stream_writer()({"event": "plan", "data": {"steps": []}})
            return state

        graph = StateGraph(TinyState)
        graph.add_node("emit", emit)
        graph.add_edge(START, "emit")
        compiled = graph.compile()

        frames = []
        async for event in compiled.astream_events(
            {"x": "ok"},
            version="v2",
            include_types=dispatcher.include_types,
            **dispatcher.astream_kwargs,
        ):
            frame = dispatcher.dispatch(event)
            if frame is not None:
                frames.append(frame)

        self.assertTrue(any(frame.event == "plan" for frame in frames))
