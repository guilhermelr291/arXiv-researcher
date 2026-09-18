"""AGUI-01 AC 12: new input on a thread with pending next starts from START."""

from __future__ import annotations

import unittest
from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph


class TinyState(TypedDict):
    query: str
    ran: list[str]


class PendingNextTest(unittest.IsolatedAsyncioTestCase):
    async def test_new_input_discards_pending_and_starts(self) -> None:
        ran: list[str] = []

        async def first(state: TinyState) -> dict:
            ran.append(f"first:{state['query']}")
            return {"ran": list(ran)}

        async def pending(state: TinyState) -> dict:
            ran.append(f"pending:{state['query']}")
            return {"ran": list(ran)}

        graph = StateGraph(TinyState)
        graph.add_node("first", first)
        graph.add_node("pending", pending)
        graph.add_edge(START, "first")
        graph.add_edge("first", "pending")
        graph.add_edge("pending", END)
        compiled = graph.compile(
            checkpointer=MemorySaver(),
            interrupt_before=["pending"],
        )
        config = {"configurable": {"thread_id": "t-pending"}}
        await compiled.ainvoke({"query": "one", "ran": []}, config)
        snapshot = await compiled.aget_state(config)
        self.assertTrue(snapshot.next)
        self.assertEqual(ran, ["first:one"])

        await compiled.ainvoke({"query": "two", "ran": []}, config)
        self.assertNotIn("pending:one", ran)
        self.assertIn("first:two", ran)


if __name__ == "__main__":
    unittest.main()
