"""AGUI-02: AguiAdapter maps custom+updates to AG-UI events."""

from __future__ import annotations

import inspect
import json
import unittest
import uuid
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import Command, Send

from plan_based_researcher.api import agui as agui_mod
from plan_based_researcher.api.agui import AguiAdapter, STREAM_MODES
from plan_based_researcher.graph.wrap import wrap_node


def parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


async def collect(adapter: AguiAdapter, input: dict | None, **kwargs) -> list[dict]:
    chunks: list[str] = []
    async for frame in adapter.stream(
        thread_id=kwargs.get("thread_id", "tid"),
        run_id=kwargs.get("run_id", "rid"),
        input=input,
        timeout_seconds=kwargs.get("timeout_seconds", 5),
        config=kwargs.get("config"),
    ):
        chunks.append(frame)
    return parse_sse("".join(chunks))


class FakeGraph:
    def __init__(self, items=(), raise_exc: BaseException | None = None) -> None:
        self.items = list(items)
        self.recorded = None
        self.raise_exc = raise_exc

    def astream(self, input, config=None, **kwargs):
        self.recorded = {"input": input, "config": config, **kwargs}
        graph = self

        class Stream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if graph.raise_exc:
                    raise graph.raise_exc
                if not graph.items:
                    raise StopAsyncIteration
                return graph.items.pop(0)

        return Stream()


