"""STRM-01, STRM-07: POST /research streams from the executor facade."""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from plan_based_researcher.api import routes
from plan_based_researcher.api.deps import get_executor, get_settings
from plan_based_researcher.api.routes import router
from plan_based_researcher.api.sse import SSE_HEADERS


class FakeExecutor:
    def __init__(self) -> None:
        self.called = None

    async def execute(self, query, thread_id, timeout_seconds):
        self.called = (query, thread_id, timeout_seconds)
        yield b"event: done\ndata: {}\n\n"


def _client(executor=None):
    app = FastAPI()
    app.include_router(router)
    fake = executor or FakeExecutor()
    app.dependency_overrides[get_executor] = lambda: fake
    app.dependency_overrides[get_settings] = lambda: SimpleNamespace(
        research_timeout_seconds=120
    )
    return TestClient(app), fake


class ResearchRouteTest(unittest.TestCase):
    def test_research_stream_headers(self) -> None:
        client, fake = _client()
        response = client.post("/research", json={"query": "q", "thread_id": "t1"})
        self.assertTrue(response.headers["content-type"].startswith("text/event-stream"))
        for key, value in SSE_HEADERS.items():
            self.assertEqual(response.headers[key], value)
        self.assertIsNotNone(fake.called)

    def test_missing_or_blank_thread_id_is_http_400(self) -> None:
        client, fake = _client()
        missing = client.post("/research", json={"query": "q"})
        self.assertEqual(missing.status_code, 400)
        self.assertIsNone(fake.called)
        blank = client.post("/research", json={"query": "q", "thread_id": " "})
        self.assertEqual(blank.status_code, 400)
        self.assertIsNone(fake.called)

    def test_non_json_body_is_http_400(self) -> None:
        client, fake = _client()
        response = client.post(
            "/research",
            content=b"not-json",
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(fake.called)

    def test_routes_source_has_no_astream(self) -> None:
        source = inspect.getsource(routes)
        self.assertNotIn("astream(", source)
        self.assertFalse(hasattr(routes, "_initial_state"))
        self.assertFalse(hasattr(routes, "iter_sse"))
        self.assertFalse(hasattr(routes, "_custom_payload"))
