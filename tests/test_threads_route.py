"""AGUI-03: GET /threads/{thread_id} replay."""

from __future__ import annotations

import unittest
from typing import Annotated, TypedDict

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from plan_based_researcher.api.deps import get_graph, get_settings, get_transcript
from plan_based_researcher.api.replay import snapshot_to_agui_messages
from plan_based_researcher.api.routes import router
from plan_based_researcher.graph.project import project_turn
from tests.transcript_memory import MemoryTranscriptStore


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


def _citation(n: int, excerpt: str) -> dict:
    return {
        "n": n,
        "chunk_id": f"c{n}",
        "arxiv_id": f"2401.0000{n}",
        "title": f"Paper {n}",
        "year": 2024,
        "url": f"https://arxiv.org/abs/2401.0000{n}",
        "excerpt": excerpt,
    }


def _assistant_doc(**overrides) -> dict:
    doc = {
        "outcome": "done",
        "content": "answer [1]",
        "gate": {"in_domain": True, "reason": "in scope"},
        "plan": [
            {
                "index": 0,
                "agent": "search",
                "task": "Find",
                "status": "passed",
                "feedback": "ok",
            }
        ],
        "steps": {
            "count": 1,
            "elapsed_ms": 40,
            "nodes": [{"name": "search", "query_used": "LoRA"}],
        },
        "citations": [_citation(1, "low-rank")],
    }
    doc.update(overrides)
    return doc


def _activity_types(messages: list) -> list[str]:
    return [
        row.get("activityType")
        for row in messages
        if row.get("role") == "activity"
    ]


