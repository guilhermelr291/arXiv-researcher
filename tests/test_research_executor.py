"""STRM-02, STRM-05, STRM-09, STRM-12: ResearchExecutor astream_events facade."""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import unittest

from plan_based_researcher.api.executor import ResearchExecutor
from plan_based_researcher.api.stream_dispatcher import StreamDispatcher

_PLAN_ENVELOPE = {
    "event": "on_chain_stream",
    "data": {"chunk": {"event": "plan", "data": {"steps": []}}},
}

_SSE01_NAMES = frozenset(
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


class FakeGraph:
    def __init__(
        self,
        events=(),
        hang=False,
        raise_exc: BaseException | None = None,
    ):
        self.events = list(events)
        self.hang = hang
        self.raise_exc = raise_exc
        self.recorded = None
        self.aclose_called = False
        self.initial_state = None

    def initial_graph_state(self, query: str):
        self.initial_state = {"query": query}
        return self.initial_state

    def astream_events(self, input, config=None, **kwargs):
        self.recorded = {"input": input, "config": config, **kwargs}
        graph = self

        class Stream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if graph.raise_exc:
                    raise graph.raise_exc
                if graph.hang:
                    await asyncio.sleep(60)
                if not graph.events:
                    raise StopAsyncIteration
                return graph.events.pop(0)

            async def aclose(self):
                graph.aclose_called = True

        return Stream()


async def collect(executor, **kwargs):
    query = kwargs.pop("query", "q")
    thread_id = kwargs.pop("thread_id", "tid")
    timeout_seconds = kwargs.pop("timeout_seconds", 30)
    out = []
    async for chunk in executor.execute(query, thread_id, timeout_seconds, **kwargs):
        out.append(chunk)
    return out


class ResearchExecutorTest(unittest.IsolatedAsyncioTestCase):
    async def test_astream_events_kwargs_from_dispatcher(self) -> None:
        graph = FakeGraph()
        dispatcher = StreamDispatcher(
            {},
            include_types=("llm",),
            stream_mode="updates",
        )
        executor = ResearchExecutor(graph, dispatcher)
        await collect(executor)
        rec = graph.recorded
        self.assertIsNotNone(rec)
        self.assertEqual(rec["version"], "v2")
        self.assertEqual(rec["include_types"], dispatcher.include_types)
        self.assertEqual(rec["stream_mode"], dispatcher.astream_kwargs["stream_mode"])
        self.assertEqual(rec["config"], {"configurable": {"thread_id": "tid"}})
        self.assertIs(rec["input"], graph.initial_state)
        self.assertEqual(rec["input"], graph.initial_graph_state("q"))

    async def test_yields_encoded_plan_frame(self) -> None:
        graph = FakeGraph(events=[_PLAN_ENVELOPE])
        executor = ResearchExecutor(graph, StreamDispatcher.default())
        chunks = await collect(executor)
        text = b"".join(chunks).decode("utf-8")
        self.assertTrue(text.startswith("event: plan"))

    async def test_timeout_yields_insufficient(self) -> None:
        graph = FakeGraph(hang=True)
        executor = ResearchExecutor(graph, StreamDispatcher.default())
        chunks = await collect(executor, timeout_seconds=0)
        text = b"".join(chunks).decode("utf-8")
        self.assertIn("event: insufficient", text)
        data_line = next(line for line in text.splitlines() if line.startswith("data: "))
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertEqual(payload["reason"], "timeout")
        self.assertTrue(graph.aclose_called)

    async def test_iterator_error_yields_error(self) -> None:
        graph = FakeGraph(raise_exc=RuntimeError("boom"))
        executor = ResearchExecutor(graph, StreamDispatcher.default())
        chunks = await collect(executor)
        text = b"".join(chunks).decode("utf-8")
        self.assertIn("event: error", text)
        data_line = next(line for line in text.splitlines() if line.startswith("data: "))
        payload = json.loads(data_line.removeprefix("data: "))
        self.assertIn("boom", payload["message"])

    async def test_aclose_ran(self) -> None:
        graph = FakeGraph(events=[_PLAN_ENVELOPE])
        executor = ResearchExecutor(graph, StreamDispatcher.default())
        await collect(executor)
        self.assertTrue(graph.aclose_called)

    def test_source_has_no_sse01_name_if_elif(self) -> None:
        from plan_based_researcher.api import executor as executor_mod

        source = inspect.getsource(executor_mod)
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                for child in ast.walk(node.test):
                    if isinstance(child, ast.Constant) and child.value in _SSE01_NAMES:
                        self.fail(
                            f"SSE-01 name {child.value!r} used in if/elif condition"
                        )
        self.assertNotIn("astream(", source)
        self.assertIn("astream_events", source)


if __name__ == "__main__":
    unittest.main()
