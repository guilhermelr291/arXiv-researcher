"""AGUI-02: POST /agent HTTP contract."""

from __future__ import annotations

import json
import unittest
import unittest.mock
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plan_based_researcher.api.agui import AguiAdapter, stream_headers
from plan_based_researcher.api.cors import DEFAULT_WEB_ORIGIN, install_cors
from ag_ui.encoder import EventEncoder

from plan_based_researcher.api.deps import get_graph, get_settings, get_transcript
from plan_based_researcher.api.routes import router
from plan_based_researcher.main import create_app
from tests.transcript_memory import MemoryTranscriptStore


def parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:].strip()))
    return events


def _body(**overrides) -> dict:
    payload = {
        "threadId": "tid-1",
        "runId": "run-1",
        "messages": [
            {"id": "u1", "role": "user", "content": "What is LoRA?"}
        ],
        "tools": [],
        "context": [],
        "forwardedProps": {},
    }
    payload.update(overrides)
    return payload


def _event_type_name(event: object) -> str:
    raw = getattr(event, "type", "")
    return str(getattr(raw, "value", raw) or "")


class RecordingGraph:
    def __init__(self, items=(), next_nodes=(), raise_exc=None, hang=False) -> None:
        self.items = list(items)
        self.next_nodes = next_nodes
        self.raise_exc = raise_exc
        self.hang = hang
        self.recorded = None
        self.transcript: MemoryTranscriptStore | None = None
        self.items_at_astream = None

    def initial_graph_state(self, query: str) -> dict:
        return {"query": query, "messages": [{"role": "user", "content": query}]}

    async def aget_state(self, config):
        return SimpleNamespace(next=self.next_nodes, values={"messages": []})

    def astream(self, input, config=None, **kwargs):
        self.recorded = {"input": input, "config": config, **kwargs}
        if self.transcript is not None:
            self.items_at_astream = list(self.transcript.items)
        graph = self

        class Stream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                if graph.raise_exc:
                    raise graph.raise_exc
                if graph.hang:
                    import asyncio

                    await asyncio.sleep(60)
                if not graph.items:
                    raise StopAsyncIteration
                return graph.items.pop(0)

        return Stream()


def _client(graph=None, timeout=30, store=None):
    app = FastAPI()
    install_cors(app, DEFAULT_WEB_ORIGIN)
    app.include_router(router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    fake_store = store if store is not None else MemoryTranscriptStore()
    fake = graph or RecordingGraph(
        [("custom", {"event": "done", "data": {"outcome": "done"}})]
    )
    fake.transcript = fake_store
    app.dependency_overrides[get_graph] = lambda: fake
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        research_timeout_seconds=timeout
    )
    app.dependency_overrides[get_transcript] = lambda: fake_store
    return TestClient(app), fake