def _client_for(compiled, store=None):
    app = FastAPI()
    app.include_router(router)
    fake_store = store if store is not None else MemoryTranscriptStore()
    app.dependency_overrides[get_graph] = lambda: compiled
    app.dependency_overrides[get_settings] = lambda: object()
    app.dependency_overrides[get_transcript] = lambda: fake_store
    return TestClient(app), fake_store


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
        client, store = _client_for(compiled)
        await store.insert_user("t-done", "h1", "q1")
        await store.insert_assistant_turn("t-done", "ai-done", _assistant_doc())
        response = client.get("/threads/t-done")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"threadId", "messages", "status"})
        self.assertEqual(body["threadId"], "t-done")
        self.assertEqual(body["status"], "idle")
        self.assertTrue(body["messages"])

    async def test_empty_thread_is_404(self) -> None:
        compiled = await self._done_refused_graph()
        client, _store = _client_for(compiled)
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
        client, store = _client_for(compiled)
        await store.insert_user("t-int", "h-int", "q")
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
        idle_client, idle_store = _client_for(idle_graph)
        await idle_store.insert_user("t-idle", "h-idle", "q")
        idle = idle_client.get("/threads/t-idle")
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

    async def test_list_threads_sorted_updated_at_desc(self) -> None:
        store = MemoryTranscriptStore()
        await store.insert_user("tid-old", "u-old", "older title")
        await store.insert_user("tid-new", "u-new", "newer title")
        store.threads["tid-old"].updated_at = "2026-09-01T00:00:00Z"
        store.threads["tid-new"].updated_at = "2026-09-19T12:00:00Z"
        client, _store = _client_for(SimpleNamespace(), store)
        response = client.get("/threads")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsInstance(body, list)
        self.assertEqual(len(body), 2)
        for row in body:
            self.assertEqual(set(row), {"threadId", "title", "updatedAt"})
        self.assertEqual(body[0]["threadId"], "tid-new")
        self.assertEqual(body[0]["title"], "newer title")
        self.assertEqual(body[0]["updatedAt"], "2026-09-19T12:00:00Z")
        self.assertEqual(body[1]["threadId"], "tid-old")
        self.assertEqual(
            [row["updatedAt"] for row in body],
            sorted((row["updatedAt"] for row in body), reverse=True),
        )

    async def test_list_threads_empty_is_200_array(self) -> None:
        client, _store = _client_for(SimpleNamespace(), MemoryTranscriptStore())
        response = client.get("/threads")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    async def test_get_thread_200_from_transcript_not_checkpoint(self) -> None:
        compiled = await self._done_refused_graph()
        await compiled.ainvoke(
            {
                "query": "from-checkpoint",
                "messages": [
                    {"role": "user", "content": "from-checkpoint", "id": "h-cp"}
                ],
                "outcome": "done",
            },
            {"configurable": {"thread_id": "tid-src"}},
        )
        store = MemoryTranscriptStore()
        await store.insert_user("tid-src", "h-tr", "from-transcript")
        client, _store = _client_for(compiled, store)
        response = client.get("/threads/tid-src")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"threadId", "messages", "status"})
        blob = str(body["messages"])
        self.assertIn("from-transcript", blob)
        self.assertNotIn("from-checkpoint", blob)

    async def test_empty_transcript_is_404_despite_checkpoint(self) -> None:
        compiled = await self._done_refused_graph()
        await compiled.ainvoke(
            {
                "query": "checkpoint only",
                "messages": [
                    {"role": "user", "content": "checkpoint only", "id": "h-cp"}
                ],
                "outcome": "done",
            },
            {"configurable": {"thread_id": "tid-empty"}},
        )
        client, _store = _client_for(compiled, MemoryTranscriptStore())
        response = client.get("/threads/tid-empty")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"detail": "thread not found"})

    async def test_replay_user_item_id_and_content(self) -> None:
        store = MemoryTranscriptStore()
        await store.insert_user("tid-u", "u-keep", "hello there")
        compiled = await self._done_refused_graph()
        client, _store = _client_for(compiled, store)
        response = client.get("/threads/tid-u")
        self.assertEqual(response.status_code, 200)
        users = [
            row
            for row in response.json()["messages"]
            if row.get("role") == "user"
        ]
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["id"], "u-keep")
        self.assertEqual(users[0]["content"], "hello there")

    async def test_done_turn_replay_order(self) -> None:
        store = MemoryTranscriptStore()
        await store.insert_assistant_turn(
            "tid-done",
            "ai-done",
            _assistant_doc(content="stored markdown"),
        )
        compiled = await self._done_refused_graph()
        client, _store = _client_for(compiled, store)
        messages = client.get("/threads/tid-done").json()["messages"]
        sequence = [
            (row["role"], row.get("activityType"))
            for row in messages
        ]
        expected = [
            ("activity", "GATE"),
            ("activity", "PLAN"),
            ("activity", "STEPS"),
            ("assistant", None),
            ("activity", "SOURCES"),
        ]
        self.assertEqual(sequence, expected)
        assistant = next(row for row in messages if row["role"] == "assistant")
        self.assertEqual(assistant["id"], "ai-done")
        self.assertEqual(assistant["content"], "stored markdown")

    async def test_non_done_turn_replay_is_outcome_not_assistant(self) -> None:
        compiled = await self._done_refused_graph()
        for outcome in ("refused", "insufficient", "error"):
            with self.subTest(outcome=outcome):
                store = MemoryTranscriptStore()
                await store.insert_assistant_turn(
                    f"tid-{outcome}",
                    f"ai-{outcome}",
                    _assistant_doc(
                        outcome=outcome,
                        content=f"{outcome} because",
                    ),
                )
                client, _store = _client_for(compiled, store)
                messages = client.get(f"/threads/tid-{outcome}").json()["messages"]
                roles = [row["role"] for row in messages]
                self.assertNotIn("assistant", roles)
                types = _activity_types(messages)
                self.assertEqual(types[0], "GATE")
                self.assertEqual(types[-1], "OUTCOME")
                outcome_msg = messages[-1]
                self.assertEqual(outcome_msg["content"]["outcome"], outcome)
                self.assertEqual(outcome_msg["content"]["reason"], f"{outcome} because")

    async def test_status_from_checkpoint_next(self) -> None:
        interrupted_graph = StateGraph(TinyState)
        interrupted_graph.add_node("first", lambda state: {})
        interrupted_graph.add_node("pending", lambda state: {})
        interrupted_graph.add_edge(START, "first")
        interrupted_graph.add_edge("first", "pending")
        interrupted_graph.add_edge("pending", END)
        compiled = interrupted_graph.compile(
            checkpointer=MemorySaver(), interrupt_before=["pending"]
        )
        await compiled.ainvoke(
            {
                "query": "q",
                "messages": [{"role": "user", "content": "q", "id": "h"}],
                "outcome": "pending",
            },
            {"configurable": {"thread_id": "t-next"}},
        )
        store = MemoryTranscriptStore()
        await store.insert_user("t-next", "h-next", "q")
        interrupted = _client_for(compiled, store)[0].get("/threads/t-next")
        self.assertEqual(interrupted.json()["status"], "interrupted")

        idle_graph = await self._done_refused_graph()
        await idle_graph.ainvoke(
            {
                "query": "q",
                "messages": [{"role": "user", "content": "q", "id": "h"}],
                "outcome": "done",
            },
            {"configurable": {"thread_id": "t-idle-next"}},
        )
        idle_store = MemoryTranscriptStore()
        await idle_store.insert_user("t-idle-next", "h-idle-next", "q")
        idle = _client_for(idle_graph, idle_store)[0].get("/threads/t-idle-next")
        self.assertEqual(idle.json()["status"], "idle")

    async def test_steps_replay_includes_stored_nodes(self) -> None:
        nodes = [{"name": "search", "query_used": "LoRA"}]
        store = MemoryTranscriptStore()
        await store.insert_assistant_turn(
            "tid-steps",
            "ai-steps",
            _assistant_doc(steps={"count": 3, "elapsed_ms": 90, "nodes": nodes}),
        )
        compiled = await self._done_refused_graph()
        messages = (
            _client_for(compiled, store)[0].get("/threads/tid-steps").json()["messages"]
        )
        steps = next(row for row in messages if row.get("activityType") == "STEPS")
        self.assertEqual(steps["content"]["count"], 3)
        self.assertEqual(steps["content"]["elapsed_ms"], 90)
        self.assertEqual(steps["content"]["nodes"], nodes)
        self.assertNotEqual(steps["content"]["nodes"], [])

    async def test_two_done_turns_sources_are_per_turn(self) -> None:
        store = MemoryTranscriptStore()
        first = _assistant_doc(
            content="first [1]",
            citations=[_citation(1, "first-excerpt")],
        )
        second = _assistant_doc(
            content="second [1]",
            citations=[_citation(1, "second-excerpt")],
        )
        await store.insert_assistant_turn("tid-two", "ai-1", first)
        await store.insert_assistant_turn("tid-two", "ai-2", second)
        compiled = await self._done_refused_graph()
        messages = (
            _client_for(compiled, store)[0].get("/threads/tid-two").json()["messages"]
        )
        sources = [row for row in messages if row.get("activityType") == "SOURCES"]
        assistants = [row for row in messages if row["role"] == "assistant"]
        self.assertEqual(len(sources), 2)
        self.assertEqual(len(assistants), 2)
        first_sources_index = messages.index(sources[0])
        first_assistant_index = messages.index(assistants[0])
        self.assertEqual(first_sources_index, first_assistant_index + 1)
        self.assertEqual(sources[0]["content"]["items"][0]["excerpt"], "first-excerpt")
        self.assertEqual(sources[1]["content"]["items"][0]["excerpt"], "second-excerpt")
