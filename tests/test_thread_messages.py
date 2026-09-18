"""AGUI-01 AC 5: checkpoint messages keep the first turn on a second run."""

from __future__ import annotations

import unittest
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages


class TinyState(TypedDict):
    query: str
    messages: Annotated[list, add_messages]


class ThreadMessagesTest(unittest.IsolatedAsyncioTestCase):
    async def test_second_run_keeps_first_turn(self) -> None:
        async def finalize(state: TinyState) -> dict:
            return {
                "messages": [
                    AIMessage(
                        id=f"ai-{state['query']}",
                        content=f"answer to {state['query']}",
                        response_metadata={"outcome": "done"},
                    )
                ]
            }

        graph = StateGraph(TinyState)
        graph.add_node("finalize", finalize)
        graph.add_edge(START, "finalize")
        graph.add_edge("finalize", END)
        compiled = graph.compile(checkpointer=MemorySaver())
        config = {"configurable": {"thread_id": "t-keep"}}

        await compiled.ainvoke(
            {"query": "first", "messages": [{"role": "user", "content": "first"}]},
            config,
        )
        await compiled.ainvoke(
            {"query": "second", "messages": [{"role": "user", "content": "second"}]},
            config,
        )
        snapshot = await compiled.aget_state(config)
        messages = snapshot.values["messages"]
        texts = []
        for item in messages:
            if isinstance(item, dict):
                texts.append((item.get("role") or item.get("type"), item.get("content")))
            else:
                role = getattr(item, "type", None) or getattr(item, "role", None)
                texts.append((str(role), getattr(item, "content", None)))
        contents = [content for _role, content in texts]
        self.assertEqual(contents[:4], ["first", "answer to first", "second", "answer to second"])


if __name__ == "__main__":
    unittest.main()
