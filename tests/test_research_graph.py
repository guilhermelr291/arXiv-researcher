"""STRM-06 / STRM-08: ResearchGraph compile-once wrapper."""

from __future__ import annotations

import inspect
import unittest
from typing import cast

from plan_based_researcher.agents.factory import AgentFactory
from plan_based_researcher.eval.strategies import (
    RetrieveEvalStrategy,
    SearchEvalStrategy,
)
from plan_based_researcher.graph.build import GraphDeps
from plan_based_researcher.graph.research_graph import ResearchGraph


class _StubFactory:
    def create(self, name: str) -> object:
        raise RuntimeError("tests do not run agents")


def _stub_deps() -> GraphDeps:
    return GraphDeps(
        factory=cast(AgentFactory, _StubFactory()),
        search_eval=SearchEvalStrategy(api_key=None),
        retrieve_eval=RetrieveEvalStrategy(api_key=None),
    )


class ResearchGraphTest(unittest.TestCase):
    def test_initial_graph_state_query_and_eval_next(self) -> None:
        state = ResearchGraph(_stub_deps()).initial_graph_state("q")
        self.assertIsInstance(state, dict)
        self.assertEqual(state["query"], "q")
        self.assertEqual(state["eval_next"], "dispatch")
        self.assertEqual(
            set(state),
            {
                "query",
                "messages",
                "papers",
                "plan",
                "step_index",
                "passed_steps",
                "retry_counts",
                "retry_count",
                "replan_used",
                "steps_executed",
                "search_artifacts",
                "last_agent",
                "last_eval",
                "eval_by_step",
                "retrieve_query_used",
                "retrieve_ingest",
                "hole_tasks",
                "evidence_chunks",
                "writer_markdown",
                "citations",
                "outcome",
                "eval_next",
                "gate",
                "error_message",
                "reuse_existing_papers",
            },
        )
        messages = state["messages"]
        self.assertIsInstance(messages, list)
        self.assertNotIsInstance(messages, str)
        self.assertEqual(messages[0]["role"], "user")
        self.assertEqual(messages[0]["content"], "q")
        self.assertEqual(state["papers"], [])
        self.assertEqual(state["plan"], [])
        self.assertEqual(state["outcome"], "pending")

    def test_compiles_with_stub_factory_no_postgres(self) -> None:
        graph = ResearchGraph(_stub_deps())
        self.assertIsNotNone(graph._compiled)
        self.assertTrue(callable(graph.astream_events))
        self.assertTrue(callable(graph._compiled.astream_events))

    def test_source_contains_build_graph_not_chatopenai_or_call_model(self) -> None:
        from plan_based_researcher.graph import research_graph as research_graph_mod

        source = inspect.getsource(research_graph_mod)
        self.assertIn("build_graph", source)
        self.assertNotIn("ChatOpenAI", source)
        self.assertNotIn("call_model", source)


if __name__ == "__main__":
    unittest.main()
