"""AGUI-02: POST /agent HTTP contract."""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plan_based_researcher.api.agui import AguiAdapter, stream_headers
from plan_based_researcher.api.cors import DEFAULT_WEB_ORIGIN, install_cors
from plan_based_researcher.api.deps import get_graph, get_settings
from plan_based_researcher.api.routes import router
from plan_based_researcher.main import create_app


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


class RecordingGraph:
    def __init__(self, items=(), next_nodes=(), raise_exc=None, hang=False) -> None:
        self.items = list(items)
        self.next_nodes = next_nodes
        self.raise_exc = raise_exc
        self.hang = hang
        self.recorded = None

    def initial_graph_state(self, query: str) -> dict:
        return {"query": query, "messages": [{"role": "user", "content": query}]}

    async def aget_state(self, config):
        return SimpleNamespace(next=self.next_nodes, values={"messages": []})

    def astream(self, input, config=None, **kwargs):
        self.recorded = {"input": input, "config": config, **kwargs}
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


def _client(graph=None, timeout=30):
    app = FastAPI()
    install_cors(app, DEFAULT_WEB_ORIGIN)
    app.include_router(router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    fake = graph or RecordingGraph(
        [("custom", {"event": "done", "data": {"outcome": "done"}})]
    )
    app.dependency_overrides[get_graph] = lambda: fake
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        research_timeout_seconds=timeout
    )
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
