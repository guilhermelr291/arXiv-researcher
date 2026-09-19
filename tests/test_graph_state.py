"""Search/eval scratchpads merge within a run and clear between turns."""

from __future__ import annotations

import unittest
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from plan_based_researcher.graph.state import merge_eval_by_step, merge_search_artifacts


def _artifact(step_index: int, query: str) -> dict:
    return {"step_index": step_index, "query_used": query, "hits": []}


class ScratchState(TypedDict):
    query: str
    search_artifacts: Annotated[dict, merge_search_artifacts]
    eval_by_step: Annotated[dict, merge_eval_by_step]


class GraphStateReducersTest(unittest.TestCase):
    def test_empty_update_clears_search_artifacts(self) -> None:
        existing = {"0": _artifact(0, "ti:LoRA")}
        self.assertEqual(merge_search_artifacts(existing, {}), {})

    def test_empty_update_clears_eval_by_step(self) -> None:
        existing = {"0": {"status": "pass", "feedback": "ok"}}
        self.assertEqual(merge_eval_by_step(existing, {}), {})

    def test_none_update_keeps_existing(self) -> None:
        artifacts = {"0": _artifact(0, "ti:LoRA")}
        evals = {"0": {"status": "pass", "feedback": "ok"}}
        self.assertEqual(merge_search_artifacts(artifacts, None), artifacts)
        self.assertEqual(merge_eval_by_step(evals, None), evals)

    def test_nonempty_patch_merges_by_key(self) -> None:
        artifacts = merge_search_artifacts(
            {"0": _artifact(0, "ti:LoRA")},
            {"1": _artifact(1, "ti:QLoRA")},
        )
        self.assertEqual(artifacts["0"]["query_used"], "ti:LoRA")
        self.assertEqual(artifacts["1"]["query_used"], "ti:QLoRA")
        evals = merge_eval_by_step(
            {"0": {"status": "pass", "feedback": "ok"}},
            {"1": {"status": "retry", "feedback": "empty"}},
        )
        self.assertEqual(evals["0"]["status"], "pass")
        self.assertEqual(evals["1"]["status"], "retry")

    def test_same_key_last_write_wins(self) -> None:
        artifacts = merge_search_artifacts(
            {"0": _artifact(0, "ti:LoRA")},
            {"0": _artifact(0, "ti:DoRA")},
        )
        self.assertEqual(artifacts["0"]["query_used"], "ti:DoRA")


class TurnResetTest(unittest.IsolatedAsyncioTestCase):
    async def test_second_turn_input_clears_scratchpads(self) -> None:
        async def echo(state: ScratchState) -> dict:
            return {}

        graph = StateGraph(ScratchState)
        graph.add_node("echo", echo)
        graph.add_edge(START, "echo")
        graph.add_edge("echo", END)
        compiled = graph.compile(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "t-scratch"}}

        await compiled.ainvoke(
            {
                "query": "first",
                "search_artifacts": {"0": _artifact(0, "ti:LoRA")},
                "eval_by_step": {"0": {"status": "pass", "feedback": "ok"}},
            },
            config,
        )
        after_first = await compiled.aget_state(config)
        self.assertEqual(
            after_first.values["search_artifacts"]["0"]["query_used"], "ti:LoRA"
        )
        self.assertEqual(after_first.values["eval_by_step"]["0"]["status"], "pass")

        await compiled.ainvoke(
            {
                "query": "second",
                "search_artifacts": {},
                "eval_by_step": {},
            },
            config,
        )
        after_second = await compiled.aget_state(config)
        self.assertEqual(after_second.values["search_artifacts"], {})
        self.assertEqual(after_second.values["eval_by_step"], {})
        self.assertEqual(after_second.values["query"], "second")


if __name__ == "__main__":
    unittest.main()
