"""Graph nodes do not import the transcript store; recents.ts is gone."""

from __future__ import annotations

import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_NODES = _ROOT / "src" / "plan_based_researcher" / "graph" / "nodes"
_RECENTS = _ROOT / "web" / "lib" / "recents.ts"


class TranscriptIsolationTest(unittest.TestCase):
    def test_graph_nodes_do_not_import_transcript(self) -> None:
        files = sorted(path for path in _NODES.glob("*.py"))
        self.assertEqual(len(files), 9)
        for path in files:
            with self.subTest(name=path.name):
                for line in path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped.startswith("import ") or stripped.startswith("from "):
                        self.assertNotIn(
                            "transcript",
                            stripped.lower(),
                            msg=f"{path.name}: {stripped}",
                        )

    def test_web_lib_recents_ts_absent(self) -> None:
        self.assertFalse(_RECENTS.exists())
