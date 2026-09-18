"""STRM-07: FastAPI Depends for the compiled graph."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from plan_based_researcher.api.deps import get_graph
from plan_based_researcher.config import DEFAULT_WEB_ORIGIN, Settings, web_origin


class ApiDepsTest(unittest.TestCase):
    def test_get_graph_returns_app_state_graph(self) -> None:
        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(graph=sentinel))
        )
        self.assertIs(get_graph(request), sentinel)

    def test_settings_web_origin_matches_helper(self) -> None:
        settings = Settings(
            openai_api_key="k",
            voyage_api_key="v",
            database_url="postgres://localhost/test",
        )
        self.assertEqual(settings.web_origin, web_origin())
        self.assertEqual(DEFAULT_WEB_ORIGIN, "http://localhost:3000")