class AguiAdapterTest(unittest.IsolatedAsyncioTestCase):
    def test_consume_path_is_astream_custom_updates(self) -> None:
        source = inspect.getsource(agui_mod)
        self.assertIn('stream_mode=STREAM_MODES', source)
        self.assertEqual(STREAM_MODES, ["custom", "updates"])
        self.assertNotIn("astream_events", source)

    async def test_step_started_for_every_node(self) -> None:
        names = (
            "gate",
            "planner",
            "dispatch",
            "search",
            "execute",
            "evaluate",
            "replan",
            "finalize",
        )

        class State(TypedDict):
            n: int

        graph = StateGraph(State)
        prev = START
        for name in names:
            async def node(state, _name=name):
                return {}

            graph.add_node(name, wrap_node(name, node))
            graph.add_edge(prev, name)
            prev = name
        graph.add_edge(prev, END)
        compiled = graph.compile()
        events = await collect(AguiAdapter(compiled), {"n": 0})
        started = [e for e in events if e.get("type") == "STEP_STARTED"]
        self.assertEqual([e["stepName"] for e in started], list(names))

    async def test_search_execute_step_started_metadata(self) -> None:
        class State(TypedDict):
            plan: list
            step_index: int

        for name in ("search", "execute"):
            with self.subTest(node=name):
                async def node(state):
                    return {}

                graph = StateGraph(State)
                graph.add_node(name, wrap_node(name, node))
                graph.add_edge(START, name)
                graph.add_edge(name, END)
                compiled = graph.compile()
                events = await collect(
                    AguiAdapter(compiled),
                    {
                        "plan": [{"agent": name, "task": f"{name} task"}],
                        "step_index": 0,
                    },
                )
                started = next(e for e in events if e.get("type") == "STEP_STARTED")
                self.assertEqual(started["stepName"], name)
                self.assertEqual(started["metadata"]["step_index"], 0)
                self.assertEqual(started["metadata"]["agent"], name)
                self.assertEqual(started["metadata"]["task"], f"{name} task")

    async def test_step_finished_query_used_from_step_end(self) -> None:
        class State(TypedDict):
            plan: list
            step_index: int

        async def search(state):
            get_stream_writer()(
                {"event": "step_end", "data": {"query_used": "ti:LoRA"}}
            )
            return {}

        graph = StateGraph(State)
        graph.add_node("search", wrap_node("search", search))
        graph.add_edge(START, "search")
        graph.add_edge("search", END)
        events = await collect(
            AguiAdapter(graph.compile()),
            {"plan": [{"agent": "search", "task": "find"}], "step_index": 0},
        )
        finished = next(e for e in events if e.get("type") == "STEP_FINISHED")
        self.assertEqual(finished["stepName"], "search")
        self.assertEqual(finished["metadata"]["query_used"], "ti:LoRA")

    async def test_parallel_search_step_indexes_differ(self) -> None:
        class State(TypedDict):
            plan: list
            step_index: int

        async def fanout(state):
            return Command(
                goto=[
                    Send("search", {**state, "step_index": 0}),
                    Send("search", {**state, "step_index": 1}),
                ]
            )

        async def search(state):
            return {}

        graph = StateGraph(State)
        graph.add_node("fanout", fanout, destinations=("search",))
        graph.add_node("search", wrap_node("search", search))
        graph.add_edge(START, "fanout")
        graph.add_edge("search", END)
        events = await collect(
            AguiAdapter(graph.compile()),
            {
                "plan": [
                    {"agent": "search", "task": "a"},
                    {"agent": "search", "task": "b"},
                ],
                "step_index": 0,
            },
        )
        started = [
            e
            for e in events
            if e.get("type") == "STEP_STARTED" and e.get("stepName") == "search"
        ]
        self.assertEqual(len(started), 2)
        indexes = {e["metadata"]["step_index"] for e in started}
        self.assertEqual(indexes, {0, 1})

    async def test_leftover_gate_chunk_is_not_activity_snapshot(self) -> None:
        graph = FakeGraph(
            [
                (
                    "custom",
                    {
                        "event": "gate",
                        "data": {
                            "in_domain": True,
                            "language": "en",
                            "reason": "ok",
                        },
                    },
                )
            ]
        )
        events = await collect(AguiAdapter(graph), {"query": "q"})
        self.assertFalse(
            any(
                e.get("type") == "ACTIVITY_SNAPSHOT" and e.get("activityType") == "GATE"
                for e in events
            )
        )

    async def test_plan_event_is_pending_snapshot(self) -> None:
        graph = FakeGraph(
            [
                (
                    "custom",
                    {
                        "event": "plan",
                        "data": {
                            "steps": [
                                {"agent": "search", "task": "Find papers"},
                            ]
                        },
                    },
                )
            ]
        )
        events = await collect(AguiAdapter(graph), {})
        snap = next(e for e in events if e.get("activityType") == "PLAN")
        item = snap["content"]["items"][0]
        self.assertEqual(item["index"], 0)
        self.assertEqual(item["agent"], "search")
        self.assertEqual(item["task"], "Find papers")
        self.assertEqual(item["status"], "pending")
        self.assertIsNone(item.get("feedback"))

    async def test_plan_delta_patch_same_message_id(self) -> None:
        graph = FakeGraph(
            [
                (
                    "custom",
                    {
                        "event": "plan",
                        "data": {
                            "steps": [
                                {"agent": "search", "task": "Find papers"},
                            ]
                        },
                    },
                ),
                (
                    "updates",
                    {
                        "evaluate": {
                            "passed_steps": [0],
                            "eval_by_step": {
                                "0": {"status": "passed", "feedback": "ok"},
                            },
                        }
                    },
                ),
            ]
        )
        events = await collect(AguiAdapter(graph), {"plan": []})
        snap = next(e for e in events if e.get("activityType") == "PLAN" and e["type"] == "ACTIVITY_SNAPSHOT")
        delta = next(e for e in events if e.get("type") == "ACTIVITY_DELTA")
        self.assertEqual(delta["activityType"], "PLAN")
        self.assertEqual(delta["messageId"], snap["messageId"])
        self.assertTrue(delta["patch"])
        paths = {op["path"] for op in delta["patch"]}
        self.assertTrue(any("status" in path or "feedback" in path for path in paths))

    async def test_eval_updates_plan_item_status(self) -> None:
        for status, expected in (("pass", "passed"), ("retry", "retry"), ("replan", "replan")):
            with self.subTest(status=status):
                graph = FakeGraph(
                    [
                        (
                            "custom",
                            {
                                "event": "plan",
                                "data": {
                                    "steps": [{"agent": "search", "task": "Find"}]
                                },
                            },
                        ),
                        (
                            "custom",
                            {
                                "event": "eval",
                                "data": {
                                    "step_index": 0,
                                    "status": status,
                                    "feedback": "english feedback",
                                },
                            },
                        ),
                    ]
                )
                events = await collect(AguiAdapter(graph), {})
                delta = next(e for e in events if e.get("type") == "ACTIVITY_DELTA")
                items = [
                    {
                        "index": 0,
                        "agent": "search",
                        "task": "Find",
                        "status": "pending",
                        "feedback": None,
                    }
                ]
                for op in delta["patch"]:
                    path = op["path"].lstrip("/").split("/")
                    target: object = {"items": items}
                    for key in path[:-1]:
                        target = target[int(key)] if key.isdigit() else target[key]
                    target[path[-1]] = op["value"]
                self.assertEqual(items[0]["status"], expected)
                self.assertEqual(items[0]["feedback"], "english feedback")

    async def test_answer_start_is_text_message_start(self) -> None:
        mid = str(uuid.uuid4())
        graph = FakeGraph(
            [
                (
                    "custom",
                    {"event": "answer_start", "data": {"message_id": mid}},
                )
            ]
        )
        events = await collect(AguiAdapter(graph), {})
        start = next(e for e in events if e["type"] == "TEXT_MESSAGE_START")
        self.assertEqual(start["messageId"], mid)
        self.assertEqual(start["role"], "assistant")

    async def test_answer_delta_is_text_message_content(self) -> None:
        mid = str(uuid.uuid4())
        graph = FakeGraph(
            [
                ("custom", {"event": "answer_start", "data": {"message_id": mid}}),
                ("custom", {"event": "answer_delta", "data": {"text": "Hello"}}),
            ]
        )
        events = await collect(AguiAdapter(graph), {})
        content = next(e for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
        self.assertEqual(content["delta"], "Hello")
        self.assertEqual(content["messageId"], mid)

    async def test_citations_end_then_sources(self) -> None:
        mid = str(uuid.uuid4())
        citation = {
            "n": 1,
            "arxiv_id": "2401.00001",
            "title": "LoRA",
            "year": 2024,
            "url": "https://arxiv.org/abs/2401.00001",
            "excerpt": "low-rank",
            "chunk_id": "c1",
        }
        graph = FakeGraph(
            [
                ("custom", {"event": "answer_start", "data": {"message_id": mid}}),
                ("custom", {"event": "citations", "data": {"citations": [citation]}}),
            ]
        )
        events = await collect(AguiAdapter(graph), {})
        types = [e["type"] for e in events]
        end_i = types.index("TEXT_MESSAGE_END")
        sources = next(e for e in events if e.get("activityType") == "SOURCES")
        self.assertGreater(types.index("ACTIVITY_SNAPSHOT", end_i), end_i)
        self.assertEqual(sources["type"], "ACTIVITY_SNAPSHOT")
        item = sources["content"]["items"][0]
        for field in ("n", "arxiv_id", "title", "year", "url", "excerpt", "chunk_id"):
            with self.subTest(field=field):
                self.assertIn(field, item)
                self.assertEqual(item[field], citation[field])

    async def test_refused_text_end_before_run_finished(self) -> None:
        mid = str(uuid.uuid4())
        graph = FakeGraph(
            [
                ("custom", {"event": "answer_start", "data": {"message_id": mid}}),
                (
                    "custom",
                    {"event": "answer_delta", "data": {"text": "out of scope"}},
                ),
                (
                    "custom",
                    {
                        "event": "done",
                        "data": {"outcome": "refused", "reason": "out of scope"},
                    },
                ),
            ]
        )
        events = await collect(AguiAdapter(graph), {})
        types = [e["type"] for e in events]
        end_i = types.index("TEXT_MESSAGE_END")
        finished_i = types.index("RUN_FINISHED")
        self.assertLess(end_i, finished_i)
        self.assertEqual(events[end_i]["messageId"], mid)

    async def test_refused_run_finished_reason(self) -> None:
        mid = str(uuid.uuid4())
        graph = FakeGraph(
            [
                ("custom", {"event": "answer_start", "data": {"message_id": mid}}),
                (
                    "custom",
                    {"event": "answer_delta", "data": {"text": "out of scope"}},
                ),
                (
                    "custom",
                    {
                        "event": "done",
                        "data": {"outcome": "refused", "reason": "out of scope"},
                    },
                ),
            ]
        )
        events = await collect(AguiAdapter(graph), {})
        finished = next(e for e in events if e["type"] == "RUN_FINISHED")
        self.assertEqual(finished["result"]["outcome"], "refused")
        self.assertEqual(finished["result"]["reason"], "out of scope")

    async def test_run_finished_reason_null_when_done(self) -> None:
        graph = FakeGraph(
            [("custom", {"event": "done", "data": {"outcome": "done"}})]
        )
        events = await collect(AguiAdapter(graph), {})
        finished = next(e for e in events if e["type"] == "RUN_FINISHED")
        self.assertEqual(finished["result"]["outcome"], "done")
        self.assertIsNone(finished["result"].get("reason"))

    async def test_terminal_event_checkpoints_finalize_message(self) -> None:
        class State(TypedDict):
            messages: Annotated[list, add_messages]

        async def finalize(state):
            get_stream_writer()({"event": "done", "data": {"outcome": "done"}})
            return {"messages": [AIMessage(content="ANSWER", id="m-answer")]}

        graph = StateGraph(State)
        graph.add_node("finalize", wrap_node("finalize", finalize))
        graph.add_edge(START, "finalize")
        graph.add_edge("finalize", END)
        compiled = graph.compile(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "tid-answer"}}
        events = await collect(
            AguiAdapter(compiled),
            {"messages": [{"role": "user", "content": "q", "id": "m-user"}]},
            thread_id="tid-answer",
            config=config,
        )
        self.assertEqual(events[-1]["type"], "RUN_FINISHED")
        snapshot = await compiled.aget_state(config)
        contents = [
            message.content if hasattr(message, "content") else message["content"]
            for message in snapshot.values["messages"]
        ]
        self.assertEqual(contents, ["q", "ANSWER"])