class AgentRouteTest(unittest.TestCase):
    def test_valid_run_starts_with_run_started(self) -> None:
        client, _fake = _client()
        response = client.post("/agent", json=_body())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        events = parse_sse(response.text)
        self.assertEqual(events[0]["type"], "RUN_STARTED")
        self.assertEqual(events[0]["threadId"], "tid-1")
        self.assertEqual(events[0]["runId"], "run-1")

    def test_invalid_body_is_422(self) -> None:
        client, fake = _client()
        response = client.post("/agent", json={"not": "run-agent-input"})
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.json().get("detail"))
        self.assertIsNone(fake.recorded)

    def test_empty_messages_without_resume_is_400(self) -> None:
        client, fake = _client()
        response = client.post(
            "/agent",
            json=_body(messages=[], forwardedProps={}),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(),
            {"detail": "one user message or resume is required"},
        )
        self.assertIsNone(fake.recorded)

    def test_resume_idle_is_409(self) -> None:
        client, fake = _client(RecordingGraph(next_nodes=()))
        response = client.post(
            "/agent",
            json=_body(messages=[], forwardedProps={"resume": True}),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"detail": "nothing to resume"})
        self.assertIsNone(fake.recorded)

    def test_resume_calls_astream_with_none(self) -> None:
        client, fake = _client(
            RecordingGraph(
                items=[("custom", {"event": "done", "data": {"outcome": "done"}})],
                next_nodes=("execute",),
            )
        )
        response = client.post(
            "/agent",
            json=_body(messages=[], forwardedProps={"resume": True}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(fake.recorded["input"])
        self.assertEqual(
            fake.recorded["config"]["configurable"]["thread_id"], "tid-1"
        )

    def test_iterator_raise_is_run_error(self) -> None:
        client, _fake = _client(
            RecordingGraph(raise_exc=RuntimeError("boom"))
        )
        response = client.post("/agent", json=_body())
        self.assertEqual(response.status_code, 200)
        events = parse_sse(response.text)
        error = next(e for e in events if e["type"] == "RUN_ERROR")
        self.assertEqual(error["message"], "boom")
        self.assertFalse(response.text.endswith("incomplete"))

    def test_timeout_is_run_finished_insufficient(self) -> None:
        client, _fake = _client(RecordingGraph(hang=True), timeout=0.05)
        response = client.post("/agent", json=_body())
        events = parse_sse(response.text)
        finished = next(e for e in events if e["type"] == "RUN_FINISHED")
        self.assertEqual(finished["result"]["outcome"], "insufficient")
        self.assertEqual(finished["result"]["reason"], "timeout")

    def test_frames_use_event_encoder(self) -> None:
        client, _fake = _client()
        response = client.post("/agent", json=_body())
        self.assertIn("data: {", response.text)
        self.assertIn('"type":"RUN_STARTED"', response.text.replace(" ", ""))
        events = parse_sse(response.text)
        self.assertEqual(events[0]["type"], "RUN_STARTED")

    def test_agent_stream_headers(self) -> None:
        client, _fake = _client()
        response = client.post("/agent", json=_body())
        for key, value in stream_headers().items():
            self.assertEqual(response.headers[key], value)

    def test_cors_allows_web_origin(self) -> None:
        client, _fake = _client()
        response = client.post(
            "/agent",
            json=_body(),
            headers={"Origin": DEFAULT_WEB_ORIGIN},
        )
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            DEFAULT_WEB_ORIGIN,
        )

    def test_options_agent_is_200(self) -> None:
        client, _fake = _client()
        response = client.options(
            "/agent",
            headers={
                "Origin": DEFAULT_WEB_ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
        self.assertEqual(response.status_code, 200)

    def test_research_route_absent_health_present(self) -> None:
        client, _fake = _client()
        missing = client.post("/research", json={"query": "q", "thread_id": "t"})
        self.assertEqual(missing.status_code, 404)
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        source = create_app
        from plan_based_researcher.main import create_app as factory
        import inspect

        text = inspect.getsource(factory)
        self.assertIn("/health", text)
        self.assertNotIn("/research", text)

    def test_post_uses_body_thread_id_as_store_and_checkpoint_id(self) -> None:
        client, fake = _client()
        response = client.post("/agent", json=_body(threadId="tid-1"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            fake.recorded["config"]["configurable"]["thread_id"], "tid-1"
        )
        self.assertEqual(fake.transcript.threads["tid-1"].thread_id, "tid-1")
        self.assertTrue(
            all(item.thread_id == "tid-1" for item in fake.transcript.items)
        )

    def test_non_resume_inserts_user_before_astream(self) -> None:
        client, fake = _client()
        response = client.post("/agent", json=_body())
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(fake.items_at_astream)
        users = [
            item for item in fake.items_at_astream if item.kind == "user"
        ]
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].id, "u1")
        self.assertEqual(users[0].payload["content"], "What is LoRA?")

    def test_first_user_title_is_eighty_chars(self) -> None:
        for length in (80, 100):
            with self.subTest(length=length):
                store = MemoryTranscriptStore()
                content = "x" * length
                client, fake = _client(store=store)
                response = client.post(
                    "/agent",
                    json=_body(
                        threadId=f"tid-{length}",
                        messages=[{"id": "u1", "role": "user", "content": content}],
                    ),
                )
                self.assertEqual(response.status_code, 200)
                title = fake.transcript.threads[f"tid-{length}"].title
                self.assertEqual(title, content[:80])
                self.assertEqual(len(title), 80)

    def test_resume_does_not_insert_user(self) -> None:
        client, fake = _client(
            RecordingGraph(
                items=[("custom", {"event": "done", "data": {"outcome": "done"}})],
                next_nodes=("execute",),
            )
        )
        response = client.post(
            "/agent",
            json=_body(messages=[], forwardedProps={"resume": True}),
        )
        self.assertEqual(response.status_code, 200)
        users = [item for item in fake.transcript.items if item.kind == "user"]
        self.assertEqual(users, [])

    def test_assistant_turn_exists_before_run_finished(self) -> None:
        store = MemoryTranscriptStore()
        orig_encode = EventEncoder.encode

        def encode(self, event):
            if _event_type_name(event) == "RUN_FINISHED":
                store.log.append("run_finished")
            return orig_encode(self, event)

        client, _fake = _client(store=store)
        with unittest.mock.patch.object(EventEncoder, "encode", encode):
            response = client.post("/agent", json=_body())
        self.assertEqual(response.status_code, 200)
        self.assertIn("assistant_turn", store.log)
        self.assertIn("run_finished", store.log)
        self.assertLess(store.log.index("assistant_turn"), store.log.index("run_finished"))

    def test_assistant_turn_exists_before_run_error(self) -> None:
        store = MemoryTranscriptStore()
        orig_encode = EventEncoder.encode

        def encode(self, event):
            if _event_type_name(event) == "RUN_ERROR":
                store.log.append("run_error")
            return orig_encode(self, event)

        client, _fake = _client(
            RecordingGraph(raise_exc=RuntimeError("boom")), store=store
        )
        with unittest.mock.patch.object(EventEncoder, "encode", encode):
            response = client.post("/agent", json=_body())
        self.assertEqual(response.status_code, 200)
        self.assertIn("assistant_turn", store.log)
        self.assertIn("run_error", store.log)
        self.assertLess(store.log.index("assistant_turn"), store.log.index("run_error"))

    def test_assistant_turn_id_is_writer_message_id(self) -> None:
        client, fake = _client(
            RecordingGraph(
                items=[
                    (
                        "updates",
                        {"execute": {"writer_message_id": "msg-writer-1"}},
                    ),
                    (
                        "custom",
                        {
                            "event": "answer_start",
                            "data": {"message_id": "msg-writer-1"},
                        },
                    ),
                    (
                        "custom",
                        {"event": "done", "data": {"outcome": "done"}},
                    ),
                ]
            )
        )
        response = client.post("/agent", json=_body())
        self.assertEqual(response.status_code, 200)
        turns = [
            item
            for item in fake.transcript.items
            if item.kind == "assistant_turn"
        ]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].id, "msg-writer-1")

    def test_timeout_assistant_turn_id_is_run_id(self) -> None:
        client, fake = _client(RecordingGraph(hang=True), timeout=0.05)
        response = client.post("/agent", json=_body(runId="run-timeout"))
        events = parse_sse(response.text)
        finished = next(e for e in events if e["type"] == "RUN_FINISHED")
        self.assertEqual(finished["result"]["outcome"], "insufficient")
        self.assertEqual(finished["result"]["reason"], "timeout")
        turns = [
            item
            for item in fake.transcript.items
            if item.kind == "assistant_turn"
        ]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0].id, "run-timeout")
        self.assertEqual(turns[0].payload["outcome"], "insufficient")
