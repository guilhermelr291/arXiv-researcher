"""OOD-01/02: gate node product events and refuse routing."""

from __future__ import annotations

import uuid
import unittest
from typing import cast
from unittest.mock import patch

from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.graph.build import GraphDeps
from plan_based_researcher.api.agui import AguiAdapter
from plan_based_researcher.graph.nodes.finalize import make_finalize_node
from plan_based_researcher.graph.nodes.gate import make_gate_node
from plan_based_researcher.graph.research_graph import ResearchGraph
from tests.test_agui_adapter import collect

_GATE_WRITER = "plan_based_researcher.graph.nodes.gate.get_stream_writer"
_FINALIZE_WRITER = "plan_based_researcher.graph.nodes.finalize.get_stream_writer"


def _spy_stream_writer(payloads: list[dict]):
    def get_stream_writer():
        def writer(payload: dict) -> None:
            payloads.append(payload)

        return writer

    return get_stream_writer


class _StubRunner:
    def __init__(self, update: dict) -> None:
        self._update = update

    async def run(self, state: dict) -> dict:
        return dict(self._update)


class _RecordingFactory:
    def __init__(self, gate_update: dict) -> None:
        self.names: list[str] = []
        self._gate_update = gate_update

    def create(self, name: str) -> object:
        self.names.append(name)
        if name == "gate":
            return _StubRunner(self._gate_update)
        raise AssertionError(f"unexpected agent {name!r}")


def _in_domain_update() -> dict:
    return {
        "gate": {
            "in_domain": True,
            "language": "en",
            "reason": "in scope",
        },
        "last_agent": "gate",
        "outcome": "pending",
    }


def _refused_update(*, reason: str = "out of scope") -> dict:
    return {
        "gate": {
            "in_domain": False,
            "language": "en",
            "reason": reason,
        },
        "last_agent": "gate",
        "outcome": "refused",
    }


class GateNodeTest(unittest.IsolatedAsyncioTestCase):
    async def test_in_domain_emits_no_gate_event(self) -> None:
        payloads: list[dict] = []
        factory = _RecordingFactory(_in_domain_update())
        node = make_gate_node(cast(AgentFactory, factory))
        with patch(_GATE_WRITER, _spy_stream_writer(payloads)):
            await node({"query": "What is LoRA?"})
        self.assertFalse(any(payload.get("event") == "gate" for payload in payloads))

    async def test_refused_emits_answer_start_then_one_delta(self) -> None:
        payloads: list[dict] = []
        factory = _RecordingFactory(_refused_update())
        node = make_gate_node(cast(AgentFactory, factory))
        with patch(_GATE_WRITER, _spy_stream_writer(payloads)):
            await node({"query": "What is the weather?"})
        events = [payload.get("event") for payload in payloads]
        self.assertNotIn("gate", events)
        self.assertEqual(events, ["answer_start", "answer_delta"])
        start = payloads[0]
        message_id = start["data"]["message_id"]
        uuid.UUID(message_id)
        self.assertEqual(payloads[1]["data"]["text"], "out of scope")

    async def test_refused_sets_writer_message_id_without_messages(self) -> None:
        payloads: list[dict] = []
        factory = _RecordingFactory(_refused_update())
        node = make_gate_node(cast(AgentFactory, factory))
        with patch(_GATE_WRITER, _spy_stream_writer(payloads)):
            update = await node({"query": "What is the weather?"})
        message_id = payloads[0]["data"]["message_id"]
        self.assertEqual(update.get("writer_message_id"), message_id)
        self.assertNotIn("messages", update)

    async def test_refused_ainvoke_skips_planner_and_writer(self) -> None:
        factory = _RecordingFactory(_refused_update())
        deps = GraphDeps(
            factory=cast(AgentFactory, factory),
            search_eval=SearchEvalStrategy(api_key=None),
            retrieve_eval=RetrieveEvalStrategy(api_key=None),
        )
        graph = ResearchGraph(deps)
        state = graph.initial_graph_state("What is the weather?")
        nodes: list[str] = []
        seen_outcome = None
        async for chunk in graph.astream(state, stream_mode="updates"):
            if isinstance(chunk, dict):
                nodes.extend(chunk.keys())
                for value in chunk.values():
                    if isinstance(value, dict) and "outcome" in value:
                        seen_outcome = value.get("outcome")
        self.assertNotIn("planner", factory.names)
        self.assertNotIn("writer", factory.names)
        self.assertIn("gate", factory.names)
        self.assertEqual(seen_outcome, "refused")
        self.assertIn("finalize", nodes)
        self.assertNotIn("planner", nodes)
        self.assertNotIn("execute", nodes)

    async def test_compiled_refuse_streams_writer_text_events(self) -> None:
        factory = _RecordingFactory(_refused_update())
        deps = GraphDeps(
            factory=cast(AgentFactory, factory),
            search_eval=SearchEvalStrategy(api_key=None),
            retrieve_eval=RetrieveEvalStrategy(api_key=None),
        )
        graph = ResearchGraph(deps)
        state = graph.initial_graph_state("What is the weather?")
        events = await collect(AguiAdapter(graph), state)
        types = [event["type"] for event in events]
        self.assertIn("TEXT_MESSAGE_START", types)
        content = next(event for event in events if event["type"] == "TEXT_MESSAGE_CONTENT")
        self.assertEqual(content["delta"], "out of scope")
        self.assertLess(types.index("TEXT_MESSAGE_END"), types.index("RUN_FINISHED"))
        self.assertFalse(
            any(
                event.get("type") == "ACTIVITY_SNAPSHOT"
                and event.get("activityType") == "GATE"
                for event in events
            )
        )
        finished = next(event for event in events if event["type"] == "RUN_FINISHED")
        self.assertEqual(finished["result"]["outcome"], "refused")
        self.assertEqual(finished["result"]["reason"], "out of scope")

    async def test_refused_stream_text_equals_aimessage_and_reason(self) -> None:
        payloads: list[dict] = []
        reason = "out of scope"
        factory = _RecordingFactory(_refused_update(reason=reason))
        gate = make_gate_node(cast(AgentFactory, factory))
        with patch(_GATE_WRITER, _spy_stream_writer(payloads)):
            gate_update = await gate({"query": "What is the weather?"})
        delta_text = payloads[1]["data"]["text"]
        finalize = make_finalize_node()
        with patch(_FINALIZE_WRITER, _spy_stream_writer([])):
            final_update = await finalize(
                {
                    "outcome": "refused",
                    "gate": gate_update["gate"],
                    "writer_message_id": gate_update["writer_message_id"],
                    "plan": [],
                    "passed_steps": [],
                    "eval_by_step": {},
                    "steps_executed": 0,
                    "started_at_ms": 1,
                    "citations": [],
                }
            )
        message = (final_update.get("messages") or [])[0]
        self.assertEqual(delta_text, reason)
        self.assertEqual(getattr(message, "content", None), reason)
        self.assertEqual(gate_update["gate"]["reason"], reason)


if __name__ == "__main__":
    unittest.main()
