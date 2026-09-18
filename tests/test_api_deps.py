"""STRM-07: FastAPI Depends for the compiled graph."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from plan_based_researcher.api.deps import get_graph


class ApiDepsTest(unittest.TestCase):
    def test_get_graph_returns_app_state_graph(self) -> None:
        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(graph=sentinel))
        )
        self.assertIs(get_graph(request), sentinel)
