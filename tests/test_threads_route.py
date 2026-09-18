"""AGUI-03: GET /threads/{thread_id} replay."""

from __future__ import annotations

import unittest
from typing import Annotated, TypedDict

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from plan_based_researcher.api.deps import get_graph, get_settings
from plan_based_researcher.api.replay import snapshot_to_agui_messages
from plan_based_researcher.api.routes import router
from plan_based_researcher.graph.project import project_turn


class TinyState(TypedDict):
    query: str
    messages: Annotated[list, add_messages]
    outcome: str


def _projection(outcome: str, *, reason: str = "") -> dict:
    plan = [
        {
            "index": 0,
            "agent": "search",
            "task": "Find",
            "status": "passed",
            "feedback": "ok",
        }
    ]
    return {
        "outcome": outcome,
        "gate": {"in_domain": True, "language": "en", "reason": "in scope"},
        "plan": plan,
        "steps": {"count": 2, "elapsed_ms": 40},
        "citations": [
            {
                "n": 1,
                "chunk_id": "c1",
                "arxiv_id": "2401.00001",
                "title": "LoRA",
                "year": 2024,
                "url": "https://arxiv.org/abs/2401.00001",
                "excerpt": "low-rank",
            }
        ],
    }


def _client_for(compiled):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_graph] = lambda: compiled
    app.dependency_overrides[get_settings] = lambda: object()
    return TestClient(app)


