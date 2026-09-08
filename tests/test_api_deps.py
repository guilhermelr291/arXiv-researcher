"""STRM-07: FastAPI Depends for ResearchExecutor."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

from plan_based_researcher.api.deps import get_executor


class ApiDepsTest(unittest.TestCase):
    def test_get_executor_returns_app_state_executor(self) -> None:
        sentinel = object()
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(executor=sentinel))
        )
        self.assertIs(get_executor(request), sentinel)
