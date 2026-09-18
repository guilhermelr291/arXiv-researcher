"""AGUI-06 AC 73: AGENTS.md names the new transport and invariants."""

from __future__ import annotations

import unittest
from pathlib import Path

_AGENTS = Path(__file__).resolve().parents[1] / "AGENTS.md"


class AguiDocsTest(unittest.TestCase):
    def test_agents_md_agent_threads_web_invariants(self) -> None:
        text = _AGENTS.read_text(encoding="utf-8")
        self.assertIn("/agent", text)
        self.assertIn("/threads", text)
        self.assertIn("web/", text)
        invariants = {
            1: "web/ is HTTP-only",
            6: "packed in this thread",
            8: "halt_before_writer",
            9: "astream",
        }
        for number, needle in invariants.items():
            with self.subTest(invariant=number):
                self.assertIn(needle, text)
        self.assertIn("stream_mode", text)
        self.assertNotIn("StreamDispatcher", text)
        self.assertNotIn("chainlit run", text.lower())
