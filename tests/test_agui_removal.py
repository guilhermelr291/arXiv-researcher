"""AGUI-06: old transport paths and chainlit dependency are gone."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "plan_based_researcher"
TESTS = ROOT / "tests"

_REMOVED = (
    SRC / "ui",
    SRC / "api" / "sse.py",
    SRC / "api" / "stream_dispatcher.py",
    SRC / "api" / "executor.py",
)


class AguiRemovalTest(unittest.TestCase):
    def test_old_transport_paths_absent(self) -> None:
        for path in _REMOVED:
            with self.subTest(path=str(path.relative_to(ROOT))):
                self.assertFalse(path.exists(), path)

    def test_pyproject_drops_chainlit_adds_ag_ui(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn("chainlit", text)
        self.assertIn("ag-ui-protocol", text)

    def test_no_test_module_imports_removed_paths(self) -> None:
        banned = (
            "plan_based_researcher.ui",
            "plan_based_researcher.api.sse",
            "plan_based_researcher.api.stream_dispatcher",
            "plan_based_researcher.api.executor",
        )
        for path in TESTS.glob("test_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertFalse(
                        any(node.module == b or node.module.startswith(b + ".") for b in banned),
                        f"{path.name} imports {node.module}",
                    )
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(
                            any(alias.name == b or alias.name.startswith(b + ".") for b in banned),
                            f"{path.name} imports {alias.name}",
                        )

    def test_discover_count_not_below_190(self) -> None:
        loader = unittest.defaultTestLoader
        suite = loader.discover(str(TESTS))
        count = suite.countTestCases()
        self.assertGreaterEqual(count, 190)