class ThreadsRouteTest(unittest.IsolatedAsyncioTestCase):
    async def _done_refused_graph(self):
        async def finalize(state: TinyState) -> dict:
            outcome = state["outcome"]
            content = "answer [1]" if outcome == "done" else "out of scope"
            return {
                "messages": [
                    AIMessage(
                        id=f"ai-{outcome}",
                        content=content,
                        response_metadata=_projection(outcome),
                    )
                ]
            }

        graph = StateGraph(TinyState)
        graph.add_node("finalize", finalize)
        graph.add_edge(START, "finalize")
        graph.add_edge("finalize", END)
        compiled = graph.compile(checkpointer=MemorySaver())

        def initial(query: str) -> dict:
            return {"query": query, "messages": [{"role": "user", "content": query, "id": "h-x"}], "outcome": "done"}

        compiled.initial_graph_state = initial  # type: ignore[attr-defined]
        compiled.astream = compiled.astream
        return compiled

    async def test_get_thread_200_shape(self) -> None:
        compiled = await self._done_refused_graph()
        config = {"configurable": {"thread_id": "t-done"}}
        await compiled.ainvoke(
            {
                "query": "q1",
                "messages": [{"role": "user", "content": "q1", "id": "h1"}],
                "outcome": "done",
            },
            config,
        )
        client = _client_for(compiled)
        response = client.get("/threads/t-done")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"threadId", "messages", "status"})
        self.assertEqual(body["threadId"], "t-done")
        self.assertEqual(body["status"], "idle")
        self.assertTrue(body["messages"])

    async def test_empty_thread_is_404(self) -> None:
        compiled = await self._done_refused_graph()
        client = _client_for(compiled)
        response = client.get("/threads/missing")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "thread not found"})

    async def test_human_maps_to_user_message(self) -> None:
        human = HumanMessage(id="h-keep", content="hello there")
        mapped = snapshot_to_agui_messages([human])
        self.assertEqual(len(mapped), 1)
        self.assertEqual(mapped[0].role, "user")
        self.assertEqual(mapped[0].id, "h-keep")
        self.assertEqual(mapped[0].content, "hello there")
        mapped_dict = snapshot_to_agui_messages(
            [{"role": "user", "id": "h-dict", "content": "from dict"}]
        )
        self.assertEqual(mapped_dict[0].id, "h-dict")
        self.assertEqual(mapped_dict[0].content, "from dict")

    async def test_done_replay_order(self) -> None:
        ai = AIMessage(
            id="ai-done",
            content="answer [1]",
            response_metadata=_projection("done"),
        )
        mapped = snapshot_to_agui_messages(
            [HumanMessage(id="h1", content="q"), ai]
        )
        kinds = [
            (getattr(m, "activity_type", None) or m.role, getattr(m, "id", None))
            for m in mapped
        ]
        activity_types = [
            m.activity_type for m in mapped if getattr(m, "role", None) == "activity"
        ]
        roles = [m.role for m in mapped]
        self.assertEqual(activity_types, ["GATE", "PLAN", "STEPS", "SOURCES"])
        self.assertEqual(roles.count("assistant"), 1)
        order = []
        for m in mapped[1:]:
            if m.role == "activity":
                order.append(m.activity_type)
            else:
                order.append(m.role)
        self.assertEqual(order, ["GATE", "PLAN", "STEPS", "assistant", "SOURCES"])
        assistant = next(m for m in mapped if m.role == "assistant")
        self.assertEqual(assistant.id, "ai-done")
        self.assertEqual(assistant.content, "answer [1]")
        steps = next(m for m in mapped if getattr(m, "activity_type", None) == "STEPS")
        self.assertEqual(steps.content["count"], 2)
        self.assertEqual(steps.content["elapsed_ms"], 40)

    async def test_non_done_replay_is_outcome_not_assistant(self) -> None:
        for outcome in ("refused", "insufficient", "error"):
            with self.subTest(outcome=outcome):
                ai = AIMessage(
                    id=f"ai-{outcome}",
                    content="terminal reason",
                    response_metadata=_projection(outcome),
                )
                mapped = snapshot_to_agui_messages([ai])
                roles = [m.role for m in mapped]
                self.assertNotIn("assistant", roles)
                types = [m.activity_type for m in mapped if m.role == "activity"]
                self.assertEqual(types[0], "GATE")
                self.assertEqual(types[-1], "OUTCOME")
                outcome_msg = mapped[-1]
                self.assertEqual(outcome_msg.content["outcome"], outcome)
                self.assertEqual(outcome_msg.content["reason"], "terminal reason")

    async def test_status_interrupted_vs_idle(self) -> None:
        async def first(state: TinyState) -> dict:
            return {}

        async def pending(state: TinyState) -> dict:
            return {}

        graph = StateGraph(TinyState)
        graph.add_node("first", first)
        graph.add_node("pending", pending)
        graph.add_edge(START, "first")
        graph.add_edge("first", "pending")
        graph.add_edge("pending", END)
        compiled = graph.compile(
            checkpointer=MemorySaver(), interrupt_before=["pending"]
        )
        compiled.initial_graph_state = lambda q: {  # type: ignore[attr-defined]
            "query": q,
            "messages": [{"role": "user", "content": q, "id": "h"}],
            "outcome": "pending",
        }
        config = {"configurable": {"thread_id": "t-int"}}
        await compiled.ainvoke(
            {
                "query": "q",
                "messages": [{"role": "user", "content": "q", "id": "h"}],
                "outcome": "pending",
            },
            config,
        )
        client = _client_for(compiled)
        interrupted = client.get("/threads/t-int")
        self.assertEqual(interrupted.status_code, 200)
        self.assertEqual(interrupted.json()["status"], "interrupted")

        idle_graph = await self._done_refused_graph()
        await idle_graph.ainvoke(
            {
                "query": "q",
                "messages": [{"role": "user", "content": "q", "id": "h"}],
                "outcome": "done",
            },
            {"configurable": {"thread_id": "t-idle"}},
        )
        idle = _client_for(idle_graph).get("/threads/t-idle")
        self.assertEqual(idle.json()["status"], "idle")

    async def test_replay_uses_project_turn(self) -> None:
        import plan_based_researcher.api.replay as replay_mod

        self.assertIs(replay_mod.project_turn, project_turn)
        state = {
            "outcome": "done",
            "gate": {"in_domain": True, "language": "en", "reason": "in scope"},
            "plan": [{"agent": "search", "task": "Find"}],
            "passed_steps": [0],
            "eval_by_step": {"0": {"status": "passed", "feedback": "ok"}},
            "steps_executed": 2,
            "started_at_ms": 0,
            "citations": _projection("done")["citations"],
        }
        projected = project_turn(state)
        ai = AIMessage(
            id="ai-p",
            content="ans",
            response_metadata=projected,
        )
        mapped = snapshot_to_agui_messages([ai])
        plan = next(m for m in mapped if getattr(m, "activity_type", None) == "PLAN")
        sources = next(m for m in mapped if getattr(m, "activity_type", None) == "SOURCES")
        self.assertEqual(plan.content["items"], projected["plan"])
        self.assertEqual(sources.content["items"], projected["citations"])
