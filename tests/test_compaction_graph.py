"""Compact sits before gate, and a resume or a missing store skips the cut."""

from __future__ import annotations

import unittest
from pathlib import Path
from typing import cast

from langgraph.checkpoint.memory import MemorySaver

from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.graph.build import GraphDeps
from plan_based_researcher.graph.research_graph import ResearchGraph
from tests.compaction_memory import MemoryCompactionStore


class _Runner:
    def __init__(self, update: dict) -> None:
        self._update = update

    async def run(self, state: dict) -> dict:
        return dict(self._update)


class _Factory:
    def create(self, name: str) -> object:
        if name == "gate":
            return _Runner(
                {
                    "gate": {"in_domain": True, "language": "en", "reason": "ok"},
                    "last_agent": "gate",
                    "outcome": "pending",
                }
            )
        raise RuntimeError(name)


def _deps() -> GraphDeps:
    return GraphDeps(
        factory=cast(AgentFactory, _Factory()),
        search_eval=SearchEvalStrategy(api_key=None),
        retrieve_eval=RetrieveEvalStrategy(api_key=None),
    )


class CompactionGraphTest(unittest.IsolatedAsyncioTestCase):
    async def _nodes_until(self, stream, stop: str) -> list[str]:
        nodes: list[str] = []
        async for chunk in stream:
            nodes.extend(chunk.keys())
            for update in chunk.values():
                if isinstance(update, dict):
                    self.assertNotIn("messages", update)
            if stop in nodes:
                break
        await stream.aclose()
        return nodes

    async def test_follow_up_input_keeps_checkpoint_summary(self) -> None:
        graph = ResearchGraph(_deps(), checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "tid-keep-summary"}}
        await graph._compiled.aupdate_state(
            config,
            {"conversation_summary": "KEEP", "applied_watermark": "m2"},
        )
        await self._nodes_until(
            graph.astream(
                graph.initial_graph_state("follow up"),
                config,
                stream_mode="updates",
            ),
            "gate",
        )
        snapshot = await graph.aget_state(config)
        self.assertEqual(snapshot.values["conversation_summary"], "KEEP")
        self.assertEqual(snapshot.values["applied_watermark"], "m2")

    async def test_fresh_run_visits_compact_before_gate(self) -> None:
        graph = ResearchGraph(_deps())
        state = graph.initial_graph_state("q")
        nodes = await self._nodes_until(
            graph.astream(state, stream_mode="updates"),
            "gate",
        )
        self.assertLess(nodes.index("compact"), nodes.index("gate"))

    async def test_resume_astream_none_skips_compact(self) -> None:
        graph = ResearchGraph(_deps(), checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "tid-resume"}}
        state = graph.initial_graph_state("q")
        first: list[str] = []
        async for chunk in graph.astream(
            state,
            config,
            stream_mode="updates",
            interrupt_before=["gate"],
        ):
            first.extend(chunk.keys())
        self.assertIn("compact", first)
        self.assertNotIn("gate", first)
        second = await self._nodes_until(
            graph.astream(None, config, stream_mode="updates"),
            "gate",
        )
        self.assertNotIn("compact", second)

    async def test_missing_store_enters_gate(self) -> None:
        store = MemoryCompactionStore()
        graph = ResearchGraph(_deps())
        state = graph.initial_graph_state("q")
        state["messages"] = [{"id": "m1", "role": "user", "content": "q"}]
        nodes = await self._nodes_until(
            graph.astream(state, stream_mode="updates"),
            "gate",
        )
        self.assertIn("gate", nodes)
        self.assertEqual(state["messages"][0]["id"], "m1")
        self.assertEqual(store.rows, {})

    def test_recall_script_has_no_compaction_store(self) -> None:
        text = Path("scripts/retrieve_writer_recall.py").read_text(encoding="utf-8")
        self.assertIn(
            "ResearchGraph(deps, checkpointer=None, halt_before_writer=True)",
            text,
        )
        self.assertNotIn("compaction", text)


if __name__ == "__main__":
    unittest.main()
